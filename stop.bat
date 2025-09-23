@echo off
for /f "tokens=2 delims=," %%a in ('tasklist /fi "imagename eq python.exe" /fo csv ^| findstr /i "uvicorn"') do taskkill /pid %%~a /f
