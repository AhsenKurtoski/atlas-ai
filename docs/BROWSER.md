# Agente browser ATLAS

ATLAS AI non è un semplice chatbot: dal 14 novembre 2026 dispone di un **browser
Chromium headless reale**, controllato tramite Playwright. L'agente può aprire siti,
eseguire JavaScript, leggere il contenuto, cliccare, compilare moduli, scegliere opzioni,
scorrere e tornare indietro. Non usa HTML statico né risposte simulate.

---

## Architettura

```text
POST /chat (FastAPI, async)
   │
   ├─ browser_profile = slug del profilo (ContextVar)
   ├─ run_in_threadpool(ai_router.chiedi)  → non blocca l'event loop
   │      │
   │      └─ Gemini function calling
   │             │  browser_apri / clicca / scrivi / ...
   │             ▼
   │        BrowserService (facade thread-safe)
   │             │  coda di comandi
   │             ▼
   │        worker thread dedicato "atlas-browser"
   │             └─ Playwright sync API + Chromium headless
   │                   ├─ BrowserContext per profilo
   │                   ├─ page, cookie, history isolati
   │                   └─ route guard SSRF/DNS su OGNI richiesta
   │                      (navigazioni, redirect, XHR, iframe, immagini, CSS, font)
   │
   └─ risposta finale + salvataggio in memoria
```

Perché un thread dedicato: le API sincrone di Playwright non sono thread-safe e gli
endpoint FastAPI girano in un threadpool. Il worker serializza i comandi, possiede il
browser e restituisce il risultato al chiamante tramite una coda. Il modello viene
eseguito con `run_in_threadpool`, quindi una navigazione lenta non blocca gli altri
utenti.

### Sessioni

- Una sessione per **slug profilo** (`BrowserContext` separato): cookie, pagine e
  cronologia non sono mai condivisi tra membri della famiglia.
- La sessione scade dopo `BROWSER_SESSION_TTL` secondi di inattività (default 900).
- `browser_chiudi()` chiude subito il contesto del profilo.
- Un solo Chromium per processo; più profili condividono il browser ma non il contesto.
- Il testo inviato al modello è troncato a ~3,8 KB; link, campi e bottoni sono
  riassunti per mantenere il contesto gestibile.

---

## Tool disponibili

| Tool | Argomenti | Risultato |
|---|---|---|
| `browser_apri` | `url` | Titolo, URL finale, testo, link, campi, bottoni |
| `browser_vedi` | — | Snapshot aggiornato della pagina corrente |
| `browser_clicca` | `elemento` (CSS o testo) | Snapshot dopo il click |
| `browser_scrivi` | `campo`, `testo`, `invio` | Snapshot dopo la compilazione |
| `browser_seleziona` | `campo`, `valore` | Snapshot dopo la scelta |
| `browser_scorri` | `direzione` (`giu`/`su`) | Snapshot dopo lo scroll |
| `browser_indietro` | — | Snapshot della pagina precedente |
| `browser_chiudi` | — | Conferma chiusura |

Esempio di ragionamento dell'agente:

```text
Utente: "Cerca un treno Milano-Roma domani e dimmi il primo prezzo"
  → browser_apri("https://...")
  → browser_vedi()                  # legge campi e bottoni
  → browser_scrivi("Da", "Milano")
  → browser_scrivi("A", "Roma")
  → browser_clicca("Cerca")
  → browser_vedi()                  # estrae risultati reali
  → risposta con orari/prezzi trovati
```

L'agente non deve mai inventare il risultato di un click: dopo ogni azione rilegge la
pagina. Se un sito richiede login, CAPTCHA o 2FA, riporta il blocco e propone
un'alternativa.

---

## Configurazione

| Variabile | Default | Note |
|---|---|---|
| `BROWSER_ENABLED` | `true` | `false` disattiva tutti i tool browser |
| `BROWSER_HEADLESS` | `true` | `false` apre una finestra (solo debug locale) |
| `BROWSER_SESSION_TTL` | `900` | Secondi di inattività prima della chiusura |
| `BROWSER_DNS_CACHE_TTL` | `60` | Cache delle risoluzioni DNS del route guard |
| `BROWSER_NAV_TIMEOUT_MS` | `25000` | Timeout navigazione |
| `BROWSER_ACTION_TIMEOUT_MS` | `8000` | Timeout click/fill/select |
| `BROWSER_NO_SANDBOX` | `false` | Solo container isolati che lo richiedono |
| `AGENT_MAX_TOOL_TURNS` | `10` | Passi massimi di tool per risposta |
| `ALLOW_PRIVATE_FETCH` | `false` | Consente anche host privati (sconsigliato) |

Installazione (una volta per macchina/container):

```bash
cd backend
pip install -r requirements.txt
python -m playwright install chromium
# Linux/CI:
python -m playwright install --with-deps chromium
```

---

## Sicurezza

1. **SSRF e DNS**: ogni URL passa da `_request_allowed` (solo HTTP/HTTPS/WS, niente
   credenziali incorporate, blocco di loopback, reti private, link-local e metadata
   cloud). Il routing del browser applica la stessa validazione a **tutte** le
   richieste: navigazioni, redirect, iframe, immagini, CSS, font e XHR. Il DNS viene
   risolto con cache (`BROWSER_DNS_CACHE_TTL`, default 60 s) e la risoluzione fallita
   è **fail-closed**; i service worker sono disabilitati per non aggirare il guard.
   L'URL finale dopo ogni navigazione viene rivalidato. Resta una finestra teorica di
   DNS rebinding tra due risoluzioni: per isolamento forte usare un proxy egress con
   IP pinnati o una rete dedicata.
