"""
Modulo italiano (compatibilità).

⚠️ DEPRECATO: i contenuti reali (lezioni + quiz + valutazione) vivono in
`app.tools.italian`. Questo file resta solo come re-export per eventuali
import storici: non contiene più quiz inventati né funzioni placeholder.
"""
from __future__ import annotations

from typing import Any

from app.tools.italian import (
    LIVELLI,
    lezione_del_giorno,
    normalizza_livello,
    quiz_per_livello,
    valuta_quiz,
)

__all__ = [
    "LIVELLI",
    "generate_italian_quiz",
    "lezione_del_giorno",
    "normalizza_livello",
    "valuta_quiz",
]


def generate_italian_quiz(livello: str = "B1") -> dict[str, Any]:
    """Ritorna la prima domanda del quiz del giorno per il livello indicato."""
    domande = quiz_per_livello(livello, 1)
    if not domande:
        return {"question": "", "options": [], "answer": None}
    domanda = domande[0]
    return {
        "question": domanda["domanda"],
        "options": domanda["opzioni"],
        "answer": domanda["opzioni"][domanda["risposta"]],
        "id": domanda["id"],
        "level": domanda["livello"],
    }
