# 🧠 ATLAS AI v3.0

Assistente Intelligenza Artificiale **family-first** con backend Python/FastAPI + frontend mobile React Native (Expo).

> Progettato per **famiglie italiane**: AI conversazionale multi-utente con autenticazione PIN, gestione profili, liste todo, budget familiare, automazioni pianificate (scheduler APScheduler), e integrazione con LLM Gemini (function calling nativo).

---

## 🏗️ Architettura generale

```
┌──────────────────────────────┐      HTTP / JSON       ┌─────────────────────────────────────────┐
│   FRONTEND MOBILE            │ ─────────────────────▶ │  BACKEND FASTAPI (Python 3.11+)         │
│   React Native · Expo 51     │  Bearer token + CORS   │                                         │
│   NativeWind / Tailwind      │ ◀───────────────────── │  - 9 endpoints REST                     │
│   AsyncStorage (persistenza) │  Chat streaming +      │  - Router AI con Gemini function calling│
│   React Navigation 6.x       │  Messaggi strutturati  │  - Auth PIN (bcrypt) + Rate Limit 5/min │
│   Bottom Tabs + Auth Stack   │                       │  - 8 automazioni (cron + interval)      │
└──────────────────────────────┘                       │  - DB: Supabase ▶ fallback JSON locale  │
                                                       │  - Scheduler APScheduler (singleton)    │
                                                       │  - Tools: calcolatrice AST · todos      │
                                                       │           budget · geoutils · web search │
                                                       └─────────────────────────────────────────┘
                                                                      │
                                                                      ▼
                                           ┌──────────────────────────────────┐
                                           │  SERVIZI ESTERNI (opzionali)     │
                                           │  · Supabase / Postgres            │
                                           │  · Google Gemini 2.0 Flash (x3)   │
                                           │  · DuckDuckGo Search · Wikipedia  │
                                           │  · News API · Meteo / IP geoloc   │
                                           └──────────────────────────────────┘
```

---

## 🚀 Avvio rapido (sviluppo locale)

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

# Copia variabili ambiente (opzionale — senza funziona in MOCK MODE)
copy .env.example .env

