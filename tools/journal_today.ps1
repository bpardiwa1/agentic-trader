param([int]$limit=50)
Invoke-RestMethod "http://127.0.0.1:8001/journal/today?limit=$limit" | ConvertTo-Json -Depth 6
