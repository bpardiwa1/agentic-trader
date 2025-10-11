# app/strategies/xau_momentum.py
from __future__ import annotations
import os
from typing import Any, Optional
import pandas as pd
from app.market.data import compute_context

_TRUE = {"1", "true", "yes", "on"}

def _env_int(name: str, default: int) -> int:
    try: return int(float((os.getenv(name) or str(default)).split("#", 1)[0].strip()))
    except Exception: return default

def _env_float(name: str, default: float) -> float:
    try: return float((os.getenv(name) or str(default)).split("#", 1)[0].strip())
    except Exception: return default

def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in _TRUE

def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def _rsi(series: pd.Series, p: int = 14) -> pd.Series:
    d = series.diff()
    g = d.clip(lower=0.0); l = (-d).clip(lower=0.0)
    ag = g.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    al = l.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    rs = ag / (al + 1e-12)
    return 100.0 - (100.0 / (1.0 + rs))

def _atr(df: pd.DataFrame, period: int = 14) -> float:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def xau_momentum_signal(symbol: str, timeframe: str, df: pd.DataFrame) -> Optional[dict[str, Any]]:
    if df is None or df.empty or "close" not in df.columns:
        return None

    ema_fast_n = _env_int("MOMENTUM_XAU_EMA_FAST", 50)
    ema_slow_n = _env_int("MOMENTUM_XAU_EMA_SLOW", 200)
    rsi_p      = _env_int("MOMENTUM_XAU_RSI_PERIOD", 14)
    long_th    = _env_int("MOMENTUM_XAU_RSI_LONG_TH", 58)
    short_th   = _env_int("MOMENTUM_XAU_RSI_SHORT_TH", 42)
    eps        = _env_float("MOMENTUM_XAU_EPS", 0.6)
    min_atr    = _env_float("MOMENTUM_XAU_MIN_ATR", 2.5)

    close = df["close"].astype(float)
    if len(close) < max(ema_slow_n, ema_fast_n, rsi_p) + 5:
        return None

    ema_fast = _ema(close, ema_fast_n)
    ema_slow = _ema(close, ema_slow_n)
    rsi = _rsi(close, rsi_p)

    price = float(close.iloc[-1]); ef = float(ema_fast.iloc[-1]); es = float(ema_slow.iloc[-1]); r = float(rsi.iloc[-1])
    atr14 = _atr(df, 14)

    # ATR floor
    if not pd.isna(atr14) and atr14 < min_atr:
        return {"side":"", "note":"no_trade", "debug":{"price":price,"ema_fast":ef,"ema_slow":es,"rsi":r,"eps":eps,"atr14":atr14},
                "why":[f"ATR {atr14:.2f} < {min_atr}"]}

    # HTF (H1) confirmation
    ctx = compute_context(symbol, "H1", 300)
    regime = ctx["regime"] if ctx.get("ok") else "UNKNOWN"

    long_ok  = (price > max(ef, es) + eps) and (r > long_th)  and (regime == "TRENDING_UP")
    short_ok = (price < min(ef, es) - eps) and (r < short_th) and (regime == "TRENDING_DOWN")

    sl_pp = _env_float("MOMENTUM_XAU_SL_PIPS", 300)
    tp_pp = _env_float("MOMENTUM_XAU_TP_PIPS", 450)

    if long_ok:
        return {"side":"LONG","entry":price,"sl_pips":sl_pp,"tp_pips":tp_pp,"note":"xau_momentum",
                "debug":{"price":price,"ema_fast":ef,"ema_slow":es,"rsi":r,"eps":eps,"atr14":atr14,"regime":regime}}
    if short_ok:
        return {"side":"SHORT","entry":price,"sl_pips":sl_pp,"tp_pips":tp_pp,"note":"xau_momentum",
                "debug":{"price":price,"ema_fast":ef,"ema_slow":es,"rsi":r,"eps":eps,"atr14":atr14,"regime":regime}}

    return {"side":"","note":"no_trade",
            "debug":{"price":price,"ema_fast":ef,"ema_slow":es,"rsi":r,"eps":eps,"atr14":atr14,"regime":regime},
            "why":["conditions not met or HTF not aligned"]}
