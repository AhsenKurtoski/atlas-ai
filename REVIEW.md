# ATLAS AI v3.0 — Code Review completa

Data: 14 novembre 2026
Perimetro: backend FastAPI, app React Native/Expo, tool AI, client MCP, notifiche, account, scheduler, database, test e documentazione.

---

## 1. Verdetto

Il progetto aveva **difetti bloccanti** (login impossibile, dipendenze non installabili,
endpoint privati senza autenticazione, funzioni che simulavano successi) e diverse
funzionalità dichiarate nei README ma inesistenti. Dopo gli interventi:

| Area | Prima | Dopo |
|---|---|---|
| Installazione backend | ❌ dipendenze in conflitto | ✅ `pip install` pulito |
| Login PIN | ❌ hash bcrypt inventati → nessun PIN valido | ✅ hash reali verificati |
| Sessione | ❌ token in RAM, persi con più worker/riavvio | ✅ token HMAC stateless |
| Endpoint privati | ❌ todos/budget/chat aperti | ✅ Bearer obbligatorio + 401 |
| Notifiche | ❌ solo log "mock", nessun invio | ✅ Expo Push reale + promemoria locali |
| MCP | ❌ 7 placeholder che dicevano "non disponibile" | ✅ client MCP JSON-RPC reale |
| Browser / agente web | ❌ solo fetch HTTP, nessuna interazione | ✅ Chromium headless reale, 8 tool, sessioni per profilo |
| Gmail/Calendar | ❌ risposte finte di successo | ✅ OAuth reale o messaggio "non configurato" |
| Voli | ❌ risultati simulati | ✅ Amadeus o link di ricerca reali |
| Traduzioni | ❌ restituiva un prompt | ✅ MyMemory reale |
| Notizie | ❌ API key "demo" → errore | ✅ NewsAPI o Google News RSS |
| Azioni | ❌ solo Alpha Vantage demo | ✅ Yahoo Finance di fallback |
| Impostazioni | ❌ switch solo UI | ✅ persistite e applicate dallo scheduler |
| Profili | ❌ "Aggiungi profilo" non faceva nulla | ✅ creazione/eliminazione reali con PIN |
| Italiano | ❌ schermata statica, punteggi finti | ✅ lezioni, quiz, punti e streak reali |
| Sessione app | ❌ riavvio → nessun ripristino | ✅ ripristino validato + logout |
| Test backend | 54 dichiarati (con `verify_pin` patchato) | 146 reali (18 Chromium + 2 loop Gemini), nessun patch dell'auth |
| Typecheck frontend | dichiarato 0 | ✅ verificato 0 |
| Multi-utente | ruoli assenti, logout non revocava | ✅ isolamento per profilo, admin-only, revoca reale |
| Open source | nessuna LICENSE radice, CI assente | ✅ MIT, SECURITY, CONTRIBUTING, CI |

---

## 2. Bug critici trovati e corretti

### Backend

1. **`requirements.txt` impossibile da installare** — `supabase==2.5.1` e
   `google-genai==2.14.0` richiedevano versioni di `httpx` incompatibili con il pin
   `0.27.2`; `passlib[bcrypt]` generava un traceback a ogni hash. Risolto con pin
   compatibili e bcrypt diretto (rimosso passlib).
2. **PIN demo non funzionanti** — gli hash in `DEFAULT_PROFILES` e in
   `supabase_schema.sql` erano stringhe inventate: `verify_pin("0000", hash)` dava False.
   I test lo mascheravano con un monkey-patch di `verify_pin` che accettava qualsiasi PIN.
   Ora hash bcrypt reali e test senza patch.
3. **Token in memoria per processo** — con 4 worker gunicorn il token creato da un worker
   non era valido sugli altri; a ogni riavvio tutti gli utenti venivano disconnessi.
   Sostituiti con token HMAC firmati (`create_access_token` / `decode_access_token`).
