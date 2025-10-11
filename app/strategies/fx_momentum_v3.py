# ============================================================
# Agentic Trader - FX Momentum v2
# EMA / RSI / ATR Enhanced Momentum Strategy
# ============================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from pandas import DataFrame

from app.util.indicators import compute_ema as ema
from app.util.indicators import compute_rsi as rsi
from app.util.mt5_bars import get_bars as _get_bars

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
    tr = np.maximum.reduce(
        [
            h[1:] - l[1:],
            np.abs(h[1:] - c[:-1]),
            np.abs(l[1:] - c[:-1]),
        ]
    )
    return float(np.mean(tr[-period:]))


# ============================================================
# Core FX Momentum v2
# ============================================================


def fx_momentum_features(
    symbol: str,
    timeframe: str,
    env: Mapping[str, str],
    get_bars: Callable[[str, str, int], DataFrame | None] = _get_bars,
) -> dict[str, Any]:
    """
    Enhanced EMA/RSI/ATR Momentum strategy.
    Returns dictionary consumed by auto_decider.
    """
    bars = get_bars(symbol, timeframe, 240)
    if bars is None or bars.empty or len(bars) < 80:
        return {"accepted": False, "symbol": symbol, "why": ["no features"]}

    closes = bars["close"].tolist()
    highs = bars["high"].tolist()
    lows = bars["low"].tolist()
    price = float(closes[-1])
    key = _norm_key(symbol)

    # --- Parameters from env ---
    ema_fast_p = _env_get(env, f"EMA_FAST_{key}", int, 20) or 20
    ema_slow_p = _env_get(env, f"EMA_SLOW_{key}", int, 50) or 50
    rsi_p = _env_get(env, f"RSI_PERIOD_{key}", int, 14) or 14
    rsi_long = _env_get(env, f"RSI_LONG_TH_{key}", float, 58.0)
    rsi_short = _env_get(env, f"RSI_SHORT_TH_{key}", float, 42.0)
    rsi_band = _env_get(env, f"RSI_BAND_{key}", float, 2.0)
    atr_p = _env_get(env, f"ATR_PERIOD_{key}", int, 14) or 14
    atr_min = _env_get(env, f"ATR_MIN_{key}", float, 0.0007)
    sep_k = _env_get(env, f"EMA_SEP_K_{key}", float, 0.6)
    eps = _env_get(env, f"EPS_{key}", float, 0.0001)

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

    # --- Decision ---
    if (
        atr_val is None
        or atr_min is None
        or np.isnan(atr_val)
        or np.isnan(atr_min)
        or atr_val < atr_min
    ):
        regime = "no_trade"
        why = ["atr_below_min"]
    elif (
        ema_fast > ema_slow
        and slope_fast > 0
        and slope_slow > 0
        and rsi_long is not None
        and rsi_band is not None
        and rsi_val > rsi_long + rsi_band
    ):
        regime = "TRENDING_UP"
        side = "LONG"
        why = ["conditions_met"]
    elif (
        ema_fast < ema_slow
        and slope_fast < 0
        and slope_slow < 0
        and rsi_short is not None
        and rsi_band is not None
        and rsi_val < rsi_short - rsi_band
    ):
        regime = "TRENDING_DOWN"
        side = "SHORT"
        why = ["conditions_met"]
    else:
        why = ["no_signal"]

    # =====================================================
    # SL/TP Logic (ATR or static fallback)
    # =====================================================
    use_atr_sl = env.get("FX_ATR_ENABLED", "false").lower() == "true"
    atr_sl_mult = _env_get(env, "FX_ATR_SL_MULT", float, 2.0)
    atr_tp_mult = _env_get(env, "FX_ATR_TP_MULT", float, 3.0)

    if (
        use_atr_sl
        and atr_val is not None
        and atr_sl_mult is not None
        and atr_tp_mult is not None
        and not np.isnan(atr_val)
        and atr_val > 0
    ):
        sl_pips = max(atr_sl_mult * atr_val * 10000, 10)
        tp_pips = max(atr_tp_mult * atr_val * 10000, 20)
    else:
        sl_pips = _env_get(env, f"SL_PIPS_{key}", float, 40.0)
        tp_pips = _env_get(env, f"TP_PIPS_{key}", float, 90.0)

    print(f"[SLTP] {symbol} sl_pips={sl_pips:.1f} tp_pips={tp_pips:.1f} (ATR={atr_val:.5f})")

    # =====================================================
    # Final return payload
    # =====================================================
    print(
        f"[DEBUG] {symbol} regime={regime} | side={side} | "
        f"EMA_FAST={ema_fast:.5f} | EMA_SLOW={ema_slow:.5f} | "
        f"RSI={rsi_val:.2f} | ATR={atr_val:.5f} | sep={sep:.5f}"
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
