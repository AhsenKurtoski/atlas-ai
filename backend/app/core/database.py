"""
Gestione database Supabase per ATLAS AI v3.0.

Schema: le tabelle usano `profile_slug` come chiave esterna verso `profiles(slug)`.
Ogni funzione ha un fallback locale (@resilient) su file JSON in `backend/_local_db/`,
così l'app funziona (in modo reale, non simulato) anche senza Supabase configurato.
"""
from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Iterable, Optional, TypeVar

from supabase import Client, create_client

from app.core.logging_config import get_logger
from app.core.settings import LOCAL_DB_DIR, is_production, supabase_config

log = get_logger(__name__)

url, key = supabase_config()
_MOCK_MODE: bool = not bool(url and key and not url.startswith("http://mock-"))


# ====================================================================
#  Fallback file-based (JSON locale)
# ====================================================================
def _fallback_path(name: str) -> str:
    os.makedirs(LOCAL_DB_DIR, exist_ok=True)
    return str(LOCAL_DB_DIR / f"{name}.json")


def _fallback_read(name: str, default: Any) -> Any:
    path = _fallback_path(name)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except (OSError, json.JSONDecodeError):
        log.warning("File locale corrotto %s, uso default", path)
    return copy.deepcopy(default)


def _fallback_write(name: str, data: Any) -> None:
    """Scrittura atomica: mai file JSON troncati a metà."""
    path = _fallback_path(name)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError as exc:
        log.error("Impossibile scrivere %s: %s", path, exc)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


F = TypeVar("F", bound=Callable)


def resilient(fallback_return: Any = None) -> Callable[[F], F]:
    """Decoratore: errori Supabase → fallback locale trasparente."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _MOCK_MODE:
                fallback = globals().get(f"_fb_{fn.__name__}")
                if callable(fallback):
                    return fallback(*args, **kwargs)
                return fallback_return
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - errori di rete
                log.exception("Errore Supabase in %s: %s. Uso fallback locale.", fn.__name__, exc)
                fallback = globals().get(f"_fb_{fn.__name__}")
                if callable(fallback):
                    try:
                        return fallback(*args, **kwargs)
                    except Exception as fallback_exc:
                        log.error("Anche il fallback di %s è fallito: %s", fn.__name__, fallback_exc)
                return fallback_return

        return wrapper  # type: ignore[return-value]

    return decorator


def is_mock_mode() -> bool:
    return _MOCK_MODE


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------- Client (lazy) ----------------
_client: Optional[Client] = None


def get_client() -> Optional[Client]:
    global _client
    if _MOCK_MODE:
        return None
    if _client is None:
        try:
            _client = create_client(url, key)
        except Exception as exc:  # pragma: no cover
            log.error("Impossibile creare client Supabase: %s", exc)
    return _client


# ====================================================================
#  MESSAGES (cronologia chat / memoria RAG)
# ====================================================================
@resilient(fallback_return=None)
def save_message(profile_slug: str, role: str, content: str) -> Any:
    """Salva un messaggio della chat (memoria conversazionale)."""
    if role not in ("user", "ai"):
        raise ValueError(f"Ruolo non valido: {role}")
    client = get_client()
    if client is None:
        return None
    response = (
        client.table("messages")
        .insert({"profile_slug": profile_slug, "role": role, "content": content})
        .execute()
    )
    log.debug("Messaggio salvato per %s (%s)", profile_slug, role)
    return response


def _fb_save_message(profile_slug: str, role: str, content: str) -> None:
    rows = _fallback_read("messages", [])
    rows.append(
        {
            "profile_slug": profile_slug,
            "role": role,
            "content": content,
            "created_at": _now_iso(),
        }
    )
    # Manteniamo solo gli ultimi 500 messaggi per non far crescere il file.
    _fallback_write("messages", rows[-500:])


@resilient(fallback_return=[])
def get_user_memory(profile_slug: str, limit: int = 20) -> list[dict]:
    """Ritorna gli ultimi N messaggi del profilo in ordine cronologico."""
    client = get_client()
    if client is None:
        return []
    response = (
        client.table("messages")
        .select("*")
        .eq("profile_slug", profile_slug)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(response.data)) if response.data else []


def _fb_get_user_memory(profile_slug: str, limit: int = 20) -> list[dict]:
    rows = _fallback_read("messages", [])
    filtered = [row for row in rows if row.get("profile_slug") == profile_slug]
    return filtered[-limit:]


# ====================================================================
#  FAMILY TODOS (lista spesa / cose da fare)
# ====================================================================
@resilient(fallback_return="ok")
def add_todo(task: str, created_by_slug: str, assegnato_a: str = "Tutti") -> str:
    client = get_client()
    if client is None:
        return ""
    data = {
        "task_text": task,
        "created_by_slug": created_by_slug,
        "assegnato_a": assegnato_a or "Tutti",
        "is_completed": False,
    }
    client.table("family_todos").insert(data).execute()
    log.info("Todo aggiunto: %s (da %s)", task[:40], created_by_slug)
    return "ok"


def _fb_add_todo(task: str, created_by_slug: str, assegnato_a: str = "Tutti") -> str:
    rows = _fallback_read("family_todos", [])
    rows.append(
        {
            "id": f"local_{len(rows) + 1}_{int(datetime.now().timestamp())}",
            "task_text": task,
            "created_by_slug": created_by_slug,
            "assegnato_a": assegnato_a or "Tutti",
            "is_completed": False,
            "created_at": _now_iso(),
        }
    )
    _fallback_write("family_todos", rows)
    return "ok"


@resilient(fallback_return=[])
def get_todos(only_pending: bool = False) -> list[dict]:
    """Lista todo in ordine cronologico (indice 1 = primo task)."""
    client = get_client()
    if client is None:
        return []
    query = client.table("family_todos").select("*").order("created_at", desc=False)
    if only_pending:
        query = query.eq("is_completed", False)
    response = query.execute()
    return list(response.data or [])


def _fb_get_todos(only_pending: bool = False) -> list[dict]:
    rows = _fallback_read("family_todos", [])
    if only_pending:
        rows = [row for row in rows if not row.get("is_completed")]
    return rows


@resilient(fallback_return=False)
def complete_todo_by_index(index: int, mark: bool = True) -> bool:
    """Segna completato l'n-esimo task della lista (1-based, come mostrato in UI)."""
    todos = get_todos()
    if not (1 <= int(index) <= len(todos)):
        return False
    item = todos[int(index) - 1]
    row_id = item.get("id")
    client = get_client()
    if client and row_id:
        client.table("family_todos").update(
            {"is_completed": mark, "completed_at": _now_iso() if mark else None}
        ).eq("id", row_id).execute()
    else:
        return _fb_complete_todo_by_index(index, mark)
    return True


