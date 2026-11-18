"""
Scheduler delle automazioni ATLAS AI v3.0 (APScheduler).

Ogni automazione esegue lavoro reale (meteo, crypto, budget, todo, email,
progressi italiano) e invia notifiche push ai dispositivi registrati.
Le automazioni disattivate in Impostazioni vengono saltate.

Lo scheduler NON parte all'import: viene avviato dal lifespan di FastAPI.
"""
from __future__ import annotations

import datetime
import threading
from typing import Any, Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import (
    automation_enabled,
    fetch_profiles,
    get_budget_summary,
    get_italian_leaderboard,
    get_due_reminders,
    get_settings,
    get_todos,
    mark_reminder_sent,
)
from app.core.logging_config import get_logger
from app.core.scheduler_lock import ProcessLock
from app.core.settings import LOCAL_DB_DIR, default_city, scheduler_timezone
from app.notifiche import invia_a_profilo, invia_a_tutti
from app.services.backup import backup_local_db
from app.tools.family import get_family_todos
from app.tools.finance import get_crypto_price, riepilogo_budget
from app.tools.italian import lezione_del_giorno
from app.tools.travel import get_weather

log = get_logger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_initialized = threading.Event()
_JOB_IDS: set[str] = set()

# Un solo processo per host esegue i job (evita notifiche duplicate con più worker).
_lock = ProcessLock(LOCAL_DB_DIR / ".scheduler.lock")

JOB_KEYS: tuple[str, ...] = (
    "lezione_italiano",
    "briefing_giornaliero",
    "controllo_email",
    "ricorda_acqua",
    "price_watcher",
    "report_settimanale",
    "classifica_studio",
    "ombrello_smart",
    "promemoria_pillola",
    "smart_calendar",
    "crypto_tracker",
    "promemoria_due",
)


def automazioni_totali() -> int:
    """Numero di automazioni definite (indipendente dal worker che le esegue)."""
    return len(JOB_KEYS)


def _log(message: str) -> None:
    log.info("[SCHED] %s", message)


def _enabled(name: str) -> bool:
    return automation_enabled(name)


def _safe(step: str, action: Callable[[], Any]) -> Any:
    """Esegue un passo dell'automazione senza far crashare il job."""
    try:
        return action()
    except Exception as exc:  # pragma: no cover - dipende da servizi esterni
        log.error("%s fallito: %s", step, exc)
        return None


# ======================================================================
#  AUTOMAZIONI
# ======================================================================
def job_lezione_italiano() -> None:
    """Invia la lezione di italiano del giorno ai profili che stanno imparando."""
    if not _enabled("lezione_italiano"):
        return
    _log("📚 Lezione italiano del giorno")
    for slug, profilo in fetch_profiles().items():
        livello = str(profilo.get("livello_italiano") or "B1")
        if livello in ("Madrelingua", "C1", "C2"):
            continue
        lezione = lezione_del_giorno(livello)
        _safe(
            "invio lezione",
            lambda s=slug, l=lezione: invia_a_profilo(
                s,
                titolo=f"Lezione di oggi · {l['livello']}",
                messaggio=f"{l['titolo']}: {l['spiegazione'][:140]}…",
                dati={"tipo": "lezione_italiano", "lezione_id": l["id"]},
            ),
        )


def job_briefing_giornaliero() -> None:
    """Briefing mattutino: meteo, todo pendenti e spesa del mese."""
    if not _enabled("briefing_giornaliero"):
        return
    _log("☀️ Briefing mattutino")
    citta = default_city()
    meteo = _safe("meteo briefing", lambda: get_weather(citta)) or "Meteo non disponibile"
    pending = [todo for todo in get_todos() if not todo.get("is_completed")]
    spesa = (get_budget_summary(only_month=True) or {}).get("totale", 0.0)
    messaggio = f"{meteo}\n🛒 {len(pending)} cose da fare · 💰 €{float(spesa):.2f} questo mese"
    _safe(
        "invio briefing",
        lambda: invia_a_tutti("Buongiorno! ☀️", messaggio, {"tipo": "briefing"}),
    )


