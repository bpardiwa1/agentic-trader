# app/monitor/loss_monitor.py
from __future__ import annotations

import os
import time
from typing import Any

from app.brokers.mt5_client import get_positions, init_and_login
from app.exec.executor import close_all

_TRUE = {"1", "true", "yes", "on"}


# ----------------------------- Env helpers ------------------------------------
def _bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in _TRUE


def _f(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).split("#", 1)[0].strip())
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float((os.getenv(name) or str(default)).split("#", 1)[0].strip()))
    except Exception:
        return default


def _now_min() -> int:
    return int(time.time() // 60)


# ----------------------------- Cooldown ---------------------------------------
_COOLDOWN_MIN: int = _i("LOSS_MONITOR_COOLDOWN_MIN", 2)
_LAST_RUN_MIN: dict[str, int] = {}


# ----------------------------- Normalizers ------------------------------------
def _positions_as_dicts(raw: Any) -> list[dict[str, Any]]:
    """
    Normalize broker positions into list[dict]. Unknown shapes are ignored
    to avoid AttributeError when accessing .get().
    """
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    if isinstance(raw, dict):
        out.append(raw)
        return out
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.append(item)
        return out
    # Unexpected type -> ignore safely
    return out


def _sum_symbol_pnl(positions: list[dict[str, Any]], symbol: str) -> float:
    total = 0.0
    for pos in positions:
        if (pos.get("symbol") or "") == symbol:
            try:
                total += float(pos.get("profit", 0.0) or 0.0)
            except Exception:
                # ignore broken entries
                pass
    return total


def _offenders_by_per_trade_floor(
    positions: list[dict[str, Any]], per_trade_min: float
) -> list[dict[str, Any]]:
    """Return positions whose floating PnL <= per_trade_min."""
    offenders: list[dict[str, Any]] = []
    for pos in positions:
        try:
            profit = float(pos.get("profit", 0.0) or 0.0)
        except Exception:
            continue
        if profit <= per_trade_min:
            offenders.append(pos)
    return offenders


# ----------------------------- Main -------------------------------------------
def monitor_and_close(symbols: list[str]) -> dict[str, Any]:
    """
    Enforce loss guardrails and optionally close positions.

    Env controls:
      LOSS_ENABLE (bool)                        -> default: true
      LOSS_MAX_PER_TRADE  (float; negative)     -> e.g. -15.0 means close any trade below -15
      LOSS_MAX_PER_SYMBOL (float; negative)     -> e.g. -40.0 means close all positions for symbol if sum < -40
      LOSS_CLOSE_MODE ("ticket"|"symbol")       -> how to close when a guard trips (default: "symbol")
      LOSS_MONITOR_COOLDOWN_MIN (int)           -> skip checks if run too recently (per symbol)
    """
    if not _bool("LOSS_ENABLE", True):
        return {"ok": True, "note": "disabled", "actions": [], "inspected": []}

    per_trade_min = _f("LOSS_MAX_PER_TRADE", float("-inf"))
    per_symbol_min = _f("LOSS_MAX_PER_SYMBOL", float("-inf"))

    close_mode = (os.getenv("LOSS_CLOSE_MODE") or "symbol").strip().lower()
    if close_mode not in ("symbol", "ticket"):
        close_mode = "symbol"

    # Prepare broker session
    try:
        init_and_login()
    except Exception:
        # non-fatal; downstream calls will surface errors if any
        pass

    actions: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []

    for symbol in symbols:
        now_min = _now_min()
        last_min = _LAST_RUN_MIN.get(symbol, 0)
        if now_min - last_min < _COOLDOWN_MIN:
            inspected.append({"symbol": symbol, "skip": "cooldown"})
            continue

        # fetch positions
        try:
            raw_positions = get_positions(symbol)
        except Exception as exc:
            inspected.append({"symbol": symbol, "error": f"positions_error:{exc}"})
            _LAST_RUN_MIN[symbol] = now_min
            continue

        positions = _positions_as_dicts(raw_positions)
        if not positions:
            inspected.append({"symbol": symbol, "positions": 0})
            _LAST_RUN_MIN[symbol] = now_min
            continue

        # --- per-trade guard ---
        offending_positions: list[dict[str, Any]] = []
        if per_trade_min != float("-inf"):
            offending_positions = _offenders_by_per_trade_floor(positions, per_trade_min)

        # --- per-symbol guard ---
        symbol_sum = _sum_symbol_pnl(positions, symbol)
        symbol_breached = per_symbol_min != float("-inf") and symbol_sum <= per_symbol_min

        # --- decide closures ---
        if offending_positions or symbol_breached:
            if close_mode == "ticket" and offending_positions:
                # Close each offending ticket individually
                for pos in offending_positions:
                    ticket_val = pos.get("ticket")
                    try:
                        ticket = int(ticket_val) if ticket_val is not None else None
                    except Exception:
                        ticket = None
                    if ticket is None:
                        continue
                    result = close_all(ticket=ticket)
                    actions.append(
                        {
                            "symbol": symbol,
                            "mode": "ticket",
                            "ticket": ticket,
                            "reason": f"per_trade <= {per_trade_min}",
                            "result": result,
                        }
                    )
            else:
                # Close the whole symbol
                reasons: list[str] = []
                if offending_positions and per_trade_min != float("-inf"):
                    reasons.append(f"per_trade <= {per_trade_min}")
                if symbol_breached:
                    reasons.append(f"per_symbol_sum <= {per_symbol_min}")
                result = close_all(symbol=symbol)
                actions.append(
                    {
                        "symbol": symbol,
                        "mode": "symbol",
                        "reason": ", ".join(reasons) if reasons else "guard breach",
                        "result": result,
                    }
                )

        inspected.append(
            {
                "symbol": symbol,
                "positions": len(positions),
                "sum_profit": symbol_sum,
                "per_trade_min": per_trade_min,
                "per_symbol_min": per_symbol_min,
                "offenders": [
                    int(p.get("ticket"))
                    for p in offending_positions
                    if p.get("ticket") is not None
                ],
                "symbol_breached": symbol_breached,
            }
        )

        _LAST_RUN_MIN[symbol] = now_min

    return {
        "ok": True,
        "actions": actions,
        "inspected": inspected,
        "cooldown_min": _COOLDOWN_MIN,
    }