4. **Endpoint privati senza auth** — `/todos`, `/budget`, `/chat`, `/profili` non
   verificavano il token (e `/chat` lo accettava opzionale). Aggiunta dipendenza
   `get_current_profile` + 401 uniforme.
5. **`get_todos` eseguiva la query due volte** (`q.execute()` in `reversed` e nel
   controllo successivo) → doppia chiamata a Supabase e risultati incoerenti.
6. **Indice todo 1-based vs documentazione 0-based** → completava il task sbagliato.
   Ora 1-based coerente ovunque (API, tool, UI) e documentato.
7. **Chiavi Gemini con nome sbagliato** — il codice leggeva `GEMINI_KEY_i`, README e
   `.env.example` dicevano `GOOGLE_API_KEY_i`: con la configurazione documentata l'AI non
   partiva. Ora entrambi gli alias sono accettati.
8. **CORS env mismatch** — codice usava `CORS_ALLOWED_ORIGINS`, README `CORS_ORIGINS`.
   Ora alias accettati e wildcard gestita correttamente con `allow_credentials`.
9. **`.env.example` mancante** nonostante i README lo citassero. Creato.
10. **`app/core/settings.py` mancante** (citato nella struttura README). Creato come unico
    punto di lettura delle env.
11. **`web_search` crashava senza `duckduckgo-search`** (`DDGS=None` chiamato) e non aveva
    fallback. Ora libreria opzionale + fallback HTML reale.
12. **`get_time_timezone` dipendeva da worldtimeapi** (spesso offline). Ora `zoneinfo`
    locale: preciso e senza rete.
13. **Errori di encoding su Windows** — log con emoji → `UnicodeEncodeError` in cascata.
    Ora stdout UTF-8 con fallback.
14. **Scrittura JSON non atomica** nel DB locale → rischio file troncati. Ora
    write-then-`os.replace`.
15. **Scheduler faceva chiamate di rete all'avvio** (`run_test=True` con price watcher) e i
    job si limitavano a loggare. Ora 11 job reali, nessuna rete al boot, rispetto delle
    impostazioni.
16. **`fetch_profiles` ignorava le modifiche locali** in modalità file. Ora i profili
    locali sono persistiti e fusi con i default.
17. **`italian_module.py`** conteneva un quiz in macedone (i profili sono albanesi) e
    funzioni placeholder. Sostituito con contenuti reali A1–C1 in `app/tools/italian.py`.
18. **`google_tools.py`** restituiva "evento creato con successo" senza creare nulla.
    Ora delega all'integrazione reale o dice che l'account non è collegato.
19. **`main.py` non poteva usare `from __future__ import annotations`** con slowapi:
    FastAPI interpretava i body come query param (422). Rimosso l'import futuro e
    documentato il perché.

### Frontend

20. **Riavvio app = nuovo login** — il token era salvato ma mai ripristinato; nessuna
    schermata iniziale condizionale. Ora ripristino validato con `/auth/me`, cache offline,
    logout reale e uscita automatica su 401.
21. **Crash potenziale su ripristino** — `MainTabs` e le schermate leggevano
    `route.params.profileId`, assente quando la navigazione parte dal contesto. Ora
    fallback a `useAuth()`.
22. **Dati finti in Home/Budget** — `emailCount = todos.length + 2` e cinque spese
    pre-caricate. Rimossi: solo dati dal backend.
23. **Dettatura vocale simulata** — registrava l'audio e aggiungeva
    "🎤 [Messaggio vocale inviato]" senza inviarlo. Ora upload base64 → Gemini → testo nel
    campo, con errori reali.
24. **PIN limitato a 4 cifre** — il backend accetta 4–8; un PIN di 6 cifre creato da
    Impostazioni non era digitabile. Ora 4–8 con validazione.
25. **`fetch()` diretta in HomeScreen** — violava l'architettura e non gestiva gli errori.
    Ora passa da `ApiService`.
