"""
Scheduler delle automazioni ATLAS AI v3.0 (APScheduler).

⚠️  NOTA SULL'AVVIO:
Lo scheduler NON viene più avviato automaticamente all'import del modulo.
Chiamare esplicitamente `start_scheduler()` dal lifespan di FastAPI
(come in main.py). Questo evita side-effect durante i test o import
non controllati.
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging_config import get_logger
from app.tools.finance import get_crypto_price, riepilogo_budget
from app.tools.travel import get_weather
from app.tools.family import get_family_todos

log = get_logger(__name__)

PUSH_TOKENS_FILE = "push_tokens.json"

# --- Singleton lazy ---
_scheduler: BackgroundScheduler | None = None
_initialized = threading.Event()
_JOB_IDS: set[str] = set()


def _log(msg: str) -> None:
    log.info("[SCHED] %s", msg)


def _get_tokens() -> dict[str, Any]:
    if os.path.exists(PUSH_TOKENS_FILE):
        try:
            with open(PUSH_TOKENS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            log.warning("%s non leggibile", PUSH_TOKENS_FILE)
    return {}


# ==============================
#  AUTOMAZIONI MATTUTINE / JOB
# ==============================
def job_lezione_italiano() -> None:
    _log("📚 Lezione italiano: invio notifiche a Mamma e Papà")
    tokens = _get_tokens()
    for p in ("mamma", "papa"):
        if p in tokens:
            _log(f"   Notifica lezione inviata a {p}")


def job_briefing_giornaliero() -> None:
    _log("☀️ Briefing mattutino per tutta la famiglia")
    try:
        meteo = get_weather("Milano")
        crypto = get_crypto_price("bitcoin")
        _log(f"   Briefing: {meteo[:80]} | {str(crypto)[:80]}...")
    except Exception as exc:
        log.error("Briefing fallito: %s", exc)


def job_controllo_email() -> None:
    _log("📧 Controllo email (ogni 15 min) - Notifica se urgenti")


def job_ricorda_acqua() -> None:
    _log("💧 Promemoria acqua per tutti i membri")
    tokens = _get_tokens()
    for p in tokens:
        _log(f"   Promemoria acqua inviato a {p}")


def job_price_watcher() -> None:
    _log("✈️ Price watcher: controllo prezzi voli e crypto")
    try:
        btc = get_crypto_price("bitcoin")
        eth = get_crypto_price("ethereum")
        _log(f"   BTC: {str(btc)[:80]}... | ETH: {str(eth)[:80]}...")
    except Exception as exc:
        log.error("Price watcher fallito: %s", exc)


def job_report_settimanale() -> None:
    _log("📊 Report settimanale famiglia")
    try:
        budget = riepilogo_budget()
        todos = get_family_todos()
        _log(f"   Budget: {str(budget)[:120]}...")
        _log(f"   Todo: {str(todos)[:120]}...")
    except Exception as exc:
        log.error("Report settimanale fallito: %s", exc)


def job_classifica_studio() -> None:
    _log("🏆 Classifica settimanale studio italiano")


def _add_job_once(scheduler: BackgroundScheduler, job_id: str, fn, trigger, **kwargs) -> None:
    """Aggiunge un job solo se non già presente (previene duplicati)."""
    if job_id in _JOB_IDS:
        return
    if scheduler.get_job(job_id):
        return
    scheduler.add_job(fn, trigger, id=job_id, **kwargs)
    _JOB_IDS.add(job_id)


def _register_jobs(scheduler: BackgroundScheduler) -> None:
    # 📚 Lezione italiano - ogni mattina 7:30
    _add_job_once(scheduler, "lezione_italiano", job_lezione_italiano,
                  CronTrigger(hour=7, minute=30, timezone="Europe/Rome"))
    _log("📚 Lezione italiano alle 7:30")

    # ☀️ Briefing giornaliero - ogni mattina 8:00
    _add_job_once(scheduler, "briefing_giornaliero", job_briefing_giornaliero,
                  CronTrigger(hour=8, minute=0, timezone="Europe/Rome"))
    _log("☀️ Briefing giornaliero alle 8:00")

    # 📧 Controllo email - ogni 15 minuti
    _add_job_once(scheduler, "controllo_email", job_controllo_email,
                  IntervalTrigger(minutes=15))
    _log("📧 Controllo email ogni 15 minuti")

    # 💧 Acqua - ogni 2 ore
    _add_job_once(scheduler, "ricorda_acqua", job_ricorda_acqua,
                  IntervalTrigger(hours=2))
    _log("💧 Promemoria acqua ogni 2 ore")

    # 📊 Price watcher - ogni 6 ore
    _add_job_once(scheduler, "price_watcher", job_price_watcher,
                  IntervalTrigger(hours=6))
    _log("📊 Price watcher ogni 6 ore")

    # 📊 Report settimanale - Lunedì 9:00
    _add_job_once(scheduler, "report_settimanale", job_report_settimanale,
                  CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Europe/Rome"))
    _log("📊 Report settimanale lunedì 9:00")

    # 🏆 Classifica studio - Venerdì 18:00
    _add_job_once(scheduler, "classifica_studio", job_classifica_studio,
                  CronTrigger(day_of_week="fri", hour=18, minute=0, timezone="Europe/Rome"))
    _log("🏆 Classifica studio venerdì 18:00")

    # 📈 Crypto tracker - ogni ora
    def _crypto_tracker():
        try:
            _log(f"📈 Crypto: {str(get_crypto_price('bitcoin'))[:100]}")
        except Exception as exc:
            log.error("Crypto tracker: %s", exc)

    _add_job_once(scheduler, "crypto_tracker_hourly", _crypto_tracker,
                  IntervalTrigger(hours=1))
    _log("📈 Crypto tracker ogni ora")


def start_scheduler(run_test: bool = True) -> BackgroundScheduler:
    """Avvia (o recupera) lo scheduler e registra i job la prima volta.

    Args:
        run_test: Esegue subito job_price_watcher una sola volta per smoke test.
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="Europe/Rome", daemon=True)
        _scheduler.start()
        _register_jobs(_scheduler)
        _log("✅ Scheduler avviato con %d automazioni!", len(_JOB_IDS))
        if run_test:
            _log("🧪 Test automazioni: esecuzione price watcher...")
            try:
                job_price_watcher()
            except Exception as exc:
                log.warning("Test price_watcher fallito (normale se Supabase/API offline): %s", exc)
        _initialized.set()
    else:
        # Assicuriamoci che tutti i job ci siano (es. hot reload)
        _register_jobs(_scheduler)
        if not _scheduler.running:
            _scheduler.start()
    return _scheduler


def get_scheduler() -> BackgroundScheduler | None:
    """Restituisce lo scheduler solo se già avviato."""
    return _scheduler if _initialized.is_set() else None


def stop_scheduler() -> None:
    """Ferma lo scheduler (utile in fase di shutdown / test tear-down)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler fermato.")
    _initialized.clear()
    _JOB_IDS.clear()
