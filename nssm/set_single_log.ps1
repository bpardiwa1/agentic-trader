# Paths# Requires: nssm 2.24
$ErrorActionPreference = 'Stop'

# Config
$nssm = 'C:\nssm\nssm-2.24\win64\nssm.exe'
$root = 'C:\agentic-trader'
$apiLog  = Join-Path $root 'logs\api\service.log'
$autoLog = Join-Path $root 'logs\auto\service.log'

# Rotation settings compatible with 2.24:
$rotateFiles   = 1      # enable rotation
$rotateOnline  = 1      # rotate without stopping process
$rotateSeconds = 0      # 0 = time-based rotation disabled
# Rotate at ~10 MB
$rotateBytes        = 10485760      # low 32-bit
$rotateBytesHigh    = 0             # high 32-bit (for files >4GB; keep 0)

# Ensure folders exist
New-Item -ItemType Directory -Force -Path (Split-Path $apiLog)  | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $autoLog) | Out-Null

function Set-Logs($svc, $logPath) {
  & $nssm stop $svc | Out-Null

  & $nssm set $svc AppStdout $logPath
  & $nssm set $svc AppStderr $logPath

  & $nssm set $svc AppRotateFiles  $rotateFiles
  & $nssm set $svc AppRotateOnline $rotateOnline
  & $nssm set $svc AppRotateSeconds $rotateSeconds
  & $nssm set $svc AppRotateBytes      $rotateBytes
  & $nssm set $svc AppRotateBytesHigh  $rotateBytesHigh

  & $nssm start $svc | Out-Null
}

Set-Logs -svc 'AgenticTraderAPI'  -logPath $apiLog
Set-Logs -svc 'AgenticTraderAuto' -logPath $autoLog

Write-Host "Configured logging + rotation on:"
Write-Host " - AgenticTraderAPI  -> $apiLog"
Write-Host " - AgenticTraderAuto -> $autoLog"

