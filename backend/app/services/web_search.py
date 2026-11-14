"""
Wrapper ricerche web (DuckDuckGo + BeautifulSoup).

Usato principalmente da codice legacy; il router AI usa gli strumenti
equivalenti in `app.tools.utility`. Gli import opzionali sono protetti: senza
la libreria `ddgs`/`duckduckgo-search` si usa comunque il fallback HTML.
"""
from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup

from app.core.logging_config import get_logger
from app.core.net_guard import UnsafeURLError, safe_get

log = get_logger(__name__)

try:
    from ddgs import DDGS  # type: ignore[import-not-found]

    DDGS_AVAILABLE = True
except ImportError:  # pragma: no cover
    try:
        from duckduckgo_search import DDGS  # type: ignore[import-not-found]

        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        DDGS = None  # type: ignore[assignment,misc]


def _html_results(query: str, max_results: int) -> list[dict[str, Any]]:
    response = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (compatible; ATLAS-AI/3.0)"},
        timeout=12,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    results: list[dict[str, Any]] = []
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


def perform_web_search(query: str, max_results: int = 3) -> str:
    """Ricerca web reale con DuckDuckGo (libreria o fallback HTML)."""
    if not query or not query.strip():
        return "Cosa devo cercare? Scrivi una domanda o un argomento."
    limit = max(1, min(int(max_results or 3), 10))
    results: list[dict[str, Any]] = []

    if DDGS_AVAILABLE and DDGS is not None:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=limit))
        except Exception as exc:
            log.warning("Libreria DuckDuckGo fallita, uso HTML: %s", exc)

    if not results:
        try:
            results = _html_results(query, limit)
        except requests.RequestException as exc:
            log.warning("perform_web_search rete: %s", exc)
            return "Errore di rete durante la ricerca."

    if not results:
        return "Nessun risultato trovato sul web."

    return "\n\n".join(
        f"Risultato {index + 1}:\nTitolo: {row.get('title', '?')}\n"
        f"Snippet: {row.get('body', '')}\nURL: {row.get('href', '')}"
        for index, row in enumerate(results[:limit])
    )


def read_website_content(url: str) -> str:
    """Legge il testo principale di una pagina (paragrafi HTML)."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return "Fornisci un URL valido che inizi per http:// o https://"
    try:
        response = safe_get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ATLAS-AI/3.0)"},
        )
        response.raise_for_status()
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return "Il contenuto di questo URL non è HTML e non può essere letto direttamente."
        soup = BeautifulSoup(response.content, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "canvas"]):
            tag.decompose()
        text = "\n\n".join(
            chunk for chunk in (p.get_text(" ", strip=True) for p in soup.find_all("p")) if len(chunk) > 30
        )[:4000]
        return text or "Pagina recuperata ma senza testo significativo (potrebbe essere tutta JS)."
    except UnsafeURLError as exc:
        log.warning("read_website_content bloccata per %s: %s", url, exc)
        return f"URL non consentito: {exc}"
    except requests.RequestException as exc:
        log.warning("read_website_content fallita per %s: %s", url, exc)
        return f"Impossibile leggere la pagina web ({type(exc).__name__})."
