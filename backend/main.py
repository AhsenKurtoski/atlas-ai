"""
ATLAS AI v3.4 — Entrypoint principale FastAPI.

Sicurezza & architettura:
- Token di sessione firmati HMAC (stateless → sicuri anche con più worker)
- Autenticazione obbligatoria su tutti i dati privati (todos, budget, chat, …)
- Rate limiting (slowapi) contro bruteforce del PIN
- Validazione input Pydantic v2 e messaggi d'errore uniformi
- Persistenza Supabase + fallback locale resiliente
- Logging strutturato con rotazione file

Nota: qui NON usiamo `from __future__ import annotations` perché FastAPI deve
risolvere le annotazioni a runtime (slowapi avvolge gli endpoint e i tipi
rinviati diventerebbero ForwardRef non risolvibili).
"""
import base64
import binascii
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.concurrency import run_in_threadpool

from app.ai_router import ai_router
from app.core import auth_guard, parental
from app.core.context import current_profile
from app.core.database import (
    DEMO_PINS,
    add_spesa,
    add_todo,
    complete_todo_by_index,
    delete_todo_by_index,
    delete_profile as db_delete_profile,
    deactivate_push_token,
    fetch_profiles,
    get_budget_summary,
    get_chat_history,
    get_dashboard,
    get_italian_leaderboard,
    get_italian_progress,
    get_push_tokens,
    get_reminders,
    get_settings,
    get_todos,
    get_user_memory,
    is_demo_pin_hash,
    is_mock_mode,
    pin_version as db_pin_version,
    save_message,
    save_push_token,
    cancel_reminder,
    mark_reminder_local_scheduled,
    update_settings,
    upsert_profile,
    add_italian_progress,
    demo_pins_in_use,
    is_token_revoked,
    revoke_token,
)
from app.core.logging_config import get_logger
from app.core.schemas import (
    AddSpesaRequest,
    AddTodoRequest,
    BudgetLimitsRequest,
    ChatRequest,
    ChatResponse,
    ConfermaInvioEmail,
    CreateProfileRequest,
    GenericResponse,
    HealthResponse,
    MeResponse,
    PinAuthRequest,
    ParentalLimitsRequest,
    PinAuthResponse,
    PdfRequest,
    ProfileSummary,
    PushRegisterRequest,
    PushTestRequest,
    QuizSubmitRequest,
    RecoverRequest,
    SettingsUpdateRequest,
    TranscriptionRequest,
    TranscriptionResponse,
    UpdatePinRequest,
)
from app.core.security import (
    create_access_token,
    decode_token_details,
    generate_recovery_code,
    hash_pin,
    is_valid_recovery_code,
    normalize_recovery_code,
    normalize_slug,
    sha256_text,
    token_info,
    token_ttl_seconds,
    verify_pin,
    verify_recovery_code,
)
from app.core.settings import (
    cors_origin_regex,
    cors_origins,
    is_production,
    scheduler_enabled,
)
from app.notifiche import invia_a_profilo
from app.services import budget_report, privacy
from app.services.backup import backup_local_db
from app.services.browser import browser_profile, shutdown_browser
from app.services.pdf import build_pdf
from app.scheduler import (
    automazioni_totali,
    get_jobs,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
)
from app.tools.italian import lezione_del_giorno, normalizza_livello, quiz_per_livello, valuta_quiz

log = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

# Uptime del processo, usato da /health per i monitor esterni.
_STARTED_AT = time.time()


# ---------------- Lifespan ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 Avvio ATLAS AI v3.4 - ambiente=%s", os.getenv("APP_ENV", "development"))
    if scheduler_enabled():
        try:
            start_scheduler()
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            log.error("Impossibile avviare scheduler (continuo senza): %s", exc)
    else:
        log.info("⏸️ Scheduler disattivato da SCHEDULER_ENABLED=false")
    log.info("✅ Modalità DB: %s", "MOCK/LOCALE" if is_mock_mode() else "SUPABASE")
    log.info("✅ Chiavi Gemini: %d", len(ai_router.chiavi))

    if is_mock_mode():
        backup = backup_local_db()
        if backup is not None:
            log.info("🗄️ Backup database locale all'avvio: %s", backup.name)

    if is_production():
        if not os.getenv("ATLAS_SECRET_KEY", "").strip():
            log.warning(
                "⚠️ ATLAS_SECRET_KEY non impostata: i token valgono solo su questo host. "
                "Imposta un segreto unico per tutti i worker/istanze."
            )
        demo = demo_pins_in_use()
        if demo:
            log.warning(
                "⚠️ PIN demo ancora attivi per: %s. Cambiali prima di esporre il servizio.",
                ", ".join(demo),
            )
        if "*" in cors_origins():
            log.warning(
                "⚠️ CORS aperto a tutte le origini: imposta CORS_ALLOWED_ORIGINS in produzione."
            )
        elif not cors_origins():
            log.info(
                "🔒 CORS chiuso: nessuna origine web autorizzata "
                "(le app native non usano CORS; imposta CORS_ALLOWED_ORIGINS per la preview web)."
            )

    try:
        yield
    finally:
        log.info("🛑 Arresto ATLAS AI")
        try:
            stop_scheduler()
        except Exception:  # pragma: no cover
            pass
        try:
            shutdown_browser()
        except Exception:  # pragma: no cover
            pass


APP_VERSION = "3.4.0"

app = FastAPI(
    title=f"ATLAS AI v{APP_VERSION} Backend",
    description="Assistente AI per la famiglia con LLM, tool reali e notifiche push",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------- CORS ----------------
_ORIGINS = cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    # Origini con IP variabile (preview web in LAN): vedi app/core/settings.py.
    allow_origin_regex=cors_origin_regex(),
    allow_credentials="*" not in _ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    max_age=600,
)


