# ☁️ ATLAS AI sempre online, senza pagare

Questa guida serve per far girare **backend FastAPI + browser Chromium** 24/7
senza abbonamenti. La strada consigliata è una VM **Oracle Cloud Always Free**
con **Tailscale Funnel** per l'HTTPS pubblico. Il piano è gratuito, ma nessun
free tier garantisce il 100% di uptime: Oracle può recuperare VM inattive e
Tailscale Funnel è in beta. Per un uso familiare è una soluzione concreta.

## Perché non basta Render/Cloud Run

- **Render free**: il servizio va in sleep dopo 15 minuti senza traffico; non è
  adatto a un backend che deve ricevere promemoria e job 24/7.
- **Cloud Run free**: scala a zero e non offre un filesystem persistente o un
  Chromium di lunga durata; il browser agent richiede un processo sempre vivo.
- **Fly.io / Heroku**: non hanno più un free tier utilizzabile per un servizio
  sempre acceso.
- **Oracle Always Free**: VM vera, disco persistente, processo sempre acceso.
  Richiede una carta per la verifica (addebito di verifica, non un abbonamento)
  e la capacità ARM non è sempre disponibile in tutte le regioni.

Fonti: [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[Render free](https://render.com/docs/free),
[Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel).

## 1. Crea la VM

1. Crea un account Oracle Cloud e scegli una **home region** vicina.
2. Crea una VM **Ubuntu 24.04** con shape `VM.Standard.A1.Flex`:
   **2 OCPU, 12 GB RAM**, boot volume 50 GB. Rientra nei limiti Always Free
   (2 OCPU/12 GB totali, 200 GB di block storage).
3. Assegna un IP pubblico e apri solo la porta **22** nel security list.
4. Entra via SSH:

```bash
ssh ubuntu@<IP-PUBBLICO>
```

Se la shape ARM non è disponibile, riprova in un'altra availability domain
della stessa region. Non creare risorse a pagamento per aggirare il limite.

## 2. Installa ATLAS

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip git curl

git clone https://github.com/AhsenKurtoski/atlas-ai.git
cd atlas-ai/backend
python3.12 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
cp .env.example .env
```

Genera un segreto vero e mettilo nel `.env`:

```bash
python -c "import secrets; print('ATLAS_SECRET_KEY=' + secrets.token_urlsafe(48))"
```

Nel `.env` imposta almeno:

```dotenv
APP_ENV=production
ATLAS_SECRET_KEY=<valore-generato>
SCHEDULER_ENABLED=true
BROWSER_HEADLESS=true
# Solo se usi il web: elenca le origini esatte, separate da virgola.
# In produzione, senza questa variabile, il CORS è chiuso (le app native non lo usano).
# CORS_ALLOWED_ORIGINS=https://il-tuo-web.example
```

Con `APP_ENV=production` valgono due protezioni sui PIN:

- i **PIN demo** (`0000/1111/2222/3333/4444`) vengono rifiutati al login e in
  fase di cambio PIN;
- se `backend/_local_db/profiles.json` manca o è illeggibile, **nessun profilo
  viene caricato** (fail closed): nessun accesso finché non ripristini un backup
  o reimposti i PIN.

Imposta i PIN reali con l'endpoint amministratore (serve un token di `io`):

```bash
TOKEN=<token restituito da POST /auth/pin per io>
curl -X POST http://127.0.0.1:8010/profili/mamma/pin \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"pin":"482915"}'
```

Prova il backend in primo piano:

```bash
uvicorn main:app --host 127.0.0.1 --port 8010
# da un altro terminale della VM:
curl http://127.0.0.1:8010/
```

Deve rispondere `"status":"ok"`. Premi `Ctrl+C`.

## 3. Avvio automatico con systemd

```bash
sudo tee /etc/systemd/system/atlas.service >/dev/null <<'EOF'
[Unit]
Description=ATLAS AI backend
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/atlas-ai/backend
EnvironmentFile=/home/ubuntu/atlas-ai/backend/.env
ExecStart=/home/ubuntu/atlas-ai/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8010
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now atlas
sudo systemctl status atlas --no-pager
```

Se la VM si riavvia, ATLAS riparte da solo. Dopo un aggiornamento:

```bash
cd ~/atlas-ai
git pull
cd backend
. venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart atlas
```

## 4. HTTPS pubblico gratis con Tailscale Funnel

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale funnel --bg 8010
sudo tailscale funnel status
```

L'URL sarà del tipo:

```text
https://<nome-macchina>.<tailnet>.ts.net
```

Tailscale Funnel accetta solo le porte 443, 8443 e 10000, e inoltra solo a un
servizio su `127.0.0.1`: per questo il backend ascolta su loopback. Non serve
aprire la porta 8010 su Internet. Funnel è disponibile anche sul piano
Personal gratuito, ma è in beta e ha limiti di banda non configurabili.

## 5. Collega l'app al nuovo URL

L'APK e la build iOS usano `EXPO_PUBLIC_API_URL` al momento della compilazione.
Aggiorna quella variabile nel workflow `.github/workflows/android-apk.yml` e
`.github/workflows/ios-build.yml`, poi rilancia la build. Non basta cambiare
l'URL nel backend.

```bash
gh workflow run android-apk.yml
gh workflow run ios-build.yml
```

Testa dal telefono, fuori dalla rete domestica:

```bash
curl https://<nome-macchina>.<tailnet>.ts.net/
```

## 6. Backup e monitoraggio

**Backup automatico**: con la modalità locale il backend crea uno zip di
`_local_db` all'avvio e ogni 6 ore in `backend/_backups/`
(`atlas-local-db-<data>.zip`), conservando gli ultimi 14 archivi ed escludendo
il file di lock e il segreto di firma `.atlas_secret`. La cartella è in
`.gitignore`, perché contiene dati personali.

Ripristino:

```bash
sudo systemctl stop atlas
cd ~/atlas-ai/backend
cp -a _local_db _local_db.prima-del-ripristino     # copia di sicurezza
python3 - <<'PY'
import zipfile, pathlib
zip_path = sorted(pathlib.Path('_backups').glob('atlas-local-db-*.zip'))[-1]
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall('_local_db')
print('ripristinato', zip_path.name)
PY
sudo systemctl start atlas
```

**Backup manuale aggiuntivo** (il database locale è in `backend/_local_db/`, mai nel repo):

```bash
sudo mkdir -p /var/backups/atlas
sudo tar czf /var/backups/atlas/atlas-$(date +%F).tgz \
  -C /home/ubuntu/atlas-ai/backend _local_db
```

Aggiungi un cron giornaliero e conserva i file fuori dalla VM (per esempio in
un bucket gratuito o sul tuo PC). Se usi Supabase, i dati sono già remoti, ma
tieni comunque un export.

**UptimeRobot** (piano gratuito) può controllare `GET /health` ogni 5 minuti e
avvisarti via email. `/health` è pensato per i monitor: non tocca il database e
risponde in pochi millisecondi.

```bash
curl -s https://<nome-macchina>.<tailnet>.ts.net/health
# {"status":"ok","versione":"3.2.0","scheduler_attivo":true,
#  "llm":true,"uptime_seconds":81.9,"uptime_iso":"2026-11-18T14:06:27Z"}
```

Se `uptime_seconds` torna a un valore basso, il processo è stato riavviato:
indaga nei log (`backend/logs/`) invece di ignorarlo. Un monitoraggio gratuito
non rende il servizio a prova di guasto, ma ti dice subito se la VM o il tunnel
sono caduti.

## 7. Se preferisci non creare una VM

Puoi tenere il PC Windows attuale acceso 24/7 con Tailscale Funnel e
l'avvio automatico di `start-atlas.bat`. È gratis, ma dipende da corrente,
Internet, aggiornamenti Windows e dal PC accesso. Non è equivalente a un server
cloud e non posso garantire l'uptime.

`start-atlas.bat` è idempotente: avvia uvicorn solo se la porta 8010 è libera e
riattiva il Funnel solo se non è già configurato. Puoi quindi richiamarlo ogni
pochi minuti come watchdog con l'Utilità di pianificazione di Windows
(PowerShell come utente corrente, senza amministratore):

```powershell
$bat = "C:\percorso\atlas-ai\backend\start-atlas.bat"
schtasks /create /tn "ATLAS AI Autostart"  /tr "`"$bat`"" /sc onlogon       /f
schtasks /create /tn "ATLAS AI Keepalive" /tr "`"$bat`"" /sc minute /mo 10 /f
schtasks /query /tn "ATLAS AI Keepalive" /fo LIST /v   # Ultimo esito: 0
```

Cosa copre davvero: crash del backend, tunnel spento dopo un riavvio, accesso
a Windows. Cosa **non** copre: PC spento, sospensione, assenza di rete,
aggiornamenti Windows che richiedono un riavvio. Per questo un monitor esterno
(UptimeRobot su `/health`) resta necessario.

## 8. iOS: cosa è gratis e cosa no

La CI iOS compila un'app per il **Simulatore** senza firma Apple. Per
installarla su un iPhone fisico serve una firma:

- **gratis**: Mac + Xcode + Apple ID personale, con firma valida 7 giorni;
- **gratis senza Mac**: strumenti di sideloading come AltStore/SideStore,
  sempre con il proprio Apple ID e rinnovo periodico;
- **TestFlight/App Store**: Apple Developer Program (a pagamento).

Nessuna di queste strade cambia il codice dell'app: cambia solo la firma.

## Checklist finale

- [ ] `systemctl is-active atlas` → `active`
- [ ] `curl http://127.0.0.1:8010/` → `200`
- [ ] `tailscale funnel status` → URL pubblico
- [ ] `curl https://...ts.net/` da rete esterna → `200`
- [ ] login con PIN reali (non quelli demo) su un telefono
- [ ] promemoria di prova a 2 minuti, telefono bloccato
- [ ] backup automatici presenti in `backend/_backups/` (almeno uno)
- [ ] PIN reali impostati e login demo rifiutato in produzione
- [ ] monitoraggio UptimeRobot attivo

**Nota onesta:** “gratis per sempre” non significa “SLA garantito”. Oracle può
richiedere la carta, può non avere capacità ARM e può recuperare istanze
inattive; Tailscale Funnel può cambiare limiti perché è in beta. Per un servizio
che non può mai fermarsi serve un piano a pagamento con SLA.
