# manual_order.ps1
$body = @{
  symbol = "XAUUSD-ECNc"
  side   = "LONG"
  price  = 0        # server requires a price field; executor will use live tick
  sl_pips = 300
  tp_pips = 600
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/orders/market" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
| ConvertTo-Json -Depth 6