def job_controllo_email() -> None:
    """Controlla le email Gmail collegate e notifica le novità (solo se connesso)."""
    if not _enabled("controllo_email"):
        return
    from app.services import google_oauth

    if not google_oauth.status()["connesso"]:
        log.debug("Controllo email saltato: account Google non collegato.")
        return
    from app.tools.communication import gmail_leggi_email

    esito = _safe("lettura email", lambda: gmail_leggi_email(3))
    if not esito or esito.startswith("⚠️") or esito.startswith("📭"):
        return
    _safe(
        "invio notifica email",
        lambda: invia_a_profilo("io", "Nuove email 📧", esito[:400], {"tipo": "email"}),
    )


def job_ricorda_acqua() -> None:
    """Promemoria idratazione, solo nelle ore diurne."""
    if not _enabled("promemoria_acqua"):
        return
    ora = datetime.datetime.now().hour
    if not (8 <= ora <= 22):
        return
    _log("💧 Promemoria acqua")
    _safe(
        "invio promemoria acqua",
        lambda: invia_a_tutti("💧 Bevi un bicchiere d'acqua", "Pausa idratazione di famiglia!", {"tipo": "acqua"}),
    )


def job_price_watcher() -> None:
    """Controlla crypto e avvisa solo se la variazione supera la soglia."""
    if not _enabled("price_watcher"):
        return
    _log("📈 Price watcher crypto")
    settings = get_settings() or {}
    soglia = float(((settings.get("soglie") or {}).get("crypto_variazione_percent")) or 5.0)

    for symbol, nome in (("bitcoin", "Bitcoin"), ("ethereum", "Ethereum")):
        esito = _safe(f"prezzo {symbol}", lambda s=symbol: get_crypto_price(s))
        if not esito or "%" not in str(esito):
            continue
        try:
            variazione = float(str(esito).split("24h:")[-1].replace("%", "").replace("📈", "").replace("📉", "").strip())
        except ValueError:
            continue
        if abs(variazione) >= soglia:
            _safe(
                "invio alert crypto",
                lambda n=nome, e=esito, v=variazione: invia_a_tutti(
                    f"{n} {'su' if v >= 0 else 'giù'} del {abs(v):.1f}%",
                    str(e),
                    {"tipo": "crypto"},
                ),
            )


def job_report_settimanale() -> None:
    """Report settimanale di budget, todo e italiano."""
    if not _enabled("report_settimanale"):
        return
    _log("📊 Report settimanale")
    budget = _safe("riepilogo budget", riepilogo_budget) or "Budget non disponibile"
    todos = _safe("lista todo", get_family_todos) or "Lista non disponibile"
    _safe(
        "invio report",
        lambda: invia_a_tutti(
            "Report settimanale 📊",
            f"{budget}\n\n{todos}"[:700],
            {"tipo": "report"},
        ),
    )


def job_classifica_studio() -> None:
    """Classifica di studio della settimana."""
    if not _enabled("classifica_studio"):
        return
    _log("🏆 Classifica studio")
    board = get_italian_leaderboard()
    if not board:
        return
    righe = [f"{index}. {row['nome']}: {row['punti']} punti" for index, row in enumerate(board[:5], 1)]
    _safe(
        "invio classifica",
        lambda: invia_a_tutti("Classifica italiano 🏆", "\n".join(righe), {"tipo": "classifica"}),
    )


def job_ombrello_smart() -> None:
    """Avvisa se oggi pioverà (meteo reale, Open-Meteo)."""
    if not _enabled("ombrello_smart"):
        return
    meteo = _safe("meteo ombrello", lambda: get_weather(default_city()))
    if not meteo or "%" not in str(meteo):
        return
    try:
        pioggia = int(str(meteo).split("Pioggia oggi:")[-1].split("%")[0].strip())
    except ValueError:
        return
    if pioggia >= 40:
        _safe(
            "invio avviso pioggia",
            lambda: invia_a_tutti("☔ Oggi piove", f"{meteo}\nPrendi l'ombrello!", {"tipo": "pioggia"}),
        )


def job_promemoria_pillola() -> None:
    """Promemoria quotidiano salute (disattivo di default)."""
    if not _enabled("promemoria_pillola"):
        return
    _safe(
        "invio promemoria pillola",
        lambda: invia_a_tutti("💊 Promemoria salute", "È ora del promemoria quotidiano.", {"tipo": "salute"}),
    )