2. **Prompt injection**: il testo delle pagine è trattato come dato non attendibile.
   Il system prompt vieta di seguire istruzioni contenute nelle pagine, rivelare dati
   del profilo/server o inserire password e dati di pagamento senza conferma esplicita.
3. **Isolamento**: un `BrowserContext` per profilo; nessun cookie condiviso.
4. **Nessuna persistenza**: cookie e pagine vivono solo in memoria; non vengono scritti
   su disco. I contenuti visitati possono essere inviati a Gemini per la risposta.
5. **Azioni sensibili**: l'agente deve chiedere conferma prima di acquisti, iscrizioni,
   invio di email/moduli o inserimento di credenziali. Non è un bypass di autenticazione.
6. **Risorse**: un worker serializza le operazioni; una navigazione bloccata non deve
   poter saturare tutti i thread del server. I timeout sono configurabili.

`ALLOW_PRIVATE_FETCH=true` è pensato solo per self-hosting che devono raggiungere un
servizio interno: espone il server a richieste verso la rete locale, quindi va evitato
in produzione pubblica.

---

## Test

I test non usano mock del browser: avviano un server HTTP locale con JavaScript, form e
una seconda pagina, poi verificano il comportamento reale di Chromium.

```bash
cd backend
python -m playwright install chromium
pytest tests/test_browser.py -v
pytest tests/test_ai_loop.py -v
pytest -q                      # suite completa: 146 test
```

Copertura di `tests/test_browser.py`:

- registry con 45 tool e 8 tool browser;
- apertura pagina e lettura di titolo/testo/link/campi;
- compilazione per label e click su bottone con aggiornamento JavaScript;
- select, scroll e contenuti caricati dinamicamente;
- navigazione verso una seconda pagina e `browser_indietro`;
- chiusura sessione e errore esplicito per elemento inesistente;
- blocco SSRF con `ALLOW_PRIVATE_FETCH=false`;
- **DNS su XHR, iframe e immagini**: un dominio che risolve a 127.0.0.1 viene bloccato
  anche dopo che la pagina è stata caricata (test con server locale e DNS simulato);
- **loop Gemini** con client finto: due tool nello stesso turno, function-response
  corrette e limite `AGENT_MAX_TOOL_TURNS` rispettato (file `test_ai_loop.py`);
- sessioni isolate tra due profili;
- browser disattivato tramite `BROWSER_ENABLED=false`;
- unit test del route guard per host privati, schema `file://` e opt-in.

La CI GitHub installa Chromium con `python -m playwright install --with-deps chromium`
prima di eseguire pytest.

Guida pratica per provare tutto passo-passo (backend, browser, foto, voce, push, OAuth):
[`TESTING_GUIDE.md`](TESTING_GUIDE.md).

---

## Limiti noti

- **CAPTCHA, 2FA e anti-bot** non vengono aggirati: l'agente riporta il blocco.
- **Login**: può compilare un form, ma non deve inserire credenziali senza conferma;
  non gestisce password manager, passkey o codici 2FA.
- **Download/PDF**: i file non vengono scaricati né analizzati; il testo di un PDF nel
  browser potrebbe non essere disponibile.
- **Screenshot**: non vengono inviati al modello; il contesto è testuale (testo, link,
  campi, bottoni). Questa scelta evita di inviare immagini di pagine private a Gemini.
- **Siti molto dinamici** possono richiedere più passi; il limite è
  `AGENT_MAX_TOOL_TURNS` (default 10).
- **Un solo worker browser** per processo: richieste concorrenti vengono serializzate.
- **RAM**: Chromium consuma ~200-400 MB per processo; in container piccoli ridurre i
  worker o disabilitare il browser.
- **DNS rebinding**: la cache DNS e la validazione per richiesta riducono il rischio,
  ma non sostituiscono un proxy egress con IP pinnati in ambienti ostili.
- **Service worker** disabilitati: alcuni siti PWA potrebbero non funzionare del tutto.
- **Evoluzione dei siti**: un selettore può cambiare; l'agente riceve l'errore e può
  rileggere la pagina, ma non c'è garanzia contro redesign o blocchi geografici.

---

## Troubleshooting

| Sintomo | Causa / soluzione |
|---|---|
| `Chromium non disponibile` | Esegui `python -m playwright install chromium` nel venv del backend |
| `URL non consentito` | Host privato/loopback: usa un URL pubblico o `ALLOW_PRIVATE_FETCH=true` in locale |
| `Elemento non trovato` | Usa `browser_vedi` e clicca con un selettore CSS o un testo più preciso |
| Timeout navigazione | Aumenta `BROWSER_NAV_TIMEOUT_MS` o usa una pagina più leggera |
| Chromium non parte in Docker | Installa `--with-deps`; se il container è isolato e lo richiede, `BROWSER_NO_SANDBOX=true` |
| Sessione persa | TTL scaduto: riapri con `browser_apri` |
