@echo off
REM Kill uvicorn server processes
for /f "tokens=2 delims=," %%a in ('tasklist /fi "imagename eq python.exe" /fo csv ^| findstr /i "uvicorn"') do taskkill /pid %%~a /f

REM Kill auto_runner.py processes
for /f "tokens=2 delims=," %%a in ('tasklist /fi "imagename eq python.exe" /fo csv ^| findstr /i "auto_runner.py"') do taskkill /pid %%~a /f

echo All agentic-trader processes stopped.
