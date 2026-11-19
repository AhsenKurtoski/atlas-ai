# Architettura di ATLAS AI

Documento tecnico per chi modifica il progetto. Descrive i componenti reali,
dove vivono i dati e quali sono i punti di estensione.

## Vista d'insieme

```
┌───────────────────────────┐        HTTP/JSON + Bearer         ┌──────────────────────────────┐
│ App React Native (Expo 51)│ ────────────────────────────────▶ │ FastAPI (Python 3.11-3.13)   │
│ iOS · Android · Web       │ ◀──────────────────────────────── │ uvicorn, 50 endpoint REST    │
│ NativeWind · AsyncStorage │      chat, PIN, push, PDF         │ slowapi, Pydantic v2         │
└───────────────────────────┘                                   └──────────────┬───────────────┘
                                                                               │
             ┌─────────────────────────────────────────────────────────────────┼──────────────────────┐
             ▼                                                                 ▼                      ▼
   ┌──────────────────┐                                            ┌────────────────────┐   ┌──────────────────┐
   │ Gemini (AI)      │                                            │ Dati               │   │ Automazioni      │
   │ ai_router.py     │                                            │ Supabase           │   │ APScheduler      │
   │ function calling │                                            │   oppure JSON      │   │ 12 job + push    │
   └──────────────────┘                                            │   _local_db        │   └──────────────────┘
                                                                   └────────────────────┘
```

- **Un solo backend** serve tutti i dispositivi; l'app non parla mai direttamente
  con il database.
- **Modalità locale di default**: senza `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` i dati
  vanno in file JSON atomici dentro `backend/_local_db/`. Con Supabase configurato
  le stesse funzioni usano le tabelle Postgres, con fallback locale se la rete cade.
- **Stato condiviso minimo**: l'app tiene solo token, slug del profilo e cache
  dell'ultimo `/auth/me`; tutto il resto viene dal backend.

## Backend

| Modulo | Responsabilità |
|---|---|
| `main.py` | App FastAPI, CORS, dipendenza `get_current_profile`, tutti gli endpoint, gestori d'errore |
| `app/ai_router.py` | Chiamate Gemini, rotazione chiavi, function calling, trascrizione audio |
| `app/scheduler.py` | 12 automazioni periodiche (briefing, meteo, email, ecc.) con lock di processo |
| `app/notifiche.py` | Invio Expo Push / FCM e disattivazione dei token morti |
| `app/core/database.py` | Accesso dati con decoratore `@resilient` (Supabase → JSON locale) |
| `app/core/security.py` | bcrypt per PIN/codici, token HMAC con scadenza e `pin_version`, codici di recupero |
| `app/core/auth_guard.py` | Blocco progressivo per profilo e registro accessi (file in `_local_db`) |
| `app/core/settings.py` | Lettura centralizzata delle variabili d'ambiente, CORS, percorsi |
| `app/core/net_guard.py` | Protezione SSRF per fetch web, browser, XHR/iframe/immagini |
| `app/core/schemas.py` | Modelli Pydantic di richiesta/risposta |
| `app/services/privacy.py` | Esportazione dati e cancellazione del profilo |
| `app/services/backup.py` | Backup cifrati di `_local_db` con rotazione e CLI di ripristino |
| `app/services/browser.py` | Worker Chromium, sessioni isolate per profilo, route guard |
| `app/services/google_oauth.py` | OAuth Gmail/Calendar con `state` firmato |
| `app/tools/*` | Tool esposti al modello (famiglia, finanza, viaggi, italiano, browser, MCP) |

### Flusso di autenticazione

1. `POST /auth/pin` con `{profilo, pin}`.
2. Prima della verifica: controllo del blocco progressivo (`auth_guard.lockout_status`).
3. bcrypt confronta il PIN; un errore incrementa il contatore e può bloccare il profilo.
4. Un successo azzera il contatore e restituisce un token
   `<payload>.<firma HMAC>` che contiene slug, scadenza e `pin_version`.
