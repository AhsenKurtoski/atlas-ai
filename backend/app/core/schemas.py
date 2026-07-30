"""
Modello di dati (Pydantic v2) per richieste e risposte dell'API ATLAS.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------- Auth ----------------
class PinAuthRequest(BaseModel):
    profilo: str = Field(..., min_length=1, max_length=50, description="Slug del profilo, es. 'mamma'")
    pin: str = Field(..., min_length=4, max_length=8, description="PIN numerico del profilo")

    @field_validator("pin")
    @classmethod
    def _pin_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("PIN deve essere numerico")
        return v


class PinAuthResponse(BaseModel):
    auth: bool
    profilo: Optional[str] = None
    token: Optional[str] = None
    message: Optional[str] = None


# ---------------- Chat ----------------
class ChatRequest(BaseModel):
    msg: str = Field(..., min_length=1, max_length=8000, description="Messaggio dell'utente")
    profilo: str = Field(..., min_length=1, max_length=50, description="Slug profilo che scrive il messaggio")
    token: Optional[str] = Field(default=None, description="Token di autenticazione rilasciato da /auth/pin")


class ChatResponse(BaseModel):
    reply: str
    function_called: Optional[str] = None
    latency_ms: Optional[float] = None


# ---------------- Profili ----------------
class ProfileSummary(BaseModel):
    nome: str
    livello_italiano: str


class ProfilesResponse(BaseModel):
    profili: dict[str, ProfileSummary]


# ---------------- Todo / Lista spesa ----------------
class AddTodoRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=500)
    assegnato_a: str = Field(default="Tutti", max_length=100)
    slug: str = Field(..., max_length=50, description="Profilo che aggiunge il todo")


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
    slug: str = Field(..., max_length=50, description="Profilo che registra la spesa")


class BudgetRow(BaseModel):
    categoria: str
    importo: float
    percentuale: Optional[float] = None


class BudgetRiepilogo(BaseModel):
    totale: float
    dettaglio: list[BudgetRow] = []


# ---------------- Generiche ----------------
class GenericResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Any = None

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok", "message": "fatto"}})


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    profili: int
    automazioni: int
    ambiente: str
    versione: str = "3.0.0"
    uptime_iso: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
