# 🍎 iOS, iPad e CI: guida completa

ATLAS AI usa Expo SDK 51 e React Native 0.74. La stessa codebase gira su iPhone,
iPad, Android e web. Questa pagina spiega cosa funziona davvero e come installarla.

## Cosa fa la CI iOS

Workflow: [`.github/workflows/ios-build.yml`](../.github/workflows/ios-build.yml)

- runner `macos-15`;
- Xcode **16.2** (ultima versione compatibile con Expo SDK 51);
- installa il runtime **iOS 18.2**, che GitHub non preinstalla più;
- esegue `expo prebuild --platform ios`, `pod install` e `xcodebuild` per
  `generic/platform=iOS Simulator`;
- carica due artifact: `ATLAS-AI-ios-simulator.zip` (`.app` non firmata) e
  `ATLAS-AI-ios-build-log`.

L'artifact serve per il **Simulatore**, non per un iPhone fisico: un `.app` senza
firma Apple non può essere installato su un dispositivo reale.

## Simulatore su Mac (gratis)

```bash
cd frontend
npm ci
npx expo prebuild --platform ios
npx expo run:ios
```

Requisiti: macOS, Xcode, CocoaPods. Se usi un backend locale, imposta
`EXPO_PUBLIC_API_URL=http://localhost:8010` prima del comando.

Per scegliere un iPad:

```bash
xcrun simctl list devices available | grep -i ipad
npx expo run:ios --device "iPad Air (5th generation)"
```

L'orientamento è `default` e `supportsTablet: true`: l'app ruota in landscape.

## iPhone personale, firma gratuita (7 giorni)

1. Mac con Xcode e un Apple ID personale.
2. `npx expo prebuild --platform ios && npx expo run:ios --device`.
3. In Xcode → target ATLASAI → **Signing & Capabilities**, scegli il team personale.
4. Installa sul dispositivo collegato e sbloccato.
5. Dopo 7 giorni rifirma con Xcode. Non è distribuibile ad altri.

## TestFlight / App Store (a pagamento)

Serve **Apple Developer Program** (99 €/anno) e un account Expo/EAS.

```bash
cd frontend
npm install -g eas-cli
eas login
eas init
eas build --platform ios --profile production
eas submit --platform ios
```

Poi in App Store Connect: bundle id `com.atlasai.family`, carica la build, aggiungi
i tester in TestFlight. La prima revisione App Store è obbligatoria per la
distribuzione pubblica.

Il profilo `preview` di `eas.json` produce una build interna; per il simulatore
puoi usare:

```bash
eas build --platform ios --profile ios-simulator
```

## Notifiche su iOS

| Tipo | Cosa serve | Stato senza configurazione |
|---|---|---|
| Locali (promemoria) | permesso notifiche iOS | funzionano dopo il consenso |
| Push remote | APNs + profilo EAS + device fisico | l'app dice che non ci sono dispositivi |

Le push non arrivano sul Simulatore iOS: è un limite di Apple, non dell'app.

## Gmail e Calendar su iOS

Il flusso OAuth usa il browser di sistema e il deep link `atlasai://oauth`.

1. In Google Cloud Console crea un client OAuth **Web**.
2. Redirect autorizzato: `http://localhost:8010/integrazioni/google/callback`
   (o l'URL HTTPS pubblico del backend).
3. Nel backend: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `GOOGLE_REDIRECT_URI`, `APP_DEEPLINK=atlasai://oauth`.
4. Nell'app: **Impostazioni → Connetti Gmail/Calendar**.

Su iOS il deep link viene gestito da `Linking`; se il browser non torna all'app,
verifica che lo scheme `atlasai` sia presente in `app.json` (lo è).

## PDF su iOS

La schermata **PDF** genera il documento sul backend e apre il pannello di
condivisione iOS (`expo-sharing`). Da lì puoi salvare in File, inviare con Mail o
condividere con un'altra app. Non richiede iCloud né servizi esterni.

## Errori iOS comuni

| Errore | Causa | Soluzione |
|---|---|---|
| `iOS 18.2 Platform Not Installed` | runtime non preinstallato su macOS 15 | la CI esegue `xcodebuild -downloadPlatform iOS -buildVersion 18.2` |
| `TARGET_OS_SIMULATOR` in `expo-device` | Xcode 16.3+ non compatibile con SDK 51 | usa Xcode 16.2 (la CI lo fa) |
| `No signing certificate` | build per device senza team | configura Signing in Xcode o usa EAS |
| `Sviluppatore non verificato` | firma gratuita | Impostazioni → Generali → VPN e gestione dispositivo → Trust |
| Push non arrivano | manca APNs o sei sul simulatore | configura APNs e usa un device fisico |
| `Network request failed` | backend non raggiungibile | usa HTTPS pubblico o `localhost` sul simulatore |

## Versione futura

Expo SDK 51 è la versione attuale del progetto. Expo Go degli store supporta solo
SDK recenti, quindi per il telefono serve una development build. L'aggiornamento a
SDK 53+ è una migrazione separata (React Native, Reanimated, expo-av) e non è
necessario per usare l'app oggi con TestFlight o firma locale.
