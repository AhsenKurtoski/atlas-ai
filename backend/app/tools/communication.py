"""
Tool Gmail e Google Calendar REALI per ATLAS AI v3.0.

Usano l'integrazione OAuth in `app.services.google_oauth` (gratuita: si creano
le credenziali su Google Cloud Console una volta sola). Se l'account non è
collegato, i tool lo dicono chiaramente e spiegano come collegarlo: non
restituiscono mai un finto successo.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.logging_config import get_logger
from app.core.settings import scheduler_timezone
from app.services.google_oauth import (
    CALENDAR_API,
    GMAIL_API,
    GoogleAuthError,
    api_get,
    api_post,
    status as google_status,
)

log = get_logger(__name__)

_NOT_CONNECTED = (
    "⚠️ Account Google non collegato.\n"
    "Apri Impostazioni → «Connetti Gmail/Calendar» nell'app, oppure imposta "
    "GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nel backend/.env e usa il pulsante "
    "di connessione. Nessun dato viene inventato finché non colleghi l'account."
)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(scheduler_timezone())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Rome")


def _header(message: dict[str, Any], name: str) -> str:
    for header in (message.get("payload") or {}).get("headers") or []:
        if str(header.get("name", "")).lower() == name.lower():
            return str(header.get("value", ""))
    return ""


# ---------------- Gmail ----------------
def gmail_leggi_email(limite: int = 5) -> str:
    """Legge le ultime email della inbox Gmail collegata.

    Args:
        limite: Numero di email da leggere (1-15, default 5).
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED

    limit = max(1, min(int(limite or 5), 15))
    try:
        listing = api_get(
            f"{GMAIL_API}/users/me/messages",
            {"maxResults": limit, "labelIds": "INBOX"},
        )
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    messages = listing.get("messages") or []
    if not messages:
        return "📭 Inbox vuota: nessuna email da leggere."

    righe: list[str] = []
    for index, item in enumerate(messages, 1):
        try:
            detail = api_get(
                f"{GMAIL_API}/users/me/messages/{item['id']}",
                {
                    "format": "metadata",
                    "metadataHeaders": ["Subject", "From", "Date"],
                },
            )
        except (GoogleAuthError, KeyError) as exc:
            log.warning("Lettura email %s fallita: %s", item.get("id"), exc)
            continue
        oggetto = _header(detail, "Subject") or "(nessun oggetto)"
        mittente = _header(detail, "From") or "?"
        data_email = _header(detail, "Date") or ""
        estratto = (detail.get("snippet") or "")[:160]
        righe.append(
            f"{index}. **{oggetto}**\n"
            f"   Da: {mittente}" + (f" · {data_email}" if data_email else "") + "\n"
            f"   {estratto}"
        )

    if not righe:
        return "📭 Nessuna email leggibile al momento."
    return f"📧 Ultime {len(righe)} email:\n\n" + "\n\n".join(righe)


