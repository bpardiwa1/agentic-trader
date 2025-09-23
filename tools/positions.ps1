param([string]$symbol="")
if ($symbol) {
  Invoke-RestMethod "http://127.0.0.1:8001/positions?symbol=$symbol" | ConvertTo-Json -Depth 6
} else {
  Invoke-RestMethod "http://127.0.0.1:8001/positions" | ConvertTo-Json -Depth 6
}
