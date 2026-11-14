"""
Tools famiglia per ATLAS AI v3.0 (lista todo / spesa, push, barzellette, traduzioni).

I todo sono salvati in Supabase (`family_todos`) con fallback trasparente su
file locale. Le notifiche push vengono inviate ai dispositivi realmente
registrati (Expo Push / FCM), non simulate.
"""
from __future__ import annotations

import random
from typing import Any
from urllib.parse import quote

import requests

from app.core.database import (
    add_todo as _db_add_todo,
    complete_todo_by_index as _db_complete_todo,
    fetch_profiles,
    get_todos as _db_get_todos,
)
from app.core.logging_config import get_logger

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
    try:
        _db_add_todo(task=task_clean, created_by_slug=creato_da, assegnato_a=who)
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
