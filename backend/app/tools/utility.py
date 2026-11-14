"""
Utility tools per ATLAS AI v3.0.

Tutti i tool funzionano con servizi gratuiti:
- ricerca web: DuckDuckGo (libreria `ddgs`/`duckduckgo-search`, fallback HTML)
- notizie: NewsAPI se configurata, altrimenti Google News RSS
- ora: fusi orari IANA via `zoneinfo` (nessuna rete richiesta)
- geolocalizzazione IP: ipwho.is (HTTPS, gratuito) con fallback ip-api.com
- calcolatrice: parser AST safe (niente eval)
"""
from __future__ import annotations

import ast
import ipaddress
import operator
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from app.core.logging_config import get_logger

log = get_logger(__name__)

# ---------------- Import opzionali (graceful degradation) ----------------
try:  # nuova libreria (rinominata da duckduckgo-search)
    from ddgs import DDGS  # type: ignore[import-not-found]

    DDGS_AVAILABLE = True
except ImportError:  # pragma: no cover - dipende dall'ambiente
    try:
        from duckduckgo_search import DDGS  # type: ignore[import-not-found]

        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        DDGS = None  # type: ignore[assignment,misc]

try:
    import wikipedia  # type: ignore[import-not-found]

    wikipedia.set_lang("it")
    WIKIPEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - ambiente senza dipendenza
    WIKIPEDIA_AVAILABLE = False
    wikipedia = None  # type: ignore[assignment]

_OP_MAP: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_MAX_EXPRESSION_LEN = 200


# ---------------- Calcolatrice safe ----------------
def _safe_eval_node(node: ast.AST) -> Any:
    """Valuta in modo ricorsivo un AST di sola espressione matematica."""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OP_MAP:
            raise ValueError(f"Operatore non consentito: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Divisione per zero non consentita")
        if op_type is ast.Pow and (abs(left) > 10**6 or right > 100):
            raise ValueError("Esponenziale troppo grande (overflow protection)")
        return _OP_MAP[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OP_MAP:
            raise ValueError(f"Operatore unario non consentito: {op_type.__name__}")
        return _OP_MAP[op_type](_safe_eval_node(node.operand))  # type: ignore[call-arg]
    raise ValueError("Tipo di nodo AST non consentito")


def _safe_math_eval(expr: str) -> float:
    """Parser matematico safe senza eval. Supporta: +, -, *, /, //, %, **, ()."""
    if len(expr) > _MAX_EXPRESSION_LEN:
        raise ValueError(f"Espressione troppo lunga (> {_MAX_EXPRESSION_LEN} caratteri)")
    tree = ast.parse(expr, mode="eval")
    result = _safe_eval_node(tree)
    if isinstance(result, (int, float)):
        return float(result)
    raise ValueError("Risultato non numerico")


def calcolatrice(espressione: str) -> str:
    """Calcola un'espressione matematica usando parser AST safe (NO eval).

    Args:
        espressione: Espressione come "15 * 3 + 20 / 4" oppure "3,5 + 2".
    """
    try:
        if not espressione:
            return "Fornisci un'espressione da calcolare (es. 15 * 3 + 20 / 4)."
        cleaned = (
            espressione.replace("x", "*")
            .replace("X", "*")
            .replace("×", "*")
            .replace("÷", "/")
            .replace(",", ".")
            .replace(" ", "")
        )
        if not cleaned:
            return "Espressione vuota."
        result = _safe_math_eval(cleaned)
        formatted = f"{result:g}"
        return f"{espressione} = {formatted}"
    except ZeroDivisionError:
        return "Impossibile dividere per zero."
    except (SyntaxError, ValueError) as exc:
        return f"Espressione non valida: {exc}. Usa formato: 15 * 3 + 20 / 4"
    except Exception as exc:  # pragma: no cover
        log.exception("calcolatrice errore inatteso: %s", exc)
        return "Errore nel calcolo. Riprova con un'espressione più semplice."


# ---------------- Ricerca web ----------------
def _ddg_html_search(query: str, max_results: int) -> list[dict[str, str]]:
    """Ricerca DuckDuckGo via HTML: funziona senza API key e senza librerie extra."""
    response = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        },
        timeout=12,
    )
    response.raise_for_status()
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(response.text, "lxml")
    results: list[dict[str, str]] = []
    for item in soup.select(".result")[:max_results]:
        link = item.select_one(".result__a")
        snippet = item.select_one(".result__snippet")
        if not link:
            continue
        results.append(
            {
                "title": link.get_text(" ", strip=True),
                "body": snippet.get_text(" ", strip=True) if snippet else "",
                "href": link.get("href", ""),
            }
        )
    return results


