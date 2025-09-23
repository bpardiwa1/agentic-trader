# app/strategies/momentum.py
from __future__ import annotations

import os
from typing import Any, Iterable

import numpy as np
import pandas as pd


def _envf(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).split("#", 1)[0].strip())
    except Exception:
        return default


def _envi(name: str, default: int) -> int:
    try:
        return int(float((os.getenv(name) or str(default)).split("#", 1)[0].strip()))
    except Exception:
        return default


def _is_xau(symbol: str) -> bool:
    s = (symbol or "").upper()
    return "XAU" in s or "GOLD" in s


def _to_dataframe(rates: Any) -> pd.DataFrame:
    """
    Normalize `rates` into a DataFrame with ['time','open','high','low','close'].
    """
    if rates is None:
        raise ValueError("rates is None")

    if isinstance(rates, pd.DataFrame):
        df = rates.copy()
    elif isinstance(rates, np.ndarray):
        df = pd.DataFrame(rates)
    elif isinstance(rates, Iterable):
        df = pd.DataFrame(list(rates))
    else:
        raise TypeError(f"Unsupported rates type: {type(rates)}")

    needed = ["time", "open", "high", "low", "close"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Rates missing columns: {missing}")

    if np.issubdtype(df["time"].dtype, np.number):
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

    return df.reset_index(drop=True)


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) == 0:
        return np.array([], dtype=float)
    k = 2.0 / (n + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + k * (x[i] - out[i - 1])
    return out


def _rsi(x: np.ndarray, period: int = 14) -> np.ndarray:
    if len(x) < period + 1:
        return np.full(len(x), np.nan, dtype=float)
    deltas = np.diff(x)
    gains = np.maximum(deltas, 0.0)
    losses = np.maximum(-deltas, 0.0)
    g = _ema(gains, period)
    l = _ema(losses, period)
    rs = np.divide(g, l, out=np.zeros_like(g), where=l != 0)
    r = 100.0 - (100.0 / (1.0 + rs))
    r = np.concatenate([[50.0], r])  # align length
    return r.astype(float)


def momentum_signal(symbol: str, timeframe: str, rates: Any) -> dict[str, Any] | None:
    try:
        df = _to_dataframe(rates)
    except Exception as exc:
        return {"side": "", "note": "data_error", "debug": {"error": str(exc)}, "why": ["bad rates input"]}

    if df.empty:
        return {"side": "", "note": "no_trade", "debug": {"len": 0}, "why": ["empty dataframe"]}

    # --- parameter selection
    if _is_xau(symbol):
        ema_fast = _envi("MOMENTUM_XAU_EMA_FAST", 50)
        ema_slow = _envi("MOMENTUM_XAU_EMA_SLOW", 200)
        rsi_p = _envi("MOMENTUM_XAU_RSI_PERIOD", 14)
        atr_min = _envf("MOMENTUM_XAU_MIN_ATR", 0.0)
        rsi_long = _envf("MOMENTUM_XAU_RSI_LONG_TH", 50.0)
        rsi_short = _envf("MOMENTUM_XAU_RSI_SHORT_TH", 40.0)
        default_sl, default_tp = 300.0, 600.0
    else:
        ema_fast = _envi("MOMENTUM_FX_EMA_FAST", 50)
        ema_slow = _envi("MOMENTUM_FX_EMA_SLOW", 200)
        rsi_p = _envi("MOMENTUM_FX_RSI_PERIOD", 14)
        atr_min = _envf("MOMENTUM_FX_MIN_ATR", 0.0)
        rsi_long = _envf("MOMENTUM_FX_RSI_LONG_TH", 50.0)
        rsi_short = _envf("MOMENTUM_FX_RSI_SHORT_TH", 40.0)
        default_sl, default_tp = 60.0, 120.0

    closes = df["close"].to_numpy(float)
    highs = df["high"].to_numpy(float)
    lows = df["low"].to_numpy(float)

    min_bars = max(ema_slow + 5, rsi_p + 5, 60)
    if len(closes) < min_bars:
        return {"side": "", "note": "no_trade", "debug": {"len": len(closes), "need": min_bars}, "why": ["not enough bars"]}

    ema_f = _ema(closes, ema_fast)
    ema_s = _ema(closes, ema_slow)
    rsi14 = _rsi(closes, rsi_p)

    price = float(closes[-1])
    ef = float(ema_f[-1])
    es = float(ema_s[-1])
    rlast = float(rsi14[-1])

    # Conditions
    long_ok = (ef > es) and (rlast > rsi_long)
    short_ok = (ef < es) and (rlast < rsi_short)

    debug = {"price": price, "ema_fast": ef, "ema_slow": es, "rsi": rlast, "tf": timeframe}

    if long_ok:
        return {"side": "LONG", "sl_pips": default_sl, "tp_pips": default_tp, "note": "momentum", "debug": debug, "why": ["EMA> and RSI>"]}
    if short_ok:
        return {"side": "SHORT", "sl_pips": default_sl, "tp_pips": default_tp, "note": "momentum", "debug": debug, "why": ["EMA< and RSI<"]}

    return {"side": "", "note": "no_trade", "debug": debug, "why": ["conditions not met"]}
