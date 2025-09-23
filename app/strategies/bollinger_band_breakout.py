import os

import numpy as np
import pandas as pd

from app.market.data import get_rates
from app.util.ta import atr


def _envf(name, dflt):  # float env
    try:
        return float(os.getenv(name, str(dflt)).split("#", 1)[0].strip())
    except:
        return dflt


def _envi(name, dflt):  # int env
    try:
        return int(float(os.getenv(name, str(dflt)).split("#", 1)[0].strip()))
    except:
        return dflt


def bollinger_breakout_signal(symbol: str, timeframe: str = "M15") -> dict:
    # Tunables (env)
    P = _envi("BB_PERIOD", 20)
    K = _envf("BB_K", 2.0)
    MIN_ATR = _envf("BB_MIN_ATR", 0.0)  # gate quiet markets (0 = off)
    LOOKBACK_CONFIRM = _envi(
        "BB_LOOKBACK_CONFIRM", 1
    )  # require close outside band within N bars
    SL_MULT_ATR = _envf("BB_SL_ATR_MULT", 1.5)
    TP_MULT_ATR = _envf("BB_TP_ATR_MULT", 3.0)

    df = get_rates(symbol, timeframe, count=max(300, P + 50))
    if df is None or df.empty:
        return {"debug": {"len": 0}, "why": ["no data"]}

    closes = df["close"].to_numpy(float)
    highs = df["high"].to_numpy(float)
    lows = df["low"].to_numpy(float)

    ma = pd.Series(closes).rolling(P).mean().to_numpy()
    sd = pd.Series(closes).rolling(P).std(ddof=0).to_numpy()
    upper = ma + K * sd
    lower = ma - K * sd

    # ATR for SL/TP sizing & market filter
    atr14 = atr(highs, lows, closes, 14)
    a = float(atr14[-1]) if not np.isnan(atr14[-1]) else None

    price = float(closes[-1])
    u = float(upper[-1]) if not np.isnan(upper[-1]) else None
    l = float(lower[-1]) if not np.isnan(lower[-1]) else None

    debug = {
        "price": price,
        "ma": float(ma[-1]) if not np.isnan(ma[-1]) else None,
        "upper": u,
        "lower": l,
        "atr": a,
        "tf": timeframe,
        "cfg": dict(
            P=P,
            K=K,
            MIN_ATR=MIN_ATR,
            LOOKBACK_CONFIRM=LOOKBACK_CONFIRM,
            SL_MULT_ATR=SL_MULT_ATR,
            TP_MULT_ATR=TP_MULT_ATR,
        ),
    }

    why = []
    if a is None:
        why.append("atr_nan")
    if MIN_ATR > 0 and (a is None or a < MIN_ATR):
        why.append(f"ATR<{MIN_ATR}")

    # “Breakout” definition: a recent close beyond band, and current price still aligned
    recent_closes = closes[-LOOKBACK_CONFIRM - 1 :]
    recent_upper = upper[-LOOKBACK_CONFIRM - 1 :]
    recent_lower = lower[-LOOKBACK_CONFIRM - 1 :]

    long_ok = np.any(recent_closes > recent_upper) and (price >= u if u else False)
    short_ok = np.any(recent_closes < recent_lower) and (price <= l if l else False)

    if long_ok and not why:
        sl_pips = None  # we set SL/TP in price terms; executor expects pips so we keep strategy SL/TP null
        tp_pips = None
        # We still pass note; executor or sizing can use ATR
        return {
            "side": "LONG",
            "size": None,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "entry": price,
            "note": "bb_breakout_up",
            "debug": debug,
        }

    if short_ok and not why:
        return {
            "side": "SHORT",
            "size": None,
            "sl_pips": None,
            "tp_pips": None,
            "entry": price,
            "note": "bb_breakout_down",
            "debug": debug,
        }

    if not long_ok and not short_ok:
        why.append("no breakout")
    return {"debug": debug, "why": why}
