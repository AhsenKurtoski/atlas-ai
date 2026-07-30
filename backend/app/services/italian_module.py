import random

def generate_italian_quiz() -> dict:
    """Genera un quiz di italiano per i genitori (Macedone -> Italiano)."""
    quizzes = [
        {"question": "Come si dice 'Buon appetito' in Macedone?", "options": ["Dobar apetit", "Zdravo", "Blagodaram"], "answer": "Dobar apetit"},
        {"question": "Cosa significa 'Fermata dell'autobus'?", "options": ["Avtobuska postojka", "Bolnica", "Banka"], "answer": "Avtobuska postojka"}
    ]
    return random.choice(quizzes)

def grammar_correction(text: str) -> str:
    """Funzione di supporto chiamata dall'AI se il genitore chiede esplicitamente di essere corretto."""
    return f"Testo analizzato per correzioni: {text}. Chiedere all'LLM di restituire le correzioni."
