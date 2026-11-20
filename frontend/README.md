# Frontend ATLAS AI — Guida tecnica

Expo SDK 57 · React Native 0.86 · React 19.2 · TypeScript 6 strict · NativeWind 4 (Tailwind 3.4) · React Navigation 7 · AsyncStorage

> **Installazione per utenti finali**: guida completa Android, iPhone, iPad e tablet in
> [`../docs/INSTALL.md`](../docs/INSTALL.md).

---

## 🔒 Dipendenze forzate (`overrides`)

Tre override npm sono intenzionali; vanno rivalidati quando si aggiornano le
librerie coinvolte:

| Override | Perché | Come verificare |
|---|---|---|
| `react-native-markdown-display` → `markdown-it@^14` | la v10 importa il core Node `punycode` (Metro non lo risolve su Android/iOS) e ha 2 advisory high | aprire la chat e controllare titoli, grassetto, link, liste |
| `markdown-it` → `linkify-it@^5.0.2` | chiude le advisory di linkify-it usate dal renderer | `npm audit --omit=dev` |
| `@expo/fingerprint`, `glob` → `minimatch@^11.0.9` | l'advisory riguarda `<= 11.0.0` | `npx expo-doctor` + `expo export` |

`npm audit --omit=dev` deve restare a **0**; se un aggiornamento rompe il
rendering markdown o il bundle nativo, aggiornare prima la libreria e poi
rimuovere l'override corrispondente.

## 📋 Prerequisiti