def _fb_complete_todo_by_index(index: int, mark: bool = True) -> bool:
    rows = _fallback_read("family_todos", [])
    if not (1 <= int(index) <= len(rows)):
        return False
    rows[int(index) - 1]["is_completed"] = mark
    rows[int(index) - 1]["completed_at"] = _now_iso() if mark else None
    _fallback_write("family_todos", rows)
    return True


@resilient(fallback_return=False)
def delete_todo_by_index(index: int) -> bool:
    """Elimina definitivamente l'n-esimo task (1-based, stesso ordine della UI)."""
    todos = get_todos()
    if not (1 <= int(index) <= len(todos)):
        return False
    item = todos[int(index) - 1]
    row_id = item.get("id")
    client = get_client()
    if client and row_id:
        client.table("family_todos").delete().eq("id", row_id).execute()
        return True
    return _fb_delete_todo_by_index(index)


def _fb_delete_todo_by_index(index: int) -> bool:
    rows = _fallback_read("family_todos", [])
    if not (1 <= int(index) <= len(rows)):
        return False
    rows.pop(int(index) - 1)
    _fallback_write("family_todos", rows)
    return True


# ====================================================================
#  PROMEMORIA PERSONALI (APScheduler + notifiche locali/push)
# ====================================================================
def _reminder_row(profile_slug: str, message: str, remind_at: str, include_todos: bool, source: str) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "profile_slug": profile_slug,
        "message": message,
        "remind_at": remind_at,
        "include_todos": bool(include_todos),
        "status": "pending",
        "source": source or "chat",
        "local_scheduled_at": None,
        "sent_at": None,
        "created_at": _now_iso(),
    }


@resilient(fallback_return=None)
def add_reminder(
    profile_slug: str,
    message: str,
    remind_at: str,
    include_todos: bool = True,
    source: str = "chat",
) -> dict | None:
    """Salva un promemoria. `remind_at` è un ISO 8601 UTC fornito dal parser."""
    client = get_client()
    if client is None:
        return _fb_add_reminder(profile_slug, message, remind_at, include_todos, source)
    response = (
        client.table("family_reminders")
        .insert(
            {
                "profile_slug": profile_slug,
                "message": message,
                "remind_at": remind_at,
                "include_todos": bool(include_todos),
                "status": "pending",
                "source": source or "chat",
            }
        )
        .execute()
    )
    rows = list(response.data or [])
    return rows[0] if rows else None


