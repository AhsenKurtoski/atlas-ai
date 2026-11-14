"""
Agente browser server-side per ATLAS AI.

Un unico thread dedicato possiede Playwright/Chromium: le API sync di
Playwright non sono thread-safe, mentre gli endpoint FastAPI girano in un
threadpool. Il servizio serializza i comandi, mantiene una sessione isolata
per profilo (cookie e pagine separati) e la chiude dopo inattività.

Sicurezza:
- ogni navigazione passa da ``validate_url`` (protezione SSRF);
- ogni richiesta del browser verso host privati viene bloccata a livello di
  routing, anche per redirect, iframe e XHR;
- le pagine web sono dati non attendibili: il prompt del modello vieta di
  seguire istruzioni contenute nel testo e di inserire credenziali senza
  conferma esplicita.
"""
from __future__ import annotations

import asyncio
import atexit
import ipaddress
import queue
import re
import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from app.core.logging_config import get_logger
from app.core.net_guard import UnsafeURLError, allow_private_fetch, validate_url
from app.core.settings import env_bool, env_int

log = get_logger(__name__)

# Profilo corrente impostato dall'endpoint /chat: le sessioni browser non
# devono mai condividere cookie o pagine tra membri della famiglia.
browser_profile: ContextVar[str] = ContextVar("atlas_browser_profile", default="default")


class BrowserError(RuntimeError):
    """Errore recuperabile dell'agente browser."""


class BrowserUnavailable(BrowserError):
    """Playwright/Chromium non installato o non avviabile."""


@dataclass
class _Session:
    context: Any
    page: Any
    touched: float


def _blocked_host(host: str) -> bool:
    host = (host or "").strip().strip("[]").lower()
    if not host:
        return True
    if host in {"localhost", "localhost.localdomain"}:
        return True
    if host.endswith((".localhost", ".local", ".internal", ".home.arpa")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Un dominio pubblico va bene: la risoluzione DNS è già stata
        # verificata da validate_url sulla navigazione principale.
        return False
    return not ip.is_global


def _request_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"data", "blob", "about"}:
        return True
    if parsed.scheme not in {"http", "https"}:
        return False
    if allow_private_fetch():
        return True
    return not _blocked_host(parsed.hostname or "")


