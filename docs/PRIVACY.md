# Privacy di ATLAS AI

Questa è la versione leggibile dell'informativa che l'app mostra in
**Impostazioni → Privacy → Informativa privacy** (la stessa restituita da
`GET /privacy/informativa`). Versione 1.0 · aggiornata il 19 novembre 2026.

## Dove restano i dati

ATLAS AI gira sul computer della famiglia. Nome, PIN, messaggi, promemoria,
spese e liste restano in `backend/_local_db` (o nel progetto Supabase scelto dal
proprietario). Non esiste un server nostro che raccoglie i dati di tutti.

## Cosa conserviamo

- nome, lingua madre e livello di italiano del profilo;
- PIN e codice di recupero **solo come hash bcrypt** (nemmeno l'amministratore
  può leggerli);
- messaggi della chat, promemoria, spese e liste condivise;
- token dei dispositivi per le notifiche;
- registro accessi: data, esito, motivo, IP e tipo di dispositivo.

## Perché

Per far funzionare l'assistente (memoria della conversazione), la sicurezza
degli accessi e i promemoria. Nessuna profilazione pubblicitaria, nessuna
vendita di dati.

## Servizi esterni

Se sono configurate le chiavi Gemini, il testo dei messaggi viene inviato a
Google per generare la risposta. Se colleghi Google (Gmail/Calendar) o attivi
le notifiche push, i dati necessari passano ai rispettivi servizi. Senza chiavi
configurate la chat non funziona e l'app resta in locale.

## Tempi di conservazione

| Dato | Per quanto |
|---|---|
| Chat | fino alla cancellazione del profilo |
| Registro accessi | 90 giorni |
| Backup | 14 copie, una ogni 6 ore (circa 3 giorni) |
| Spese e liste | finché esiste il profilo famiglia (sono condivise) |

## I tuoi diritti, dentro l'app

- **Esporta i miei dati** → JSON con profilo, messaggi, promemoria, progressi,
  dispositivi (token oscurati), spese, attività e accessi.
- **Cancella il mio profilo** → rimuove messaggi, promemoria, progressi,
  dispositivi e registro accessi; le liste condivise restano alla famiglia ma
  non sono più collegate alla persona. L'operazione non si può annullare.
- Il profilo amministratore `io` non può cancellarsi da solo: deve prima
  esistere un altro amministratore che gestisca la famiglia.

## Sicurezza

PIN e codici di recupero sono hash bcrypt; le sessioni usano token firmati con
scadenza, blocco progressivo dopo troppi errori e blocco automatico dell'app
dopo inattività. I backup del database sono cifrati (AES/Fernet) con una chiave
derivata da `ATLAS_BACKUP_PASSWORD` o dal segreto del server: senza quella
chiave un archivio copiato altrove non è leggibile.

## Limiti noti

- Sulla web app aperta in Safari (iPhone/iPad) il token di sessione vive nello
  storage del sito: iOS non espone il Keychain alle web app. La protezione è
  quindi blocco automatico, scadenza della sessione e "esci da tutti i
  dispositivi". Una build nativa può usare `expo-secure-store`.
- Lo sblocco con impronta/volto richiede una build nativa o WebAuthn/passkey:
  non è disponibile nella versione web attuale, dove resta il PIN.
