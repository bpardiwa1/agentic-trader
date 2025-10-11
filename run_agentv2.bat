@echo off
REM --------------------------------------------------------
REM run_agent.bat - wrapper to launch app\scripts\run_agent.ps1
REM bypasses PowerShell execution policy
REM Usage examples:
REM   run_agent.bat -Asset FX -Env "app\env\core.env,app\env\fx.env"
REM   run_agent.bat -Asset XAU -Env "app\env\core.env,app\env\xau.env" -Port 8002
REM --------------------------------------------------------

SETLOCAL
SET SCRIPT=app\scripts\run_agentv2.ps1

IF NOT EXIST "%SCRIPT%" (
    echo ERROR: %SCRIPT% not found!
    EXIT /B 1
)

powershell -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT%" %*
ENDLOCAL
