# app/brokers/mt5_client.py
from __future__ import annotations

import logging
import os
import time
from typing import Any

import MetaTrader5 as mt5  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
TRADE_CONTEXT_BUSY = 10016
INVALID_STOPS = 10004
TRADE_RETCODE_DONE = 10009

DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes", "on")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return default


def _get_side(request: dict[str, Any]) -> str:
    """
    Normalize trade direction:
    - LONG / BUY → BUY
    - SHORT / SELL → SELL
    """
    s = str(request.get("side") or request.get("type") or "BUY").upper()
    if "SELL" in s or "SHORT" in s:
        return "SELL"
    return "BUY"


def _comment_is_invalid_stops(comment: str | None) -> bool:
    if not comment:
        return False
    c = comment.lower()
    return "invalid stops" in c or "invalid sl" in c or "invalid tp" in c


# ---------------------------------------------------------------------
# Symbol utilities
# ---------------------------------------------------------------------
def _adjust_volume(symbol: str, vol: float) -> float:
    info = getattr(mt5, "symbol_info", lambda _: None)(symbol)
    if not info:
        return round(vol, 2)
    vmin = float(getattr(info, "volume_min", 0.01))
    vmax = float(getattr(info, "volume_max", 100.0))
    step = float(getattr(info, "volume_step", 0.01))
    vol = max(vmin, min(vol, vmax))
    steps = round(vol / step)
    return round(steps * step, 2)


def _ensure_market_price(symbol: str, side: str, current: float | None) -> float:
    tick = getattr(mt5, "symbol_info_tick", lambda _: None)(symbol)
    if not tick:
        return float(current or 0.0)
    return float(tick.ask if side == "BUY" else tick.bid)


def _compute_sl_tp(
    symbol: str, side: str, price: float, sl_pips: float, tp_pips: float
) -> tuple[float, float]:
    pip_mode = os.getenv("INDICES_PIP_MODE", "mt5_point").lower()
    is_index = any(x in symbol.upper() for x in ("NAS100", "US30", "GER40", "SPX500"))
    info = getattr(mt5, "symbol_info", lambda _: None)(symbol)
    point = float(getattr(info, "point", 0.01)) if info else 0.01
    mult = 1.0 if (pip_mode == "index_point" and is_index) else point

    if side == "BUY":
        sl, tp = price - sl_pips * mult, price + tp_pips * mult
    else:
        sl, tp = price + sl_pips * mult, price - tp_pips * mult

    logger.info(
        "[compute_sl_tp] %s %s mode=%s mult=%.5f -> SL=%.5f TP=%.5f",
        symbol,
        side,
        "index_point" if (is_index and pip_mode == "index_point") else "mt5_point",
        mult,
        sl,
        tp,
    )
    return sl, tp


def _ensure_min_stops(
    symbol: str, side: str, price: float, sl: float, tp: float
) -> tuple[float, float]:
    info = getattr(mt5, "symbol_info", lambda _: None)(symbol)
    if not info:
        return sl, tp
    min_stop = int(getattr(info, "trade_stops_level", 0))
    if min_stop <= 0:
        min_stop = _env_int("MT5_MIN_STOP_POINTS", 300)
    pt = float(getattr(info, "point", 0.01))
    dist = float(min_stop) * pt

    if side == "BUY":
        if price - sl < dist:
            sl = price - dist
        if tp - price < dist:
            tp = price + dist
    else:
        if sl - price < dist:
            sl = price + dist
        if price - tp < dist:
            tp = price - dist
    return sl, tp


def _dump_symbol_info(symbol: str) -> None:
    info = getattr(mt5, "symbol_info", lambda _: None)(symbol)
    if not info:
        logger.info("[symbol_info] %s -> <none>", symbol)
        return
    logger.info(
        "[symbol_info] %s point=%.5f stops_level=%s freeze_level=%s digits=%s exec_mode=%s",
        symbol,
        float(getattr(info, "point", 0.0)),
        getattr(info, "trade_stops_level", None),
        getattr(info, "freeze_level", None),
        getattr(info, "digits", None),
        getattr(info, "trade_exemode", None),
    )


