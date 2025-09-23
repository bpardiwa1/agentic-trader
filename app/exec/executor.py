# app/exec/executor.py
from __future__ import annotations

import os
import time
from typing import Optional, Tuple

import MetaTrader5 as mt5

__all__ = [
    "execute_market_order",
    "place_order",                # <-- new thin wrapper alias
    "calc_sl_tp_from_pips",
    "close_all",
]

# -------- Env handling ----------
MT5_STOP_WIDEN_MULT = float(os.getenv("MT5_STOP_WIDEN_MULT", "2.0"))
MT5_ATTACH_RETRIES = int(os.getenv("MT5_ATTACH_RETRIES", "5"))
MT5_ATTACH_DELAY_SEC = float(os.getenv("MT5_ATTACH_DELAY_SEC", "0.8"))

# ----------------------------------------------------------------
# pip/price helpers
# ----------------------------------------------------------------
def _pip_size(symbol: str, info) -> float:
    """
    Decide pip size per asset:
      - XAU (Gold): pip = 0.1 (=> 300 pips = 30.0)
      - FX with 5/3 digits: pip = 10 * point (so EURUSD 1 pip = 0.0001)
      - Otherwise: pip = point
    """
    s = (symbol or "").upper()
    try:
        digits = int(getattr(info, "digits", 0) or 0)
        point = float(getattr(info, "point", 0.0) or 0.0)
    except Exception:
        digits, point = 0, 0.0

    if "XAU" in s or "GOLD" in s:
        return 0.1

    if digits in (3, 5) and point:
        return 10.0 * point

    return point or 0.0


def _round_price(value: float, digits: Optional[int]) -> float:
    if digits is None:
        return value
    return float(f"{value:.{digits}f}")


