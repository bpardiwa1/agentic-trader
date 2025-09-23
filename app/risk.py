import os

from . import config
from .schemas import Signal
from .util.pricing import normalize_symbol_key


def per_symbol_lot(symbol: str) -> float:
    key = f"LOTS_{normalize_symbol_key(symbol)}"
    v = os.environ.get(key, None)
    if v is None:
        return float(config.MT5_DEFAULT_LOTS)
    try:
        return float(v)
    except Exception:
        return float(config.MT5_DEFAULT_LOTS)


def size_from_risk(
    symbol: str, price: float, sl: float, risk_pct: float = 0.5
) -> float:
    return per_symbol_lot(symbol)


def risk_manager(sig: Signal):
    try:
        size = size_from_risk(sig.symbol, sig.entry, sig.sl)
        return (
            {
                "symbol": sig.symbol,
                "side": sig.side,
                "entry": sig.entry,
                "sl": sig.sl,
                "tp": sig.tp,
                "size": size,
            },
            None,
        )
    except Exception as e:
        return (None, str(e))