uvicorn main:app --reload --port 8000
# ✅ Health check:  http://localhost:8000/
```

### 2. Frontend (Expo / React Native)

```bash
cd frontend
npm install
npx expo start
```

Oppure per testare senza device:
```bash
npm run web        # Web preview
npm run typecheck  # Verifica statica TypeScript
```

---

## 🔐 Configurazione ambiente (variabili)

Creare `backend/.env` (**tutte opzionali** — il sistema funziona anche in **MOCK MODE** con file JSON locali):

| Variabile | Scopo | Default |
|---|---|---|
| `APP_ENV` | `development` / `staging` / `production` | `development` |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `CORS_ORIGINS` | Lista origini consentite (separate da virgola) | `*` |
| `SUPABASE_URL` | URL progetto Supabase | *(vuoto = MOCK MODE)* |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key Supabase | *(vuoto = MOCK MODE)* |
| `GOOGLE_API_KEY_1`..`_3` | Chiavi Gemini (rotazione automatica + fallback 429) | *(vuoto = no LLM)* |
| `NEWSAPI_KEY` | Chiave NewsAPI.org (notizie) | opzionale |
| `OPENWEATHER_API_KEY` | Chiave OpenWeather (meteo) | opzionale |

**Frontend**: variabili ambiente `EXPO_PUBLIC_API_URL` per forzare l'endpoint backend (utile per build production). Se assente, viene auto-risolto: `EXPO_PUBLIC_API_URL` → IP LAN Expo Go → `localhost:8000`.

---

## 🛡️ Caratteristiche di sicurezza (hardened)

| Controllo | Stato | Dove |
|---|---|---|
| Hash PIN con `bcrypt` + `passlib` (rounds=12) | ✅ | [backend/app/core/security.py](backend/app/core/security.py) |
| Confronto PIN a tempo costante (`hmac.compare_digest`) | ✅ | `security.constant_time_equal()` |
| Rate limit anti-bruteforce PIN: **5/min per IP** | ✅ | `slowapi` + storage in-memory in [main.py](backend/main.py) |
| Validazione input PIN (4–8 cifre numeriche) | ✅ | Pydantic `field_validator` in [main.py](backend/main.py) |
| CORS restrittivo da env (nessun wildcard + allow_credentials) | ✅ | lifespan CORS middleware |
| **Rimosso `eval()`** — calcolatrice con parser AST whitelist | ✅ | [backend/app/tools/utility.py](backend/app/tools/utility.py) · `_safe_math_eval()` |
| Autenticazione stateless: token 32-byte + TTL 8h | ✅ | `security.generate_safe_token()` |
| Error handler globale (nessun leak stacktrace in prod) | ✅ | `@app.exception_handler(Exception)` in main.py |

---

## 🧪 Qualità & Test

### Backend — pytest (54 test)
```bash
cd backend
.\venv\Scripts\activate
pytest -v         # 54 test: security (16) · tools (24) · endpoints (14)
pytest --cov=app  # Copertura codice
```

| Suite test | N. | Cosa copre |
|---|---|---|
| `test_security.py` | 16 | bcrypt hash/verify, validazione pin, costant-time, token, sanitize, SHA256 |
| `test_tools.py` | 24 | Calcolatrice AST (19 test), todos (3), budget (2), Haversine |
| `test_endpoints.py` | 14 | Health, /profili, /auth/pin (5 casi + rate limit), /chat, todos CRUD, budget CRUD, 422 Pydantic |

### Frontend — TypeScript strict
```bash
cd frontend
npm run typecheck    # tsc --noEmit · strict mode
```

---

## 📦 Ambienti

| Ambiente | Configurazione | Note |
|---|---|---|
| **Sviluppo** | `APP_ENV=development` | log DEBUG, auto-reload uvicorn, CORS * |
| **Staging** | `APP_ENV=staging` · 1 chiave Gemini | CORS dominio staging specifico, logger `RotatingFileHandler` 5MB |
| **Produzione** | `APP_ENV=production` · Supabase + 3 chiavi Gemini | `gunicorn -k uvicorn.workers.UvicornWorker -w 4` + env CORS stretto, reverse proxy Nginx |

---

## 📂 Struttura cartelle

```
atlas-ai/
├── backend/
│   ├── main.py                 # Entrypoint FastAPI, endpoints, lifespan, rate limit, handlers
│   ├── requirements.txt        # Dipendenze pinned
│   ├── pytest.ini              # Config pytest
│   ├── tests/                  # test_security · test_tools · test_endpoints · conftest
│   ├── .env.example            # Template env vars
│   ├── app/
│   │   ├── ai_router.py        # Router Gemini function calling (0/1/2/3 keys fallback)
│   │   ├── scheduler.py        # Singleton APScheduler, 8 automazioni pianificate
│   │   ├── core/
│   │   │   ├── database.py     # Supabase client lazy + @resilient decorator fallback locale
│   │   │   ├── security.py     # bcrypt PIN, token, sanitize, constant_time
│   │   │   ├── logging_config.py # RotatingFileHandler + StreamHandler strutturato
│   │   │   └── settings.py     # Parsing env, pin limiti, rotazione API keys
│   │   └── tools/
│   │       ├── registry.py     # 18+ funzioni registerate per function calling
│   │       ├── utility.py      # Calcolatrice AST, web search, wikipedia, news, haversine
│   │       ├── family.py       # Todos · note · voti scuola
│   │       ├── finance.py      # Budget familiare, spese, report
│   │       ├── travel.py       # Meteo, geolocalizzazione, cambio valuta
│   │       ├── italian_module.py # Esercizi italiano per stranieri
│   │       ├── google_tools.py # Documenti Google, Gmail (placeholder)
│   │       └── services/       # web_search.py, nlp_italian.py helpers
│   └── _local_db/              # File JSON fallback (todos, spese, messaggi...) — creato auto se Supabase assente
│
└── frontend/
    ├── App.tsx                 # AuthContext, navigazione (Stack + BottomTabs)
    ├── package.json            # Expo ~51.0, React Native 0.74, NativeWind 3.3
    ├── tsconfig.json           # strict: true, alias @/*
    ├── shims.d.ts              # moduli assets + AsyncStorage stub
    ├── nativewind-env.d.ts     # className supporto nei componenti RN
    └── src/
        ├── config.ts           # URL backend dinamico (env → Expo LAN → localhost)
        ├── services/api.ts     # ApiService singleton · timeout 15s · Bearer auto
        ├── context/AuthContext.tsx  # Stato auth globale, persistenza AsyncStorage
        └── screens/            # ProfileScreen (PIN) · Home · Chat · Todos · Budget
```

---

## 🔄 Resilienza & Fallback (design chiave)

1. **Database**: Decoratore `@resilient(fallback_return=...)` su tutte le funzioni DB — se Supabase è irraggiungibile, salva/legge in modo trasparente da file JSON locale sotto `backend/_local_db/`. L'utente non percepisce alcun downtime.
2. **LLM Gemini**: Fino a 3 chiavi API ruotate automaticamente; se tutte danno errore 429 (quota), viene ritornata risposta locale sintetica invece di crash.
3. **Tools opzionali**: Import `wikipedia` e `duckduckgo-search` con graceful degradation — se mancano, le funzioni tornano messaggio istruttivo invece di bloccare l'intera app.
4. **Rate limiting**: Tutti gli endpoint protetti (es. `/auth/pin`) + limiti generosi per endpoints pubblici.

---

## 🚀 Deploy

### Backend (Docker / Ubuntu / Railway / Render)

```bash
# Dockerfile esempio
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
ENV APP_ENV=production PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "main:app"]
```

### Frontend (EAS Build)

```bash
npm install -g eas-cli
eas build:configure
eas build --platform android --profile preview     # APK di test
eas build --platform ios --profile production      # App Store
```

---

## ✅ Checklist upgrade enterprise (attuali)

- [x] Sicurezza: bcrypt, rate limit 5/min, anti-bruteforce, CORS restrittivo, AST parser instead of eval
- [x] Architettura: FastAPI lifespan, scheduler singleton, @resilient fallback Supabase→JSON
- [x] Frontend: AuthContext, ApiService singleton, URL dinamico, PIN verify remoto
- [x] Gestione errori: handler globale, log strutturato (RotatingFileHandler), except specifici
- [x] Test: 54 test pytest (security/tools/endpoints), 16/16, 24/24, 14/14 PASSATI
- [x] Dipendenze: pinned a versione stabile ~30 packages backend, Expo 51.0.28 frontend
- [x] Typecheck: `tsc --noEmit` 0 errori strict mode
- [x] Avvio backend reale verificato + endpoints rispondono 200 OK
