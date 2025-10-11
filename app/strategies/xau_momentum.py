# app/strategies/xau_momentum.py

import logging
from typing import Any

import MetaTrader5 as _mt5

from app.util.indicators import compute_ema, compute_rsi
from app.util.mt5_bars import get_bars

logger = logging.getLogger(__name__)
mt5: Any = _mt5


def xau_momentum_features(
    symbol: str, timeframe: str, env: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Extract EMA/RSI features for XAU (Gold) momentum strategy.
    No trade decision logic here — just raw features for auto_decider.
    """

    try:
        key_base = symbol.replace("-", "_").replace(".", "_").upper()

        # Parameter overrides
        ema_fast = int(env.get(f"EMA_FAST_{key_base}", 20)) if env else 20
        ema_slow = int(env.get(f"EMA_SLOW_{key_base}", 50)) if env else 50
        rsi_period = int(env.get(f"RSI_PERIOD_{key_base}", 14)) if env else 14
        rsi_long_th = float(env.get(f"RSI_LONG_TH_{key_base}", 60)) if env else 60
        rsi_short_th = float(env.get(f"RSI_SHORT_TH_{key_base}", 40)) if env else 40
        eps = float(env.get(f"EPS_{key_base}", 1.0)) if env else 1.0
        sl_pips = float(env.get(f"SL_{key_base}", 300.0)) if env else 300.0
        tp_pips = float(env.get(f"TP_{key_base}", 600.0)) if env else 600.0

        timeframe_val = env.get("TIMEFRAME", "M15") if env else "M15"
        df = get_bars(symbol, timeframe_val, ema_slow + 5)
        if df is None or df.empty:
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
                # placeholder flags for guardrails (to be filled later)
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
        logger.exception("Error in xau_momentum_features")
        return {"accepted": False, "error": "strategy_error", "why": [str(e)]}
