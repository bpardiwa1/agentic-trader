import os
from . import config
from .schemas import Signal
from .util.pricing import normalize_symbol_key
import MetaTrader5 as mt5

def per_symbol_lot(symbol: str) -> float:
    key = f"LOTS_{normalize_symbol_key(symbol)}"
    v = os.environ.get(key, None)
    if v is None:
        return float(getattr(config, "MT5_DEFAULT_LOTS", 0.01))
    try:
        return float(v)
    except Exception:
        return float(getattr(config, "MT5_DEFAULT_LOTS", 0.01))

def _account_equity_default() -> float:
    try:
        ai = mt5.account_info()
        if ai and getattr(ai, "equity", None) is not None:
            return float(ai.equity)
    except Exception:
        pass
    return float(os.environ.get("ACCOUNT_EQUITY", "10000"))

def _pip_size(symbol: str) -> float:
    s = (symbol or "").upper()
    if "XAU" in s: return 0.1
    si = mt5.symbol_info(symbol)
    if si and si.digits and si.digits >= 5: return 0.0001
    return (si.point * 10.0) if si else 0.0001

def size_from_risk(symbol: str, price: float, sl_price: float, risk_pct: float = None) -> float:
    if risk_pct is None:
        try:
            risk_pct = float(os.environ.get("RISK_PCT", "0.01"))
        except Exception:
            risk_pct = 0.01

    eq = _account_equity_default()
    min_lot = float(os.environ.get("MIN_LOT", "0.01"))
    max_lot = float(os.environ.get("MAX_LOT", "1.0"))

    if not price or not sl_price or price == sl_price:
        return max(min_lot, min(per_symbol_lot(symbol), max_lot))

    stop_dist = abs(price - sl_price)  # in price units
    pip = _pip_size(symbol)
    if pip <= 0: return max(min_lot, min(per_symbol_lot(symbol), max_lot))

    risk_amt = eq * risk_pct
    if stop_dist <= 0: return max(min_lot, min(per_symbol_lot(symbol), max_lot))
    lots = risk_amt / max(stop_dist / pip, 1e-9)

    return max(min_lot, min(lots, max_lot))

def risk_manager(sig: Signal):
    try:
        sl = sig.sl
        if not sl and hasattr(sig, "sl_pips") and sig.sl_pips:
            tick = mt5.symbol_info_tick(sig.symbol)
            if tick:
                entry = sig.entry or (tick.ask if (sig.side.upper()=="LONG") else tick.bid)
                pip = _pip_size(sig.symbol)
                delta = pip * float(sig.sl_pips)
                sl = entry - delta if sig.side.upper()=="LONG" else entry + delta

        entry_price = sig.entry or (mt5.symbol_info_tick(sig.symbol).ask if sig.side.upper()=="LONG" else mt5.symbol_info_tick(sig.symbol).bid)
        if not entry_price: return ({"error": "no_price"}, "no entry price")
        size = size_from_risk(sig.symbol, entry_price, sl or entry_price, None)

        return ({
            "symbol": sig.symbol,
            "side": sig.side,
            "entry": sig.entry,
            "sl": sig.sl,
            "tp": sig.tp,
            "size": size,
        }, None)
    except Exception as e:
        return (None, str(e))
