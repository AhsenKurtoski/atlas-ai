import os

# Nota: per un'app in produzione qui si userebbero google-auth e google-api-python-client
# ricevendo l'access_token dell'utente specifico dal DB tramite Supabase

def get_calendar_events(user_id: str, date: str) -> str:
    """Estrae gli eventi del calendario Google per un utente in una certa data."""
    # Placeholder per la logica OAuth reale
    return f"Eventi per il {date}: Nessun evento trovato nel mock database."

def create_calendar_event(user_id: str, title: str, date: str, time: str) -> str:
    """Crea un evento nel calendario Google dell'utente."""
    return f"Evento '{title}' creato con successo per il {date} alle {time}."

def prepare_email_draft(user_id: str, to: str, subject: str, body: str) -> str:
    """Prepara una bozza di email. L'invio reale richiede conferma UI."""
    return f"Bozza email preparata per {to} con oggetto: {subject}. ATTESA CONFERMA DA FRONTEND."
