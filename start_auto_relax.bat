@echo off
setlocal
call .venv\Scripts\activate.bat
set AGENT_API=http://127.0.0.1:8001
set AGENT_SYMBOLS=EURUSD,XAUUSD,MSFT,NVDA
set AGENT_TF=H1
set AGENT_PERIOD_SEC=60
set AGENT_MAX_OPEN=8
set AGENT_MAX_PER_SYMBOL=2
set AGENT_BLOCK_SAME_SIDE=false
set AGENT_COOLDOWN_MIN=0
set AGENT_TRADING_START=00:00
set AGENT_TRADING_END=23:59
REM python auto_runner.py
python run_auto.py
endlocal
