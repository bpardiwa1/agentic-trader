# app/strategies/indices_momentum.py

import logging
from typing import Any

import numpy as np

from app.util.mt5_bars import get_bars

logger = logging.getLogger(__name__)

# -----------------------------
# Constants
# -----------------------------
RSI_LONG_DEFAULT = 60.0
RSI_SHORT_DEFAULT = 40.0
EPSILON_MIN = 1e-9


def compute_ema(values: list[float], period: int) -> float:
    """Compute EMA using numpy for stability."""
    weights = np.exp(np.linspace(-1.0, 0.0, period))
    weights /= weights.sum()
    ema = np.convolve(values, weights, mode="full")[: len(values)]
    return float(ema[-1])


def compute_rsi(values: list[float], period: int) -> float:
    """Compute RSI with numpy operations."""
    deltas = np.diff(values)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / (down + EPSILON_MIN)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(rsi)


def indices_momentum_features(
    symbol: str, timeframe: str, env: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Extract EMA/RSI features for Indices.
    No trade decision here — features only, consumed by auto_decider.
    """
    try:
        # Normalize symbol -> key_base
        key_base = symbol.replace(".s", "").replace("-", "_").upper()

        # Params with env overrides
        ema_fast = int(env.get("INDICES_EMA_FAST", 20)) if env else 20
        ema_slow = int(env.get("INDICES_EMA_SLOW", 50)) if env else 50
        rsi_period = int(env.get("INDICES_RSI_PERIOD", 14)) if env else 14
        rsi_long_th = (
            float(
                env.get(
                    f"INDICES_RSI_LONG_TH_{key_base}",
                    env.get("INDICES_RSI_LONG_TH", RSI_LONG_DEFAULT),
                )
            )
            if env
            else RSI_LONG_DEFAULT
        )
        rsi_short_th = (
            float(
                env.get(
                    f"INDICES_RSI_SHORT_TH_{key_base}",
                    env.get("INDICES_RSI_SHORT_TH", RSI_SHORT_DEFAULT),
                )
            )
            if env
            else RSI_SHORT_DEFAULT
        )

        eps = float(env.get(f"INDICES_EPS_{key_base}", env.get("INDICES_EPS", 1.0))) if env else 1.0
        sl_pips = (
            float(env.get(f"INDICES_SL_{key_base}", env.get("INDICES_SL", 100.0))) if env else 100.0
        )
        tp_pips = (
            float(env.get(f"INDICES_TP_{key_base}", env.get("INDICES_TP", 200.0))) if env else 200.0
        )

        # Get candles
        df = get_bars(symbol, timeframe, ema_slow + 5)
        if df is None or len(df) < ema_slow + 5:
            return {"accepted": False, "note": "no_data"}

        closes = df["close"].astype(float).tolist()

        ema_fast_val = float(compute_ema(closes, ema_fast))
        ema_slow_val = float(compute_ema(closes, ema_slow))
        rsi_val = float(compute_rsi(closes, rsi_period))
        price = float(closes[-1])

        return {
            "accepted": True,
            "symbol": symbol,
            "price": price,
            "ema_fast": ema_fast_val,
            "ema_slow": ema_slow_val,
            "rsi": rsi_val,
            "eps": eps,
            "params": {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi_period": rsi_period,
                "rsi_long_th": rsi_long_th,
                "rsi_short_th": rsi_short_th,
                "eps": eps,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
            },
            "features": {
                # Placeholder guardrail flags
                "structure_break_up": False,
                "pullback_holds_fastEMA_or_VWAP": False,
                "bearish_divergence": False,
                "level_rejection": False,
                "structure_break_down": False,
                "pullback_rejects_fastEMA_or_VWAP": False,
                "bullish_divergence": False,
                "support_hold": False,
            },
        }

    except Exception as e:
        logger.exception("%s: Strategy error", symbol)
        return {"accepted": False, "error": "strategy_error", "why": [str(e)]}
