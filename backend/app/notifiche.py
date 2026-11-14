"""
Notifiche push reali per ATLAS AI v3.0.

Canale primario: **Expo Push Service** (gratuito, nessuna chiave richiesta,
usato da tutte le app Expo/React Native con `ExponentPushToken[...]`).
Canale secondario: **Firebase Cloud Messaging** (solo se il file credenziali
esiste e i token sono token FCM nativi).

Nessuna simulazione: se il servizio non è raggiungibile la funzione ritorna
False e il chiamante lo comunica all'utente.
"""
from __future__ import annotations

from typing import Any, Iterable

import requests

from app.core.logging_config import get_logger
from app.core.settings import expo_push_url, firebase_credentials_path

log = get_logger(__name__)

_FIREBASE_INIT = False
_FIREBASE_AVAILABLE = False

_EXPO_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Content-Type": "application/json",
}
_EXPO_CHUNK = 100


# ------------------------------------------------------------------
#  Firebase (opzionale, per token FCM/APNs nativi)
# ------------------------------------------------------------------
def _ensure_firebase() -> bool:
    """Inizializzazione lazy di Firebase, solo se il file credenziali esiste."""
    global _FIREBASE_INIT, _FIREBASE_AVAILABLE
    if _FIREBASE_INIT:
        return _FIREBASE_AVAILABLE
    _FIREBASE_INIT = True

    cred_path = firebase_credentials_path()
    try:
        import os

        if not os.path.exists(cred_path):
            log.info("Firebase non configurato (%s assente): uso solo Expo Push.", cred_path)
            return False
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
        _FIREBASE_AVAILABLE = True
        log.info("Firebase inizializzato da %s", cred_path)
    except Exception as exc:  # pragma: no cover - dipende da file esterni
        log.warning("Firebase NON disponibile: %s", exc)
        _FIREBASE_AVAILABLE = False
    return _FIREBASE_AVAILABLE


def is_expo_token(token: str) -> bool:
    return bool(token) and token.startswith(("ExponentPushToken[", "ExpoPushToken["))


# ------------------------------------------------------------------
#  Expo Push Service (reale, gratuito)
# ------------------------------------------------------------------
def _expo_message(token: str, titolo: str, messaggio: str, dati: dict | None) -> dict[str, Any]:
    return {
        "to": token,
        "title": f"🧠 ATLAS — {titolo}" if not titolo.startswith("🧠") else titolo,
        "body": str(messaggio)[:800],
        "data": {str(k): str(v) for k, v in (dati or {}).items()},
        "sound": "default",
        "priority": "high",
        "channelId": "atlas_default",
    }


def _disattiva_token_morto(token: str) -> None:
    """Disattiva un token che Expo ha dichiarato non più valido."""
    try:
        from app.core.database import deactivate_push_token

        deactivate_push_token(token)
        log.info("Token push disattivato (DeviceNotRegistered): %s…", token[:28])
    except Exception as exc:  # pragma: no cover - difensivo
        log.warning("Impossibile disattivare il token push: %s", exc)


def invia_push_multi(
    tokens: Iterable[str],
    titolo: str,
    messaggio: str,
    dati: dict | None = None,
) -> int:
    """Invia una notifica a più token. Ritorna il numero di invii accettati."""
    expo_tokens = [t for t in dict.fromkeys(tokens) if is_expo_token(t)]
    inviati = 0

    for start in range(0, len(expo_tokens), _EXPO_CHUNK):
        chunk = expo_tokens[start : start + _EXPO_CHUNK]
        payload = [_expo_message(token, titolo, messaggio, dati) for token in chunk]
        try:
            response = requests.post(expo_push_url(), json=payload, headers=_EXPO_HEADERS, timeout=15)
            response.raise_for_status()
            body = response.json()
            tickets = body.get("data") if isinstance(body, dict) else None
            if isinstance(tickets, dict):
                tickets = [tickets]
            for ticket, token in zip(tickets or [], chunk):
                if isinstance(ticket, dict) and ticket.get("status") == "ok":
                    inviati += 1
                    continue
                details = ticket.get("details") if isinstance(ticket, dict) else None
                if isinstance(details, dict) and details.get("error") == "DeviceNotRegistered":
                    _disattiva_token_morto(token)
                log.warning("Expo push rifiutata: %s", ticket)
        except requests.RequestException as exc:
            log.warning("Expo Push non raggiungibile: %s", exc)
        except (ValueError, TypeError) as exc:
            log.warning("Risposta Expo Push non valida: %s", exc)

    # Token non-Expo: tentiamo Firebase se configurato.
    other_tokens = [t for t in dict.fromkeys(tokens) if t and not is_expo_token(t)]
    if other_tokens and _ensure_firebase():
        for token in other_tokens:
            if invia_push(token, titolo, messaggio, dati):
                inviati += 1

    return inviati


def invia_push(token_dispositivo: str, titolo: str, messaggio: str, dati: dict | None = None) -> bool:
    """Invia una singola notifica push. True se il servizio l'ha accettata."""
    if not token_dispositivo:
        log.warning("Tentativo invio push senza token dispositivo.")
        return False

    if is_expo_token(token_dispositivo):
        return invia_push_multi([token_dispositivo], titolo, messaggio, dati) > 0

    if not _ensure_firebase():
        log.warning("Token push non-Expo senza Firebase configurato: invio non possibile.")
        return False

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(
                title=f"🧠 ATLAS — {titolo}" if not titolo.startswith("🧠") else titolo,
                body=str(messaggio),
            ),
            data={str(k): str(v) for k, v in (dati or {}).items()},
            token=token_dispositivo,
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(badge=1, sound="default", category="ATLAS_ACTION")
                )
            ),
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="atlas_default",
                    default_sound=True,
                ),
            ),
        )
        message_id = messaging.send(message)
        log.info("Push FCM inviata: %s", str(message_id)[:80])
        return True
    except Exception as exc:  # pragma: no cover - dipende da servizio esterno
        log.exception("Errore invio push FCM: %s", exc)
        return False


# ------------------------------------------------------------------
#  Helper per profilo / famiglia (token presi dal DB)
# ------------------------------------------------------------------
def invia_a_profilo(
    profile_slug: str,
    titolo: str,
    messaggio: str,
    dati: dict | None = None,
) -> int:
    """Invia la notifica a tutti i dispositivi registrati di un profilo."""
    from app.core.database import get_push_tokens

    tokens = [row.get("token", "") for row in get_push_tokens(profile_slug) if row.get("token")]
    if not tokens:
        log.info("Nessun dispositivo registrato per %s: notifica non inviata.", profile_slug)
        return 0
    return invia_push_multi(tokens, titolo, messaggio, dati)


def invia_a_tutti(titolo: str, messaggio: str, dati: dict | None = None) -> int:
    """Invia la notifica a tutti i dispositivi della famiglia."""
    from app.core.database import get_push_tokens

    tokens = [row.get("token", "") for row in get_push_tokens() if row.get("token")]
    if not tokens:
        log.info("Nessun dispositivo registrato: notifica non inviata.")
        return 0
    return invia_push_multi(tokens, titolo, messaggio, dati)
