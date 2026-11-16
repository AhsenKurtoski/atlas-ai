# 📲 Installare ATLAS AI — Android, iPhone, iPad e tablet

ATLAS AI è un'app **React Native / Expo**. L'APK Android è già pronta; per iPhone
serve una firma Apple (gratuita con un Mac e un Apple ID, oppure TestFlight/App Store
con Apple Developer Program). Questa guida è pensata per essere seguita senza
conoscere Xcode o EAS.

> **Demo account**: `io` / `0000` (admin), `mamma` / `1111`, `papa` / `2222`.
> Cambia i PIN prima di usare l'app con la tua famiglia.

---

## ⚡ La via più veloce

| Dispositivo | Cosa scaricare | Tempo |
|---|---|---|
| **Android (telefono o tablet)** | [APK ATLAS AI](https://github.com/AhsenKurtoski/atlas-ai/releases/download/android-v3.1.0/ATLAS-AI-android.apk) | 1 minuto |
| **iPhone / iPad** | TestFlight o build firmata (vedi sotto) | 10 minuti + account Apple |
| **Mac (simulatore iPhone/iPad)** | Xcode + `npx expo run:ios` | 15 minuti, gratis |
| **Sviluppo su telefono** | Expo Go / development build | 2 minuti |

L'app ha bisogno del **backend ATLAS** raggiungibile. L'APK pubblicata punta a:

```
https://atlas-ai.tailf30c71.ts.net
```

Se usi un fork, il backend deve essere raggiungibile in **HTTPS** (o sulla LAN per
una build di sviluppo) e devi ricompilare con `EXPO_PUBLIC_API_URL` corretto.

---

## 🤖 Android — installazione dell'APK

### Telefono o tablet Android

1. Apri dal dispositivo il link diretto:
   **[ATLAS-AI-android.apk](https://github.com/AhsenKurtoski/atlas-ai/releases/download/android-v3.1.0/ATLAS-AI-android.apk)**
   (oppure la [pagina della release](https://github.com/AhsenKurtoski/atlas-ai/releases/tag/android-v3.1.0)).
2. Tocca **ATLAS-AI-android.apk** (circa 156 MB).
3. Se Chrome chiede il permesso, scegli **Imposta** → **Consenti da questa fonte**.
   Su Android 13+ il percorso può essere **Installa app sconosciute**.
4. Apri il file scaricato e tocca **Installa**.
5. Apri **ATLAS AI**, scegli il profilo e inserisci il PIN.
6. Concedi notifiche e microfono quando richiesto (servono per promemoria e dettatura).

Se Play Protect mostra un avviso, è normale: l'APK è firmata con la chiave di debug
del progetto, non con una chiave Play Store. Tocca **Installa comunque** e verifica
che la fonte sia il repository GitHub ufficiale.

### Tablet Android

L'APK è la stessa. Su tablet il layout passa automaticamente a due colonne e i
contenuti restano leggibili; non serve una versione separata. Se il tablet non ha
il Play Store, abilita l'installazione da browser come sopra.

### Ricompilare l'APK

La release viene rigenerata automaticamente da GitHub Actions a ogni modifica del
frontend (workflow `Android APK`). Per compilarla in locale:

```bash
cd frontend
npm ci
npx expo prebuild --platform android --no-install
cd android
./gradlew assembleDebug
# APK: frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

Per una build **distribuibile** (non debug) usa EAS:

```bash
npm install -g eas-cli
eas login
eas build --platform android --profile preview   # APK interno
eas build --platform android --profile production # AAB per il Play Store
```

---

## 🍎 iOS — la guida semplice

Ci sono tre strade. Scegli quella giusta in base a cosa hai a disposizione.

### A. iPhone personale, gratis, con un Mac e un Apple ID

Questa è la strada **senza abbonamento** (la firma scade ogni 7 giorni).

1. Serve un **Mac** con **Xcode** installato (App Store) e **CocoaPods** (`pod --version`).
2. Collega l'iPhone al Mac e sbloccalo; su iPhone tocca **Fidati di questo computer**.
3. Apri il progetto:
   ```bash
   cd frontend
   npm install
   npx expo prebuild --platform ios
   npx expo run:ios --device
   ```
4. Xcode chiede il team: scegli il tuo **Apple ID personale** in
   **Signing & Capabilities** (Xcode → Settings → Accounts).
5. Al primo avvio su iPhone, se compare “Sviluppatore non verificato”, vai in
   **Impostazioni → Generali → VPN e gestione dispositivo → Trust**.
6. L'app resta installata; dopo 7 giorni va rifirmata con Xcode.

> La firma gratuita richiede un Mac e un Apple ID. Non è possibile installare
> un'app iOS firmata partendo da Windows o Linux: Apple non lo consente.

### B. TestFlight / App Store — la strada per tutta la famiglia

Serve **Apple Developer Program** (99 €/anno) e un account EAS. È la via più
semplice per installare su più iPhone/iPad senza cavo.

```bash
cd frontend
npm install -g eas-cli
eas login
eas init                       # crea il projectId EAS
eas build --platform ios --profile production
eas submit --platform ios      # carica su App Store Connect
```

Poi, su App Store Connect:

1. Crea l'app con bundle id **`com.atlasai.family`**.
2. In **TestFlight**, aggiungi i membri della famiglia come tester.
3. Invia l'invito: si installa **TestFlight** dall'App Store, si apre il link e si
   tocca **Installa**. Non serve Xcode.
4. Per la distribuzione pubblica serve la revisione Apple.

Le push iOS richiedono una chiave **APNs** caricata su EAS; senza di essa
funzionano comunque promemoria locali, chat e tutte le altre funzioni.

### C. Simulatore iPhone/iPad sul Mac — gratis, senza iPhone

1. Installa **Xcode** e apri una volta il simulatore.
2. ```bash
   cd frontend
   npm install
   npx expo run:ios
   ```
3. Scegli il simulatore (iPhone o iPad) dal menu di Xcode/Expo.
4. Il backend deve essere raggiungibile dal Mac; per il simulatore va bene
   `http://localhost:8010`.

Questa modalità è ideale per provare l'interfaccia e il layout tablet, non per
installare l'app su un iPhone fisico.

### D. Expo Go — solo per sviluppo rapido

Il progetto usa **Expo SDK 51**. L'Expo Go degli store aggiorna solo l'SDK più
recente, quindi potrebbe rifiutare il progetto. Per lo sviluppo quotidiano usa una
**development build**:

```bash
cd frontend
npx expo start
# poi, con EAS:
eas build --profile development --platform ios
```

Per un utente finale, meglio TestFlight (B) o la firma personale (A).

---

## 🧑‍💻 Avvio completo in locale

### 1. Backend

```bash
cd backend
# Windows
py -3.12 -m venv venv
.\venv\Scripts\activate
# macOS/Linux
# python3 -m venv venv && source venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env      # macOS/Linux: cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8010
```

Health check: <http://localhost:8010/> → `{"status":"ok", ...}`.

### 2. App

```bash
cd frontend
npm install

# Windows PowerShell
$env:EXPO_PUBLIC_API_URL="http://TUO-IP-LAN:8010"
npx expo start

# macOS/Linux
EXPO_PUBLIC_API_URL=http://TUO-IP-LAN:8010 npx expo start
```

Telefono e PC devono stare sulla stessa Wi-Fi. In alternativa usa l'URL HTTPS
Tailscale già configurato.

### 3. Verifica veloce

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -q   # 146 test
cd frontend && npm run typecheck                      # 0 errori
cd frontend && npx expo-doctor                        # 17/17 check
cd frontend && npx expo export --platform android
cd frontend && npx expo export --platform ios
```

---

## 📱 Tablet e iPad

- **iPad**: `supportsTablet: true` è già in `frontend/app.json`; l'app usa card a due
  colonne e testi leggibili. L'esperienza è ottimizzata per l'uso verticale, come gli
  screenshot inclusi.
- **Tablet Android**: stessa APK del telefono; il layout usa la larghezza disponibile.
- **Test consigliato**: apri Home, Chat, Italiano e Budget su un iPad o tablet;
  controlla che il contenuto non venga tagliato e che il tab bar resti raggiungibile.
- **Screenshot tablet**: [`screenshots/07-tablet-login.png`](../screenshots/07-tablet-login.png).

---

## 🧯 Problemi comuni

| Sintomo | Soluzione |
|---|---|
| “Network request failed” | Backend spento o URL errato. Apri l'URL nel browser del telefono. |
| Login rifiutato | PIN errato o backend non raggiungibile. Usa `io` / `0000` per la demo. |
| Sessione scaduta (401) | Torna ai profili e reinserisci il PIN. |
| Android blocca l'APK | Consenti “Installa app sconosciute” per il browser; è una build debug. |
| iPhone “Sviluppatore non verificato” | Impostazioni → Generali → VPN e gestione dispositivo → Trust. |
| TestFlight non vede l'app | Attendi l'elaborazione Apple; verifica di essere tester del gruppo. |
| Nessuna risposta AI | Manca una chiave Gemini nel backend (`GOOGLE_API_KEY_1`). |
| Push non arrivano | Su Android controlla il canale notifiche; su iOS serve APNs su EAS. |
| Video/foto non funzionano | Concedi i permessi microfono/galleria dalle impostazioni del telefono. |

---

## 🔐 Prima di condividere l'app

- Cambia i PIN demo e il segreto `ATLAS_SECRET_KEY` nel backend.
- Non esporre il backend senza HTTPS e senza autenticazione.
- Le API key (Gemini, Google, Supabase) restano **solo nel backend**, mai
  nell'APK né nel repository.
- L'APK è una build **debug** pensata per test e uso personale; per il Play Store
  usa il profilo `production` e una keystore dedicata.