# ---------------- Autenticazione ----------------
def get_current_profile(request: Request) -> str:
    """Slug del profilo autenticato (header `Authorization: Bearer <token>`)."""
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token mancante: effettua l'accesso.")
    raw_token = header[7:].strip()
    details = decode_token_details(raw_token)
    if not details:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione scaduta: effettua di nuovo l'accesso.")
    slug, _expires_at, token_version = details
    if is_token_revoked(sha256_text(raw_token)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione chiusa: effettua di nuovo l'accesso.")
    profilo = fetch_profiles().get(slug)
    if not profilo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Profilo non più valido.")
    if token_version != db_pin_version(profilo):
        # Il PIN è cambiato dopo l'emissione del token: sessione revocata.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "PIN aggiornato: accedi di nuovo con il nuovo PIN.",
        )
    return slug


# ---------------- Root & Health ----------------
@app.get("/", response_model=HealthResponse)
@limiter.limit("60/minute")
def read_root(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        profili=len(fetch_profiles()),
        automazioni=automazioni_totali(),
        scheduler_attivo=get_scheduler() is not None,
        ambiente=os.getenv("APP_ENV", "development"),
        db_mode="locale" if is_mock_mode() else "supabase",
        notifiche="expo",
        llm=bool(ai_router.chiavi),
    )


@app.get("/health")
@limiter.limit("240/minute")
def healthcheck(request: Request) -> dict[str, Any]:
    """Health check leggero per i monitor di uptime (UptimeRobot, systemd, CI).

    Non tocca il database: risponde in pochi millisecondi anche sotto carico.
    """
    return {
        "status": "ok",
        "versione": APP_VERSION,
        "ambiente": os.getenv("APP_ENV", "development"),
        "scheduler_attivo": get_scheduler() is not None,
        "llm": bool(ai_router.chiavi),
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "uptime_iso": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ---------------- Profili ----------------
@app.get("/profili", response_model=dict[str, ProfileSummary])
@limiter.limit("60/minute")
def get_profili(request: Request) -> dict[str, ProfileSummary]:
    return {
        slug: ProfileSummary(
            nome=profile.get("nome", ""),
            livello_italiano=profile.get("livello_italiano", "B1"),
            lingua_madre=profile.get("lingua_madre", "Italiano"),
            tipo=str(profile.get("tipo") or "adulto"),
        )
        for slug, profile in fetch_profiles().items()
    }


@app.post("/profili", response_model=GenericResponse)
@limiter.limit("20/minute")
def crea_profilo(
    request: Request,
    payload: CreateProfileRequest,
    slug_autenticato: str = Depends(get_current_profile),
) -> GenericResponse:
    if slug_autenticato != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo il profilo amministratore può creare o eliminare profili.",
        )
    profili = fetch_profiles()
    slug = normalize_slug(payload.slug or payload.nome)
    if not slug:
        return GenericResponse(status="error", message="Nome non valido: usa lettere o numeri.")
    if slug in profili:
        return GenericResponse(status="error", message=f"Esiste già un profilo '{slug}'.")
    if len(profili) >= 15:
        return GenericResponse(status="error", message="Limite di 15 profili famiglia raggiunto.")

    codice_recupero = generate_recovery_code()
    upsert_profile(
        slug=slug,
        nome=payload.nome.strip(),
        lingua_madre=payload.lingua_madre.strip() or "Italiano",
        livello_italiano=payload.livello_italiano.strip() or "B1",
        pin_hash=hash_pin(payload.pin),
        recovery_hash=hash_pin(normalize_recovery_code(codice_recupero)),
    )
    log.info("Profilo creato da %s: %s", slug_autenticato, slug)
    return GenericResponse(
        status="ok",
        message=f"Profilo '{payload.nome}' creato. Consegna il codice di recupero al membro: non sarà più visibile.",
        data={"slug": slug, "codice_recupero": codice_recupero},
    )


@app.post("/profili/{slug}/recupero", response_model=GenericResponse)
@limiter.limit("10/minute")
def genera_codice_recupero(
    request: Request,
    slug: str,
    slug_autenticato: str = Depends(get_current_profile),
) -> GenericResponse:
    """Genera un nuovo codice di recupero monouso (solo amministratore).

    Il codice in chiaro viene restituito una sola volta: nel database resta
    solo l'hash bcrypt. Un codice precedente smette di funzionare.
    """
    if slug_autenticato != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo il profilo amministratore può generare codici di recupero.",
        )
    target = normalize_slug(slug)
    profilo = fetch_profiles().get(target)
    if not profilo:
        return GenericResponse(status="error", message="Profilo non trovato.")

    codice = generate_recovery_code()
    upsert_profile(
        slug=target,
        nome=str(profilo.get("nome") or target),
        lingua_madre=str(profilo.get("lingua_madre") or "Italiano"),
        livello_italiano=str(profilo.get("livello_italiano") or "B1"),
        recovery_hash=hash_pin(normalize_recovery_code(codice)),
    )
    ip, device = _request_context(request)
    auth_guard.record_event(target, "ok", "recupero_generato", ip, device)
    log.info("Codice di recupero rigenerato per %s da %s", target, slug_autenticato)
    return GenericResponse(
        status="ok",
        message="Nuovo codice di recupero. Scrivilo subito: non sarà più visibile.",
        data={"codice_recupero": codice},
    )


@app.delete("/profili/{slug}", response_model=GenericResponse)
@limiter.limit("20/minute")
def elimina_profilo(
    request: Request,
    slug: str,
    slug_autenticato: str = Depends(get_current_profile),
) -> GenericResponse:
    if slug_autenticato != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo il profilo amministratore può creare o eliminare profili.",
        )
    target = normalize_slug(slug)
    if target == slug_autenticato:
        return GenericResponse(status="error", message="Non puoi eliminare il profilo con cui sei connesso.")
    if target == "io":
        return GenericResponse(status="error", message="Il profilo amministratore non può essere eliminato.")
    if target not in fetch_profiles():
        return GenericResponse(status="error", message="Profilo non trovato.")
    db_delete_profile(target)
    return GenericResponse(status="ok", message=f"Profilo '{target}' eliminato.")


