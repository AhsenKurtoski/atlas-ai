"""
Gmail e Calendar: ricerca email, allegati, bozza con conferma, eventi modificabili.

Regole di sicurezza di questo modulo:

- nessun tool invia email: `gmail_prepara_email` salva una bozza e l'invio
  avviene solo da `POST /integrazioni/gmail/bozza/invia` con `conferma: true`,
  cioè dopo un'azione esplicita dell'utente nell'app;
- nessun invito a partecipanti viene creato implicitamente: gli eventi non
  hanno `attendees` se non li aggiunge l'utente dal calendario Google;
- i fusi orari sono IANA validati (`ZoneInfo`), mai offset inventati.

Se l'account Google non è collegato ogni funzione lo dice e non finge nulla.
"""
from __future__ import annotations

import base64
import re
import threading
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.context import current_profile
from app.core.database import get_setting, set_setting
from app.core.logging_config import get_logger
from app.core.settings import scheduler_timezone
from app.services.google_oauth import (
    CALENDAR_API,
    GMAIL_API,
    GoogleAuthError,
    api_delete,
    api_get,
    api_patch,
    api_post,
    status as google_status,
)

log = get_logger(__name__)

_NOT_CONNECTED = (
    "⚠️ Account Google non collegato.\n"
    "Apri Impostazioni → «Connetti Gmail/Calendar» nell'app, oppure imposta "
    "GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nel backend/.env."
)

_DRAFT_KEY = "google.bozza"
# Un solo invio alla volta: due tap su «Invia» non devono spedire due email.
_SEND_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_BODY = 20_000
_MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024


# ------------------------------------------------------------------
#  Helper
# ------------------------------------------------------------------
def _tz(name: str = "") -> tuple[ZoneInfo, str]:
    """Fuso IANA richiesto, oppure quello dello scheduler."""
    candidate = (name or "").strip() or scheduler_timezone()
    try:
        zone = ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Fuso orario sconosciuto: {candidate!r}. Usa un nome IANA, es. Europe/Rome.")
    return zone, candidate


def _walk_parts(part: dict[str, Any]) -> list[dict[str, Any]]:
    found = [part]
    for child in part.get("parts") or []:
        found.extend(_walk_parts(child))
    return found


