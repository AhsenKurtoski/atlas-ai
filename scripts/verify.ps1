<#
.SYNOPSIS
  Verifica completa di ATLAS AI con un solo comando: test backend, typecheck
  frontend e (opzionale) build web.

.DESCRIPTION
  Esegue in sequenza:
    1. pytest del backend (suite completa, DB isolato in una cartella temporanea)
    2. pip check (dipendenze Python coerenti)
    3. tsc --noEmit sul frontend (strict)
    4. con -Build: export web in frontend\dist
  Esce con codice 0 solo se tutti i passaggi sono verdi.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\verify.ps1

.EXAMPLE
  # Include la build web (ferma prima il server sulla 19007: Windows blocca la cartella dist)
  powershell -ExecutionPolicy Bypass -File scripts\verify.ps1 -Build
#>
param(
    [switch]$Build,
    [switch]$SkipBrowserInstall
)

$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $root "backend\venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }
$esiti = @()

function Invoke-Passo([string]$Nome, [scriptblock]$Azione) {
    Write-Host ""
    Write-Host "==> $Nome" -ForegroundColor Cyan
    $inizio = Get-Date
    & $Azione
    $codice = $LASTEXITCODE
    if ($null -eq $codice) { $codice = 0 }
    $secondi = [math]::Round(((Get-Date) - $inizio).TotalSeconds, 1)
    if ($codice -eq 0) {
        Write-Host "[OK] $Nome ($secondi s)" -ForegroundColor Green
        $script:esiti += [pscustomobject]@{ Passo = $Nome; Esito = "OK"; Secondi = $secondi }
    } else {
        Write-Host "[FALLITO] $Nome (exit $codice)" -ForegroundColor Red
        $script:esiti += [pscustomobject]@{ Passo = $Nome; Esito = "FALLITO ($codice)"; Secondi = $secondi }
    }
}

Push-Location (Join-Path $root "backend")
try {
    Invoke-Passo "pytest backend" { & $python -m pytest -q }
    Invoke-Passo "pip check" { & $python -m pip check }
} finally {
    Pop-Location
}

Push-Location (Join-Path $root "frontend")
try {
    Invoke-Passo "tsc --noEmit" { npx tsc --noEmit }
    if ($Build) {
        Invoke-Passo "expo export web" { npm run export:web }
    }
} finally {
    Pop-Location
}

Write-Host ""
$esiti | Format-Table -AutoSize
$falliti = @($esiti | Where-Object { $_.Esito -ne "OK" }).Count
if ($falliti -gt 0) {
    Write-Host "$falliti passaggi falliti." -ForegroundColor Red
    exit 1
}
Write-Host "Tutti i controlli sono passati." -ForegroundColor Green
