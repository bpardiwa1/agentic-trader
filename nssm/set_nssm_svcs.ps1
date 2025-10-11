# Add NSSM to PATH for this session
$env:Path = "C:\nssm\nssm-2.24\win64;" + $env:Path
Write-Host "Setting services up using $NSSM"


# API service
nssm stop AgenticTraderAPI
nssm set AgenticTraderAPI  Application  C:\Windows\System32\cmd.exe
nssm set AgenticTraderAPI  AppParameters '/c "C:\agentic-trader\start_safe.bat"'
nssm set AgenticTraderAPI  AppDirectory  C:\agentic-trader

# Auto service
nssm stop AgenticTraderAuto
nssm set AgenticTraderAuto Application  C:\Windows\System32\cmd.exe
nssm set AgenticTraderAuto AppParameters '/c "C:\agentic-trader\start_auto_safe.bat"'
nssm set AgenticTraderAuto AppDirectory  C:\agentic-trader
