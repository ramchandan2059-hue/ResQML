# Polypharmacy Risk Analyzer PowerShell Launcher
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "       Starting Polypharmacy Risk Analyzer (FastAPI + Groq)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[!] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    & "$ScriptDir\venv\Scripts\pip.exe" install -r requirements.txt
}

Write-Host "[*] Starting FastAPI Server on http://127.0.0.1:8000 ..." -ForegroundColor Green
& "$ScriptDir\venv\Scripts\uvicorn.exe" app:app --host 127.0.0.1 --port 8000 --reload
