@echo off
cd /d "%~dp0"
echo =========================================================
echo   Opta QuantBet AI - Iniciando servidor local (Colombia)
echo   Abre en tu navegador: http://localhost:8000
echo =========================================================
start "" "http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
