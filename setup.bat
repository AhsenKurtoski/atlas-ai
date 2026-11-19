@echo off
rem Installa ATLAS AI: dipendenze backend/frontend e build della web app.
rem Doppio clic da Esplora file oppure: setup.bat -Autostart
setlocal
set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\setup.ps1" %*
pause