def _attr(value: str) -> str:
    """Valore sicuro per un selettore CSS tra doppi apici."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


class _BrowserWorker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="atlas-browser", daemon=True)
        self.jobs: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.error: str | None = None
        self._playwright: Any = None
        self._browser: Any = None
        self._sessions: dict[str, _Session] = {}
        self._ttl = max(60, env_int("BROWSER_SESSION_TTL", default=900))
        self._headless = env_bool("BROWSER_HEADLESS", default=True)
        self._nav_timeout = max(5000, env_int("BROWSER_NAV_TIMEOUT_MS", default=25000))
        self._action_timeout = max(2000, env_int("BROWSER_ACTION_TIMEOUT_MS", default=8000))

    # ---------- ciclo di vita ----------
    def run(self) -> None:  # pragma: no cover - dipende da Chromium
        try:
            # Su Windows il loop di default creato da Playwright in un thread
            # secondario può essere un SelectorEventLoop, che non supporta
            # subprocess: Chromium non partirebbe. Forziamo Proactor.
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            args = ["--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            if env_bool("BROWSER_NO_SANDBOX", default=False):
                args.append("--no-sandbox")
            self._browser = self._playwright.chromium.launch(headless=self._headless, args=args)
            log.info("Agente browser pronto (headless=%s)", self._headless)
        except Exception as exc:  # pragma: no cover - ambiente senza browser
            self.error = (
                "Chromium non disponibile. Esegui `python -m playwright install chromium` "
                f"nel backend. Dettaglio: {str(exc)[:300]}"
            )
            log.error("Browser non avviato: %s", exc)
        finally:
            self.ready.set()

        while True:
            job = self.jobs.get()
            if job is None:
                break
            fn, box = job
            try:
                box["result"] = fn()
            except BaseException as exc:  # noqa: BLE001 - inoltrato al chiamante
                box["error"] = exc
            finally:
                box["done"].set()

        self._close_all()

    def _close_all(self) -> None:
        for session in list(self._sessions.values()):
            try:
                session.context.close()
            except Exception:
                pass
        self._sessions.clear()
        try:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass

    # ---------- sessioni ----------
    def _cleanup(self) -> None:
        now = time.time()
        for profile, session in list(self._sessions.items()):
            expired = now - session.touched > self._ttl
            closed = session.page.is_closed()
            if expired or closed:
                try:
                    session.context.close()
                except Exception:
                    pass
                self._sessions.pop(profile, None)

    def _session(self, profile: str) -> _Session:
        self._cleanup()
        session = self._sessions.get(profile)
        if session is not None and not session.page.is_closed():
            session.touched = time.time()
            return session
        if self._browser is None:
            raise BrowserUnavailable(self.error or "Browser non inizializzato.")

        context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="it-IT",
            timezone_id="Europe/Rome",
            java_script_enabled=True,
            accept_downloads=False,
        )
        context.set_default_timeout(self._action_timeout)
        context.set_default_navigation_timeout(self._nav_timeout)
        context.route("**/*", self._route)
        page = context.new_page()
        page.on("dialog", lambda dialog: dialog.dismiss())
        session = _Session(context=context, page=page, touched=time.time())
        self._sessions[profile] = session
        return session

    @staticmethod
    def _route(route: Any) -> None:
        try:
            url = route.request.url
            if not _request_allowed(url):
                log.warning("Browser: richiesta privata bloccata (%s)", url[:120])
                route.abort("blockedbyclient")
                return
            # Le navigazioni (inclusi i redirect) vengono rivalidate con DNS:
            # un dominio pubblico che punta a 10.x/127.x non deve essere raggiunto.
            if route.request.is_navigation_request() and not allow_private_fetch():
                validate_url(url)
            route.continue_()
        except UnsafeURLError as exc:
            log.warning("Browser: navigazione SSRF bloccata (%s): %s", route.request.url[:120], exc)
            try:
                route.abort("blockedbyclient")
            except Exception:
                pass
        except Exception:
            try:
                route.abort()
            except Exception:
                pass

    def _active_page(self, profile: str) -> Any:
        self._cleanup()
        session = self._sessions.get(profile)
        if session is None or session.page.is_closed():
            raise BrowserError("Nessuna pagina aperta. Usa prima browser_apri.")
        session.touched = time.time()
        return session.page

    # ---------- azioni ----------
    def open_page(self, profile: str, url: str) -> str:
        validate_url(url)
        session = self._session(profile)
        page = session.page
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self._nav_timeout)
        except Exception as exc:
            if page.url in {"", "about:blank"}:
                raise BrowserError(f"Impossibile aprire {url}: {str(exc)[:250]}") from exc
        page.wait_for_timeout(800)
        validate_url(page.url)
        return self._snapshot(page, prefix=f"🌐 Aperto: {page.url}")

    def view(self, profile: str) -> str:
        page = self._active_page(profile)
        return self._snapshot(page)

    def click(self, profile: str, target: str) -> str:
        session = self._session(profile)
        page = session.page
        locator = self._resolve(page, target)
        before = {id(item) for item in session.context.pages}
        try:
            locator.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        locator.click(timeout=self._action_timeout)
        page.wait_for_timeout(700)
        new_pages = [item for item in session.context.pages if id(item) not in before]
        if new_pages:
            session.page = new_pages[-1]
            try:
                session.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
        else:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
        validate_url(session.page.url)
        return self._snapshot(
            session.page, prefix=f"✅ Cliccato «{target}». Pagina attuale: {session.page.url}"
        )

    def fill(self, profile: str, field: str, text: str, submit: bool = False) -> str:
        page = self._active_page(profile)
        locator = self._resolve_field(page, field)
        locator.fill(text, timeout=self._action_timeout)
        if submit:
            locator.press("Enter", timeout=self._action_timeout)
            page.wait_for_timeout(900)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            validate_url(page.url)
        return self._snapshot(
            page,
            prefix=(
                f"✅ Compilato «{field}»"
                + (" e inviato con Invio" if submit else "")
                + f". Pagina attuale: {page.url}"
            ),
        )

    def select(self, profile: str, field: str, value: str) -> str:
        page = self._active_page(profile)
        locator = self._resolve_field(page, field)
        try:
            locator.select_option(label=value, timeout=self._action_timeout)
        except Exception:
            locator.select_option(value=value, timeout=self._action_timeout)
        page.wait_for_timeout(400)
        return self._snapshot(page, prefix=f"✅ Selezionato «{value}» in «{field}».")

    def scroll(self, profile: str, direction: str) -> str:
        page = self._active_page(profile)
        down = direction.strip().lower() not in {"su", "up", "sopra", "indietro"}
        page.mouse.wheel(0, 800 if down else -800)
        page.wait_for_timeout(500)
        return self._snapshot(page, prefix="↕️ Scorrimento eseguito.")

    def back(self, profile: str) -> str:
        page = self._active_page(profile)
        try:
            response = page.go_back(wait_until="domcontentloaded", timeout=self._nav_timeout)
        except Exception:
            response = None
        if response is None:
            return "ℹ️ Nessuna pagina precedente nella cronologia del browser."
        page.wait_for_timeout(500)
        validate_url(page.url)
        return self._snapshot(page, prefix=f"⬅️ Tornato a: {page.url}")

    def close(self, profile: str) -> str:
        self._cleanup()
        session = self._sessions.pop(profile, None)
        if session is None:
            return "ℹ️ Nessuna sessione browser aperta."
        try:
            session.context.close()
        except Exception:
            pass
        return "✅ Browser chiuso per questo profilo."

    # ---------- risoluzione elementi ----------
    @staticmethod
    def _looks_like_css(target: str) -> bool:
        return (
            target.startswith(("#", ".", "[", "css=", "xpath=", "text="))
            or "[" in target
            or "]" in target
            or " > " in target
            or ":nth-" in target
        )

    def _resolve(self, page: Any, target: str) -> Any:
        target = target.strip()
        if not target:
            raise BrowserError("Specifica un elemento da cliccare (selettore CSS o testo visibile).")
        candidates = []
        if target.startswith(("css=", "xpath=", "text=")):
            candidates.append(page.locator(target))
        else:
            if self._looks_like_css(target):
                candidates.append(page.locator(target))
            candidates.extend(
                [
                    page.get_by_role("button", name=target, exact=False),
                    page.get_by_role("link", name=target, exact=False),
                    page.get_by_text(target, exact=False),
                ]
            )
        for locator in candidates:
            try:
                if locator.count() > 0:
                    return locator.first
            except Exception:
                continue
        raise BrowserError(
            f"Elemento non trovato: «{target}». Usa browser_vedi per vedere testo, link e campi disponibili."
        )

    def _resolve_field(self, page: Any, target: str) -> Any:
        target = target.strip()
        if not target:
            raise BrowserError("Specifica il campo da compilare (selettore, nome o placeholder).")
        candidates = [
            page.get_by_label(target, exact=False),
            page.get_by_placeholder(target, exact=False),
        ]
        if self._looks_like_css(target):
            candidates.append(page.locator(target))
        escaped = _attr(target)
        candidates.extend(
            [
                page.locator(f'input[name="{escaped}"]'),
                page.locator(f'textarea[name="{escaped}"]'),
                page.locator(f'[placeholder="{escaped}"]'),
            ]
        )
        for locator in candidates:
            try:
                if locator.count() > 0:
                    return locator.first
            except Exception:
                continue
        raise BrowserError(
            f"Campo non trovato: «{target}». Usa browser_vedi per l'elenco dei campi con i selettori."
        )

    # ---------- lettura pagina ----------
    def _snapshot(self, page: Any, prefix: str = "") -> str:
        try:
            title = page.title()
        except Exception:
            title = ""
        url = page.url
        try:
            text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            text = ""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        lines = [prefix or "🌐 Pagina corrente", f"URL: {url}", f"Titolo: {title}", ""]
        if text:
            lines.extend(["TESTO VISIBILE:", text[:2200], ""])
        else:
            lines.extend(["TESTO VISIBILE: (nessun testo; la pagina potrebbe richiedere login o JavaScript)", ""])

        links: list[str] = []
        seen: set[str] = set()
        try:
            anchors = page.locator("a[href]").all()[:60]
        except Exception:
            anchors = []
        for anchor in anchors:
            try:
                label = " ".join(anchor.inner_text(timeout=500).split())
                href = anchor.get_attribute("href", timeout=500) or ""
            except Exception:
                continue
            if not label or not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue
            absolute = urljoin(url, href)
            if absolute in seen or not absolute.startswith(("http://", "https://")):
                continue
            seen.add(absolute)
            links.append(f"- {label[:70]} → {absolute[:180]}")
            if len(links) >= 10:
                break
        if links:
            lines.extend(["LINK PRINCIPALI:", *links, ""])

        fields: list[str] = []
        try:
            controls = page.locator("input, textarea, select").all()[:30]
        except Exception:
            controls = []
        for control in controls:
            try:
                control_type = (control.get_attribute("type") or "").lower()
                if control_type in {"hidden", "submit", "button", "image", "file", "reset"}:
                    continue
                tag = control.evaluate("el => el.tagName.toLowerCase()")
                name = control.get_attribute("name") or ""
                element_id = control.get_attribute("id") or ""
                placeholder = control.get_attribute("placeholder") or ""
                label_text = ""
                try:
                    label_text = control.evaluate(
                        "el => el.labels && el.labels.length ? el.labels[0].innerText : ''"
                    )
                except Exception:
                    pass
                if element_id:
                    selector = f'[id="{_attr(element_id)}"]'
                elif name:
                    selector = f'{tag}[name="{_attr(name)}"]'
                elif placeholder:
                    selector = f'{tag}[placeholder="{_attr(placeholder)}"]'
                else:
                    continue
                descrizione = (label_text or placeholder or name or control_type or tag).strip()
                fields.append(f"- {descrizione[:60]} → {selector}")
                if len(fields) >= 10:
                    break
            except Exception:
                continue
        if fields:
            lines.extend(["CAMPI COMPILABILI:", *fields, ""])

        buttons: list[str] = []
        try:
            controls = page.locator("button, [role=button], input[type=submit]").all()[:20]
        except Exception:
            controls = []
        for control in controls:
            try:
                label = " ".join(control.inner_text(timeout=400).split())
                if not label:
                    label = control.get_attribute("value") or ""
                if label and label not in buttons:
                    buttons.append(label[:60])
                if len(buttons) >= 12:
                    break
            except Exception:
                continue
        if buttons:
            lines.extend(["BOTTONI:", ", ".join(buttons), ""])

        return "\n".join(lines)[:3800]


class BrowserService:
    """Facade thread-safe usata dai tool Gemini."""

    def __init__(self) -> None:
        self._worker: _BrowserWorker | None = None
        self._lock = threading.Lock()

    def _ensure_worker(self) -> _BrowserWorker:
        with self._lock:
            worker = self._worker
            if worker is not None and worker.is_alive():
                return worker
            worker = _BrowserWorker()
            self._worker = worker
            worker.start()
        if not worker.ready.wait(30):
            raise BrowserUnavailable("Avvio di Chromium troppo lento (timeout).")
        if worker.error:
            raise BrowserUnavailable(worker.error)
        return worker

    def _call(self, operation: Callable[[], str], timeout: int | None = None) -> str:
        worker = self._ensure_worker()
        box: dict[str, Any] = {"done": threading.Event()}
        worker.jobs.put((operation, box))
        limit = timeout or max(30, env_int("BROWSER_OPERATION_TIMEOUT", default=75))
        if not box["done"].wait(limit):
            raise BrowserError("Operazione browser troppo lenta: riprova con una pagina più semplice.")
        error = box.get("error")
        if error is not None:
            raise error
        return str(box.get("result") or "")

    def _operation(self, name: str, *args: Any) -> str:
        worker = self._ensure_worker()
        return str(getattr(worker, name)(*args))

    # ----- API usate dai tool -----
    def open_page(self, profile: str, url: str) -> str:
        return self._call(lambda: self._operation("open_page", profile, url))

    def view(self, profile: str) -> str:
        return self._call(lambda: self._operation("view", profile))

    def click(self, profile: str, target: str) -> str:
        return self._call(lambda: self._operation("click", profile, target))

    def fill(self, profile: str, field: str, text: str, submit: bool = False) -> str:
        return self._call(lambda: self._operation("fill", profile, field, text, submit))

    def select(self, profile: str, field: str, value: str) -> str:
        return self._call(lambda: self._operation("select", profile, field, value))

    def scroll(self, profile: str, direction: str) -> str:
        return self._call(lambda: self._operation("scroll", profile, direction))

    def back(self, profile: str) -> str:
        return self._call(lambda: self._operation("back", profile))

    def close(self, profile: str) -> str:
        worker = self._worker
        if worker is None or not worker.is_alive():
            return "ℹ️ Nessuna sessione browser aperta."
        return self._call(lambda: self._operation("close", profile))

    def shutdown(self) -> None:
        with self._lock:
            worker = self._worker
            self._worker = None
        if worker is None:
            return
        try:
            worker.jobs.put(None)
            worker.join(timeout=10)
        except Exception:
            pass


browser_service = BrowserService()
atexit.register(browser_service.shutdown)


def shutdown_browser() -> None:
    browser_service.shutdown()


__all__ = [
    "BrowserError",
    "BrowserUnavailable",
    "BrowserService",
    "browser_profile",
    "browser_service",
    "shutdown_browser",
]
