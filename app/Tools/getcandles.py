import MetaTrader5 as mt5
from app.util.mt5_bars import get_bars

mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe")

for sym in ["EURUSD-ECNc", "GBPUSD-ECNc", "AUDUSD-ECNc"]:
    df = get_bars(sym, "M15", 100)
    print(
        sym,
        "->",
        "ok" if df is not None and not df.empty else "❌ no data",
        len(df) if df is not None else 0,
    )

mt5.shutdown()