# ---------------------------------------------------------------------
# SL/TP attach helper
# ---------------------------------------------------------------------
def _attach_sltp(
    symbol: str, ticket: int, sl: float, tp: float, retries: int, delay: float
) -> dict:
    action_sltp = getattr(mt5, "TRADE_ACTION_SLTP", 0x67)
    modify_req = {
        "action": action_sltp,
        "symbol": symbol,
        "position": int(ticket),
        "sl": float(sl),
        "tp": float(tp),
        "comment": "attach_sltp",
    }

    for attempt in range(1, retries + 1):
        try:
            res = getattr(mt5, "order_send", lambda _: None)(modify_req)
        except Exception as e:
            logger.error("[SLTP] order_send exception (%s/%s): %s", attempt, retries, e)
            time.sleep(delay)
            continue

        if not res:
            logger.error("[SLTP] No response (attempt %s/%s)", attempt, retries)
            time.sleep(delay)
            continue

        r = res._asdict()
        rc, cm = r.get("retcode"), r.get("comment")

        if rc == TRADE_RETCODE_DONE:
            logger.info("[SLTP] Attached OK: ticket=%s sl=%.2f tp=%.2f", ticket, sl, tp)
            return {"ok": True, "result": r}

        if rc == TRADE_CONTEXT_BUSY:
            logger.warning("[SLTP] busy (attempt %s/%s)", attempt, retries)
            time.sleep(delay)
            continue

        if rc == INVALID_STOPS or _comment_is_invalid_stops(cm):
            logger.warning("[SLTP] Invalid stops on modify: %s — stop retries", cm)
            return {"ok": False, "result": r}

        logger.error(
            "[SLTP] Modify rejected: rc=%s cm=%s (attempt %s/%s)", rc, cm, attempt, retries
        )
        time.sleep(delay)

    return {"ok": False, "error": "attach_sltp_failed"}


