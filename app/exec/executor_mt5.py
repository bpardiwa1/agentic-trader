# app/exec/executor_mt5.py
from __future__ import annotations

import math
from typing import Any, Optional

import MetaTrader5 as mt5


# ---------- symbol helpers ----------------------------------------------------

def _syminfo(symbol: str):
    return mt5.symbol_info(symbol)

def _digits(symbol: str) -> int:
    si = _syminfo(symbol)
    return int(si.digits) if si else 5

def _point(symbol: str) -> float:
    si = _syminfo(symbol)
    return float(si.point) if si else 0.00001

def _tick_size(symbol: str) -> float:
    # smallest price increment
    si = _syminfo(symbol)
    ts = getattr(si, "trade_tick_size", None)
    if ts is None or ts <= 0:
        # fall back to "point"
        ts = _point(symbol)
    return float(ts) if ts else 0.00001

def _stop_level_points(symbol: str) -> float:
    # broker min distance from current price to SL/TP, in POINTS
    si = _syminfo(symbol)
    return float(getattr(si, "trade_stops_level", 0.0))  # already in "points"
    # Note: if zero, broker doesn’t impose a min distance

def _pip_size(symbol: str) -> float:
    """
    Our *strategy pips* -> price mapping.
    - Most FX pairs with 5 digits -> 0.0001 per pip
    - XAUUSD -> 0.1 per pip
    - Fallback: 10 * point
    """
    s = (symbol or "").upper()
    if "XAU" in s:
        return 0.1
    # Generic FX
    if _digits(symbol) >= 5:
        return 0.0001
    # Fallback: 10 * point (e.g. 3 digits)
    return _point(symbol) * 10.0


def _price_from_pips(symbol: str, entry: float, pips: float, side: str, is_sl: bool) -> float:
    """
    Convert pips to absolute price from the entry.
    - For LONG:  SL below, TP above
    - For SHORT: SL above, TP below
    """
    pip = _pip_size(symbol)
    delta = pip * float(pips)
    if side == "LONG":
        return entry - delta if is_sl else entry + delta
    else:  # SHORT
        return entry + delta if is_sl else entry - delta


def _round_to_tick(symbol: str, price: float) -> float:
    ts = _tick_size(symbol)
    if ts <= 0:
        return price
    # round to nearest trade tick
    return round(price / ts) * ts


def _ensure_min_stop_distance(symbol: str, side: str, entry: float, sl: float, tp: float) -> tuple[float, float]:
    """
    Make sure SL/TP respect broker 'trade_stops_level' in *points*.
    Convert points -> price distance using 'point'.
    """
    stop_level_pts = _stop_level_points(symbol)
    if stop_level_pts <= 0:
        return sl, tp  # no min distance

    pt = _point(symbol)
    min_dist_price = stop_level_pts * pt  # price distance

    if side == "LONG":
        # SL below entry, TP above entry
        if (entry - sl) < min_dist_price:
            sl = entry - min_dist_price
        if (tp - entry) < min_dist_price:
            tp = entry + min_dist_price
    else:
        # SHORT
        if (sl - entry) < min_dist_price:
            sl = entry + min_dist_price
        if (entry - tp) < min_dist_price:
            tp = entry - min_dist_price

    # Round to tick
    sl = _round_to_tick(symbol, sl)
    tp = _round_to_tick(symbol, tp)
    return sl, tp


# ---------- public API --------------------------------------------------------

def compute_sl_tp_prices(
    symbol: str,
    side: str,
    entry: float,
    sl_pips: float,
    tp_pips: float,
) -> dict[str, float]:
    """
    Convert *pips* to *prices*, round to tick, enforce min stop distance.
    """
    side = side.upper()
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"invalid side: {side}")

    raw_sl = _price_from_pips(symbol, entry, sl_pips, side, is_sl=True)
    raw_tp = _price_from_pips(symbol, entry, tp_pips, side, is_sl=False)

    sl = _round_to_tick(symbol, raw_sl)
    tp = _round_to_tick(symbol, raw_tp)

    sl, tp = _ensure_min_stop_distance(symbol, side, entry, sl, tp)

    return {
        "entry": float(entry),
        "sl": float(sl),
        "tp": float(tp),
        "pip_size": _pip_size(symbol),
        "tick_size": _tick_size(symbol),
        "stop_level_points": _stop_level_points(symbol),
        "point": _point(symbol),
    }


def place_market_order(
    symbol: str,
    side: str,
    lots: float,
    sl_pips: float,
    tp_pips: float,
    comment: str = "",
    *,
    entry_override: Optional[float] = None,
) -> dict[str, Any]:
    """
    Place a market order and set SL/TP using pips -> price conversion.
    If entry_override is None, we use best available (ask for LONG, bid for SHORT).
    """
    # Pull current ticks
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"status": "error", "error": "no_tick"}

    # Decide entry
    side = side.upper()
    if side == "LONG":
        entry = float(tick.ask)
        order_type = mt5.ORDER_TYPE_BUY
    elif side == "SHORT":
        entry = float(tick.bid)
        order_type = mt5.ORDER_TYPE_SELL
    else:
        return {"status": "error", "error": f"invalid side: {side}"}

    if entry_override is not None:
        entry = float(entry_override)

    # Compute SL/TP prices
    st = compute_sl_tp_prices(symbol, side, entry, sl_pips, tp_pips)

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": entry,
        "sl": st["sl"],
        "tp": st["tp"],
        "deviation": 10,
        "magic": 0,
        "comment": comment or "auto",
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    res = mt5.order_send(req)
    if res is None:
        return {"status": "error", "error": "order_send_none", "debug": {"req": req, "st": st}}

    ok = res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
    return {
        "status": "ok" if ok else "error",
        "retcode": int(res.retcode),
        "order": int(getattr(res, "order", 0) or 0),
        "deal": int(getattr(res, "deal", 0) or 0),
        "price": float(getattr(res, "price", entry) or entry),
        "sl": float(st["sl"]),
        "tp": float(st["tp"]),
        "debug": {
            "entry": entry,
            "pip_size": st["pip_size"],
            "tick_size": st["tick_size"],
            "stop_level_points": st["stop_level_points"],
            "point": st["point"],
            "req": req,
        },
    }
