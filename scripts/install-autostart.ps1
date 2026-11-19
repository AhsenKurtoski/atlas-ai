<#
.SYNOPSIS
  Registra ATLAS AI nell'avvio automatico di Windows e apre la porta 19007
  nel firewall, così dopo un riavvio l'app sul telefono funziona da sola.

.NOTES
  L'avvio automatico usa la cartella Startup dell'utente: nessun permesso di
  amministratore. La regola firewall richiede invece l'elevazione: se lo script
  non è amministratore, stampa il comando da eseguire una volta sola.
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$startScript = Join-Path $Root "backend\start-atlas.bat"
if (-not (Test-Path $startScript)) {
    throw "Non trovo $startScript. Esegui lo script dalla cartella del progetto."
}

# ---------------------------------------------------------------- Startup
$startup = [Environment]::GetFolderPath("Startup")
$voce = Join-Path $startup "ATLAS-AI.bat"
$contenuto = "@echo off`r`nrem Avvia backend (8010) e web app (19007) di ATLAS AI.`r`ncall `"$startScript`"`r`n"
Set-Content -Path $voce -Value $contenuto -Encoding ASCII
Write-Host "Avvio automatico registrato: $voce" -ForegroundColor Green

# ---------------------------------------------------------------- Firewall
$regola = "ATLAS AI web 19007"
$esistente = Get-NetFirewallRule -DisplayName $regola -ErrorAction SilentlyContinue
if ($esistente) {
    Write-Host "Regola firewall '$regola' già presente." -ForegroundColor Green
} else {
    $admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if ($admin) {
        New-NetFirewallRule -DisplayName $regola -Direction Inbound -Action Allow -Protocol TCP -LocalPort 19007 -Profile Any | Out-Null
        Write-Host "Regola firewall '$regola' creata." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "La porta 19007 non è ancora aperta nel firewall." -ForegroundColor Yellow
        Write-Host "Esegui una volta PowerShell come amministratore e lancia:"
        Write-Host "  New-NetFirewallRule -DisplayName '$regola' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 19007 -Profile Any" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "Al prossimo accesso Windows il backend e la web app partiranno da soli."
