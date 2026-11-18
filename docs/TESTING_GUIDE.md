# Guida di test passo-passo

Questa guida serve a verificare **tutto** su Windows, macOS o Linux: backend, agente
browser, foto, voce, notifiche, OAuth e app mobile. Ogni comando è pronto da copiare.

> Regola d'oro: se una funzione richiede una chiave e non è configurata, ATLAS deve
> dirlo esplicitamente. Non deve mai inventare una risposta o un successo.

---

## 0. Prerequisiti

| Strumento | Versione | Verifica |
|---|---|---|
| Python | 3.11–3.13 | `python --version` |
| Node.js | 20+ | `node --version` |
| npm | incluso con Node | `npm --version` |
| Git | qualsiasi recente | `git --version` |
| Chromium Playwright | installato al passo 1 | `python -m playwright --version` |
| Chiave Gemini (opzionale ma consigliata) | free tier | <https://aistudio.google.com/apikey> |

Su Windows usare **PowerShell** o **Git Bash**. Nei comandi sotto, il percorso del
progetto è `C:\Users\anelk\Desktop\Progetti Personali\atlas-ai-main\atlas-ai-main`;
sostituiscilo con il tuo.

---

## 1. Backend: installazione

```powershell
cd "C:\Users\anelk\Desktop\Progetti Personali\atlas-ai-main\atlas-ai-main\backend"
py -3.12 -m venv venv            # NON usare Python 3.14/3.15: i pacchetti pinned sono per 3.11-3.13
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Su macOS/Linux:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Crea il file di configurazione:

```powershell
copy .env.example .env
notepad .env
```

Aggiungi almeno:

```dotenv
GOOGLE_API_KEY_1=la_tua_chiave_gemini
```

Senza chiave il backend parte e tutti i test locali passano, ma la chat risponderà
`⚠️ Nessuna chiave Gemini valida...`: è il comportamento corretto, non un bug.

---

## 2. Backend: test automatici

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
```

Risultato atteso:

```text
185 passed
```

Test mirati:

```powershell
# 18 test con Chromium reale (click, form, XHR, iframe, immagini, DNS, SSRF)
.\venv\Scripts\python.exe -m pytest tests/test_browser.py -v

# 2 test del loop Gemini con client finto (nessuna chiave necessaria)
.\venv\Scripts\python.exe -m pytest tests/test_ai_loop.py -v

# Hardening PIN, backup del DB locale e CORS (nessuna rete, nessun dato reale)
.\venv\Scripts\python.exe -m pytest tests/test_profiles_hardening.py -v

# Solo il test DNS su XHR/iframe/immagini
.\venv\Scripts\python.exe -m pytest tests/test_browser.py::TestBrowserReale::test_blocca_dns_xhr_iframe_e_immagini -v

# Solo i test della cache/fail-closed DNS
.\venv\Scripts\python.exe -m pytest tests/test_browser.py::TestSicurezzaBrowser -v
```

Se compare `Chromium non disponibile`, riesegui:

```powershell
python -m playwright install chromium
```

---

## 3. Backend: avvio e health check

La porta 8000 su questo PC è spesso occupata: usa **8010**.

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8010
```

In un secondo terminale:

```powershell
curl.exe http://localhost:8010/
curl.exe http://localhost:8010/health   # health check leggero per i monitor
```

Risposta attesa (valori indicativi):

```json
{
  "status": "ok",
  "profili": 5,
  "automazioni": 12,
  "scheduler_attivo": true,
  "ambiente": "development",
  "db_mode": "locale",
  "notifiche": "expo",
  "llm": true
}
```

`llm: false` significa che manca la chiave Gemini: chat e voce non possono rispondere,
ma il resto funziona.

---

## 4. Frontend: avvio

```powershell
cd frontend
npm install
$env:EXPO_PUBLIC_API_URL="http://192.168.1.50:8010"   # IP del PC sulla Wi-Fi
npx expo start
```

Su macOS/Linux:

```bash
cd frontend
npm install
EXPO_PUBLIC_API_URL=http://192.168.1.50:8010 npx expo start
```

Apri l'app con Expo Go o con una development build. Il telefono e il PC devono essere
sulla stessa rete Wi-Fi.

### Nota importante su Expo Go

Il progetto usa **Expo SDK 51**. L'Expo Go degli store supporta solo l'SDK più recente:
se non si apre, crea una development build:

```powershell
npm install -g eas-cli
eas login
cd frontend
eas init
eas build --profile development --platform android
```

Per iOS serve un account Apple e `eas build --profile development --platform ios`
(solo macOS per il simulatore, EAS cloud per il device).

---

## 5. Login e test manuali di base

1. Apri l'app: scegli il profilo **io**.
2. PIN demo: **0000**. Altri profili demo: `mamma` → `1111`, `papa` → `2222`.
3. Se il PIN non funziona, controlla di aver avviato il backend giusto e che
   `backend/_local_db/profiles.json` esista (viene creato al primo avvio).
4. Vai su **Chat**.

### Checklist rapida

| Test | Azione | Risultato atteso |
|---|---|---|
| Health | `curl.exe http://localhost:8010/` | `status: ok` |
| Login | profilo `io`, PIN `0000` | entri nella Home |
| Chat testo | “Ciao, chi sei?” | risposta reale (con chiave Gemini) |
| Foto | 🖼️ → scegli foto → invia | ATLAS descrive/legge la foto |
| Voce | tieni premuto 🎤 → parla → rilascia | testo trascritto nella casella |
| Todo | “Aggiungi latte alla lista” | appare nella lista |
| Budget | “Ho speso 12 euro per pranzo” | spesa registrata |
| Meteo | “Che tempo fa a Milano?” | temperatura reale Open-Meteo |
| Browser | “Apri https://example.com e dimmi il titolo” | `Example Domain` |
| Browser multi-step | “Apri https://news.ycombinator.com e dimmi i primi 3 titoli” | titoli reali |
| Browser + form | “Apri https://www.wikipedia.org, cerca ‘Roma’ e riassumi” | risultati reali |
| Logout | Impostazioni → Esci | torni ai profili; il token è revocato |

