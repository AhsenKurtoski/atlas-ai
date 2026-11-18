# Contribuire ad ATLAS AI

Grazie per l'interesse! Questo documento spiega come preparare l'ambiente, cosa
viene considerato accettabile e come proporre una modifica.

## Prima di iniziare

- Apri una **issue** per discutere cambiamenti importanti (nuovi servizi, modifiche
  all'API, al DB o all'esperienza utente).
- Per i bug di sicurezza segui [SECURITY.md](SECURITY.md): **non** aprire issue pubbliche.
- Licenza del progetto: MIT (vedi [LICENSE](LICENSE)). Con una pull request accetti
  che il tuo contributo sia distribuito con la stessa licenza.

## Ambiente di sviluppo

### Backend

```bash
cd backend
# Windows: py -3.12 -m venv venv    (NON usare Python 3.14/3.15)
# macOS/Linux: python3 -m venv venv
.\venv\Scripts\activate             # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # Chromium per i test browser
copy .env.example .env      # opzionale: senza .env parte in modalità locale
uvicorn main:app --reload --port 8000
```

Richiede **Python 3.11-3.13** (le dipendenze pinned non supportano 3.15).

### Frontend

```bash
cd frontend
npm install
npx expo start
```

Richiede **Node 20+**. Per il typecheck: `npm run typecheck`.

## Verifiche obbligatorie prima di una PR

```bash
cd backend && pytest -q          # 186 test, inclusi 18 Chromium reali + 2 loop Gemini
cd frontend && npm run typecheck
```

La CI esegue gli stessi comandi. Una PR che rompe i test o il typecheck non viene
unita.

## Regole del progetto

1. **Niente dati finti o successi simulati.** Se una funzione non è configurata deve
   dirlo esplicitamente e spiegare come attivarla. Non restituire "ok" se non è
   successo nulla.
2. **Nessun servizio a pagamento obbligatorio.** Le integrazioni devono avere un piano
   gratuito o un fallback reale (es. link di ricerca) e restare opzionali.
3. **Nessun segreto nel repository.** Chiavi e token vanno in `.env` (ignorato) o nel
   secret store della piattaforma.
4. **Privacy per profilo.** Chat, token push e progressi sono per profilo; lista spesa,
   budget e impostazioni sono condivisi dalla famiglia. Non mischiare i due livelli.
5. **Compatibilità mobile.** Ogni modifica al frontend deve funzionare su Android e iOS
   (Expo SDK 51) e mantenere il design esistente.
6. **Nessuna nuova dipendenza senza motivo.** Preferisci la libreria standard o
   quello che è già installato.

## Stile

- Python: type hint dove possibile, funzioni piccole, errori gestiti, log strutturato.
- TypeScript: tipi espliciti nelle API (`src/services/api.ts`), niente `any` non
  giustificato.
- Italiano per i messaggi utente, inglese per nomi tecnici quando è la convenzione
  del file.

## Pull request

1. Fork + branch descrittivo (`fix/logout-token`, `feat/...`).
2. Messaggi di commit chiari, al presente.
3. Aggiorna README/REVIEW se cambi comportamento, endpoint o variabili d'ambiente.
4. Descrivi nella PR: problema, soluzione, verifiche eseguite e cosa **non** hai potuto
   testare (es. push su device fisico, OAuth reale).
5. Non includere file generati (`node_modules`, `venv`, build, `.expo`, log).