- **Node.js 22.13+** (richiesto da Expo SDK 57)
- `npm`
- *Opzionale*: [Expo Go](https://expo.dev/go) su iOS/Android per provare l'app
- *Opzionale*: Android Studio / Xcode per build native
- Backend ATLAS raggiungibile (vedi `backend/README.md`), con Chromium installato per l'agente browser

---

## 🏁 Installazione & avvio

```bash
cd frontend
npm install
npx expo start
```

| Comando | Cosa fa |
|---|---|
| `npm run start` | Bundler Metro + QR code |
| `npm run android` | Emulatore Android |
| `npm run ios` | Simulatore iOS (solo macOS) |
| `npm run typecheck` | `tsc --noEmit` (strict) |

---

## 🔐 Configurazione URL backend

Risolto in `src/config.ts`, in ordine:

| Priorità | Fonte | Esempio |
|---|---|---|
| 1 | `EXPO_PUBLIC_API_URL` | `https://api.atlas.miodominio.it` |
| 2 | IP LAN di Expo Go | `http://192.168.1.123:8000` |
| 3 | Loopback | `http://10.0.2.2:8000` (emulatore Android) / `http://localhost:8000` |

```bash
# Backend su porta diversa o host remoto
EXPO_PUBLIC_API_URL=http://192.168.1.50:8010 npx expo start
```

> Su un telefono fisico in Expo Go, PC e telefono devono stare sulla stessa rete Wi-Fi.
> Se il backend usa HTTPS, aggiorna `EXPO_PUBLIC_API_URL` di conseguenza.

---

## 🧩 Schermate

| Tab | Contenuto | Dati reali |
|---|---|---|
| **Profile** (auth) | Scelta profilo + PIN 4-8 cifre | `GET /profili`, `POST /auth/pin` |
| **Home** | Stato backend, versione/DB, dispositivi push, lista attività | `/`, `/dashboard`, `/todos` |
| **Chat** | Chat AI con Markdown, dettatura vocale, **foto dalla galleria**, **agente browser**, cronologia locale | `/chat`, `/chat/trascrivi` |
| **Italiano** | Lezione del giorno, quiz con punteggio, classifica, roleplay | `/italiano/*` |
| **Budget** | Spese per categoria + inserimento | `/budget`, `/budget/spesa` |
| **Impostazioni** | Notifiche, automazioni, Gmail/Calendar, gestione profili (solo admin), logout | `/impostazioni`, `/integrazioni/google/*`, `/profili` |

> **Agente browser**: la navigazione avviene interamente nel backend con Chromium
> headless. L'app non richiede permessi aggiuntivi: basta chiedere in chat, ad esempio
> «apri quel sito e cerca il treno». Cookie e pagine sono isolati per profilo e non
> vengono salvati sul dispositivo. Dettagli in [`../docs/BROWSER.md`](../docs/BROWSER.md)
> e guida di test passo-passo in [`../docs/TESTING_GUIDE.md`](../docs/TESTING_GUIDE.md).

---

## 🔑 Autenticazione

1. L'utente sceglie il profilo e inserisce il PIN.
2. `POST /auth/pin` restituisce un token firmato (TTL 8h).
3. Il token e il profilo vengono salvati in AsyncStorage; all'avvio l'app chiama
   `GET /auth/me` per validare la sessione (se offline usa l'ultima info salvata).
4. Qualsiasi risposta **401** fa tornare automaticamente alla schermata profili
   (`ApiService.setUnauthorizedHandler`).
5. Il logout (Impostazioni) **revoca il token sul server**, disattiva il token push, cancella i promemoria locali e infine la sessione salvata (in quest'ordine: le richieste leggono il token da AsyncStorage).

### Ruoli

- `io` è l'amministratore: solo lui vede “Aggiungi membro” e i pulsanti “Elimina”.
- Gli altri profili usano l'app normalmente, ma non possono creare o rimuovere membri
  (il backend risponde 403 anche se la richiesta viene inviata a mano).
- Chat, punti italiano e push sono separati per profilo; todo, budget e impostazioni
  sono condivisi dalla famiglia.

---

## 🔔 Notifiche

- **Locali**: promemoria giornalieri e promemoria personali creati in chat,
  pianificati con `expo-notifications` sul dispositivo (funzionano ad app chiusa,
  senza EAS/FCM).
- **Remote push**: all'accesso l'app richiede il permesso e registra il token Expo
  sul backend. Serve un `projectId` EAS in `app.json`:

```bash
npm install -g eas-cli
eas login
eas init          # scrive extra.eas.projectId in app.json
```

Senza `projectId` l'app lo segnala nelle Impostazioni e usa solo i promemoria locali
(nessuna simulazione di push).

Canale Android: `atlas_default` (importanza alta, colore `#7c3aed`).

Per una **build standalone** le push Android richiedono anche le credenziali **FCM**
caricate nel progetto Expo (EAS → Credentials); in Expo Go funzionano senza configurazione.
Le push iOS richiedono la chiave APNs configurata su EAS.

---

## 🖼️ Foto dalla galleria

1. Tocca 🖼️ accanto al campo messaggio: si apre la galleria di sistema.
2. La foto viene mostrata in anteprima; puoi rimuoverla con ✕ o aggiungere una didascalia.
3. Al invio viene compressa in JPEG (`quality 0.65`) e inviata a `POST /chat` in base64.
4. ATLAS la analizza con Gemini (descrizione, OCR di documenti/ricette/cartelli) e risponde.

Permessi: iOS `NSPhotoLibraryUsageDescription`, Android photo picker di sistema. Se il
permesso è negato l'app spiega come attivarlo; se la foto supera ~10 MB chiede di
sceglierne una più piccola. La foto non viene salvata nella cronologia locale (solo il testo).

## 🎤 Dettatura vocale

1. Tieni premuto il microfono in Chat (permesso microfono richiesto).
2. Al rilascio l'audio viene letto in base64 e inviato a `POST /chat/trascrivi`.
3. Gemini trascrive e il testo viene inserito nel campo messaggio.

Se il backend non ha chiavi Gemini, l'app mostra l'errore reale e non inventa un testo.

---

## 📱 Persistenza locale

| Chiave | Contenuto |
|---|---|
| `@atlas/auth_token` | Token di sessione |
| `@atlas/profile` | Slug profilo attivo |
| `@atlas/profile_info` | Nome, lingua, livello (cache offline) |
| `@atlas/history/<slug>` | Ultimi messaggi chat |
| `@atlas/push_token` | Token Expo del dispositivo |
| `@atlas/local_notifications` | ID dei promemoria pianificati |

Nessun dato sensibile (PIN, chiavi API) viene salvato sul dispositivo.

---

## 🚀 Build Android / iOS

Identificativi già configurati in `app.json`:

- iOS bundle identifier: `com.atlasai.family`
- Android package: `com.atlasai.family`
- Deep link scheme: `atlasai://` (ritorno OAuth)
- Permessi: microfono, notifiche, vibrazione
- Plugin: `expo-notifications`

```bash
npm install -g eas-cli
eas login
eas init                     # genera projectId (necessario per le push)
eas build --platform android --profile preview
eas build --platform ios --profile production
```

> **iOS senza abbonamento**: con un Mac e un Apple ID gratuito puoi firmare l'app
> per il tuo iPhone con `npx expo run:ios --device` (la firma scade ogni 7 giorni).
> TestFlight e App Store richiedono Apple Developer Program. Procedura dettagliata in
> [`../docs/INSTALL.md`](../docs/INSTALL.md).

Imposta `EXPO_PUBLIC_API_URL` nel profilo EAS (`eas.json`) con l'URL HTTPS del backend.

---

## 🧪 Verifica

```bash
npm run typecheck                                        # 0 errori
npx expo export --platform android --output-dir .export   # bundle Android
npx expo export --platform ios --output-dir .export-ios   # bundle iOS
```

Le build di verifica non richiedono account a pagamento.

Dopo l'aggiunta di `expo-image-picker` serve una nuova development build per testare la
galleria su device fisico: **Expo Go include già il modulo**, mentre una build precedente
non lo contiene. Per un backend in HTTP sulla LAN usa Expo Go in sviluppo; per una build
standalone pubblica il backend in **HTTPS** (iOS ATS e Android cleartext bloccano HTTP).

---

## ℹ️ Note

- Le notifiche push remote in **Expo Go** hanno limitazioni: per un test completo usa una
  development build (`eas build --profile development`).
- La preview web non è un target di prodotto: l'app è progettata per iOS/Android.
- `expo-blur` è presente tra le dipendenze ma non è usato dalle schermate attuali.
