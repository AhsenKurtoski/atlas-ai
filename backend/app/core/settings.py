"""
Configurazione centralizzata di ATLAS AI.

Unico punto di accesso alle variabili d'ambiente, con alias accettati per
retrocompatibilità (es. `GOOGLE_API_KEY_1` / `GEMINI_KEY_1`). In questo modo
README, .env.example e codice non possono divergere silenziosamente.
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
LOCAL_DB_DIR = BACKEND_DIR / "_local_db"

TRUTHY = {"1", "true", "yes", "on", "si", "sì"}


def env(*names: str, default: str = "") -> str:
    """Prima variabile d'ambiente non vuota tra `names` (in ordine)."""
    for name in names:
        raw = os.getenv(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return default


def env_int(*names: str, default: int) -> int:
    raw = env(*names)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def env_float(*names: str, default: float) -> float:
    raw = env(*names)
    try:
        return float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return default


def env_bool(*names: str, default: bool = False) -> bool:
    raw = env(*names)
    if not raw:
        return default
    return raw.lower() in TRUTHY


def app_env() -> str:
    return env("APP_ENV", default="development").lower()


def is_production() -> bool:
    return app_env() in {"production", "prod"}


# ---------------- LLM ----------------
def gemini_api_keys() -> list[str]:
    """Chiavi Gemini configurate (fino a 3), con alias GOOGLE_/GEMINI_."""
    keys: list[str] = []
    for index in range(1, 4):
        key = env(f"GOOGLE_API_KEY_{index}", f"GEMINI_KEY_{index}")
        if key and not key.upper().startswith(("INSERISCI", "YOUR_", "CHANGE_ME")):
            keys.append(key)
    return keys


def gemini_model() -> str:
    # gemini-2.0-flash è stato ritirato da Google; 3.5-flash-lite è disponibile
    # anche sul free tier mentre i modelli 3.8 Flash sono sovraccarichi.
    return env("GEMINI_MODEL", default="gemini-3.5-flash-lite")


# ---------------- CORS / rete ----------------
def cors_origins() -> list[str]:
    """Origini web consentite.

    In produzione il default è **nessuna origine** (fail closed): le app native
    non usano CORS, quindi solo una preview web esplicita va autorizzata con
    `CORS_ALLOWED_ORIGINS`. In sviluppo resta la wildcard per comodità.
    """
    raw = env("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return [] if is_production() else ["*"]
    if app_env() == "development":
        for extra in ("http://localhost:8081", "http://localhost:19006", "http://localhost:19000"):
            if extra not in parts:
                parts.append(extra)
    # "*" è incompatibile con allow_credentials: lo trattiamo come wildcard puro.
    return parts


def supabase_config() -> tuple[str, str]:
    url = env("SUPABASE_URL")
    key = env("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    return url, key


# ---------------- Notifiche ----------------
def expo_push_url() -> str:
    return env("EXPO_PUSH_URL", default="https://exp.host/--/api/v2/push/send")


def firebase_credentials_path() -> str:
    return env("FIREBASE_CREDENTIALS", default=str(BACKEND_DIR / "firebase-credentials.json"))


# ---------------- Google (Gmail + Calendar) ----------------
def google_client_id() -> str:
    return env("GOOGLE_CLIENT_ID")


def google_client_secret() -> str:
    return env("GOOGLE_CLIENT_SECRET")


def google_redirect_uri() -> str:
    return env("GOOGLE_REDIRECT_URI")


def app_deeplink() -> str:
    return env("APP_DEEPLINK", default="atlasai://oauth")


# ---------------- Scheduler ----------------
def default_city() -> str:
    """Città usata dalle automazioni meteo (briefing e ombrello)."""
    return env("ATLAS_CITY", default="Milano")


def scheduler_timezone() -> str:
    return env("SCHEDULER_TIMEZONE", default="Europe/Rome")


def scheduler_enabled() -> bool:
    return env_bool("SCHEDULER_ENABLED", default=True)


# ---------------- Agente / browser ----------------
def agent_max_tool_turns() -> int:
    """Numero massimo di turni di function calling (browser incluso)."""
    return max(1, min(20, env_int("AGENT_MAX_TOOL_TURNS", default=10)))
