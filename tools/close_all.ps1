param([string]$symbol="")
$body = @{}
if ($symbol) { $body.symbol = $symbol }
$body = $body | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8001/orders/close" -Method POST -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
