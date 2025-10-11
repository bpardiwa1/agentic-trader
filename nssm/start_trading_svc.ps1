$env:Path = "C:\nssm\nssm-2.24\win64;" + $env:Path

# Verify
# Write-Host "PATH is now: $env:Path"

nssm start AgenticTraderAPI
nssm start AgenticTraderAuto