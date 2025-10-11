# ============================================================
# Agentic Trader - Indices Momentum v2 (NAS100-focused)
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

# ---- constants ----
MIN_BARS_REQUIRED = 80
DEFAULT_ATR_PERIOD = 14


def _env_get(env: Mapping[str, str], key: str, cast: Callable = float, default=None):
    v = env.get(key)
    if v is None:
        return default
    try:
        result = cast(v)
        if result is None:
            return default
        return result
    except Exception:
        return default


def _norm_key(symbol: str) -> str:
    # e.g. "NAS100-ECNc" -> "NAS100_ECNC" -> env keys like EMA_FAST_NAS100
    # We'll try a couple of fallbacks: raw root (NAS100) as primary.
    up = symbol.replace("-", "_").replace(".", "_").upper()
    # Prefer pure index root if present in the symbol
    for root in ("NAS100", "US30", "GER40", "SPX500", "UK100", "HK50", "JP225"):
        if root in up:
            return root
    return up


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    """Average True Range using simple mean of TR over last 'period' bars."""
    if len(highs) < period + 1:
        return float("nan")
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    tr = np.maximum.reduce(
        [
            h[1:] - l[1:],
            np.abs(h[1:] - c[:-1]),
            np.abs(l[1:] - c[:-1]),
        ]
    )
    return float(np.mean(tr[-period:]))


