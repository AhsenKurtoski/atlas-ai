# Changelog

Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e
[Semantic Versioning](https://semver.org/lang/it/).

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
