import logging
import os
import sys

import MetaTrader5 as mt5

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Read MT5 path from env (optional) ---
MT5_PATH = os.getenv("MT5_PATH", None)


def main():
    # Initialise MT5
    if MT5_PATH:
        ok = mt5.initialize(path=MT5_PATH)
    else:
        ok = mt5.initialize()

    if not ok:
        print("❌ MT5 init failed:", mt5.last_error())
        sys.exit(1)

    symbol = "NAS100.s"

    # Ensure symbol is selected
    if not mt5.symbol_select(symbol, True):
        print(f"❌ Could not select {symbol}")
        sys.exit(1)

    info = mt5.symbol_info(symbol)
    if not info:
        print(f"❌ No info for {symbol}")
        sys.exit(1)

    # Print only volume limits
    print(
        {
            "symbol": info.name,
            "digits": info.digits,
            "volume_min": float(info.volume_min),
            "volume_step": float(info.volume_step),
            "volume_max": float(info.volume_max),
        }
    )

    mt5.shutdown()


if __name__ == "__main__":
    main()
