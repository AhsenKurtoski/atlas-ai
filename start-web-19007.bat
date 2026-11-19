@echo off
setlocal
rem Serve l'export web (frontend/dist) sulla porta 19007, l'app che si apre da
rem Safari sull'iPhone. Idempotente: se la porta e' gia' in ascolto non fa nulla,
rem quindi puo' essere chiamato da ogni avvio (Windows o manuale).
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "WEB=%ROOT%\frontend\dist"
set "PY=%ROOT%\backend\venv\Scripts\python.exe"
set "LOGDIR=%ROOT%\backend\logs"

if not exist "%WEB%\index.html" exit /b 0
if not exist "%PY%" exit /b 0
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 19007 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -FilePath '%PY%' -ArgumentList '-m','http.server','19007','--bind','0.0.0.0' -WorkingDirectory '%WEB%' -RedirectStandardOutput '%LOGDIR%\web-19007.log' -RedirectStandardError '%LOGDIR%\web-19007.err.log' -WindowStyle Hidden }"

endlocal
exit /b 0
