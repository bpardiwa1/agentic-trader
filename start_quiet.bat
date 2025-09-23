@echo off
setlocal
call .venv\Scripts\activate.bat
if "%PORT%"=="" set PORT=8001
set PYTHONPATH=%CD%
uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload --log-level warning --no-access-log
endlocal