5. Ogni endpoint privato dipende da `get_current_profile`, che verifica firma,
   scadenza, denylist dei token revocati e `pin_version` del profilo.
6. Cambio PIN, recupero con codice e "esci da tutti i dispositivi" avanzano
   `pin_version`: tutti i token precedenti diventano invalidi.

Il codice di recupero è monouso: dopo l'uso l'hash viene rimosso dal profilo.

### Dati e persistenza

- **Locale** (`ATLAS_DB_DIR`, default `backend/_local_db`): `profiles.json`,
  `messages.json`, `family_todos.json`, `family_reminders.json`,
  `family_expenses.json`, `italian_progress.json`, `push_tokens.json`,
  `app_settings.json`, `revoked_tokens.json`, `auth_lockout.json`, `access_log.json`.
- **Supabase**: stesse entità in tabelle; lo schema è in `backend/supabase_schema.sql`.
  Aggiungi `pin_version`, `recovery_hash` e `recovery_created_at` alla tabella `profiles`.
- **Backup**: `backend/_backups/atlas-local-db-*.zip.enc`, cifrati AES/Fernet,
  ultimi 14. Ripristino con `python -m app.services.backup decrypt`.
- **Log**: `backend/logs/`, rotazione già configurata.

### CORS e rete

`cors_origins()` elenca le origini esplicite; `cors_origin_regex()` copre la web
app servita dal PC su `:19007` quando l'IP della LAN cambia (loopback, 10.x,
192.168.x, 172.16-31.x, nomi macchina e `.local`). In produzione il default è
chiuso: senza `CORS_ALLOWED_ORIGINS` nessuna origine web è autorizzata.

## Frontend

| File | Ruolo |
|---|---|
| `App.tsx` | `AuthContext`, ripristino sessione, blocco automatico, navigazione |
| `src/config.ts` | URL backend (env → origine pagina → hostUri Expo → loopback) e costanti |
| `src/services/api.ts` | Client tipizzato, timeout per tipo di richiesta, gestione 401 |
| `src/services/notifications.ts` | Push Expo, notifiche locali, promemoria |
| `src/screens/*` | Profili, Home, Chat, Italiano, Budget, Impostazioni, Lista spesa, PDF, PIN, blocco |

### URL del backend

1. `EXPO_PUBLIC_API_URL` se impostata (build dedicate e CI).
2. **Web**: stesso host della pagina, porta `8010` (o `EXPO_PUBLIC_BACKEND_PORT`,
   `8000` quando la pagina è servita da `expo start` sulla 8081). Così la web app
   in LAN continua a funzionare quando il router cambia l'IP del PC.
3. Expo Go: IP del bundler.
4. Emulatore Android: `10.0.2.2`; altrove `localhost`.

### Sessione e blocco

Il token è in `AsyncStorage`. Dopo 5 minuti di inattività, o al ritorno dal
background oltre la soglia, `App.tsx` mostra `LockScreen` e chiede il PIN: un PIN
corretto emette un token nuovo. Su iOS Safari non esiste accesso al Keychain:
per una build nativa si può sostituire lo storage con `expo-secure-store`.

## Deploy

- **PC di casa (default)**: `backend/start-atlas.bat` avvia backend `:8010`,
  web app statica `:19007` e, se configurato, il tunnel. La cartella Startup di
  Windows richiama lo stesso script (`scripts/install-autostart.ps1`).
- **Cloud gratis**: `docs/DEPLOY_FREE.md` (Oracle Always Free + Tailscale Funnel).
- **App mobile**: EAS build per Android/iOS; la web app non richiede store.

## Scelte e limiti noti

- Il fallback JSON è **fail closed** in produzione: profili mancanti o corrotti
  non vengono sostituiti dai PIN demo.
- Il rate limiter è in memoria (un processo). Con più worker serve Redis.
- Il blocco progressivo e il registro accessi sono file locali: su più host
  servirebbe una tabella condivisa.
- L'agente browser e lo scheduler consumano CPU/RAM sul PC: restano disattivabili
  con `BROWSER_ENABLED=false` e `SCHEDULER_ENABLED=false`.
