import os
import re
from typing import Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel

from app.agents.auto_decider import decide_signal
from app.exec.executor import execute_market_order as execute_order
from app.risk.guards import risk_guard

from . import config


# --------- Schemas ---------
class MarketOrder(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT", "BUY", "SELL"]
    price: float | None = None
    volume: float | None = None
    size: float | None = None
    sl_pips: float | None = None
    tp_pips: float | None = None
    comment: str | None = None


app = FastAPI(title="Agentic Trader Universal")


# --------- Helpers ---------
def _lots_for(symbol: str, default_lots: float = 0.01) -> float:
    key = "LOTS_" + re.sub(r"[^A-Z0-9]+", "_", symbol.upper())
    try:
        return float(os.environ.get(key, str(default_lots)).split("#", 1)[0].strip())
    except Exception:
        return default_lots


def _default_lots() -> float:
    try:
        return float(
            os.environ.get("MT5_DEFAULT_LOTS", "0.01").split("#", 1)[0].strip()
        )
    except Exception:
        return 0.01


# --------- Endpoints ---------
@app.get("/health")
def health():
    return {"ok": True, "mode": config.EXECUTION_MODE, "backend": config.BROKER_BACKEND}


@app.get("/agents/decide")
def agents_decide(
    symbol: str,
    tf: str = Query("H1", alias="tf"),
    agent: str = "auto",
    execute: bool = Query(False, alias="execute"),
):
    """
    Preview or execute a decision for `symbol` on timeframe `tf`.
    Uses strategy unless STRATEGY_BYPASS=true is set in .env
    """
    try:
        if os.getenv("STRATEGY_BYPASS", "false").lower() == "true":
            # ENV bypass mode
            side = (os.getenv("BYPASS_SIDE", "LONG") or "LONG").upper()
            size = float(os.getenv("BYPASS_SIZE", _default_lots()))
            sl_pips = float(os.getenv("BYPASS_SL_PIPS", "300"))
            tp_pips = float(os.getenv("BYPASS_TP_PIPS", "600"))
            entry = None
            note = "bypass"
        else:
            # Normal strategy
            sig = decide_signal(symbol=symbol, timeframe=tf, agent=agent) or {}
            side = (sig.get("side") or "").upper()
            size = sig.get("size")
            sl_pips = sig.get("sl_pips")
            tp_pips = sig.get("tp_pips")
            entry = sig.get("entry")
            note = sig.get("note") or sig.get("reason") or agent
    except Exception as e:
        return {"accepted": False, "error": f"strategy_error: {e}"}

    if side not in ("LONG", "SHORT"):
        return {"accepted": False, "note": "no trade signal"}

    # Position sizing
    lots = _lots_for(symbol, _default_lots())
    if size is None:
        size = lots

    preview = {
        "symbol": symbol,
        "side": side,
        "size": float(size),
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "entry": entry,
        "timeframe": tf,
        "agent": agent,
        "note": note,
    }

    if not execute:
        return {"accepted": True, "preview": preview, "note": note}

    # Guardrails
    guard = risk_guard(symbol, side, sl_pips)
    if not guard["accepted"]:
        return {"accepted": False, "note": guard["note"], "preview": preview}

    # Execute
    try:
        order_res = execute_order(
            symbol=symbol,
            side=side,
            volume=float(size),
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            comment=f"{agent}:{note}",
        )
        return {"accepted": True, "order": order_res, "note": note}
    except Exception as e:
        return {
            "accepted": True,
            "order": {"status": "error", "error": f"execution_error: {e}"},
            "note": note,
        }


@app.post("/agents/force")
def agents_force(order: MarketOrder):
    """
    Force one trade bypassing strategy, but still applies guardrails.
    Example:
      { "symbol":"XAUUSD-ECNc","side":"LONG","sl_pips":300,"tp_pips":600,"volume":0.2 }
    """
    side = (order.side or "").upper()
    if side in ("LONG", "BUY"):
        norm_side = "LONG"
    elif side in ("SHORT", "SELL"):
        norm_side = "SHORT"
    else:
        return {"accepted": False, "error": "invalid_side"}

    size = order.volume or order.size or _lots_for(order.symbol, _default_lots())
    sl_pips = order.sl_pips
    tp_pips = order.tp_pips

    guard = risk_guard(order.symbol, norm_side, sl_pips)
    if not guard["accepted"]:
        return {"accepted": False, "note": guard["note"]}

    res = execute_order(
        symbol=order.symbol,
        side=norm_side,
        volume=float(size),
        sl_pips=sl_pips,
        tp_pips=tp_pips,
        comment=order.comment or "force",
    )
    return {"accepted": True, "order": res, "note": "force"}


@app.post("/orders/market")
def orders_market(order: MarketOrder):
    """Direct manual order (no guardrails)."""
    side = (order.side or "").upper()
    if side == "LONG":
        side = "BUY"
    elif side == "SHORT":
        side = "SELL"

    lot = order.volume or order.size or _default_lots()

    res = execute_order(
        symbol=order.symbol,
        side=side,
        volume=float(lot),
        sl_pips=order.sl_pips,
        tp_pips=order.tp_pips,
        comment=order.comment or "manual",
    )
    return res
