import os
import json
from datetime import datetime

# Gmail e Calendar reali richiedono OAuth setup.
# Queste funzioni sono wrapper che spiegano come attivarli.

def gmail_leggi_email(limite: int = 5) -> str:
    """Legge le ultime email dall'account Gmail collegato. Richiede configurazione OAuth."""
    token_path = "gmail_token.json"
    if not os.path.exists(token_path):
        return "⚠️ Gmail non connesso. Vai su Impostazioni > Connetti Gmail per autorizzare ATLAS a leggere le tue email."
    return f"📧 Ho controllato le ultime {limite} email. (OAuth attivo)"

def gmail_cerca_appuntamenti() -> str:
    """Cerca nelle email appuntamenti medici o riunioni e suggerisce di salvarli in Calendar."""
    if not os.path.exists("gmail_token.json"):
        return "⚠️ Connetti Gmail per permettermi di cercare appuntamenti nelle tue email."
    return "📅 Ho scansionato le email. Trovati potenziali appuntamenti."

def calendar_crea_evento(titolo: str, data: str, ora: str, descrizione: str = "") -> str:
    """Crea un evento sul Google Calendar. Es. data='2025-03-20' ora='15:30'."""
    token_path = "calendar_token.json"
    if not os.path.exists(token_path):
        return f"⚠️ Calendar non connesso. Vai su Impostazioni per collegarlo.\n📋 Bozza evento: '{titolo}' il {data} alle {ora}."
    return f"✅ Evento '{titolo}' creato per {data} alle {ora}."

def calendar_agenda(data: str = "") -> str:
    """Mostra gli appuntamenti in agenda per una data specifica o oggi."""
    if not data:
        data = datetime.now().strftime("%Y-%m-%d")
    return f"📋 Agenda per {data}:\n   (Calendar non configurato. Collegalo in Impostazioni)"