# ---------------------------------------------------------------------
# Main order path
# ---------------------------------------------------------------------
def place_order(request: dict[str, Any]) -> dict:
    symbol = request.get("symbol")
    if not symbol:
        return {"ok": False, "error": "missing_symbol"}

    # Resolve side
    side = _get_side(request)
    logger.info("[SIDE_RESOLVE] %s -> %s", symbol, side)

    # Determine lot size dynamically from environment
    sym_up = symbol.replace("-", "_").replace(".", "_").upper()
    env_key = f"LOTS_{sym_up}"
    vol = float(os.getenv(env_key, os.getenv("MT5_DEFAULT_LOTS", "0.01")))
    request["volume"] = _adjust_volume(symbol, vol)
    logger.info("[VOLUME] %s volume=%.2f (env key=%s)", symbol, request["volume"], env_key)

    if DRY_RUN:
        logger.info("[DRY_RUN] %s skipping order send", symbol)
        return {"ok": True, "comment": "dry_run"}
    if TEST_MODE:
        return {"ok": True, "comment": "simulated", "ticket": 999999}

    retries = _env_int("MT5_ATTACH_RETRIES", 5)
    delay = _env_float("MT5_ATTACH_DELAY_SEC", 0.8)
    widen_mult = _env_float("MT5_STOP_WIDEN_MULT", 2.0)
    deviation = _env_int("MT5_DEVIATION", 80)
    request["deviation"] = deviation

    price = _ensure_market_price(symbol, side, request.get("price"))
    request["price"] = price
    sl_pips = float(request.get("sl_pips", 100.0))
    tp_pips = float(request.get("tp_pips", 200.0))
    sl, tp = _compute_sl_tp(symbol, side, price, sl_pips, tp_pips)
    sl, tp = _ensure_min_stops(symbol, side, price, sl, tp)

    info = getattr(mt5, "symbol_info", lambda _: None)(symbol)
    _dump_symbol_info(symbol)
    if not info:
        return {"ok": False, "error": "no_symbol_info"}

    # Fill mode detection
    fill_mode_value = getattr(info, "fill_mode", None)
    if fill_mode_value is None:
        fill_mode = getattr(mt5, "ORDER_FILLING_IOC", 1)
        logger.info("[FILL_MODE] %s fill_mode=<not available> -> using IOC", symbol)
    else:
        if fill_mode_value == 1:
            fill_mode = getattr(mt5, "ORDER_FILLING_FOK", 0)
        elif fill_mode_value == 2:
            fill_mode = getattr(mt5, "ORDER_FILLING_IOC", 1)
        elif fill_mode_value == 3:
            fill_mode = getattr(mt5, "ORDER_FILLING_RETURN", 2)
        else:
            fill_mode = getattr(mt5, "ORDER_FILLING_IOC", 1)
        logger.info("[FILL_MODE] %s fill_mode=%s", symbol, fill_mode_value)

    # Market execution fallback
    if getattr(info, "trade_exemode", 0) == 2:
        logger.info("[MARKET_EXEC] %s exec_mode=2 -> placing naked then attach SL/TP", symbol)

    # Build base trade request
    trade_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": request["volume"],
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": deviation,
        "magic": 123456,
        "comment": "AgenticTrader auto order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": fill_mode,
        "sl": sl,
        "tp": tp,
    }

    last_result: Any = None

    # Attempt order with SL/TP
    for attempt in range(1, retries + 1):
        try:
            res = getattr(mt5, "order_send", lambda _: None)(trade_req)
        except Exception as e:
            logger.error("order_send exception (%s/%s): %s", attempt, retries, e)
            time.sleep(delay)
            continue

        if not res:
            logger.error("No response (attempt %s/%s)", attempt, retries)
            time.sleep(delay)
            continue

        r = res._asdict()
        rc, cm = r.get("retcode"), r.get("comment")

        if rc == TRADE_RETCODE_DONE:
            logger.info("Order executed with SL/TP: %s", r.get("order"))
            return {"ok": True, "retcode": rc, "comment": cm, "result": r}

        if rc == TRADE_CONTEXT_BUSY:
            logger.warning("Busy retcode 10016 attempt %s/%s", attempt, retries)
            time.sleep(delay)
            continue

        if rc == INVALID_STOPS or _comment_is_invalid_stops(cm):
            logger.warning("Invalid stops rc=%s cm=%s — widening", rc, cm)
            sl_pips *= widen_mult
            tp_pips *= widen_mult
            sl, tp = _compute_sl_tp(symbol, side, price, sl_pips, tp_pips)
            sl, tp = _ensure_min_stops(symbol, side, price, sl, tp)
            trade_req["sl"], trade_req["tp"] = sl, tp
            time.sleep(delay)
            continue

        logger.error("Order rejected: rc=%s cm=%s (attempt %s/%s)", rc, cm, attempt, retries)
        last_result = r
        time.sleep(delay)

    # Fallback naked order + attach SL/TP
    logger.warning("[FALLBACK] placing %s naked then attach SL/TP", symbol)
    naked_req = dict(trade_req)
    naked_req.pop("sl", None)
    naked_req.pop("tp", None)

    order_ticket: int | None = None
    for attempt in range(1, retries + 1):
        try:
            res = getattr(mt5, "order_send", lambda _: None)(naked_req)
        except Exception as e:
            logger.error("[NAKED] exception (%s/%s): %s", attempt, retries, e)
            time.sleep(delay)
            continue

        if not res:
            logger.error("[NAKED] no response (attempt %s/%s)", attempt, retries)
            time.sleep(delay)
            continue

        r = res._asdict()
        rc, cm = r.get("retcode"), r.get("comment")

        if rc == TRADE_RETCODE_DONE:
            order_ticket = int(r.get("order") or 0)
            logger.info("Order executed WITHOUT SL/TP: ticket=%s", order_ticket)
            break

        logger.error("[NAKED] rejected rc=%s cm=%s (attempt %s/%s)", rc, cm, attempt, retries)
        time.sleep(delay)

    if not order_ticket:
        logger.warning("[%s] order failed: %s", symbol, last_result)
        return {"ok": False, "result": last_result or {"error": "failed_naked_order"}}

    attach = _attach_sltp(symbol, order_ticket, float(sl), float(tp), retries=retries, delay=delay)
    if not attach.get("ok"):
        return {
            "ok": True,
            "ticket": order_ticket,
            "warning": "sltp_attach_failed",
            "attach": attach,
        }

    return {
        "ok": True,
        "ticket": order_ticket,
        "retcode": TRADE_RETCODE_DONE,
        "comment": "attached_sltp",
    }