def indices_momentum_features(
    symbol: str,
    timeframe: str,
    env: Mapping[str, str],
    get_bars: Callable[[str, str, int], DataFrame | None] = _get_bars,
) -> dict[str, Any]:
    """
    Momentum v2 for Indices (NAS100). Returns a dict consumed by auto_decider.
    """
    bars = get_bars(symbol, timeframe, 240)
    if bars is None or bars.empty or len(bars) < MIN_BARS_REQUIRED:
        return {"accepted": False, "symbol": symbol, "why": ["no features"]}

    closes = bars["close"].astype(float).tolist()
    highs = bars["high"].astype(float).tolist()
    lows = bars["low"].astype(float).tolist()
    price = float(closes[-1])

    key = _norm_key(symbol)  # -> "NAS100" for NAS100-ECNc

    # -----------------------------
    # Parameters (with safe defaults tuned for NAS100)
    # -----------------------------
    ema_fast_p_val = _env_get(env, f"EMA_FAST_{key}", int, 20)
    ema_fast_p: int = int(ema_fast_p_val if ema_fast_p_val is not None else 20)
    ema_slow_p_val = _env_get(env, f"EMA_SLOW_{key}", int, 50)
    ema_slow_p: int = int(ema_slow_p_val if ema_slow_p_val is not None else 50)
    rsi_p_val = _env_get(env, f"RSI_PERIOD_{key}", int, 14)
    rsi_p: int = int(rsi_p_val if rsi_p_val is not None else 14)
    rsi_long_val = _env_get(env, f"RSI_LONG_TH_{key}", float, 60.0)
    rsi_long: float = float(rsi_long_val if rsi_long_val is not None else 60.0)
    rsi_short_val = _env_get(env, f"RSI_SHORT_TH_{key}", float, 40.0)
    rsi_short: float = float(rsi_short_val if rsi_short_val is not None else 40.0)
    rsi_band_val = _env_get(env, f"RSI_BAND_{key}", float, 3.0)
    rsi_band: float = float(rsi_band_val if rsi_band_val is not None else 3.0)

    atr_p_val = _env_get(env, f"ATR_PERIOD_{key}", int, DEFAULT_ATR_PERIOD)
    atr_p: int = int(atr_p_val if atr_p_val is not None else DEFAULT_ATR_PERIOD)
    # NAS100 typical 15m ATR tens of points; start with 30 as min filter
    atr_min_val = _env_get(env, f"ATR_MIN_{key}", float, 30.0)
    atr_min: float = float(atr_min_val if atr_min_val is not None else 30.0)

    # how far EMAs must be separated (k * ATR) to avoid flat crosses
    sep_k_val = _env_get(env, f"EMA_SEP_K_{key}", float, 0.6)
    sep_k: float = float(sep_k_val if sep_k_val is not None else 0.6)

    # execution epsilon (point rounding / spread cushion)
    eps_val = _env_get(env, f"EPS_{key}", float, 0.5)
    eps: float = float(eps_val if eps_val is not None else 0.5)

    # -----------------------------
    # Indicators
    # -----------------------------
    ema_fast = ema(closes, ema_fast_p)
    ema_slow = ema(closes, ema_slow_p)
    rsi_val = rsi(closes, rsi_p)
    atr_val = _atr(highs, lows, closes, atr_p)

    if any(np.isnan(x) for x in (ema_fast, ema_slow, rsi_val, atr_val)):
        return {"accepted": False, "symbol": symbol, "why": ["invalid_indicators"]}

    # EMA slopes (short EMA of last window vs 2 bars back)
    slope_win_fast = max(2, ema_fast_p // 2)
    slope_win_slow = max(2, ema_slow_p // 2)
    slope_fast = ema(closes[-ema_fast_p:], slope_win_fast) - ema(
        closes[-ema_fast_p - 2 : -2], slope_win_fast
    )
    slope_slow = ema(closes[-ema_slow_p:], slope_win_slow) - ema(
        closes[-ema_slow_p - 2 : -2], slope_win_slow
    )

    sep = abs(ema_fast - ema_slow)

    regime = "no_trade"
    side = ""
    why: list[str] = []

    # -----------------------------
    # Filters & signal
    # -----------------------------
    if atr_val < atr_min:
        why.append("atr_below_min")
    elif sep < sep_k * atr_val:
        why.append("ema_separation_insufficient")
    elif (
        ema_fast > ema_slow
        and slope_fast > 0
        and slope_slow > 0
        and rsi_val > (rsi_long + rsi_band)
    ):
        regime, side = "TRENDING_UP", "LONG"
        why.append("conditions_met")
    elif (
        ema_fast < ema_slow
        and slope_fast < 0
        and slope_slow < 0
        and rsi_val < (rsi_short - rsi_band)
    ):
        regime, side = "TRENDING_DOWN", "SHORT"
        why.append("conditions_met")
    else:
        why.append("no_signal")

    # -----------------------------
    # ATR-based SL/TP (points) with safe fallback
    # -----------------------------
    use_atr_sl = env.get("INDEX_ATR_ENABLED", "false").lower() == "true"
    atr_sl_mult_val = _env_get(env, "INDEX_ATR_SL_MULT", float, 1.0)
    atr_sl_mult: float = float(atr_sl_mult_val if atr_sl_mult_val is not None else 1.0)
    atr_tp_mult_val = _env_get(env, "INDEX_ATR_TP_MULT", float, 2.0)
    atr_tp_mult: float = float(atr_tp_mult_val if atr_tp_mult_val is not None else 2.0)

    if use_atr_sl and atr_val > 0:
        sl_pips = max(atr_sl_mult * atr_val, 10.0)  # min 10 points
        tp_pips = max(atr_tp_mult * atr_val, 20.0)
    else:
        # Fallback static SL/TP in points (indices “pips” == points here)
        sl_pips_val = _env_get(env, f"SL_PIPS_{key}", float, 80.0)
        sl_pips = float(sl_pips_val if sl_pips_val is not None else 80.0)
        tp_pips_val = _env_get(env, f"TP_PIPS_{key}", float, 160.0)
        tp_pips = float(tp_pips_val if tp_pips_val is not None else 160.0)

    print(
        f"[IDX SLTP] {symbol} sl={sl_pips:.1f} tp={tp_pips:.1f} "
        f"(ATR={atr_val:.2f}, sep={sep:.2f}, k={sep_k})"
    )
    print(
        f"[IDX DEBUG] {symbol} regime={regime} side={side} "
        f"EMAf={ema_fast:.2f} EMAs={ema_slow:.2f} slope_f={slope_fast:.4f} slope_s={slope_slow:.4f} "
        f"RSI={rsi_val:.2f}"
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