def _fb_add_reminder(
    profile_slug: str,
    message: str,
    remind_at: str,
    include_todos: bool = True,
    source: str = "chat",
) -> dict:
    rows = _fallback_read("family_reminders", [])
    row = _reminder_row(profile_slug, message, remind_at, include_todos, source)
    rows.append(row)
    _fallback_write("family_reminders", rows)
    return row


@resilient(fallback_return=[])
def get_reminders(profile_slug: Optional[str] = None, only_pending: bool = True) -> list[dict]:
    """Promemoria in ordine di scadenza, opzionalmente solo quelli attivi."""
    client = get_client()
    if client is None:
        return []
    query = client.table("family_reminders").select("*")
    if profile_slug:
        query = query.eq("profile_slug", profile_slug)
    if only_pending:
        query = query.eq("status", "pending")
    response = query.order("remind_at", desc=False).execute()
    return sorted(list(response.data or []), key=lambda row: str(row.get("remind_at") or ""))


def _fb_get_reminders(profile_slug: Optional[str] = None, only_pending: bool = True) -> list[dict]:
    rows = _fallback_read("family_reminders", [])
    if profile_slug:
        rows = [row for row in rows if row.get("profile_slug") == profile_slug]
    if only_pending:
        rows = [row for row in rows if row.get("status") == "pending"]
    return sorted(rows, key=lambda row: str(row.get("remind_at") or ""))


@resilient(fallback_return=False)
def cancel_reminder(reminder_id: str, profile_slug: str) -> bool:
    """Annulla un promemoria solo se appartiene al profilo autenticato."""
    client = get_client()
    if client is None:
        return False
    response = (
        client.table("family_reminders")
        .update({"status": "cancelled"})
        .eq("id", reminder_id)
        .eq("profile_slug", profile_slug)
        .eq("status", "pending")
        .execute()
    )
    return bool(response.data)


def _fb_cancel_reminder(reminder_id: str, profile_slug: str) -> bool:
    rows = _fallback_read("family_reminders", [])
    changed = False
    for row in rows:
        if row.get("id") == reminder_id and row.get("profile_slug") == profile_slug:
            if row.get("status") == "pending":
                row["status"] = "cancelled"
                changed = True
            break
    if changed:
        _fallback_write("family_reminders", rows)
    return changed


@resilient(fallback_return=False)
def mark_reminder_local_scheduled(reminder_id: str, profile_slug: str) -> bool:
    """Conferma che l'app ha pianificato la notifica locale (evita il push duplicato)."""
    client = get_client()
    if client is None:
        return False
    response = (
        client.table("family_reminders")
        .update({"local_scheduled_at": _now_iso()})
        .eq("id", reminder_id)
        .eq("profile_slug", profile_slug)
        .eq("status", "pending")
        .execute()
    )
    return bool(response.data)


def _fb_mark_reminder_local_scheduled(reminder_id: str, profile_slug: str) -> bool:
    rows = _fallback_read("family_reminders", [])
    for row in rows:
        if row.get("id") == reminder_id and row.get("profile_slug") == profile_slug:
            row["local_scheduled_at"] = _now_iso()
            _fallback_write("family_reminders", rows)
            return True
    return False


@resilient(fallback_return=False)
def mark_reminder_sent(reminder_id: str) -> bool:
    client = get_client()
    if client is None:
        return False
    response = (
        client.table("family_reminders")
        .update({"status": "sent", "sent_at": _now_iso()})
        .eq("id", reminder_id)
        .eq("status", "pending")
        .execute()
    )
    return bool(response.data)


def _fb_mark_reminder_sent(reminder_id: str) -> bool:
    rows = _fallback_read("family_reminders", [])
    for row in rows:
        if row.get("id") == reminder_id and row.get("status") == "pending":
            row["status"] = "sent"
            row["sent_at"] = _now_iso()
            _fallback_write("family_reminders", rows)
            return True
    return False


@resilient(fallback_return=[])
def get_due_reminders(now_iso: str, limit: int = 50) -> list[dict]:
    client = get_client()
    if client is None:
        return []
    response = (
        client.table("family_reminders")
        .select("*")
        .eq("status", "pending")
        .lte("remind_at", now_iso)
        .order("remind_at", desc=False)
        .limit(max(1, int(limit)))
        .execute()
    )
    return list(response.data or [])


