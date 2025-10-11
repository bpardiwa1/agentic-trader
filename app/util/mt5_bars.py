# ============================================================
# app/util/mt5_bars.py
# Agentic Trader - MT5 OHLCV Fetch Utility (timeframe-safe)
# ============================================================

import os
from typing import Any

import MetaTrader5 as _mt5
import pandas as pd

mt5: Any = _mt5  # cast to Any to silence type warnings


# ============================================================
# Internal: Normalize timeframe strings
# ============================================================
def _resolve_timeframe(tf_in: str):
    """
    Accepts '15m'/'M15', '1h'/'H1', '1d'/'D1', etc. and returns
    the corresponding MT5 timeframe constant.
    """
    s = str(tf_in).strip().upper()

    # Normalize numeric-first forms: '15M' -> 'M15', '1H' -> 'H1', etc.
    if s.endswith("M") and s[:-1].isdigit():
        s = "M" + s[:-1]
    elif s.endswith("H") and s[:-1].isdigit():
        s = "H" + s[:-1]
    elif s.endswith("D") and s[:-1].isdigit():
        s = "D" + s[:-1]
    elif s.endswith("W") and s[:-1].isdigit():
        s = "W" + s[:-1]
    elif s.endswith("MN") and s[:-2].isdigit():  # '1MN'
        s = "MN" + s[:-2]

    mapping = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }

    return mapping.get(s)


# ============================================================
# Core bar fetch function
# ============================================================
def get_bars(symbol: str, timeframe: str, count: int = 300) -> pd.DataFrame | None:
    """
    Fetch OHLCV bars from MetaTrader 5 and return as DataFrame.
    Handles both normalized timeframes and reinitializes if needed.
    """
    mt5_path = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

    if not mt5.initialize(mt5_path):
        print("[WARN] MT5 not initialized, retrying ...")
        if not mt5.initialize():
            print("[ERROR] MT5 initialization failed:", mt5.last_error())
            return None

    # Ensure symbol is visible and subscribed
    if not mt5.symbol_select(symbol, True):
        print(f"[WARN] Failed to select symbol {symbol}")
        return None

    tf = _resolve_timeframe(timeframe)
    if tf is None:
        print(f"[ERROR] Invalid timeframe '{timeframe}'")
        return None

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        print(f"[WARN] No rates fetched for {symbol} ({timeframe})")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)

    print(f"[DEBUG] Refreshed {len(df)} bars for {symbol} ({timeframe})")
    return df


# ============================================================
# Helper to extract closes
# ============================================================
def get_closes(rates: Any) -> list[float]:
    """Normalize MT5 rates into a list of closing prices."""
    if rates is None:
        return []

    if isinstance(rates, pd.DataFrame):
        return rates["close"].tolist()

    try:
        return [r.close for r in rates]
    except Exception:
        return []