26. **Tipi AsyncStorage sovrascritti** da due shim `.d.ts` duplicati, che nascondevano i
    tipi reali del pacchetto. Rimossi.
27. **`MainTabs.tsx` duplicato e morto** (3 tab, mai importato): rimosso.
28. **Nessun identificativo di build** in `app.json` (iOS/Android) e nessun permesso
    microfono/notifiche: le build store sarebbero fallite o l'audio non avrebbe chiesto
    permesso. Aggiunti bundle id, package, scheme, plugin e permessi.
29. **URL backend errato su emulatore Android** (`localhost` = emulatore stesso). Aggiunto
    `10.0.2.2`.
30. **Switch Impostazioni senza effetto**, Gmail/Calendar non collegabili, nessun logout,
    nessuna gestione profili. Tutto implementato e persistito.
31. **Italiano non funzionante** (pulsanti inerti, punteggi hardcoded). Ora lezione,
    quiz con valutazione, punti, streak e classifica reali.
32. **Scheduler duplicato con più worker** — ogni processo avviava gli stessi job
    (notifiche duplicate). Aggiunto lock inter-processo: un solo worker esegue i job.
33. **Token push morti mai rimossi** — Expo `DeviceNotRegistered` veniva solo loggato.
    Ora il token viene disattivato e non riceve più invii.
34. **SSRF nei tool web** — `mcp_web_fetch_*` e la lettura pagine potevano raggiungere
    `127.0.0.1`, reti private e metadata cloud. Aggiunto `net_guard` con validazione
    DNS/IP e redirect, opt-in esplicito per la rete locale.
35. **Logout non invalidava il token** — restava valido 8h anche dopo l'uscita.
    Ora c'è una denylist server-side (`revoked_tokens`) controllata a ogni richiesta.
36. **Qualsiasi membro poteva eliminare gli altri profili** — ora solo l'admin `io`
    può creare/eliminare profili (403 per gli altri, UI coerente).
37. **Licenza Expo nel frontend e nessuna LICENSE alla radice** — sostituita con
    licenza MIT del progetto; aggiunti SECURITY.md, CONTRIBUTING.md e CI GitHub Actions.
38. **Memoria chat duplicata** — il messaggio corrente veniva salvato prima di leggere
    la memoria, quindi compariva due volte nel prompt. Ora la memoria è letta prima.
39. **Health incoerente con più worker** — `automazioni` dipendeva dal worker che
    rispondeva (0 sui worker senza scheduler). Ora riporta il totale definito e
    `scheduler_attivo`.
40. **Race sul logout lato app** — il token veniva cancellato in parallelo alla
    disattivazione del push, che quindi poteva rispondere 401. Ora l'ordine è garantito.
41. **Meteo rotto con Open-Meteo** — l'API ha rinominato `temperature_max/min` in
    `temperature_2m_max/min`: ogni richiesta meteo reale rispondeva HTTP 400 e
    l'app mostrava “servizio non raggiungibile”. Nomi corretti e test di regressione;
    verificato dal vivo (Milano e Roma).
42. **Città delle automazioni fissa su Milano** — ora configurabile con `ATLAS_CITY`.
43. **Invio foto dalla galleria** — implementato end-to-end: picker iOS/Android, compressione JPEG,
    upload base64, validazione MIME/dimensione e invio a Gemini vision. La foto non viene salvata
    su disco dal backend; senza chiave Gemini la risposta lo dice esplicitamente.

---

## 3. Funzioni verificate una per una

