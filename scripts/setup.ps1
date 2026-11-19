<#
.SYNOPSIS
  Installa ATLAS AI da zero: scarica il progetto (se serve), crea la venv,
  installa le dipendenze, prepara .env e costruisce la web app.

.EXAMPLE
  # Da PowerShell, senza avere il progetto:
  irm https://raw.githubusercontent.com/AhsenKurtoski/atlas-ai/main/scripts/setup.ps1 | iex

.EXAMPLE
  # Dentro al progetto già clonato:
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Autostart
#>
param(
    [string]$Dest = (Join-Path $env:USERPROFILE "ATLAS-AI"),
    [string]$Repo = "https://github.com/AhsenKurtoski/atlas-ai.git",
    [switch]$NoBuild,
    [switch]$Autostart,
    [switch]$SkipBrowser
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Testo) {
    Write-Host ""
    Write-Host "==> $Testo" -ForegroundColor Cyan
}

function Test-Command([string]$Nome) {
    return [bool](Get-Command $Nome -ErrorAction SilentlyContinue)
}

function Invoke-Python([string]$Comando, [string[]]$Argomenti) {
    # "py -3.12" → eseguibile "py" + argomento "-3.12" davanti agli altri.
    $parti = @($Comando.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries))
    $exe = $parti[0]
    $prefisso = @()
    if ($parti.Length -gt 1) { $prefisso = $parti[1..($parti.Length - 1)] }
    & $exe @($prefisso + $Argomenti)
}

function Find-Python {
    foreach ($candidato in @("py -3.12", "py -3.13", "py -3.11", "python")) {
        $exe = $candidato.Split(" ")[0]
        if (Test-Command $exe) {
            $versione = Invoke-Python $candidato @("--version") 2>$null
            if ($versione -match "3\.(11|12|13)") {
                return $candidato
            }
        }
    }
    throw "Serve Python 3.11-3.13. Installalo da https://www.python.org/downloads/ e riprova."
}

# ---------------------------------------------------------------- prerequisiti
Write-Step "Controllo i prerequisiti"
if (-not (Test-Command "node")) { throw "Serve Node.js 18+ (https://nodejs.org)." }
if (-not (Test-Command "npm")) { throw "Serve npm (incluso con Node.js)." }
$python = Find-Python
Write-Host "Python: $python"
Write-Host "Node:   $(node --version)"

# ---------------------------------------------------------------- progetto
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$locale = Join-Path $scriptDir "..\backend\main.py"
if (Test-Path $locale) {
    $root = (Resolve-Path (Join-Path $scriptDir "..")).Path
    Write-Step "Progetto già presente in $root"
} else {
    if (-not (Test-Command "git")) { throw "Serve Git per scaricare il progetto (https://git-scm.com)." }
    Write-Step "Scarico il progetto in $Dest"
    if (Test-Path $Dest) {
        Write-Host "Cartella esistente: aggiorno con git pull"
        git -C $Dest pull --ff-only
    } else {
        git clone $Repo $Dest
    }
    $root = (Resolve-Path $Dest).Path
}

Set-Location $root

# ---------------------------------------------------------------- backend
Write-Step "Preparo il backend (venv + dipendenze)"
$venvPython = Join-Path $root "backend\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Invoke-Python $python @("-m", "venv", (Join-Path $root "backend\venv"))
}
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r (Join-Path $root "backend\requirements.txt")
& $venvPython -m pip check

$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) {
    # Il modello inizia con una riga [TEMPLATE] che non è una variabile.
    Get-Content (Join-Path $root "backend\.env.example") |
        Where-Object { $_.Trim() -ne "[TEMPLATE]" } |
        Set-Content $envFile -Encoding UTF8
    Write-Host "Creato backend\.env dalle impostazioni di esempio (modalità locale, senza LLM)." -ForegroundColor Yellow
}

if (-not $SkipBrowser) {
    Write-Step "Installo Chromium per l'agente browser (può richiedere qualche minuto)"
    & $venvPython -m playwright install chromium
}

# ---------------------------------------------------------------- frontend
Write-Step "Installo le dipendenze del frontend"
Push-Location (Join-Path $root "frontend")
try {
    if (Test-Path "package-lock.json") { npm ci } else { npm install }
    if (-not $NoBuild) {
        Write-Step "Costruisco la web app (frontend\dist, servita sulla porta 19007)"
        npm run export:web
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- autostart
if ($Autostart) {
    & (Join-Path $root "scripts\install-autostart.ps1") -Root $root
}

Write-Step "Fatto"
Write-Host "Avvio manuale:  $root\backend\start-atlas.bat" -ForegroundColor Green
Write-Host "Web app:        http://localhost:19007   (dal telefono: http://IP-DEL-PC:19007)"
Write-Host "Telefono:       apri l'indirizzo in Safari -> Condividi -> Aggiungi a Home"
Write-Host "Autostart:      powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1"
