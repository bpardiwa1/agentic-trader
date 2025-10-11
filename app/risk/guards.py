# app/risk/guards.py
from __future__ import annotations

import datetime as dt
import os
from typing import Any, cast

import MetaTrader5 as _mt5

# Treat MT5 as dynamic for type-checking (silences Pylance attr warnings)
mt5: Any = cast(Any, _mt5)

# ---------------- Env helpers ----------------
_TRUE = {"1", "true", "yes", "on"}


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


def _normalize_key(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in (s or "").upper())


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ---------------- Data access helpers ----------------
def _positions(symbol: str | None = None) -> list[Any]:
    return list(mt5.positions_get(symbol=symbol)) if symbol else list(mt5.positions_get())


def _account_equity() -> float:
    acc = mt5.account_info()
    if not acc:
        return 0.0
    eq = float(getattr(acc, "equity", 0.0))
    if eq > 0:
        return eq
    return float(getattr(acc, "balance", 0.0))


def _daily_pnl() -> float:
    acc = mt5.account_info()
    realized = float(getattr(acc, "profit", 0.0)) if acc else 0.0

    flt = 0.0
    for p in _positions():
        flt += float(getattr(p, "profit", 0.0))

    return realized + flt


def _floating_symbol_pnl(symbol: str) -> float:
    total = 0.0
    for p in _positions(symbol):
        total += float(getattr(p, "profit", 0.0))
    return total


def _market_is_open(symbol: str) -> bool:
    info = mt5.symbol_info(symbol)
    if not info:
        return False
    if not getattr(info, "visible", True):
        mt5.symbol_select(symbol, True)

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False

    last = getattr(tick, "time_msc", None) or getattr(tick, "time", None)
    if not last:
        return True
    try:
        ts = float(last) / (1000.0 if last > 10**12 else 1.0)
        age = _now_utc() - dt.datetime.fromtimestamp(ts, tz=dt.UTC)
        return age <= dt.timedelta(minutes=5)
    except Exception:
        return True


# ---------------- Cooldown bookkeeping ----------------
_last_trade_at: dict[str, dt.datetime] = {}


def note_trade(symbol: str) -> None:
    _last_trade_at[_normalize_key(symbol)] = _now_utc()


def _cooldown_remaining(symbol: str, cooldown_min: int) -> float:
    if cooldown_min <= 0:
        return 0.0
    key = _normalize_key(symbol)
    last = _last_trade_at.get(key)
    if not last:
        return 0.0
    passed = (_now_utc() - last).total_seconds() / 60.0
    remain = float(cooldown_min) - passed
    return remain if remain > 0.0 else 0.0


# ---------------- Guard checks ----------------
def _cap_current_open() -> tuple[int, int]:
    max_all = _env_int("MAX_OPEN_POSITIONS", _env_int("AGENT_MAX_OPEN", 0))
    cur_all = len(_positions())
    return cur_all, max_all


def _cap_symbol_open(symbol: str) -> tuple[int, int]:
    max_sym = _env_int("MAX_TRADES_PER_SYMBOL", _env_int("AGENT_MAX_PER_SYMBOL", 0))
    cur_sym = len(_positions(symbol))
    return cur_sym, max_sym


def _same_side_block(symbol: str, side: str) -> bool:
    if not _env_bool("AGENT_BLOCK_SAME_SIDE", False):
        return False
    want_buy = (side or "").upper() == "LONG"
    for p in _positions(symbol):
        is_buy = int(getattr(p, "type", 0)) == getattr(mt5, "POSITION_TYPE_BUY", 0)
        if is_buy == want_buy:
            return True
    return False


def _exposure_side_count(symbol: str, side: str) -> int:
    want_buy = (side or "").upper() == "LONG"
    n = 0
    for p in _positions(symbol):
        is_buy = int(getattr(p, "type", 0)) == getattr(mt5, "POSITION_TYPE_BUY", 0)
        if is_buy == want_buy:
            n += 1
    return n


def _exposure_side_cap(symbol: str, side: str) -> tuple[int, int]:
    key = f"MAX_PER_SIDE_{_normalize_key(symbol)}"
    sym_cap = _env_int(key, 0)
    if sym_cap > 0:
        return _exposure_side_count(symbol, side), sym_cap
    return _exposure_side_count(symbol, side), _env_int("AGENT_MAX_PER_SIDE", 0)


# ---------------- Public API ----------------
def check_pretrade_guards(symbol: str, side: str) -> dict[str, Any]:
    reasons: list[str] = []
    caps: dict[str, Any] = {}

    if _env_bool("AGENT_MARKET_CHECK", True) and not _market_is_open(symbol):
        reasons.append("market_closed_or_stale")

    cd_min = _env_int("AGENT_COOLDOWN_MIN", 0)
    cd_left = _cooldown_remaining(symbol, cd_min)
    caps["cooldown_min"] = cd_min
    caps["cooldown_left_min"] = round(cd_left, 2)
    if cd_left > 0.0:
        reasons.append("cooldown_active")

    cur_all, max_all = _cap_current_open()
    cur_sym, max_sym = _cap_symbol_open(symbol)
    caps["open_all"] = cur_all
    caps["cap_all"] = max_all
    caps["open_symbol"] = cur_sym
    caps["cap_symbol"] = max_sym

    if max_all > 0 and cur_all >= max_all:
        reasons.append("max_open_reached")
    if max_sym > 0 and cur_sym >= max_sym:
        reasons.append("per_symbol_cap_reached")

    side_open, side_cap = _exposure_side_cap(symbol, side)
    caps["open_side"] = side_open
    caps["cap_side"] = side_cap
    if side_cap > 0 and side_open >= side_cap:
        reasons.append("per_side_cap_reached")

    if _same_side_block(symbol, side):
        reasons.append("same_side_blocked")

    eq = _account_equity()
    floor = _env_float("EQUITY_FLOOR", 0.0)
    caps["equity"] = round(eq, 2)
    caps["equity_floor"] = floor
    if floor > 0.0 and eq <= floor:
        reasons.append("equity_floor_breached")

    daily_loss_limit = _env_float("DAILY_LOSS_LIMIT", 0.0)
    daily_pnl_val = _daily_pnl()
    caps["daily_pnl"] = round(daily_pnl_val, 2)
    caps["daily_loss_limit"] = daily_loss_limit
    if daily_loss_limit > 0.0 and daily_pnl_val <= -abs(daily_loss_limit):
        reasons.append("daily_loss_limit_hit")

    min_symbol_flt = _env_float("MIN_SYMBOL_FLOATING_PNL", 0.0)
    flt = _floating_symbol_pnl(symbol)
    caps["symbol_floating_pnl"] = round(flt, 2)
    caps["symbol_floating_min"] = min_symbol_flt
    if min_symbol_flt < 0.0 and flt <= min_symbol_flt:
        reasons.append("symbol_floating_under_min")

    ok = not reasons
    return {"ok": ok, "why": reasons, "caps": caps}


# ---- Back-compat export (main.py expects risk_guard) ----
risk_guard = check_pretrade_guards

# Optional: define _all_ so static analyzers know what's exported
_all_ = [
    "check_pretrade_guards",
    "note_trade",
    "risk_guard",
]
