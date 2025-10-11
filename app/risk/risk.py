from __future__ import annotations

import os
from typing import Any, cast

import MetaTrader5 as _mt5

# Treat MT5 as dynamic at type-check time (stops Pylance attr errors).
mt5: Any = cast(Any, _mt5)

# ---------------- Tunables / constants ----------------
MAX_SYMBOL_SELECT_TRIES = 5
DIGITS_FIVE = 5
DIGITS_THREE = 3

# Env keys
ENV_LOT_MODE = "LOT_MODE"  # "risk" or "fixed"
ENV_RISK_DOLLARS = "RISK_DOLLAR_PER_TRADE"
ENV_RISK_PCT = "RISK_PCT"  # 0.01 = 1%
ENV_MIN_LOT = "MIN_LOT"
ENV_MAX_LOT = "MAX_LOT"
ENV_DEFAULT_LOTS = "MT5_DEFAULT_LOTS"


# ---------------- Env helpers ----------------
def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


def _env_float(name: str, default: float) -> float:
    try:
        raw = (os.getenv(name) or str(default)).split("#", 1)[0].strip()
        return float(raw)
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_key(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in (s or "").upper())


def _per_symbol_lots(symbol: str, fallback: float) -> float:
    key = f"LOTS_{_normalize_key(symbol)}"
    val = os.getenv(key)
    if val:
        try:
            return float(val)
        except Exception:
            pass
    return _env_float(ENV_DEFAULT_LOTS, fallback)


# ---------------- Pricing helpers ----------------
def _pip_size_guess(symbol: str) -> float:
    """
    Guess pip size (price units per pip).
    - Metals XAU*: 0.10
    - *JPY pairs:   0.01
    - 5-digit FX:   0.00010
    Fallback: use symbol point scaled by digits.
    """
    s = symbol.upper()
    if "XAU" in s:
        return 0.10
    if s.endswith("JPY") or "JPY" in s:
        return 0.01

    info = mt5.symbol_info(symbol)
    point = float(getattr(info, "point", 0.0)) if info else 0.0
    digits = int(getattr(info, "digits", 0)) if info else 0

    if digits >= DIGITS_FIVE:
        # 5-digit quotes: 1 pip = 10 * point
        return 10.0 * point or 0.00010
    if digits >= DIGITS_THREE:
        # 3-digit quotes: 1 pip = 10 * point
        return 10.0 * point or 0.010
    return point or 0.00010


def pip_value_per_lot(symbol: str) -> float:
    """
    Value of 1 pip for 1.00 lot, in account currency.
    Uses MT5 tick_value and tick_size when available; otherwise falls back to pip guess.
    """
    info = mt5.symbol_info(symbol)
    if not info:
        # Conservative default for FX majors if metadata missing.
        return 10.0

    tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "tick_size", 0.0))
    tick_value = float(getattr(info, "trade_tick_value", 0.0) or getattr(info, "tick_value", 0.0))
    point = float(getattr(info, "point", 0.0))
    pip = _pip_size_guess(symbol)

    if tick_size and tick_value and point:
        # Convert tick value (per 1 point change) to per-pip value.
        # Relation: 1 pip = (pip / point) * (point / tick_size) * tick_value_per_tick
        # But in MT5, tick_value is usually per tick_size or per point depending on broker.
        # A safer approximation is: per-pip value ~= (pip / point) * tick_value
        try:
            per_pip = (pip / point) * tick_value
            if per_pip > 0:
                return per_pip
        except Exception:
            pass

    # Fallback heuristic: FX majors ~ $10/pip per lot, JPY pairs similar after scaling,
    # metals vary; use pip guess and assume $1 per 0.0001 on 1 lot (=> $10 per pip).
    # If broker metadata is partial, this keeps sizing in a safe ballpark.
    if "XAU" in symbol.upper():
        # Gold typical: ~ $1 per 0.01 tick per lot -> ~$10 per $0.10 (1 pip)
        return 10.0

    return 10.0


# ---------------- Account helpers ----------------
def _account_equity() -> float:
    acc = mt5.account_info()
    if not acc:
        # If MT5 not connected yet, assume a safe placeholder.
        return 0.0
    eq = float(getattr(acc, "equity", 0.0))
    if eq > 0:
        return eq
    # Some brokers report 0 during reconnect; fall back to balance.
    return float(getattr(acc, "balance", 0.0))


# ---------------- Sizing ----------------
def size_from_risk(
    symbol: str,
    sl_pips: float,
    risk_dollars: float | None = None,
    risk_pct: float | None = None,
    min_lot: float | None = None,
    max_lot: float | None = None,
) -> float:
    """
    Compute lot size given SL distance (in pips) and either absolute dollars or percentage risk.
    Clamps to [min_lot, max_lot].
    """
    eq = _account_equity()
    min_l = float(min_lot if min_lot is not None else _env_float(ENV_MIN_LOT, 0.01))
    max_l = float(max_lot if max_lot is not None else _env_float(ENV_MAX_LOT, 1.00))

    # Determine risk dollars
    rd = float(risk_dollars) if risk_dollars is not None else 0.0
    if rd <= 0.0 and risk_pct is not None and risk_pct > 0.0 and eq > 0.0:
        rd = float(eq * float(risk_pct))

    # As a final fallback, use env RISK_DOLLAR_PER_TRADE or RISK_PCT*equity
    if rd <= 0.0:
        env_rd = _env_float(ENV_RISK_DOLLARS, 0.0)
        if env_rd > 0.0:
            rd = env_rd
        else:
            env_rpct = _env_float(ENV_RISK_PCT, 0.0)
            if env_rpct > 0.0 and eq > 0.0:
                rd = eq * env_rpct

    # If still zero, return minimum lot to avoid divide-by-zero surprises.
    if rd <= 0.0 or sl_pips <= 0.0:
        return max(min_l, 0.0)

    per_pip_1lot = pip_value_per_lot(symbol)
    if per_pip_1lot <= 0.0:
        return min_l

    # risk = per_pip_value * sl_pips * lots
    lots = float(rd / (per_pip_1lot * sl_pips))

    if lots < min_l:
        return min_l
    if lots > max_l:
        return max_l
    return lots


def compute_order_size(
    symbol: str,
    side: str,
    sl_pips: float | None,
) -> float:
    """
    User-facing entrypoint used by the executor/agents.
    Decides between LOT_MODE=risk|fixed and returns the lot size.
    """
    mode = _env_str(ENV_LOT_MODE, "risk").lower()
    if mode not in {"risk", "fixed"}:
        mode = "risk"

    if mode == "fixed":
        # Per-symbol override (LOTS_<SYMBOL>) -> MT5_DEFAULT_LOTS -> 0.01
        return _per_symbol_lots(symbol, 0.01)

    # LOT_MODE=risk
    sp = float(sl_pips or 0.0)
    return size_from_risk(
        symbol=symbol,
        sl_pips=sp if sp > 0.0 else 1.0,  # avoid zero; will clamp by min lot anyway
        risk_dollars=None,  # let size_from_risk read env or % of equity
        risk_pct=None,
        min_lot=None,
        max_lot=None,
    )
