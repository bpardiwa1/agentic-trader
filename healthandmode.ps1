$health = Invoke-RestMethod "http://127.0.0.1:8001/health" | out-string
Write-Output $health
$ping = Invoke-RestMethod "http://127.0.0.1:8001/mt5/ping" | out-string
Write-Output $ping
