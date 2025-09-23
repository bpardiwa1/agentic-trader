import os

import numpy as np

from app.market.data import get_rates


def _envf(name, dflt):
    try:
        return float(os.getenv(name, str(dflt)).split("#", 1)[0].strip())
    except:
        return dflt


def _envi(name, dflt):
    try:
        return int(float(os.getenv(name, str(dflt)).split("#", 1)[0].strip()))
    except:
        return dflt


def _ema(arr, period):
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def macd_crossover_signal(symbol: str, timeframe: str = "M15") -> dict:
    FAST = _envi("MACD_FAST", 12)
    SLOW = _envi("MACD_SLOW", 26)
    SIG = _envi("MACD_SIGNAL", 9)
    HIST_MIN = _envf("MACD_MIN_HIST", 0.0)  # optional min histogram magnitude

    df = get_rates(symbol, timeframe, count=max(300, SLOW + SIG + 20))
    if df is None or df.empty:
        return {"debug": {"len": 0}, "why": ["no data"]}

    closes = df["close"].to_numpy(float)
    ema_f = _ema(closes, FAST)
    ema_s = _ema(closes, SLOW)
    macd = ema_f - ema_s
    signal = _ema(macd, SIG)
    hist = macd - signal

    last = int(len(closes) - 1)
    prev = last - 1

    cross_up = (hist[prev] <= 0) and (hist[last] > 0)
    cross_down = (hist[prev] >= 0) and (hist[last] < 0)

    debug = {
        "price": float(closes[-1]),
        "macd": float(macd[-1]),
        "signal": float(signal[-1]),
        "hist": float(hist[-1]),
        "tf": timeframe,
        "cfg": dict(FAST=FAST, SLOW=SLOW, SIGNAL=SIG, HIST_MIN=HIST_MIN),
    }

    if cross_up and abs(hist[last]) >= HIST_MIN:
        return {
            "side": "LONG",
            "size": None,
            "sl_pips": None,
            "tp_pips": None,
            "entry": float(closes[-1]),
            "note": "macd_up",
            "debug": debug,
        }

    if cross_down and abs(hist[last]) >= HIST_MIN:
        return {
            "side": "SHORT",
            "size": None,
            "sl_pips": None,
            "tp_pips": None,
            "entry": float(closes[-1]),
            "note": "macd_down",
            "debug": debug,
        }

    why = []
    if not cross_up and not cross_down:
        why.append("no macd cross")
    if abs(hist[last]) < HIST_MIN:
        why.append(f"|hist|<{HIST_MIN}")
    return {"debug": debug, "why": why}
