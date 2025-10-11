@echo off
REM run_auto_safe.bat with logging

setlocal
call .venv\Scripts\activate

REM FX bot logs -> logs/fx.log
start "" powershell -ExecutionPolicy Bypass -Command ^
  "app\scripts\run_agent.ps1 -Asset FX *>&1 | Tee-Object -FilePath logs\fx.log"

REM Gold bot logs -> logs/xau.log
start "" powershell -ExecutionPolicy Bypass -Command ^
  "app\scripts\run_agent.ps1 -Asset XAU *>&1 | Tee-Object -FilePath logs\xau.log"

REM Indices bot logs -> logs/indices.log
start "" powershell -ExecutionPolicy Bypass -Command ^
  "app\scripts\run_agent.ps1 -Asset INDICES *>&1 | Tee-Object -FilePath logs\indices.log"

REM Equities bot logs -> logs/equities.log
start "" powershell -ExecutionPolicy Bypass -Command ^
  "app\scripts\run_agent.ps1 -Asset EQUITIES *>&1 | Tee-Object -FilePath logs\equities.log"

endlocal