def _attachment_info(message: dict[str, Any]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for part in _walk_parts(message.get("payload") or {}):
        filename = str(part.get("filename") or "").strip()
        body = part.get("body") or {}
        attachment_id = str(body.get("attachmentId") or "")
        if filename and attachment_id:
            files.append(
                {
                    "filename": filename,
                    "mime": str(part.get("mimeType") or "application/octet-stream"),
                    "size": str(body.get("size") or 0),
                    "attachment_id": attachment_id,
                    "message_id": str(message.get("id") or ""),
                }
            )
    return files


def _latest_message_id() -> str:
    listing = api_get(f"{GMAIL_API}/users/me/messages", {"maxResults": 1, "labelIds": "INBOX"})
    messages = listing.get("messages") or []
    return str(messages[0].get("id") or "") if messages else ""


# ------------------------------------------------------------------
#  Gmail: ricerca e allegati
# ------------------------------------------------------------------
def gmail_cerca_email(
    mittente: str = "",
    oggetto: str = "",
    testo: str = "",
    dopo: str = "",
    prima: str = "",
    limite: int = 5,
) -> str:
    """Cerca email per mittente, oggetto, parole o intervallo di date.

    Args:
        mittente: Email o nome del mittente (es. "studio@medico.it").
        oggetto: Parole presenti nell'oggetto.
        testo: Parole nel corpo dell'email.
        dopo: Data minima YYYY-MM-DD (inclusa).
        prima: Data massima YYYY-MM-DD (esclusa).
        limite: Numero di risultati (1-10, default 5).
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED

    parti: list[str] = []
    if mittente.strip():
        parti.append(f"from:({mittente.strip()})")
    if oggetto.strip():
        parti.append(f"subject:({oggetto.strip()})")
    if testo.strip():
        parti.append(testo.strip())
    for valore, prefisso in ((dopo, "after"), (prima, "before")):
        if valore.strip():
            try:
                giorno = datetime.strptime(valore.strip(), "%Y-%m-%d")
            except ValueError:
                return "Data non valida: usa il formato YYYY-MM-DD."
            parti.append(f"{prefisso}:{giorno.strftime('%Y/%m/%d')}")

    if not parti:
        return "Servono almeno un criterio (mittente, oggetto, testo o date) per cercare."

    limit = max(1, min(int(limite or 5), 10))
    query = " ".join(parti)
    try:
        listing = api_get(
            f"{GMAIL_API}/users/me/messages",
            {"q": query, "maxResults": limit},
        )
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    messages = listing.get("messages") or []
    if not messages:
        return f"🔎 Nessuna email trovata per: {query}"

    righe = [f"🔎 {len(messages)} email trovate per «{query}»:"]
    for index, item in enumerate(messages, 1):
        try:
            detail = api_get(
                f"{GMAIL_API}/users/me/messages/{item['id']}",
                {"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
        except (GoogleAuthError, KeyError) as exc:
            log.debug("Dettaglio ricerca email fallito: %s", exc)
            continue
        headers = {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in (detail.get("payload") or {}).get("headers") or []}
        righe.append(
            f"{index}. **{headers.get('subject') or '(nessun oggetto)'}**\n"
            f"   Da: {headers.get('from') or '?'} · {headers.get('date') or 'data sconosciuta'}\n"
            f"   id: {detail.get('id')}\n"
            f"   {(detail.get('snippet') or '')[:140]}"
        )
    return "\n\n".join(righe)


def gmail_allegati(message_id: str = "", limite: int = 10) -> str:
    """Elenca gli allegati di un'email (default: l'ultima della inbox).

    Args:
        message_id: id dell'email (opzionale; vuoto = ultima ricevuta).
        limite: numero massimo di allegati da mostrare (default 10).
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED
    try:
        mid = message_id.strip() or _latest_message_id()
        if not mid:
            return "📭 Inbox vuota: nessun allegato da leggere."
        message = api_get(f"{GMAIL_API}/users/me/messages/{mid}", {"format": "full"})
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    files = _attachment_info(message)
    if not files:
        return "📎 Nessun allegato in questa email."

    righe = [f"📎 Allegati di «{_subject(message)}»:"]
    for item in files[: max(1, int(limite or 10))]:
        kb = int(item["size"] or 0) / 1024
        righe.append(f"- {item['filename']} ({item['mime']}, {kb:.0f} KB)")
    righe.append(
        "\nPer rispondere allegando uno di questi file, chiedi di preparare l'email "
        "indicando il nome del file."
    )
    return "\n".join(righe)


def _subject(message: dict[str, Any]) -> str:
    for header in (message.get("payload") or {}).get("headers") or []:
        if str(header.get("name", "")).lower() == "subject":
            return str(header.get("value") or "(nessun oggetto)")
    return "(nessun oggetto)"


