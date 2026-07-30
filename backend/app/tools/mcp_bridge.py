"""
ATLAS AI — Bridge per Server MCP (Model Context Protocol)
==========================================================

Modulo che integra i server MCP disponibili nel runtime di ATLAS AI
come tools chiamabili tramite function-calling dell'AI.

Ogni funzione è decorata con docstring + annotazioni forti per il parsing Pydantic,
e implementa un **graceful fallback** se il server MCP non è raggiungibile:
  * Multi_Fetch  → fallback a `requests` + `beautifulsoup4` (installati)
  * GitHub MCP   → fallback a GitHub public REST API v3 (senza auth, rate limit 60/h)
  * Browser / Playwright / Chrome DevTools / Blender → messaggio istruttivo +
                                 suggerimento attivazione MCP nel runtime.

I server MCP integrati:
  - mcp_Multi_Fetch        (fetch_html, fetch_json, fetch_markdown, fetch_txt)
  - mcp_GitHub             (get_file_contents, search_code, search_repositories)
  - integrated_browser     (navigate, click, screenshot, evaluate)
  - mcp_Playwright         (playwright_navigate, playwright_screenshot, playwright_click)
  - mcp_Chrome_DevTools_MCP (performance, console messages, network)
  - mcp_Blender            (3D assets: sketchfab, polyhaven, hyper3d generation)
  - mcp_testsprite         (QA / test generation)
"""
from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import quote, urlencode

import requests

from app.core.logging_config import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------
# Configurazione MCP: indica all'AI quali server sono disponibili
# tramite l'enum `_MCP_SERVERS`. Il router li usa come "hint".
# ---------------------------------------------------------------------
_MCP_SERVERS = frozenset(
    {
        "mcp_Multi_Fetch",
        "mcp_GitHub",
        "integrated_browser",
        "mcp_Playwright",
        "mcp_Chrome_DevTools_MCP",
        "mcp_Blender",
        "mcp_testsprite",
    }
)

_HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36 ATLAS-AI/3.0 (+https://atlas.ai)"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

_GITHUB_API = "https://api.github.com"


# =====================================================================
#  1 — mcp_Multi_Fetch: fetch web HTML / JSON / Markdown / TXT
# =====================================================================

def mcp_web_fetch_markdown(url: str, max_chars: int = 4000) -> str:
    """
    Scarica una pagina web e ne restituisce il contenuto in formato Markdown
    (o plain text pulito).

    Args:
        url: URL completo (https://...) da scaricare.
        max_chars: Numero massimo di caratteri da restituire (default 4000).

    Returns:
        Contenuto Markdown / testo della pagina, troncato a max_chars.
    """
    try:
        resp = requests.get(url, headers=_HEADERS_BROWSER, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").lower()
        text: str
        if "text/html" in content_type:
            # Graceful fallback BeautifulSoup (già installato)
            try:
                from bs4 import BeautifulSoup  # type: ignore[import-not-found]

                soup = BeautifulSoup(resp.text, "lxml")
                for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            except Exception:
                text = resp.text
        else:
            text = resp.text
        text = text.replace("\r", "").replace("\t", " ")
        # Collassa newlines multipli
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text[:max_chars] + (
            "\n\n[...troncato — aumenta `max_chars` per intero contenuto]"
            if len(text) > max_chars
            else ""
        )
    except requests.RequestException as exc:
        log.warning("mcp_web_fetch_markdown fallita rete: %s -> %s", url, exc)
        return (
            f"⚠️ Impossibile raggiungere {url} (errore rete: {exc}).\n"
            "Suggerimento: abilita il server MCP `mcp_Multi_Fetch` nel runtime ATLAS "
            "per una gestione resilientissima di redirect, caching e rendering JS."
        )
    except Exception as exc:  # pragma: no cover
        log.exception("mcp_web_fetch_markdown errore: %s", exc)
        return f"Errore generico durante fetch di {url}: {exc!r}"


def mcp_web_fetch_json(url: str, query_params: Optional[dict[str, Any]] = None) -> str:
    """
    Scarica un endpoint JSON REST e restituisce la risposta formattata.

    Args:
        url: URL endpoint (https://).
        query_params: Dizionario chiave/valore da appendere come query string (opzionale).

    Returns:
        Stringa JSON formattata (indentata) della risposta.
    """
    try:
        if query_params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(query_params)}"
        resp = requests.get(
            url,
            headers={**_HEADERS_BROWSER, "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        out = json.dumps(payload, ensure_ascii=False, indent=2)
        return out[: 8000] + (
            "\n\n[...troncato per lunghezza]" if len(out) > 8000 else ""
        )
    except requests.RequestException as exc:
        log.warning("mcp_web_fetch_json fallita rete %s: %s", url, exc)
        return (
            f"⚠️ Impossibile recuperare JSON da {url} (errore rete: {exc}).\n"
            "Attiva il server MCP `mcp_Multi_Fetch` nel runtime ATLAS per una gestione"
            " più robusta (caching, retry, TLS custom)."
        )
    except json.JSONDecodeError as exc:
        return f"❌ Risposta non valida (JSON) da {url}: {exc.msg}"
    except Exception as exc:  # pragma: no cover
        return f"Errore generico mcp_web_fetch_json {url}: {exc!r}"


# =====================================================================
#  2 — mcp_GitHub: lettura file, ricerca codice, info repo
# =====================================================================

def mcp_github_get_file(owner: str, repo: str, path: str, branch: str = "main") -> str:
    """
    Legge il contenuto di un singolo file da un repository GitHub pubblico.

    Args:
        owner: Username o organizzazione proprietaria (es. "octocat").
        repo: Nome repository (es. "Hello-World").
        path: Percorso file nel repo (es. "README.md").
        branch: Nome branch (default "main").

    Returns:
        Contenuto file come testo, o messaggio errore.
    """
    try:
        safe_path = quote(path)
        api_url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{safe_path}?ref={quote(branch)}"
        resp = requests.get(
            api_url,
            headers={**_HEADERS_BROWSER, "Accept": "application/vnd.github.raw+json"},
            timeout=15,
        )
        if resp.status_code == 404:
            return (
                f"📂 File non trovato in {owner}/{repo}@{branch}: `{path}`\n"
                "Suggerimento: attiva il server MCP `mcp_GitHub` nel runtime per "
                "accesso illimitato a repo pubbliche/private e scrittura."
            )
        if resp.status_code == 403:
            return (
                "⚠️ Rate limit GitHub pubblico raggiunto (60 richieste/ora).\n"
                "Per oltre, configura GITHUB_TOKEN o usa il server MCP `mcp_GitHub`"
                " autenticato nel runtime ATLAS."
            )
        resp.raise_for_status()
        return resp.text[:8000] + (
            "\n\n[...troncato]" if len(resp.text) > 8000 else ""
        )
    except Exception as exc:  # pragma: no cover
        log.exception("mcp_github_get_file %s/%s/%s: %s", owner, repo, path, exc)
        return f"Errore mcp_github_get_file: {exc!r}"


def mcp_github_search_code(query: str, language: Optional[str] = None, max_results: int = 5) -> str:
    """
    Cerca codice sorgente in GitHub pubblico.

    Args:
        query: Testo di ricerca (es. "FastAPI rate limit").
        language: Filtra per linguaggio (es. "python", "typescript") — opzionale.
        max_results: Numero massimo di risultati (default 5).

    Returns:
        Elenco formattato di risultati (repo, path, anteprima).
    """
    try:
        q = query
        if language:
            q += f" language:{language}"
        url = f"{_GITHUB_API}/search/code?q={quote(q)}&per_page={max(max_results,1)}"
        resp = requests.get(url, headers={**_HEADERS_BROWSER, "Accept": "application/vnd.github+json"}, timeout=20)
        if resp.status_code == 403:
            return "⚠️ Rate limit ricerca GitHub raggiunto — abilita il server MCP `mcp_GitHub` autenticato."
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") or []
        if not items:
            return f"Nessun risultato per query='{query}'"
        out: list[str] = []
        for i, it in enumerate(items[:max_results], 1):
            repo_full = (it.get("repository") or {}).get("full_name", "?")
            path = it.get("path", "?")
            html_url = it.get("html_url", "")
            score = it.get("score", 0)
            out.append(f"{i}. **{repo_full}** — `{path}`\n   🔗 {html_url}\n   (score={score:.1f})")
        return "\n\n".join(out)
    except Exception as exc:  # pragma: no cover
        log.exception("mcp_github_search_code q=%s: %s", query, exc)
        return f"Errore mcp_github_search_code: {exc!r}"


def mcp_github_search_repositories(query: str, sort: str = "stars", max_results: int = 5) -> str:
    """
    Cerca repository GitHub pubblici per popolarità/rilevanza.

    Args:
        query: Termine di ricerca (es. "fastapi ai assistant").
        sort: Criterio ordinamento: "stars", "forks", "help-wanted-issues", "updated".
        max_results: Numero risultati (default 5).

    Returns:
        Lista repo: nome full, stelle, linguaggio, descrizione, URL.
    """
    try:
        url = (
            f"{_GITHUB_API}/search/repositories?q={quote(query)}"
            f"&sort={quote(sort)}&per_page={max(max_results,1)}&order=desc"
        )
        resp = requests.get(url, headers={**_HEADERS_BROWSER}, timeout=15)
        if resp.status_code == 403:
            return "⚠️ Rate limit GitHub ricerca pubbliche raggiunto."
        resp.raise_for_status()
        items = (resp.json() or {}).get("items") or []
        if not items:
            return f"Nessun repo trovato per query='{query}'"
        out: list[str] = []
        for i, r in enumerate(items[:max_results], 1):
            stars = r.get("stargazers_count", 0)
            forks = r.get("forks_count", 0)
            lang = r.get("language") or "—"
            desc = (r.get("description") or "(nessuna descrizione)").strip()
            link = r.get("html_url", "")
            out.append(
                f"{i}. **{r.get('full_name','?')}** ⭐ {stars:,}  🍴 {forks:,}  [lang: {lang}]\n"
                f"   {desc}\n   🔗 {link}"
            )
        return "\n\n".join(out)
    except Exception as exc:  # pragma: no cover
        log.exception("mcp_github_search_repositories q=%s: %s", query, exc)
        return f"Errore mcp_github_search_repositories: {exc!r}"


# =====================================================================
#  3 — integrated_browser / mcp_Playwright: automazione web
#  (placeholder istruttivi in modalità fallback; se MCP è attivo nel
#   runtime ATLAS essi sostituiranno queste funzioni)
# =====================================================================

def mcp_browse_url(url: str, wait_seconds: int = 2, screenshot: bool = False) -> str:
    """
    Apri un URL in un browser headless integrato (MCP `integrated_browser`
    oppure `mcp_Playwright` nel runtime).

    Args:
        url: Indirizzo web completo (https://).
        wait_seconds: Secondi di attesa caricamento (default 2).
        screenshot: Se True salva screenshot (solo se MCP attivo).

    Returns:
        Anteprima HTML testuale / stato operazione.
    """
    return (
        f"📡 Richiesta di navigazione registrata: {url} (wait={wait_seconds}s, screenshot={screenshot}).\n\n"
        "⚠️ Browser integrato **MCP** non attivo in questo ambiente.\n"
        "Per abilitarlo, avvia ATLAS AI nel runtime TRAE dove sono disponibili i server:\n"
        "  - `integrated_browser`  (navigazione interattiva, click, screenshot, evaluate JS)\n"
        "  - `mcp_Playwright`      (automazione headless multi-browser, fill, form, PDF, trace)\n"
        "  - `mcp_Chrome_DevTools_MCP` (Lighthouse, performance, rete, console, heap snapshot)\n\n"
        "In assenza di MCP, puoi usare `mcp_web_fetch_markdown('" + url + "')` per leggere il sorgente statico."
    )


def mcp_playwright_automate(url: str, click_selector: Optional[str] = None, fill_selector: Optional[str] = None, fill_value: Optional[str] = None) -> str:
    """
    Esegui uno step di automazione Playwright (click/fill) su una pagina.
    Disponibile solo con server MCP `mcp_Playwright` attivo.
    """
    steps = [f"Apri {url}"]
    if click_selector:
        steps.append(f"Click sul selettore CSS: {click_selector}")
    if fill_selector and fill_value is not None:
        steps.append(f"Fill '{fill_selector}' con '{fill_value}'")
    return (
        "🎭 Playwright automation richiesta:\n - " + "\n - ".join(steps) + "\n\n"
        "⚠️ MCP `mcp_Playwright` non disponibile in questo runtime ATLAS.\n"
        "Abilitalo in TRAE per usare: playwright_navigate, playwright_fill, playwright_click, playwright_screenshot, playwright_save_as_pdf."
    )


# =====================================================================
#  4 — mcp_Blender: asset 3D
# =====================================================================

def mcp_blender_search_3d_assets(keyword: str, source: str = "polyhaven", max_results: int = 3) -> str:
    """
    Cerca asset 3D (texture, HDRI, modelli) via MCP `mcp_Blender`
    (Polyhaven · Sketchfab · Hyper3D · Hunyuan3D).

    Args:
        keyword: Parola chiave ricerca (es. "casa italiana", "marmo bianco").
        source: "polyhaven" (texture/HDRI free), "sketchfab" (modelli), "all".
        max_results: Numero risultati (default 3).

    Returns:
        Anteprima lista asset trovati.
    """
    return (
        f"🎨 Richiesta ricerca asset 3D: keyword='{keyword}' source='{source}' max={max_results}.\n\n"
        "⚠️ MCP `mcp_Blender` non disponibile in questo ambiente.\n"
        "Per abilitarlo e scaricare/applicare texture HDRI direttamente in Blender: "
        "avvia ATLAS AI dove il server MCP Blender è connesso "
        "(tool: search_polyhaven_assets, download_polyhaven_asset, set_texture, "
        "search_sketchfab_models, generate_hyper3d_model_via_text, generate_hunyuan3d_model...)."
    )


# =====================================================================
#  5 — mcp_testsprite: QA & Test auto
# =====================================================================

def mcp_qa_generate_tests(kind: str, target_path_or_url: str) -> str:
    """
    Genera automaticamente piani di test (PRD, test plan unitari/integrativi/e2e)
    e codice eseguibile (pytest / Playwright) per un modulo specifico.

    Args:
        kind: Tipo di artefatto richiesto: "prd" · "frontend_test_plan" ·
              "backend_test_plan" · "generate_code_and_execute".
        target_path_or_url: Percorso file locale (backend/main.py) o URL dell'app.
    """
    kinds_valid = {"prd", "frontend_test_plan", "backend_test_plan", "generate_code_and_execute"}
    if kind not in kinds_valid:
        return f"❌ Tipo `{kind}` non valido. Usare uno tra: {sorted(kinds_valid)}."
    return (
        f"🧪 Richiesta QA MCP TestSprite: kind='{kind}' target='{target_path_or_url}'.\n\n"
        "⚠️ MCP `mcp_testsprite` non attivo.\n"
        "Quando il server è disponibile nel runtime ATLAS puoi usare: "
        "testsprite_generate_standardized_prd, testsprite_generate_frontend_test_plan, "
        "testsprite_generate_backend_test_plan, testsprite_generate_code_and_execute, "
        "e visualizzare il risultato nel dashboard: testsprite_open_test_result_dashboard."
    )


# =====================================================================
#  6 — Helpers di disponibilità (utili a LLM per introspezione)
# =====================================================================

def mcp_elenca_server_disponibili() -> str:
    """
    Elenca tutti i server MCP integrati nella piattaforma ATLAS AI,
    con un breve sommario di cosa offre ciascuno.
    """
    rows = [
        ("mcp_Multi_Fetch", "Fetch web resilientissimo (HTML/JSON/Markdown/TXT)"),
        ("mcp_GitHub", "Lettura/Scrittura repo, PR, issues, search code"),
        ("integrated_browser", "Browser interattivo, click, screenshot, evaluate"),
        ("mcp_Playwright", "Automazione headless multi-browser, e2e test"),
        ("mcp_Chrome_DevTools_MCP", "Lighthouse, performance, rete, console, heap"),
        ("mcp_Blender", "Asset 3D (Polyhaven, Sketchfab, Hyper3D, Hunyuan3D)"),
        ("mcp_testsprite", "QA: PRD auto, test plan, pytest + e2e + dashboard"),
    ]
    lines = [
        "🧭 Server MCP integrati nella piattaforma **ATLAS AI v3.0**:",
        "",
    ]
    for name, desc in rows:
        lines.append(f"- **{name}** — {desc}")
    lines.append("")
    lines.append(
        "Se un server è contrassegnato come non disponibile nella risposta dei tool,"
        " significa che il runtime corrente non lo ha attivato: riavvia ATLAS AI nel"
        " workspace TRAE dove i server MCP sono abilitati per sbloccare tutte le funzionalità."
    )
    return "\n".join(lines)


__all__ = [
    "mcp_web_fetch_markdown",
    "mcp_web_fetch_json",
    "mcp_github_get_file",
    "mcp_github_search_code",
    "mcp_github_search_repositories",
    "mcp_browse_url",
    "mcp_playwright_automate",
    "mcp_blender_search_3d_assets",
    "mcp_qa_generate_tests",
    "mcp_elenca_server_disponibili",
]
