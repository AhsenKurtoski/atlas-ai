"""
Integrazione Google reale (Gmail + Calendar) per ATLAS AI v3.0.

Flusso OAuth2 "authorization code" lato server (gratuito, nessun servizio a
pagamento). Le credenziali dell'app Google si creano gratis su
https://console.cloud.google.com/apis/credentials e si mettono nel `.env`:

    GOOGLE_CLIENT_ID=...
    GOOGLE_CLIENT_SECRET=...
    GOOGLE_REDIRECT_URI=http://localhost:8000/integrazioni/google/callback

I token (access + refresh) vengono salvati nel DB/configurazione dell'app
(Supabase o file locale) e mai esposti al client.
"""
from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from app.core.database import get_setting, set_setting
from app.core.logging_config import get_logger
from app.core.security import create_access_token, decode_access_token
from app.core.settings import (
    app_deeplink,
    google_client_id,
    google_client_secret,
    google_redirect_uri,
)

log = get_logger(__name__)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_TOKENS_KEY = "google.tokens"
_EMAIL_KEY = "google.email"
_STATE_SLUG = "google-oauth"


# ------------------------------------------------------------------
#  Configurazione / stato
# ------------------------------------------------------------------
def is_configured() -> bool:
    return bool(google_client_id() and google_client_secret())


def default_redirect_uri(base_url: str = "") -> str:
    explicit = google_redirect_uri()
    if explicit:
        return explicit
    base = (base_url or "http://localhost:8000").rstrip("/")
    return f"{base}/integrazioni/google/callback"


def _stored_tokens() -> dict[str, Any]:
    data = get_setting(_TOKENS_KEY, {}) or {}
    return data if isinstance(data, dict) else {}


def status() -> dict[str, Any]:
    tokens = _stored_tokens()
    return {
        "configurato": is_configured(),
        "connesso": bool(tokens.get("refresh_token") or tokens.get("access_token")),
        "email": get_setting(_EMAIL_KEY, "") or "",
        "redirect_uri": default_redirect_uri(),
        "istruzioni": (
            ""
            if is_configured()
            else "Crea credenziali OAuth (gratuito) su console.cloud.google.com, "
            "abilita Gmail API e Google Calendar API, poi imposta GOOGLE_CLIENT_ID e "
            "GOOGLE_CLIENT_SECRET nel backend/.env."
        ),
    }


def build_auth_url(base_url: str = "") -> str:
    """URL di consenso Google. Lo `state` è firmato HMAC (anti-CSRF)."""
    if not is_configured():
        raise RuntimeError("Integrazione Google non configurata (GOOGLE_CLIENT_ID/SECRET mancanti).")
    state = create_access_token(_STATE_SLUG, ttl_seconds=900)
    params = {
        "client_id": google_client_id(),
        "redirect_uri": default_redirect_uri(base_url),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def validate_state(state: str) -> bool:
    return decode_access_token(state or "") == _STATE_SLUG


def exchange_code(code: str, base_url: str = "") -> bool:
    """Scambia il `code` OAuth con i token e li salva. True se riuscito."""
    if not is_configured():
        return False
    payload = {
        "code": code,
        "client_id": google_client_id(),
        "client_secret": google_client_secret(),
        "redirect_uri": default_redirect_uri(base_url),
        "grant_type": "authorization_code",
    }
    try:
        response = requests.post(TOKEN_ENDPOINT, data=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.error("Scambio codice Google fallito: %s", exc)
        return False

    access_token = data.get("access_token")
    if not access_token:
        log.error("Risposta token Google priva di access_token: %s", list(data))
        return False

    tokens = {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token") or _stored_tokens().get("refresh_token", ""),
        "expires_at": int(time.time()) + int(data.get("expires_in", 3600)) - 30,
        "scope": data.get("scope", ""),
    }
    set_setting(_TOKENS_KEY, tokens)

    email = _fetch_email(access_token)
    if email:
        set_setting(_EMAIL_KEY, email)
    log.info("Google collegato%s", f" per {email}" if email else "")
    return True


def _fetch_email(access_token: str) -> str:
    try:
        response = requests.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json().get("email") or "")
    except (requests.RequestException, ValueError) as exc:
        log.debug("Impossibile leggere email Google: %s", exc)
        return ""


def disconnect() -> None:
    set_setting(_TOKENS_KEY, {})
    set_setting(_EMAIL_KEY, "")


def access_token(force_refresh: bool = False) -> Optional[str]:
    """Token di accesso valido (rinnova automaticamente con il refresh token)."""
    tokens = _stored_tokens()
    if not tokens:
        return None
    current = tokens.get("access_token")
    expires_at = int(tokens.get("expires_at") or 0)
    if current and not force_refresh and expires_at > int(time.time()):
        return str(current)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token or not is_configured():
        return str(current) if current and expires_at > int(time.time()) else None

    try:
        response = requests.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": google_client_id(),
                "client_secret": google_client_secret(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Refresh token Google fallito: %s", exc)
        return None

    new_token = data.get("access_token")
    if not new_token:
        log.warning("Refresh Google senza access_token: %s", list(data))
        return None

    tokens.update(
        {
            "access_token": new_token,
            "expires_at": int(time.time()) + int(data.get("expires_in", 3600)) - 30,
        }
    )
    set_setting(_TOKENS_KEY, tokens)
    return str(new_token)


# ------------------------------------------------------------------
#  Helper REST
# ------------------------------------------------------------------
def api_get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET autenticata su Google API. Solleva `GoogleAuthError` se non connesso."""
    token = access_token()
    if not token:
        raise GoogleAuthError("Account Google non collegato.")
    try:
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if response.status_code == 401:
            token = access_token(force_refresh=True)
            if not token:
                raise GoogleAuthError("Sessione Google scaduta: ricollega l'account.")
            response = requests.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise GoogleAuthError(f"Errore Google API: {exc}") from exc


def api_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST autenticata su Google API."""
    token = access_token()
    if not token:
        raise GoogleAuthError("Account Google non collegato.")
    try:
        response = requests.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=20,
        )
        if response.status_code == 401:
            token = access_token(force_refresh=True)
            if not token:
                raise GoogleAuthError("Sessione Google scaduta: ricollega l'account.")
            response = requests.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=20,
            )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise GoogleAuthError(f"Errore Google API: {exc}") from exc


class GoogleAuthError(RuntimeError):
    """Account Google assente o token non più valido."""


def oauth_success_deeplink() -> str:
    return f"{app_deeplink()}?google=ok"


def oauth_error_deeplink(reason: str = "error") -> str:
    return f"{app_deeplink()}?google={reason}"
