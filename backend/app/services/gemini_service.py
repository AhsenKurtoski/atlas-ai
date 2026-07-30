"""
Servizio Gemini LEGACY per retrocompatibilità.

⚠️  DEPRECATO: Usa app.ai_router.GeminiRouter (ai_router) che è la versione
attiva, più robusta e con supporto completo a tutti gli ATLAS_TOOLS.
Questa classe esiste solo per eventuali moduli terzi che l'hanno importata
direttamente in passato.
"""
from __future__ import annotations

import os

from app.core.logging_config import get_logger

log = get_logger(__name__)

log.warning(
    "services.gemini_service è deprecato. Usa app.ai_router.ai_router.chiedi() "
    "per la nuova implementazione."
)


class GeminiRotator:
    """Implementazione legacy. Inoltra a GeminiRouter se disponibile."""

    def __init__(self):
        self.keys = [
            os.getenv("GEMINI_KEY_1", ""),
            os.getenv("GEMINI_KEY_2", ""),
            os.getenv("GEMINI_KEY_3", ""),
        ]
        self.keys = [k for k in self.keys if k]
        self.current_key_idx = 0

    def rotate_key(self) -> bool:
        if not self.keys:
            return False
        self.current_key_idx = (self.current_key_idx + 1) % len(self.keys)
        return True

    def generate_content(self, messages: list) -> str:
        """Legacy entrypoint. Inoltra la richiesta al nuovo router quando possibile."""
        last = str(messages[-1]) if messages else ""
        try:
            from app.ai_router import ai_router

            return ai_router.chiedi(last, profilo_utente={"nome": "Utente Legacy", "lingua_madre": "Italiano", "livello_italiano": "C1"})
        except Exception as exc:
            log.exception("Fallito inoltro legacy: %s", exc)
            return f"Servizio AI non disponibile: {exc}"


gemini_rotator = GeminiRotator()
