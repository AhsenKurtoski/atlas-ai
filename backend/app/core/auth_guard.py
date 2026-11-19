"""
Protezione degli accessi: blocco progressivo e registro degli accessi.

I dati vivono in `_local_db` accanto al database, così il blocco sopravvive al
riavvio del backend. Sono informazioni di sicurezza del server: nessun client
può leggerle o modificarle direttamente.

Politica di blocco (tentativi falliti negli ultimi 15 minuti, per profilo):
    5 → 1 minuto · 6 → 2 minuti · 7 → 5 minuti · 8+ → 15 minuti.
Un accesso riuscito azzera il contatore.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.core import database
from app.core.logging_config import get_logger

log = get_logger(__name__)

FAILURE_WINDOW = timedelta(minutes=15)
# (tentativi falliti, secondi di blocco) — oltre l'ultima soglia si applica il massimo.
LOCK_STEPS: tuple[tuple[int, int], ...] = ((5, 60), (6, 120), (7, 300), (8, 900))
MAX_LOCK_SECONDS = 900
MAX_EVENTS = 2000
# Retention dichiarata nell'informativa privacy: gli accessi più vecchi spariscono.
EVENT_RETENTION = timedelta(days=90)
# Tetto ai profili/slug seguiti: un attacco con nomi casuali non fa crescere il file.
MAX_TRACKED_PROFILES = 500

_LOCK_FILE = "auth_lockout.json"
_LOG_FILE = "access_log.json"


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path(name: str) -> Path:
    return Path(database.LOCAL_DB_DIR) / name


def _read(name: str, default: Any) -> Any:
    path = _path(name)
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except (OSError, json.JSONDecodeError):
        log.warning("File di sicurezza illeggibile: %s", path)
    return default


def _write(name: str, data: Any) -> None:
    path = _path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("Impossibile scrivere %s: %s", path, exc)


# ---------------- Blocco progressivo ----------------
def _lock_state() -> dict[str, dict]:
    state = _read(_LOCK_FILE, {})
    if not isinstance(state, dict):
        return {}
    state.setdefault("failures", {})
    state.setdefault("locks", {})
    return state


def lockout_status(profile_slug: str, now: Optional[int] = None) -> dict[str, Any]:
    """Stato del blocco per un profilo: locked, retry_after, failures, level."""
    moment = _now() if now is None else int(now)
    state = _lock_state()
    lock = (state.get("locks") or {}).get(profile_slug) or {}
    until = int(lock.get("until") or 0)
    if until > moment:
        return {
            "locked": True,
            "retry_after": until - moment,
            "failures": int((state.get("failures") or {}).get(profile_slug, {}).get("count") or 0),
            "level": int(lock.get("level") or 1),
        }
    if until:
        # Blocco scaduto: lo rimuoviamo (il contatore resta per la progressività).
        state.get("locks", {}).pop(profile_slug, None)
        _write(_LOCK_FILE, state)
    return {"locked": False, "retry_after": 0, "failures": 0, "level": 0}


def register_failure(profile_slug: str) -> dict[str, Any]:
    """Registra un tentativo fallito e applica l'eventuale blocco."""
    moment = _now()
    state = _lock_state()
    failures = state.setdefault("failures", {})
    entry = failures.get(profile_slug) or {}
    first = int(entry.get("first") or moment)
    if moment - first > int(FAILURE_WINDOW.total_seconds()):
        first = moment
        entry = {}
    count = int(entry.get("count") or 0) + 1
    failures[profile_slug] = {"count": count, "first": first, "last": moment}

    # Pulizia: via le voci fuori finestra e, se serve, le più vecchie.
    scaduto = moment - int(FAILURE_WINDOW.total_seconds())
    failures = {
        slug: data
        for slug, data in failures.items()
        if int(data.get("last") or 0) >= scaduto
    }
    if len(failures) > MAX_TRACKED_PROFILES:
        tenuti = sorted(failures.items(), key=lambda item: int(item[1].get("last") or 0))
        failures = dict(tenuti[-MAX_TRACKED_PROFILES:])
    state["failures"] = failures

    level = 0
    seconds = 0
    for soglia, attesa in LOCK_STEPS:
        if count >= soglia:
            level, seconds = soglia - 4, attesa
    if level:
        state.setdefault("locks", {})[profile_slug] = {"until": moment + seconds, "level": level}

    _write(_LOCK_FILE, state)
    return {
        "locked": bool(level),
        "retry_after": seconds,
        "failures": count,
        "level": level,
    }


def register_success(profile_slug: str) -> None:
    """Azzera contatore e blocco dopo un accesso riuscito."""
    state = _lock_state()
    changed = False
    if (state.get("failures") or {}).pop(profile_slug, None) is not None:
        changed = True
    if (state.get("locks") or {}).pop(profile_slug, None) is not None:
        changed = True
    if changed:
        _write(_LOCK_FILE, state)


def reset_all() -> None:
    """Azzera tutto (usato dai test per isolare i casi)."""
    _write(_LOCK_FILE, {"failures": {}, "locks": {}})


# ---------------- Registro accessi ----------------
def record_event(
    profile_slug: str,
    esito: str,
    motivo: str = "",
    ip: str = "",
    dispositivo: str = "",
) -> None:
    """Aggiunge una riga al registro accessi (chi, quando, da dove)."""
    rows = _read(_LOG_FILE, [])
    if not isinstance(rows, list):
        rows = []
    # Applica la retention dichiarata all'utente (90 giorni).
    soglia = _iso(int((datetime.now(timezone.utc) - EVENT_RETENTION).timestamp()))
    rows = [row for row in rows if str(row.get("quando") or "") >= soglia]
    rows.append(
        {
            "quando": _iso(_now()),
            "profilo": profile_slug,
            "esito": esito,  # ok | errore | bloccato
            "motivo": motivo,
            "ip": (ip or "")[:64],
            "dispositivo": (dispositivo or "")[:160],
        }
    )
    _write(_LOG_FILE, rows[-MAX_EVENTS:])


def list_events(profile_slug: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Eventi dal più recente, opzionalmente filtrati per profilo."""
    rows = _read(_LOG_FILE, [])
    if not isinstance(rows, list):
        return []
    if profile_slug:
        rows = [row for row in rows if row.get("profilo") == profile_slug]
    return list(reversed(rows))[: max(1, int(limit))]


def clear_events(profile_slug: Optional[str] = None) -> int:
    """Elimina gli eventi di un profilo (o tutti) e ritorna quanti ne ha rimossi."""
    rows = _read(_LOG_FILE, [])
    if not isinstance(rows, list):
        rows = []
    if profile_slug:
        tenuti = [row for row in rows if row.get("profilo") != profile_slug]
    else:
        tenuti = []
    _write(_LOG_FILE, tenuti)
    return len(rows) - len(tenuti)


# ---------------- Etichette per il registro ----------------
def describe_device(user_agent: str) -> str:
    """Riduce lo user-agent a un'etichetta leggibile (iPhone, Android, PC…)."""
    ua = (user_agent or "").lower()
    if not ua:
        return "Dispositivo sconosciuto"
    if "iphone" in ua:
        return "iPhone (Safari)" if "safari" in ua else "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android"
    if "windows" in ua:
        return "PC Windows"
    if "macintosh" in ua or "mac os" in ua:
        return "Mac"
    if "linux" in ua:
        return "Linux"
    return "Dispositivo sconosciuto"


def client_ip(request: Any) -> str:
    """IP del client, rispettando il primo hop di `X-Forwarded-For`."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    client = getattr(request, "client", None)
    return getattr(client, "host", "") or ""