def web_search(query: str, max_results: int = 4) -> str:
    """Cerca informazioni sul web in tempo reale (DuckDuckGo, gratuito).

    Args:
        query: Testo da cercare.
        max_results: Numero massimo di risultati (1-10).
    """
    if not query or not query.strip():
        return "Cosa devo cercare? Scrivi una domanda o un argomento."
    limit = max(1, min(int(max_results or 4), 10))
    results: list[dict[str, str]] = []

    if DDGS_AVAILABLE and DDGS is not None:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=limit))
        except Exception as exc:
            log.warning("DuckDuckGo libreria fallita (%s): provo HTML", exc)
            results = []

    if not results:
        try:
            results = _ddg_html_search(query, limit)
        except Exception as exc:
            log.warning("web_search HTML fallita: %s", exc)
            return "Errore di rete durante la ricerca. Riprova più tardi."

    if not results:
        return "Nessun risultato trovato."

    righe: list[str] = []
    for index, item in enumerate(results[:limit], 1):
        title = item.get("title") or "(no titolo)"
        body = (item.get("body") or "")[:220]
        href = item.get("href") or item.get("url") or ""
        riga = f"{index}. **{title}**\n   {body}"
        if href:
            riga += f"\n   🔗 {href}"
        righe.append(riga)
    return "\n\n".join(righe)


def cerca_wikipedia(query: str, lingua: str = "it") -> str:
    """Cerca su Wikipedia nella lingua specificata.

    Args:
        query: Voce da cercare.
        lingua: Codice lingua Wikipedia (default "it").
    """
    if not WIKIPEDIA_AVAILABLE or wikipedia is None:
        return "Wikipedia non disponibile in questo ambiente (pacchetto `wikipedia` non installato)."
    try:
        wikipedia.set_lang((lingua or "it")[:5])
        page = wikipedia.summary(query, sentences=3)
        return str(page) if page else "Nessun risultato su Wikipedia."
    except wikipedia.exceptions.PageError:
        return f"Nessuna voce Wikipedia trovata per '{query}'."
    except wikipedia.exceptions.DisambiguationError as exc:
        options = ", ".join(str(o) for o in list(getattr(exc, "options", []))[:6])
        return f"Voce ambigua. Possibili alternative: {options}"
    except requests.RequestException as exc:
        log.warning("cerca_wikipedia rete: %s", exc)
        return "Impossibile raggiungere Wikipedia al momento."
    except Exception as exc:
        log.exception("cerca_wikipedia: %s", exc)
        return "Errore nella ricerca Wikipedia."


# ---------------- Notizie ----------------
def _news_rss(argomento: str, page_size: int) -> str:
    """Notizie reali e gratuite da Google News RSS (nessuna chiave)."""
    url = (
        "https://news.google.com/rss/search?q="
        f"{quote(argomento)}&hl=it&gl=IT&ceid=IT:it"
    )
    response = requests.get(url, timeout=10, headers={"User-Agent": "ATLAS-AI/3.0"})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = root.findall(".//item")[:page_size]
    if not items:
        return f"Nessuna notizia recente su '{argomento}'."
    righe: list[str] = []
    for item in items:
        titolo = (item.findtext("title") or "Senza titolo").strip()
        link = (item.findtext("link") or "").strip()
        data = (item.findtext("pubDate") or "").strip()
        riga = f"📰 {titolo}"
        if data:
            riga += f"\n   🕐 {data}"
        if link:
            riga += f"\n   🔗 {link}"
        righe.append(riga)
    return "\n\n".join(righe)


