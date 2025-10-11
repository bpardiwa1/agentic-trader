from __future__ import annotations
import os, re, pandas as pd
from typing import Any, Optional
from .momentum import _ema, _rsi, _env_int, _env_float

def _symkey(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", (s or "").upper())

def _eps_for(symbol: str) -> float:
    key = f"INDICES_EPS_{_symkey(symbol)}"
    return float(os.getenv(key, os.getenv("INDICES_EPS_DEFAULT", "10")))

def _sl_for(symbol: str) -> float:
    key = f"INDICES_SL_{_symkey(symbol)}"
    return float(os.getenv(key, os.getenv("INDICES_SL_DEFAULT", "120")))

def _tp_for(symbol: str) -> float:
    key = f"INDICES_TP_{_symkey(symbol)}"
    return float(os.getenv(key, os.getenv("INDICES_TP_DEFAULT", "240")))

def indices_momentum_signal(symbol: str, timeframe: str, df: pd.DataFrame) -> Optional[dict[str, Any]]:
    if df is None or df.empty or "close" not in df.columns:
        return None

    ema_fast_n = _env_int("IND_EMA_FAST", 50)
    ema_slow_n = _env_int("IND_EMA_SLOW", 200)
    rsi_p      = _env_int("IND_RSI_PERIOD", 14)
    long_th    = _env_int("IND_RSI_LONG_TH", 55)
    short_th   = _env_int("IND_RSI_SHORT_TH", 45)

    eps   = _eps_for(symbol)
    sl_pp = _sl_for(symbol)
    tp_pp = _tp_for(symbol)

    close = df["close"].astype(float)
    if len(close) < max(ema_slow_n, ema_fast_n, rsi_p) + 5:
        return None

    ema_fast = _ema(close, ema_fast_n)
    ema_slow = _ema(close, ema_slow_n)
    rsi = _rsi(close, rsi_p)

    price = float(close.iloc[-1]); ef = float(ema_fast.iloc[-1]); es = float(ema_slow.iloc[-1]); r = float(rsi.iloc[-1])

    long_ok  = (price > max(ef, es) + eps) and (r > long_th)
    short_ok = (price < min(ef, es) - eps) and (r < short_th)

    if long_ok:
        return {"side":"LONG","entry":price,"sl_pips":sl_pp,"tp_pips":tp_pp,"note":"indices_momentum",
                "debug":{"price":price,"ema_fast":ef,"ema_slow":es,"rsi":r,"eps":eps}}
    if short_ok:
        return {"side":"SHORT","entry":price,"sl_pips":sl_pp,"tp_pips":tp_pp,"note":"indices_momentum",
                "debug":{"price":price,"ema_fast":ef,"ema_slow":es,"rsi":r,"eps":eps}}
    return {"side":"","note":"no_trade","debug":{"price":price,"ema_fast":ef,"ema_slow":es,"rsi":r,"eps":eps},
            "why":["conditions not met"]}
