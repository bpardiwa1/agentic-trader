# Add NSSM to PATH for this session
$env:Path = "C:\nssm\nssm-2.24\win64;" + $env:Path
Write-Host "Setting services up using nssm"

nssm.exe stop  AgenticTraderAPI
nssm.exe stop  AgenticTraderAuto
nssm.exe start AgenticTraderAPI
nssm.exe start AgenticTraderAuto

# Get-Content C:\agentic-trader\logs\api\stdout.log  -Wait
# In another terminal:
# Get-Content C:\agentic-trader\logs\auto\stdout.log -Wait


