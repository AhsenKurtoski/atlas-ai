"""
Client MCP (Model Context Protocol) reale per ATLAS AI v3.0.

ATLAS non finge di avere server MCP: si collega davvero a server MCP
configurati via variabile d'ambiente `MCP_SERVERS` (JSON) e ne espone i tool
all'AI. Il trasporto implementato è **Streamable HTTP** (JSON-RPC 2.0 su POST,
con risposte JSON o SSE), che è quello usato dai server MCP moderni.

Esempio `.env`:

    MCP_SERVERS={"files":{"url":"http://127.0.0.1:9000/mcp"},
                 "remoto":{"url":"https://mcp.example.com/mcp","headers":{"Authorization":"Bearer ..."}}}

In più restano disponibili due capacità native, sempre reali e gratuite:
  * fetch web (HTML → testo/Markdown, JSON) con `requests` + BeautifulSoup
  * GitHub REST API pubblica (con `GITHUB_TOKEN` opzionale per i limiti)
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib.parse import quote

import requests

from app.core.logging_config import get_logger
from app.core.net_guard import UnsafeURLError, safe_get

log = get_logger(__name__)

_HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36 ATLAS-AI/3.0"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
_GITHUB_API = "https://api.github.com"
_MCP_PROTOCOL_VERSION = "2025-06-18"
_MCP_TIMEOUT = 30

# Stato delle sessioni MCP: url -> {"session_id": str, "initialized": bool}
_MCP_SESSIONS: dict[str, dict[str, Any]] = {}


# =====================================================================
#  Configurazione server MCP
# =====================================================================
def _servers_config() -> dict[str, dict[str, Any]]:
    """Legge `MCP_SERVERS` (JSON) e normalizza la configurazione."""
    raw = os.getenv("MCP_SERVERS", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("MCP_SERVERS non è JSON valido: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        log.error("MCP_SERVERS deve essere un oggetto {nome: {url: ...}}")
        return {}
    servers: dict[str, dict[str, Any]] = {}
    for name, value in parsed.items():
        if isinstance(value, str):
            servers[str(name)] = {"url": value, "headers": {}}
        elif isinstance(value, dict) and value.get("url"):
            servers[str(name)] = {
                "url": str(value["url"]),
                "headers": {str(k): str(v) for k, v in (value.get("headers") or {}).items()},
            }
    return servers


def _server(name: str) -> dict[str, Any]:
    servers = _servers_config()
    if name not in servers:
        raise MCPError(
            f"Server MCP '{name}' non configurato. Server disponibili: "
            f"{', '.join(servers) if servers else '(nessuno)'}."
        )
    return servers[name]


class MCPError(RuntimeError):
    """Errore di comunicazione con un server MCP."""


# =====================================================================
#  Trasporto JSON-RPC 2.0 / Streamable HTTP
# =====================================================================
def _parse_sse(text: str, request_id: int | None) -> dict[str, Any] | None:
    """Estrae la risposta JSON-RPC da un corpo text/event-stream."""
    result: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            message = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        if request_id is None or message.get("id") == request_id:
            result = message
    return result


def _rpc(
    name: str,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    notification: bool = False,
) -> dict[str, Any]:
    """Esegue una chiamata JSON-RPC verso il server MCP indicato."""
    cfg = _server(name)
    url = cfg["url"]
    session = _MCP_SESSIONS.setdefault(url, {"session_id": None, "initialized": False})

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": _MCP_PROTOCOL_VERSION,
    }
    headers.update(cfg.get("headers") or {})
    if session.get("session_id"):
        headers["Mcp-Session-Id"] = session["session_id"]

    if notification:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
    else:
        request_id = int(os.urandom(3).hex(), 16)
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=_MCP_TIMEOUT)
    except requests.RequestException as exc:
        raise MCPError(f"Server MCP '{name}' non raggiungibile: {exc}") from exc

    if notification and response.status_code in (200, 202, 204):
        return {}

    content_type = response.headers.get("Content-Type", "")
    if response.status_code >= 400:
        raise MCPError(
            f"Server MCP '{name}' ha risposto HTTP {response.status_code}: {response.text[:200]}"
        )

    if "text/event-stream" in content_type.lower():
        message = _parse_sse(response.text, payload.get("id"))
    else:
        try:
            message = response.json()
        except ValueError as exc:
            raise MCPError(f"Risposta MCP non JSON da '{name}': {response.text[:200]}") from exc

    if message is None:
        raise MCPError(f"Nessuna risposta JSON-RPC da '{name}'.")

    session_id = response.headers.get("Mcp-Session-Id")
    if session_id:
        session["session_id"] = session_id

    if message.get("error"):
        error = message["error"]
        detail = error.get("message") if isinstance(error, dict) else str(error)
        raise MCPError(f"Errore MCP da '{name}': {detail}")

    return message.get("result") or {}


def _ensure_initialized(name: str) -> None:
    cfg = _server(name)
    session = _MCP_SESSIONS.setdefault(cfg["url"], {"session_id": None, "initialized": False})
    if session.get("initialized"):
        return
    _rpc(
        name,
        "initialize",
        {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {"roots": {"listChanged": False}},
            "clientInfo": {"name": "atlas-ai", "version": "3.0.0"},
        },
    )
    try:
        _rpc(name, "notifications/initialized", notification=True)
    except MCPError as exc:
        log.debug("notifications/initialized ignorata da %s: %s", name, exc)
    session["initialized"] = True


# =====================================================================
#  Tool esposti all'AI
# =====================================================================
def mcp_elenca_server() -> str:
    """Elenca i server MCP configurati in ATLAS (con URL) e lo stato della sessione."""
    servers = _servers_config()
    if not servers:
        return (
            "Nessun server MCP configurato.\n"
            "Per collegarne uno, imposta la variabile d'ambiente MCP_SERVERS, esempio:\n"
            'MCP_SERVERS={"files":{"url":"http://127.0.0.1:9000/mcp"}}\n'
            "Poi riavvia il backend."
        )
    righe = ["🧭 Server MCP configurati:"]
    for name, cfg in servers.items():
        session = _MCP_SESSIONS.get(cfg["url"], {})
        stato = "sessione attiva" if session.get("initialized") else "da inizializzare"
        righe.append(f"- **{name}** → {cfg['url']} ({stato})")
    return "\n".join(righe)


def mcp_elenca_tool(server: str) -> str:
    """Elenca i tool esposti da un server MCP configurato.

    Args:
        server: Nome del server MCP come definito in MCP_SERVERS.
    """
    try:
        _ensure_initialized(server)
        result = _rpc(server, "tools/list", {})
    except MCPError as exc:
        log.warning("mcp_elenca_tool(%s): %s", server, exc)
        return f"⚠️ {exc}"
    tools = result.get("tools") or []
    if not tools:
        return f"Il server MCP '{server}' non espone alcun tool."
    righe = [f"🧰 Tool di '{server}':"]
    for tool in tools:
        descrizione = (tool.get("description") or "").strip().splitlines()
        sintesi = descrizione[0][:160] if descrizione else "(senza descrizione)"
        schema = tool.get("inputSchema") or {}
        props = ", ".join((schema.get("properties") or {}).keys())
        righe.append(f"- **{tool.get('name')}** — {sintesi}" + (f" | parametri: {props}" if props else ""))
    return "\n".join(righe)


def mcp_chiama_tool(server: str, tool: str, argomenti_json: str = "{}") -> str:
    """Esegue un tool di un server MCP configurato e ne restituisce il risultato.

    Args:
        server: Nome del server MCP (vedi MCP_SERVERS).
        tool: Nome del tool da eseguire (vedi mcp_elenca_tool).
        argomenti_json: Oggetto JSON con gli argomenti del tool (default "{}").
    """
    try:
        argomenti = json.loads(argomenti_json) if argomenti_json and argomenti_json.strip() else {}
    except json.JSONDecodeError as exc:
        return f"❌ argomenti_json non è JSON valido: {exc}"
    if not isinstance(argomenti, dict):
        return "❌ argomenti_json deve essere un oggetto JSON."

    try:
        _ensure_initialized(server)
        result = _rpc(server, "tools/call", {"name": tool, "arguments": argomenti})
    except MCPError as exc:
        log.warning("mcp_chiama_tool(%s/%s): %s", server, tool, exc)
        return f"⚠️ {exc}"

    if result.get("isError"):
        parti = _extract_text(result)
        return f"⚠️ Tool '{tool}' ha restituito un errore: {parti or '(nessun dettaglio)'}"
    testo = _extract_text(result)
    return testo or f"✅ Tool '{tool}' eseguito (nessun output testuale)."


def _extract_text(result: dict[str, Any]) -> str:
    """Concatena i blocchi testuali del risultato MCP."""
    chunks: list[str] = []
    for block in result.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            chunks.append(str(block["text"]))
        elif block.get("type") == "resource" and block.get("resource"):
            resource = block["resource"]
            if isinstance(resource, dict) and resource.get("text"):
                chunks.append(str(resource["text"]))
    if not chunks and result.get("structuredContent"):
        chunks.append(json.dumps(result["structuredContent"], ensure_ascii=False, indent=2))
    return "\n".join(chunks)[:6000]


# =====================================================================
#  Capacità native: fetch web
# =====================================================================
def mcp_web_fetch_markdown(url: str, max_chars: int = 4000) -> str:
    """Scarica una pagina web e restituisce il testo pulito (ex HTML → Markdown).

    Args:
        url: URL completo (https://...) da scaricare.
        max_chars: Numero massimo di caratteri da restituire (default 4000).
    """
    if not url.lower().startswith(("http://", "https://")):
        return "Fornisci un URL valido che inizi per http:// o https://"
    try:
        response = safe_get(url, headers=_HEADERS_BROWSER, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        text = response.text
        if "text/html" in content_type:
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(response.text, "lxml")
                for tag in soup(["script", "style", "nav", "footer", "noscript", "iframe"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            except Exception as exc:  # parser non disponibile: testo grezzo
                log.debug("BeautifulSoup non disponibile: %s", exc)
        text = text.replace("\r", "").replace("\t", " ")
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        limite = max(500, min(int(max_chars or 4000), 20000))
        return text[:limite] + ("\n\n[...troncato]" if len(text) > limite else "")
    except UnsafeURLError as exc:
        log.warning("mcp_web_fetch_markdown bloccata: %s -> %s", url, exc)
        return f"⚠️ URL non consentito: {exc}"
    except requests.RequestException as exc:
        log.warning("mcp_web_fetch_markdown fallita: %s -> %s", url, exc)
        return f"⚠️ Impossibile raggiungere {url} (errore rete: {exc})."


def mcp_web_fetch_json(url: str, query_params: Optional[dict[str, Any]] = None) -> str:
    """Scarica un endpoint JSON e restituisce la risposta formattata.

    Args:
        url: URL endpoint (https://).
        query_params: Dizionario chiave/valore da aggiungere come query string.
    """
    if not url.lower().startswith(("http://", "https://")):
        return "Fornisci un URL valido che inizi per http:// o https://"
    try:
        response = safe_get(
            url,
            headers={**_HEADERS_BROWSER, "Accept": "application/json"},
            timeout=15,
            params=query_params,
        )
        response.raise_for_status()
        payload = response.json()
        out = json.dumps(payload, ensure_ascii=False, indent=2)
        return out[:8000] + ("\n\n[...troncato]" if len(out) > 8000 else "")
    except UnsafeURLError as exc:
        log.warning("mcp_web_fetch_json bloccata: %s -> %s", url, exc)
        return f"⚠️ URL non consentito: {exc}"
    except requests.RequestException as exc:
        log.warning("mcp_web_fetch_json fallita: %s -> %s", url, exc)
        return f"⚠️ Impossibile recuperare JSON da {url} (errore rete: {exc})."
    except ValueError as exc:
        return f"❌ Risposta non JSON da {url}: {exc}"


# =====================================================================
#  Capacità native: GitHub REST
# =====================================================================
def _github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {**_HEADERS_BROWSER, "Accept": accept}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def mcp_github_get_file(owner: str, repo: str, path: str, branch: str = "main") -> str:
    """Legge un file da un repository GitHub.

    Args:
        owner: Username o organizzazione (es. "octocat").
        repo: Nome repository (es. "Hello-World").
        path: Percorso del file (es. "README.md").
        branch: Branch o tag (default "main").
    """
    try:
        api_url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{quote(path)}?ref={quote(branch)}"
        response = requests.get(
            api_url,
            headers=_github_headers("application/vnd.github.raw+json"),
            timeout=15,
        )
        if response.status_code == 404:
            return f"📂 File non trovato in {owner}/{repo}@{branch}: `{path}`"
        if response.status_code == 403:
            return "⚠️ Rate limit GitHub raggiunto. Imposta GITHUB_TOKEN per alzare il limite."
        response.raise_for_status()
        return response.text[:8000] + ("\n\n[...troncato]" if len(response.text) > 8000 else "")
    except requests.RequestException as exc:
        log.warning("mcp_github_get_file %s/%s/%s: %s", owner, repo, path, exc)
        return f"⚠️ Errore GitHub: {exc}"


def mcp_github_search_code(query: str, language: Optional[str] = None, max_results: int = 5) -> str:
    """Cerca codice su GitHub.

    Args:
        query: Testo di ricerca (es. "FastAPI rate limit").
        language: Filtro linguaggio (es. "python", "typescript") — opzionale.
        max_results: Numero massimo di risultati (default 5).
    """
    try:
        qualifier = f"{query} language:{language}" if language else query
        limit = max(1, min(int(max_results or 5), 20))
        api_url = f"{_GITHUB_API}/search/code?q={quote(qualifier)}&per_page={limit}"
        response = requests.get(api_url, headers=_github_headers(), timeout=20)
        if response.status_code == 403:
            return "⚠️ Rate limit ricerca GitHub raggiunto. Imposta GITHUB_TOKEN."
        response.raise_for_status()
        items = (response.json() or {}).get("items") or []
        if not items:
            return f"Nessun risultato per query='{query}'"
        righe: list[str] = []
        for index, item in enumerate(items[:limit], 1):
            repo_full = (item.get("repository") or {}).get("full_name", "?")
            righe.append(
                f"{index}. **{repo_full}** — `{item.get('path', '?')}`\n"
                f"   🔗 {item.get('html_url', '')}"
            )
        return "\n\n".join(righe)
    except requests.RequestException as exc:
        log.warning("mcp_github_search_code %s: %s", query, exc)
        return f"⚠️ Errore GitHub: {exc}"


def mcp_github_search_repositories(query: str, sort: str = "stars", max_results: int = 5) -> str:
    """Cerca repository GitHub per popolarità/rilevanza.

    Args:
        query: Termine di ricerca (es. "fastapi ai assistant").
        sort: Ordinamento: "stars", "forks", "updated" (default "stars").
        max_results: Numero risultati (default 5).
    """
    try:
        limit = max(1, min(int(max_results or 5), 20))
        api_url = (
            f"{_GITHUB_API}/search/repositories?q={quote(query)}"
            f"&sort={quote(sort)}&order=desc&per_page={limit}"
        )
        response = requests.get(api_url, headers=_github_headers(), timeout=15)
        if response.status_code == 403:
            return "⚠️ Rate limit GitHub raggiunto. Imposta GITHUB_TOKEN."
        response.raise_for_status()
        items = (response.json() or {}).get("items") or []
        if not items:
            return f"Nessun repo trovato per query='{query}'"
        righe: list[str] = []
        for index, repo in enumerate(items[:limit], 1):
            righe.append(
                f"{index}. **{repo.get('full_name', '?')}** ⭐ {repo.get('stargazers_count', 0):,} "
                f"[{repo.get('language') or '—'}]\n"
                f"   {(repo.get('description') or '(nessuna descrizione)').strip()}\n"
                f"   🔗 {repo.get('html_url', '')}"
            )
        return "\n\n".join(righe)
    except requests.RequestException as exc:
        log.warning("mcp_github_search_repositories %s: %s", query, exc)
        return f"⚠️ Errore GitHub: {exc}"


__all__ = [
    "MCPError",
    "mcp_elenca_server",
    "mcp_elenca_tool",
    "mcp_chiama_tool",
    "mcp_web_fetch_markdown",
    "mcp_web_fetch_json",
    "mcp_github_get_file",
    "mcp_github_search_code",
    "mcp_github_search_repositories",
]
