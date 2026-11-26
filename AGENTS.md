# AGENTS.md — istruzioni per agenti di codice (ATLAS AI)

Questo file è per chi lavora sul repository con un agente LLM. Descrive ciò che
è vero oggi. Se una cosa non è verificata, non va scritta qui: meglio una riga in
meno che una riga falsa.

## Cos'è questo repository

**ATLAS AI** è un assistente AI *family-first* pensato per una famiglia su
un'istanza privata (non un SaaS multi-tenant). Due parti, un solo prodotto:

- **`backend/`** — FastAPI (Python **3.11–3.13**), Pydantic v2, APScheduler,
  Playwright/Chromium per l'agente browser. Tutte le route sono in
  `backend/main.py`; autenticazione PIN (bcrypt) + token di sessione HMAC.
- **`frontend/`** — app Expo / React Native (TypeScript **strict**), NativeWind,
  AsyncStorage. Gira su Android, iOS e web (`expo export --platform web`).

I dati stanno su **Supabase** se configurato, altrimenti in file JSON atomici
dentro `backend/_local_db/` (default). L'app **non parla mai** con il database:
passa sempre dal backend.

- Versione: `APP_VERSION` in `backend/main.py` (oggi 3.4.x)
- Licenza: MIT
- CI: `.github/workflows/ci.yml` (backend + frontend + sicurezza),
  `e2e.yml` (Playwright sulla build web), `android-apk.yml`, `ios-build.yml`

## Regole non negoziabili

1. **Nessun successo finto.** Se manca una chiave o una funzione non è
   configurata, l'utente deve leggere un errore esplicito. Vale per i tool AI,
   le notifiche, l'OAuth e i PDF. Un tool che "sembra funzionare" è un bug.
2. **Nessun segreto nel repository.** `.env`, `_local_db/`, `_backups/`, token
   OAuth, keystore: tutti ignorati da `.gitignore` e mai committati. I nomi
   delle variabili sono in `backend/.env.example`.
3. **Il backend è l'unica fonte di verità.** Nessuna chiamata diretta a
   Supabase dal frontend, nessuna logica di autorizzazione nell'app.
4. **Italiano.** UI, messaggi d'errore, commenti e documenti sono in italiano;
   le chiavi tecniche (JSON, endpoint, campi DB) restano in inglese.
5. **Un comportamento nuovo porta un test.** La suite è `pytest` (vedi sotto):
   un fix senza test di regressione non è finito.
6. **Non indebolire i controlli per far passare una run.** Niente PIN demo
   ammessi, niente CORS aperto, niente test skippati, niente soglie abbassate.

## Comandi

```bash
# Backend (dalla cartella backend/)
python3 -m venv .venv && . .venv/bin/activate     # Windows: py -3.12 -m venv .venv
pip install -r requirements.txt
python -m playwright install chromium             # una volta sola, ~130 MB
python -m pip check                               # dipendenze coerenti
python -m pytest -q                               # suite completa
uvicorn main:app --reload --port 8000             # http://localhost:8000/

# Frontend (dalla cartella frontend/)
npm ci
npx tsc --noEmit                                  # typecheck strict
npm run export:web                                # build statica in dist/
npm run test:e2e                                  # Playwright (serve backend su :8010)
```