@app.post("/profili/{slug}/pin", response_model=GenericResponse)
@limiter.limit("10/minute")
def aggiorna_pin_profilo(
    request: Request,
    slug: str,
    payload: UpdatePinRequest,
    slug_autenticato: str = Depends(get_current_profile),
) -> GenericResponse:
    """Cambia il PIN di un profilo esistente (solo amministratore).

    Il PIN viene salvato solo come hash bcrypt. Prima della scrittura viene
    creato un backup di `_local_db`, così un cambio sbagliato è recuperabile.
    """
    if slug_autenticato != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo il profilo amministratore può cambiare i PIN.",
        )
    target = normalize_slug(slug)
    profilo = fetch_profiles().get(target)
    if not profilo:
        return GenericResponse(status="error", message="Profilo non trovato.")
    if is_production() and payload.pin in DEMO_PINS.values():
        return GenericResponse(
            status="error",
            message="PIN demo non ammesso in produzione: scegli un PIN personale.",
        )

    backup = backup_local_db()
    if is_mock_mode() and backup is None:
        log.warning("Backup pre-cambio PIN non riuscito: procedo comunque.")

    nuova_versione = db_pin_version(profilo) + 1
    upsert_profile(
        slug=target,
        nome=str(profilo.get("nome") or target),
        lingua_madre=str(profilo.get("lingua_madre") or "Italiano"),
        livello_italiano=str(profilo.get("livello_italiano") or "B1"),
        pin_hash=hash_pin(payload.pin),
        pin_version=nuova_versione,
    )
    log.info(
        "PIN aggiornato per %s da %s: sessioni precedenti revocate (v%d)",
        target,
        slug_autenticato,
        nuova_versione,
    )
    return GenericResponse(
        status="ok",
        message=(
            f"PIN aggiornato per '{target}'. Le sessioni già aperte di quel profilo "
            "sono state chiuse: serve accedere di nuovo con il nuovo PIN."
        ),
    )


# ---------------- Auth PIN ----------------
def _request_context(request: Request) -> tuple[str, str]:
    """IP e dispositivo leggibile per il registro accessi."""
    ip = auth_guard.client_ip(request)
    device = auth_guard.describe_device(request.headers.get("user-agent", ""))
    return ip, device


def _lock_message(retry_after: int) -> str:
    minuti = max(1, round(retry_after / 60))
    if retry_after < 60:
        return f"Troppi tentativi errati. Riprova tra {retry_after} secondi."
    return f"Troppi tentativi errati. Riprova tra {minuti} minuti."


@app.post("/auth/pin", response_model=PinAuthResponse)
@limiter.limit("5/minute")  # anti-bruteforce: 5 tentativi al minuto per IP
async def verifica_pin(request: Request, payload: PinAuthRequest) -> PinAuthResponse:
    slug_richiesto = normalize_slug(payload.profilo)
    ip, device = _request_context(request)

    stato = auth_guard.lockout_status(slug_richiesto)
    if stato["locked"]:
        auth_guard.record_event(slug_richiesto, "bloccato", "pin_bloccato", ip, device)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _lock_message(stato["retry_after"]))

    profilo = fetch_profiles().get(slug_richiesto)
    if not profilo:
        auth_guard.register_failure(slug_richiesto)
        auth_guard.record_event(slug_richiesto, "errore", "profilo_sconosciuto", ip, device)
        log.warning("Auth fallito: profilo sconosciuto %s", payload.profilo)
        return PinAuthResponse(auth=False, message="Profilo non valido.")

    pin_hash = profilo.get("pin_hash")
    if not pin_hash:
        log.error("Nessun pin_hash configurato per %s", profilo.get("slug"))
        return PinAuthResponse(auth=False, message="Profilo non configurato correttamente.")

    if is_production() and is_demo_pin_hash(pin_hash):
        log.error("Login bloccato: %s usa ancora un PIN demo in produzione", profilo.get("slug"))
        return PinAuthResponse(
            auth=False,
            message="PIN demo disabilitato in produzione: imposta un PIN personale.",
        )

    if not verify_pin(payload.pin, pin_hash):
        nuovo_stato = auth_guard.register_failure(profilo["slug"])
        auth_guard.record_event(profilo["slug"], "errore", "pin_errato", ip, device)
        log.info("PIN errato per %s (tentativo %d)", profilo["slug"], nuovo_stato["failures"])
        if nuovo_stato["locked"]:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                _lock_message(nuovo_stato["retry_after"]),
            )
        return PinAuthResponse(auth=False, message="PIN errato.")

    auth_guard.register_success(profilo["slug"])
    auth_guard.record_event(profilo["slug"], "ok", "pin", ip, device)
    token = create_access_token(profilo["slug"], pin_version=db_pin_version(profilo))
    log.info("Auth OK: %s", profilo["slug"])
    return PinAuthResponse(
        auth=True,
        profilo=profilo.get("nome"),
        slug=profilo["slug"],
        token=token,
        expires_in=token_ttl_seconds(),
        message="Autenticazione riuscita.",
    )