def calc_sl_tp_from_pips(
    symbol: str,
    side: str,
    entry_price: float,
    sl_pips: float | None,
    tp_pips: float | None,
) -> Tuple[float | None, float | None]:
    """
    Convert pips → absolute SL/TP in price. Returns (sl, tp) or (None, None) if missing.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        # fallback: treat "pips" like points if we cannot get symbol_info
        pip = 0.0001
        digits = 5
    else:
        pip = _pip_size(symbol, info)
        digits = int(info.digits or 5)

    side_up = (side or "").upper()
    sl = tp = None

    try:
        if sl_pips is not None:
            if side_up in ("BUY", "LONG"):
                sl = entry_price - float(sl_pips) * pip
            else:
                sl = entry_price + float(sl_pips) * pip

        if tp_pips is not None:
            if side_up in ("BUY", "LONG"):
                tp = entry_price + float(tp_pips) * pip
            else:
                tp = entry_price - float(tp_pips) * pip

        if sl is not None:
            sl = _round_price(sl, digits)
        if tp is not None:
            tp = _round_price(tp, digits)

    except Exception:
        sl = tp = None

    return sl, tp


# ----------------------------------------------------------------
# Market order execution
# ----------------------------------------------------------------
def execute_market_order(
    symbol: str,
    side: str,
    volume: float,
    price_hint: float | None = None,
    sl_pips: float | None = None,
    tp_pips: float | None = None,
    comment: str = "",
) -> dict:
    """
    Place a market order and (if provided) attach SL/TP computed from pips.
    Returns a dict describing the result.
    """
    side_up = (side or "").upper()
    if side_up not in ("BUY", "SELL", "LONG", "SHORT"):
        return {"status": "error", "error": "invalid_side"}

    if side_up == "SHORT":
        side_up = "SELL"
    if side_up == "LONG":
        side_up = "BUY"

    info = mt5.symbol_info(symbol)
    if info is None or not info.visible:
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"status": "error", "error": "symbol_not_found"}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"status": "error", "error": "no_tick"}

    entry_price = tick.ask if side_up == "BUY" else tick.bid

    sl_price, tp_price = calc_sl_tp_from_pips(
        symbol, side_up, entry_price, sl_pips, tp_pips
    )

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_BUY if side_up == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": entry_price,
        "deviation": 50,
        "comment": comment or "",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    if sl_price is not None:
        request["sl"] = sl_price
    if tp_price is not None:
        request["tp"] = tp_price

    result = mt5.order_send(request)
    if result is None:
        return {"status": "error", "error": "order_send_none"}

    # If broker rejects due to min stop distance, try widening a few times
    if result.retcode != mt5.TRADE_RETCODE_DONE and (sl_price or tp_price):
        widened = False
        for _ in range(MT5_ATTACH_RETRIES):
            time.sleep(MT5_ATTACH_DELAY_SEC)

            pos_list = mt5.positions_get(symbol=symbol)
            if not pos_list:
                break
            pos = pos_list[0]
            t2 = mt5.symbol_info_tick(symbol)
            if not t2:
                break
            current_price = t2.ask if side_up == "BUY" else t2.bid

            w_sl, w_tp = sl_price, tp_price
            if w_sl is not None:
                if side_up == "BUY":
                    w_sl = current_price - (
                        abs(entry_price - sl_price) * MT5_STOP_WIDEN_MULT
                    )
                else:
                    w_sl = current_price + (
                        abs(entry_price - sl_price) * MT5_STOP_WIDEN_MULT
                    )
                w_sl = _round_price(w_sl, info.digits)

            if w_tp is not None:
                if side_up == "BUY":
                    w_tp = current_price + (
                        abs(tp_price - entry_price) * MT5_STOP_WIDEN_MULT
                    )
                else:
                    w_tp = current_price - (
                        abs(tp_price - entry_price) * MT5_STOP_WIDEN_MULT
                    )
                w_tp = _round_price(w_tp, info.digits)

            modify = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": pos.ticket,
                "sl": w_sl if w_sl is not None else 0.0,
                "tp": w_tp if w_tp is not None else 0.0,
            }
            mres = mt5.order_send(modify)
            if mres and mres.retcode == mt5.TRADE_RETCODE_DONE:
                widened = True
                break

        if not widened:
            return {
                "status": "error",
                "retcode": result.retcode,
                "comment": getattr(result, "comment", "attach_failed"),
            }

    status = "ok" if result.retcode == mt5.TRADE_RETCODE_DONE else "partial"
    return {
        "status": status,
        "retcode": result.retcode,
        "order": getattr(result, "order", 0),
        "deal": getattr(result, "deal", 0),
        "price": entry_price,
        "sl": sl_price,
        "tp": tp_price,
    }




# --- Close utilities ---
def close_all(symbol: str | None = None, volume: float | None = None) -> dict:
    """
    Close all open positions (optionally only those matching `symbol`).
    If `volume` is provided, closes up to that amount per position; otherwise closes full size.
    """
    if symbol:
        info = mt5.symbol_info(symbol)
        if info is None or not info.visible:
            mt5.symbol_select(symbol, True)

    pos_list = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not pos_list:
        return {"closed": 0, "reports": [], "message": "no open positions"}

    closed = 0
    reports = []

    for p in pos_list:
        sym = p.symbol
        vol_to_close = float(volume or p.volume)

        # Opposite side to close
        order_type = (
            mt5.ORDER_TYPE_SELL
            if p.type == mt5.POSITION_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            reports.append(
                {
                    "symbol": sym,
                    "ticket": p.ticket,
                    "status": "error",
                    "error": "no_tick",
                }
            )
            continue

        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "position": p.ticket,
            "volume": vol_to_close,
            "type": order_type,
            "price": price,
            "deviation": 50,
            "comment": "close_all",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        ok = bool(res and res.retcode == mt5.TRADE_RETCODE_DONE)
        reports.append(
            {
                "symbol": sym,
                "ticket": p.ticket,
                "status": "ok" if ok else "error",
                "retcode": getattr(res, "retcode", None),
                "comment": getattr(res, "comment", ""),
            }
        )
        if ok:
            closed += 1

    return {"closed": closed, "reports": reports}
# -----------------------------------------------------------------------------
# NEW: Thin wrapper so other modules can import `place_order` safely
# -----------------------------------------------------------------------------

# --- Compatibility adapter for different place_order call styles ---
def place_order(*args, **kwargs) -> dict:
    """
    Supports BOTH calling styles:

    1) Dict style (new):
       place_order(symbol, sig_dict)
         - sig_dict keys: side, size, sl_pips, tp_pips, entry, note

    2) Positional style (legacy):
       place_order(symbol, side, size, sl_pips=None, tp_pips=None, entry=None, note="")
    """
    # Handle dict style: (symbol, sig_dict)
    if len(args) >= 2 and isinstance(args[1], dict):
        symbol = args[0]
        sig = args[1]
        side = sig.get("side")
        size = sig.get("size")
        sl_pips = sig.get("sl_pips")
        tp_pips = sig.get("tp_pips")
        entry = sig.get("entry")
        note = sig.get("note", "auto")
        if size is None:
            return {"status": "error", "error": "size_missing_in_signal"}
        return execute_market_order(
            symbol=symbol,
            side=side,
            volume=size,
            price_hint=entry,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            comment=note,
        )

    # Handle positional legacy style:
    # (symbol, side, size, sl_pips=None, tp_pips=None, entry=None, note="")
    # Also support keyword overrides via kwargs.
    if len(args) >= 3:
        symbol = args[0]
        side = args[1]
        size = args[2]
        sl_pips = args[3] if len(args) > 3 else None
        tp_pips = args[4] if len(args) > 4 else None
        entry = args[5] if len(args) > 5 else None
        note = args[6] if len(args) > 6 else ""

        # Allow kwargs to override
        side = kwargs.get("side", side)
        size = kwargs.get("size", size)
        sl_pips = kwargs.get("sl_pips", sl_pips)
        tp_pips = kwargs.get("tp_pips", tp_pips)
        entry = kwargs.get("entry", entry)
        note = kwargs.get("note", note)

        if size is None:
            return {"status": "error", "error": "size_missing"}

        return execute_market_order(
            symbol=symbol,
            side=side,
            volume=size,
            price_hint=entry,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            comment=note,
        )

    # If we get here, the invocation was invalid
    return {"status": "error", "error": "invalid_place_order_signature"}