def gmail_cerca_appuntamenti() -> str:
    """Cerca nelle email appuntamenti, visite o riunioni imminenti."""
    if not google_status()["connesso"]:
        return _NOT_CONNECTED

    query = (
        "subject:(appuntamento OR visita OR prenotazione OR riunione OR invito) "
        "newer_than:30d"
    )
    try:
        listing = api_get(
            f"{GMAIL_API}/users/me/messages",
            {"q": query, "maxResults": 8},
        )
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    messages = listing.get("messages") or []
    if not messages:
        return "📅 Nessun appuntamento trovato nelle email degli ultimi 30 giorni."

    righe: list[str] = ["📅 Possibili appuntamenti trovati:"]
    for item in messages:
        try:
            detail = api_get(
                f"{GMAIL_API}/users/me/messages/{item['id']}",
                {"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
        except (GoogleAuthError, KeyError) as exc:
            log.debug("Dettaglio email appuntamento fallito: %s", exc)
            continue
        righe.append(
            f"- **{_header(detail, 'Subject') or '(nessun oggetto)'}** "
            f"({_header(detail, 'Date') or 'data sconosciuta'})\n  "
            f"{(detail.get('snippet') or '')[:140]}"
        )
    return "\n".join(righe)


# ---------------- Calendar ----------------
def calendar_crea_evento(
    titolo: str,
    data: str,
    ora: str = "09:00",
    descrizione: str = "",
    durata_minuti: int = 60,
    fuso_orario: str = "",
) -> str:
    """Crea un evento sul Google Calendar collegato.

    Args:
        titolo: Titolo dell'evento (es. "Visita medica mamma").
        data: Data in formato YYYY-MM-DD.
        ora: Ora di inizio in formato HH:MM (default 09:00).
        descrizione: Note opzionali.
        durata_minuti: Durata in minuti (default 60).
        fuso_orario: Fuso IANA, es. Europe/Rome (vuoto = quello dello scheduler).
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED

    nome_fuso = (fuso_orario or "").strip() or str(_tz())
    try:
        zone = ZoneInfo(nome_fuso)
    except (ZoneInfoNotFoundError, ValueError):
        return f"Fuso orario sconosciuto: {nome_fuso!r}. Usa un nome IANA, es. Europe/Rome."

    try:
        start_date = datetime.strptime(f"{data.strip()} {ora.strip()[:5]}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "Data o ora non valide. Usa data YYYY-MM-DD e ora HH:MM (es. 2026-03-20, 15:30)."

    durata = max(15, min(int(durata_minuti or 60), 480))
    start = start_date.replace(tzinfo=zone)
    end = start + timedelta(minutes=durata)

    body = {
        "summary": titolo.strip()[:200] or "Evento ATLAS",
        "description": (descrizione or "").strip()[:2000],
        "start": {"dateTime": start.isoformat(), "timeZone": nome_fuso},
        "end": {"dateTime": end.isoformat(), "timeZone": nome_fuso},
        "reminders": {"useDefault": True},
    }
    try:
        created = api_post(f"{CALENDAR_API}/calendars/primary/events", body)
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    link = created.get("htmlLink") or ""
    event_id = created.get("id") or ""
    from app.tools.google_advanced import overlap_warning

    return (
        f"✅ Evento «{body['summary']}» creato per il "
        f"{start.strftime('%d/%m/%Y alle %H:%M')}–{end.strftime('%H:%M')} ({nome_fuso})."
        + (f"\n🆔 id: {event_id}" if event_id else "")
        + (f"\n🔗 {link}" if link else "")
        + overlap_warning(start, end)
    )


def calendar_agenda(data: str = "") -> str:
    """Mostra gli appuntamenti in agenda per un giorno (default oggi).

    Args:
        data: Data in formato YYYY-MM-DD (vuoto = oggi).
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED

    giorno = data.strip() or date.today().isoformat()
    try:
        day = datetime.strptime(giorno, "%Y-%m-%d").date()
    except ValueError:
        return "Data non valida: usa il formato YYYY-MM-DD."

    time_min = datetime.combine(day, time.min, tzinfo=_tz()).isoformat()
    time_max = datetime.combine(day, time.max, tzinfo=_tz()).isoformat()
    try:
        payload = api_get(
            f"{CALENDAR_API}/calendars/primary/events",
            {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    events = payload.get("items") or []
    if not events:
        return f"📋 Agenda del {day.strftime('%d/%m/%Y')}: nessun evento."

    righe = [f"📋 Agenda del {day.strftime('%d/%m/%Y')} ({_tz()}):"]
    for event in events:
        start_info = event.get("start") or {}
        end_info = event.get("end") or {}
        start_raw = start_info.get("dateTime") or start_info.get("date") or ""
        end_raw = end_info.get("dateTime") or end_info.get("date") or ""
        if "T" in start_raw:
            orario = start_raw[11:16] + (f"–{end_raw[11:16]}" if "T" in end_raw else "")
        else:
            orario = "tutto il giorno"
        event_id = str(event.get("id") or "")
        righe.append(
            f"  {orario} — {event.get('summary') or '(senza titolo)'}"
            + (f" [id: {event_id}]" if event_id else "")
        )
    return "\n".join(righe)
