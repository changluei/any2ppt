@echo off
setlocal
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Backend virtual environment not found: backend\.venv
  echo Create it and install backend dependencies first.
  exit /b 1
)

echo [1/2] Checking and applying database migrations...
".venv\Scripts\python.exe" -m app.core.migrations
if errorlevel 1 (
  echo [ERROR] Database migration failed. Backend was not started.
  exit /b 1
)

echo [2/2] Starting backend at http://127.0.0.1:8000 ...
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
