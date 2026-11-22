# ✅ Funzionalità ATLAS AI: cosa è reale e cosa serve

Questa tabella è volutamente severa: una funzione è “reale” solo se esegue
un'azione o legge un dato da un servizio vero. Se manca una credenziale, l'app
risponde con un messaggio esplicito e non simula un successo.

## App e famiglia

| Funzione | iOS | Android | Web | Prerequisiti |
|---|---|---|---|---|
| Login PIN, sessione persistente, logout con revoca | ✅ | ✅ | ✅ | — |
| Profili famiglia e isolamento chat per profilo | ✅ | ✅ | ✅ | — |
| Cambio PIN dall'app (Impostazioni → Cambia PIN) con revoca sessioni | ✅ | ✅ | ✅ | profilo `io` |
| **Controllo genitore**: orari, messaggi/giorno, tool per adulti bloccati | ✅ | ✅ | ✅ | profilo `io` |
| **Cronologia chat sincronizzata** con ricerca su tutti i dispositivi | ✅ | ✅ | ✅ | backend |
| Home con dashboard, budget, todo e promemoria | ✅ | ✅ | ✅ | backend |
| Lista spesa condivisa (aggiungi/completa/elimina/pulisci) | ✅ | ✅ | ✅ | backend |
| Budget per categoria e totale mese | ✅ | ✅ | ✅ | backend |
| **Soglie di spesa** con avviso di sforamento e confronto col mese precedente | ✅ | ✅ | ✅ | profilo `io` |
| Promemoria in linguaggio naturale + notifica locale | ✅ | ✅ | ✅ | permesso notifiche |
| Notifiche push remote | ✅ con APNs | ✅ con FCM/EAS | — | EAS/APNs/FCM + device |
| Lezioni e quiz di italiano con punti/streak | ✅ | ✅ | ✅ | backend |
| Tema scuro, layout telefono/tablet, landscape | ✅ | ✅ | ✅ | — |
| PDF A4 con condivisione/salvataggio | ✅ | ✅ | ✅ download | backend |
| Foto dalla galleria in chat | ✅ | ✅ | ✅ | Gemini |
| Dettatura vocale | ✅ | ✅ | ✅ | Gemini + microfono |

## Intelligenza e servizi

| Funzione | Cosa usa | Prerequisiti | Note |
|---|---|---|---|
| Chat AI e memoria | Google Gemini | `GOOGLE_API_KEY_1` | senza chiave: avviso esplicito |
| Analisi foto/OCR | Gemini vision | chiave Gemini | immagini non salvate su disco |
| Meteo attuale e previsioni | Open-Meteo | — | gratuito, senza chiave |
| Ricerca web | DuckDuckGo (libreria + HTML) | — | risultati reali |
| Notizie | Google News RSS / NewsAPI | NewsAPI opzionale | fallback RSS |
| Wikipedia | API Wikipedia | — | lingua configurabile |
| Crypto, azioni, cambi | CoinGecko / Yahoo Finance | — | quote reali |
| Voli | Amadeus | `AMADEUS_*` | senza chiave: link reali, non finti voli |
| Traduzioni | MyMemory | — | limite gratuito |
| Calcolatrice | parser AST safe | — | nessun `eval` |
| QR code | api.qrserver.com | — | URL immagine reale |
| Gmail: leggi email | Gmail API OAuth | credenziali Google | “non configurato” senza OAuth |
| Calendar: agenda, crea, modifica, elimina evento | Calendar API OAuth | credenziali Google | evento reale, avviso sovrapposizioni |
| Gmail: invio email | Gmail API OAuth (`gmail.send`) | conferma esplicita in app | bozza + pulsante Invia |
| Gmail: allegati | Gmail API OAuth | credenziali Google | elenco e riuso in risposta |
| Ricerca nelle email per appuntamenti | Gmail API OAuth | credenziali Google | — |
| Agente browser (naviga, clicca, compila) | Chromium Playwright | `playwright install chromium` | SSRF protetto |
| Server MCP | JSON-RPC/HTTP | `MCP_SERVERS` | tool discovery e call reali |
| GitHub search/code | API GitHub | `GITHUB_TOKEN` opzionale | rate limit più alto |
| PDF | generatore interno | — | nessun servizio esterno |

## Sicurezza

| Controllo | Stato |
|---|---|
| PIN bcrypt (12 rounds), token HMAC, TTL 8h | ✅ |
| Logout con denylist del token | ✅ |
| Rate limit PIN/chat | ✅ |
| Ruoli: solo `io` crea/elimina profili e cambia i PIN | ✅ |
| Cambio PIN → sessioni già aperte di quel profilo revocate subito | ✅ |
| Profili fail-closed in produzione + backup automatico del DB locale | ✅ |
| SSRF su fetch, browser, XHR, iframe, immagini | ✅ |
| Prompt injection: pagine trattate come dati | ✅ |
| Segreti solo nel backend, `.env` ignorato | ✅ |
| Errori API senza stacktrace | ✅ |

## Limiti dichiarati

- **Nessuna app iOS installabile senza firma Apple**: la CI produce un `.app`
  per il Simulatore. Per un iPhone serve firma gratuita (7 giorni) o Apple
  Developer/TestFlight.
- **Expo Go degli store** deve essere allineato a Expo SDK 57: in caso contrario serve
  una development build.
- **CAPTCHA, 2FA e paywall** non vengono aggirati dall'agente browser.
- **Nessun hosting gratuito garantisce uptime 24/7**: vedi
  [DEPLOY_FREE.md](DEPLOY_FREE.md) per l'opzione Oracle + Tailscale e i suoi limiti.
- **Le quote Gemini gratuite** possono esaurirsi; l'app mostra l'errore reale.
- **Gli screenshot** in `screenshots/` sono della build web con lo stesso codice
  React Native; non sono mockup.
