# app/util/sizing.py
from __future__ import annotations

import os

# app/util/sizing.py
import re

import MetaTrader5 as mt5


def lots_override_for(symbol: str, default_lots: float) -> float:
    key = "LOTS_" + re.sub(r"[^A-Z0-9]+", "_", symbol.upper())
    val = os.getenv(key)
    try:
        return float(val) if val is not None else default_lots
    except Exception:
        return default_lots


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)).split("#", 1)[0].strip())
    except Exception:
        return default


def _env_str(key: str, default: str) -> str:
    v = os.environ.get(key, default)
    return v.split("#", 1)[0].strip()


def _pip_to_price(symbol: str, pips: float) -> float:
    """Convert 'pips' to absolute price distance using mt5 symbol point & pip convention."""
    info = mt5.symbol_info(symbol)
    if not info:
        # Fallback: assume FX 1 pip = 10 * point; XAU 1 pip = 0.1 (varies by broker)
        point = 0.0001
        pip_factor = 10.0
    else:
        point = info.point
        # Heuristic: FX usually 1 pip = 10 * point (e.g. EURUSD point=0.00001, pip=0.0001)
        # Metals often quote point=0.01 or 0.1; many brokers treat 1 "pip" as 0.1 for gold
        sym = symbol.upper()
        if sym.startswith("XAU") or "GOLD" in sym:
            # Treat 1 pip as 0.1 (adjustable via env override)
            pip_val_abs = _env_float("XAU_PIP_ABS", 0.1)
            return float(pips) * pip_val_abs
        # Default FX pip
        pip_factor = 10.0
    return float(pips) * point * pip_factor


def _risk_lots_from_sl(
    symbol: str, sl_price_distance: float, risk_amount: float
) -> float | None:
    """
    Compute lots so that risk = risk_amount when SL is hit.
    Uses tick_value/tick_size from MT5 to estimate money per price unit per 1 lot.
    lots = risk_amount / (sl_distance * money_per_price_unit_per_1lot)
    """
    info = mt5.symbol_info(symbol)
    if not info:
        return None
    tv = info.trade_tick_value
    ts = info.trade_tick_size if info.trade_tick_size else info.point
    if not ts or not tv:
        return None
    money_per_price_unit_1lot = tv / ts  # $ per 1.0 price unit for 1 lot
    risk_per_lot = sl_price_distance * money_per_price_unit_1lot
    if risk_per_lot <= 0:
        return None
    lots = risk_amount / risk_per_lot
    return lots


def compute_lot(
    symbol: str,
    sl_pips: float | None,
    *,
    mode: str | None = None,
    default_lots: float | None = None,
) -> float:
    """
    Returns lot size float based on LOT_MODE:
      - fixed:  LOTS_<SYMBOL> or MT5_DEFAULT_LOTS
      - risk:   RISK_PCT% of balance per trade, sized by sl_pips and symbol tick economics
    """
    mode = (mode or _env_str("LOT_MODE", "fixed")).lower()
    # Read defaults
    if default_lots is None:
        try:
            default_lots = float(
                os.environ.get("MT5_DEFAULT_LOTS", "0.01").split("#", 1)[0].strip()
            )
        except Exception:
            default_lots = 0.01

    # Per-symbol override (works in either mode as a hard cap/fallback)
    import re

    key = "LOTS_" + re.sub(r"[^A-Z0-9]+", "_", symbol.upper())
    env_lots_raw = os.environ.get(key)
    env_lots = None
    try:
        if env_lots_raw:
            env_lots = float(env_lots_raw.split("#", 1)[0].strip())
    except Exception:
        env_lots = None

    # Fixed mode: honor per-symbol or default
    if mode == "fixed" or sl_pips is None:
        return env_lots if env_lots is not None else default_lots

    # Risk mode
    # Parameters
    risk_pct = _env_float("RISK_PCT", 0.01)  # 1% default
    min_lot = _env_float("MIN_LOT", 0.01)
    max_lot = _env_float("MAX_LOT", 1.00)

    # Account balance
    ai = mt5.account_info()
    if not ai:
        # Fallback to fixed if no account context
        return env_lots if env_lots is not None else default_lots
    risk_amount = max(0.0, ai.balance * risk_pct)

    # Convert SL (pips) -> absolute price distance
    sl_dist = _pip_to_price(symbol, sl_pips)

    lots = _risk_lots_from_sl(symbol, sl_dist, risk_amount)
    if lots is None:
        # Fallback: fixed
        return env_lots if env_lots is not None else default_lots

    # Optional clamp with per-symbol env override (acts as cap if provided)
    if env_lots is not None:
        max_lot = min(max_lot, env_lots)

    lots = max(min_lot, min(max_lot, lots))
    # Normalize to broker step if available
    info = mt5.symbol_info(symbol)
    if info and info.volume_step:
        step = float(info.volume_step)
        # round down to step to avoid "invalid volume"
        lots = (int(lots / step)) * step
        lots = max(lots, step)
    return float(lots)