def job_controllo_calendario() -> None:
    """Legge l'agenda di oggi dal Calendar collegato e la riassume."""
    if not _enabled("smart_calendar"):
        return
    from app.services import google_oauth

    if not google_oauth.status()["connesso"]:
        log.debug("Smart calendar saltato: Google Calendar non collegato.")
        return
    from app.tools.communication import calendar_agenda

    agenda = _safe("lettura agenda", lambda: calendar_agenda())
    if not agenda or "nessun evento" in agenda.lower():
        return
    _safe(
        "invio agenda",
        lambda: invia_a_profilo("io", "Agenda di oggi 📅", agenda[:400], {"tipo": "calendario"}),
    )


def job_crypto_tracker() -> None:
    """Log orario dei prezzi (senza notifiche: evita spam)."""
    if not _enabled("crypto_tracker"):
        return
    btc = _safe("crypto btc", lambda: get_crypto_price("bitcoin"))
    log.info("📈 Crypto orario: %s", str(btc)[:120])


def job_backup_local_db() -> None:
    """Backup periodico del database locale (JSON in `_local_db`)."""
    esito = backup_local_db()
    if esito is None:
        log.warning("Backup locale non eseguito (vedi log del servizio backup).")
    else:
        _log(f"🗄️ Backup locale creato: {esito.name}")


def job_promemoria_due() -> None:
    """Invia i promemoria scaduti non ancora pianificati localmente.

    L'app pianifica una notifica locale appena crea/sincronizza un promemoria
    e lo conferma con /promemoria/{id}/programmato. Se quella conferma manca
    (app chiusa, permesso negato, altro dispositivo), lo scheduler usa il push
    reale come fallback. In questo modo non arrivano due notifiche uguali.
    """
    if not _enabled("promemoria_due"):
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    due = _safe("lettura promemoria scaduti", lambda: get_due_reminders(now_iso, limit=30)) or []
    for reminder in due:
        try:
            reminder_id = str(reminder.get("id") or "")
            profile = str(reminder.get("profile_slug") or "")
            if not reminder_id or not profile:
                continue
            if reminder.get("local_scheduled_at"):
                # La notifica locale è già pianificata sul dispositivo: niente push duplicata.
                mark_reminder_sent(reminder_id)
                continue
            messaggio = str(reminder.get("message") or "Promemoria")
            if bool(reminder.get("include_todos", True)):
                pending = [
                    str(todo.get("task_text") or todo.get("task") or "").strip()
                    for todo in (get_todos(only_pending=True) or [])
                    if (todo.get("task_text") or todo.get("task"))
                ]
                if pending:
                    anteprima = ", ".join(pending[:12])
                    messaggio += f"\n🛒 Lista ({len(pending)}): {anteprima}" + ("…" if len(pending) > 12 else "")
            inviati = invia_a_profilo(
                profile,
                "⏰ Promemoria ATLAS",
                messaggio[:800],
                {"tipo": "promemoria", "reminder_id": reminder_id},
            )
            if inviati > 0:
                mark_reminder_sent(reminder_id)
                log.info("Promemoria %s inviato a %s", reminder_id[:12], profile)
            else:
                log.info("Promemoria %s in attesa: nessun dispositivo push per %s", reminder_id[:12], profile)
        except Exception as exc:  # pragma: no cover - dipende dal DB/rete
            log.error("Errore promemoria %s: %s", str(reminder.get("id"))[:12], exc)


# ======================================================================
#  REGISTRAZIONE JOB
# ======================================================================
def _add_job_once(scheduler: BackgroundScheduler, job_id: str, func, trigger, **kwargs) -> None:
    if job_id in _JOB_IDS or scheduler.get_job(job_id):
        return
    scheduler.add_job(func, trigger, id=job_id, coalesce=True, max_instances=1, **kwargs)
    _JOB_IDS.add(job_id)