def get_news(argomento: str = "tecnologia", page_size: int = 5) -> str:
    """Ultime notizie su un argomento (NewsAPI se configurata, altrimenti Google News).

    Args:
        argomento: Tema delle notizie (es. "Italia", "economia").
        page_size: Numero di notizie (1-10).
    """
    limit = max(1, min(int(page_size or 5), 10))
    api_key = os.getenv("NEWSAPI_KEY", "").strip()
    if api_key and api_key.lower() != "demo":
        try:
            response = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": argomento,
                    "language": "it",
                    "pageSize": limit,
                    "sortBy": "publishedAt",
                    "apiKey": api_key,
                },
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()
            articles = payload.get("articles") or []
            if articles:
                return "\n\n".join(
                    f"📰 {a.get('title', 'Senza titolo')}\n   {(a.get('description') or '')[:180]}"
                    for a in articles[:limit]
                )
        except (requests.RequestException, ValueError) as exc:
            log.warning("NewsAPI fallita, uso Google News: %s", exc)

    try:
        return _news_rss(argomento, limit)
    except requests.RequestException as exc:
        log.warning("get_news RSS fallita: %s", exc)
        return "Impossibile recuperare le notizie al momento (errore di rete)."
    except ET.ParseError as exc:
        log.warning("get_news RSS non valido: %s", exc)
        return "Errore nel recupero delle notizie."


# ---------------- Ora / fuso orario ----------------
def get_time_timezone(timezone: str = "Europe/Rome") -> str:
    """Ora esatta in qualsiasi fuso orario IANA (calcolo locale, nessuna rete).

    Args:
        timezone: Nome IANA, es. "Europe/Rome", "America/New_York".
    """
    nome = (timezone or "Europe/Rome").strip()
    try:
        now = datetime.now(ZoneInfo(nome))
    except (ZoneInfoNotFoundError, ValueError):
        return f"Fuso orario '{nome}' non valido. Esempi: Europe/Rome, Europe/London, America/New_York."
    return f"🕐 {nome.replace('_', ' ')}: {now.strftime('%H:%M:%S')} ({now.strftime('%d/%m/%Y')})"


# ---------------- Geolocalizzazione IP ----------------
def get_ip_info(ip: str = "") -> str:
    """Geolocalizzazione di un indirizzo IP (vuoto = IP pubblico del server).

    Args:
        ip: Indirizzo IPv4/IPv6 da analizzare, vuoto per l'IP corrente.
    """
    try:
        if ip:
            ipaddress.ip_address(ip)
    except ValueError:
        return "Indirizzo IP non valido."

    target = quote(ip) if ip else ""
    try:
        response = requests.get(f"https://ipwho.is/{target}", timeout=8)
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            return (
                f"🌐 IP: {data.get('ip')} | {data.get('city', '?')}, "
                f"{data.get('country', '?')} | ISP: {(data.get('connection') or {}).get('isp', '?')}"
            )
    except (requests.RequestException, ValueError) as exc:
        log.warning("get_ip_info ipwho.is: %s", exc)

    try:
        url = f"http://ip-api.com/json/{target}" if target else "http://ip-api.com/json/"
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            return (
                f"🌐 IP: {data.get('query')} | {data.get('city', '?')}, "
                f"{data.get('country', '?')} | ISP: {data.get('isp', '?')}"
            )
    except (requests.RequestException, ValueError) as exc:
        log.warning("get_ip_info ip-api: %s", exc)

    return "Errore di rete durante la richiesta IP."


def genera_qr_code(testo: str) -> str:
    """Genera l'URL di un QR code (immagine 300x300) per un testo.

    Args:
        testo: Contenuto da codificare (URL, testo, numero).
    """
    if not testo:
        return "Fornisci del testo per generare il QR code."
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(testo)}"
