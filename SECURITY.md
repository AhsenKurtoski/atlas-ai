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
3. Cambiare i **PIN demo** (`0000/1111/2222/3333/4444`) con `POST /profili` o aggiornando il DB; all'avvio in produzione il backend segnala i PIN ancora invariati.
4. `CORS_ALLOWED_ORIGINS` impostato esplicitamente (il default `*` è accettato solo in sviluppo).
5. HTTPS obbligatorio davanti al backend (reverse proxy) e `--proxy-headers` per l'IP reale.
6. `SCHEDULER_ENABLED=true` su **un solo processo** per host: il lock su file impedisce ai worker di duplicare i job, ma su più host serve un processo dedicato.
7. Rate limiter su Redis (`storage_uri`) se usi più processi e vuoi limiti condivisi.
8. Backup di `backend/_local_db/` (modalità locale) o del progetto Supabase.
9. Non committare `.env`, `_local_db/`, credenziali Firebase o token Google.
10. Aggiornare le dipendenze con regolarità (`pip list --outdated`, `npm outdated`).

## Controlli implementati

- Hash PIN bcrypt (12 rounds), confronto a tempo costante.
- Token firmati HMAC-SHA256 con scadenza; **revoca server-side al logout** (denylist).
- Endpoint privati protetti da `Authorization: Bearer`; 401 uniforme.
- Ruoli: gestione profili riservata all'amministratore.
- Rate limiting su PIN, chat e endpoint di scrittura.
- Protezione SSRF su tutti i fetch web e sull'agente browser (`ALLOW_PRIVATE_FETCH=true` per opt-in esplicito).
- Browser: blocco di redirect/iframe/XHR verso host privati, sessioni isolate per profilo,
  nessuna persistenza di cookie su disco; il testo delle pagine è trattato come dato non
  attendibile per limitare il prompt injection.
- Azioni sensibili (credenziali, acquisti, invio moduli) richiedono conferma esplicita
  nel system prompt; l'agente non aggira CAPTCHA, 2FA o controlli di accesso.
- Disattivazione automatica dei token push dichiarati morti da Expo.
- Nessun dettaglio interno restituito al client negli errori 500.
- Dipendenze e segreti fuori dal repository (`.gitignore`).

## Ambito escluso

- Sicurezza fisica del dispositivo su cui gira l'app.
- Configurazione errata di reverse proxy, firewall o provider cloud.
- Servizi di terze parti (Google, Expo, Supabase, Amadeus): valgono le loro policy.
