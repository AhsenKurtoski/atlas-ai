"""
Tools famiglia per ATLAS AI v3.0 (lista todo / spesa, push, barzellette, traduzioni).

I todo sono salvati in Supabase (`family_todos`) con fallback trasparente su
file locale. Le notifiche push vengono inviate ai dispositivi realmente
registrati (Expo Push / FCM), non simulate.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from app.core.context import current_profile
from app.core.database import (
    add_reminder as _db_add_reminder,
    add_todo as _db_add_todo,
    cancel_reminder as _db_cancel_reminder,
    complete_todo_by_index as _db_complete_todo,
    fetch_profiles,
    get_reminders as _db_get_reminders,
    get_todos as _db_get_todos,
)
from app.core.logging_config import get_logger
from app.core.settings import scheduler_timezone

log = get_logger(__name__)

# Nomi lingua → codice ISO per il servizio di traduzione
_LINGUE = {
    "italiano": "it",
    "inglese": "en",
    "albanese": "sq",
    "macedone": "mk",
    "spagnolo": "es",
    "francese": "fr",
    "tedesco": "de",
    "portoghese": "pt",
    "rumeno": "ro",
    "arabo": "ar",
    "cinese": "zh",
    "giapponese": "ja",
    "russo": "ru",
    "ucraino": "uk",
    "greco": "el",
    "turco": "tr",
}


# ---------------- TODO / Lista spesa ----------------
def add_family_todo(task: str, assegnato_a: str = "Tutti", creato_da: str = "io") -> str:
    """Aggiunge un task alla lista della spesa / cose da fare condivisa.

    Args:
        task: Testo del task (es. "Latte intero").
        assegnato_a: Membro a cui è assegnato (default "Tutti").
        creato_da: Slug del profilo che crea il task.
    """
    if not task or not task.strip():
        return "Cosa devo aggiungere? Es: 'Aggiungi in lista: Latte intero'"
    task_clean = task.strip()[:500]
    who = (assegnato_a or "Tutti").strip()[:100] or "Tutti"
    creator = current_profile.get() or creato_da or "io"
    try:
        _db_add_todo(task=task_clean, created_by_slug=creator, assegnato_a=who)
    except Exception as exc:
        log.exception("add_family_todo errore DB: %s", exc)
        return f"Non sono riuscito ad aggiungere il task: {exc}"
    extra = f" per {who}" if who and who != "Tutti" else ""
    return f"✅ '{task_clean}' aggiunto alla lista{extra}."


def get_family_todos(filtro: str = "") -> str:
    """Mostra la lista task condivisa.

    Args:
        filtro: "da fare" / "pending" per vedere solo i task non completati.
    """
    only_pending = (filtro or "").lower() in ("da_fare", "pending", "attivi", "da fare")
    try:
        todos = _db_get_todos(only_pending=only_pending)
    except Exception as exc:
        log.exception("get_family_todos: %s", exc)
        return "Non riesco a leggere la lista in questo momento."

    if not todos:
        return "🎉 La lista è vuota! Tutto fatto."

    righe: list[str] = []
    for index, todo in enumerate(todos, 1):
        task = todo.get("task_text") or todo.get("task") or "(senza descrizione)"
        done = bool(todo.get("is_completed", todo.get("done", False)))
        who = todo.get("assegnato_a") or "Tutti"
        stato = "✅" if done else "⬜"
        extra = f" ({who})" if who and who != "Tutti" else ""
        righe.append(f"{stato} {index}. {task}{extra}")

    titolo = "📋 Task da fare" if only_pending else "📋 Lista completa"
    return f"{titolo}:\n" + "\n".join(righe)


def completa_todo(numero: int) -> str:
    """Marca completato l'n-esimo task della lista (numerazione che vedi nell'elenco).

    Args:
        numero: Numero del task nell'elenco (parte da 1).
    """
    try:
        index = int(numero)
    except (TypeError, ValueError):
        return "Numero task non valido. Usa il numero visibile nella lista."
    try:
        ok = _db_complete_todo(index)
    except Exception as exc:
        log.exception("completa_todo: %s", exc)
        return f"Errore durante il completamento: {exc}"
    if not ok:
        return f"Non c'è nessun task numero {index} nella lista."
    return f"✅ Task {index} completato! Ottimo lavoro 💪"


# ---------------- PROMEMORIA ----------------
_SETTIMANE = {
    "lunedi": 0,
    "martedi": 1,
    "mercoledi": 2,
    "giovedi": 3,
    "venerdi": 4,
    "sabato": 5,
    "domenica": 6,
}


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(scheduler_timezone())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Rome")


def _normalizza_quando(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    text = text.replace("all'una", "alle 1").replace("all'una e mezza", "alle 1:30")
    text = re.sub(r"\b(\d{1,2})\s+e\s+mezza\b", r"\1:30", text)
    text = re.sub(r"\b(\d{1,2})\s+e\s+un\s+quarto\b", r"\1:15", text)
    text = re.sub(r"\b(\d{1,2})\s+e\s+tre\s+quarti\b", r"\1:45", text)
    text = text.replace("mezzogiorno", "12:00").replace("mezzanotte", "00:00")
    return text


def _ora_24(ora: int, periodo: str | None) -> int:
    if periodo == "mattina":
        return 0 if ora == 12 else ora
    if periodo in {"pomeriggio", "sera"}:
        return ora + 12 if 1 <= ora < 12 else ora
    # In italiano "alle 4" significa quasi sempre le 16; "alle 9" resta mattina.
    if 1 <= ora <= 7:
        return ora + 12
    return ora


def _formatta_locale(moment: datetime, now: datetime) -> str:
    giorni = (moment.date() - now.date()).days
    if giorni == 0:
        giorno = "oggi"
    elif giorni == 1:
        giorno = "domani"
    elif giorni == 2:
        giorno = "dopodomani"
    else:
        nomi = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
        giorno = f"{nomi[moment.weekday()]} {moment.strftime('%d/%m')}"
    return f"{giorno} alle {moment.strftime('%H:%M')}"


def _parse_quando(quando: str, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    """Converte un'espressione italiana in (UTC, ora locale, etichetta).

    Supporta ISO 8601, "tra 30 minuti", "domani alle 9", "stasera alle 20",
    "lunedì alle 10" e intervalli come "verso le 4-5" (16:00–17:00).
    """
    testo = _normalizza_quando(quando)
    if not testo:
        raise ValueError("Dimmi quando devo ricordartelo (es. 'domani alle 16').")

    tz = _tz()
    adesso = now.astimezone(tz) if now else datetime.now(tz)

    # ISO 8601 completo: il modello può passarlo già risolto.
    iso = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})(?:[t ](\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*(z|[+-]\d{2}:?\d{2})?$",
        testo,
    )
    if iso:
        anno, mese, giorno, ora, minuto, secondo, fuso = iso.groups()
        parsed = datetime(
            int(anno), int(mese), int(giorno), int(ora or 9), int(minuto or 0), int(secondo or 0),
            tzinfo=tz,
        )
        if fuso:
            if fuso == "z":
                parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
            else:
                segno = 1 if fuso[0] == "+" else -1
                ore_fuso, minuti_fuso = fuso[1:].replace(":", "")[:2], fuso[1:].replace(":", "")[2:]
                parsed = parsed.replace(
                    tzinfo=ZoneInfo("UTC"),
                ) - timedelta(hours=segno * int(ore_fuso), minutes=segno * int(minuti_fuso or 0))
        local = parsed.astimezone(tz)
        if local <= adesso:
            raise ValueError("L'orario indicato è già passato. Scegli un orario futuro.")
        return local.astimezone(ZoneInfo("UTC")), local, _formatta_locale(local, adesso)

    # Espressioni relative.
    rel = re.search(r"\b(?:tra|fra)\s+(\d+)\s*(minut\w*|or[ae]|giorn\w*)", testo)
    if rel or "tra mezz'ora" in testo or "fra mezz'ora" in testo:
        if rel:
            quantita = int(rel.group(1))
            unita = rel.group(2)
            delta = timedelta(minutes=quantita) if unita.startswith("minut") else (
                timedelta(hours=quantita) if unita.startswith("or") else timedelta(days=quantita)
            )
        else:
            delta = timedelta(minutes=30)
        local = adesso + delta
        return local.astimezone(ZoneInfo("UTC")), local.astimezone(tz), _formatta_locale(local.astimezone(tz), adesso)

    # Giorno esplicito.
    day_offset: int | None = None
    weekday: int | None = None
    if "dopodomani" in testo:
        day_offset = 2
    elif "domani" in testo:
        day_offset = 1
    elif "oggi" in testo or "stasera" in testo or "stamattina" in testo:
        day_offset = 0

    testo_senza_accenti = (
        testo.replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i")
        .replace("ò", "o").replace("ù", "u")
    )
    for nome, indice in _SETTIMANE.items():
        if re.search(rf"\b{nome}\b", testo_senza_accenti):
            weekday = indice
            day_offset = None
            break

    # Fascia oraria.
    periodo: str | None = None
    if any(word in testo for word in ("mattina", "stamattina", "mattino")):
        periodo = "mattina"
    elif "pomeriggio" in testo:
        periodo = "pomeriggio"
    elif "sera" in testo or "stasera" in testo:
        periodo = "sera"

    # Intervallo tipo "verso le 4-5": la finestra è 16:00–17:00.
    intervallo = re.search(
        r"(?:verso\s+le|tra\s+le|alle|per\s+le|ore)\s*(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?",
        testo,
    )
    if intervallo:
        ora_inizio = _ora_24(int(intervallo.group(1)), periodo)
        minuto_inizio = int(intervallo.group(2) or 0)
        ora_fine = _ora_24(int(intervallo.group(3)), periodo)
        minuto_fine = int(intervallo.group(4) or 0)
        inizio = adesso.replace(hour=ora_inizio, minute=minuto_inizio, second=0, microsecond=0)
        fine = adesso.replace(hour=ora_fine, minute=minuto_fine, second=0, microsecond=0)
        if day_offset is not None:
            inizio += timedelta(days=day_offset)
            fine += timedelta(days=day_offset)
        if weekday is not None:
            giorni = (weekday - adesso.weekday()) % 7
            inizio += timedelta(days=giorni)
            fine += timedelta(days=giorni)
            if inizio <= adesso:
                inizio += timedelta(days=7)
                fine += timedelta(days=7)
        if day_offset is None and weekday is None:
            if adesso < inizio:
                scelto = inizio
            elif adesso <= fine:
                # Siamo già nella finestra: dai un preavviso utile, non una
                # notifica alla fine dell'intervallo (es. 16:15 → 16:30).
                candidato = adesso + timedelta(minutes=15)
                minuti_arrotondati = ((candidato.minute + 4) // 5) * 5
                if minuti_arrotondati >= 60:
                    candidato = candidato.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                else:
                    candidato = candidato.replace(minute=minuti_arrotondati, second=0, microsecond=0)
                scelto = min(fine, max(inizio, candidato))
            else:
                scelto = inizio + timedelta(days=1)
        else:
            scelto = inizio
            if scelto <= adesso and day_offset == 0:
                raise ValueError("Quella fascia di oggi è già passata: dimmi un altro orario.")
        return scelto.astimezone(ZoneInfo("UTC")), scelto, _formatta_locale(scelto, adesso)

    # Orario singolo: "alle 16", "verso le 4", "16:30".
    orario = re.search(
        r"(?:alle|verso\s+le|per\s+le|ore|dalle)\s*(\d{1,2})(?::(\d{2}))?",
        testo,
    ) or re.search(r"\b(\d{1,2}):(\d{2})\b", testo)
    if orario:
        ora = _ora_24(int(orario.group(1)), periodo)
        minuto = int(orario.group(2) or 0)
    elif "mezzogiorno" in testo:
        ora, minuto = 12, 0
    elif "mezzanotte" in testo:
        ora, minuto = 0, 0
    elif periodo:
        ora, minuto = (9, 0) if periodo == "mattina" else ((16, 0) if periodo == "pomeriggio" else (20, 0))
    else:
        raise ValueError("Non ho capito l'orario. Dimmi ad esempio 'oggi alle 17' o 'domani alle 9'.")

    if not (0 <= ora <= 23 and 0 <= minuto <= 59):
        raise ValueError("Orario non valido.")

    target = adesso.replace(hour=ora, minute=minuto, second=0, microsecond=0)
    if weekday is not None:
        giorni = (weekday - adesso.weekday()) % 7
        target += timedelta(days=giorni)
        if target <= adesso:
            target += timedelta(days=7)
    elif day_offset is not None:
        target += timedelta(days=day_offset)
        if target <= adesso and day_offset == 0:
            raise ValueError("Quell'orario di oggi è già passato: dimmi un altro orario.")
    elif target <= adesso:
        # Un orario appena passato (entro 10 minuti) resta utile: avviso subito.
        if adesso - target <= timedelta(minutes=10):
            target = adesso + timedelta(minutes=1)
        else:
            target += timedelta(days=1)

    return target.astimezone(ZoneInfo("UTC")), target, _formatta_locale(target, adesso)


def _lista_pendente() -> list[str]:
    try:
        todos = _db_get_todos(only_pending=True)
    except Exception:
        return []
    return [str(todo.get("task_text") or todo.get("task") or "").strip() for todo in todos if (todo.get("task_text") or todo.get("task"))]


def crea_promemoria(quando: str, messaggio: str, includi_lista: bool = False) -> str:
    """Crea un promemoria reale che verrà notificato sul dispositivo.

    Usa questo tool ogni volta che l'utente dice di voler essere avvisato a
    un'ora precisa o in un intervallo (es. "verso le 4-5 devo andare da Lidl").
    Se la richiesta riguarda la spesa, includi la lista condivisa nella notifica.

    Args:
        quando: Quando avvisare, in linguaggio naturale o ISO 8601
            (es. "oggi alle 17", "domani alle 9", "tra 30 minuti").
        messaggio: Cosa ricordare (es. "Andare a fare la spesa da Lidl").
        includi_lista: True per allegare le cose ancora da comprare. Per i
            promemoria non legati alla spesa lascialo False (default).
    """
    testo = (messaggio or "").strip()
    if not testo:
        return "Cosa devo ricordarti?"
    testo = testo[:500]
    basso = testo.lower()
    vuole_lista = bool(includi_lista) or any(
        parola in basso for parola in ("spesa", "supermercato", "lidl", "carrefour", "esselunga", "lista")
    )
    if "senza lista" in basso:
        vuole_lista = False

    try:
        remind_utc, remind_local, etichetta = _parse_quando(quando)
    except ValueError as exc:
        return f"⚠️ {exc}"

    slug = current_profile.get() or "io"
    try:
        creato = _db_add_reminder(
            profile_slug=slug,
            message=testo,
            remind_at=remind_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            include_todos=vuole_lista,
            source="chat",
        )
    except Exception as exc:
        log.exception("crea_promemoria: %s", exc)
        return f"⚠️ Non sono riuscito a salvare il promemoria: {exc}"
    if not creato:
        return "⚠️ Il promemoria non è stato salvato. Riprova tra poco."

    righe = [f"⏰ Promemoria impostato per **{etichetta}**.", f"🔔 «{testo}»"]
    if vuole_lista:
        lista = _lista_pendente()
        if lista:
            anteprima = ", ".join(lista[:12])
            extra = "…" if len(lista) > 12 else ""
            unita = "cosa" if len(lista) == 1 else "cose"
            righe.append(f"🛒 Allego la lista attuale ({len(lista)} {unita}): {anteprima}{extra}")
        else:
            righe.append("🛒 La lista è vuota: aggiungi le cose che mancano e le ritroverai nel promemoria.")
    righe.append("📱 Tieni attive le notifiche di ATLAS sul telefono.")
    return "\n".join(righe)


def elenca_promemoria() -> str:
    """Elenca i prossimi promemoria reali del profilo corrente."""
    slug = current_profile.get() or "io"
    try:
        rows = _db_get_reminders(profile_slug=slug, only_pending=True)
    except Exception as exc:
        log.exception("elenca_promemoria: %s", exc)
        return "⚠️ Non riesco a leggere i promemoria in questo momento."
    if not rows:
        return "📭 Non hai promemoria attivi. Dimmi ad esempio: 'Ricordami domani alle 9 di chiamare il medico'."
    tz = _tz()
    adesso = datetime.now(tz)
    righe = []
    for index, row in enumerate(rows[:15], 1):
        try:
            local = datetime.fromisoformat(str(row.get("remind_at") or "").replace("Z", "+00:00")).astimezone(tz)
            quando = _formatta_locale(local, adesso)
        except (TypeError, ValueError):
            quando = str(row.get("remind_at") or "orario non disponibile")
        messaggio = str(row.get("message") or "Promemoria")
        righe.append(f"{index}. {quando} — {messaggio}")
    return "⏰ Promemoria attivi:\n" + "\n".join(righe)


def annulla_promemoria(riferimento: str) -> str:
    """Annulla un promemoria per numero (1-based), ID o parte del testo."""
    slug = current_profile.get() or "io"
    try:
        rows = _db_get_reminders(profile_slug=slug, only_pending=True)
    except Exception as exc:
        return f"⚠️ Errore nella lettura dei promemoria: {exc}"
    if not rows:
        return "📭 Non ci sono promemoria da annullare."
    target = (riferimento or "").strip().lower()
    scelto: dict | None = None
    if target.isdigit() and 1 <= int(target) <= len(rows):
        scelto = rows[int(target) - 1]
    else:
        for row in rows:
            if target and (target in str(row.get("id") or "").lower() or target in str(row.get("message") or "").lower()):
                scelto = row
                break
    if not scelto:
        return f"Non trovo un promemoria che corrisponda a «{riferimento}». Usa 'elenca i promemoria' per vedere i numeri."
    try:
        ok = _db_cancel_reminder(str(scelto.get("id")), slug)
    except Exception as exc:
        return f"⚠️ Non sono riuscito ad annullare il promemoria: {exc}"
    if not ok:
        return "⚠️ Il promemoria non è stato annullato. Riprova."
    return f"🗑️ Promemoria «{scelto.get('message')}» annullato."


# ---------------- Push notifiche reali ----------------
def _resolve_profile(membro: str) -> tuple[str, str] | None:
    """Trova (slug, nome) del membro per slug o nome."""
    target = (membro or "").strip().lower()
    if not target:
        return None
    for slug, profilo in fetch_profiles().items():
        if target == slug.lower() or target == str(profilo.get("nome", "")).lower():
            return slug, str(profilo.get("nome", slug))
    return None


def invia_push_famigliare(membro: str, messaggio: str) -> str:
    """Invia una notifica push reale a un membro della famiglia.

    Args:
        membro: Nome o slug del membro (es. "mamma").
        messaggio: Testo della notifica.
    """
    if not membro or not messaggio:
        return "Dimmi a chi e cosa devo inviare. Es: 'Invia a mamma: Ricorda la medicina'"

    resolved = _resolve_profile(membro)
    if not resolved:
        return f"Non conosco nessun membro chiamato '{membro}'."

    slug, nome = resolved
    try:
        from app.notifiche import invia_a_profilo

        inviati = invia_a_profilo(
            slug,
            titolo=f"Messaggio per {nome}",
            messaggio=messaggio[:500],
            dati={"tipo": "famiglia", "da": "ATLAS"},
        )
    except Exception as exc:
        log.exception("Push fallita (membro=%s): %s", slug, exc)
        return f"Non sono riuscito a inviare la notifica a {nome}: {exc}"

    if inviati <= 0:
        return (
            f"⚠️ Nessun dispositivo registrato per {nome}. "
            "Apri l'app sul suo telefono e attiva le notifiche in Impostazioni."
        )
    return f"📬 Notifica inviata a {nome} ({inviati} dispositivo/i)."


# ---------------- Intrattenimento ----------------
_JOKE_FALLBACK = [
    "Perché il computer è andato dal dottore? Perché aveva un virus!",
    "Cosa dice un caffè all'altro? 'Ti amo talmente tanto che mi sciolgo per te!'",
    "Perché il pomodoro non attraversa la strada? Perché si trasforma in ketchup!",
    "Qual è il colmo per un elettricista? Prendere la scossa per una brutta copia!",
    "Cosa dice un giardiniere all'altro? 'Sei un fiore!'",
]


def get_random_joke() -> str:
    """Racconta una barzelletta (JokeAPI in italiano con fallback locale)."""
    try:
        response = requests.get(
            "https://v2.jokeapi.dev/joke/Any",
            params={"type": "single", "lang": "it"},
            timeout=6,
        )
        response.raise_for_status()
        joke = response.json().get("joke")
        if joke:
            return str(joke)
    except requests.RequestException as exc:
        log.debug("get_random_joke API fallita: %s", exc)
    except (ValueError, TypeError) as exc:
        log.exception("get_random_joke: %s", exc)
    return random.choice(_JOKE_FALLBACK)


def get_advice() -> str:
    """Un breve consiglio o frase motivazionale."""
    try:
        response = requests.get("https://api.adviceslip.com/advice", timeout=6)
        response.raise_for_status()
        advice = (response.json().get("slip") or {}).get("advice")
        if advice:
            return f"💡 Consiglio: {advice}"
    except requests.RequestException as exc:
        log.debug("get_advice API fallita: %s", exc)
    except (ValueError, TypeError, KeyError) as exc:
        log.exception("get_advice: %s", exc)
    return "💡 Ricorda: la costanza quotidiana vince sulla quantità una tantum."


# ---------------- Traduzioni (MyMemory, gratuito) ----------------
def _lang_code(lingua: str) -> str:
    value = (lingua or "").strip().lower()
    if value in _LINGUE:
        return _LINGUE[value]
    if len(value) == 2:
        return value
    return "en"


def traduci_testo(testo: str, lingua: str, lingua_origine: str = "it") -> str:
    """Traduce un testo usando MyMemory (servizio gratuito, nessuna chiave).

    Args:
        testo: Testo da tradurre.
        lingua: Lingua di destinazione (es. "albanese" oppure "sq").
        lingua_origine: Lingua di partenza (default "it").
    """
    if not testo or not lingua:
        return "Dimmi testo e lingua di destinazione. Es: 'Traduci Ciao mamma in Albanese'."

    source = _lang_code(lingua_origine)
    target = _lang_code(lingua)
    if source == target:
        return f"🌍 Il testo è già in {lingua}: {testo}"

    try:
        response = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": testo[:500], "langpair": f"{source}|{target}"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        translated = (payload.get("responseData") or {}).get("translatedText")
        if isinstance(translated, str) and translated.strip() and "MYMEMORY WARNING" not in translated.upper():
            return f"🌍 Traduzione ({source.upper()} → {target.upper()}): {translated.strip()}"
        log.warning("MyMemory risposta non valida: %s", str(payload)[:200])
    except requests.RequestException as exc:
        log.warning("traduci_testo rete: %s", exc)
    except (ValueError, TypeError) as exc:
        log.exception("traduci_testo: %s", exc)

    return (
        "⚠️ Servizio di traduzione temporaneamente non raggiungibile. "
        "Riprova tra poco: nessuna traduzione inventata."
    )


_ = (Any, quote)  # import mantenuti per compatibilità con estensioni future
