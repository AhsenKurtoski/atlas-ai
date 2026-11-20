# Changelog

Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e
[Semantic Versioning](https://semver.org/lang/it/).

## [3.3.0] — 2026-11-20

### Cambiato — piattaforma

- **Expo SDK 51 → 57** (React Native 0.74 → 0.86, React 18 → 19.2, TypeScript 6):
  51 vulnerabilità di `npm audit` ridotte a **3** (restano solo quelle transitive di
  `react-native-markdown-display`, senza fix disponibile upstream).
- **React Navigation 6 → 7** (`native`, `bottom-tabs`, `native-stack`).
- **NativeWind 2 → 4**: nuova pipeline Metro/Babel con `global.css`, preset Tailwind
  e CSS reale sul web; verificato nel browser (fondo `#0a0a0f`, testi bianchi).
- **expo-av → expo-audio** per la dettatura (hook `useAudioRecorder`).
- `expo-file-system` usa l'API legacy esplicita (`expo-file-system/legacy`), come
  richiesto da SDK 57 per `cacheDirectory`/base64.
- Notifiche: trigger tipizzati (`DAILY`/`DATE`) e handler con
  `shouldShowBanner`/`shouldShowList`.
- Config: splash migrata al plugin `expo-splash-screen`, aggiunti `expo-asset` e
  `expo-audio`; `baseUrl` rimosso dal `tsconfig` (deprecato in TypeScript 6).
- Tema scuro esplicito per `NavigationContainer`: senza di esso il web mostrava il
  fondo chiaro predefinito sotto i testi bianchi.
- CI: Node 22, iOS su `macos-latest` con la Xcode più recente e runtime del simulatore
  scelto in base all'SDK della Xcode installata.

### Corretto

- `SafeAreaView` core non applica `className` su RN 0.86/web: lo sfondo scuro ora
  arriva dal tema di navigazione e dal CSS di base.

## [Non rilasciato]

### Aggiunto — sicurezza

- Codice di recupero personale (16 caratteri, hash bcrypt, monouso): ogni membro
  reimposta il PIN senza l'amministratore.
- Blocco progressivo dopo PIN errati (5 → 1 min, 6 → 2 min, 7 → 5 min, 8+ → 15 min).
- Registro accessi con esito, motivo, IP e dispositivo, retention 90 giorni.
- `POST /auth/logout-tutti` per chiudere ogni sessione del profilo.
- Blocco automatico dell'app dopo 5 minuti di inattività o al ritorno dal background.
- Backup cifrati AES/Fernet (`.zip.enc`) con CLI di ripristino
  (`python -m app.services.backup decrypt`).

### Aggiunto — famiglia

- **Controllo genitore** (Impostazioni → Gestione profili → Limiti): fascia oraria,
  messaggi al giorno e contenuti adatti ai bambini. I limiti sono applicati dal
  backend: `POST /chat` risponde 403 con il motivo reale fuori orario o a quota
  esaurita, e per i profili bambino i tool "da adulti" (spese, email, browser,
  crypto, trading) non vengono passati al modello.
- **Cronologia chat sincronizzata** (`GET /chat/cronologia`) con ricerca nel testo:
  gli stessi messaggi su ogni dispositivo, con la cache locale come fallback offline.
- **Soglie di budget** (`POST /budget/limiti`) e report mensile (`GET /budget/report`)
  con confronto col mese precedente e avvisi di sforamento nella schermata Budget.
- Il limite di 15 profili famiglia è ora rispettato anche nella suite di test
  (ripristino dei profili dopo ogni test).

### Aggiunto — privacy

- `GET /privacy/informativa` e documento `docs/PRIVACY.md`.
- `GET /privacy/dati`: export JSON completo dei propri dati.
- `DELETE /privacy/profilo`: cancellazione del profilo con anonimizzazione delle
  liste condivise; il profilo amministratore non può auto-eliminarsi.

### Aggiunto — strumenti

- `scripts/setup.ps1` e `setup.bat`: installazione completa con un comando.
- `scripts/verify.ps1`: test backend + typecheck + build web in un solo comando.
- `scripts/install-autostart.ps1`: avvio automatico Windows e regola firewall.
- `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/PRIVACY.md`.

### Corretto

- Web app: l'URL del backend ora deriva dall'host della pagina, così l'app in LAN
  funziona anche quando il router cambia IP del PC (prima serviva ricostruire il
  bundle con `EXPO_PUBLIC_API_URL`).
- `cryptography` dichiarata in `requirements.txt` (era solo una dipendenza
  indiretta, necessaria per i backup cifrati).
- `ATLAS_DB_DIR` per isolare database locale in test E2E e prove di ripristino.

## [3.2.0] — 2026-11-18

### Aggiunto

- Web app servita dal PC su `:19007` con avvio automatico Windows.
- CORS con regex per IP privati variabili (`PREVIEW_WEB_ORIGIN_REGEX`).
- Regola firewall documentata per l'accesso dal telefono.

## [3.1.0]

- Chat con foto, trascrizione audio, PDF, agente browser Chromium, integrazione
  Gmail/Calendar, server MCP, automazioni APScheduler.

## [3.0.0]

- Prima versione family-first: profili con PIN, liste condivise, budget, italiano.