def _fb_get_due_reminders(now_iso: str, limit: int = 50) -> list[dict]:
    rows = [
        row
        for row in _fallback_read("family_reminders", [])
        if row.get("status") == "pending" and str(row.get("remind_at") or "") <= now_iso
    ]
    return sorted(rows, key=lambda row: str(row.get("remind_at") or ""))[: max(1, int(limit))]


# ====================================================================
#  BUDGET / SPESE
# ====================================================================
@resilient(fallback_return="ok")
def add_spesa(importo: float, categoria: str, descrizione: str, slug: str) -> str:
    client = get_client()
    if client is None:
        return ""
    data = {
        "amount": importo,
        "category": categoria,
        "description": descrizione or "",
        "created_by_slug": slug,
    }
    client.table("family_expenses").insert(data).execute()
    log.info("Spesa €%.2f registrata in %s da %s", importo, categoria, slug)
    return "ok"


def _fb_add_spesa(importo: float, categoria: str, descrizione: str, slug: str) -> str:
    rows = _fallback_read("family_expenses", [])
    rows.append(
        {
            "id": f"local_{len(rows) + 1}_{int(datetime.now().timestamp())}",
            "amount": importo,
            "category": categoria,
            "description": descrizione,
            "created_by_slug": slug,
            "created_at": _now_iso(),
        }
    )
    _fallback_write("family_expenses", rows)
    return "ok"


def _summarize_expenses(rows: Iterable[dict], only_month: bool = False) -> dict:
    """Calcola totale e dettaglio per categoria (usato da Supabase e fallback)."""
    today = date.today()
    filtered: list[dict] = []
    for row in rows:
        if only_month:
            created = str(row.get("created_at") or "")
            if created[:7] != today.strftime("%Y-%m"):
                continue
        filtered.append(row)

    totale = sum(float(row.get("amount", 0) or 0) for row in filtered)
    per_cat: dict[str, float] = {}
    for row in filtered:
        category = row.get("category") or "Altro"
        per_cat[category] = per_cat.get(category, 0.0) + float(row.get("amount", 0) or 0)
    dettaglio = sorted(per_cat.items(), key=lambda item: item[1], reverse=True)
    return {
        "totale": round(totale, 2),
        "dettaglio": [
            {
                "categoria": category,
                "importo": round(value, 2),
                "percentuale": round((value / totale) * 100, 1) if totale else 0.0,
            }
            for category, value in dettaglio
        ],
    }


def _expense_rows() -> list[dict]:
    """Tutte le spese (Supabase se disponibile, altrimenti file locale)."""
    client = get_client()
    if client is not None:
        try:
            response = client.table("family_expenses").select("*").execute()
            rows = list(response.data or [])
            if rows:
                return rows
        except Exception as exc:  # pragma: no cover - rete
            log.warning("Lettura spese da Supabase fallita: %s", exc)
    return _fallback_read("family_expenses", [])


@resilient(fallback_return={"totale": 0.0, "dettaglio": []})
def get_budget_summary(only_month: bool = False) -> dict:
    return _summarize_expenses(_expense_rows(), only_month=only_month)


def _fb_get_budget_summary(only_month: bool = False) -> dict:
    return _summarize_expenses(_fallback_read("family_expenses", []), only_month=only_month)


# ====================================================================
#  PROFILI
# ====================================================================
# PIN demo (hash bcrypt reali): io=0000 · mamma=1111 · papa=2222
# fratello1=3333 · fratello2=4444 — cambiarli in produzione (POST /profili).
DEFAULT_PROFILES: dict[str, dict] = {
    "io": {
        "slug": "io",
        "nome": "Tu (Admin)",
        "lingua_madre": "Italiano",
        "livello_italiano": "C1",
        "pin_hash": "$2b$12$3H35nZSLzP2KdIhJqjKsAu/dEHhIFS8PGhti0kpd6pdOSreO5rx7y",
    },
    "mamma": {
        "slug": "mamma",
        "nome": "Mamma",
        "lingua_madre": "Albanese",
        "livello_italiano": "B1",
        "pin_hash": "$2b$12$W0ULwtx0rEHNM0mUsZHrUuEWjpcqSlnOQIKSdfZdBPgprSNst0D4G",
    },
    "papa": {
        "slug": "papa",
        "nome": "Papà",
        "lingua_madre": "Albanese",
        "livello_italiano": "A2",
        "pin_hash": "$2b$12$4zsGd6Qz14tNEpXEwmvnkuqWdMTuyAVKmAYtu/rR23.mrmro8uMVC",
    },
    "fratello1": {
        "slug": "fratello1",
        "nome": "Fratello 1",
        "lingua_madre": "Italiano",
        "livello_italiano": "Madrelingua",
        "pin_hash": "$2b$12$aYuNTtNhF.EFpozA9fhoXe/p3/UvKENZy3E/tQbhT1ZtBFa58DQkG",
    },
    "fratello2": {
        "slug": "fratello2",
        "nome": "Fratello 2",
        "lingua_madre": "Italiano",
        "livello_italiano": "Madrelingua",
        "pin_hash": "$2b$12$07nQ0IAXtns1ofaUmvXIVeQU3u2jg3q7nTT4x9NzjL3hH54DRblua",
    },
}