def _register_jobs(scheduler: BackgroundScheduler) -> None:
    tz = scheduler_timezone()

    _add_job_once(
        scheduler, "lezione_italiano", job_lezione_italiano,
        CronTrigger(hour=7, minute=30, timezone=tz),
    )
    _add_job_once(
        scheduler, "briefing_giornaliero", job_briefing_giornaliero,
        CronTrigger(hour=8, minute=0, timezone=tz),
    )
    _add_job_once(
        scheduler, "controllo_email", job_controllo_email,
        IntervalTrigger(minutes=15),
    )
    _add_job_once(
        scheduler, "ricorda_acqua", job_ricorda_acqua,
        IntervalTrigger(hours=2),
    )
    _add_job_once(
        scheduler, "price_watcher", job_price_watcher,
        IntervalTrigger(hours=6),
    )
    _add_job_once(
        scheduler, "report_settimanale", job_report_settimanale,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=tz),
    )
    _add_job_once(
        scheduler, "classifica_studio", job_classifica_studio,
        CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=tz),
    )
    _add_job_once(
        scheduler, "ombrello_smart", job_ombrello_smart,
        CronTrigger(hour=6, minute=45, timezone=tz),
    )
    _add_job_once(
        scheduler, "promemoria_pillola", job_promemoria_pillola,
        CronTrigger(hour=21, minute=0, timezone=tz),
    )
    _add_job_once(
        scheduler, "smart_calendar", job_controllo_calendario,
        IntervalTrigger(hours=1),
    )
    _add_job_once(
        scheduler, "crypto_tracker", job_crypto_tracker,
        IntervalTrigger(hours=1),
    )
    _add_job_once(
        scheduler, "promemoria_due", job_promemoria_due,
        IntervalTrigger(seconds=30),
    )
    # Non è un'automazione utente: nessuna chiave in JOB_KEYS, nessuna notifica.
    _add_job_once(
        scheduler, "backup_local_db", job_backup_local_db,
        IntervalTrigger(hours=6),
    )
    _log(f"✅ Registrate {len(_JOB_IDS)} automazioni")


def start_scheduler(run_test: bool = False) -> Optional[BackgroundScheduler]:
    """Avvia (o recupera) lo scheduler. Nessuna chiamata di rete all'avvio.

    Con più worker solo il processo che ottiene il lock esegue i job: gli
    altri servono le API ma non duplicano le notifiche.
    """
    global _scheduler
    if _scheduler is None:
        if not _lock.acquire():
            log.warning(
                "⏭️ Scheduler già attivo in un altro processo: questo worker non eseguirà i job."
            )
            return None
        try:
            _scheduler = BackgroundScheduler(timezone=scheduler_timezone(), daemon=True)
            _scheduler.start()
            _register_jobs(_scheduler)
            _initialized.set()
        except Exception:
            _lock.release()
            _scheduler = None
            raise
    else:
        _register_jobs(_scheduler)
        if not _scheduler.running:
            _scheduler.start()
    if run_test:
        _log("🧪 Test automazioni disabilitato di default (nessuna chiamata di rete all'avvio).")
    return _scheduler


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Scheduler attivo (None se non ancora avviato)."""
    return _scheduler if _initialized.is_set() else None


def get_jobs() -> list[dict[str, Any]]:
    """Elenco job con prossima esecuzione (per l'endpoint /automazioni)."""
    scheduler = get_scheduler()
    if not scheduler:
        return []
    out: list[dict[str, Any]] = []
    for job in scheduler.get_jobs():
        if job.id not in JOB_KEYS:
            # Job di servizio (es. backup del database locale): non è un'automazione utente.
            continue
        next_run = getattr(job, "next_run_time", None)
        out.append(
            {
                "id": job.id,
                "prossima": next_run.isoformat() if next_run else None,
                "attiva": automation_enabled(job.id),
            }
        )
    return sorted(out, key=lambda item: item["id"])


def stop_scheduler() -> None:
    """Ferma lo scheduler e consente un riavvio pulito (usato nei test)."""
    global _scheduler
    if _scheduler is not None:
        try:
            if _scheduler.running:
                _scheduler.shutdown(wait=False)
        except Exception as exc:  # pragma: no cover
            log.warning("Errore arresto scheduler: %s", exc)
    _scheduler = None
    _initialized.clear()
    _JOB_IDS.clear()
    _lock.release()
