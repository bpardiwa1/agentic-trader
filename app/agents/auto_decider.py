# app/agents/auto_decider.py
from __future__ import annotations

import logging
import os
from typing import Any

import MetaTrader5 as mt5  # type: ignore[import]

from app.market.data import get_rates_df
from app.strategies.fx_momentum import fx_momentum_features
from app.strategies.indices_momentum import indices_momentum_features
from app.strategies.xau_momentum import xau_momentum_features

logger = logging.getLogger(__name__)

# USE_EXPERIMENTAL_FX = os.getenv("USE_EXPERIMENTAL_FX", "false").lower() == "true"
# if USE_EXPERIMENTAL_FX:
#     from app.strategies.fx_momentum_v2 import fx_momentum_features
# else:
#     from app.strategies.fx_momentum import fx_momentum_features


# ============================================================
# Strategy imports — dynamically load v2 if experimental mode is active
# ============================================================


USE_EXPERIMENTAL_FX = os.getenv("USE_EXPERIMENTAL_FX", "false").lower() == "true"
if USE_EXPERIMENTAL_FX:
    try:
        from app.strategies.fx_momentum_v2 import fx_momentum_features

        print("[AUTO_DECIDER] Using experimental FX Momentum v2")
    except ImportError:
        from app.strategies.fx_momentum import fx_momentum_features

        print("[AUTO_DECIDER] v2 import failed — reverted to stable FX Momentum")
else:
    from app.strategies.fx_momentum import fx_momentum_features

USE_EXPERIMENTAL_XAU = os.getenv("USE_EXPERIMENTAL_XAU", "false").lower() == "true"
if USE_EXPERIMENTAL_XAU:
    try:
        from app.strategies.xau_momentum_v2 import xau_momentum_features

        print("[AUTO_DECIDER] Using experimental XAU Momentum v2")
    except ImportError:
        from app.strategies.xau_momentum import xau_momentum_features

        print("[AUTO_DECIDER] v2 import failed — reverted to stable XAU Momentum")
else:
    from app.strategies.xau_momentum import xau_momentum_features

USE_EXPERIMENTAL_INDEX = os.getenv("USE_EXPERIMENTAL_INDEX", "false").lower() == "true"
if USE_EXPERIMENTAL_INDEX:
    try:
        from app.strategies.indices_momentum_v2 import indices_momentum_features

        print("[AUTO_DECIDER] Using experimental Indices Momentum v2")
    except ImportError:
        from app.strategies.indices_momentum import indices_momentum_features

        print("[AUTO_DECIDER] v2 import failed — reverted to stable Indices Momentum")
else:
    from app.strategies.indices_momentum import indices_momentum_features


# Indices remain stable (no v2 yet)


# -----------------------------
# Regime Classification (Dynamic)
# -----------------------------
def classify_regime(
    ema_fast: float,
    ema_slow: float,
    rsi: float,
    rsi_long_th: float = 55,
    rsi_short_th: float = 45,
) -> tuple[str, float, float]:
    """
    Return regime, position factor, and confidence.
    Dynamically adapts thresholds based on per-symbol RSI settings.
    """
    if ema_fast > ema_slow and rsi >= rsi_long_th:
        return "ALIGNED_BULL", 1.0, 1.0
    if ema_fast < ema_slow and rsi <= rsi_short_th:
        return "ALIGNED_BEAR", 1.0, 1.0
    if ema_fast < ema_slow and rsi >= rsi_long_th:
        return "MIXED_UP", 0.5, 0.6
    if ema_fast > ema_slow and rsi <= rsi_short_th:
        return "MIXED_DOWN", 0.5, 0.6
    return "NEUTRAL", 0.0, 0.0


# -----------------------------
# Guardrails for Mixed Signals
# -----------------------------
def validate_mixed_up(features: dict[str, Any]) -> dict[str, Any] | None:
    if features.get("structure_break_up") and features.get("pullback_holds_fastEMA_or_VWAP"):
        return {"side": "LONG", "note": "Mixed-Up HL confirmed"}
    if features.get("bearish_divergence") and features.get("level_rejection"):
        return {"side": "SHORT", "note": "Mixed-Up fade at resistance"}
    return None


def validate_mixed_down(features: dict[str, Any]) -> dict[str, Any] | None:
    if features.get("structure_break_down") and features.get("pullback_rejects_fastEMA_or_VWAP"):
        return {"side": "SHORT", "note": "Mixed-Down LH confirmed"}
    if features.get("bullish_divergence") and features.get("support_hold"):
        return {"side": "LONG", "note": "Mixed-Down fade at support"}
    return None


