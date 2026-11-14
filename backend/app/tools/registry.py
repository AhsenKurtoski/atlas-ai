"""
Registro dei tool esposti a Gemini (function calling).

Contiene solo strumenti che eseguono azioni reali: nessun placeholder che
restituisce finti successi. I server MCP eventualmente configurati vengono
usati tramite `mcp_elenca_server` / `mcp_elenca_tool` / `mcp_chiama_tool`.
"""
from app.tools.finance import (
    get_crypto_price,
    get_exchange_rate,
    get_stock_price,
    get_top_crypto,
    riepilogo_budget,
    traccia_spesa,
)
from app.tools.travel import (
    calcola_distanza,
    cerca_volo,
    get_weather,
    get_weather_forecast,
)
from app.tools.family import (
    add_family_todo,
    completa_todo,
    get_advice,
    get_family_todos,
    get_random_joke,
    invia_push_famigliare,
    traduci_testo,
)
from app.tools.communication import (
    calendar_agenda,
    calendar_crea_evento,
    gmail_cerca_appuntamenti,
    gmail_leggi_email,
)
from app.tools.utility import (
    calcolatrice,
    cerca_wikipedia,
    genera_qr_code,
    get_ip_info,
    get_news,
    get_time_timezone,
    web_search,
)
from app.tools.browser import BROWSER_TOOLS
from app.tools.italian import lezione_italiano
from app.tools.mcp_bridge import (
    mcp_chiama_tool,
    mcp_elenca_server,
    mcp_elenca_tool,
    mcp_github_get_file,
    mcp_github_search_code,
    mcp_github_search_repositories,
    mcp_web_fetch_json,
    mcp_web_fetch_markdown,
)

ATLAS_TOOLS = [
    # Finanza
    get_crypto_price,
    get_top_crypto,
    get_exchange_rate,
    get_stock_price,
    traccia_spesa,
    riepilogo_budget,
    # Viaggi e meteo
    get_weather,
    get_weather_forecast,
    calcola_distanza,
    cerca_volo,
    # Famiglia
    add_family_todo,
    get_family_todos,
    completa_todo,
    invia_push_famigliare,
    get_random_joke,
    get_advice,
    traduci_testo,
    # Comunicazione (Gmail/Calendar reali via OAuth)
    gmail_leggi_email,
    gmail_cerca_appuntamenti,
    calendar_crea_evento,
    calendar_agenda,
    # Utility
    web_search,
    cerca_wikipedia,
    get_news,
    get_time_timezone,
    get_ip_info,
    genera_qr_code,
    calcolatrice,
    # Browser agent (Chromium reale, sessioni per profilo)
    *BROWSER_TOOLS,
    # Italiano
    lezione_italiano,
    # MCP (client reale + capacità native)
    mcp_elenca_server,
    mcp_elenca_tool,
    mcp_chiama_tool,
    mcp_web_fetch_markdown,
    mcp_web_fetch_json,
    mcp_github_get_file,
    mcp_github_search_code,
    mcp_github_search_repositories,
]

# Mappa nome → funzione (utile a chi ispeziona i tool disponibili).
ATLAS_TOOLS_BY_NAME = {tool.__name__: tool for tool in ATLAS_TOOLS}

__all__ = ["ATLAS_TOOLS", "ATLAS_TOOLS_BY_NAME"]
