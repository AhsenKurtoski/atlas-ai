"""
Privacy: esportazione e cancellazione dei dati personali.

Ogni membro della famiglia può scaricare tutto ciò che l'app conserva su di lui
e cancellare il proprio profilo. Nessun dato viene inviato a terzi da questo
modulo: l'esportazione è un JSON restituito al richiedente autenticato.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core import auth_guard, database
from app.core.logging_config import get_logger

log = get_logger(__name__)

POLICY_VERSION = "1.0"
POLICY_UPDATED = "2026-11-19"

# Tempi di conservazione dichiarati all'utente (e applicati dai backup locali).
RETENTION: dict[str, str] = {
    "chat": "Fino alla cancellazione del profilo (o alla rimozione manuale).",
    "accessi": "90 giorni, poi vengono eliminati automaticamente dal registro.",
    "backup": "14 copie, una ogni 6 ore: circa 3 giorni di storico.",
    "spese_e_liste": "Finché il profilo famiglia esiste: sono dati condivisi.",
}

POLICY_SECTIONS: list[dict[str, str]] = [
    {
        "titolo": "Chi tratta i dati",
        "testo": (
            "ATLAS AI gira sul computer della famiglia. I dati non passano da un "
            "server nostro: restano nel database locale del PC (o nel progetto "
            "Supabase configurato dal proprietario)."
        ),
    },
    {
        "titolo": "Quali dati conserviamo",
        "testo": (
            "Nome, lingua e livello di italiano del profilo; PIN e codice di recupero "
            "solo come hash bcrypt (non sono leggibili nemmeno dall'amministratore); "
            "messaggi della chat, promemoria, spese e liste condivise; token delle "
            "notifiche; registro degli accessi (data, esito, IP e tipo di dispositivo)."
        ),
    },
    {
        "titolo": "Perché li conserviamo",
        "testo": (
            "Per far funzionare l'assistente (memoria della conversazione), per la "
            "sicurezza degli accessi e per i promemoria. Non c'è profilazione "
            "pubblicitaria e non vendiamo dati a nessuno."
        ),
    },
    {
        "titolo": "Servizi esterni",
        "testo": (
            "Se sono configurate le chiavi Gemini, il testo dei messaggi viene inviato "
            "a Google per generare la risposta. Se colleghi Google (Gmail/Calendar) o "
            "attivi le notifiche push, i dati necessari passano ai rispettivi servizi. "
            "Senza chiavi configurate l'app resta in locale e la chat non funziona."
        ),
    },
    {
        "titolo": "I tuoi diritti",
        "testo": (
            "Da Impostazioni → Privacy puoi scaricare tutti i tuoi dati in JSON e "
            "cancellare il tuo profilo. La cancellazione rimuove messaggi, promemoria, "
            "progressi, dispositivi e registro accessi; le liste condivise restano "
            "alla famiglia ma non sono più collegate a te. Il profilo amministratore "
            "non può cancellarsi da solo: deve prima nominare un altro amministratore."
        ),
    },
    {
        "titolo": "Sicurezza",
        "testo": (
            "PIN e codici di recupero sono salvati come hash bcrypt. Le sessioni usano "
            "token firmati con scadenza, blocco progressivo dopo troppi errori e "
            "blocco automatico dell'app dopo inattività. I backup del database sono "
            "cifrati (AES) con una chiave derivata dal segreto del server."
        ),
    },
]


def policy_payload() -> dict[str, Any]:
    return {
        "versione": POLICY_VERSION,
        "aggiornata": POLICY_UPDATED,
        "sezioni": POLICY_SECTIONS,
        "conservazione": RETENTION,
    }


def _public_profile(slug: str) -> dict[str, Any]:
    profilo = database.fetch_profiles().get(slug, {})
    return {
        "slug": slug,
        "nome": profilo.get("nome", ""),
        "lingua_madre": profilo.get("lingua_madre", ""),
        "livello_italiano": profilo.get("livello_italiano", ""),
        "pin_impostato": bool(profilo.get("pin_hash")),
        "codice_recupero_attivo": bool(profilo.get("recovery_hash")),
    }


def build_export(slug: str) -> dict[str, Any]:
    """Tutto ciò che riguarda un profilo, in un dizionario serializzabile."""
    rows = database.export_profile_rows(slug)
    dispositivi = [
        {
            "dispositivo": row.get("device_info", ""),
            "piattaforma": row.get("platform", ""),
            "attivo": bool(row.get("is_active", True)),
            # Il token push è una credenziale: si esporta solo che esiste.
            "token": "••••" if row.get("token") else "",
        }
        for row in rows.get("push_tokens", [])
    ]
    return {
        "esportato_il": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "informativa": {"versione": POLICY_VERSION, "aggiornata": POLICY_UPDATED},
        "profilo": _public_profile(slug),
        "messaggi": [
            {
                "ruolo": row.get("role"),
                "testo": row.get("content"),
                "quando": row.get("created_at"),
            }
            for row in rows.get("messages", [])
        ],
        "promemoria": [
            {
                "messaggio": row.get("message"),
                "quando": row.get("remind_at"),
                "stato": row.get("status"),
            }
            for row in rows.get("family_reminders", [])
        ],
        "progressi_italiano": rows.get("italian_progress", []),
        "dispositivi_notifiche": dispositivi,
        "spese_registrate": rows.get("family_expenses", []),
        "attivita_create": rows.get("family_todos", []),
        "accessi": auth_guard.list_events(slug, limit=500),
    }


def delete_profile(slug: str) -> dict[str, Any]:
    """Cancella i dati personali e il profilo. Non tocca il profilo `io`."""
    counts = database.delete_personal_data(slug)
    eventi = auth_guard.clear_events(slug)
    rimosso = database.delete_profile(slug)
    log.info("Profilo %s cancellato su richiesta (righe: %s, eventi: %d)", slug, counts, eventi)
    return {
        "profilo_eliminato": bool(rimosso),
        "righe_eliminate": counts,
        "eventi_accesso_eliminati": eventi,
    }
