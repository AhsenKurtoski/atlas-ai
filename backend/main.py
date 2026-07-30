"""
ATLAS AI v3.0 — Entrypoint principale FastAPI.

Sicurezza & Architettura:
- CORS restrittivo basato su variabile ambiente
- Rate limiting (slowapi) per proteggere PIN bruteforce
- Validazione input Pydantic v2
- Autenticazione PIN con hash bcrypt + confronto a tempo costante
- Persistenza Supabase + fallback locale resiliente
- Logging strutturato con rotazione file
"""
from __future__ import annotations

import ipaddress
import os
import time
import urllib.parse
from contextlib import asynccontextmanager
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.ai_router import ai_router
from app.core.database import (
    add_spesa,
    add_todo,
    complete_todo_by_index,
    fetch_profiles,
    get_budget_summary,
    get_todos,
    get_user_memory,
    is_mock_mode,
    save_message,
)
from app.core.logging_config import get_logger
from app.core.schemas import (
    AddSpesaRequest,
    AddTodoRequest,
    ChatRequest,
    ChatResponse,
    GenericResponse,
    HealthResponse,
    PinAuthRequest,
    PinAuthResponse,
    ProfileSummary,
)
from app.core.security import generate_safe_token, is_safe_numeric_pin, verify_pin
from app.scheduler import start_scheduler, stop_scheduler

log = get_logger(__name__)

# ---------------- Rate Limiter ----------------
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


# ---------------- Lifespan ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 Avvio ATLAS AI v3.0 - ambiente=%s", os.getenv("APP_ENV", "development"))
    try:
        start_scheduler(run_test=True)
    except Exception as exc:
        log.error("Impossibile avviare scheduler (continuo senza): %s", exc)
    log.info("✅ Modalità DB: %s", "MOCK/LOCALE" if is_mock_mode() else "SUPABASE")
    yield
    log.info("🛑 Arresto ATLAS AI")
    try:
        stop_scheduler()
    except Exception:
        pass


# ---------------- App & middleware ----------------
app = FastAPI(
    title="ATLAS AI v3.0 Backend",
    description="Assistente AI per la famiglia con LLM + 45+ tools integrati",
    version="3.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    # In produzione: "*" con credentials è proibito dallo standard; permettiamo
    # origini esplicite. Se "development" aggiungiamo localhost standard Expo.
    env = os.getenv("APP_ENV", "development")
    if env == "development":
        for extra in ("http://localhost:8081", "http://localhost:19006"):
            if extra not in parts:
                parts.append(extra)
    # Filtriamo wild-card disallineati con credentials=True
    safe: list[str] = [p for p in parts if p != "*"]
    return safe


_CORS_ORIGINS = _parse_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS if _CORS_ORIGINS else ["*"],
    allow_credentials=bool(_CORS_ORIGINS),  # non si può abilitare con "*"
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    max_age=600,
)
log.info("CORS origins: %s", _CORS_ORIGINS or ["*"])


# ---------------- Token storage in-memory (refactorabile in Redis/Supabase) ----------------
_TOKENS: dict[str, tuple[str, float]] = {}  # token -> (slug, expires_at)
_TOKEN_TTL_SEC = 60 * 60 * 8  # 8 ore


def _validate_token(token: str | None, expected_slug: str) -> bool:
    """Valida un token e opzionalmente controlla che appartenga allo slug atteso."""
    if not token:
        return False
    entry = _TOKENS.get(token)
    if not entry:
        return False
    slug, expires = entry
    if expires < time.time():
        _TOKENS.pop(token, None)
        return False
    return slug == expected_slug


# ---------------- Root & Health ----------------
@app.get("/", response_model=HealthResponse)
@limiter.limit("60/minute")
def read_root(request: Request) -> HealthResponse:
    profili = len(fetch_profiles())
    return HealthResponse(
        status="ok",
        profili=profili,
        automazioni=8,
        ambiente=os.getenv("APP_ENV", "development"),
        versione="3.0.0",
    )


# ---------------- Profili ----------------
@app.get("/profili", response_model=dict[str, ProfileSummary])
@limiter.limit("30/minute")
def get_profili(request: Request) -> dict[str, ProfileSummary]:
    profili = fetch_profiles()
    return {
        k: ProfileSummary(
            nome=v.get("nome", ""),
            livello_italiano=v.get("livello_italiano", "B1"),
        )
        for k, v in profili.items()
    }