@app.post("/auth/recupero", response_model=PinAuthResponse)
@limiter.limit("5/minute")
async def recupera_accesso(request: Request, payload: RecoverRequest) -> PinAuthResponse:
    """Recupero senza amministratore: codice personale monouso + nuovo PIN."""
    slug_richiesto = normalize_slug(payload.profilo)
    ip, device = _request_context(request)

    stato = auth_guard.lockout_status(slug_richiesto)
    if stato["locked"]:
        auth_guard.record_event(slug_richiesto, "bloccato", "recupero_bloccato", ip, device)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _lock_message(stato["retry_after"]))

    messaggio_generico = "Codice di recupero non valido o già utilizzato."
    profilo = fetch_profiles().get(slug_richiesto)
    if not profilo or not profilo.get("recovery_hash"):
        auth_guard.register_failure(slug_richiesto)
        auth_guard.record_event(slug_richiesto, "errore", "recupero_senza_codice", ip, device)
        return PinAuthResponse(auth=False, message=messaggio_generico)

    if not is_valid_recovery_code(payload.codice) or not verify_recovery_code(
        payload.codice, str(profilo.get("recovery_hash"))
    ):
        nuovo_stato = auth_guard.register_failure(slug_richiesto)
        auth_guard.record_event(slug_richiesto, "errore", "recupero_errato", ip, device)
        if nuovo_stato["locked"]:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                _lock_message(nuovo_stato["retry_after"]),
            )
        return PinAuthResponse(auth=False, message=messaggio_generico)

    if is_production() and payload.nuovo_pin in DEMO_PINS.values():
        return PinAuthResponse(
            auth=False,
            message="PIN demo non ammesso in produzione: scegli un PIN personale.",
        )

    nuova_versione = db_pin_version(profilo) + 1
    upsert_profile(
        slug=slug_richiesto,
        nome=str(profilo.get("nome") or slug_richiesto),
        lingua_madre=str(profilo.get("lingua_madre") or "Italiano"),
        livello_italiano=str(profilo.get("livello_italiano") or "B1"),
        pin_hash=hash_pin(payload.nuovo_pin),
        pin_version=nuova_versione,
        recovery_hash="",
    )
    auth_guard.register_success(slug_richiesto)
    auth_guard.record_event(slug_richiesto, "ok", "recupero", ip, device)
    log.info("Accesso recuperato con codice personale: %s (v%d)", slug_richiesto, nuova_versione)
    return PinAuthResponse(
        auth=True,
        profilo=profilo.get("nome"),
        slug=slug_richiesto,
        token=create_access_token(slug_richiesto, pin_version=nuova_versione),
        expires_in=token_ttl_seconds(),
        message="PIN reimpostato. Il codice di recupero è stato consumato: generane uno nuovo.",
    )


@app.get("/auth/me", response_model=MeResponse)
@limiter.limit("60/minute")
def auth_me(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> MeResponse:
    profilo = fetch_profiles().get(slug, {})
    header = request.headers.get("Authorization", "")
    info = token_info(header[7:].strip()) if header else None
    return MeResponse(
        slug=slug,
        nome=profilo.get("nome", slug),
        lingua_madre=profilo.get("lingua_madre", "Italiano"),
        livello_italiano=profilo.get("livello_italiano", "B1"),
        expires_at=info[1] if info else None,
        tipo=str(profilo.get("tipo") or "adulto"),
        limiti=parental.limits_for(profilo),
    )


@app.get("/profili/{slug}/limiti", response_model=GenericResponse)
@limiter.limit("60/minute")
def leggi_limiti_profilo(
    request: Request,
    slug: str,
    slug_autenticato: str = Depends(get_current_profile),
) -> GenericResponse:
    """Limiti del profilo: il proprio, oppure quelli di un membro se sei io."""
    target = normalize_slug(slug)
    if target != slug_autenticato and slug_autenticato != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Puoi vedere solo i tuoi limiti.",
        )
    profilo = fetch_profiles().get(target)
    if not profilo:
        return GenericResponse(status="error", message="Profilo non trovato.")
    return GenericResponse(
        status="ok",
        data={
            "tipo": str(profilo.get("tipo") or "adulto"),
            "limiti": parental.limits_for(profilo),
        },
    )


@app.post("/profili/{slug}/limiti", response_model=GenericResponse)
@limiter.limit("20/minute")
def salva_limiti_profilo(
    request: Request,
    slug: str,
    payload: ParentalLimitsRequest,
    slug_autenticato: str = Depends(get_current_profile),
) -> GenericResponse:
    """Attiva/disattiva il controllo genitore per un profilo (solo amministratore)."""
    if slug_autenticato != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo il profilo amministratore può impostare i limiti.",
        )
    target = normalize_slug(slug)
    profilo = fetch_profiles().get(target)
    if not profilo:
        return GenericResponse(status="error", message="Profilo non trovato.")
    limiti = payload.model_dump()
    upsert_profile(
        slug=target,
        nome=str(profilo.get("nome") or target),
        lingua_madre=str(profilo.get("lingua_madre") or "Italiano"),
        livello_italiano=str(profilo.get("livello_italiano") or "B1"),
        tipo="bambino" if payload.attivo else "adulto",
        limiti=limiti,
    )
    ip, device = _request_context(request)
    auth_guard.record_event(target, "ok", "limiti_aggiornati", ip, device)
    log.info("Limiti controllo genitore aggiornati per %s da %s", target, slug_autenticato)
    return GenericResponse(
        status="ok",
        message=(
            f"Controllo genitore attivo per {profilo.get('nome') or target}: "
            f"{limiti['ora_inizio']}–{limiti['ora_fine']}"
            + (
                f", massimo {limiti['messaggi_giorno']} messaggi al giorno."
                if limiti["messaggi_giorno"]
                else ", messaggi illimitati."
            )
            if payload.attivo
            else f"Controllo genitore disattivato per {profilo.get('nome') or target}."
        ),
        data={"tipo": "bambino" if payload.attivo else "adulto", "limiti": limiti},
    )


@app.post("/auth/logout", response_model=GenericResponse)
@limiter.limit("30/minute")
def auth_logout(request: Request, slug: str = Depends(get_current_profile)) -> GenericResponse:
    """Chiude la sessione revocando il token corrente (denylist fino a scadenza)."""
    header = request.headers.get("Authorization", "")
    raw_token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    info = token_info(raw_token) if raw_token else None
    if info:
        revoke_token(sha256_text(raw_token), info[1])
    ip, device = _request_context(request)
    auth_guard.record_event(slug, "ok", "logout", ip, device)
    log.info("Logout profilo %s (token revocato)", slug)
    return GenericResponse(status="ok", message="Sessione chiusa su questo dispositivo.")


