from __future__ import annotations

from typing import Literal, TypedDict, Optional
import pandas as pd

Side = Literal["BULLISH", "BEARISH"]
TradeSide = Literal["LONG", "SHORT"]


class FVG(TypedDict):
    side: Side
    start_idx: int
    end_idx: int
    low: float
    high: float
    mid: float


def find_fvgs(df: pd.DataFrame, lookback: int = 100) -> list[FVG]:
    """
    Detect simple 3-candle FVGs using:
      - Bullish: C.low > A.high  -> gap [A.high, C.low]
      - Bearish: C.high < A.low  -> gap [C.high, A.low]
    Expects columns: 'high', 'low'. Returns most-recent last.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    start = max(2, n - lookback)
    out: list[FVG] = []

    for i in range(start, n):
        a = i - 2
        b = i - 1  # unused but shows classic A,B,C indexing
        c = i
        if a < 0:
            continue

        # Bullish FVG
        if lows[c] > highs[a]:
            low, high = float(highs[a]), float(lows[c])
            out.append({
                "side": "BULLISH",
                "start_idx": a,
                "end_idx": c,
                "low": low,
                "high": high,
                "mid": (low + high) / 2.0,
            })

        # Bearish FVG
        if highs[c] < lows[a]:
            low, high = float(highs[c]), float(lows[a])
            out.append({
                "side": "BEARISH",
                "start_idx": a,
                "end_idx": c,
                "low": low,
                "high": high,
                "mid": (low + high) / 2.0,
            })

    return out


def latest_same_side_fvg(
    df: pd.DataFrame, side: TradeSide, lookback: int = 100
) -> Optional[FVG]:
    fvgs = find_fvgs(df, lookback)
    if side == "LONG":
        for z in reversed(fvgs):
            if z["side"] == "BULLISH":
                return z
    else:
        for z in reversed(fvgs):
            if z["side"] == "BEARISH":
                return z
    return None
