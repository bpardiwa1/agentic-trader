@echo off
REM start_auto_safe.bat - guarded auto-runner with dynamic lot sizing
setlocal
call .venv\Scripts\activate
REM set AGENT_MAX_OPEN=6
REM set AGENT_MAX_PER_SYMBOL=3



python run_auto_guarded.py
endlocal
