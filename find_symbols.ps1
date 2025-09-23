# Search for EURUSD
Invoke-RestMethod "http://127.0.0.1:8001/mt5/search_symbols?q=EURUSD" | ConvertTo-Json -Depth 4

# Search for Gold
Invoke-RestMethod "http://127.0.0.1:8001/mt5/search_symbols?q=XAU" | ConvertTo-Json -Depth 4
