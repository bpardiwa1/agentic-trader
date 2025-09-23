@echo off
setlocal
call .venv\Scripts\activate.bat
REM set AGENT_API=http://127.0.0.1:8001
REM set AGENT_SYMBOLS=EURUSD,XAUUSD,MSFT,NVDA
REM set AGENT_TF=H1
REM set AGENT_PERIOD_SEC=15
set AGENT_MAX_OPEN=4
set AGENT_MAX_PER_SYMBOL=2
REM set AGENT_BLOCK_SAME_SIDE=true
REM set AGENT_COOLDOWN_MIN=60
REM set AGENT_TRADING_START=00:00
REM set AGENT_TRADING_END=23:59
REM python auto_runner.py

REM python run_auto.py

python run_auto_guarded.py
endlocal