| Funzione | Verifica | Esito |
|---|---|---|
| Foto dalla galleria → Gemini vision | test endpoint (PNG valido, MIME/base64 errati) + bundle iOS/Android | ✅ codice reale; vision da provare con chiave Gemini |
| Agente browser | 18 test con Chromium su server locale (click, form, select, scroll, back, DNS su XHR/iframe/immagini, SSRF, sessioni) | ✅ reale |
| Loop Gemini | 2 test con client finto (tool multipli, function-response, limite turni) | ✅ reale |
| Health `/` | uvicorn reale + curl | ✅ 200, 5 profili, 11 automazioni, db_mode |
| Login PIN | curl `0000`, `1111` + 146 test | ✅ token valido, PIN errato rifiutato |
| Protezione endpoint | curl senza token | ✅ 401 |
| Todos CRUD | curl + test | ✅ aggiunta, lista, completamento |
| Budget | curl + test | ✅ totale e percentuali |
| Dashboard | curl | ✅ KPI reali |
| Chat | test senza chiavi | ✅ messaggio esplicito, nessun crash |
| Trascrizione | test audio non valido / senza chiavi | ✅ 400 / 503 espliciti |
| Notifiche | test HTTP su endpoint Expo mock | ✅ invio, ticket rifiutato, token per profilo, token disattivato |
| MCP | server JSON-RPC locale nei test | ✅ initialize, tools/list, tools/call, errori |
| Google OAuth | test URL/state | ✅ URL corretto, state firmato, non configurato esplicito |
| Impostazioni | curl + test | ✅ merge parziale persistito |
| Italiano | curl + test | ✅ lezione, quiz senza soluzioni, valutazione, progressi |
| Profili | test crea/login/elimina | ✅ + protezione admin |
| Automazioni | curl | ✅ 11 job con prossima esecuzione |
| Typecheck frontend | `tsc --noEmit` | ✅ 0 errori |
| Bundle Android/iOS | `expo export` | ✅ Android OK · ✅ iOS OK |

---

## 4. Cosa richiede ancora una configurazione (non è un bug)

Queste funzioni sono **codice reale**, ma dipendono da credenziali che solo il proprietario
può creare. In assenza, l'app lo dice chiaramente:

| Funzione | Cosa serve | Costo |
|---|---|---|
| Chat AI e dettatura | `GOOGLE_API_KEY_1` da Google AI Studio | gratuito (free tier) |
| Push remote | `eas init` → `extra.eas.projectId` | gratuito |
| Gmail + Calendar | client OAuth Google + redirect URI | gratuito |
| Ricerca voli in tempo reale | `AMADEUS_CLIENT_ID/SECRET` (self-service) | free tier |
| Notizie NewsAPI (opzionale) | `NEWSAPI_KEY` | free tier |
| Database remoto | progetto Supabase | free tier |
| Server MCP | un server MCP raggiungibile | dipende dal server |
| Agente browser | Chromium (`playwright install chromium`) | gratuito |

**Promemoria locali, todo, budget, italiano, profili, impostazioni e automazioni locali
funzionano senza nessuna credenziale.**

---

## 5. Raccomandazioni rimanenti (non implementate)

Priorità alta:
1. **Upgrade Expo SDK 51 → 57/58**: l'Expo Go degli store supporta solo l'SDK più recente
   e SDK 51 è del 2024. Le build attuali sono verificate (bundle iOS/Android, doctor 17/17)
   ma per un'app pubblicabile oggi serve la migrazione (RN 0.74→0.8x, React 19,
   Reanimated 4, sostituzione di `expo-av` con `expo-audio`, NativeWind).
2. **Test end-to-end su device reale** (Android + iOS) per permessi notifiche, microfono,
   galleria e flusso OAuth: non eseguibili in questo ambiente.
3. **Redis per il rate limiter** in produzione multi-worker: ora il limite è per processo.
4. **Migrazioni DB versionate** (Alembic/Supabase migrations) invece di un unico `.sql`.
5. **Scheduler su più host**: il lock copre i worker dello stesso host; per più istanze
   serve un processo scheduler dedicato o un lock distribuito.
