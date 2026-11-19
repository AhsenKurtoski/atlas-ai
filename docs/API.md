# API di ATLAS AI

Base URL locale: `http://127.0.0.1:8010` (produzione dietro tunnel: il dominio
Tailscale). Documentazione interattiva: `/docs` (Swagger) e `/redoc`.

Tutti gli endpoint privati richiedono `Authorization: Bearer <token>`; senza
token o con token scaduto/revocato rispondono `401` con
`{"status": "error", "message": "..."}`. Gli errori di validazione sono `422`.

## Pubblici

| Metodo | Percorso | Note |
|---|---|---|
| `GET` | `/` | Stato completo: profili, automazioni, DB, LLM |
| `GET` | `/health` | Health check leggero per monitor e uptime |
| `GET` | `/profili` | Elenco profili (nome, livello, lingua). Nessun hash |
| `GET` | `/privacy/informativa` | Informativa privacy e tempi di conservazione |
| `POST` | `/auth/pin` | `{profilo, pin}` → token. 429 se bloccato |
| `POST` | `/auth/recupero` | `{profilo, codice, nuovo_pin}` → token, consuma il codice |
| `GET` | `/integrazioni/google/callback` | Callback OAuth (redirect all'app) |

## Autenticazione e sessione

| Metodo | Percorso | Note |
|---|---|---|
| `GET` | `/auth/me` | Profilo del token e scadenza |
| `POST` | `/auth/logout` | Revoca il token corrente (denylist) |
| `POST` | `/auth/logout-tutti` | Avanza `pin_version`: chiude **tutte** le sessioni |
| `GET` | `/auth/accessi?profilo=` | Registro accessi (proprio; admin può scegliere) |

## Profili (amministratore `io`)

| Metodo | Percorso | Note |
|---|---|---|
| `POST` | `/profili` | Crea profilo e restituisce il codice di recupero una volta |
| `DELETE` | `/profili/{slug}` | Elimina un membro (non `io`, non se stesso) |
| `POST` | `/profili/{slug}/pin` | Cambia PIN, revoca le sessioni del profilo |
| `POST` | `/profili/{slug}/recupero` | Rigenera il codice di recupero (visibile una volta) |

## Privacy

| Metodo | Percorso | Note |
|---|---|---|
| `GET` | `/privacy/dati` | Export JSON con `Content-Disposition` e `no-store` |
| `DELETE` | `/privacy/profilo` | Cancella profilo e dati personali (non `io`) |

## Chat e contenuti

| Metodo | Percorso | Note |
|---|---|---|
| `POST` | `/chat` | `{msg, immagine_base64?, immagine_mime_type?}` |
| `POST` | `/chat/trascrivi` | Audio base64 → testo (Gemini) |
| `POST` | `/documenti/pdf` | Genera un PDF A4, restituisce base64 |

## Famiglia

| Metodo | Percorso | Note |
|---|---|---|
| `GET` | `/dashboard` | KPI della Home |
| `GET` | `/todos?filtro=` | Lista condivisa (`filtro=da_fare` per i pendenti) |
| `POST` | `/todos` | `{task, assegnato_a}` |
| `POST` | `/todos/{n}/completa` | Indice 1-based, come in UI |
| `DELETE` | `/todos/{n}` | Indice 1-based |
| `GET` | `/promemoria` | Promemoria attivi del profilo |
| `DELETE` | `/promemoria/{id}` | Annulla |
| `POST` | `/promemoria/{id}/programmato` | Conferma notifica locale pianificata |
| `GET` | `/budget` | Totale e dettaglio per categoria |
| `POST` | `/budget/spesa` | `{importo, categoria, descrizione}` |

## Notifiche e impostazioni

| Metodo | Percorso | Note |
|---|---|---|
| `POST` | `/notifiche/registra` | Registra token push del dispositivo |
| `DELETE` | `/notifiche/registra?token=` | Disattiva il token |
| `POST` | `/notifiche/test` | Notifica di prova |
| `GET` | `/notifiche/dispositivi` | Dispositivi collegati |
| `GET` | `/impostazioni` | Automazioni, notifiche, soglie |
| `POST` | `/impostazioni` | Patch parziale |
| `GET` | `/automazioni` | Job scheduler e prossime esecuzioni |

## Italiano

| Metodo | Percorso | Note |
|---|---|---|
| `GET` | `/italiano/lezione?livello=` | Lezione del giorno + progresso |
| `GET` | `/italiano/quiz?livello=&n=` | Domande senza risposte corrette |
| `POST` | `/italiano/quiz/valuta` | Correzioni e aggiornamento punteggio |
| `GET` | `/italiano/progressi` | Propri progressi e classifica famiglia |

## Google

| Metodo | Percorso | Note |
|---|---|---|
| `GET` | `/integrazioni/google/stato` | Configurato/connesso |
| `GET` | `/integrazioni/google/url` | URL di consenso OAuth |
| `POST` | `/integrazioni/google/disconnetti` | Revoca il collegamento |

## Esempi

```bash
# Login
curl -s -X POST http://127.0.0.1:8010/auth/pin \
  -H "Content-Type: application/json" \
  -d '{"profilo":"io","pin":"123456"}'

# Chiamata autenticata
TOKEN="<token>"
curl -s http://127.0.0.1:8010/dashboard -H "Authorization: Bearer $TOKEN"

# Export dei propri dati
curl -s -OJ http://127.0.0.1:8010/privacy/dati -H "Authorization: Bearer $TOKEN"
```

## Limiti e rate limiting

| Endpoint | Limite |
|---|---|
| `/auth/pin`, `/auth/recupero` | 5/minuto per IP + blocco progressivo per profilo |
| `/chat` | 20/minuto |
| `/privacy/dati`, `/privacy/profilo` | 5/minuto |
| Resto | 30-240/minuto secondo l'endpoint |

I limiti sono per processo (`memory://`): con più worker configura Redis in
`limiter = Limiter(..., storage_uri=...)`.
