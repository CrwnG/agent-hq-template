@echo off
rem Double-click to open the HQ dashboard (keeps running in this window; Ctrl+C to stop).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No .venv yet. Run:  python -m venv .venv  then  .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
start "" http://127.0.0.1:8787
.venv\Scripts\python.exe -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8787