# ------------------------------------------------------------------
#  Gmail: bozza + invio con conferma esplicita
# ------------------------------------------------------------------
def gmail_prepara_email(
    destinatario: str,
    oggetto: str,
    corpo: str,
    allegato: str = "",
    message_id: str = "",
) -> str:
    """Prepara una bozza di email. NON invia: serve la conferma dell'utente nell'app.

    Args:
        destinatario: indirizzo email del destinatario.
        oggetto: oggetto dell'email.
        corpo: testo del messaggio.
        allegato: nome file di un allegato ricevuto (opzionale).
        message_id: id dell'email da cui prendere l'allegato (opzionale).
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED

    to = destinatario.strip()
    if not _EMAIL_RE.match(to):
        return "Indirizzo email non valido: serve un indirizzo come nome@dominio.it."
    subject = oggetto.strip()[:200]
    if not subject:
        return "Serve un oggetto per la bozza."
    body = corpo.strip()
    if not body:
        return "Serve il testo dell'email."
    if len(body) > _MAX_BODY:
        return f"Testo troppo lungo ({len(body)} caratteri, massimo {_MAX_BODY})."

    attachment: dict[str, str] | None = None
    if allegato.strip():
        try:
            mid = message_id.strip() or _latest_message_id()
            message = api_get(f"{GMAIL_API}/users/me/messages/{mid}", {"format": "full"})
        except GoogleAuthError as exc:
            return f"⚠️ {exc}"
        wanted = allegato.strip().lower()
        match = next((f for f in _attachment_info(message) if f["filename"].lower() == wanted), None)
        if match is None:
            disponibili = ", ".join(f["filename"] for f in _attachment_info(message)) or "nessuno"
            return f"Allegato «{allegato}» non trovato. Disponibili: {disponibili}."
        if int(match["size"] or 0) > _MAX_ATTACHMENT_BYTES:
            return "Allegato troppo grande per l'invio (massimo 8 MB)."
        attachment = match

    draft = {
        "a": to,
        "oggetto": subject,
        "corpo": body,
        "allegato": attachment,
        "creata": datetime.now(ZoneInfo("UTC")).isoformat(),
        "profilo": current_profile.get(),
    }
    set_setting(_DRAFT_KEY, draft)
    log.info("Bozza email preparata per %s (da %s), in attesa di conferma", to, draft["profilo"])
    extra = f"\n📎 Allegato: {attachment['filename']}" if attachment else ""
    return (
        "✋ **Bozza pronta, non inviata.**\n"
        f"A: {to}\nOggetto: {subject}\n\n{body}{extra}\n\n"
        "Conferma l'invio dal banner «Invia email» nell'app: senza quel passaggio "
        "non parte nulla."
    )


def get_pending_draft() -> dict[str, Any] | None:
    """Bozza in attesa di conferma (None se non c'è)."""
    draft = get_setting(_DRAFT_KEY, {}) or {}
    return draft if isinstance(draft, dict) and draft.get("a") else None


def cancel_pending_draft() -> bool:
    if not get_pending_draft():
        return False
    set_setting(_DRAFT_KEY, {})
    return True


def send_pending_draft() -> tuple[bool, str]:
    """Invia la bozza in attesa. Chiamabile SOLO dall'endpoint con conferma.

    La bozza viene "reclamata" (rimossa) prima della chiamata a Google, così un
    secondo tap simultaneo non può inviare la stessa email due volte; se l'invio
    fallisce la bozza viene ripristinata e resta confermabile.
    """
    with _SEND_LOCK:
        draft = get_pending_draft()
        if not draft:
            return False, "Nessuna bozza in attesa di invio."
        if not google_status()["connesso"]:
            return False, _NOT_CONNECTED

        set_setting(_DRAFT_KEY, {})
        try:
            raw = _build_raw_message(draft)
            sent = api_post(
                f"{GMAIL_API}/users/me/messages/send",
                {"raw": raw},
            )
        except GoogleAuthError as exc:
            set_setting(_DRAFT_KEY, draft)
            return False, f"⚠️ {exc}"
        except (ValueError, KeyError) as exc:
            set_setting(_DRAFT_KEY, draft)
            log.warning("Invio email fallito: %s", exc)
            return False, f"Invio non riuscito: {exc}"
        except Exception:
            set_setting(_DRAFT_KEY, draft)
            raise

    log.info("Email inviata a %s", draft.get("a"))
    message_id = str(sent.get("id") or "")
    return True, (
        f"✅ Email inviata a {draft.get('a')}."
        + (f" (id {message_id})" if message_id else "")
    )


def _build_raw_message(draft: dict[str, Any]) -> str:
    msg = EmailMessage()
    msg["To"] = str(draft["a"])
    msg["Subject"] = str(draft["oggetto"])
    msg.set_content(str(draft["corpo"]))

    allegato = draft.get("allegato") or None
    if isinstance(allegato, dict):
        message_id = str(allegato.get("message_id") or "")
        attachment_id = str(allegato.get("attachment_id") or "")
        if message_id and attachment_id:
            data = api_get(
                f"{GMAIL_API}/users/me/messages/{message_id}/attachments/{attachment_id}"
            )
            blob = base64.urlsafe_b64decode(str(data.get("data") or "") + "===")
            if len(blob) > _MAX_ATTACHMENT_BYTES:
                raise ValueError("allegato oltre 8 MB")
            msg.add_attachment(
                blob,
                maintype="application",
                subtype="octet-stream",
                filename=str(allegato.get("filename") or "allegato"),
            )

    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


# ------------------------------------------------------------------
#  Calendar: eventi, fusi, sovrapposizioni
# ------------------------------------------------------------------
def _event_bounds(event: dict[str, Any]) -> tuple[datetime, datetime] | None:
    start_raw = (event.get("start") or {}).get("dateTime")
    end_raw = (event.get("end") or {}).get("dateTime")
    if not start_raw or not end_raw:
        return None
    try:
        return datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw)
    except ValueError:
        return None


def _events_between(start: datetime, end: datetime) -> list[dict[str, Any]]:
    payload = api_get(
        f"{CALENDAR_API}/calendars/primary/events",
        {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
        },
    )
    return list(payload.get("items") or [])


