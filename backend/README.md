# Backend ATLAS AI — Guida tecnica

FastAPI 0.115+ · Python 3.11+ · Pydantic v2 · APScheduler · Supabase / local JSON fallback

---

## 📋 Prerequisiti

- Python **3.11, 3.12 o 3.13+** (testato anche su 3.14-rc)
- `venv` incluso in Python standard
- *Opzionale*: un progetto **Supabase** attivo (senza → MOCK MODE automatico con file JSON)
- *Opzionale*: 1–3 chiavi API **Google Gemini** per function calling LLM

---

## 🏁 Installazione & Avvio

```powershell
# 1. Crea ambiente virtuale
python -m venv venv

# 2. Attivalo (Windows PowerShell)
.\venv\Scripts\Activate.ps1

#    (Linux/macOS)
# source venv/bin/activate

# 3. Installa dipendenze (tutte pinned — nessuna build Rust necessaria)
pip install -r requirements.txt

# 4. (Opzionale) Crea .env da template
copy .env.example .env

# 5. Avvia server in modalità sviluppo
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

✅ **Verifica**: apri <http://localhost:8000/> nel browser — ottieni risposta tipo:
```json
{
  "status": "ok",
  "profili": 5,
  "automazioni": 8,
  "ambiente": "development",
  "versione": "3.0.0"
}
```

---

## 🧪 Test (54 test)

```powershell
# Tutti i test
pytest -v -W ignore::DeprecationWarning

# Solo sicurezza
pytest tests/test_security.py -v

# Solo tools (calcolatrice, todos, budget, geoutils)
pytest tests/test_tools.py -v

# Solo integrazione endpoints
pytest tests/test_endpoints.py -v

# Con rapporto di copertura
pytest --cov=app --cov-report=html
```

**Stato attuale**: `54 passed / 0 failed` ✅

---

## 🗺️ Endpoints API pubblici

Tutti ritornano JSON. Autenticazione: dopo `/auth/pin` ricevi `{token}` → passalo come header `Authorization: Bearer <token>` per endpoints protetti.

| Metodo | Path | Auth | Descrizione | Esempio corpo |
|---|---|---|---|---|
| GET | `/` | ❌ | Health check, stato generale | – |
| GET | `/profili` | ❌ | Elenco profili famiglia (slug → nome + livello italiano) | – |
| POST | `/auth/pin` | ❌ | Verifica PIN + restituisce token `{auth, token, message}` | `{"profile_slug": "io", "pin": "0000"}` |
| POST | `/chat` | ✅ | Interroga AI (streaming opzionale); funzione calling automatico | `{"profile_slug": "io", "messaggio": "Quanto speso a cibo?", "token": "xxx"}` |
| GET | `/todos?filtro=all/pending/completed` | ✅ | Lista todo del profilo | – |
| POST | `/todos/aggiungi` | ✅ | Aggiungi todo | `{"profile_slug":"io","testo":"Spesa"}` |
| POST | `/todos/completa` | ✅ | Completa per indice 0-based | `{"profile_slug":"io","indice":0}` |
| GET | `/budget` | ✅ | Riepilogo budget {totale, dettaglio:[{categoria, importo, percentuale}]} | – |
| POST | `/budget/spesa` | ✅ | Aggiungi spesa | `{"profile_slug":"mamma","importo":25.5,"categoria":"Cibo","nota":"Pizza"}` |

**Rate limit**:
- `/auth/pin` → 5 richieste/minuto per IP (anti-bruteforce)
- Altri endpoints → 30–60 richieste/minuto per IP

---

## 👤 Profili di default (per sviluppo / test)

I PIN bcrypt **veri** andranno impostati su Supabase; in ambiente di **test** viene usato mapping noto (vedi `tests/conftest.py`):

| Slug | Nome | PIN test |
|---|---|---|
| `io` | (tu) | 0000 |
| `mamma` | Mamma | 1111 |
| `papa` | Papà | 2222 |
| `fratello1` | Fratello 1 | 3333 |
| `fratello2` | Fratello 2 | 4444 |

⚠️ In **produzione** sovrascrivi gli hash in `DEFAULT_PROFILES` di `app/core/database.py` oppure carica i profili direttamente sulla tabella `family_profiles` di Supabase.

---

## 💽 Modalità DB

| Modalità | Come si attiva | Dove salva i dati |
|---|---|---|
| **SUPABASE** | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` valorizzate in env | Postgres remoto Supabase |
| **MOCK/LOCALE** | chiavi Supabase assenti o non raggiungibili | File JSON in `backend/_local_db/{todos, messages, family_expenses, profiles, ...}.json` |

Il passaggio tra le due è **totalmente trasparente** grazie al decoratore `@resilient()` in `app/core/database.py`.

---

## ⏰ Automazioni Scheduler (8 jobs)

Vengono avviate in `lifespan` all'avvio dell'app (nessun side-effect a import).

| Job | Trigger | Cosa fa |
|---|---|---|
| Lezione italiano | **cron** 7:30 tutti i giorni | Promemoria esercizi lingua italiana |
| Briefing giornaliero | **cron** 8:00 tutti i giorni | Riassunto meteo + appuntamenti + todos |
| Controllo email | **interval** ogni 15 min | Verifica IMAP Gmail (placeholder) |
| Promemoria acqua | **interval** ogni 2 ore | Push notifica bere acqua |
| Price watcher | **interval** ogni 6h | Monitoraggio prezzi Amazon (placeholder) |
| Report settimanale | **cron** Lunedì 9:00 | Riepilogo budget + todos settimana |
| Classifica studio | **cron** Venerdì 18:00 | Punti di progresso fratelli |
| Crypto tracker | **interval** ogni 1h | Prezzi BTC/ETH (se API disponibile) |

---

## 📜 Logging

Configurato in `app/core/logging_config.py`:
- **StreamHandler stdout**: per development
- **RotatingFileHandler**: `logs/atlas.log` — 5MB max / 3 backup
- **Livello**: `LOG_LEVEL` env (default `INFO`)
- Librerie terze parti silenziate: `httpx`, `supabase`, `apscheduler` (WARNING)

---

## 🚀 Produzione

```bash
# 1. Imposta variabili ambiente
export APP_ENV=production
export CORS_ORIGINS="https://atlas.miodominio.it,https://*.vercel.app"
export SUPABASE_URL="..."
export SUPABASE_SERVICE_ROLE_KEY="..."
export GOOGLE_API_KEY_1="..." GOOGLE_API_KEY_2="..." GOOGLE_API_KEY_3="..."

# 2. Avvia con process manager (4 worker per 4 CPU)
gunicorn -k uvicorn.workers.UvicornWorker \
         -w 4 -b 0.0.0.0:8000 \
         --timeout 60 --graceful-timeout 30 \
         --access-logfile logs/access.log \
         --error-logfile logs/error.log \
         main:app
```

**Reverse proxy**: Nginx davanti a gunicorn (HTTPS + rate-limit extra + compressione gzip).

---

## 🔧 Strumenti di debug

```bash
# Verifica dipendenze + security check
pip-audit

# Controllo tipi (se mypy installato)
mypy app/ --ignore-missing-imports

# Entrypoint debug REPL
python -c "from app.core.database import *; from pprint import pp; pp(fetch_profiles())"
```
