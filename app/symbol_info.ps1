Invoke-RestMethod "http://127.0.0.1:8001/mt5/symbol_info?symbol=EURUSD-ECNc" | ConvertTo-Json -Depth 6
Invoke-RestMethod "http://127.0.0.1:8001/mt5/symbol_info?symbol=XAUUSD-ECNc" | ConvertTo-Json -Depth 6
