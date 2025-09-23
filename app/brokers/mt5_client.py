# --- history warmup helpers ---
from __future__ import annotations
import datetime as dt

import MetaTrader5 as mt5
from typing import Any, Optional

from .. import config

_TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def _tf_to_mt5(tf: str):
    return _TF_MAP.get(tf.upper(), mt5.TIMEFRAME_M15)


def warmup_history(symbol: str, tf: str = "M15", bars: int = 500) -> dict:
    """
    Ensure MT5 has at least `bars` candles for (symbol, tf).
    Selects symbol, requests history, retries copy if needed.
    """
    if not mt5.symbol_select(symbol, True):
        return {"ok": False, "note": f"symbol_select failed for {symbol}"}

    timeframe = _tf_to_mt5(tf)
    # First attempt
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    got = 0 if rates is None else len(rates)
    if got >= min(100, bars):  # enough to start
        return {
            "ok": True,
            "symbol": symbol,
            "tf": tf,
            "bars": got,
            "note": "ok_cached",
        }

    # Ask MT5 to load roughly the needed history window
    minutes = {
        "M1": 1,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
    }.get(tf.upper(), 15)
    lookback_min = int(bars * minutes * 1.5)  # 50% buffer
    end = dt.datetime.now()
    start = end - dt.timedelta(minutes=lookback_min)
    mt5.history_select(start, end)

    # Retry a couple of times
    for _ in range(3):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        got = 0 if rates is None else len(rates)
        if got >= min(100, bars):
            return {
                "ok": True,
                "symbol": symbol,
                "tf": tf,
                "bars": got,
                "note": "ok_loaded",
            }
    return {
        "ok": False,
        "symbol": symbol,
        "tf": tf,
        "bars": got,
        "note": "insufficient_history",
    }


def _ensure_init():
    if not mt5.initialize(path=getattr(config, "MT5_PATH", None)):
        return False, mt5.last_error()
    # Best-effort login; ignore if already logged in
    login = getattr(config, "MT5_LOGIN", None)
    pwd = getattr(config, "MT5_PASSWORD", None)
    srv = getattr(config, "MT5_SERVER", None)
    if login and pwd and srv:
        try:
            mt5.login(int(login), password=pwd, server=srv)
        except Exception:
            pass
    return True, None


def _symbol_to_dict(i):
    """Safely serialize SymbolInfo."""
    if i is None:
        return None

    def g(name, default=None):
        return getattr(i, name, default)

    return {
        "name": g("name"),
        "path": g("path"),
        "visible": g("visible"),
        "select": g("select"),
        "digits": g("digits"),
        "point": g("point"),
        "trade_mode": g("trade_mode"),
        "trade_stops_level": g("trade_stops_level"),
        "volume_min": g("volume_min"),
        "volume_step": g("volume_step"),
        "volume_max": g("volume_max"),
        "trade_tick_size": g("trade_tick_size", g("point")),
        # Session-related flags often indicate if market is “openish”
        "session_deals": g("session_deals", 0),
        "session_buy_orders": g("session_buy_orders", 0),
        "session_sell_orders": g("session_sell_orders", 0),
    }


def search_symbols(query: str):
    ok, err = _ensure_init()
    if not ok:
        return {"ok": False, "error": str(err)}
    try:
        results = mt5.symbols_get(f"*{query}*") or []
        return {
            "ok": True,
            "count": len(results),
            "symbols": [_symbol_to_dict(s) for s in results],
        }
    except Exception as e:
        return {"ok": False, "error": f"symbols_get error: {e}"}


# app/brokers/mt5_client.py
import time

import MetaTrader5 as mt5


