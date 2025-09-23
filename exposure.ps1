
$PositionCount      = (Invoke-RestMethod "http://127.0.0.1:8001/positions").positions.Count
$EURUSDPositionCount = (Invoke-RestMethod "http://127.0.0.1:8001/positions?symbol=EURUSD").positions.Count
$XAUUSDPositionCount = (Invoke-RestMethod "http://127.0.0.1:8001/positions?symbol=XAUUSD").positions.Count

Write-Host "Total Positions = $PositionCount | EURUSD Positions = $EURUSDPositionCount | XAUUSD Positions = $XAUUSDPositionCount"
