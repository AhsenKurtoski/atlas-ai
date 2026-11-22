"""
Modelli di dati (Pydantic v2) per richieste e risposte dell'API ATLAS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import is_safe_numeric_pin


# ---------------- Auth ----------------
class PinAuthRequest(BaseModel):
    profilo: str = Field(..., min_length=1, max_length=50, description="Slug del profilo, es. 'mamma'")
    pin: str = Field(..., min_length=4, max_length=8, description="PIN numerico del profilo")

    @field_validator("pin")
    @classmethod
    def _pin_must_be_digits(cls, value: str) -> str:
        if not is_safe_numeric_pin(value):
            raise ValueError("Il PIN deve contenere solo cifre (4-8)")
        return value


class PinAuthResponse(BaseModel):
    auth: bool
    profilo: Optional[str] = None
    slug: Optional[str] = None
    token: Optional[str] = None
    expires_in: Optional[int] = None
    message: Optional[str] = None


class UpdatePinRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, description="Nuovo PIN numerico del profilo")

    @field_validator("pin")
    @classmethod
    def _pin_must_be_digits(cls, value: str) -> str:
        if not is_safe_numeric_pin(value):
            raise ValueError("Il PIN deve contenere solo cifre (4-8)")
        return value


class RecoverRequest(BaseModel):
    """Recupero accesso con codice personale + scelta di un nuovo PIN."""

    profilo: str = Field(..., min_length=1, max_length=50)
    codice: str = Field(..., min_length=8, max_length=40, description="Codice di recupero personale")
    nuovo_pin: str = Field(..., min_length=4, max_length=8)

    @field_validator("nuovo_pin")
    @classmethod
    def _pin_must_be_digits(cls, value: str) -> str:
        if not is_safe_numeric_pin(value):
            raise ValueError("Il PIN deve contenere solo cifre (4-8)")
        return value


class MeResponse(BaseModel):
    slug: str
    nome: str
    lingua_madre: str
    livello_italiano: str
    expires_at: Optional[int] = None
    tipo: str = "adulto"
    limiti: dict[str, Any] = {}


class ParentalLimitsRequest(BaseModel):
    """Limiti del profilo bambino (orari, messaggi al giorno, contenuti)."""

    attivo: bool = True
    ora_inizio: str = Field(default="07:00", max_length=5)
    ora_fine: str = Field(default="21:00", max_length=5)
    messaggi_giorno: int = Field(default=0, ge=0, le=500)
    contenuti_bambino: bool = True

    @field_validator("ora_inizio", "ora_fine")
    @classmethod
    def _valid_time(cls, value: str) -> str:
        parts = value.strip().split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("Usa il formato HH:MM")
        ore, minuti = int(parts[0]), int(parts[1])
        if not (0 <= ore <= 23 and 0 <= minuti <= 59):
            raise ValueError("Orario non valido")
        return f"{ore:02d}:{minuti:02d}"


class BudgetLimitsRequest(BaseModel):
    limiti: dict[str, float] = Field(default_factory=dict)


# ---------------- Chat ----------------
class ChatRequest(BaseModel):
    msg: str = Field(..., min_length=1, max_length=8000, description="Messaggio dell'utente")
    profilo: Optional[str] = Field(default=None, max_length=50, description="Ignorato: il profilo arriva dal token")
    token: Optional[str] = Field(default=None, description="Deprecato: usa l'header Authorization")
    immagine_base64: Optional[str] = Field(
        default=None,
        max_length=15_000_000,
        description="Foto dalla galleria in base64 (max ~10 MB reali)",
    )
    immagine_mime_type: Optional[str] = Field(default=None, max_length=80)


class ChatResponse(BaseModel):
    reply: str
    function_called: Optional[str] = None
    latency_ms: Optional[float] = None


class TranscriptionRequest(BaseModel):
    audio_base64: str = Field(..., min_length=32, max_length=14_000_000)
    mime_type: str = Field(default="audio/mp4", max_length=80)


class TranscriptionResponse(BaseModel):
    testo: str
    disponibile: bool = True


# ---------------- Profili ----------------
class ProfileSummary(BaseModel):
    nome: str
    livello_italiano: str
    lingua_madre: str = "Italiano"
    tipo: str = "adulto"


class CreateProfileRequest(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    pin: str = Field(..., min_length=4, max_length=8)
    slug: Optional[str] = Field(default=None, max_length=50)
    lingua_madre: str = Field(default="Italiano", max_length=50)
    livello_italiano: str = Field(default="B1", max_length=20)

    @field_validator("pin")
    @classmethod
    def _pin_must_be_digits(cls, value: str) -> str:
        if not is_safe_numeric_pin(value):
            raise ValueError("Il PIN deve contenere solo cifre (4-8)")
        return value


# ---------------- Todo / Lista spesa ----------------
class AddTodoRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=500)
    assegnato_a: str = Field(default="Tutti", max_length=100)
    slug: Optional[str] = Field(default=None, max_length=50, description="Ignorato: arriva dal token")


class TodoItem(BaseModel):
    id: Optional[str] = None
    task: str
    assegnato_a: str = "Tutti"
    done: bool = False
    created: Optional[str] = None


# ---------------- Budget ----------------
class AddSpesaRequest(BaseModel):
    importo: float = Field(..., gt=0, lt=10_000_000)
    categoria: str = Field(..., min_length=1, max_length=50)
    descrizione: str = Field(default="", max_length=500)
    slug: Optional[str] = Field(default=None, max_length=50, description="Ignorato: arriva dal token")


class BudgetRow(BaseModel):
    categoria: str
    importo: float
    percentuale: Optional[float] = None


class BudgetRiepilogo(BaseModel):
    totale: float
    dettaglio: list[BudgetRow] = []


# ---------------- Documenti PDF ----------------
class PdfRequest(BaseModel):
    titolo: str = Field(..., min_length=1, max_length=120)
    contenuto: str = Field(..., min_length=1, max_length=20_000)

    @field_validator("titolo", "contenuto")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Il campo non può essere vuoto")
        return value.strip()


# ---------------- Notifiche ----------------
class PushRegisterRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=255)
    device: str = Field(default="", max_length=200)
    platform: str = Field(default="", max_length=20)


class PushTestRequest(BaseModel):
    titolo: str = Field(default="Test ATLAS", max_length=80)
    messaggio: str = Field(default="Le notifiche funzionano! 🎉", max_length=300)


# ---------------- Impostazioni ----------------
class SettingsUpdateRequest(BaseModel):
    automazioni: Optional[dict[str, bool]] = None
    notifiche: Optional[dict[str, bool]] = None
    soglie: Optional[dict[str, float]] = None


# ---------------- Italiano ----------------
class QuizAnswer(BaseModel):
    id: str = Field(..., max_length=40)
    scelta: int = Field(..., ge=0, le=3)


class QuizSubmitRequest(BaseModel):
    risposte: list[QuizAnswer] = Field(..., max_length=20)
    livello: Optional[str] = Field(default="B1", max_length=5)


# ---------------- Generiche ----------------
class GenericResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Any = None

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok", "message": "fatto"}})


class ConfermaInvioEmail(BaseModel):
    """Conferma esplicita dell'utente prima di inviare una bozza Gmail."""

    conferma: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    profili: int
    automazioni: int
    scheduler_attivo: bool = False
    ambiente: str
    versione: str = "3.4.0"
    db_mode: str = "locale"
    notifiche: str = "expo"
    llm: bool = False
    uptime_iso: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
