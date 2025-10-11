# app/exec/executor_mt5.py
from __future__ import annotations
import os, math
from typing import Any, Optional
import MetaTrader5 as mt5

def _syminfo(symbol: str): return mt5.symbol_info(symbol)
def _digits(symbol: str) -> int: si = _syminfo(symbol); return int(si.digits) if si else 5
def _point(symbol: str) -> float: si = _syminfo(symbol); return float(si.point) if si else 0.00001
def _tick_size(symbol: str) -> float:
    si = _syminfo(symbol); ts = getattr(si, "trade_tick_size", None)
    if ts is None or ts <= 0: ts = _point(symbol)
    return float(ts) if ts else 0.00001
def _stop_level_points(symbol: str) -> float:
    si = _syminfo(symbol); return float(getattr(si, "trade_stops_level", 0.0))

def _pip_size(symbol: str) -> float:
    s = (symbol or "").upper()
    if "XAU" in s: return 0.1            # $0.10 per pip
    if _digits(symbol) >= 5: return 0.0001
    return _point(symbol) * 10.0

def _price_from_pips(symbol: str, entry: float, pips: float, side: str, is_sl: bool) -> float:
    pip = _pip_size(symbol); delta = pip * float(pips)
    if side == "LONG":  return entry - delta if is_sl else entry + delta
    else:               return entry + delta if is_sl else entry - delta

def _round_to_tick(symbol: str, price: float) -> float:
    ts = _tick_size(symbol)
    if ts <= 0: return price
    return round(price / ts) * ts

def _env_min_abs_stop(symbol: str) -> float:
    s = (symbol or "").upper()
    if "XAU" in s:
        return float(os.getenv("SLTP_MIN_ABS_XAUUSD", "0") or 0)
    return 0.0

def _ensure_min_stop_distance(symbol: str, side: str, entry: float, sl: float, tp: float) -> tuple[float, float]:
    # 1) Broker 'trade_stops_level' in points
    stop_level_pts = _stop_level_points(symbol)
    if stop_level_pts > 0:
        pt = _point(symbol); min_dist_price = stop_level_pts * pt
        if side == "LONG":
            if (entry - sl) < min_dist_price: sl = entry - min_dist_price
            if (tp - entry) < min_dist_price: tp = entry + min_dist_price
        else:
            if (sl - entry) < min_dist_price: sl = entry + min_dist_price
            if (entry - tp) < min_dist_price: tp = entry - min_dist_price

    # 2) ENV absolute minimum distance (price units)
    min_abs = _env_min_abs_stop(symbol)
    if min_abs > 0:
        if side == "LONG":
            if (entry - sl) < min_abs: sl = entry - min_abs
            if (tp - entry) < min_abs: tp = entry + min_abs
        else:
            if (sl - entry) < min_abs: sl = entry + min_abs
            if (entry - tp) < min_abs: tp = entry - min_abs

    # Round to tick
    sl = _round_to_tick(symbol, sl)
    tp = _round_to_tick(symbol, tp)
    return sl, tp

def compute_sl_tp_prices(symbol: str, side: str, entry: float, sl_pips: float, tp_pips: float) -> dict[str, float]:
    side = side.upper()
    if side not in ("LONG", "SHORT"): raise ValueError(f"invalid side: {side}")
    raw_sl = _price_from_pips(symbol, entry, sl_pips, side, is_sl=True)
    raw_tp = _price_from_pips(symbol, entry, tp_pips, side, is_sl=False)
    sl = _round_to_tick(symbol, raw_sl); tp = _round_to_tick(symbol, raw_tp)
    sl, tp = _ensure_min_stop_distance(symbol, side, entry, sl, tp)
    return {"entry": float(entry), "sl": float(sl), "tp": float(tp),
            "pip_size": _pip_size(symbol), "tick_size": _tick_size(symbol),
            "stop_level_points": _stop_level_points(symbol), "point": _point(symbol)}

def place_market_order(symbol: str, side: str, lots: float, sl_pips: float, tp_pips: float, comment: str = "", *, entry_override: Optional[float] = None) -> dict[str, Any]:
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return {"status": "error", "error": "no_tick"}
    side = side.upper()
    if side == "LONG": entry = float(tick.ask); order_type = mt5.ORDER_TYPE_BUY
    elif side == "SHORT": entry = float(tick.bid); order_type = mt5.ORDER_TYPE_SELL
    else: return {"status": "error", "error": f"invalid side: {side}"}
    if entry_override is not None: entry = float(entry_override)
    st = compute_sl_tp_prices(symbol, side, entry, sl_pips, tp_pips)
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(lots), "type": order_type,
           "price": entry, "sl": st["sl"], "tp": st["tp"], "deviation": 10, "magic": 0,
           "comment": comment or "auto", "type_filling": mt5.ORDER_FILLING_FOK}
    res = mt5.order_send(req)
    if res is None: return {"status": "error", "error": "order_send_none", "debug": {"req": req, "st": st}}
    ok = res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
    return {"status": "ok" if ok else "error", "retcode": int(res.retcode),
            "order": int(getattr(res, "order", 0) or 0), "deal": int(getattr(res, "deal", 0) or 0),
            "price": float(getattr(res, "price", entry) or entry),
            "sl": float(st["sl"]), "tp": float(st["tp"]),
            "debug": {"entry": entry, "pip_size": st["pip_size"], "tick_size": st["tick_size"],
                      "stop_level_points": st["stop_level_points"], "point": st["point"], "req": req}}
