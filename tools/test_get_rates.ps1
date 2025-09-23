# tools/test_get_rates.ps1
param(
    [string]$symbol = "EURUSD-ECNc",
    [string]$tf = "M15",
    [int]$n = 20
)

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/inspect/candles?symbol=$symbol&tf=$tf&n=$n" `
  -Method GET |
  ConvertTo-Json -Depth 6
