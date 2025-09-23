Invoke-RestMethod "http://127.0.0.1:8001/health" | ConvertTo-Json -Depth 6
Invoke-RestMethod "http://127.0.0.1:8001/mt5/ping" | ConvertTo-Json -Depth 6
