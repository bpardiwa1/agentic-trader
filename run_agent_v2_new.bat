@echo off
setlocal enabledelayedexpansion

REM =============================================================
REM Agentic Trader v2 Unified Launcher (.BAT)
REM Supports FX / XAU / INDEX / EQUITY with auto experimental mode
REM =============================================================

set "Asset=%~1"
set "Port=%~2"
set "Env=%~3"
set "Log=%~4"

REM Default parameters
if "%Asset%"=="" set "Asset=FX"
if "%Env%"=="" set "Env=app\env\core.env"

echo Starting Agentic Trader (%Asset% Momentum v2)

REM -----------------------------
REM Assign default ports
REM -----------------------------
if /I "%Asset%"=="FX" (
    if "%Port%"=="" set "Port=9101"
) else if /I "%Asset%"=="XAU" (
    if "%Port%"=="" set "Port=9102"
) else if /I "%Asset%"=="INDEX" (
    if "%Port%"=="" set "Port=9103"
) else if /I "%Asset%"=="EQUITY" (
    if "%Port%"=="" set "Port=9104"
) else (
    if "%Port%"=="" set "Port=9110"
)
echo Assigned Port: %Port%

REM -----------------------------
REM Resolve paths
REM -----------------------------
set "Root=%~dp0\..\.."
for %%I in ("%Root%") do set "Root=%%~fI"
set "EnvDir=%Root%\app\env"
set "MergedDir=%EnvDir%\.merged"
if not exist "%MergedDir%" mkdir "%MergedDir%"

REM -----------------------------
REM Merge env files
REM -----------------------------
setlocal disableDelayedExpansion
set "MergedFile=%MergedDir%\env.%Asset%.merged.env"
echo Using env file: %MergedFile%

(
    echo # --- merged env for %Asset% (v2) ---
) > "%MergedFile%"

for %%F in (%Env%) do (
    set "FilePath=%Root%\%%~F"
    if exist "!FilePath!" (
        type "!FilePath!" >> "%MergedFile%"
    ) else (
        echo WARNING: env file not found: !FilePath!
    )
)
endlocal

REM -----------------------------
REM Ensure logs directory
REM -----------------------------
set "LogDir=%Root%\logs"
if not exist "%LogDir%" mkdir "%LogDir%"

REM -----------------------------
REM Setup timestamped logs
REM -----------------------------
for /f "tokens=1-4 delims=/:. " %%a in ("%date% %time%") do (
    set ts=%%a-%%b-%%c_%%d
)
if "%Log%"=="" set "Log=%LogDir%\%Asset%_v2_%ts%.log"
set "LatestLog=%LogDir%\%Asset%.latest.log"

echo Logging to %Log%
echo Latest log link: %LatestLog%

copy "%Log%" "%LatestLog%" >nul 2>&1

REM -----------------------------
REM Build command
REM -----------------------------
set "cmd=python.exe"
set "uniargs=-m uvicorn app.main:app --host 127.0.0.1 --port %Port%"

REM -----------------------------
REM Environment variables
REM -----------------------------
set "ASSET=%Asset%"
set "DOTENV_FILE=%MergedFile%"

REM Auto-enable experimental flag based on asset
if /I "%Asset%"=="FX" (
    set "USE_EXPERIMENTAL_FX=true"
    set "USE_EXPERIMENTAL_XAU=false"
    set "USE_EXPERIMENTAL_INDEX=false"
    echo USE_EXPERIMENTAL_FX set to true
) else if /I "%Asset%"=="XAU" (
    set "USE_EXPERIMENTAL_FX=false"
    set "USE_EXPERIMENTAL_XAU=true"
    set "USE_EXPERIMENTAL_INDEX=false"
    echo USE_EXPERIMENTAL_XAU set to true
) else if /I "%Asset%"=="INDEX" (
    set "USE_EXPERIMENTAL_FX=false"
    set "USE_EXPERIMENTAL_XAU=false"
    set "USE_EXPERIMENTAL_INDEX=true"
    echo USE_EXPERIMENTAL_INDEX set to true
) else (
    set "USE_EXPERIMENTAL_FX=false"
    set "USE_EXPERIMENTAL_XAU=false"
    set "USE_EXPERIMENTAL_INDEX=false"
)

echo Running: %cmd% %uniargs%
echo Merged env: %MergedFile%
echo Experimental flags -> FX: %USE_EXPERIMENTAL_FX% ^| XAU: %USE_EXPERIMENTAL_XAU% ^| INDEX: %USE_EXPERIMENTAL_INDEX%

REM -----------------------------
REM Run & mirror logs
REM -----------------------------
%cmd% %uniargs% | tee "%Log%" >> "%LatestLog%"
endlocal