def is_symbol_trading_now(symbol: str):
    """
    Robust 'is open' check:
    - visible/select + trade_mode allows trading
    - fresh tick within N seconds
    - optional order_check probe (no volume, should not hard-fail as 'market closed')
    Returns a dict used by guards.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return {
            "ok": False,
            "symbol": symbol,
            "not_disabled": False,
            "session_active_like": False,
            "market_open_like": False,
            "info": None,
            "note": "symbol_info None",
        }

    # visible/select
    vis_ok = bool(info.visible and info.select)

    # trade_mode
    tradable_mode = info.trade_mode in (
        mt5.SYMBOL_TRADE_MODE_FULL,
        mt5.SYMBOL_TRADE_MODE_LONGONLY,
        mt5.SYMBOL_TRADE_MODE_SHORTONLY,
    )

    # fresh tick
    tick = mt5.symbol_info_tick(symbol)
    now = time.time()
    fresh_tick = bool(tick and getattr(tick, "time", 0) and (now - tick.time) < 180)

    # optional lightweight probe: order_check with zero volume
    probe_ok = True
    try:
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "type": mt5.ORDER_TYPE_BUY,
            "volume": 0.0,  # zero volume probe; broker should not accept, but we only care retcode
            "deviation": 50,
        }
        chk = mt5.order_check(req)
        # If broker strictly rejects zero-volume, ignore; but if it says "market closed", treat as closed
        comment = (getattr(chk, "comment", "") or "").lower()
        if "market closed" in comment or "trading prohibited" in comment:
            probe_ok = False
    except Exception:
        # if order_check not available or raises, ignore
        pass

    market_open_like = vis_ok and tradable_mode and (fresh_tick or probe_ok)

    return {
        "ok": True,
        "symbol": symbol,
        "not_disabled": vis_ok and tradable_mode,
        "session_active_like": market_open_like,  # keep same fields for callers
        "market_open_like": market_open_like,
        "info": {
            "name": info.name,
            "path": info.path,
            "visible": bool(info.visible),
            "select": bool(info.select),
            "digits": info.digits,
            "trade_mode": int(info.trade_mode),
            "trade_stops_level": int(info.trade_stops_level),
            "volume_min": float(info.volume_min),
            "volume_step": float(info.volume_step),
            "volume_max": float(info.volume_max),
        },
        "note": f"fresh_tick={fresh_tick} tradable_mode={tradable_mode} probe_ok={probe_ok}",
    }


def symbol_info_dict(symbol: str):
    ok, err = _ensure_init()
    if not ok:
        return {"ok": False, "error": str(err)}
    mt5.symbol_select(symbol, True)
    info = mt5.symbol_info(symbol)
    if not info:
        return {"ok": False, "error": "symbol not found"}
    return {"ok": True, "info": _symbol_to_dict(info)}


# ---------------- Backward-compatibility shims ----------------


def init_and_login():
    """Legacy alias used by main.py"""
    return _ensure_init()


def list_symbols(pattern: str = "*"):
    """Legacy: returns a list of basic symbol dicts."""
    ok, err = _ensure_init()
    if not ok:
        return {"ok": False, "error": str(err)}
    try:
        syms = mt5.symbols_get(pattern) or []
        return {
            "ok": True,
            "symbols": [
                {
                    "name": s.name,
                    "path": getattr(s, "path", ""),
                    "digits": getattr(s, "digits", None),
                    "point": getattr(s, "point", None),
                }
                for s in syms
            ],
        }
    except Exception as e:
        return {"ok": False, "error": f"symbols_get error: {e}"}


def market_symbol_info(symbol: str):
    """Legacy: minimal info used around the codebase."""
    ok, err = _ensure_init()
    if not ok:
        return {"ok": False, "error": str(err)}
    try:
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
        if not info:
            return {"ok": False, "error": "symbol not found"}
        return {
            "ok": True,
            "info": {
                "name": info.name,
                "digits": getattr(info, "digits", None),
                "point": getattr(info, "point", None),
                "trade_stops_level": getattr(info, "trade_stops_level", 0),
                "volume_min": getattr(info, "volume_min", 0.01),
                "volume_step": getattr(info, "volume_step", 0.01),
                "volume_max": getattr(info, "volume_max", None),
                "trade_tick_size": getattr(
                    info, "trade_tick_size", getattr(info, "point", None)
                ),
            },
        }
    except Exception as e:
        return {"ok": False, "error": f"symbol_info error: {e}"}


# app/brokers/mt5_client.py


def _type_desc(pos_type: int) -> str:
    # MT5: 0 = BUY, 1 = SELL
    try:
        return "BUY" if pos_type == getattr(mt5, "POSITION_TYPE_BUY", 0) else "SELL"
    except Exception:
        return "BUY" if pos_type == 0 else "SELL"

def get_positions(symbol: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Return broker positions as a list of normalized dicts with a stable schema.
    Keys we rely on elsewhere: ticket, symbol, volume, type_desc, side,
    price_open, price_current, sl, tp, profit.
    """
    try:
        raw = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    except Exception:
        raw = None

    out: list[dict[str, Any]] = []
    if not raw:
        return out

    for p in raw:
        try:
            pos = {
                "ticket": getattr(p, "ticket", None),
                "symbol": getattr(p, "symbol", None),
                "volume": float(getattr(p, "volume", 0.0) or 0.0),
                "type": getattr(p, "type", None),
                "type_desc": _type_desc(getattr(p, "type", 0)),
                "side": _type_desc(getattr(p, "type", 0)),  # alias used by other modules
                "price_open": float(getattr(p, "price_open", 0.0) or 0.0),
                "price_current": float(getattr(p, "price_current", 0.0) or 0.0),
                "sl": float(getattr(p, "sl", 0.0) or 0.0),
                "tp": float(getattr(p, "tp", 0.0) or 0.0),
                "profit": float(getattr(p, "profit", 0.0) or 0.0),
                "swap": float(getattr(p, "swap", 0.0) or 0.0),
                "commission": float(getattr(p, "commission", 0.0) or 0.0),
                "time": getattr(p, "time", None),
            }
            out.append(pos)
        except Exception:
            # Defensive: skip malformed entries
            continue

    return out

def get_account_info() -> dict:
    """Return account info (equity, balance, currency, margin, etc) as dict."""
    info = mt5.account_info()
    if info is None:
        return {}
    return info._asdict()
