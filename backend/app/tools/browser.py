"""
Tool browser per l'agente ATLAS AI.

Questi strumenti controllano un Chromium headless reale: aprono pagine,
leggono testo/link/moduli, cliccano, compilano campi e navigano. Non sono
scraping HTTP: eseguono JavaScript, quindi funzionano anche su siti dinamici
e richiedono una conferma esplicita prima di azioni sensibili.
"""
from __future__ import annotations

from typing import Callable

from app.core.logging_config import get_logger
from app.core.net_guard import UnsafeURLError
from app.core.settings import env_bool
from app.services.browser import (
    BrowserError,
    browser_profile,
    browser_service,
)

log = get_logger(__name__)


def _run(operation: Callable[[], str]) -> str:
    if not env_bool("BROWSER_ENABLED", default=True):
        return "❌ Browser disattivato dal server (BROWSER_ENABLED=false)."
    try:
        return operation()
    except UnsafeURLError as exc:
        return f"❌ URL non consentito: {exc}"
    except BrowserError as exc:
        return f"❌ Browser: {exc}"
    except Exception as exc:  # pragma: no cover - errori imprevisti di Chromium
        log.exception("Errore imprevisto del browser: %s", exc)
        return f"❌ Errore browser: {str(exc)[:300]}"


def _profile() -> str:
    return browser_profile.get()


def browser_apri(url: str) -> str:
    """Apre un sito web in un browser Chromium reale e ne restituisce il contenuto.

    Usa questo tool quando devi visitare una pagina, interagire con un sito
    dinamico, compilare un modulo o quando web_search/fetch non bastano.
    Restituisce titolo, URL finale, testo visibile, link principali, campi
    compilabili e bottoni. Dopo l'apertura puoi usare browser_clicca,
    browser_scrivi, browser_seleziona, browser_scorri e browser_vedi.

    Args:
        url: Indirizzo completo del sito (es. "https://www.example.com").
    """
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    return _run(lambda: browser_service.open_page(_profile(), url))


def browser_vedi() -> str:
    """Legge la pagina attualmente aperta nel browser.

    Restituisce URL, titolo, testo visibile aggiornato, link e campi
    compilabili. Usalo dopo un click, uno scroll o un caricamento dinamico
    per capire cosa è cambiato prima di compiere la prossima azione.
    """
    return _run(lambda: browser_service.view(_profile()))


def browser_clicca(elemento: str) -> str:
    """Clicca un elemento nella pagina aperta.

    Args:
        elemento: Selettore CSS (es. "#accedi", "button[type=submit]") oppure
            testo visibile del bottone/link (es. "Accetta cookie", "Cerca").
            Se il testo è ambiguo viene scelto il primo elemento visibile.
    """
    return _run(lambda: browser_service.click(_profile(), elemento))


def browser_scrivi(campo: str, testo: str, invio: bool = False) -> str:
    """Scrive in un campo di testo o textarea della pagina aperta.

    Args:
        campo: Selettore CSS, nome del campo, label o placeholder
            (es. "q", "Cerca", "#email").
        testo: Testo da inserire nel campo.
        invio: Se true preme Invio dopo aver scritto (utile per le ricerche).
    """
    return _run(lambda: browser_service.fill(_profile(), campo, testo, bool(invio)))


def browser_seleziona(campo: str, valore: str) -> str:
    """Seleziona un'opzione in un menu a tendina (select) della pagina aperta.

    Args:
        campo: Selettore CSS, nome, label o placeholder del select.
        valore: Testo visibile oppure value dell'opzione da selezionare.
    """
    return _run(lambda: browser_service.select(_profile(), campo, valore))


def browser_scorri(direzione: str = "giu") -> str:
    """Scorre la pagina aperta per caricare altro contenuto.

    Args:
        direzione: "giu" (default) oppure "su".
    """
    return _run(lambda: browser_service.scroll(_profile(), direzione))


def browser_indietro() -> str:
    """Torna alla pagina precedente nella cronologia del browser."""
    return _run(lambda: browser_service.back(_profile()))


def browser_chiudi() -> str:
    """Chiude la sessione browser del profilo corrente e libera le risorse."""
    return _run(lambda: browser_service.close(_profile()))


BROWSER_TOOLS = [
    browser_apri,
    browser_vedi,
    browser_clicca,
    browser_scrivi,
    browser_seleziona,
    browser_scorri,
    browser_indietro,
    browser_chiudi,
]

__all__ = [
    "BROWSER_TOOLS",
    "browser_apri",
    "browser_vedi",
    "browser_clicca",
    "browser_scrivi",
    "browser_seleziona",
    "browser_scorri",
    "browser_indietro",
    "browser_chiudi",
]
