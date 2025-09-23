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

set PORT=8001
set EXECUTION_MODE=live
set BROKER_BACKEND=mt5
set MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
set MT5_LOGIN=5039942868
set MT5_PASSWORD=0aWgYp!y
set MT5_SERVER=MetaQuotes-Demo
set MT5_DEFAULT_LOTS=0.01
set JOURNAL_DIR=app/journal
set DATA_DIR=data
set VERBOSE=true
set RELOAD=true
set LOG_LEVEL=info
set MT5_STOP_WIDEN_MULT=2.0  
set MT5_ATTACH_RETRIES=5
set MT5_ATTACH_DELAY_SEC=0.8
set SLTP_MIN_ABS_XAUUSD=12.0
set AGENT_SYMBOLS=EURUSD,XAUUSD,MSFT,NVDA
set AGENT_TIMEFRAME=M15
set LOTS_EURUSD=0.02
set LOTS_XAUUSD=0.02
set LOTS_MSFT=1
set LOTS_NVDA=1
set SLTP_MIN_ABS_NVDA=20.0
set SLTP_MIN_ABS_MSFT=2.0

if "%PORT%"=="" set PORT=8001
if "%LOG_LEVEL%"=="" set LOG_LEVEL=info

REM Run server with .env loaded
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload --log-level %LOG_LEVEL%


