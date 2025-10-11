# app/exec/executor.py
# Unified exporter: use the robust MT5 executor everywhere
from .executor_mt5 import (
    compute_sl_tp_prices as calc_sl_tp_from_pips,  # keep old name for compatibility
    place_market_order as place_order,
)

# Compatibility wrapper
def execute_market_order(symbol: str, side: str, volume: float, price_hint=None, sl_pips=None, tp_pips=None, comment: str = ""):
    side = (side or "").upper().replace("BUY", "LONG").replace("SELL", "SHORT")
    return place_order(symbol, side, float(volume), float(sl_pips or 0.0), float(tp_pips or 0.0), comment, entry_override=price_hint)

# Close-all passthrough
import MetaTrader5 as mt5
def close_all(symbol: str | None = None, volume: float | None = None) -> dict:
    if symbol:
        info = mt5.symbol_info(symbol)
        if info is None or not info.visible:
            mt5.symbol_select(symbol, True)
    pos_list = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not pos_list: return {"closed": 0, "reports": [], "message": "no open positions"}
    closed, reports = 0, []
    for p in pos_list:
        sym = p.symbol; vol_to_close = float(volume or p.volume)
        order_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            reports.append({"symbol": sym, "ticket": p.ticket, "status": "error", "error": "no_tick"}); continue
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "position": p.ticket, "volume": vol_to_close,
               "type": order_type, "price": price, "deviation": 50, "comment": "close_all", "type_filling": mt5.ORDER_FILLING_IOC}
        res = mt5.order_send(req); ok = bool(res and res.retcode == mt5.TRADE_RETCODE_DONE)
        reports.append({"symbol": sym, "ticket": p.ticket, "status": "ok" if ok else "error",
                        "retcode": getattr(res, "retcode", None), "comment": getattr(res, "comment", "")})
        if ok: closed += 1
    return {"closed": closed, "reports": reports}
