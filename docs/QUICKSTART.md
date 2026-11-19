# ⚡ ATLAS AI in 5 minuti (e cosa richiede davvero iOS)

Questa è la via più corta per vedere ATLAS AI funzionare. I tempi sono realistici:
dipendono dalla connessione e dal fatto che Python/Node siano già installati.

## La via più veloce: Android + backend già online

1. Apri dal telefono questo link:
   **[ATLAS-AI-android.apk](https://github.com/AhsenKurtoski/atlas-ai/releases/download/android-v3.2.0/ATLAS-AI-android.apk)**
2. Consenti l'installazione da browser e installa l'APK (release firmata, non debug).
3. Apri ATLAS AI, scegli **io** e inserisci il PIN del tuo profilo. Su
   un'installazione nuova i PIN demo sono `0000`/`1111`/`2222`; sul backend
   pubblico i PIN demo sono stati sostituiti, quindi usa quelli comunicati
dall'amministratore (non sono nel repo).
4. La build pubblica punta al backend HTTPS già attivo:
   `https://atlas-ai.tailf30c71.ts.net`.

Tempo tipico: **1–2 minuti**. Non serve compilare nulla.

> L'APK è una release interna firmata con la chiave di debug del progetto: va bene
> per uso personale e test, non per il Play Store. Per lo store serve una keystore
> dedicata e un AAB.

## iPhone/iPad: perché non esistono 5 minuti gratis

Apple non consente di installare un'app iOS non firmata. Non è un limite di ATLAS:
è una regola del sistema operativo. Le opzioni reali sono:

| Via | Tempo | Costo | Serve |
|---|---|---|---|
| Simulatore iOS su Mac | 15–25 min | gratis | Mac + Xcode |
| iPhone personale con firma gratuita | 10–20 min | gratis | Mac + Apple ID (scade ogni 7 giorni) |
| TestFlight / App Store | 30–60 min + review | 99 €/anno | Apple Developer Program + EAS |
| Build CI per simulatore | automatica | gratis | GitHub Actions (artifact `.app`, non installabile su iPhone) |

La guida completa, comandi inclusi, è in **[IOS.md](IOS.md)**.
La CI iOS del repository compila davvero l'app per iPhone **e** iPad Simulator a
ogni push; l'artifact è `ATLAS-AI-ios-simulator.zip`.

## Sviluppo locale completo (Windows/macOS/Linux)

Prerequisiti: **Python 3.11–3.13**, **Node 20+**, Git. Chromium viene installato
da Playwright.

```bash
git clone https://github.com/AhsenKurtoski/atlas-ai.git
cd atlas-ai/backend
python -m venv venv
# Windows: .\venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env        # Windows: copy .env.example .env

uvicorn main:app --host 0.0.0.0 --port 8010
```

In un secondo terminale:

```bash
cd frontend
npm ci
# Sostituisci con l'IP del PC se usi un telefono sulla stessa Wi-Fi
EXPO_PUBLIC_API_URL=http://localhost:8010 npx expo start
```

Apri l'app con una development build o un emulatore. La chat AI richiede una
chiave Gemini gratuita in `backend/.env` (`GOOGLE_API_KEY_1`); senza chiave il
backend risponde esplicitamente che l'LLM non è configurato, non inventa risposte.

### Verifica in 60 secondi

```bash
curl http://localhost:8010/          # status: ok, llm: true/false
cd backend && pytest -q             # test backend
cd frontend && npm run typecheck    # 0 errori
```

## Demo web (senza telefono)

```bash
cd backend && uvicorn main:app --port 8010
cd frontend
EXPO_PUBLIC_API_URL=http://localhost:8010 npm run export:web
```

Poi servi l'export statico:

```bash
# Windows: serve frontend/dist su :19007 (idempotente, log in backend/logs)
start-web-19007.bat
# macOS / Linux
cd frontend/dist && python3 -m http.server 19007
```

Apri `http://localhost:19007`. La web app usa lo stesso codice React Native.
Per un test automatico: `npm run test:e2e` (backend su `:8010`).

## Cosa NON è gratuito o automatico

- **iOS su device fisico**: richiede firma Apple; nessun workaround legale.
- **Push iOS**: le notifiche locali funzionano subito; le push remote richiedono
  APNs configurato su EAS. Senza APNs l'app lo dice, non finge.
- **Gmail/Calendar**: servono credenziali OAuth Google tue; senza di esse la
  funzione risponde “non configurato”.
- **Gemini**: il piano gratuito ha quote; per uso intenso serve una chiave tua.
- **Hosting 24/7**: la guida gratuita Oracle + Tailscale è in [DEPLOY_FREE.md](DEPLOY_FREE.md),
  ma nessun hosting gratuito offre una garanzia di uptime.