@app.post("/auth/logout-tutti", response_model=GenericResponse)
@limiter.limit("10/minute")
def auth_logout_tutti(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Chiude ogni sessione del profilo (token legati alla vecchia versione del PIN)."""
    profilo = fetch_profiles().get(slug)
    if not profilo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Profilo non più valido.")
    nuova_versione = db_pin_version(profilo) + 1
    upsert_profile(
        slug=slug,
        nome=str(profilo.get("nome") or slug),
        lingua_madre=str(profilo.get("lingua_madre") or "Italiano"),
        livello_italiano=str(profilo.get("livello_italiano") or "B1"),
        pin_version=nuova_versione,
    )
    ip, device = _request_context(request)
    auth_guard.record_event(slug, "ok", "logout_tutti", ip, device)
    log.info("Tutte le sessioni chiuse per %s (v%d)", slug, nuova_versione)
    return GenericResponse(
        status="ok",
        message="Tutte le sessioni sono state chiuse, compresa questa. Accedi di nuovo con il tuo PIN.",
    )


@app.get("/auth/accessi", response_model=GenericResponse)
@limiter.limit("30/minute")
def auth_accessi(
    request: Request,
    profilo: str = Query(default="", max_length=50),
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Registro accessi: il proprio, oppure quello di un membro se sei io."""
    target = normalize_slug(profilo) if profilo else slug
    if target != slug and slug != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Puoi vedere solo il registro dei tuoi accessi.",
        )
    return GenericResponse(status="ok", data=auth_guard.list_events(target, limit=50))


# ---------------- Privacy ----------------
@app.get("/privacy/informativa", response_model=GenericResponse)
@limiter.limit("60/minute")
def privacy_informativa(request: Request) -> GenericResponse:
    """Informativa privacy in italiano semplice (leggibile senza login)."""
    return GenericResponse(status="ok", data=privacy.policy_payload())


