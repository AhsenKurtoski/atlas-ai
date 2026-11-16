# Backend ATLAS AI — Guida tecnica

FastAPI 0.115 · Python 3.11-3.13 · Pydantic v2 · APScheduler · Playwright/Chromium · Supabase / fallback JSON locale

---

## 📋 Prerequisiti

- **Python 3.11, 3.12 o 3.13** (le dipendenze pinned non supportano ancora 3.15)
- `venv` incluso in Python
- *Opzionale*: progetto **Supabase** (senza → modalità locale su file JSON)
- *Opzionale*: 1–3 chiavi **Google Gemini** (chat + dettatura vocale)
- *Opzionale*: credenziali OAuth Google (Gmail + Calendar, gratuite)
- *Opzionale*: server MCP via `MCP_SERVERS`
- **Chromium** per l'agente browser (`python -m playwright install chromium`, ~130 MB)

---

## 🏁 Installazione & avvio

```powershell
py -3.12 -m venv venv            # NON usare Python 3.14/3.15
.\venv\Scripts\Activate.ps1      # macOS/Linux: python3 -m venv venv && source venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium   # una volta sola (Windows/macOS/Linux)
copy .env.example .env           # cp su macOS/Linux (opzionale)

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

✅ Verifica: <http://localhost:8000/>

```json
{
  "status": "ok",
  "profili": 5,
  "automazioni": 11,
  "ambiente": "development",
  "versione": "3.1.0",
  "db_mode": "locale",
  "notifiche": "expo",
  "llm": false
}
```

> Se la porta 8000 è occupata da un altro programma, usa `--port 8010` e configura
> `EXPO_PUBLIC_API_URL` nel frontend.

---

## 🧪 Test (146)

```bash
pytest -q                     # tutti
pytest tests/test_endpoints.py -v
pytest --cov=app --cov-report=html
```

Stato attuale: **146 passed / 0 failed** (18 test con Chromium reale + 2 del loop Gemini con client finto).

| Suite | Copre |
|---|---|
| `test_security.py` | bcrypt, validazione PIN, token, sanitizzazione |
| `test_tools.py` | calcolatrice AST, todos, budget, formule geografiche |
| `test_endpoints.py` | health, profili, auth reale, 401, chat, todos, budget, dashboard, notifiche, impostazioni, italiano, profili, Google |
| `test_mcp.py` | client MCP contro un server JSON-RPC locale |
| `test_notifications.py` | invio Expo Push (mock HTTP), ticket rifiutati, token per profilo |
| `test_google_oauth.py` | URL OAuth, state firmato, stato non configurato |
| `test_multiuser.py` | isolamento dati per profilo, ruoli, revoca token al logout |
| `test_net_guard.py` | blocco SSRF (loopback, reti private, metadata cloud) |
| `test_scheduler_lock.py` | lock inter-processo dello scheduler |
| `test_weather.py` | variabili Open-Meteo corrette, parsing meteo e previsioni |
| `test_chat_image.py` | foto in chat: PNG valido, MIME/base64/dimensioni non validi |
| `test_browser.py` | Chromium headless reale: apertura, testo, click, form, select, scroll, back, sessioni per profilo, DNS su XHR/iframe/immagini, SSRF |
| `test_ai_loop.py` | loop di function calling Gemini con client finto: tool multipli, function-response, limite turni |

---

## 🖼️ Foto in chat

`POST /chat` accetta oltre a `msg`:

```json
{
  "msg": "Che ricetta è?",
  "immagine_base64": "...",
  "immagine_mime_type": "image/jpeg"
}
```

- Formati: `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`.
- Limite: 10 MB reali (base64 max 15 MB di caratteri); oltre → HTTP 413.
- Base64 o MIME non validi → HTTP 400 con messaggio chiaro.
- La foto viene passata a Gemini come `Part.from_bytes` insieme al testo: nessuna
  descrizione simulata. Senza chiavi Gemini la risposta spiega che l'AI non è attiva.
- L'app comprime la foto (`quality 0.65`) e invia JPEG per compatibilità iOS/Android.

## 🌐 Agente browser

ATLAS non è un chatbot che si limita a leggere HTML: dispone di un **Chromium headless
reale** (Playwright) che esegue JavaScript, conserva i cookie e interagisce con i siti.

| Tool | Cosa fa |
|---|---|
| `browser_apri(url)` | Apre una pagina e restituisce titolo, testo, link, campi e bottoni |
| `browser_vedi()` | Rilegge la pagina attuale (dopo click, scroll o caricamento dinamico) |
| `browser_clicca(elemento)` | Click su selettore CSS o testo visibile |
| `browser_scrivi(campo, testo, invio)` | Compila input/textarea, opzionalmente invia con Invio |
| `browser_seleziona(campo, valore)` | Sceglie un'opzione in un menu select |
| `browser_scorri(direzione)` | Scorre per caricare contenuti lazy |
| `browser_indietro()` | Torna alla pagina precedente |
| `browser_chiudi()` | Chiude la sessione del profilo e libera memoria |

Come funziona:

- un **worker thread dedicato** possiede Playwright (le API sync non sono thread-safe);
- ogni profilo ha un `BrowserContext` separato: cookie e pagine non si mescolano;
- la sessione scade dopo `BROWSER_SESSION_TTL` (default 900 s) o con `browser_chiudi`;
- il testo restituito al modello è limitato a ~3,8 KB per non saturare il contesto;
- il numero di turni di tool per risposta è `AGENT_MAX_TOOL_TURNS` (default 10), così
  l'agente può fare più passi (apri → leggi → clicca → rileggi);
- **ogni richiesta** (navigazione, redirect, XHR, iframe, immagini, CSS, font) passa da
  un controllo DNS con cache: se un dominio risolve a un IP non pubblico viene bloccata.
  I service worker sono disabilitati per non aggirare il route guard.

Variabili: `BROWSER_ENABLED`, `BROWSER_HEADLESS`, `BROWSER_SESSION_TTL`,
`BROWSER_DNS_CACHE_TTL`, `BROWSER_NAV_TIMEOUT_MS`, `BROWSER_ACTION_TIMEOUT_MS`,
`BROWSER_NO_SANDBOX` (solo container isolati), `AGENT_MAX_TOOL_TURNS`. Dettagli e limiti
in [`docs/BROWSER.md`](../docs/BROWSER.md); guida pratica in
[`docs/TESTING_GUIDE.md`](../docs/TESTING_GUIDE.md).

**Sicurezza**: ogni richiesta HTTP(S) passa da `_request_allowed` (schema, host e DNS con
cache); il routing blocca navigazioni, redirect, iframe, immagini, CSS, font e XHR verso
host privati, loopback o domini che risolvono a IP non pubblici. La risoluzione fallita
è fail-closed. Il testo delle pagine è dato non attendibile e il system prompt vieta di
eseguire istruzioni contenute nelle pagine o inserire credenziali/pagamenti senza conferma.

## 🔐 Autenticazione

1. `POST /auth/pin` con `{"profilo": "io", "pin": "0000"}` → `{auth: true, token, expires_in}`
2. Invia `Authorization: Bearer <token>` su tutti gli endpoint privati.

Il token è **firmato HMAC-SHA256** (`payload.firma`, TTL 8h configurabile): non richiede
storage condiviso, quindi funziona anche con gunicorn a più worker e dopo un riavvio del
processo. Il segreto viene letto da `ATLAS_SECRET_KEY` o generato una volta in
`_local_db/.atlas_secret`.

Endpoint privati: `/chat`, `/chat/trascrivi`, `/todos*`, `/budget*`, `/dashboard`,
`/notifiche*`, `/impostazioni`, `/automazioni`, `/italiano*`, `/profili` (POST/DELETE),
`/integrazioni/google*`.

Pubblici: `/`, `/profili` (GET), `/auth/pin`.

---

## 🗺️ Endpoints

| Metodo | Path | Auth | Descrizione |
|---|---|---|---|
| GET | `/` | ❌ | Health: profili, automazioni, DB, LLM |
| GET | `/profili` | ❌ | Elenco profili (nome, livello, lingua — **senza** hash PIN) |
| POST | `/profili` | ✅ 👑 | Crea profilo (solo amministratore `io`) |
| DELETE | `/profili/{slug}` | ✅ 👑 | Elimina profilo (solo admin, non sé stessi) |
| POST | `/auth/pin` | ❌ | Verifica PIN → token (5/min per IP) |
| GET | `/auth/me` | ✅ | Profilo della sessione + scadenza |
| POST | `/auth/logout` | ✅ | Revoca il token corrente (denylist fino a scadenza) |
| POST | `/chat` | ✅ | Messaggio AI (testo + foto opzionale) con function calling |
| POST | `/chat/trascrivi` | ✅ | Audio base64 → testo (Gemini) |
| GET | `/dashboard` | ✅ | KPI: todo, spesa mese, dispositivi push, punti |
| GET | `/todos?filtro=pending` | ✅ | Lista todo |
| POST | `/todos` | ✅ | Aggiungi todo |
| POST | `/todos/{numero}/completa` | ✅ | Completa il task n (1-based) |
| GET | `/budget` | ✅ | Totale + dettaglio per categoria |
| POST | `/budget/spesa` | ✅ | Registra spesa |
| POST | `/notifiche/registra` | ✅ | Registra token push del dispositivo |
| DELETE | `/notifiche/registra?token=` | ✅ | Disattiva token |
| POST | `/notifiche/test` | ✅ | Invia notifica di test |
| GET | `/notifiche/dispositivi` | ✅ | Dispositivi registrati |
| GET/POST | `/impostazioni` | ✅ | Automazioni, notifiche, soglie |
| GET | `/automazioni` | ✅ | Job pianificati + prossima esecuzione |
| GET | `/italiano/lezione` | ✅ | Lezione del giorno per livello |
| GET | `/italiano/quiz` | ✅ | Quiz del giorno (senza soluzioni) |
| POST | `/italiano/quiz/valuta` | ✅ | Valutazione + punti |
| GET | `/italiano/progressi` | ✅ | Punti, streak, classifica |
| GET | `/integrazioni/google/stato` | ✅ | Configurato / connesso / email |
| GET | `/integrazioni/google/url` | ✅ | URL consenso OAuth |
| GET | `/integrazioni/google/callback` | ❌ | Callback OAuth (state firmato) |
| POST | `/integrazioni/google/disconnetti` | ✅ | Scollega account |

---

## 👤 Profili e PIN

I profili di default hanno **hash bcrypt reali** (verificati dai test):

| Slug | Nome | PIN |
|---|---|---|
| `io` | Tu (Admin) | `0000` |
| `mamma` | Mamma | `1111` |
| `papa` | Papà | `2222` |
| `fratello1` | Fratello 1 | `3333` |
| `fratello2` | Fratello 2 | `4444` |

In produzione cambia i PIN: crea i profili con `POST /profili` (hash generato dal server)
oppure aggiorna `pin_hash` sulla tabella `profiles`.

---

## 💽 Modalità DB

| Modalità | Come si attiva | Dove salva |
|---|---|---|
| **SUPABASE** | `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` | Postgres remoto |
| **LOCALE** | chiavi assenti/non raggiungibili | `backend/_local_db/*.json` (scrittura atomica) |

Tabelle usate: `profiles`, `messages`, `family_todos`, `family_expenses`,
`italian_progress`, `push_tokens`, `app_settings`, `revoked_tokens`.
Esegui `supabase_schema.sql` nell'SQL editor di Supabase per crearle.

---

## ⏰ Automazioni (11)

La città usata da briefing e ombrello smart si imposta con `ATLAS_CITY` (default `Milano`).

Avviate dal lifespan (nessuna chiamata di rete all'avvio). Ogni job rispetta gli
interruttori in `/impostazioni` e invia notifiche ai dispositivi registrati.

| Job | Trigger | Cosa fa |
|---|---|---|
| Lezione italiano | cron 7:30 | Invia la lezione del giorno a chi ha livello A1–B2 |
| Briefing giornaliero | cron 8:00 | Meteo + todo pendenti + spesa del mese |
| Controllo email | ogni 15 min | Legge Gmail se collegata e notifica |
| Promemoria acqua | ogni 2h (8–22) | Notifica idratazione |
| Price watcher | ogni 6h | Avvisa se BTC/ETH si muovono oltre la soglia |
| Report settimanale | lun 9:00 | Budget + todo |
| Classifica studio | ven 18:00 | Classifica punti italiano |
| Ombrello smart | cron 6:45 | Avvisa se pioverà (Open-Meteo) |
| Promemoria pillola | cron 21:00 | Disattivo di default |
| Smart calendar | ogni ora | Agenda del giorno da Google Calendar |
| Crypto tracker | ogni ora | Log prezzi (senza spam di notifiche) |

---

## 🔔 Notifiche

- **Expo Push Service** (primario, gratuito, nessuna chiave): richiede che l'app abbia un
  `projectId` EAS (`eas init`) per ottenere un token `ExponentPushToken[...]`.
- **Firebase** (secondario, opzionale): solo per token FCM/APNs nativi, con
  `FIREBASE_CREDENTIALS` che punta al file di servizio.
- **Promemoria locali** nell'app: funzionano sempre, anche senza backend.

Se non ci sono dispositivi registrati, gli endpoint rispondono con un messaggio esplicito
(non simulano un invio riuscito).

---

## 🧭 Server MCP

Imposta un JSON con i server (trasporto Streamable HTTP / JSON-RPC 2.0):

```bash
MCP_SERVERS={"files":{"url":"http://127.0.0.1:9000/mcp"},"remoto":{"url":"https://mcp.example.com/mcp","headers":{"Authorization":"Bearer ..."}}}
```

L'AI può usare:
- `mcp_elenca_server` — server configurati
- `mcp_elenca_tool(server)` — tool esposti
- `mcp_chiama_tool(server, tool, argomenti_json)` — esecuzione reale

In più restano disponibili fetch web, GitHub REST e l'agente browser Chromium senza server MCP.

---

## 🔐 Gmail + Calendar (gratuito)

1. Crea un client OAuth **Web** su <https://console.cloud.google.com/apis/credentials>
2. Abilita **Gmail API** e **Google Calendar API**
3. Aggiungi il redirect esatto della porta usata dal backend (es. `http://localhost:8010/integrazioni/google/callback`)
4. Imposta `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (e `GOOGLE_REDIRECT_URI` se diverso)
5. Finché l'app OAuth non è verificata da Google, aggiungi gli indirizzi della famiglia
   come **Test users** nella schermata OAuth consent (altrimenti Google blocca l'accesso)

Nell'app: Impostazioni → «Connetti Gmail (OAuth)». I token vengono salvati in
`app_settings` e mai esposti al client.

---

## 🚀 Produzione

```bash
export APP_ENV=production
export ATLAS_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export CORS_ALLOWED_ORIGINS="https://atlas.miodominio.it"
gunicorn -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000 main:app
```

Note:
- I token sono firmati HMAC e il logout li revoca tramite denylist (`revoked_tokens`).
- **Scheduler**: con più worker solo il processo che ottiene `_local_db/.scheduler.lock`
  esegue i job; gli altri servono le API. Su più host avvia lo scheduler in un solo
  processo dedicato (`SCHEDULER_ENABLED=false` sugli altri).
- Il rate limiter usa storage in memoria **per worker**: per limiti esatti usa Redis
  (`storage_uri="redis://..."` nel `Limiter`).
- Dietro reverse proxy imposta `--proxy-headers` in uvicorn/gunicorn per l'IP reale.
- `ALLOW_PRIVATE_FETCH=true` solo se vuoi che gli strumenti web e il browser possano
  leggere IP privati/locali (default: bloccati per sicurezza).
- L'agente browser usa ~200-400 MB di RAM per Chromium: in container limita i worker e
  installa le dipendenze di sistema con `python -m playwright install --with-deps chromium`.
- In produzione il backend avvisa se i PIN demo sono ancora attivi, se manca
  `ATLAS_SECRET_KEY` o se CORS è aperto a `*`.
- Non committare `.env` né `_local_db/`.

## 👥 Multi-utente

- Chat, punti italiano e push sono **per profilo** (lo slug arriva dal token, mai dal body).
- Todo, budget, impostazioni e account Google sono **condivisi** dalla famiglia.
- Solo `io` può creare/eliminare profili (403 per gli altri).
- Una istanza = una famiglia; per più famiglie servono istanze separate o `family_id`.

## 🛡️ Sicurezza di rete

I tool `mcp_web_fetch_markdown`, `mcp_web_fetch_json`, la lettura pagine e i tool
`browser_*` bloccano URL con IP privati, loopback, link-local (metadata cloud) e
credenziali incorporate; il browser applica il controllo DNS a **ogni** richiesta
(navigazioni, redirect, iframe, immagini, CSS, font e XHR).
`ALLOW_PRIVATE_FETCH=true` disattiva il blocco per self-hosting particolari.
