@echo off
setlocal
set "ROOT=C:\Users\anelk\Desktop\Progetti Personali\atlas-ai-main\atlas-ai-main"
set "BACKEND=%ROOT%\backend"
set "CLOUDFLARED=%ROOT%\.tools\cloudflared.exe"
set "TAILSCALE=C:\Program Files\Tailscale\tailscale.exe"
cd /d "%BACKEND%"

rem Avvia il backend solo se la porta 8010 non è già in ascolto.
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -FilePath '%BACKEND%\venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','main:app','--host','0.0.0.0','--port','8010' -WorkingDirectory '%BACKEND%' -WindowStyle Hidden }"

rem Avvia Funnel senza bloccare l'accesso a Windows.
if exist "%TAILSCALE%" (
    "%TAILSCALE%" status >nul 2>&1
    if not errorlevel 1 (
        powershell -NoProfile -Command "Start-Process -FilePath '%TAILSCALE%' -ArgumentList 'funnel','--bg','8010' -WindowStyle Hidden"
        powershell -NoProfile -Command "Start-Sleep -Seconds 3"
        "%TAILSCALE%" funnel status 2>&1 | findstr /I "https://atlas-ai" >nul
        if not errorlevel 1 goto :done
    )
)

rem Fallback: tunnel Cloudflare rapido, solo se non è già attivo.
powershell -NoProfile -Command "if (-not (Get-Process -Name cloudflared -ErrorAction SilentlyContinue)) { Start-Process -FilePath '%CLOUDFLARED%' -ArgumentList 'tunnel','--url','http://localhost:8010','--no-autoupdate' -WindowStyle Hidden }"

:done
endlocal
exit /b 0
