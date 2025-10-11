# Restart on exit/crash and add throttle to avoid rapid restart loops

# Add NSSM to PATH for this session
$env:Path = "C:\nssm\nssm-2.24\win64;" + $env:Path

# Verify
# Write-Host "PATH is now: $env:Path"


nssm set AgenticTraderAPI  AppExit Default Restart
nssm set AgenticTraderAPI  AppThrottle 1500
nssm set AgenticTraderAuto AppExit Default Restart
nssm set AgenticTraderAuto AppThrottle 1500

# Start automatically on boot
sc.exe config AgenticTraderAPI  start= auto
sc.exe config AgenticTraderAuto start= auto