def _local_profiles() -> dict[str, dict]:
    """Profili locali (file) fusi con i default; il file ha la precedenza.

    In produzione il comportamento è *fail closed*: se il file dei profili manca
    o è illeggibile non vengono caricati né i profili demo né i loro PIN. Un
    file parziale non viene fuso con i default, così un profilo mancante non
    può riabilitare il PIN demo. Il ripristino avviene da un backup di
    `_local_db` o reimpostando i PIN con `POST /profili/{slug}/pin`.
    """
    stored = _fallback_read("profiles", None)
    if isinstance(stored, dict) and stored:
        if is_production():
            return copy.deepcopy(stored)
        merged = copy.deepcopy(DEFAULT_PROFILES)
        merged.update(stored)
        return merged
    if is_production():
        log.error(
            "Profili assenti o illeggibili in produzione: nessun profilo caricato "
            "(fail closed). Ripristina un backup di _local_db o reimposta i PIN."
        )
        return {}
    return copy.deepcopy(DEFAULT_PROFILES)


def _profiles_fallback() -> dict[str, dict]:
    """Fallback quando la lettura profili fallisce: mai i PIN demo in produzione."""
    if is_production():
        return {}
    return copy.deepcopy(DEFAULT_PROFILES)


def _local_profiles_write(profiles: dict[str, dict]) -> None:
    _fallback_write("profiles", profiles)


DEMO_PINS: dict[str, str] = {
    "io": "0000",
    "mamma": "1111",
    "papa": "2222",
    "fratello1": "3333",
    "fratello2": "4444",
}


def is_demo_pin_hash(pin_hash: Optional[str]) -> bool:
    """True se l'hash corrisponde a uno dei PIN demo del progetto."""
    if not pin_hash:
        return False
    return pin_hash in {
        str(profile.get("pin_hash")) for profile in DEFAULT_PROFILES.values() if profile.get("pin_hash")
    }


def demo_pins_in_use() -> list[str]:
    """Slug dei profili che usano ancora l'hash PIN demo (avviso in produzione)."""
    profiles = fetch_profiles()
    return [
        slug
        for slug in DEMO_PINS
        if slug in profiles
        and profiles[slug].get("pin_hash") == DEFAULT_PROFILES[slug].get("pin_hash")
    ]


@resilient(fallback_return=_profiles_fallback())
def fetch_profiles() -> dict[str, dict]:
    """Restituisce tutti i profili (chiave = slug)."""
    client = get_client()
    if client is None:
        return _local_profiles()
    response = client.table("profiles").select("*").execute()
    rows = response.data or []
    if not rows:
        return _local_profiles()
    profiles: dict[str, dict] = {}
    for row in rows:
        slug = row.get("slug")
        if not slug:
            continue
        profiles[slug] = {
            "slug": slug,
            "nome": row.get("nome", ""),
            "lingua_madre": row.get("lingua_madre", "Italiano"),
            "livello_italiano": row.get("livello_italiano", "B1"),
            "pin_hash": row.get("pin_hash"),
        }
    return profiles or _local_profiles()


def _fb_fetch_profiles() -> dict[str, dict]:
    return _local_profiles()


