# Agentic Trader – Daily Checklist

## Before overnight run
- Verify `.env` (symbols, MT5 creds, guardrails)
- Start server: `.\start.bat`
- Start auto safe: `.\start_auto_safe.bat`
- Quick health: `tools\check_health.ps1`

## Debug / spot-check
- Symbols visible: `tools\inspect_symbols.ps1 -q XAU`
- Candles: `tools\inspect_candles.ps1 -symbol XAUUSD-ECNc -tf M15 -n 3`
- Strategy preview: `tools\decide_preview.ps1 -symbol EURUSD-ECNc`
- Force execution: `tools\decide_execute.ps1 -symbol EURUSD-ECNc`

## Manual orders
- EURUSD: `tools\manual_order_fx.ps1 -symbol EURUSD-ECNc -side LONG -sl_pips 30 -tp_pips 60`
- XAUUSD: `tools\manual_order_xau.ps1 -symbol XAUUSD-ECNc -side LONG -sl_pips 300 -tp_pips 600`

## Positions
- All: `tools\positions.ps1`
- One symbol: `tools\positions.ps1 -symbol EURUSD-ECNc`
- Close by symbol: `tools\close_all.ps1 -symbol EURUSD-ECNc`

## Morning
- Journal quick view: `tools\journal_today.ps1 -limit 50`
- Performance: `python tools\analyze_journal.py`
- Backup: `tools\backup_full.ps1` (zip) or `tools\backup_copy.ps1` (folder)
