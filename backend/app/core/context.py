"""Contesto della richiesta corrente condiviso dai tool.

Il profilo NON deve mai arrivare come argomento dal modello: viene impostato
dall'endpoint autenticato e letto dai tool che salvano dati personali.
"""
from contextvars import ContextVar

current_profile: ContextVar[str] = ContextVar("atlas_current_profile", default="io")

__all__ = ["current_profile"]