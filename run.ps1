<#
.SYNOPSIS
Starts the Autonomous Resume Agent backend and frontend.

.DESCRIPTION
This script activates the virtual environment, starts the FastAPI backend,
and launches the Vite React frontend.

.EXAMPLE
.\run.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host "🚀 Starting Autonomous Resume Agent..." -ForegroundColor Cyan

# Check if venv exists
if (-not (Test-Path ".\venv")) {
    Write-Host "Error: Virtual environment not found. Please run: python -m venv venv" -ForegroundColor Red
    exit 1
}

# Start backend in background job
Write-Host "Starting FastAPI Backend on port 8000..." -ForegroundColor Green
$backendJob = Start-Job {
    Set-Location $args[0]
    & .\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
} -ArgumentList (Get-Location).Path

# Wait a moment for backend to initialize
Start-Sleep -Seconds 2

# Start frontend
Write-Host "Starting Vite Frontend on port 5173..." -ForegroundColor Green
Set-Location "frontend"
npm run dev

# Cleanup jobs when frontend stops
Write-Host "Shutting down backend..." -ForegroundColor Yellow
Stop-Job -Job $backendJob
Remove-Job -Job $backendJob
Write-Host "Done." -ForegroundColor Green
