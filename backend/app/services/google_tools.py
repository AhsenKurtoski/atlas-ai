"""
Wrapper di compatibilità per Google Calendar/Gmail.

⚠️ Le implementazioni reali vivono in `app.tools.communication` (Gmail e
Calendar via OAuth) e in `app.services.google_oauth` (flusso token). Questo
modulo non restituisce più risposte finte: se l'account non è collegato lo
dice esplicitamente.
"""
from __future__ import annotations

from app.services import google_oauth
from app.tools.communication import (
    calendar_agenda,
    calendar_crea_evento,
    gmail_leggi_email,
)

__all__ = [
    "create_calendar_event",
    "get_calendar_events",
    "is_google_connected",
    "prepare_email_draft",
    "read_inbox",
]


def is_google_connected() -> bool:
    """True se un account Google è realmente collegato."""
    return bool(google_oauth.status().get("connesso"))


def get_calendar_events(user_id: str, date: str) -> str:
    """Eventi del calendario per una data (delega all'integrazione reale)."""
    _ = user_id  # il token OAuth è unico per la famiglia
    return calendar_agenda(date)


def create_calendar_event(user_id: str, title: str, date: str, time: str) -> str:
    """Crea un evento reale sul calendario Google collegato."""
    _ = user_id
    return calendar_crea_evento(titolo=title, data=date, ora=time)


def prepare_email_draft(user_id: str, to: str, subject: str, body: str) -> str:
    """Compone una bozza di email (l'invio richiede conferma esplicita)."""
    _ = user_id
    return (
        "📝 Bozza email pronta (nessun invio automatico):\n"
        f"A: {to}\nOggetto: {subject}\n\n{body}\n\n"
        "Conferma l'invio dall'app per procedere."
    )


def read_inbox(limite: int = 5) -> str:
    """Legge le ultime email reali dalla inbox collegata."""
    return gmail_leggi_email(limite)
