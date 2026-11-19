"""
Controllo genitore per i profili bambino.

Tre limiti, applicati dal backend (non solo dall'interfaccia):
- orario: la chat funziona solo nella fascia impostata (gestisce la mezzanotte);
- messaggi al giorno: 0 = illimitato;
- contenuti: prompt dedicato e tool "da adulti" (finanza, browser, MCP) nascosti.

Il conteggio dei messaggi vive in `_local_db/usage.json`, accanto agli altri
dati locali, e viene azzerato automaticamente al cambio di giorno.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core import database
from app.core.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_LIMITS: dict[str, Any] = {
    "attivo": False,
    "ora_inizio": "07:00",
    "ora_fine": "21:00",
    "messaggi_giorno": 0,
    "contenuti_bambino": True,
}

# Tool non disponibili per un profilo bambino: denaro, acquisti, browser e MCP.
CHILD_BLOCKED_TOOLS = {
    "get_crypto_price",
    "get_top_crypto",
    "get_exchange_rate",
    "get_stock_price",
    "traccia_spesa",
    "riepilogo_budget",
    "cerca_volo",
    "gmail_leggi_email",
    "gmail_cerca_appuntamenti",
    "calendar_crea_evento",
    "calendar_agenda",
    "web_search",
    "get_ip_info",
    "mcp_elenca_server",
    "mcp_elenca_tool",
    "mcp_chiama_tool",
    "mcp_web_fetch_markdown",
    "mcp_web_fetch_json",
    "mcp_github_get_file",
    "mcp_github_search_code",
    "mcp_github_search_repositories",
    "mcp_github_search_repositories",
}
# Tutti i browser_* sono bloccati: il nome inizia con "browser_".

_USAGE_FILE = "usage.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _usage_path() -> Path:
    return Path(database.LOCAL_DB_DIR) / _USAGE_FILE


def _read_usage() -> dict[str, dict[str, int]]:
    path = _usage_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        log.warning("File utilizzo illeggibile: %s", path)
    return {}


def _write_usage(data: dict[str, dict[str, int]]) -> None:
    path = _usage_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("Impossibile scrivere %s: %s", path, exc)


def limits_for(profile: Optional[dict]) -> dict[str, Any]:
    """Limiti effettivi del profilo, con i default per i campi mancanti."""
    raw = (profile or {}).get("limiti") or {}
    limits = dict(DEFAULT_LIMITS)
    if isinstance(raw, dict):
        limits.update({key: value for key, value in raw.items() if key in DEFAULT_LIMITS})
    return limits


def is_child(profile: Optional[dict]) -> bool:
    return str((profile or {}).get("tipo") or "adulto").lower() == "bambino"


def parse_hhmm(value: str, fallback: str) -> tuple[int, int]:
    try:
        ore, minuti = str(value).strip().split(":")
        ore_i, minuti_i = int(ore), int(minuti)
        if 0 <= ore_i <= 23 and 0 <= minuti_i <= 59:
            return ore_i, minuti_i
    except (ValueError, AttributeError):
        pass
    ore, minuti = fallback.split(":")
    return int(ore), int(minuti)


def is_within_hours(limits: dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True se l'ora attuale è nella fascia consentita (anche a cavallo di mezzanotte)."""
    moment = (now or datetime.now()).time()
    inizio = parse_hhmm(limits.get("ora_inizio", "07:00"), "07:00")
    fine = parse_hhmm(limits.get("ora_fine", "21:00"), "21:00")
    attuale = (moment.hour, moment.minute)
    if inizio == fine:
        return True
    if inizio < fine:
        return inizio <= attuale < fine
    # Fascia notturna, es. 21:00 → 07:00.
    return attuale >= inizio or attuale < fine


def messages_today(profile_slug: str) -> int:
    return int((_read_usage().get(_today()) or {}).get(profile_slug) or 0)


def register_message(profile_slug: str) -> int:
    """Registra un messaggio del profilo e ritorna il totale di oggi."""
    data = _read_usage()
    oggi = _today()
    # Retention: teniamo solo oggi e ieri (basta per il limite giornaliero).
    data = {day: rows for day, rows in data.items() if day >= _previous_day(oggi)}
    giorno = data.setdefault(oggi, {})
    giorno[profile_slug] = int(giorno.get(profile_slug) or 0) + 1
    _write_usage(data)
    return giorno[profile_slug]


def _previous_day(today: str) -> str:
    from datetime import timedelta

    return (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


def check(profile: Optional[dict]) -> tuple[bool, str]:
    """(consentito, motivo) per l'accesso alla chat del profilo."""
    if not profile or not is_child(profile):
        return True, ""
    limits = limits_for(profile)
    if not limits.get("attivo"):
        return True, ""
    if not is_within_hours(limits):
        return (
            False,
            f"La chat è disponibile dalle {limits.get('ora_inizio')} alle {limits.get('ora_fine')}. "
            "Torna in quella fascia.",
        )
    limite = int(limits.get("messaggi_giorno") or 0)
    if limite > 0 and messages_today(str(profile.get("slug"))) >= limite:
        return (
            False,
            f"Hai raggiunto i {limite} messaggi di oggi. Ci risentiamo domani!",
        )
    return True, ""


def blocked_tools_for(profile: Optional[dict]) -> set[str]:
    """Nomi dei tool da nascondere al modello per questo profilo."""
    if not is_child(profile) or not limits_for(profile).get("contenuti_bambino", True):
        return set()
    return set(CHILD_BLOCKED_TOOLS)


def reset_usage() -> None:
    """Azzera i contatori (usato dai test)."""
    _write_usage({})