6. **Dipendenze frontend**: `npm audit` segnala 53 vulnerabilità (24 high, 2 critical)
   quasi tutte nel tooling Expo/Metro di SDK 51; l'upgrade SDK è la correzione strutturale.

7. **Anti-bot e CAPTCHA**: l'agente browser non li aggira (scelta etica e legale); siti
   molto protetti restano non automatizzabili. Documentare all'utente il blocco reale.
8. **Prompt injection web**: il system prompt e il route guard riducono il rischio, ma
   nessun LLM è immune. Per azioni distruttive serve sempre conferma umana.
9. **DNS rebinding**: il route guard valida ogni richiesta e usa una cache di 60 s; un
   attaccante che cambia DNS tra due risoluzioni potrebbe ancora sfruttare la finestra.
   Per isolamento forte usare un proxy egress con IP pinnati o una rete dedicata.

Priorità media:
10. **Streaming delle risposte chat** (oggi risposta completa): migliora la percezione di
   velocità sui testi lunghi.
11. **Cifratura dei messaggi** a riposo se il DB è condiviso.
12. **Backup automatico** di `_local_db` in modalità locale.
13. **Ruff/mypy** in CI (non sono tra le dipendenze: aggiungerli come dev dependency).
14. **Accessibilità**: label per screen reader su icone e pulsanti.
15. **i18n** della UI (oggi solo italiano, coerente col prodotto).

Priorità bassa:
16. Rimuovere `expo-blur` se non verrà usato.
17. Documentare le quote dei servizi gratuiti usati (Gemini, CoinGecko, MyMemory).

---

## 6. Verifiche eseguite (comandi e risultati)

```text
backend:  python -m venv venv (Python 3.12) + pip install -r requirements.txt   → OK
backend:  python -m pytest -q                                                  → 146 passed
backend:  pytest tests/test_browser.py -v                                      → 18 passed (Chromium reale)
backend:  pytest tests/test_ai_loop.py -v                                      → 2 passed (client Gemini finto)
backend:  python -m playwright install chromium                                → OK (Chromium 159)
backend:  uvicorn main:app --port 8010 + curl /, /auth/pin, /todos, /budget,
          /dashboard, /italiano/lezione, /impostazioni, /automazioni            → 200 / 401 attesi
frontend: npm install                                                          → OK
frontend: npx tsc --noEmit                                                     → 0 errori
frontend: npx expo export --platform android / ios                             → vedi esito sotto
frontend: npx expo-doctor                                                      → 17/17 checks passed
frontend: npx expo config --type introspect                                    → permessi foto/mic/ATS presenti
backend:  POST /chat con PNG valido                                            → 200 + avviso no chiavi
backend:  POST /chat con MIME/base64 errati                                    → 400
```

Esito export bundle:
```text
npx expo export --platform android   → OK, 1181 moduli, bundle 3.25 MB
npx expo export --platform ios       → OK, 1181 moduli, bundle 3.24 MB
```

Note di ambiente: la porta 8000 di questa macchina è occupata da un'altra applicazione
(AhsenDS), quindi lo smoke test è stato eseguito sulla porta 8010. Non è un problema del
progetto: basta avviare uvicorn su una porta libera e allineare `EXPO_PUBLIC_API_URL`.

---

## 7. Giudizio per area

| Area | Voto | Nota |
|---|---|---|
| Architettura | 7/10 | Buona separazione; manca lo streaming e le migrazioni |
| Sicurezza | 8/10 | bcrypt, HMAC, revoca token, SSRF browser, rate limit; manca Redis condiviso |
| Qualità codice | 7/10 | Tipizzato, testato; restano moduli legacy tollerati per compatibilità |
| Affidabilità | 8/10 | Fallback locali reali, errori espliciti, nessun finto successo |
| UX/UI | 7/10 | Design invariato; ora tutti i controlli fanno qualcosa |
| Documentazione | 9/10 | README, docs/BROWSER.md, SECURITY e REVIEW allineati al codice |
