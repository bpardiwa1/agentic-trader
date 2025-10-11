from __future__ import annotations

import os
from typing import Any

import pandas as pd

from app.market.data import compute_context
from app.strategies.fx_momentum import _ema, _env_float, _env_int, _rsi


def _is_blackout(symbol: str) -> bool:
    bl = (os.getenv("EARNINGS_BLACKOUT") or "").strip()
    if not bl:
        return False
    # Format: MSFT:2025-10-23;AAPL:2025-10-30
    sym = symbol.split(".", 1)[0].upper()
    for item in [x for x in bl.split(";") if x.strip()]:
        k = item.split(":", 1)[0].upper().strip()
        if k == sym:
            return True
    return False


def equities_momentum_signal(
    symbol: str, timeframe: str, df: pd.DataFrame
) -> dict[str, Any] | None:
    if df is None or df.empty or "close" not in df.columns:
        return None
    if _is_blackout(symbol):
        return {"side": "", "note": "no_trade", "why": ["earnings blackout"]}

    ema_fast_n = _env_int("EQ_EMA_FAST", 20)
    ema_slow_n = _env_int("EQ_EMA_SLOW", 100)
    rsi_p = _env_int("EQ_RSI_PERIOD", 14)
    long_th = _env_int("EQ_RSI_LONG_TH", 55)
    short_th = _env_int("EQ_RSI_SHORT_TH", 45)
    eps = _env_float("EQ_EPS", 0.25)

    close = df["close"].astype(float)
    if len(close) < max(ema_slow_n, ema_fast_n, rsi_p) + 5:
        return None

    ema_fast = _ema(close, ema_fast_n)
    ema_slow = _ema(close, ema_slow_n)
    rsi = _rsi(close, rsi_p)

    price = float(close.iloc[-1])
    ef = float(ema_fast.iloc[-1])
    es = float(ema_slow.iloc[-1])
    r = float(rsi.iloc[-1])

    # HTF (H1) confirmation
    ctx = compute_context(symbol, "H1", 300)
    regime = ctx["regime"] if ctx.get("ok") else "UNKNOWN"

    long_ok = (price > max(ef, es) + eps) and (r > long_th) and (regime == "TRENDING_UP")
    short_ok = (price < min(ef, es) - eps) and (r < short_th) and (regime == "TRENDING_DOWN")

    sl_pp = _env_float("EQ_SL_PIPS", 2.0)
    tp_pp = _env_float("EQ_TP_PIPS", 4.0)

    if long_ok:
        return {
            "side": "LONG",
            "entry": price,
            "sl_pips": sl_pp,
            "tp_pips": tp_pp,
            "note": "equities_momentum",
            "debug": {
                "price": price,
                "ema_fast": ef,
                "ema_slow": es,
                "rsi": r,
                "eps": eps,
                "regime": regime,
            },
        }
    if short_ok:
        return {
            "side": "SHORT",
            "entry": price,
            "sl_pips": sl_pp,
            "tp_pips": tp_pp,
            "note": "equities_momentum",
            "debug": {
                "price": price,
                "ema_fast": ef,
                "ema_slow": es,
                "rsi": r,
                "eps": eps,
                "regime": regime,
            },
        }
    return {
        "side": "",
        "note": "no_trade",
        "debug": {
            "price": price,
            "ema_fast": ef,
            "ema_slow": es,
            "rsi": r,
            "eps": eps,
            "regime": regime,
        },
        "why": ["conditions not met or HTF not aligned"],
    }
