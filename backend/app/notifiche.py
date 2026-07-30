"""
Notifiche push per ATLAS AI v3.0 (Firebase Admin SDK con fallback mock).
"""
from __future__ import annotations

import os

from app.core.logging_config import get_logger

log = get_logger(__name__)

_FIREBASE_INIT = False
_FIREBASE_AVAILABLE = False


def _ensure_init() -> bool:
    """Inizializzazione lazy di Firebase (solo se file credenziali esiste)."""
    global _FIREBASE_INIT, _FIREBASE_AVAILABLE
    if _FIREBASE_INIT:
        return _FIREBASE_AVAILABLE
    cred_path = os.getenv("FIREBASE_CREDENTIALS", "./firebase-credentials.json")
    try:
        if os.path.exists(cred_path):
            import firebase_admin  # import lazy per non crashare senza SDK
            from firebase_admin import credentials, messaging

            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            _FIREBASE_AVAILABLE = True
            log.info("Firebase inizializzato.")
    except Exception as exc:
        log.warning("Firebase NON disponibile: %s", exc)
        _FIREBASE_AVAILABLE = False
    finally:
        _FIREBASE_INIT = True
    return _FIREBASE_AVAILABLE


def invia_push(token_dispositivo: str, titolo: str, messaggio: str, dati: dict | None = None) -> bool:
    """
    Invia una notifica push (Firebase Cloud Messaging).

    Restituisce True se inviata con successo, False altrimenti.
    In assenza di Firebase logga la notifica in modo "mock" per agevolare
    lo sviluppo locale.
    """
    if not token_dispositivo:
        log.warning("Tentativo invio push senza token dispositivo.")
        return False

    dati = dati or {}

    if not _ensure_init():
        log.info(
            "[MOCK PUSH] A: %s | %s: %s | Dati: %s",
            token_dispositivo[:10] + "...",
            titolo,
            messaggio[:80],
            dati,
        )
        return False

    try:
        from firebase_admin import messaging  # noqa: F811 - import lazy

        msg = messaging.Message(
            notification=messaging.Notification(
                title=f"🧠 ATLAS — {titolo}" if not titolo.startswith("🧠") else titolo,
                body=str(messaggio),
            ),
            data={str(k): str(v) for k, v in dati.items()},
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
                    click_action="FLUTTER_NOTIFICATION_CLICK",
                    default_sound=True,
                ),
            ),
        )
        response = messaging.send(msg)
        log.info("Push inviata con successo: %s", str(response)[:80])
        return True
    except Exception as exc:
        log.exception("Errore invio push: %s", exc)
        return False
