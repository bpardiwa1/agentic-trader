# app/strategies/fx_momentum.py
from __future__ import annotations

import os
from typing import Any

import MetaTrader5 as mt5
import pandas as pd


# ---------- env helpers ----------
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).split("#", 1)[0].strip())
    except:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).split("#", 1)[0].strip())
    except:
        return default


# ---------- params (FX) ----------
EMA_FAST = _env_int("MOMENTUM_FX_EMA_FAST", 50)
EMA_SLOW = _env_int("MOMENTUM_FX_EMA_SLOW", 200)
RSI_PERIOD = _env_int("MOMENTUM_FX_RSI_PERIOD", 14)
ATR_PERIOD = _env_int("MOMENTUM_FX_ATR_PERIOD", 14)
RSI_LONG_TH = _env_float("MOMENTUM_FX_RSI_LONG_TH", 55.0)
RSI_SHORT_TH = _env_float("MOMENTUM_FX_RSI_SHORT_TH", 45.0)
MIN_ATR_FX = _env_float("MOMENTUM_FX_MIN_ATR", 0.0)  # 0 to disable

_TF = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def _tf(tf: str) -> int:
    return _TF.get((tf or "M15").upper(), mt5.TIMEFRAME_M15)


# ---------- basic indicators ----------
def _rates(symbol: str, tf: str, n=300):
    r = mt5.copy_rates_from_pos(symbol, _tf(tf), 0, max(EMA_SLOW + 5, n, 220))
    if r is None or len(r) == 0:
        return None
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, p=14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    ag = g.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    al = l.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    rs = ag / (al + 1e-12)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, p=14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / p, adjust=False).mean()


# ---------- strategy ----------
def signal(symbol: str, timeframe: str = "M15") -> dict[str, Any] | None:
    df = _rates(symbol, timeframe, 300)
    if df is None or len(df) < max(EMA_SLOW + 5, 220):
        return {
            "side": None,
            "note": "no trade",
            "debug": {
                "reason": "no_data_or_too_short",
                "len": (0 if df is None else len(df)),
                "tf": timeframe,
            },
            "why": ["insufficient candles for indicators"],
        }

    df["ema_fast"] = _ema(df["close"], EMA_FAST)
    df["ema_slow"] = _ema(df["close"], EMA_SLOW)
    df["rsi14"] = _rsi(df["close"], RSI_PERIOD)
    df["atr14"] = _atr(df, ATR_PERIOD)

    last = df.iloc[-1]
    price = float(last["close"])
    ema_f = float(last["ema_fast"])
    ema_s = float(last["ema_slow"])
    rsi = float(last["rsi14"])
    atr = float(last["atr14"])

    debug = {
        "price": price,
        "ema_fast": ema_f,
        "ema_slow": ema_s,
        "rsi14": rsi,
        "atr14": atr,
        "tf": timeframe,
        "config": {
            "EMA_FAST": EMA_FAST,
            "EMA_SLOW": EMA_SLOW,
            "RSI_PERIOD": RSI_PERIOD,
            "ATR_PERIOD": ATR_PERIOD,
            "RSI_LONG_TH": RSI_LONG_TH,
            "RSI_SHORT_TH": RSI_SHORT_TH,
            "MIN_ATR_FX": MIN_ATR_FX,
        },
    }

    # quiet market gate
    if MIN_ATR_FX > 0 and atr < MIN_ATR_FX:
        return {
            "side": None,
            "note": "no trade",
            "debug": debug,
            "why": [f"ATR {atr:.6f} < MIN_ATR_FX {MIN_ATR_FX}"],
        }

    long_ok = (ema_f > ema_s) and (rsi > RSI_LONG_TH)
    short_ok = (ema_f < ema_s) and (rsi < RSI_SHORT_TH)

    if long_ok:
        return {
            "side": "LONG",
            "sl_pips": 30,
            "tp_pips": 60,
            "entry": price,
            "note": "fx_momentum",
            "debug": debug,
            "why": ["LONG conditions met (EMA_FAST>EMA_SLOW and RSI>LONG_TH)"],
        }
    if short_ok:
        return {
            "side": "SHORT",
            "sl_pips": 30,
            "tp_pips": 60,
            "entry": price,
            "note": "fx_momentum",
            "debug": debug,
            "why": ["SHORT conditions met (EMA_FAST<EMA_SLOW and RSI<SHORT_TH)"],
        }

    why = []
    if not (ema_f > ema_s):
        why.append("EMA_FAST<=EMA_SLOW (no up-trend)")
    if not (rsi > RSI_LONG_TH):
        why.append(f"RSI {rsi:.2f} <= LONG_TH {RSI_LONG_TH}")
    if not (ema_f < ema_s):
        why.append("EMA_FAST>=EMA_SLOW (no down-trend)")
    if not (rsi < RSI_SHORT_TH):
        why.append(f"RSI {rsi:.2f} >= SHORT_TH {RSI_SHORT_TH}")
    return {"side": None, "note": "no trade", "debug": debug, "why": why}
