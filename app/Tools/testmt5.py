from typing import Any

import MetaTrader5 as _mt5
import MetaTrader5 as mt5

# Cast to Any to silence Pylance false errors
mt5: Any = _mt5  # type: ignore

if mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    print("✅ Connected to MT5:", mt5.version())
    print("Account Info:", mt5.account_info())
    mt5.shutdown()
else:
    print("❌ Initialize failed:", mt5.last_error())