---

## 6. Test manuale dell'agente browser

Apri la Chat e prova questi prompt **uno alla volta**, aspettando la risposta:

1. **Lettura semplice**
   > Apri https://example.com e dimmi titolo e primo paragrafo.

   Atteso: titolo `Example Domain` e testo reale della pagina.

2. **Sito dinamico / lista**
   > Apri https://news.ycombinator.com e riporta i primi 3 titoli con il punteggio.

   Atteso: tre titoli e punteggi letti dalla pagina; nessun titolo inventato.

3. **Ricerca con form**
   > Apri https://www.wikipedia.org, scrivi “Roma” nel campo di ricerca, premi Invio e riassumi il primo risultato.

   Atteso: l'agente compila il campo, invia e legge la pagina dei risultati.

4. **Click e navigazione**
   > Apri https://example.com, clicca “More information...” e dimmi cosa contiene la pagina.

   Atteso: click reale sul link e lettura della pagina IANA.

5. **Controllo di un blocco**
   > Apri http://127.0.0.1:8010/ e dimmi cosa vedi.

   Atteso: `URL non consentito` (protezione SSRF). Non deve aprire il backend.

6. **Chiusura sessione**
   > Chiudi il browser.

   Atteso: conferma di chiusura; la sessione viene ricreata al prompt successivo.

Se un selettore non viene trovato, chiedi ad ATLAS di rileggere la pagina: userà
`browser_vedi` e potrà correggere il tiro.

### Cosa NON aspettarti

- CAPTCHA, 2FA, login con password o paywall non vengono aggirati.
- Non inserisce credenziali o dati di pagamento senza una tua conferma esplicita.
- I siti possono cambiare layout: un selettore può smettere di funzionare.
- Non scarica file e non invia screenshot al modello: il contesto è testuale.

---

## 7. Foto dalla galleria

1. In Chat tocca 🖼️.
2. Concedi il permesso alla galleria (iOS: Foto; Android: file/immagini).
3. Scegli una foto, aggiungi una didascalia se vuoi.
4. Tocca ↑.
5. Atteso: la foto viene compressa, inviata e analizzata da Gemini; la cronologia
   locale conserva solo il testo, non il file.

Test di errore: scegli un file non immagine o troppo grande (>10 MB): il backend
risponde 400/413 con un messaggio chiaro.

---

## 8. Voce

1. Tieni premuto 🎤 e parla.
2. Rilascia.
3. Atteso: il testo compare nella casella di input; poi invialo.

Senza `GOOGLE_API_KEY_1` la trascrizione risponde 503 con un messaggio esplicito.

---

## 9. Notifiche

### Locali (funzionano subito)

Impostazioni → Notifiche → attiva i promemoria. Su Android 13+ concedi
`POST_NOTIFICATIONS`; su iOS accetta il prompt.

### Push remote

1. `cd frontend && eas init` per creare `extra.eas.projectId`.
2. Su EAS aggiungi le credenziali **FCM** (Android) e **APNs** (iOS) per le build standalone.
3. Avvia l'app su un device fisico (le push non arrivano su simulatore iOS).
4. Impostazioni → Notifiche → “Invia notifica di test”.
5. Atteso: `Notifica inviata a 1 dispositivo/i` e notifica sul telefono.

Se non ci sono dispositivi: `Nessun dispositivo registrato` — non è un finto successo.

---

## 10. Gmail e Calendar

1. Google Cloud Console → credenziali OAuth **Web**.
2. Abilita Gmail API e Calendar API.
3. Redirect: `http://localhost:8010/integrazioni/google/callback`.
4. Nel `.env`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.
5. Aggiungi gli account della famiglia come **Test users** nell'OAuth consent screen.
6. Nell'app: Impostazioni → “Connetti Gmail (OAuth)”.
7. Prova: “Leggi le ultime 3 email” e “Crea un evento domani alle 18”.

