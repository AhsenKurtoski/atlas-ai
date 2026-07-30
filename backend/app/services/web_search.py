"""
Wrapper ricerche web per Gemini (DuckDuckGo + BeautifulSoup).
Usato principalmente dal servizio gemini_service legacy; il nuovo ai_router
usa invece gli strumenti equivalenti definiti in app.tools.utility.
"""
from __future__ import annotations

from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from app.core.logging_config import get_logger

log = get_logger(__name__)


def perform_web_search(query: str, max_results: int = 3) -> str:
    """Ricerca web con DuckDuckGo (stessi risultati di app.tools.utility.web_search)."""
    try:
        if not query or not query.strip():
            return "Cosa devo cercare? Scrivi una domanda o un argomento."
        results: list[str] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max(1, min(int(max_results or 3), 10))):
                results.append(
                    f"Titolo: {r.get('title', '?')}\n"
                    f"Snippet: {r.get('body', '')}\n"
                    f"URL: {r.get('href', '')}"
                )
        if not results:
            return "Nessun risultato trovato sul web."
        formatted = "\n\n".join(f"Risultato {i+1}:\n{r}" for i, r in enumerate(results))
        return formatted
    except requests.RequestException as exc:
        log.warning("perform_web_search rete: %s", exc)
        return "Errore di rete durante la ricerca."
    except Exception as exc:
        log.exception("perform_web_search: %s", exc)
        return "Errore durante la ricerca web."


def read_website_content(url: str) -> str:
    """Legge il testo principale di una pagina (solo paragrafi)."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return "Fornisci un URL valido che inizi per http:// o https://"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "ATLAS-AI/3.0 (+http://atlas.local)"})
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" not in ctype.lower():
            return "Il contenuto di questo URL non è testo HTML e non può essere letto direttamente."
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "canvas"]):
            tag.decompose()
        paragraphs = soup.find_all("p")
        text_chunks = [p.get_text(" ", strip=True) for p in paragraphs]
        text = "\n\n".join(t for t in text_chunks if len(t) > 30)[:4000]
        if not text.strip():
            return "Pagina recuperata ma senza testo significativo (potrebbe essere tutta grafica o JS)."
        return text
    except requests.RequestException as exc:
        log.warning("read_website_content fallita per %s: %s", url, exc)
        return f"Impossibile leggere la pagina web ({type(exc).__name__})."
    except Exception as exc:
        log.exception("read_website_content errore: %s", exc)
        return "Impossibile leggere la pagina web."
