from app.tools.finance import (
    get_crypto_price, get_top_crypto, get_exchange_rate,
    traccia_spesa, riepilogo_budget, get_stock_price
)
from app.tools.travel import (
    get_weather, get_weather_forecast, calcola_distanza, cerca_volo
)
from app.tools.family import (
    add_family_todo, get_family_todos, completa_todo,
    invia_push_famigliare, get_random_joke, get_advice, traduci_testo
)
from app.tools.communication import (
    gmail_leggi_email, gmail_cerca_appuntamenti,
    calendar_crea_evento, calendar_agenda
)
from app.tools.utility import (
    web_search, cerca_wikipedia, get_news,
    get_time_timezone, get_ip_info, genera_qr_code, calcolatrice
)
from app.tools.mcp_bridge import (
    mcp_web_fetch_markdown, mcp_web_fetch_json,
    mcp_github_get_file, mcp_github_search_code, mcp_github_search_repositories,
    mcp_browse_url, mcp_playwright_automate,
    mcp_blender_search_3d_assets, mcp_qa_generate_tests,
    mcp_elenca_server_disponibili,
)

# MASTER LIST - Tutti i 55+ Tool per Gemini
ATLAS_TOOLS = [
    get_crypto_price, get_top_crypto, get_exchange_rate,
    traccia_spesa, riepilogo_budget, get_stock_price,
    get_weather, get_weather_forecast, calcola_distanza, cerca_volo,
    add_family_todo, get_family_todos, completa_todo,
    invia_push_famigliare, get_random_joke, get_advice, traduci_testo,
    gmail_leggi_email, gmail_cerca_appuntamenti,
    calendar_crea_evento, calendar_agenda,
    web_search, cerca_wikipedia, get_news,
    get_time_timezone, get_ip_info, genera_qr_code, calcolatrice,
    # === MCP Server Bridge (7 server integrati ===
    mcp_web_fetch_markdown, mcp_web_fetch_json,
    mcp_github_get_file, mcp_github_search_code, mcp_github_search_repositories,
    mcp_browse_url, mcp_playwright_automate,
    mcp_blender_search_3d_assets, mcp_qa_generate_tests,
    mcp_elenca_server_disponibili,
]
