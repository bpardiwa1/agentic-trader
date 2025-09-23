param(
  [string]$symbol = "EURUSD-ECNc",
  [string]$tf     = "M15",
  [string]$agent  = "auto",
  [string]$base   = "http://127.0.0.1:8001"
)

$uri = "$base/agents/decide?symbol=$symbol&tf=$tf&agent=$agent&execute=true"
Invoke-RestMethod $uri | ConvertTo-Json -Depth 6
