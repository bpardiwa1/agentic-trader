# app/risk/guards.py
from __future__ import annotations

import os
import time
import datetime as dt
from typing import Any

from app.brokers.mt5_client import get_positions  # required

try:
    from app.brokers.mt5_client import is_symbol_trading_now  # type: ignore
except Exception:  # pragma: no cover
    def is_symbol_trading_now(symbol: str) -> dict[str, Any]:
        return {
            "tradable": True,
            "market_open": True,
            "note": "mt5_client.is_symbol_trading_now not available",
        }

try:
    from app.brokers.mt5_client import get_account_info  # type: ignore
except Exception:  # pragma: no cover
    def get_account_info() -> dict[str, Any]:
        return {}

_TRUE = {"1", "true", "yes", "on"}
_LAST_REJECT_MIN: dict[str, int] = {}

def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in _TRUE

def _env_int(name: str, default: int) -> int:
    try:
        return int(float((os.getenv(name) or str(default)).split("#", 1)[0].strip()))
    except Exception:
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).split("#", 1)[0].strip())
    except Exception:
        return default

def _now_min() -> int:
    return int(time.time() // 60)

def _cooldown_min() -> int:
    return _env_int("AGENT_COOLDOWN_MIN", 10)

def _market_check_enabled() -> bool:
    return _env_bool("AGENT_MARKET_CHECK", True)

def _block_same_side_enabled() -> bool:
    return _env_bool("AGENT_BLOCK_SAME_SIDE", True)

def _per_symbol_cap() -> int:
    return _env_int("AGENT_MAX_PER_SYMBOL", 2)

def _global_cap() -> int:
    return _env_int("AGENT_MAX_OPEN", 6)

def _min_symbol_floating_pnl() -> float:
    return _env_float("MIN_SYMBOL_FLOATING_PNL", -9999.0)

def _equity_floor() -> float:
    return _env_float("EQUITY_FLOOR", 0.0)

def _daily_loss_limit() -> float:
    return _env_float("DAILY_LOSS_LIMIT", 0.0)

# --- Sessions parsing ---
def _parse_sessions() -> list[tuple[int,int,int,int,int,int]]:
    raw = (os.getenv("SESSIONS") or "").strip()
    if not raw: return []
    out = []
    def _dow(s):
        s = s.upper()
        map_ = {"MON":0,"TUE":1,"WED":2,"THU":3,"FRI":4,"SAT":5,"SUN":6}
        return map_.get(s, 0)
    for block in [b.strip() for b in raw.split(",") if b.strip()]:
        try:
            days, hours = block.split(None, 1)
            if "-" in days:
                a,b = days.split("-",1); ds, de = _dow(a), _dow(b)
            else:
                ds = de = _dow(days)
            t1, t2 = hours.split("-",1)
            h1,m1 = [int(x) for x in t1.split(":",1)]
            h2,m2 = [int(x) for x in t2.split(":",1)]
            out.append((ds,de,h1,m1,h2,m2))
        except Exception:
            continue
    return out

def _in_session(now: dt.datetime, sessions) -> bool:
    if not sessions: return True
    dow = now.weekday()
    for ds,de,h1,m1,h2,m2 in sessions:
        if ds <= dow <= de:
            start = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
            end   = now.replace(hour=h2, minute=m2, second=0, microsecond=0)
            if start <= now <= end:
                return True
    return False

def _clean_positions(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    if isinstance(raw, dict):
        out.append(raw)
        return out
    if not isinstance(raw, list):
        print(f"[risk_guard] unexpected positions type: {type(raw)} -> {raw}")
        return out
    for pos in raw:
        if isinstance(pos, dict):
            out.append(pos)
        else:
            print(f"[risk_guard] unexpected position entry type: {type(pos)} -> {pos}")
    return out

def _same_side(pos_side: str | None) -> str:
    s = (pos_side or "").upper()
    if s in ("BUY", "LONG"):
        return "LONG"
    if s in ("SELL", "SHORT"):
        return "SHORT"
    return ""

def risk_guard(symbol: str, side: str, sl_pips: float | None) -> dict[str, Any]:
    requested_side = (side or "").upper()
    if requested_side not in ("LONG", "SHORT"):
        return {"accepted": False, "note": "invalid side"}

    now_minute = _now_min()
    cooldown_min = _cooldown_min()
    last_reject = _LAST_REJECT_MIN.get(symbol, 0)

    if cooldown_min > 0 and (now_minute - last_reject) < cooldown_min:
        return {
            "accepted": False,
            "note": f"cooldown {symbol} ({cooldown_min}m) after last reject",
        }

    # Market / trading hours gate
    if _market_check_enabled():
        try:
            info = is_symbol_trading_now(symbol)
            tradable = bool(info.get("tradable", True))
            market_open = bool(info.get("market_open", True))
            if not (tradable and market_open):
                _LAST_REJECT_MIN[symbol] = now_minute
                return {"accepted": False, "note": f"{symbol} appears closed; skipping"}
        except Exception as exc:
            print(f"[risk_guard] market_check error: {exc}")

    # Session window (env-driven)
    sessions = _parse_sessions()
    now = dt.datetime.now()
    if not _in_session(now, sessions):
        _LAST_REJECT_MIN[symbol] = now_minute
        return {"accepted": False, "note": "outside session window"}

    # exposure caps
    per_symbol_cap = _per_symbol_cap()
    global_cap = _global_cap()
    block_same = _block_same_side_enabled()

    try:
        sym_positions_raw = get_positions(symbol)
        all_positions_raw = get_positions(None)
    except Exception as exc:
        _LAST_REJECT_MIN[symbol] = now_minute
        return {"accepted": False, "note": f"positions_error: {exc}"}

    sym_positions = _clean_positions(sym_positions_raw)
    all_positions = _clean_positions(all_positions_raw)

    if len(sym_positions) >= per_symbol_cap:
        _LAST_REJECT_MIN[symbol] = now_minute
        return {
            "accepted": False,
            "note": f"{symbol} per-symbol cap reached ({per_symbol_cap})",
        }

    if len(all_positions) >= global_cap:
        _LAST_REJECT_MIN[symbol] = now_minute
        return {"accepted": False, "note": f"global cap reached ({global_cap})"}

    if block_same:
        for pos in sym_positions:
            pos_side = _same_side(pos.get("side") or pos.get("type") or pos.get("type_desc"))
            if pos_side and pos_side == requested_side:
                _LAST_REJECT_MIN[symbol] = now_minute
                return {"accepted": False, "note": f"{symbol} same-side open; skipping"}

    # floating PnL floor per symbol
    min_symbol_pnl = _min_symbol_floating_pnl()
    try:
        floating = sum(float(p.get("profit", 0.0)) for p in sym_positions)
    except Exception:
        floating = 0.0
    if floating < min_symbol_pnl:
        _LAST_REJECT_MIN[symbol] = now_minute
        return {
            "accepted": False,
            "note": f"{symbol} floating PnL {floating:.2f} < {min_symbol_pnl}; guard",
        }

    # account-level guards
    account: dict[str, Any] = {}
    try:
        account = get_account_info() or {}
    except Exception as exc:
        print(f"[risk_guard] get_account_info error: {exc}")

    eq_floor = _equity_floor()
    if account and eq_floor > 0.0:
        eq_val = float(account.get("equity", account.get("Equity", 0.0)) or 0.0)
        if eq_val and eq_val < eq_floor:
            _LAST_REJECT_MIN[symbol] = now_minute
            return {"accepted": False, "note": f"equity {eq_val:.2f} < floor {eq_floor:.2f}"}

    daily_lim = _daily_loss_limit()
    if account and daily_lim > 0.0:
        pass

    return {"accepted": True, "note": "ok"}
