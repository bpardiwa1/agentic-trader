@echo off
REM --- Agentic Trader Start Script ---
REM Loads .env automatically and launches FastAPI server

echo Starting Agentic Trader...

REM Activate venv
call .venv\Scripts\activate

REM Ensure python-dotenv installed
pip install -q python-dotenv




REM Use defaults if not set
if "%PORT%"=="" set PORT=8001
if "%LOG_LEVEL%"=="" set LOG_LEVEL=info

REM Run server with .env loaded
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload --log-level %LOG_LEVEL%

