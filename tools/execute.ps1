param([string]$symbol="EURUSD-ECNc",[string]$tf="M15",[string]$agent="auto")
Invoke-RestMethod "http://127.0.0.1:8001/agents/decide?symbol=$symbol&tf=$tf&agent=$agent&execute=true" | ConvertTo-Json -Depth 6
