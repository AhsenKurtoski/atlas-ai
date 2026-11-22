# 🗺️ Roadmap ATLAS AI

Stato al **22 novembre 2026** (v3.3.0). Le voci sono ordinate per impatto reale
sull'uso quotidiano, non per facilità. Ogni voce indica cosa manca davvero e
come verificarla.

Legenda: ✅ fatto e testato · 🟡 parziale · ⛔ non ancora iniziato

---

## Sicurezza e privacy

| Voce | Stato | Note |
|---|---|---|
| Isolamento dati per profilo | ✅ | Token Bearer + slug derivato dal token; `tests/test_multiuser.py` |
| Token OAuth Google cifrati a riposo | ✅ | AES/Fernet, migrazione automatica dei token in chiaro (v3.3.0) |
| Protezione SSRF, rate limit, audit accessi | ✅ | `net_guard.py`, slowapi, `/auth/accessi` |
| Audit delle operazioni eseguite dall'AI | ⛔ | Oggi resta il log applicativo, non un registro consultabile per profilo |
| Eliminazione account + export dati | ✅ | `/privacy/dati`, `/privacy/profilo` |

## Integrazioni Google

| Voce | Stato | Note |
|---|---|---|
| Lettura Gmail e ricerca appuntamenti | ✅ | `gmail_leggi_email`, `gmail_cerca_appuntamenti` |
| Ricerca email per mittente/data/oggetto | ✅ | `gmail_cerca_email` |
| Revoca dei permessi Google | ✅ | revoca su Google + cancellazione token locali |
| Invio email con conferma esplicita | ✅ | Bozza + conferma in app, tool di invio non esposto al modello |
| Allegati delle email | ✅ | Elenco allegati e riuso in una risposta (max 8 MB) |
| Creazione eventi / agenda | ✅ | `calendar_crea_evento`, `calendar_agenda` |
| Modifica e cancellazione eventi | ✅ | `calendar_modifica_evento`, `calendar_elimina_evento` |
| Fusi orari e sovrapposizioni | ✅ | Fusi IANA validati, avviso di sovrapposizione su creazione e modifica |

## Intelligenza artificiale

| Voce | Stato | Note |
|---|---|---|
| Memoria conversazionale | ✅ | Ultimi messaggi del profilo nel prompt |
| Memoria persistente di preferenze | ⛔ | Proposta: tool `ricorda_preferenza` / `elenca_preferenze` con store per profilo |
| Gestione contesto lungo | 🟡 | Finestra limitata agli ultimi messaggi, nessun riassunto progressivo |
| Fallback provider / rotazione chiavi | ✅ | 3 chiavi Gemini, errori quota gestiti |
| Limiti di costo API | 🟡 | Rotazione chiavi; manca un tetto giornaliero per profilo |
| Conferma prima di azioni importanti | 🟡 | Vale per i promemoria; non per invii email/eventi |

## Voce

| Voce | Stato | Note |
|---|---|---|
| Riconoscimento vocale (dettatura) | ✅ | `/chat/trascrivi` + `expo-audio` |
| Sintesi vocale delle risposte | ⛔ | Aggiungere `expo-speech` con pulsante "Ascolta" sulle risposte |

## Documenti e ricerca

| Voce | Stato | Note |
|---|---|---|
| Generazione PDF | ✅ | `/documenti/pdf` |
| Caricamento e lettura di PDF esistenti | ⛔ | Serve estrazione testo (`pypdf`) + endpoint di upload |
| Riassunto e ricerca nel contenuto | ⛔ | Dipende dalla voce precedente |
| Ricerca web con fonti | ✅ | DuckDuckGo/Wikipedia, fonti incluse nella risposta |

## Notifiche e automazioni

| Voce | Stato | Note |
|---|---|---|
| Push Android/iOS | ✅ | Expo Push, token per profilo, cleanup `DeviceNotRegistered` |
| Notifiche desktop Windows | ⛔ | Oggi solo web/PWA: nessuna notifica nativa Windows |
| Promemoria ricorrenti | 🟡 | Promemoria singoli + automazioni periodiche |
| Meteo, acqua, farmaci, prezzi, budget | ✅ | 12 job APScheduler |
| Sospensione/modifica di ogni automazione | ✅ | `/impostazioni` + `/automazioni` |

## Offline e sincronizzazione

| Voce | Stato | Note |
|---|---|---|
| Cronologia chat offline | ✅ | Cache AsyncStorage per profilo |
| Code di operazioni offline | ⛔ | Proposta: outbox persistente con retry al ritorno della rete |
| Sincronizzazione multi-dispositivo | ✅ | Chat, todo, budget e impostazioni vivono sul backend |

## Qualità

| Voce | Stato | Note |
|---|---|---|
| Suite backend | ✅ | 221 test, inclusi Chromium reale e loop agente |
| Typecheck e audit npm | ✅ | 0 errori TypeScript, 0 vulnerabilità |
| Test su dispositivi fisici | ⛔ | Solo emulatore Android e simulatore iOS finora |
| Monitoraggio errori in produzione | ⛔ | Nessun Sentry/equivalente |
| Test di carico | ⛔ | Nessun k6/Locust nel repo |

---

## Prossimi tre passi consigliati

1. **Voce completa**: sintesi vocale delle risposte (una sera di lavoro, nessun
   servizio esterno) e poi conversazione a mani libere.
2. **Google completo**: invio email con conferma + modifica/cancellazione eventi,
   con test su un account reale.
3. **Documenti**: upload PDF, estrazione testo, riassunto e ricerca — è la
   funzione che oggi manca di più rispetto a ciò che il README promette.
