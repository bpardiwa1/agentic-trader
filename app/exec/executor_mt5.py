# app/exec/executor_mt5.py
from __future__ import annotations

import os
from typing import Any, cast

import MetaTrader5 as _mt5

# Type-hint MT5 as Any so Pylance allows dynamic attrs (order_send, symbol_info_tick, etc.)
mt5: Any = cast(Any, _mt5)

# Tunables / "magic numbers" expressed as constants
MAX_SYMBOL_SELECT_TRIES = 5
DEFAULT_DEVIATION = 50
DEFAULT_FILLING = 1  # ORDER_FILLING_IOC
ACTION_DEAL = 1  # TRADE_ACTION_DEAL
ORDER_BUY = 0  # ORDER_TYPE_BUY
ORDER_SELL = 1  # ORDER_TYPE_SELL
RETCODE_DONE = 10009  # TRADE_RETCODE_DONE

MIN_DIGITS_FOR_FIVE_DIGIT_FX = 5  # Used for pip size guess
MIN_DIGITS_FOR_THREE_DIGIT_FX = 3  # Used for pip size guess


def _env_float(name: str, default: float) -> float:
    try:
        raw = (os.getenv(name) or str(default)).split("#", 1)[0].strip()
        return float(raw)
    except Exception:
        return default


def _ensure_symbol_visible(symbol: str) -> bool:
    """Make sure the symbol is selected/visible before trading."""
    info = mt5.symbol_info(symbol)
    if info and getattr(info, "visible", True):
        return True

    return any(mt5.symbol_select(symbol, True) for _ in range(MAX_SYMBOL_SELECT_TRIES))


def _pip_size_guess(symbol: str) -> float:
    """
    Best-effort pip size (price units per pip).
    - XAUUSD ~ $0.10 per pip (most brokers quote to 0.01)
    - XXXJPY ~ 0.01
    - 5-digit FX ~ 0.00010
    Fallback: 10 * point if digits >= 3, else point.
    """
    s = symbol.upper()
    if "XAU" in s:
        return 0.10
    if s.endswith("JPY") or "JPY" in s:
        return 0.01

    info = mt5.symbol_info(symbol)
    try:
        point = float(getattr(info, "point", 0.0)) if info else 0.0
        digits = int(getattr(info, "digits", 0)) if info else 0
    except Exception:
        point = 0.0
        digits = 0

    if digits >= MIN_DIGITS_FOR_FIVE_DIGIT_FX:
        # 5-digit FX (e.g., EURUSD to 1e-5): 1 pip = 0.00010
        return 10.0 * point or 0.00010
    if digits >= MIN_DIGITS_FOR_THREE_DIGIT_FX:
        # 3-digit (JPY-style): 1 pip = 0.01
        return 10.0 * point or 0.010
    # Conservative fallback if broker metadata missing
    return point or 0.00010


def compute_sl_tp_prices(
    symbol: str,
    entry: float,
    sl_pips: float | None,
    tp_pips: float | None,
    side: str,
) -> tuple[float | None, float | None]:
    """
    Convert SL/TP (in pips) to absolute prices based on entry and side.
    Returns (sl_price, tp_price).
    """
    pip = _pip_size_guess(symbol)
    is_long = (side or "").upper() == "LONG"

    sl_price: float | None = None
    tp_price: float | None = None

    if sl_pips and sl_pips > 0:
        sl_delta = sl_pips * pip
        sl_price = entry - sl_delta if is_long else entry + sl_delta

    if tp_pips and tp_pips > 0:
        tp_delta = tp_pips * pip
        tp_price = entry + tp_delta if is_long else entry - tp_delta

    return sl_price, tp_price


def _price_for_side(symbol: str, side: str) -> float | None:
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return None
    return float(tick.ask) if (side or "").upper() == "LONG" else float(tick.bid)


def _side_to_order_type(side: str) -> int:
    return ORDER_BUY if (side or "").upper() == "LONG" else ORDER_SELL


def place_market_order(
    symbol: str,
    side: str,
    lots: float,
    sl_pips: float | None = None,
    tp_pips: float | None = None,
    comment: str = "",
    entry_override: float | None = None,
) -> dict[str, Any]:
    """
    Place a market order with optional SL/TP in pips.
    Returns an execution report-like dict (retcode, status, etc.).
    """
    # 1) Ensure tradable symbol
    if not _ensure_symbol_visible(symbol):
        return {
            "status": "error",
            "reason": "symbol_not_visible",
            "symbol": symbol,
        }

    # 2) Determine entry price
    price = float(entry_override) if entry_override else _price_for_side(symbol, side)
    if price is None:
        return {
            "status": "error",
            "reason": "no_tick",
            "symbol": symbol,
        }

    # 3) Compute SL/TP absolute prices
    sl_price, tp_price = compute_sl_tp_prices(symbol, price, sl_pips, tp_pips, side)

    # 4) Build and send request
    order_type = _side_to_order_type(side)
    req = {
        "action": ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": float(price),
        "deviation": int(_env_float("MT5_DEVIATION", DEFAULT_DEVIATION)),
        "comment": comment or "",
        "type_filling": DEFAULT_FILLING,
    }
    if sl_price:
        req["sl"] = float(sl_price)
    if tp_price:
        req["tp"] = float(tp_price)

    res = mt5.order_send(req)

    # 5) Normalize response
    retcode = int(getattr(res, "retcode", 0)) if res else 0
    ok = bool(res and retcode == RETCODE_DONE)

    result: dict[str, Any] = {
        "status": "ok" if ok else "error",
        "retcode": retcode,
        "symbol": symbol,
        "requested": {
            "side": side,
            "lots": float(lots),
            "price": float(price),
            "sl_pips": float(sl_pips or 0.0),
            "tp_pips": float(tp_pips or 0.0),
            "sl": sl_price,
            "tp": tp_price,
            "comment": comment or "",
        },
        "raw": {
            "order": int(getattr(res, "order", 0)) if res else None,
            "deal": int(getattr(res, "deal", 0)) if res else None,
            "comment": getattr(res, "comment", "") if res else "",
        },
    }
    return result
