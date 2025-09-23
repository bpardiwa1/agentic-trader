param(
  [string]$symbol="EURUSD-ECNc",
  [ValidateSet("LONG","SHORT","BUY","SELL")] [string]$side="LONG",
  [int]$sl_pips=30, [int]$tp_pips=60
)
$body = @{ symbol=$symbol; side=$side; price=0; sl_pips=$sl_pips; tp_pips=$tp_pips } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8001/orders/market" -Method POST -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
