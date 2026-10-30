@echo off
title Polypharmacy Risk Analyzer
echo ======================================================================
echo           Starting Polypharmacy Risk Analyzer (FastAPI)
echo ======================================================================
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Creating one...
    python -m venv venv
    venv\Scripts\pip.exe install -r requirements.txt
)

echo [*] Launching Uvicorn Server at http://127.0.0.1:8000 ...
echo [*] Press CTRL+C to stop the server.
venv\Scripts\uvicorn.exe app:app --host 127.0.0.1 --port 8000 --reload
pause
