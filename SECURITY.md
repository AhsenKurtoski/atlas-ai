# Security Policy

## Versioni supportate

| Versione | Supporto |
|---|---|
| 3.x | ✅ correzioni di sicurezza |
| < 3.0 | ❌ non supportata |

## Segnalare una vulnerabilità

**Non aprire una issue pubblica per problemi di sicurezza.**

Usa il pulsante **Report a vulnerability** nella scheda *Security* del repository
(GitHub private advisory) oppure scrivi ai maintainer indicati nel README.
Includi: versione, passi per riprodurre, impatto e, se possibile, una prova di concetto.

Risposta attesa: conferma entro 5 giorni lavorativi, correzione o mitigazione entro 30
giorni per i problemi ad alta priorità.

## Modello di minaccia

ATLAS è pensato per **una famiglia su un'istanza privata**, non come SaaS multi-tenant:

- L'accesso avviene con PIN numerico (4-8 cifre) + token di sessione firmato HMAC.
- Il PIN è pensato per essere comodo in famiglia, non per resistere a un attacco mirato
  offline. Servono HTTPS, rate limiting e PIN non banali.
- I membri della famiglia condividono lista spesa, budget, impostazioni e l'account
  Google collegato (Gmail/Calendar). Chat, punti italiano e dispositivi push sono
  invece separati per profilo.
- Solo il profilo `io` (amministratore) può creare o eliminare profili.

## Checklist per l'installazione in produzione

1. `APP_ENV=production`
2. `ATLAS_SECRET_KEY` impostata con un segreto lungo e unico (`python -c "import secrets;print(secrets.token_urlsafe(48))"`), condivisa da tutti i worker.
3. Cambiare i **PIN demo** (`0000/1111/2222/3333/4444`) con
   `POST /profili/{slug}/pin` (amministratore `io`, body `{"pin": "123456"}`) o
   aggiornando il DB. In produzione i PIN demo sono **rifiutati** sia al login sia
   in fase di cambio PIN, anche se un backup vecchio li reintroduce.
4. `CORS_ALLOWED_ORIGINS` impostato esplicitamente: in produzione, senza questa
   variabile, il CORS è **chiuso** (nessuna origine web). In sviluppo resta `*`.
   La web app servita dal PC in LAN passa dal default `PREVIEW_WEB_ORIGIN_REGEX`
   (solo loopback, reti private e nomi locali su `:19007`); `CORS_ALLOWED_ORIGIN_REGEX`
   lo sostituisce con un pattern esplicito (es. il dominio pubblico della web app).
5. HTTPS obbligatorio davanti al backend (reverse proxy) e `--proxy-headers` per l'IP reale.
6. `SCHEDULER_ENABLED=true` su **un solo processo** per host: il lock su file impedisce ai worker di duplicare i job, ma su più host serve un processo dedicato.
7. Rate limiter su Redis (`storage_uri`) se usi più processi e vuoi limiti condivisi.
8. Backup di `backend/_local_db/`: il backend ne crea uno automatico all'avvio e
   ogni 6 ore in `backend/_backups` (ultimi 14 archivi, escluso il lock).
   Ripristino: fermare il servizio, scompattare lo zip scelto dentro
   `backend/_local_db` e riavviare. Per Supabase, esporta il progetto.
9. Non committare `.env`, `_local_db/`, credenziali Firebase o token Google.
10. Aggiornare le dipendenze con regolarità (`pip list --outdated`, `npm outdated`).

## Controlli implementati

- Hash PIN bcrypt (12 rounds), confronto a tempo costante.
- **Fail closed sui profili**: in produzione, se `profiles.json` manca, è corrotto
  o parziale, non viene caricato nessun profilo (e nessun fallback ai PIN demo).
- **PIN demo bloccati in produzione** anche a livello di autenticazione, come
  difesa in profondità rispetto al solo fail closed sul file.
- **Cambio PIN** riservato all'amministratore (`POST /profili/{slug}/pin`, e
  Impostazioni → Cambia PIN nell'app), con validazione 4-8 cifre, rate limit e
  backup automatico prima della scrittura.
- **Revoca immediata delle sessioni**: ogni profilo ha un `pin_version` che
  avanza al cambio PIN. I token portano la versione con cui sono stati emessi,
  quindi tutte le sessioni aperte di quel profilo ricevono 401 al primo uso (le
  sessioni degli altri profili restano valide).
- Con Supabase, aggiungi la colonna `pin_version INTEGER NOT NULL DEFAULT 0`
  alla tabella `profiles`; in modalità locale è dentro `profiles.json`.
- **Backup automatico** del database locale con rotazione (14 archivi).
- **CORS fail closed** in produzione: solo le origini elencate esplicitamente.
- Token firmati HMAC-SHA256 con scadenza; **revoca server-side al logout** (denylist).
- Endpoint privati protetti da `Authorization: Bearer`; 401 uniforme.
- Ruoli: gestione profili riservata all'amministratore.
- Rate limiting su PIN, chat e endpoint di scrittura.
- Protezione SSRF su tutti i fetch web e sull'agente browser (`ALLOW_PRIVATE_FETCH=true` per opt-in esplicito).
- Browser: controllo DNS su **ogni** richiesta (navigazioni, redirect, iframe, immagini,
  CSS, font e XHR) con cache di 60 s e fail-closed; blocco di host privati/loopback,
  service worker disabilitati, sessioni isolate per profilo, nessuna persistenza di
  cookie su disco. Resta una finestra teorica di DNS rebinding tra due risoluzioni:
  per isolamento forte usare un proxy egress con IP pinnati.
- Il testo delle pagine è trattato come dato non attendibile per limitare il prompt injection.
- Azioni sensibili (credenziali, acquisti, invio moduli) richiedono conferma esplicita
  nel system prompt; l'agente non aggira CAPTCHA, 2FA o controlli di accesso.
- Disattivazione automatica dei token push dichiarati morti da Expo.
- Nessun dettaglio interno restituito al client negli errori 500.
- Dipendenze e segreti fuori dal repository (`.gitignore`).

## Ambito escluso

- Sicurezza fisica del dispositivo su cui gira l'app.
- Configurazione errata di reverse proxy, firewall o provider cloud.
- Servizi di terze parti (Google, Expo, Supabase, Amadeus): valgono le loro policy.
