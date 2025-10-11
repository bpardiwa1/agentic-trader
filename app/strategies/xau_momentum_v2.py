# ============================================================
# Agentic Trader - XAU Momentum v2
# EMA / RSI / ATR Enhanced Momentum Strategy (Gold)
# ============================================================

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from pandas import DataFrame

from app.util.indicators import compute_ema as ema
from app.util.indicators import compute_rsi as rsi
from app.util.mt5_bars import get_bars as _get_bars

# ============================================================
# Constants
# ============================================================
MIN_BARS_REQUIRED = 60
logger = logging.getLogger(__name__)

# ============================================================
# Helpers
# ============================================================


def _env_get(env: Mapping[str, str], key: str, cast: Callable = float, default=None):
    v = env.get(key)
    try:
        return cast(v) if v is not None else default
    except Exception:
        return default


def _norm_key(symbol: str) -> str:
    return symbol.replace("-", "_").replace(".", "_").upper()


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    """Compute ATR using True Range."""
    if len(highs) < period + 1:
        return float("nan")
    h, l, c = np.array(highs), np.array(lows), np.array(closes)
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    return float(np.mean(tr[-period:]))


# ============================================================
# Core XAU Momentum v2
# ============================================================


def xau_momentum_features(
    symbol: str,
    timeframe: str,
    env: Mapping[str, str],
    get_bars: Callable[[str, str, int], DataFrame | None] = _get_bars,
) -> dict[str, Any]:
    """
    Enhanced EMA/RSI/ATR Momentum strategy for Gold.
    Returns dictionary consumed by auto_decider.
    """
    bars = get_bars(symbol, timeframe, 240)
    if bars is None or bars.empty or len(bars) < MIN_BARS_REQUIRED:
        return {"accepted": False, "symbol": symbol, "why": ["no features"]}

    closes = bars["close"].tolist()
    highs = bars["high"].tolist()
    lows = bars["low"].tolist()
    price = float(closes[-1])
    key = _norm_key(symbol)

    # --- Parameters from env ---
    ema_fast_p = _env_get(env, f"EMA_FAST_{key}", int, 20)
    ema_slow_p = _env_get(env, f"EMA_SLOW_{key}", int, 50)
    rsi_p = _env_get(env, f"RSI_PERIOD_{key}", int, 14)
    rsi_long = _env_get(env, f"RSI_LONG_TH_{key}", float, 60.0)
    rsi_short = _env_get(env, f"RSI_SHORT_TH_{key}", float, 40.0)
    rsi_band = _env_get(env, f"RSI_BAND_{key}", float, 3.0)
    atr_p = _env_get(env, f"ATR_PERIOD_{key}", int, 14)
    atr_min = _env_get(env, f"ATR_MIN_{key}", float, 0.50)
    sep_k = _env_get(env, f"EMA_SEP_K_{key}", float, 0.8)
    eps = _env_get(env, f"EPS_{key}", float, 0.10)

    # Ensure period parameters are valid
    if (
        ema_fast_p is None
        or ema_slow_p is None
        or rsi_p is None
        or atr_p is None
        or rsi_long is None
        or rsi_short is None
        or rsi_band is None
    ):
        return {"accepted": False, "symbol": symbol, "why": ["invalid_period_parameter"]}

    # --- Indicators ---
    ema_fast = ema(closes, ema_fast_p)
    ema_slow = ema(closes, ema_slow_p)
    rsi_val = rsi(closes, rsi_p)
    atr_val = _atr(highs, lows, closes, atr_p)

    if np.isnan(ema_fast) or np.isnan(ema_slow) or np.isnan(rsi_val):
        return {"accepted": False, "symbol": symbol, "why": ["invalid_indicators"]}

    # --- Regime logic ---
    regime = "no_trade"
    side = ""
    sep = abs(ema_fast - ema_slow)

    slope_fast = ema(closes[-ema_fast_p:], max(2, ema_fast_p // 2)) - ema(
        closes[-ema_fast_p - 2 : -2], max(2, ema_fast_p // 2)
    )
    slope_slow = ema(closes[-ema_slow_p:], max(2, ema_slow_p // 2)) - ema(
        closes[-ema_slow_p - 2 : -2], max(2, ema_slow_p // 2)
    )

    if atr_val is None or np.isnan(atr_val) or atr_min is None or atr_val < atr_min:
        regime = "no_trade"
        why = ["atr_below_min"]
    elif (
        ema_fast > ema_slow
        and slope_fast > 0
        and slope_slow > 0
        and rsi_val > (rsi_long + rsi_band)
    ):
        regime = "TRENDING_UP"
        side = "LONG"
        why = ["conditions_met"]
    elif (
        ema_fast < ema_slow
        and slope_fast < 0
        and slope_slow < 0
        and rsi_val < (rsi_short - rsi_band)
    ):
        regime = "TRENDING_DOWN"
        side = "SHORT"
        why = ["conditions_met"]
    else:
        why = ["no_signal"]

    # =====================================================
    # SL/TP Logic (ATR or static fallback)
    # =====================================================
    use_atr_sl = env.get("XAU_ATR_ENABLED", "false").lower() == "true"
    atr_sl_mult = _env_get(env, "XAU_ATR_SL_MULT", float, 1.0)
    atr_tp_mult = _env_get(env, "XAU_ATR_TP_MULT", float, 2.0)

    if (
        use_atr_sl
        and atr_val is not None
        and not np.isnan(atr_val)
        and atr_val > 0
        and atr_sl_mult is not None
        and atr_tp_mult is not None
    ):
        pip_mult = 10.0 if "XAU" in symbol.upper() else 1.0
        sl_pips = max(float(atr_sl_mult) * float(atr_val) * float(pip_mult), 50.0)
        tp_pips = max(float(atr_tp_mult) * float(atr_val) * float(pip_mult), 100.0)
    else:
        sl_pips = _env_get(env, f"SL_PIPS_{key}", float, 400.0)
        tp_pips = _env_get(env, f"TP_PIPS_{key}", float, 900.0)

    logger.info(f"[SLTP] {symbol} sl_pips={sl_pips:.2f} tp_pips={tp_pips:.2f} (ATR={atr_val:.3f})")

    # =====================================================
    # Debug deltas — how far from trigger
    # =====================================================
    rsi_gap_long = rsi_val - rsi_long
    rsi_gap_short = rsi_short - rsi_val
    ema_sep_atr = sep / max(atr_val, 1e-6)

    logger.info(
        f"[DEBUG_DELTA] {symbol} RSI={rsi_val:.2f} "
        f"(gap_long={rsi_gap_long:+.2f}, gap_short={rsi_gap_short:+.2f}) | "
        f"EMA_sep={sep:.3f} ({ema_sep_atr:.2f} ATRs)"
    )

    # =====================================================
    # Final return payload
    # =====================================================
    logger.info(
        f"[DEBUG] {symbol} regime={regime} | side={side} | "
        f"EMA_FAST={ema_fast:.3f} | EMA_SLOW={ema_slow:.3f} | "
        f"RSI={rsi_val:.2f} | ATR={atr_val:.3f} | sep={sep:.3f}"
    )

    return {
        "accepted": True,
        "symbol": symbol,
        "price": price,
        "side": side,
        "regime": regime,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "rsi": rsi_val,
        "atr": atr_val,
        "eps": eps,
        "params": {
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "rsi_long_th": rsi_long,
            "rsi_short_th": rsi_short,
            "rsi_period": rsi_p,
        },
        "features": {
            "ema_slope_fast": slope_fast,
            "ema_slope_slow": slope_slow,
            "sep": sep,
            "sep_k": sep_k,
            "rsi_band": rsi_band,
            "atr_min": atr_min,
            "atr_p": atr_p,
            "timeframe": timeframe,
        },
        "why": why,
    }
