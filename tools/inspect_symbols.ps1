param([string]$q="XAU")
Invoke-RestMethod "http://127.0.0.1:8001/mt5/search_symbols?q=$q" | ConvertTo-Json -Depth 6
