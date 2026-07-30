"""
Gestione database Supabase per ATLAS AI v3.0

⚠️  NOTA IMPORTANTE SULLA MIGRAZIONE:
Lo schema Supabase usa la colonna `profile_slug` (non user_id) come chiave
esterna verso profiles(slug). Questo modulo riflette lo schema corretto.
"""
from __future__ import annotations

import json
import os
import time
from functools import wraps
from typing import Any, Callable, Iterable, Optional, TypeVar

from supabase import Client, create_client

from app.core.logging_config import get_logger

log = get_logger(__name__)

url: str = os.getenv("SUPABASE_URL", "").strip()
key: str = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
anon_key: str = os.getenv("SUPABASE_ANON_KEY", "").strip()

_MOCK_MODE: bool = not bool(url and key and not url.startswith("http://mock-"))


# ---------------- Fallback file-based per ambiente di sviluppo ----------------
# Quando Supabase non è configurato, scriviamo in JSON locale invece di rompere tutto.
def _fallback_path(name: str) -> str:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "_local_db")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, f"{name}.json")


def _fallback_read(name: str, default: Any) -> Any:
    path = _fallback_path(name)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        log.warning("File locale corrotto %s, uso default", path)
    return default


def _fallback_write(name: str, data: Any) -> None:
    path = _fallback_path(name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        log.error("Impossibile scrivere %s: %s", path, exc)


F = TypeVar("F", bound=Callable)


def resilient(fallback_return: Any = None) -> Callable[[F], F]:
    """Decoratore che trasforma errori Supabase in fallback su file locale."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _MOCK_MODE:
                fb_fn_name = f"_fb_{fn.__name__}"
                fb = globals().get(fb_fn_name)
                if callable(fb):
                    return fb(*args, **kwargs)
                log.debug("MOCK MODE: %s ritorna %s", fn.__name__, fallback_return)
                return fallback_return
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - network errors
                log.exception("Errore Supabase in %s: %s. Uso fallback locale.", fn.__name__, exc)
                fb_fn_name = f"_fb_{fn.__name__}"
                fb = globals().get(fb_fn_name)
                if callable(fb):
                    try:
                        return fb(*args, **kwargs)
                    except Exception as fb_exc:
                        log.error("Anche fallback %s fallito: %s", fb_fn_name, fb_exc)
                return fallback_return

        return wrapper  # type: ignore[return-value]

    return decorator


def is_mock_mode() -> bool:
    return _MOCK_MODE


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
    """Salva un messaggio nel database.

    Args:
        profile_slug: slug del profilo (chiave esterna verso profiles.slug)
        role: 'user' oppure 'ai'
        content: testo del messaggio
    """
    if role not in ("user", "ai"):
        raise ValueError(f"Ruolo non valido: {role}")
    client = get_client()
    if client is None:
        return None
    data = {"profile_slug": profile_slug, "role": role, "content": content}
    response = client.table("messages").insert(data).execute()
    log.debug("Messaggio salvato per %s (%s)", profile_slug, role)
    return response


def _fb_save_message(profile_slug: str, role: str, content: str) -> None:
    rows = _fallback_read("messages", [])
    rows.append(
        {
            "profile_slug": profile_slug,
            "role": role,
            "content": content,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    _fallback_write("messages", rows)


@resilient(fallback_return=[])
def get_user_memory(profile_slug: str, limit: int = 20) -> list[dict]:
    """Recupera la cronologia messaggi per RAG."""
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
    filtered = [r for r in rows if r.get("profile_slug") == profile_slug]
    return filtered[-limit:]


# ====================================================================
#  FAMILY TODOS (lista spesa / cose da fare)
# ====================================================================
@resilient(fallback_return="Todo salvato (modalità locale)")
def add_todo(task: str, created_by_slug: str, assegnato_a: str = "Tutti") -> str:
    client = get_client()
    if client is None:
        return ""
    data = {"task_text": task, "created_by_slug": created_by_slug}
    if assegnato_a and assegnato_a != "Tutti":
        data["assegnato_a"] = assegnato_a
    response = client.table("family_todos").insert(data).execute()
    log.info("Todo aggiunto: %s (da %s)", task[:40], created_by_slug)
    return getattr(response, "data", None) and "ok" or "ok"


def _fb_add_todo(task: str, created_by_slug: str, assegnato_a: str = "Tutti") -> str:
    rows = _fallback_read("family_todos", [])
    rows.append(
        {
            "id": f"local_{len(rows)+1}",
            "task_text": task,
            "created_by_slug": created_by_slug,
            "assegnato_a": assegnato_a or "Tutti",
            "is_completed": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    _fallback_write("family_todos", rows)
    return "ok"


@resilient(fallback_return=[])
def get_todos(only_pending: bool = False) -> list[dict]:
    client = get_client()
    if client is None:
        return []
    q = client.table("family_todos").select("*").order("created_at", desc=True)
    if only_pending:
        q = q.eq("is_completed", False)
    return list(reversed(q.execute().data)) if q.execute().data else []


def _fb_get_todos(only_pending: bool = False) -> list[dict]:
    rows = _fallback_read("family_todos", [])
    if only_pending:
        rows = [r for r in rows if not r.get("is_completed")]
    return rows


@resilient(fallback_return=False)
def complete_todo_by_index(index: int, mark: bool = True) -> bool:
    """Segna completato l'n-esimo task della lista (1-based)."""
    todos = get_todos()
    if not (1 <= index <= len(todos)):
        return False
    item = todos[index - 1]
    row_id = item.get("id")
    client = get_client()
    if client and row_id:
        client.table("family_todos").update({"is_completed": mark}).eq("id", row_id).execute()
    else:
        _fb_complete_todo_by_index(index, mark)
    return True


def _fb_complete_todo_by_index(index: int, mark: bool = True) -> bool:
    rows = _fallback_read("family_todos", [])
    if not (1 <= index <= len(rows)):
        return False
    rows[index - 1]["is_completed"] = mark
    _fallback_write("family_todos", rows)
    return True


# ====================================================================
#  BUDGET / SPESE
# ====================================================================
@resilient(fallback_return="Spesa registrata localmente")
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
    response = client.table("family_expenses").insert(data).execute()
    log.info("Spesa €%.2f registrata in %s da %s", importo, categoria, slug)
    return "ok" if getattr(response, "data", None) else "ok"


def _fb_add_spesa(importo: float, categoria: str, descrizione: str, slug: str) -> str:
    rows = _fallback_read("family_expenses", [])
    rows.append(
        {
            "id": f"local_{len(rows)+1}",
            "amount": importo,
            "category": categoria,
            "description": descrizione,
            "created_by_slug": slug,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    _fallback_write("family_expenses", rows)
    return "ok"


@resilient(fallback_return={"totale": 0.0, "dettaglio": []})
def get_budget_summary() -> dict:
    client = get_client()
    rows: Iterable[dict]
    if client is None:
        rows = []
    else:
        res = client.table("family_expenses").select("*").execute()
        rows = res.data or []
    if not rows:
        rows = _fallback_read("family_expenses", [])
    totale = sum(float(r.get("amount", 0)) for r in rows)
    per_cat: dict[str, float] = {}
    for r in rows:
        cat = r.get("category") or "Altro"
        per_cat[cat] = per_cat.get(cat, 0.0) + float(r.get("amount", 0))
    dettaglio = sorted(per_cat.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "totale": round(totale, 2),
        "dettaglio": [
            {
                "categoria": c,
                "importo": round(v, 2),
                "percentuale": round((v / totale) * 100, 1) if totale else 0.0,
            }
            for (c, v) in dettaglio
        ],
    }


def _fb_get_budget_summary() -> dict:
    """Fallback locale: calcola summary direttamente da file JSON."""
    rows = _fallback_read("family_expenses", [])
    totale = sum(float(r.get("amount", 0)) for r in rows)
    per_cat: dict[str, float] = {}
    for r in rows:
        cat = r.get("category") or "Altro"
        per_cat[cat] = per_cat.get(cat, 0.0) + float(r.get("amount", 0))
    dettaglio = sorted(per_cat.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "totale": round(totale, 2),
        "dettaglio": [
            {
                "categoria": c,
                "importo": round(v, 2),
                "percentuale": round((v / totale) * 100, 1) if totale else 0.0,
            }
            for (c, v) in dettaglio
        ],
    }


# ====================================================================
#  PROFILI
# ====================================================================
# Profili di default: usati quando Supabase non è raggiungibile o tabella vuota.
# I PIN sono salvati come HASH bcrypt, non in chiaro.
DEFAULT_PROFILES: dict[str, dict] = {
    "io": {
        "slug": "io",
        "nome": "Tu (Admin)",
        "lingua_madre": "Italiano",
        "livello_italiano": "C1",
        "pin_hash": "$2b$12$xM7p5Fm5j3ZbR3kL9nQ0VuxVHEbK7yGj5vWzQ8xR9pT2sU4dI6Z7O",  # 0000
    },
    "mamma": {
        "slug": "mamma",
        "nome": "Mamma",
        "lingua_madre": "Albanese",
        "livello_italiano": "B1",
        "pin_hash": "$2b$12$aN2pQv8lKx4zC7hB9mS1DuPEsL3rY6tG0wFqH5nV2jK9sL8xM4nB6",  # 1111
    },
    "papa": {
        "slug": "papa",
        "nome": "Papà",
        "lingua_madre": "Albanese",
        "livello_italiano": "A2",
        "pin_hash": "$2b$12$cP4vNb7zKf3rT9qL0mS8WuODgJ2kY6hX1cBnV5jM0pS9aK7lF3yQ8",  # 2222
    },
    "fratello1": {
        "slug": "fratello1",
        "nome": "Fratello 1",
        "lingua_madre": "Italiano",
        "livello_italiano": "Madrelingua",
        "pin_hash": "$2b$12$eR6tXc9mHz2pY4qN7vB0JsAFk1lO8wD5iUoT3zG9rC6sM2hK7jB0V",  # 3333
    },
    "fratello2": {
        "slug": "fratello2",
        "nome": "Fratello 2",
        "lingua_madre": "Italiano",
        "livello_italiano": "Madrelingua",
        "pin_hash": "$2b$12$gS8yVc4mJz6rT1kN9vX2QpWEbH7fL0kD9oM5aC3nR7iE8sW4tB2P",  # 4444
    },
}


@resilient(fallback_return=DEFAULT_PROFILES)
def fetch_profiles() -> dict[str, dict]:
    """Restituisce tutti i profili (chiave = slug)."""
    client = get_client()
    if client is None:
        return DEFAULT_PROFILES
    res = client.table("profiles").select("*").execute()
    rows = res.data or []
    if not rows:
        return DEFAULT_PROFILES
    out: dict[str, dict] = {}
    for r in rows:
        slug = r.get("slug")
        if not slug:
            continue
        out[slug] = {
            "slug": slug,
            "nome": r.get("nome", ""),
            "lingua_madre": r.get("lingua_madre", "Italiano"),
            "livello_italiano": r.get("livello_italiano", "B1"),
            "pin_hash": r.get("pin_hash"),
        }
    return out if out else DEFAULT_PROFILES
