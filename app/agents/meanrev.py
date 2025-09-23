# app/agents/meanrev.py

from __future__ import annotations
from typing import Any

# Tunable RSI thresholds for mean reversion strategy
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


def propose(symbol: str, price: float, ctx: dict[str, Any]) -> dict[str, Any] | None:
    rsi = ctx.get("rsi14", 50)
    atr = ctx.get("atr", 0.001)
    price = float(ctx.get("price", 0.0) or price)

    if rsi > RSI_OVERBOUGHT:
        side = "SHORT"
    elif rsi < RSI_OVERSOLD:
        side = "LONG"
    else:
        return None

    entry = price
    sl = entry + 2 * atr if side == "SHORT" else entry - 2 * atr
    tp = entry - 4 * atr if side == "SHORT" else entry + 4 * atr

    return {
        "strategy_id": "meanrev",
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "confidence": 0.6,
    }
