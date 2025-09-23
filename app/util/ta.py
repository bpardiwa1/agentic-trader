# app/util/ta.py
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: list[float] | np.ndarray, period: int) -> np.ndarray:
    """
    Exponential Moving Average (EMA).
    Falls back to NaN array if not enough data.
    """
    arr = np.asarray(series, dtype=float)
    if arr.size < period:
        return np.full_like(arr, np.nan, dtype=float)
    return pd.Series(arr).ewm(span=period, adjust=False).mean().to_numpy(dtype=float)


def rsi(series: list[float] | np.ndarray, period: int = 14) -> np.ndarray:
    """
    Relative Strength Index (RSI).
    Returns an array aligned with input series.
    """
    arr = np.asarray(series, dtype=float)
    n = arr.size
    if n < period + 1:
        return np.full(n, np.nan, dtype=float)

    deltas = np.diff(arr)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0.0

    out = np.zeros(n, dtype=float)
    out[:period] = np.nan
    out[period] = 100.0 - 100.0 / (1.0 + rs)

    up_val, down_val = up, down
    for i in range(period + 1, n):
        delta = deltas[i - 1]
        up_val = (up_val * (period - 1) + max(delta, 0.0)) / period
        down_val = (down_val * (period - 1) + max(-delta, 0.0)) / period
        rs = up_val / down_val if down_val != 0 else 0.0
        out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def atr(
    highs: list[float] | np.ndarray,
    lows: list[float] | np.ndarray,
    closes: list[float] | np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Average True Range (ATR).
    Returns array aligned with closes length.
    """
    highs_arr = np.asarray(highs, dtype=float)
    lows_arr = np.asarray(lows, dtype=float)
    closes_arr = np.asarray(closes, dtype=float)

    n = closes_arr.size
    if n < period + 1:
        return np.full(n, np.nan, dtype=float)

    trs = np.zeros(n, dtype=float)
    trs[0] = np.nan
    for i in range(1, n):
        trs[i] = max(
            highs_arr[i] - lows_arr[i],
            abs(highs_arr[i] - closes_arr[i - 1]),
            abs(lows_arr[i] - closes_arr[i - 1]),
        )

    atr_out = np.full(n, np.nan, dtype=float)
    atr_out[period] = np.nanmean(trs[1 : period + 1])
    for i in range(period + 1, n):
        atr_out[i] = (atr_out[i - 1] * (period - 1) + trs[i]) / period
    return atr_out
