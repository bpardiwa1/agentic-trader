param(
  [string]$symbol = "EURUSD-ECNc",
  [string]$tf = "M15",
  [int]$n = 5
)

Invoke-RestMethod "http://127.0.0.1:8001/inspect/candles?symbol=$symbol&tf=$tf&n=$n" | ConvertTo-Json -Depth 6

# Candle example