Script di comodo (Windows): `scripts/setup.ps1` installa tutto,
`scripts/verify.ps1` esegue test + `pip check` + typecheck (con `-Build` anche
l'export web), `scripts/install-autostart.ps1` registra l'avvio automatico.

La verifica minima prima di una PR:

```bash
cd backend && python -m pytest -q && python -m pip check
cd frontend && npm ci && npx tsc --noEmit
```

Se tocchi l'agente browser aggiungi anche `python -m playwright install chromium`
prima dei test. Se tocchi la build web, `npm run export:web`.

## Mappa del repository

```
backend/main.py                  app FastAPI, CORS, dipendenza get_current_profile, tutte le route
backend/app/ai_router.py         Gemini: rotazione chiavi, function calling, trascrizione audio
backend/app/scheduler.py         automazioni periodiche (JOB_KEYS) + lock di processo
backend/app/notifiche.py         Expo Push / FCM, disattivazione dei token morti
backend/app/core/                auth_guard, context, database, logging, net_guard,
                                 parental, scheduler_lock, schemas, secrets_box,
                                 security (PIN/token), settings
backend/app/services/            backup cifrati, browser (Chromium), budget, gemini,
                                 google_oauth, google_tools, italiano, pdf,
                                 privacy, web_search
backend/app/tools/               strumenti esposti a Gemini: family, finance, travel,
                                 communication, google_advanced, italiano, browser,
                                 mcp_bridge, registry (schema function calling)
backend/tests/                   suite pytest (conftest isola DB e segreti)
frontend/App.tsx                 navigazione e provider
frontend/src/screens/            10 schermate (Home, Chat, Budget, Liste, PIN, …)
frontend/src/services/           client HTTP e storage
frontend/e2e/                    smoke test Playwright della build web
docs/                            API, architettura, browser, deploy, install, iOS,
                                 privacy, roadmap, guida ai test
scripts/                         setup / verify / autostart (PowerShell)
```

## Dove si aggiunge una cosa

- **Nuovo strumento per l'AI**: funzione in `backend/app/tools/<dominio>.py`,
  registrazione e schema in `backend/app/tools/registry.py`, test in
  `backend/tests/`. Se lo strumento compie un'azione irreversibile (inviare
  un'email, cancellare dati) serve una conferma esplicita dell'utente, come già
  fanno Gmail e Calendar.
- **Nuovo endpoint**: `backend/main.py`, con `Depends(get_current_profile)` se
  tocca dati privati, schema Pydantic in `app/core/schemas.py` e test.
- **Nuova schermata**: `frontend/src/screens/` + voce di navigazione in
  `App.tsx`; il client HTTP va in `frontend/src/services/`.
- **Nuova automazione**: `backend/app/scheduler.py` + test del lock
  (`tests/test_scheduler_lock.py`) per non duplicare i job.
- **Nuovo documento**: `docs/` e un link dal `README.md`.

## Trappole note (verificate)

- **Python 3.14/3.15 non sono supportati**: i pacchetti sono pinnati per
  3.11–3.13 (la CI usa 3.12). Con 3.14 l'installazione fallisce.
- **I test vanno lanciati da `backend/`**: `pytest.ini` imposta `testpaths =
  tests` e `asyncio_mode = auto`. `conftest.py` forza `APP_ENV=test`,
  `SCHEDULER_ENABLED=false`, un `CORS_ALLOWED_ORIGINS` esplicito, rimuove le
  chiavi reali e sposta `_local_db` in una cartella temporanea: nessun dato di
  sviluppo viene toccato.
- **`tests/test_browser.py` richiede Chromium vero**, non un mock. In un
  container minimale non bastano i binari di Playwright: servono le librerie di
  sistema (`playwright install-deps`) **e almeno un font**. Senza font il layout
  ha altezza 0 e `innerText` torna vuoto: 10 test falliscono con un messaggio
  che sembra un bug dell'agente browser, mentre è l'ambiente. In CI
  `e2e.yml` installa Chromium con `--with-deps`.
- **`npm ci` esige il lockfile sincronizzato**: una PR di dipendenze che cambia
  `package.json` senza rigenerare `package-lock.json` si ferma con `EUSAGE`
  prima ancora del typecheck.
- **L'E2E ha bisogno di due processi**: backend su `:8010`
  (`EXPO_PUBLIC_API_URL` puntato lì) e build web servita su `:19007`
  (`playwright.config.ts` avvia `serve`). `EXPO_PUBLIC_API_URL` viene letta al
  momento dell'export, non a runtime.
- **In `main.py` non si usa `from __future__ import annotations`**: FastAPI
  risolve le annotazioni a runtime e slowapi le avvolgerebbe in `ForwardRef`
  non risolvibili. Il motivo è scritto nel docstring del file.
- **`fastapi` 0.165 porta `starlette` 1.x**: le API asincrone si importano come
  oggi (`from starlette.concurrency import run_in_threadpool`). Un downgrade di
  `fastapi` reintroduce le vulnerabilità chiuse da `pip-audit`.

## Sicurezza: cosa non deve regredire

- PIN con hash **bcrypt 12 rounds** e confronto a tempo costante; rate limiting
  slowapi sugli endpoint di autenticazione.
- **Fail closed sui profili**: in produzione, se `profiles.json` manca o è
  corrotto non viene caricato nessun profilo; i **PIN demo** (`0000`, `1111`,
  …) sono rifiutati sia al login sia al cambio PIN.
- **Revoca delle sessioni**: `pin_version` avanza al cambio PIN, i token
  portano la versione e le sessioni vecchie prendono 401.
- **Codice di recupero** salvato solo come hash, monouso, rigenerabile
  dall'amministratore.
- **CORS chiuso in produzione** senza `CORS_ALLOWED_ORIGINS`; l'origine della
  web app locale passa da `PREVIEW_WEB_ORIGIN_REGEX` (solo loopback e reti
  private).
- **Agente browser**: ogni profilo ha sessioni Playwright isolate e i test
  verificano che DNS interni, XHR, iframe e immagini restino bloccati
  (`tests/test_browser.py`). Le richieste HTTP in uscita passano da
  `app/core/net_guard.py`, che rifiuta schema non `http(s)`, credenziali
  nell'URL e IP privati/loopback (si riabilitano solo con
  `ALLOW_PRIVATE_FETCH=true`).
- **OAuth Google**: i token sono cifrati (`app/core/secrets_box.py`) e alla
  disconnessione i grant vengono revocati davvero, non solo dimenticati.
- **Backup** cifrati (Fernet) con chiave derivata da `ATLAS_BACKUP_PASSWORD` o
  `ATLAS_SECRET_KEY`; conserva quella password fuori dal PC.
- **CI**: `pip-audit` sulle dipendenze Python, `npm audit --omit=dev
  --audit-level=high` sul frontend e **gitleaks** su tutta la storia. Un
  segreto committato resta nella storia anche se lo rimuovi dopo.

## Cosa non fare

- Non committare `.env`, `_local_db/`, `_backups/`, APK/IPA, keystore o chiavi.
- Non inventare numeri, risultati o recensioni nella documentazione.
- Non aggiungere dipendenze se il problema si risolve con Python/Node standard.
- Non fare push diretti su `main`: branch + PR + CI verde.
- Non disattivare un test o una regola di sicurezza per far passare la CI:
  correggi la causa o spiega perché il comportamento richiesto è cambiato.
