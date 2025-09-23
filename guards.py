# app/risk/guards.py
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from app.brokers.mt5_client import get_account_info, get_positions


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).split("#", 1)[0].strip())
    except:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).split("#", 1)[0].strip())
    except:
        return default


def risk_guard(
    symbol: str, side: str, sl_pips: float | None = None
) -> dict[str, Any]:
    """
    Central guardrail logic. Returns dict with 'accepted': bool and 'note': str.
    """
    # ---- exposure caps ----
    max_sym = _env_int("MAX_TRADES_PER_SYMBOL", 2)
    max_all = _env_int("MAX_OPEN_POSITIONS", 6)

    pos_all = get_positions(None)
    pos_sym = get_positions(symbol)

    if len(pos_sym) >= max_sym:
        return {
            "accepted": False,
            "note": f"{symbol} per-symbol cap reached ({max_sym})",
        }
    if len(pos_all) >= max_all:
        return {"accepted": False, "note": f"global cap reached ({max_all})"}

    # ---- same-side cooldown ----
    block_same = (
        os.environ.get("AGENT_BLOCK_SAME_SIDE", "false").lower().strip() == "true"
    )
    cool_min = _env_int("SAME_SIDE_COOLDOWN_MIN", _env_int("AGENT_COOLDOWN_MIN", 0))
    if block_same and side in ("LONG", "SHORT"):
        want_buy = side == "LONG"
        same_side_pos = []
        for p in pos_sym:
            ps = str(p.get("side") or p.get("type"))
            is_buy = ps.upper() == "BUY" or ps == "0"
            if is_buy == want_buy:
                same_side_pos.append(p)
        if same_side_pos:
            if cool_min <= 0:
                return {"accepted": False, "note": f"{symbol} same-side open; skipping"}
            newest = max(
                (p.get("time_msc") or p.get("time") or 0) for p in same_side_pos
            )
            if newest > 10**12:
                newest = newest / 1000.0
            last_dt = datetime.fromtimestamp(float(newest), tz=UTC)
            if datetime.now(UTC) - last_dt < timedelta(minutes=cool_min):
                return {
                    "accepted": False,
                    "note": f"{symbol} same-side cooldown active",
                }

    # ---- floating PnL guard ----
    min_symbol_pnl = _env_float("MIN_SYMBOL_FLOATING_PNL", -9999)
    try:
        floating = sum(float(p.get("profit", 0)) for p in pos_sym)
    except Exception:
        floating = 0.0
    if floating < min_symbol_pnl:
        return {
            "accepted": False,
            "note": f"{symbol} floating PnL {floating:.2f} < {min_symbol_pnl}",
        }

    # ---- equity floor / daily loss ----
    equity_floor = _env_float("EQUITY_FLOOR", 0.0)
    daily_loss_limit = _env_float("DAILY_LOSS_LIMIT", 0.0)
    acct = get_account_info() or {}
    equity = float(acct.get("equity", 0))
    balance = float(acct.get("balance", 0))

    if equity_floor > 0 and equity < equity_floor:
        return {
            "accepted": False,
            "note": f"equity {equity:.2f} < floor {equity_floor}",
        }
    if daily_loss_limit > 0 and (balance - equity) > daily_loss_limit:
        return {
            "accepted": False,
            "note": f"daily loss {balance - equity:.2f} > limit {daily_loss_limit}",
        }

    return {"accepted": True, "note": "ok"}
