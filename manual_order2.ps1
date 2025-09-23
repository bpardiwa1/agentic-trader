$body = @{
  symbol = "XAUUSD-ECNc"
  side   = "LONG"
  sl_pips = 300
  tp_pips = 600
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/orders/market" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body | ConvertTo-Json -Depth 6


  $body = @{
  symbol  = "EURUSD-ECNc"   # use the exact broker symbol
  side    = "LONG"          # or "SHORT"
  price   = 0               # accepted by API, ignored by executor
  sl_pips = 30              # stop-loss 30 pips (~0.0030)
  tp_pips = 60              # take-profit 60 pips (~0.0060)
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/orders/market" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body | ConvertTo-Json -Depth 6