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
from app.core.secrets_box import is_sealed, seal, unseal
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
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
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
    """Token decifrati; i valori legacy in chiaro vengono risigillati subito."""
    raw = get_setting(_TOKENS_KEY, {}) or {}
    tokens = unseal(raw)
    if tokens and not is_sealed(raw) and (tokens.get("access_token") or tokens.get("refresh_token")):
        try:
            _save_tokens(tokens)
            log.info("Token Google in chiaro migrati al formato cifrato")
        except Exception as exc:  # pragma: no cover - difensivo
            log.warning("Migrazione token Google cifrati fallita: %s", exc)
    return tokens


def _save_tokens(tokens: dict[str, Any]) -> None:
    """Salva i token cifrati a riposo: mai access/refresh token in chiaro."""
    set_setting(_TOKENS_KEY, seal(tokens))


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
    _save_tokens(tokens)

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
    """Revoca i permessi su Google e cancella i token locali.

    La sola cancellazione locale lascerebbe l'app autorizzata nel tuo account
    Google: qui chiamiamo l'endpoint di revoca per access e refresh token.
    Se la chiamata fallisce (offline, token già scaduto) i token vengono
    comunque rimossi: l'utente può revocare a mano da myaccount.google.com.
    """
    tokens = _stored_tokens()
    for key in ("refresh_token", "access_token"):
        token = str(tokens.get(key) or "").strip()
        if not token:
            continue
        try:
            requests.post(REVOKE_ENDPOINT, data={"token": token}, timeout=10)
        except requests.RequestException as exc:
            log.warning("Revoca token Google fallita (%s): %s", key, exc)
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
    _save_tokens(tokens)
    return str(new_token)


# ------------------------------------------------------------------
#  Helper REST
# ------------------------------------------------------------------
def _authorized(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Richiesta autenticata, con un retry dopo refresh del token su 401."""
    token = access_token()
    if not token:
        raise GoogleAuthError("Account Google non collegato.")

    def _send(current: str) -> "requests.Response":
        return requests.request(
            method,
            url,
            params=params,
            json=body,
            headers={"Authorization": f"Bearer {current}"},
            timeout=20,
        )

    try:
        response = _send(token)
        if response.status_code == 401:
            refreshed = access_token(force_refresh=True)
            if not refreshed:
                raise GoogleAuthError("Sessione Google scaduta: ricollega l'account.")
            response = _send(refreshed)
        response.raise_for_status()
        if method == "DELETE" or not response.content:
            return {}
        return response.json()
    except requests.RequestException as exc:
        raise GoogleAuthError(f"Errore Google API: {exc}") from exc


def api_get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET autenticata su Google API. Solleva `GoogleAuthError` se non connesso."""
    return _authorized("GET", url, params=params)


def api_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST autenticata su Google API."""
    return _authorized("POST", url, body=body)


def api_patch(url: str, body: dict[str, Any]) -> dict[str, Any]:
    """PATCH autenticata (modifica parziale di un evento)."""
    return _authorized("PATCH", url, body=body)


def api_delete(url: str) -> dict[str, Any]:
    """DELETE autenticata (eliminazione di un evento)."""
    return _authorized("DELETE", url)


class GoogleAuthError(RuntimeError):
    """Account Google assente o token non più valido."""


def oauth_success_deeplink() -> str:
    return f"{app_deeplink()}?google=ok"


def oauth_error_deeplink(reason: str = "error") -> str:
    return f"{app_deeplink()}?google={reason}"
