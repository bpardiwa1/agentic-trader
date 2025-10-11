# app/exec/executor.py
from __future__ import annotations

from typing import Any, cast

import MetaTrader5 as _mt5

from .executor_mt5 import (
    compute_sl_tp_prices as calc_sl_tp_from_pips,
)
from .executor_mt5 import (
    place_market_order as place_order,
)

# Cast MT5 to Any to silence Pylance on dynamic attrs
mt5: Any = cast(Any, _mt5)

# Alphabetical order to satisfy Ruff
__all__ = ["calc_sl_tp_from_pips", "close_all", "execute_market_order", "place_order"]


def execute_market_order(
    symbol: str,
    side: str,
    volume: float,
    price_hint: float | None = None,
    sl_pips: float | None = None,
    tp_pips: float | None = None,
    comment: str = "",
) -> dict[str, Any]:
    """Compatibility wrapper around place_order with simple side normalization."""
    norm_side = (side or "").upper().replace("BUY", "LONG").replace("SELL", "SHORT")
    return place_order(
        symbol=symbol,
        side=norm_side,
        lots=float(volume),
        sl_pips=float(sl_pips or 0.0),
        tp_pips=float(tp_pips or 0.0),
        comment=comment,
        entry_override=price_hint,
    )


def close_all(symbol: str | None = None, volume: float | None = None) -> dict[str, Any]:
    """
    Close all open positions (optionally only for a symbol).
    Uses MT5 DEAL actions directly. Returns a summary with per-trade reports.
    """
    if symbol:
        info = mt5.symbol_info(symbol)
        if info is None or not getattr(info, "visible", True):
            mt5.symbol_select(symbol, True)

    pos_list = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not pos_list:
        return {"closed": 0, "reports": [], "message": "no open positions"}

    closed = 0
    reports: list[dict[str, Any]] = []

    for p in pos_list:
        sym = p.symbol
        vol_to_close = float(volume or p.volume)
        is_buy = int(getattr(p, "type", 0)) == getattr(mt5, "POSITION_TYPE_BUY", 0)
        order_type = (
            getattr(mt5, "ORDER_TYPE_SELL", 1) if is_buy else getattr(mt5, "ORDER_TYPE_BUY", 0)
        )

        tick = mt5.symbol_info_tick(sym)
        if not tick:
            reports.append(
                {"symbol": sym, "ticket": int(p.ticket), "status": "error", "error": "no_tick"}
            )
            continue

        price = (
            float(tick.bid) if order_type == getattr(mt5, "ORDER_TYPE_SELL", 1) else float(tick.ask)
        )

        req = {
            "action": getattr(mt5, "TRADE_ACTION_DEAL", 1),
            "symbol": sym,
            "position": int(p.ticket),
            "volume": vol_to_close,
            "type": order_type,
            "price": price,
            "deviation": 50,
            "comment": "close_all",
            "type_filling": getattr(mt5, "ORDER_FILLING_IOC", 1),
        }

        res = mt5.order_send(req)
        ok = bool(
            res and int(getattr(res, "retcode", 0)) == getattr(mt5, "TRADE_RETCODE_DONE", 10009)
        )

        reports.append(
            {
                "symbol": sym,
                "ticket": int(p.ticket),
                "status": "ok" if ok else "error",
                "retcode": int(getattr(res, "retcode", 0)) if res else None,
                "comment": getattr(res, "comment", "") if res else "",
            }
        )
        if ok:
            closed += 1

    return {"closed": closed, "reports": reports}