def overlap_warning(start: datetime, end: datetime, ignore_id: str = "") -> str:
    try:
        events = _events_between(start, end)
    except GoogleAuthError:
        return ""
    conflitti: list[str] = []
    for event in events:
        if ignore_id and str(event.get("id")) == ignore_id:
            continue
        bounds = _event_bounds(event)
        if bounds is None:
            continue
        ev_start, ev_end = bounds
        if ev_start < end and start < ev_end:
            orario = ev_start.strftime("%H:%M")
            conflitti.append(f"{orario} {event.get('summary') or '(senza titolo)'}")
    if not conflitti:
        return ""
    return "\n⚠️ Si sovrappone a: " + "; ".join(conflitti[:3])


def _parse_local(data: str, ora: str, zone: ZoneInfo) -> datetime:
    return datetime.strptime(f"{data.strip()} {ora.strip()[:5]}", "%Y-%m-%d %H:%M").replace(tzinfo=zone)


def calendar_modifica_evento(
    event_id: str,
    titolo: str = "",
    data: str = "",
    ora: str = "",
    durata_minuti: int = 0,
    descrizione: str = "",
    fuso_orario: str = "",
) -> str:
    """Modifica un evento esistente (titolo, data, ora, durata, note, fuso).

    Args:
        event_id: id dell'evento (lo trovi nell'agenda o nel link dell'evento).
        titolo: nuovo titolo (vuoto = invariato).
        data: nuova data YYYY-MM-DD (vuota = invariata).
        ora: nuova ora HH:MM (vuota = invariata).
        durata_minuti: nuova durata in minuti (0 = invariata).
        descrizione: nuove note (vuoto = invariate).
        fuso_orario: fuso IANA (vuoto = quello dello scheduler).
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED
    if not event_id.strip():
        return "Serve l'id dell'evento da modificare."

    try:
        zone, zone_name = _tz(fuso_orario)
    except ValueError as exc:
        return str(exc)

    try:
        current = api_get(f"{CALENDAR_API}/calendars/primary/events/{event_id.strip()}")
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    bounds = _event_bounds(current)
    if bounds is None:
        return "L'evento è a giornata intera o ha orari non modificabili da qui."
    start, end = bounds
    durata = int((end - start).total_seconds() // 60)

    try:
        if data.strip() or ora.strip():
            new_start = _parse_local(
                data.strip() or start.astimezone(zone).strftime("%Y-%m-%d"),
                ora.strip() or start.astimezone(zone).strftime("%H:%M"),
                zone,
            )
        else:
            new_start = start.astimezone(zone)
    except ValueError:
        return "Data o ora non valide: usa YYYY-MM-DD e HH:MM."

    if int(durata_minuti or 0) > 0:
        durata = max(15, min(int(durata_minuti), 480))
    new_end = new_start + timedelta(minutes=durata)

    body: dict[str, Any] = {
        "start": {"dateTime": new_start.isoformat(), "timeZone": zone_name},
        "end": {"dateTime": new_end.isoformat(), "timeZone": zone_name},
    }
    if titolo.strip():
        body["summary"] = titolo.strip()[:200]
    if descrizione.strip():
        body["description"] = descrizione.strip()[:2000]

    try:
        updated = api_patch(
            f"{CALENDAR_API}/calendars/primary/events/{event_id.strip()}",
            body,
        )
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"

    summary = updated.get("summary") or body.get("summary") or "(senza titolo)"
    return (
        f"✅ Evento «{summary}» aggiornato: {new_start.strftime('%d/%m/%Y %H:%M')}–"
        f"{new_end.strftime('%H:%M')} ({zone_name})."
        + overlap_warning(new_start, new_end, ignore_id=event_id.strip())
    )


def calendar_elimina_evento(event_id: str) -> str:
    """Elimina un evento dal calendario Google collegato.

    Args:
        event_id: id dell'evento da eliminare.
    """
    if not google_status()["connesso"]:
        return _NOT_CONNECTED
    if not event_id.strip():
        return "Serve l'id dell'evento da eliminare."
    try:
        api_delete(f"{CALENDAR_API}/calendars/primary/events/{event_id.strip()}")
    except GoogleAuthError as exc:
        return f"⚠️ {exc}"
    return f"🗑️ Evento {event_id.strip()} eliminato dal calendario."


__all__ = [
    "calendar_elimina_evento",
    "calendar_modifica_evento",
    "cancel_pending_draft",
    "get_pending_draft",
    "gmail_allegati",
    "gmail_cerca_email",
    "gmail_prepara_email",
    "send_pending_draft",
]
