Here’s the improved version of tools\inspect_candles.ps1 with parameters:

param(
  [string]$symbol = "EURUSD-ECNc",
  [string]$tf = "M15",
  [int]$n = 5
)

Invoke-RestMethod "http://127.0.0.1:8001/inspect/candles?symbol=$symbol&tf=$tf&n=$n" | ConvertTo-Json -Depth 6

Usage examples

Inspect last 3 candles on XAUUSD-ECNc:

tools\inspect_candles.ps1 -symbol XAUUSD-ECNc -tf M15 -n 3


Inspect last 10 candles on NAS100:

tools\inspect_candles.ps1 -symbol NAS100 -tf H1 -n 10


Inspect last 2 candles on MSFT:

tools\inspect_candles.ps1 -symbol MSFT -tf D1 -n 2


👉 We can apply the same pattern to the other scripts (decide_preview.ps1, decide_execute.ps1, manual_order_fx.ps1, etc.), so you only need to type the symbol and parameters at runtime.

Would you like me to go through each script in the toolkit and make them fully parameterized (so you can reuse them for any asset without editing)?

You said:
what is the tf and -n parameters for?
ChatGPT said:

Great question 👍 — let’s break down what those two parameters mean in the context of inspect_candles.ps1 (and the /inspect/candles endpoint):

📌 -tf (timeframe)

This tells MT5 what candle interval you want.

Examples:

"M1" → 1-minute bars

"M5" → 5-minute bars

"M15" → 15-minute bars

"H1" → 1-hour bars

"H4" → 4-hour bars

"D1" → 1-day bars

So if you run:

tools\inspect_candles.ps1 -symbol XAUUSD-ECNc -tf M15


👉 You’ll get the last few 15-minute candles for gold.

📌 -n (number of candles)

This tells the endpoint how many recent candles to return.

Default in our script is 5.

If you want a quick snapshot, you might use -n 3.

If you want more context, maybe -n 20.

Example:

tools\inspect_candles.ps1 -symbol EURUSD-ECNc -tf H1 -n 10


👉 Returns the last 10 one-hour candles for EURUSD.

📊 Why this matters

Trading strategies often use different timeframes:

Scalpers → M1/M5

Swing traders → H1/H4

Long-term → D1

The number of candles (-n) helps you quickly inspect if your bot is seeing correct data.
For example:

-n 3 is enough to spot the most recent activity.

-n 100 would let you see a full dataset for analysis.

✅ So together:

-tf = candle duration

-n = how many candles to fetch