@resilient(fallback_return=None)
def upsert_profile(
    slug: str,
    nome: str,
    lingua_madre: str = "Italiano",
    livello_italiano: str = "B1",
    pin_hash: Optional[str] = None,
) -> dict | None:
    """Crea o aggiorna un profilo famiglia."""
    client = get_client()
    if client is None:
        return None
    data: dict[str, Any] = {
        "slug": slug,
        "nome": nome,
        "lingua_madre": lingua_madre,
        "livello_italiano": livello_italiano,
    }
    if pin_hash:
        data["pin_hash"] = pin_hash
    client.table("profiles").upsert(data, on_conflict="slug").execute()
    log.info("Profilo salvato: %s (%s)", slug, nome)
    return data


def _fb_upsert_profile(
    slug: str,
    nome: str,
    lingua_madre: str = "Italiano",
    livello_italiano: str = "B1",
    pin_hash: Optional[str] = None,
) -> dict:
    profiles = _local_profiles()
    existing = profiles.get(slug, {})
    profile = {
        "slug": slug,
        "nome": nome,
        "lingua_madre": lingua_madre,
        "livello_italiano": livello_italiano,
        "pin_hash": pin_hash or existing.get("pin_hash") or "",
    }
    profiles[slug] = profile
    _local_profiles_write(profiles)
    return profile


@resilient(fallback_return=False)
def delete_profile(slug: str) -> bool:
    client = get_client()
    if client is None:
        return False
    client.table("profiles").delete().eq("slug", slug).execute()
    log.info("Profilo eliminato: %s", slug)
    return True


def _fb_delete_profile(slug: str) -> bool:
    profiles = _local_profiles()
    if slug not in profiles:
        return False
    profiles.pop(slug, None)
    _local_profiles_write(profiles)
    return True