@app.get("/privacy/dati")
@limiter.limit("5/minute")
def privacy_esporta_dati(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> JSONResponse:
    """Esporta in JSON tutti i dati del profilo autenticato (diritto di accesso)."""
    esportazione = privacy.build_export(slug)
    auth_guard.record_event(slug, "ok", "esportazione_dati", *_request_context(request))
    log.info("Esportazione dati per %s", slug)
    filename = f"atlas-{slug}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    return JSONResponse(
        content=esportazione,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.delete("/privacy/profilo", response_model=GenericResponse)
@limiter.limit("5/minute")
def privacy_elimina_profilo(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Cancella il proprio profilo e i dati personali (diritto all'oblio)."""
    if slug == "io":
        return GenericResponse(
            status="error",
            message=(
                "Il profilo amministratore non può cancellarsi da solo: serve un "
                "altro amministratore che gestisca la famiglia."
            ),
        )
    esito = privacy.delete_profile(slug)
    log.info("Profilo %s cancellato dall'utente", slug)
    return GenericResponse(
        status="ok" if esito["profilo_eliminato"] else "error",
        message=(
            "Profilo e dati personali cancellati."
            if esito["profilo_eliminato"]
            else "Cancellazione non riuscita: riprova o contatta l'amministratore."
        ),
        data=esito,
    )


# ---------------- Chat ----------------
@app.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    slug: str = Depends(get_current_profile),
) -> ChatResponse:
    started = time.perf_counter()
    profilo = fetch_profiles().get(slug)
    if profilo is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profilo inesistente.")

    # Controllo genitore: orari e limite giornaliero applicati dal server.
    consentito, motivo = parental.check(profilo)
    if not consentito:
        ip, device = _request_context(request)
        auth_guard.record_event(slug, "errore", "limite_genitore", ip, device)
        raise HTTPException(status.HTTP_403_FORBIDDEN, motivo)

    immagine: tuple[bytes, str] | None = None
    if payload.immagine_base64:
        mime = (payload.immagine_mime_type or "image/jpeg").strip().lower()
        if mime not in {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Formato immagine non supportato (usa JPEG, PNG, WebP o HEIC).",
            )
        try:
            dati_immagine = base64.b64decode(payload.immagine_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Immagine base64 non valida.")
        if len(dati_immagine) < 64:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Immagine troppo piccola o vuota.")
        if len(dati_immagine) > 10 * 1024 * 1024:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "Foto troppo grande (max 10 MB). Scegline una più piccola.",
            )
        immagine = (dati_immagine, mime)

    memoria = get_user_memory(profile_slug=slug, limit=10)
    save_message(profile_slug=slug, role="user", content=payload.msg)
    # Il browser usa il profilo corrente per isolare cookie/pagine; il modello
    # gira in un thread per non bloccare l'event loop durante navigazioni lunghe.
    profilo_browser = browser_profile.set(slug)
    profilo_tool = current_profile.set(slug)
    try:
        risposta = await run_in_threadpool(
            ai_router.chiedi,
            prompt=payload.msg,
            profilo_utente=profilo,
            memoria=memoria,
            immagine=immagine,
        )
    finally:
        current_profile.reset(profilo_tool)
        browser_profile.reset(profilo_browser)
    save_message(profile_slug=slug, role="ai", content=str(risposta))
    parental.register_message(slug)

    if immagine:
        log.info("Chat con foto per %s: %d KB (%s)", slug, len(immagine[0]) // 1024, immagine[1])
    return ChatResponse(
        reply=str(risposta),
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
    )


@app.get("/chat/cronologia", response_model=GenericResponse)
@limiter.limit("60/minute")
def chat_cronologia(
    request: Request,
    q: str = Query(default="", max_length=200),
    limite: int = Query(default=50, ge=1, le=200),
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Cronologia della chat sincronizzata (stessa per tutti i dispositivi).

    `q` cerca nel testo; senza `q` restituisce gli ultimi `limite` messaggi.
    """
    righe = get_chat_history(slug, limit=limite, query=q)
    return GenericResponse(
        status="ok",
        data=[
            {
                "ruolo": row.get("role"),
                "testo": row.get("content"),
                "quando": row.get("created_at"),
            }
            for row in righe
        ],
        message=(
            f"{len(righe)} messaggi trovati per '{q.strip()}'."
            if q.strip()
            else None
        ),
    )


@app.post("/chat/trascrivi", response_model=TranscriptionResponse)
@limiter.limit("20/minute")
async def trascrivi_audio(
    request: Request,
    payload: TranscriptionRequest,
    slug: str = Depends(get_current_profile),
) -> TranscriptionResponse:
    """Trascrive un messaggio vocale (base64) usando Gemini."""
    mime = payload.mime_type.strip().lower()
    if not mime.startswith("audio/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Formato audio non supportato.")
    try:
        audio = base64.b64decode(payload.audio_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audio base64 non valido.")
    if len(audio) < 512:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audio troppo corto.")
    if len(audio) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio troppo grande (max 10 MB).")

    testo = ai_router.trascrivi_audio(audio, mime_type=mime)
    if not testo:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Trascrizione non disponibile: verifica le chiavi Gemini nel backend.",
        )
    log.info("Trascrizione per %s: %d caratteri", slug, len(testo))
    return TranscriptionResponse(testo=testo)


# ---------------- Dashboard ----------------
@app.get("/dashboard", response_model=GenericResponse)
@limiter.limit("60/minute")
def dashboard(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    return GenericResponse(status="ok", data=get_dashboard(slug))


# ---------------- Todos / Lista spesa ----------------
@app.get("/todos", response_model=GenericResponse)
@limiter.limit("60/minute")
def lista_todos(
    request: Request,
    filtro: str = Query(default=""),
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    only_pending = filtro.lower() in ("da_fare", "pending", "attivi", "da fare")
    todos = get_todos(only_pending=only_pending)
    simplified = [
        {
            "id": todo.get("id"),
            "task": todo.get("task_text") or todo.get("task"),
            "assegnato_a": todo.get("assegnato_a", "Tutti"),
            "done": bool(todo.get("is_completed", todo.get("done", False))),
            "created": todo.get("created_at") or todo.get("created"),
        }
        for todo in todos
    ]
    return GenericResponse(status="ok", data=simplified)


@app.post("/todos", response_model=GenericResponse)
@limiter.limit("30/minute")
def aggiungi_todo(
    request: Request,
    payload: AddTodoRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    esito = add_todo(task=payload.task.strip(), created_by_slug=slug, assegnato_a=payload.assegnato_a)
    return GenericResponse(
        status="ok",
        message=esito if isinstance(esito, str) and esito != "ok" else "Todo aggiunto.",
    )


@app.post("/todos/{numero}/completa", response_model=GenericResponse)
@limiter.limit("60/minute")
def completa_todo(
    request: Request,
    numero: int,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    if complete_todo_by_index(numero):
        return GenericResponse(status="ok", message=f"Todo {numero} completato.")
    return GenericResponse(status="error", message="Numero task non valido.")


@app.delete("/todos/{numero}", response_model=GenericResponse)
@limiter.limit("30/minute")
def elimina_todo(
    request: Request,
    numero: int,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    if delete_todo_by_index(numero):
        return GenericResponse(status="ok", message=f"Task {numero} eliminato.")
    return GenericResponse(status="error", message="Numero task non valido.")


# ---------------- Promemoria personali ----------------
def _reminder_payload(row: dict, pending_tasks: list[str] | None = None) -> dict:
    remind_at = str(row.get("remind_at") or "")
    include_todos = bool(row.get("include_todos", True))
    return {
        "id": str(row.get("id") or ""),
        "message": str(row.get("message") or "Promemoria"),
        "remind_at": remind_at,
        "include_todos": include_todos,
        "status": str(row.get("status") or "pending"),
        "local_scheduled": bool(row.get("local_scheduled_at")),
        "lista": (pending_tasks or []) if include_todos else [],
    }


@app.get("/promemoria", response_model=GenericResponse)
@limiter.limit("60/minute")
def lista_promemoria(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    rows = get_reminders(profile_slug=slug, only_pending=True)
    pending_tasks = [
        str(todo.get("task_text") or todo.get("task") or "").strip()
        for todo in get_todos(only_pending=True)
        if (todo.get("task_text") or todo.get("task"))
    ]
    return GenericResponse(status="ok", data=[_reminder_payload(row, pending_tasks) for row in rows])


@app.delete("/promemoria/{reminder_id}", response_model=GenericResponse)
@limiter.limit("30/minute")
def annulla_promemoria_endpoint(
    request: Request,
    reminder_id: str,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    if cancel_reminder(reminder_id, slug):
        return GenericResponse(status="ok", message="Promemoria annullato.")
    return GenericResponse(status="error", message="Promemoria non trovato o già annullato.")


@app.post("/promemoria/{reminder_id}/programmato", response_model=GenericResponse)
@limiter.limit("60/minute")
def conferma_promemoria_locale(
    request: Request,
    reminder_id: str,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    if mark_reminder_local_scheduled(reminder_id, slug):
        return GenericResponse(status="ok", message="Notifica locale registrata.")
    return GenericResponse(status="error", message="Promemoria non trovato.")


# ---------------- Budget / Spese ----------------
@app.get("/budget", response_model=GenericResponse)
@limiter.limit("60/minute")
def budget(request: Request, slug: str = Depends(get_current_profile)) -> GenericResponse:
    return GenericResponse(status="ok", data=get_budget_summary())


@app.post("/budget/spesa", response_model=GenericResponse)
@limiter.limit("30/minute")
def aggiungi_spesa(
    request: Request,
    payload: AddSpesaRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    esito = add_spesa(
        importo=float(payload.importo),
        categoria=payload.categoria.strip(),
        descrizione=payload.descrizione.strip(),
        slug=slug,
    )
    return GenericResponse(
        status="ok",
        message=esito if isinstance(esito, str) and esito != "ok" else "Spesa registrata.",
    )


# ---------------- Report budget ----------------
@app.get("/budget/report", response_model=GenericResponse)
@limiter.limit("60/minute")
def budget_report_endpoint(
    request: Request,
    mese: str = Query(default="", max_length=7),
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Report mensile: totale, confronto col mese scorso, soglie e sforamenti."""
    return GenericResponse(status="ok", data=budget_report.monthly_report(mese or None))


@app.post("/budget/limiti", response_model=GenericResponse)
@limiter.limit("20/minute")
def budget_limiti(
    request: Request,
    payload: BudgetLimitsRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Salva le soglie mensili per categoria (usato dagli avvisi di sforamento)."""
    if slug != "io":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo l'amministratore può impostare i limiti di spesa.",
        )
    salvate = budget_report.save_limits(payload.limiti)
    return GenericResponse(
        status="ok",
        message=(
            f"Limiti salvati per {len(salvate)} categorie."
            if salvate
            else "Nessun limite valido: inserisci importi maggiori di zero."
        ),
        data=salvate,
    )


# ---------------- Documenti PDF ----------------
@app.post("/documenti/pdf", response_model=GenericResponse)
@limiter.limit("10/minute")
def genera_documento_pdf(
    request: Request,
    payload: PdfRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Genera un PDF A4 reale e lo restituisce in base64 per il download/share."""
    try:
        pdf = build_pdf(payload.titolo, payload.contenuto)
    except ValueError as exc:
        return GenericResponse(status="error", message=str(exc))
    filename = f"ATLAS-{slug}-{int(time.time())}.pdf"
    log.info("PDF generato da %s: %s (%d byte)", slug, filename, len(pdf))
    return GenericResponse(
        status="ok",
        message="PDF generato.",
        data={
            "filename": filename,
            "mime_type": "application/pdf",
            "size": len(pdf),
            "base64": base64.b64encode(pdf).decode("ascii"),
        },
    )


# ---------------- Notifiche push ----------------
@app.post("/notifiche/registra", response_model=GenericResponse)
@limiter.limit("30/minute")
def registra_notifiche(
    request: Request,
    payload: PushRegisterRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    token = payload.token.strip()
    valid = token.startswith(("ExponentPushToken[", "ExpoPushToken[")) or len(token) > 40
    if not valid:
        return GenericResponse(status="error", message="Token push non valido.")
    device_info = " ".join(part for part in (payload.device.strip(), payload.platform.strip()) if part)
    ok = save_push_token(slug, token, device_info=device_info, platform=payload.platform)
    return GenericResponse(
        status="ok" if ok else "error",
        message="Notifiche attivate su questo dispositivo." if ok else "Salvataggio token fallito.",
    )


@app.delete("/notifiche/registra", response_model=GenericResponse)
@limiter.limit("30/minute")
def elimina_notifica(
    request: Request,
    token: str = Query(..., min_length=8, max_length=255),
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    deactivate_push_token(token)
    return GenericResponse(status="ok", message="Notifiche disattivate su questo dispositivo.")


@app.post("/notifiche/test", response_model=GenericResponse)
@limiter.limit("10/minute")
def test_notifica(
    request: Request,
    payload: PushTestRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    inviati = invia_a_profilo(slug, payload.titolo, payload.messaggio, {"tipo": "test"})
    if inviati <= 0:
        return GenericResponse(
            status="error",
            message="Nessun dispositivo registrato: attiva le notifiche nell'app e riprova.",
        )
    return GenericResponse(status="ok", message=f"Notifica inviata a {inviati} dispositivo/i.")


@app.get("/notifiche/dispositivi", response_model=GenericResponse)
@limiter.limit("30/minute")
def dispositivi_notifiche(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    rows = get_push_tokens(slug)
    return GenericResponse(
        status="ok",
        data=[{"device": row.get("device_info", ""), "platform": row.get("platform", "")} for row in rows],
    )


# ---------------- Impostazioni ----------------
@app.get("/impostazioni", response_model=GenericResponse)
@limiter.limit("60/minute")
def leggi_impostazioni(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    return GenericResponse(status="ok", data=get_settings())


@app.post("/impostazioni", response_model=GenericResponse)
@limiter.limit("30/minute")
def salva_impostazioni(
    request: Request,
    payload: SettingsUpdateRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    patch: dict[str, Any] = {}
    for section in ("automazioni", "notifiche", "soglie"):
        value = getattr(payload, section)
        if value:
            patch[section] = value
    if not patch:
        return GenericResponse(status="error", message="Nessuna impostazione da salvare.")
    updated = update_settings(patch)
    log.info("Impostazioni aggiornate da %s: %s", slug, list(patch))
    return GenericResponse(status="ok", message="Impostazioni salvate.", data=updated)


@app.get("/automazioni", response_model=GenericResponse)
@limiter.limit("60/minute")
def elenca_automazioni(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    return GenericResponse(status="ok", data=get_jobs())


# ---------------- Italiano ----------------
@app.get("/italiano/lezione", response_model=GenericResponse)
@limiter.limit("60/minute")
def italiano_lezione(
    request: Request,
    livello: str = Query(default="B1"),
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    livello_norm = normalizza_livello(livello)
    lezione = lezione_del_giorno(livello_norm)
    progresso = get_italian_progress(slug)
    return GenericResponse(status="ok", data={"lezione": lezione, "progresso": progresso})


@app.get("/italiano/quiz", response_model=GenericResponse)
@limiter.limit("60/minute")
def italiano_quiz(
    request: Request,
    livello: str = Query(default="B1"),
    n: int = Query(default=5, ge=1, le=10),
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    domande = [
        {
            "id": domanda["id"],
            "livello": domanda["livello"],
            "domanda": domanda["domanda"],
            "opzioni": domanda["opzioni"],
        }
        for domanda in quiz_per_livello(livello, n)
    ]
    return GenericResponse(
        status="ok",
        data={"domande": domande, "progresso": get_italian_progress(slug)},
    )


@app.post("/italiano/quiz/valuta", response_model=GenericResponse)
@limiter.limit("30/minute")
def italiano_valuta(
    request: Request,
    payload: QuizSubmitRequest,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    if not payload.risposte:
        return GenericResponse(status="error", message="Nessuna risposta inviata.")
    esito = valuta_quiz([risposta.model_dump() for risposta in payload.risposte])
    if esito["totale"] == 0:
        return GenericResponse(status="error", message="Risposte non valide.")
    add_italian_progress(slug, f"quiz-{payload.livello or 'B1'}", int(esito["punteggio"]))
    esito["progresso"] = get_italian_progress(slug)
    return GenericResponse(status="ok", data=esito)


@app.get("/italiano/progressi", response_model=GenericResponse)
@limiter.limit("60/minute")
def italiano_progressi(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    return GenericResponse(
        status="ok",
        data={
            "mio": get_italian_progress(slug),
            "classifica": get_italian_leaderboard(),
        },
    )


# ---------------- Integrazioni Google (Gmail + Calendar) ----------------
@app.get("/integrazioni/google/stato", response_model=GenericResponse)
@limiter.limit("60/minute")
def google_stato(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    from app.services import google_oauth

    return GenericResponse(status="ok", data=google_oauth.status())


@app.get("/integrazioni/google/url", response_model=GenericResponse)
@limiter.limit("30/minute")
def google_url(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    from app.services import google_oauth

    stato = google_oauth.status()
    if not stato["configurato"]:
        return GenericResponse(
            status="error",
            message=stato["istruzioni"],
            data={"configurato": False, "connesso": stato["connesso"]},
        )
    try:
        url = google_oauth.build_auth_url(str(request.base_url))
    except RuntimeError as exc:
        return GenericResponse(status="error", message=str(exc))
    return GenericResponse(status="ok", data={"url": url, "configurato": True})


@app.get("/integrazioni/google/callback")
def google_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
):
    from app.services import google_oauth

    if error or not code:
        return RedirectResponse(google_oauth.oauth_error_deeplink("annullato"))
    if not google_oauth.validate_state(state):
        log.warning("Callback Google con state non valido")
        return RedirectResponse(google_oauth.oauth_error_deeplink("state"))
    if not google_oauth.exchange_code(code, str(request.base_url)):
        return RedirectResponse(google_oauth.oauth_error_deeplink("scambio"))
    return RedirectResponse(google_oauth.oauth_success_deeplink())


@app.post("/integrazioni/google/disconnetti", response_model=GenericResponse)
@limiter.limit("20/minute")
def google_disconnetti(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    from app.services import google_oauth

    google_oauth.disconnect()
    return GenericResponse(status="ok", message="Account Google scollegato.")


@app.get("/integrazioni/gmail/bozza", response_model=GenericResponse)
@limiter.limit("60/minute")
def gmail_bozza(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Bozza email in attesa di conferma (mai inviata automaticamente)."""
    from app.tools.google_advanced import get_pending_draft

    draft = get_pending_draft()
    if not draft:
        return GenericResponse(status="ok", data=None)
    return GenericResponse(
        status="ok",
        data={
            "destinatario": draft.get("a", ""),
            "oggetto": draft.get("oggetto", ""),
            "corpo": draft.get("corpo", ""),
            "allegato": (draft.get("allegato") or {}).get("filename") if draft.get("allegato") else None,
            "creata": draft.get("creata", ""),
            "profilo": draft.get("profilo", ""),
        },
    )


@app.post("/integrazioni/gmail/bozza/invia", response_model=GenericResponse)
@limiter.limit("10/minute")
def gmail_invia_bozza(
    request: Request,
    payload: ConfermaInvioEmail,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Invia la bozza solo con `conferma: true` esplicito dall'app."""
    from app.tools.google_advanced import get_pending_draft, send_pending_draft

    if not get_pending_draft():
        return GenericResponse(status="error", message="Nessuna bozza in attesa di invio.")
    if payload.conferma is not True:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Serve una conferma esplicita: imposta conferma=true solo dopo aver letto la bozza.",
        )
    ok, message = send_pending_draft()
    log.info("Invio bozza Gmail richiesto da %s: %s", slug, "ok" if ok else "fallito")
    return GenericResponse(status="ok" if ok else "error", message=message)


@app.delete("/integrazioni/gmail/bozza", response_model=GenericResponse)
@limiter.limit("30/minute")
def gmail_scarta_bozza(
    request: Request,
    slug: str = Depends(get_current_profile),
) -> GenericResponse:
    """Scarta la bozza senza inviare nulla."""
    from app.tools.google_advanced import cancel_pending_draft

    scartata = cancel_pending_draft()
    return GenericResponse(
        status="ok" if scartata else "error",
        message="Bozza scartata." if scartata else "Nessuna bozza da scartare.",
    )


# ---------------- Gestione errori ----------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors() or []
    first = errors[0] if errors else {}
    field = ".".join(str(part) for part in first.get("loc", [])[1:]) or "richiesta"
    message = f"{field}: {first.get('msg', 'valore non valido')}"
    log.warning("Validazione fallita su %s: %s", request.url.path, message)
    return JSONResponse(status_code=422, content={"status": "error", "message": message})


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
        content={"status": "error", "message": "Errore interno del server. I dettagli sono nel log."},
    )
