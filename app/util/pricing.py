# app/util/pricing.py
from __future__ import annotations

import math
from typing import Optional

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # allow importing without MT5 present (unit tests, etc.)
    mt5 = None  # type: ignore


def _symbol_info(symbol: str):
    if mt5 is None:
        return None
    try:
        return mt5.symbol_info(symbol)
    except Exception:
        return None


def tick_size(symbol: str) -> float:
    """Tick size in price units (fallback to point if trade_tick_size missing)."""
    i = _symbol_info(symbol)
    if i is None:
        # sensible default if broker info unavailable
        return 0.00001
    ts = float(getattr(i, "trade_tick_size", 0.0) or 0.0)
    if ts > 0:
        return ts
    pt = float(getattr(i, "point", 0.0) or 0.0)
    return ts if ts > 0 else (pt if pt > 0 else 0.00001)


def pip_size(symbol: str) -> float:
    """
    Define a *strategy pip* size (used for SL/TP in 'pips').

    FX 5/3 digits: 1 pip = 10 points
    FX 4/2 digits: 1 pip = 1 point
    XAU: **1 pip = $0.10** (common discretionary convention)
    """
    s = (symbol or "").upper()
    if "XAU" in s:
        return 0.10  # unify metals convention across the codebase

    i = _symbol_info(symbol)
    digits = int(getattr(i, "digits", 5) or 5) if i else 5
    pt = float(getattr(i, "point", 10.0 ** (-digits)) or (10.0 ** (-digits)))
    return (10.0 * pt) if digits in (3, 5) else pt


def price_delta_from_pips(symbol: str, pips: float) -> float:
    return float(pips) * pip_size(symbol)


def round_price_to_tick(symbol: str, price: float) -> float:
    ts = tick_size(symbol)
    if ts <= 0:
        return float(price)
    return float(round(math.floor(float(price) / ts) * ts, 10))