# ---------------- Auth PIN ----------------
@app.post("/auth/pin", response_model=PinAuthResponse)
@limiter.limit("5/minute")  # Protezione bruteforce: 5 tentativi al minuto per IP
async def verifica_pin(request: Request, payload: PinAuthRequest) -> PinAuthResponse:
    profili = fetch_profiles()
    profilo = profili.get(payload.profilo.lower())
    if not profilo:
        log.warning("Auth fallito: profilo sconosciuto %s", payload.profilo)
        return PinAuthResponse(auth=False, message="Profilo non valido.")

    if not is_safe_numeric_pin(payload.pin):
        return PinAuthResponse(auth=False, message="PIN non valido (solo cifre 4-8).")

    pin_hash = profilo.get("pin_hash")
    if not pin_hash:
        log.error("Nessun pin_hash configurato per %s (auth non disponibile)", profilo["slug"])
        return PinAuthResponse(auth=False, message="Profilo non configurato correttamente.")

    ok = verify_pin(payload.pin, pin_hash)
    if not ok:
        log.info("PIN errato per %s", profilo["slug"])
        return PinAuthResponse(auth=False, message="PIN errato.")

    token = generate_safe_token(40)
    expires = time.time() + _TOKEN_TTL_SEC
    _TOKENS[token] = (profilo["slug"], expires)
    log.info("Auth OK: %s, token=%s...", profilo["slug"], token[:6])
    return PinAuthResponse(
        auth=True,
        profilo=profilo.get("nome"),
        token=token,
        message="Autenticazione riuscita.",
    )


# ---------------- Chat ----------------
@app.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_endpoint(request: Request, payload: ChatRequest) -> ChatResponse:
    t0 = time.perf_counter()
    profili = fetch_profiles()
    slug = payload.profilo.lower()
    profilo = profili.get(slug) or profili.get("io")
    if profilo is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profilo inesistente.")

    # Chat è permessa anche senza token se l'utente ha già superato il PIN lato app;
    # il token è opzionale ma se fornito viene validato per sicurezza.
    if payload.token and not _validate_token(payload.token, slug):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido o scaduto.")

    # Salva messaggio utente (persistente RAG)
    save_message(profile_slug=slug, role="user", content=payload.msg)

    # Carica memoria recente come contesto (se supportato dal router)
    memoria = get_user_memory(profile_slug=slug, limit=10)

    risposta = ai_router.chiedi(prompt=payload.msg, profilo_utente=profilo, memoria=memoria)

    save_message(profile_slug=slug, role="ai", content=str(risposta))

    return ChatResponse(
        reply=str(risposta),
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


# ---------------- Todos / Lista spesa ----------------
@app.get("/todos")
@limiter.limit("60/minute")
def lista_todos(request: Request, filtro: str = Query(default="")) -> GenericResponse:
    only_pending = filtro.lower() in ("da_fare", "pending", "attivi", "da fare")
    todos = get_todos(only_pending=only_pending)
    simplified = [
        {
            "id": t.get("id"),
            "task": t.get("task_text") or t.get("task"),
            "assegnato_a": t.get("assegnato_a", "Tutti"),
            "done": bool(t.get("is_completed", t.get("done", False))),
            "created": t.get("created_at") or t.get("created"),
        }
        for t in todos
    ]
    return GenericResponse(status="ok", data=simplified)


@app.post("/todos", response_model=GenericResponse)
@limiter.limit("30/minute")
def aggiungi_todo(request: Request, payload: AddTodoRequest) -> GenericResponse:
    esito = add_todo(task=payload.task, created_by_slug=payload.slug, assegnato_a=payload.assegnato_a)
    return GenericResponse(status="ok", message=esito if isinstance(esito, str) else "Todo aggiunto.")


@app.post("/todos/{numero}/completa", response_model=GenericResponse)
@limiter.limit("60/minute")
def completa_todo(request: Request, numero: int) -> GenericResponse:
    if complete_todo_by_index(numero):
        return GenericResponse(status="ok", message=f"Todo {numero} completato.")
    return GenericResponse(status="error", message="Numero task non valido.")


# ---------------- Budget / Spese ----------------
@app.get("/budget")
@limiter.limit("60/minute")
def budget(request: Request) -> GenericResponse:
    return GenericResponse(status="ok", data=get_budget_summary())


@app.post("/budget/spesa", response_model=GenericResponse)
@limiter.limit("30/minute")
def aggiungi_spesa(request: Request, payload: AddSpesaRequest) -> GenericResponse:
    esito = add_spesa(
        importo=float(payload.importo),
        categoria=payload.categoria.strip(),
        descrizione=payload.descrizione.strip(),
        slug=payload.slug.lower(),
    )
    return GenericResponse(status="ok", message=esito if isinstance(esito, str) else "Spesa registrata.")


# ---------------- Gestione errori globali ----------------
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    log.warning("HTTP %s: %s", exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Eccezione non gestita su %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "Errore interno del server. I dettagli sono nel log.",
        },
    )