# ====================================================================
#  IMPOSTAZIONI APP (automazioni, notifiche, soglie)
# ====================================================================
DEFAULT_SETTINGS: dict[str, Any] = {
    "automazioni": {
        "lezione_italiano": True,
        "briefing_giornaliero": True,
        "controllo_email": True,
        "promemoria_acqua": True,
        "price_watcher": True,
        "report_settimanale": True,
        "classifica_studio": True,
        "crypto_tracker": True,
        "smart_calendar": True,
        "ombrello_smart": True,
        "promemoria_pillola": False,
    },
    "notifiche": {"attive": True},
    "soglie": {"crypto_variazione_percent": 5.0},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@resilient(fallback_return={})
def get_settings() -> dict:
    """Impostazioni complete (default + override salvati)."""
    client = get_client()
    stored: dict[str, Any] = {}
    if client is not None:
        try:
            response = client.table("app_settings").select("key,value").execute()
            for row in response.data or []:
                stored[str(row.get("key"))] = row.get("value")
        except Exception as exc:  # pragma: no cover - rete
            log.warning("Lettura impostazioni Supabase fallita: %s", exc)
    if not stored:
        stored = _fallback_read("app_settings", {}) or {}
    return _deep_merge(DEFAULT_SETTINGS, stored)


def _fb_get_settings() -> dict:
    return _deep_merge(DEFAULT_SETTINGS, _fallback_read("app_settings", {}) or {})


def _save_settings_local(patch: dict) -> dict:
    stored = _fallback_read("app_settings", {}) or {}
    merged = _deep_merge(stored, patch)
    _fallback_write("app_settings", merged)
    return _deep_merge(DEFAULT_SETTINGS, merged)


@resilient(fallback_return=DEFAULT_SETTINGS)
def update_settings(patch: dict) -> dict:
    """Applica un patch alle impostazioni (merge profondo per sezione)."""
    client = get_client()
    if client is None:
        return _save_settings_local(patch)
    for section, value in (patch or {}).items():
        if not isinstance(value, dict):
            continue
        client.table("app_settings").upsert(
            {"key": section, "value": value}, on_conflict="key"
        ).execute()
    return get_settings()


def _fb_update_settings(patch: dict) -> dict:
    return _save_settings_local(patch)


@resilient(fallback_return=None)
def get_setting(key: str, default: Any = None) -> Any:
    client = get_client()
    if client is None:
        return (_fallback_read("app_settings", {}) or {}).get(key, default)
    response = client.table("app_settings").select("value").eq("key", key).limit(1).execute()
    rows = response.data or []
    if not rows:
        return default
    return rows[0].get("value", default)


def _fb_get_setting(key: str, default: Any = None) -> Any:
    return (_fallback_read("app_settings", {}) or {}).get(key, default)


@resilient(fallback_return=False)
def set_setting(key: str, value: Any) -> bool:
    client = get_client()
    if client is None:
        return False
    client.table("app_settings").upsert({"key": key, "value": value}, on_conflict="key").execute()
    return True


def _fb_set_setting(key: str, value: Any) -> bool:
    stored = _fallback_read("app_settings", {}) or {}
    stored[key] = value
    _fallback_write("app_settings", stored)
    return True


def automation_enabled(name: str) -> bool:
    """True se l'automazione è attiva nelle impostazioni (default: sì)."""
    try:
        settings = get_settings() or DEFAULT_SETTINGS
        automazioni = settings.get("automazioni") or {}
        notifiche = settings.get("notifiche") or {}
        if notifiche.get("attive") is False:
            return False
        return bool(automazioni.get(name, True))
    except Exception:
        return True


# ====================================================================
#  PUSH TOKENS
# ====================================================================
@resilient(fallback_return=False)
def save_push_token(profile_slug: str, token: str, device_info: str = "", platform: str = "") -> bool:
    """Registra (o riattiva) il token push di un dispositivo."""
    client = get_client()
    if client is None:
        return False
    client.table("push_tokens").upsert(
        {
            "profile_slug": profile_slug,
            "token": token,
            "device_info": (device_info or platform or "")[:200],
            "platform": (platform or "")[:20],
            "is_active": True,
        },
        on_conflict="token",
    ).execute()
    return True


def _fb_save_push_token(profile_slug: str, token: str, device_info: str = "", platform: str = "") -> bool:
    rows = _fallback_read("push_tokens", [])
    for row in rows:
        if row.get("token") == token:
            row.update(
                {
                    "profile_slug": profile_slug,
                    "device_info": device_info or platform or "",
                    "platform": platform or "",
                    "is_active": True,
                }
            )
            break
    else:
        rows.append(
            {
                "profile_slug": profile_slug,
                "token": token,
                "device_info": device_info or platform or "",
                "platform": platform or "",
                "is_active": True,
                "created_at": _now_iso(),
            }
        )
    _fallback_write("push_tokens", rows)
    return True


@resilient(fallback_return=[])
def get_push_tokens(profile_slug: Optional[str] = None) -> list[dict]:
    """Token push attivi, eventualmente filtrati per profilo."""
    client = get_client()
    if client is None:
        return []
    query = client.table("push_tokens").select("*").eq("is_active", True)
    if profile_slug:
        query = query.eq("profile_slug", profile_slug)
    return list(query.execute().data or [])


def _fb_get_push_tokens(profile_slug: Optional[str] = None) -> list[dict]:
    rows = _fallback_read("push_tokens", [])
    active = [row for row in rows if row.get("is_active", True)]
    if profile_slug:
        active = [row for row in active if row.get("profile_slug") == profile_slug]
    return active


@resilient(fallback_return=False)
def deactivate_push_token(token: str) -> bool:
    client = get_client()
    if client is None:
        return False
    client.table("push_tokens").update({"is_active": False}).eq("token", token).execute()
    return True


def _fb_deactivate_push_token(token: str) -> bool:
    rows = _fallback_read("push_tokens", [])
    changed = False
    for row in rows:
        if row.get("token") == token:
            row["is_active"] = False
            changed = True
    if changed:
        _fallback_write("push_tokens", rows)
    return changed


# ====================================================================
#  TOKEN REVOCATI (logout reale)
# ====================================================================
@resilient(fallback_return=False)
def revoke_token(token_hash: str, expires_at: int) -> bool:
    """Inserisce l'impronta del token nella denylist fino alla scadenza."""
    client = get_client()
    if client is None:
        return False
    client.table("revoked_tokens").upsert(
        {"token_hash": token_hash, "expires_at": int(expires_at)},
        on_conflict="token_hash",
    ).execute()
    return True


def _fb_revoke_token(token_hash: str, expires_at: int) -> bool:
    now = int(datetime.now(timezone.utc).timestamp())
    rows = [
        row
        for row in _fallback_read("revoked_tokens", [])
        if int(row.get("expires_at", 0) or 0) > now
    ]
    rows.append({"token_hash": token_hash, "expires_at": int(expires_at)})
    _fallback_write("revoked_tokens", rows)
    return True


@resilient(fallback_return=False)
def is_token_revoked(token_hash: str) -> bool:
    client = get_client()
    if client is None:
        return False
    response = (
        client.table("revoked_tokens")
        .select("token_hash")
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def _fb_is_token_revoked(token_hash: str) -> bool:
    now = int(datetime.now(timezone.utc).timestamp())
    for row in _fallback_read("revoked_tokens", []):
        if row.get("token_hash") == token_hash and int(row.get("expires_at", 0) or 0) > now:
            return True
    return False


# ====================================================================
#  PROGRESSO ITALIANO
# ====================================================================
@resilient(fallback_return=False)
def add_italian_progress(profile_slug: str, lezione_id: str, punteggio: int) -> bool:
    client = get_client()
    if client is None:
        return False
    client.table("italian_progress").insert(
        {
            "profile_slug": profile_slug,
            "lezione_id": lezione_id[:100],
            "punteggio": int(punteggio),
            "completato": True,
        }
    ).execute()
    return True


def _fb_add_italian_progress(profile_slug: str, lezione_id: str, punteggio: int) -> bool:
    rows = _fallback_read("italian_progress", [])
    rows.append(
        {
            "profile_slug": profile_slug,
            "lezione_id": lezione_id[:100],
            "punteggio": int(punteggio),
            "completato": True,
            "created_at": _now_iso(),
        }
    )
    _fallback_write("italian_progress", rows)
    return True


def _progress_rows() -> list[dict]:
    client = get_client()
    if client is not None:
        try:
            response = client.table("italian_progress").select("*").execute()
            rows = list(response.data or [])
            if rows:
                return rows
        except Exception as exc:  # pragma: no cover
            log.warning("Lettura progressi Supabase fallita: %s", exc)
    return _fallback_read("italian_progress", [])


def _calculate_streak(days: set[str]) -> int:
    """Giorni consecutivi con attività, contando da oggi (o ieri)."""
    if not days:
        return 0
    cursor = date.today()
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@resilient(fallback_return={"punti": 0, "streak": 0, "esercizi": 0})
def get_italian_progress(profile_slug: str) -> dict:
    rows = [row for row in _progress_rows() if row.get("profile_slug") == profile_slug]
    punti = sum(int(row.get("punteggio", 0) or 0) for row in rows)
    days = {
        str(row.get("created_at") or "")[:10]
        for row in rows
        if row.get("created_at")
    }
    return {"punti": punti, "streak": _calculate_streak(days), "esercizi": len(rows)}


def _fb_get_italian_progress(profile_slug: str) -> dict:
    rows = [row for row in _fallback_read("italian_progress", []) if row.get("profile_slug") == profile_slug]
    punti = sum(int(row.get("punteggio", 0) or 0) for row in rows)
    days = {str(row.get("created_at") or "")[:10] for row in rows if row.get("created_at")}
    return {"punti": punti, "streak": _calculate_streak(days), "esercizi": len(rows)}


def _build_leaderboard(rows: list[dict]) -> list[dict]:
    profiles = fetch_profiles()
    totals: dict[str, int] = {}
    days: dict[str, set[str]] = {}
    for row in rows:
        slug = str(row.get("profile_slug") or "")
        if not slug:
            continue
        totals[slug] = totals.get(slug, 0) + int(row.get("punteggio", 0) or 0)
        days.setdefault(slug, set()).add(str(row.get("created_at") or "")[:10])
    board = [
        {
            "slug": slug,
            "nome": profiles.get(slug, {}).get("nome", slug),
            "punti": punti,
            "streak": _calculate_streak(days.get(slug) or set()),
        }
        for slug, punti in totals.items()
    ]
    return sorted(board, key=lambda item: item["punti"], reverse=True)


@resilient(fallback_return=[])
def get_italian_leaderboard() -> list[dict]:
    """Classifica famiglia per punti italiano."""
    return _build_leaderboard(_progress_rows())


def _fb_get_italian_leaderboard() -> list[dict]:
    return _build_leaderboard(_fallback_read("italian_progress", []))


# ====================================================================
#  DASHBOARD (dati reali per la Home)
# ====================================================================
def get_dashboard(profile_slug: str) -> dict:
    """KPI reali della famiglia per la schermata Home."""
    todos = get_todos()
    pending = [todo for todo in todos if not todo.get("is_completed")]
    budget_month = get_budget_summary(only_month=True)
    tokens = get_push_tokens()
    progress = get_italian_progress(profile_slug)
    return {
        "todos_totali": len(todos),
        "todos_pendenti": len(pending),
        "spesa_mese": float((budget_month or {}).get("totale", 0.0) or 0.0),
        "dispositivi_notifiche": len(tokens),
        "punti_italiano": int((progress or {}).get("punti", 0) or 0),
        "streak_italiano": int((progress or {}).get("streak", 0) or 0),
    }