Senza credenziali l'app mostra “non configurato”, non una risposta finta.

---

## 11. MCP

Nel `backend/.env`:

```dotenv
MCP_SERVERS={"files":{"url":"http://127.0.0.1:9000/mcp"},"remoto":{"url":"https://mcp.example.com/mcp","headers":{"Authorization":"Bearer ..."}}}
```

Riavvia il backend e chiedi: “Elenca i server MCP e i loro tool”. Verifica che i tool
siano davvero raggiungibili; se il server è spento, l'errore deve essere esplicito.

---

## 12. Test di sicurezza browser (DNS su XHR/iframe/immagini)

Il test automatico chiave è:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests/test_browser.py::TestBrowserReale::test_blocca_dns_xhr_iframe_e_immagini -v
```

Cosa fa:

1. avvia un server HTTP locale con una pagina che, al click, lancia una `fetch`, carica
   un'immagine e crea un iframe verso `evil.example`;
2. carica la pagina con `ALLOW_PRIVATE_FETCH=true` (il server è su 127.0.0.1);
3. disattiva l'opt-in e simula un DNS che risolve `evil.example` → `127.0.0.1`;
4. clicca: il route guard blocca **tutte e tre** le richieste prima che raggiungano
   il server; il test verifica che nessun path `/xhr`, `/img`, `/iframe` sia arrivato.

Altri test utili:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_browser.py::TestSicurezzaBrowser -v
.\venv\Scripts\python.exe -m pytest tests/test_ai_loop.py -v
```

---

## 13. CI GitHub

Dopo ogni push su `main`, apri:

<https://github.com/AhsenKurtoski/atlas-ai/actions>

Devono essere verdi tutti i workflow:

- **CI / Backend (pytest, Python 3.12)** — installa Chromium e esegue 185 test;
- **CI / Frontend (TypeScript)** — `npm ci` + `tsc --noEmit`;
- **E2E / Web smoke** — avvia FastAPI, esporta il web e verifica login, lista spesa e generazione PDF nel browser;
- **iOS Build** — genera il progetto iOS e compila l'app per il simulatore su macOS;
- **Android APK** — compila l'APK, lo installa e lo avvia su un emulatore Android, poi pubblica la release.

Se il job backend fallisce, apri il log del passo “Test” e cerca il primo `FAILED`:
non ignorare un test rosso. Se fallisce l'installazione di Chromium, verifica
`python -m playwright install --with-deps chromium`.

---

## 14. Troubleshooting

| Sintomo | Causa | Soluzione |
|---|---|---|
| `Chromium non disponibile` | browser non scaricato | `python -m playwright install chromium` |
| `URL non consentito` | host privato/loopback | usa URL pubblico; `ALLOW_PRIVATE_FETCH=true` solo in locale |
| `Elemento non trovato` | selettore o testo cambiati | chiedi di rileggere la pagina (`browser_vedi`) |
| `Timeout navigazione` | sito lento | aumenta `BROWSER_NAV_TIMEOUT_MS` |
| Chat senza risposta AI | manca la chiave | imposta `GOOGLE_API_KEY_1` e riavvia |
| `Sessione scaduta` (401) | token scaduto/revocato | torna ai profili e reinserisci il PIN |
| Expo Go “incompatible” | SDK 51 vs store | development build o upgrade SDK |
| Porta 8000 occupata | altro servizio | usa `--port 8010` e aggiorna `EXPO_PUBLIC_API_URL` |
| Push non arriva | manca projectId/FCM/APNs | `eas init` + credenziali EAS + device fisico |
| Nessun dispositivo registrato | token push assente | attiva le notifiche nell'app e riprova |

---

## 15. Checklist finale

- [ ] `pytest -q` → 185 passed
- [ ] `pytest tests/test_browser.py -v` → 18 passed
- [ ] `pytest tests/test_ai_loop.py -v` → 2 passed
- [ ] `npx tsc --noEmit` → 0 errori
- [ ] `npm run export:web` → export completato
- [ ] `npm run test:e2e` → 1 passed (backend su :8010)
- [ ] `curl.exe http://localhost:8010/` → `status: ok`
- [ ] login `io` / `0000`
- [ ] chat testo con Gemini
- [ ] foto dalla galleria
- [ ] dettatura vocale
- [ ] browser: `example.com` + `news.ycombinator.com`
- [ ] blocco `http://127.0.0.1:8010/`
- [ ] notifica locale
- [ ] push su device (se configurata)
- [ ] OAuth Gmail/Calendar (se configurato)
- [ ] CI GitHub verde

Se un punto fallisce, riporta comando, output e passi fatti: il messaggio d'errore
di ATLAS è progettato per dire cosa manca, senza simulare nulla.