# -----------------------------
# Risk Adjustment
# -----------------------------
def adjust_risk(regime: str, sl_pips: float, tp_pips: float) -> tuple[float, float]:
    """
    Adjust stop-loss and take-profit depending on regime.
    Mixed trades tighten risk and reduce reward to account for uncertainty.
    """
    if regime == "MIXED_UP":
        return sl_pips * 1.1, tp_pips * 0.8
    if regime == "MIXED_DOWN":
        return sl_pips * 0.9, tp_pips * 0.7
    return sl_pips, tp_pips


# -----------------------------
# Mixed Fallback Decision
# -----------------------------
def mixed_fallback_decision(
    regime: str,
    ema_fast: float,
    ema_slow: float,
    rsi: float,
    rsi_long_th: float,
    rsi_short_th: float,
    eps: float,
    env: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Optional fallback for MIXED_* regimes when micro-structure features are absent.
    Trades small size if RSI is decisively extreme relative to the mixed side.
    Controlled by MIXED_FALLBACK=true in each asset env file.
    """
    if not env:
        return None

    allow_fallback = str(env.get("MIXED_FALLBACK", "false")).lower() == "true"
    if not allow_fallback:
        return None

    rsi_pad = float(env.get("MIXED_FALLBACK_RSI_PAD", 1.0))
    ema_gap_ok = float(env.get("MIXED_FALLBACK_EMA_GAP_OK", eps * 2))
    ema_gap = abs(ema_fast - ema_slow)

    if regime == "MIXED_DOWN":
        if rsi <= (rsi_short_th - rsi_pad) and ema_gap <= ema_gap_ok:
            return {"side": "SHORT", "note": "Mixed-Down fallback"}
    elif regime == "MIXED_UP":
        if rsi >= (rsi_long_th + rsi_pad) and ema_gap <= ema_gap_ok:
            return {"side": "LONG", "note": "Mixed-Up fallback"}

    return None


# -----------------------------
# SL/TP computation for indices
# -----------------------------
def compute_sl_tp(
    symbol: str, side: str, price: float, sl_pips: float, tp_pips: float
) -> tuple[float, float]:
    """
    Compute absolute SL/TP prices, handling 'index points' vs MT5 points automatically.
    """
    try:
        info = mt5.symbol_info(symbol)  # type: ignore[attr-defined]
        point = float(info.point if info else 0.01)
    except Exception:
        point = 0.01

    pip_mode = os.getenv("INDICES_PIP_MODE", "mt5_point").lower()
    if pip_mode == "index_point" and any(
        x in symbol.upper() for x in ["NAS", "US30", "GER", "SPX"]
    ):
        mult = 1.0
    else:
        mult = point

    if side.upper() == "LONG":
        sl = price - sl_pips * mult
        tp = price + tp_pips * mult
    else:
        sl = price + sl_pips * mult
        tp = price - tp_pips * mult

    logger.debug(
        "Computed SL/TP for %s [%s]: price=%.2f sl=%.2f tp=%.2f (mult=%.5f mode=%s)",
        symbol,
        side,
        price,
        sl,
        tp,
        mult,
        pip_mode,
    )

    return sl, tp


# -----------------------------
# Asset Classification
# -----------------------------
def _classify_asset(symbol: str, env: dict[str, Any] | None) -> str:
    """Lightweight asset-class classification."""
    s = symbol.upper()
    if env:
        cls = env.get("ASSET_CLASS", "")
        if isinstance(cls, str):
            cls = cls.upper().strip()
            if cls in {"FX", "XAU", "INDEX", "INDICES"}:
                return "INDEX" if cls == "INDICES" else cls
    if "XAU" in s or "GOLD" in s:
        return "XAU"
    if s in {"US30", "NAS100", "GER40", "SPX500"} or s.endswith(".S"):
        return "INDEX"
    if s.endswith(("USD", "JPY", "EUR", "GBP", "AUD", "NZD", "CHF", "CAD")) or "-ECNC" in s:
        return "FX"
    return "EQUITY"


# -----------------------------
# Main Decision
# -----------------------------
def decide_signal(
    symbol: str, timeframe: str = "H1", agent: str | None = None, env: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Route symbol to its strategy (features only), classify regime,
    and return normalized decision dict with side, SL/TP, confidence, and volume_factor.
    """
    try:
        cls = _classify_asset(symbol, env)
        logger.debug("Symbol=%s classified as %s", symbol, cls)

        df = get_rates_df(symbol, timeframe, 300)
        if df is None or df.empty:
            return {
                "accepted": False,
                "note": "no market data",
                "why": ["data frame empty or unavailable"],
            }

        # Fetch raw features
        if cls == "FX":
            raw = fx_momentum_features(symbol, timeframe, env or {})
        elif cls == "INDEX":
            raw = indices_momentum_features(symbol, timeframe, env or {})
        elif cls == "XAU":
            raw = xau_momentum_features(symbol, timeframe, env or {})
        else:
            raw = None

        if raw is None or not raw.get("accepted", False):
            return {
                "accepted": True,
                "preview": {
                    "side": "",
                    "note": "no_trade",
                    "why": ["no features"],
                    "confidence": 0.0,
                    "volume_factor": 0.0,
                    "debug": {},
                },
            }

        ema_fast = raw["ema_fast"]
        ema_slow = raw["ema_slow"]
        rsi = raw["rsi"]
        sl_pips = raw["params"]["sl_pips"]
        tp_pips = raw["params"]["tp_pips"]
        rsi_long_th = raw["params"]["rsi_long_th"]
        rsi_short_th = raw["params"]["rsi_short_th"]
        features = raw["features"]

        # --- Regime Classification (dynamic RSI thresholds) ---
        regime, pos_factor, conf = classify_regime(
            ema_fast, ema_slow, rsi, rsi_long_th, rsi_short_th
        )

        logger.info(
            "[DECIDE] %s regime=%s ema_fast=%.5f ema_slow=%.5f rsi=%.2f (th_long=%.1f th_short=%.1f)",
            symbol,
            regime,
            ema_fast,
            ema_slow,
            rsi,
            rsi_long_th,
            rsi_short_th,
        )

        preview: dict[str, Any] = {
            "side": "",
            "note": "no_trade",
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "why": ["neutral or guardrails not met"],
            "volume_factor": pos_factor,
            "confidence": conf,
            "debug": raw,
        }

        # --- Aligned Bull / Bear ---
        if regime in ("ALIGNED_BULL", "ALIGNED_BEAR"):
            side = "LONG" if regime == "ALIGNED_BULL" else "SHORT"
            sl_adj, tp_adj = adjust_risk(regime, sl_pips, tp_pips)
            preview.update(
                {
                    "side": side,
                    "note": regime,
                    "sl_pips": sl_adj,
                    "tp_pips": tp_adj,
                    "why": [regime],
                    "volume_factor": pos_factor,
                    "confidence": conf,
                }
            )
            # 💡 Diagnostic signal logging
            logger.info("[SIGNAL] %s detected %s regime -> %s trade", symbol, regime, side)

        # --- Mixed Up ---
        elif regime == "MIXED_UP":
            sig = validate_mixed_up(features)
            if not sig:
                sig = mixed_fallback_decision(
                    regime,
                    ema_fast,
                    ema_slow,
                    rsi,
                    rsi_long_th,
                    rsi_short_th,
                    raw["eps"],
                    env or {},
                )
            if sig:
                sl_adj, tp_adj = adjust_risk(regime, sl_pips, tp_pips)
                preview.update(
                    {
                        "side": sig["side"],
                        "note": sig["note"],
                        "sl_pips": sl_adj,
                        "tp_pips": tp_adj,
                        "why": [regime, sig["note"]],
                        "volume_factor": min(0.33, pos_factor),
                        "confidence": min(0.6, conf),
                    }
                )

        # --- Mixed Down ---
        elif regime == "MIXED_DOWN":
            sig = validate_mixed_down(features)
            if not sig:
                sig = mixed_fallback_decision(
                    regime,
                    ema_fast,
                    ema_slow,
                    rsi,
                    rsi_long_th,
                    rsi_short_th,
                    raw["eps"],
                    env or {},
                )
            if sig:
                sl_adj, tp_adj = adjust_risk(regime, sl_pips, tp_pips)
                preview.update(
                    {
                        "side": sig["side"],
                        "note": sig["note"],
                        "sl_pips": sl_adj,
                        "tp_pips": tp_adj,
                        "why": [regime, sig["note"]],
                        "volume_factor": min(0.33, pos_factor),
                        "confidence": min(0.6, conf),
                    }
                )

        return {"accepted": True, "preview": preview}

    except Exception as e:
        logger.exception("Error in decide_signal for %s", symbol)
        return {"accepted": False, "error": "strategy_error", "why": [f"{type(e).__name__}: {e}"]}
