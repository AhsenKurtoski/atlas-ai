"""
Tools famiglia per ATLAS AI v3.0 (lista todo / spesa, push, barzellette, traduzioni).

I TODO vengono salvati in Supabase (family_todos) tramite il modulo database,
con fallback trasparente su file locale. Non usiamo più todos.json diretto.
"""
from __future__ import annotations

import random
from urllib.parse import quote

import requests

from app.core.database import (
    add_todo as _db_add_todo,
    complete_todo_by_index as _db_complete_todo,
    get_todos as _db_get_todos,
)
from app.core.logging_config import get_logger

log = get_logger(__name__)


# ---------------- TODO / Lista spesa ----------------
def add_family_todo(task: str, assegnato_a: str = "Tutti") -> str:
    """Aggiunge un task alla lista della spesa / cose da fare condivisa."""
    if not task or not task.strip():
        return "Cosa devo aggiungere? Es: 'Aggiungi in lista: Latte intero'"
    task_clean = task.strip()[:500]
    who = (assegnato_a or "Tutti").strip()[:100] or "Tutti"
    try:
        _db_add_todo(task=task_clean, created_by_slug="io", assegnato_a=who)
    except Exception as exc:
        log.exception("add_family_todo errore DB: %s", exc)
        return f"Non sono riuscito ad aggiungere il task: {exc}"
    extra = f" per {who}" if who and who != "Tutti" else ""
    return f"✅ '{task_clean}' aggiunto alla lista{extra}."


def get_family_todos(filtro: str = "") -> str:
    """Mostra la lista task. Usa filtro='da fare' per i soli non completati."""
    only_pending = (filtro or "").lower() in ("da_fare", "pending", "attivi", "da fare")
    try:
        todos = _db_get_todos(only_pending=only_pending)
    except Exception as exc:
        log.exception("get_family_todos: %s", exc)
        return "Non riesco a leggere la lista in questo momento."

    if not todos:
        return "🎉 La lista è vuota! Tutto fatto."

    righe: list[str] = []
    for i, t in enumerate(todos, 1):
        task = t.get("task_text") or t.get("task") or "(senza descrizione)"
        done = bool(t.get("is_completed", t.get("done", False)))
        who = t.get("assegnato_a") or "Tutti"
        status = "✅" if done else "⬜"
        who_extra = f" ({who})" if who and who != "Tutti" else ""
        righe.append(f"{status} {i}. {task}{who_extra}")

    titolo = "📋 Lista completa" if not only_pending else "📋 Task da fare"
    return f"{titolo}:\n" + "\n".join(righe)


def completa_todo(numero: int) -> str:
    """Marca completato l'n-esimo task della lista (1-based)."""
    try:
        idx = int(numero)
    except (TypeError, ValueError):
        return "Numero task non valido. Usa il numero visibile nella lista."
    try:
        ok = _db_complete_todo(idx)
    except Exception as exc:
        log.exception("completa_todo: %s", exc)
        return f"Errore durante la rimozione: {exc}"
    if not ok:
        return f"Non c'è nessun task numero {idx} nella lista."
    return f"✅ Task {idx} completato! Ottimo lavoro 💪"


# ---------------- Push notifiche (mock se Firebase non configurato) ----------------
def invia_push_famigliare(membro: str, messaggio: str) -> str:
    """Invia una notifica push a un membro. Richiede token dispositivo + Firebase."""
    if not membro or not messaggio:
        return "Dimmi a chi e cosa devo inviare. Es: 'Invia a mamma: Ricorda la medicina'"
    try:
        from app.notifiche import invia_push

        # TODO: recuperare token del membro da DB. Per ora mandiamo a me stesso.
        token = os.getenv("PUSH_TOKEN_DEMO", "")
        if token:
            ok = invia_push(token, titolo=f"Messaggio da {membro}", messaggio=messaggio, dati={"da": membro})
            if ok:
                return f"📬 Notifica inviata a {membro}."
    except Exception as exc:
        log.warning("Push fallita (membro=%s): %s", membro, exc)
    return f"📬 Notifica accodata per {membro}: {messaggio} (servizio push non ancora configurato)."


# ---------------- Intrattenimento ----------------
_JOKE_FALLBACK = [
    "Perché il computer è andato dal dottore? Perché aveva un virus!",
    "Cosa dice un caffè all'altro? 'Ti amo talmente tanto che mi sciolgo per te!'",
    "Perché il pomodoro non attraversa la strada? Perché si trasforma in ketchup!",
    "Qual è il colmo per un elettricista? Prendere la scossa per una brutta copia!",
    "Cosa dice un giardiniere all'altro? 'Sei un fiore!'",
]


def get_random_joke() -> str:
    """Una barzelletta (API italiana con fallback locale)."""
    try:
        resp = requests.get(
            "https://v2.jokeapi.dev/joke/Any?type=single&lang=it",
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        joke = data.get("joke")
        if joke:
            return str(joke)
    except requests.RequestException as exc:
        log.debug("get_random_joke API fallita: %s", exc)
    except Exception as exc:
        log.exception("get_random_joke: %s", exc)
    return random.choice(_JOKE_FALLBACK)


def get_advice() -> str:
    """Un breve consiglio o frase motivazionale."""
    try:
        resp = requests.get("https://api.adviceslip.com/advice", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        advice = data.get("slip", {}).get("advice")
        if advice:
            return f"💡 Consiglio: {advice}"
    except requests.RequestException as exc:
        log.debug("get_advice API fallita: %s", exc)
    except Exception as exc:
        log.exception("get_advice: %s", exc)
    return "💡 Ricorda: la costanza quotidiana vince sulla quantità una tantum."


# ---------------- Traduzioni ----------------
def traduci_testo(testo: str, lingua: str) -> str:
    """Richiede a Gemini di tradurre (tramite il prompt task-specifico)."""
    if not testo or not lingua:
        return "Dimmi testo e lingua di destinazione. Es: 'Traduci Ciao mamma in Albanese'."
    return (
        f"[TRADUZIONE] Traduci il testo seguente in {lingua}. "
        f"Mostra PRIMA la traduzione e POI, se il livello d'italiano dell'utente è basso, "
        f"una nota breve che spieghi parole o costruzioni difficili.\n\n"
        f"Testo da tradurre:\n{testo}"
    )


import os  # noqa: E402 - usato solo in caso reale di push
