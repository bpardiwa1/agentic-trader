# app/strategies/momentum.py
from __future__ import annotations

import os
from typing import Any, Optional, Tuple

import pandas as pd


# ----------------------------
# small env helpers
# ----------------------------
_TRUE = {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(float((os.getenv(name) or str(default)).split("#", 1)[0].strip()))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).split("#", 1)[0].strip())
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in _TRUE


# ----------------------------
# core indicators (pandas)
# ----------------------------
def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _rsi(series: pd.Series, p: int = 14) -> pd.Series:
    d = series.diff()
    g = d.clip(lower=0.0)
    l = (-d).clip(lower=0.0)
    ag = g.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    al = l.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    rs = ag / (al + 1e-12)
    return 100.0 - (100.0 / (1.0 + rs))


# ----------------------------
# strategy (FX)
# ----------------------------
def momentum_signal(symbol: str, timeframe: str, df: pd.DataFrame) -> Optional[dict[str, Any]]:
    """
    FX momentum:
      LONG  when price > both EMAs by EPS and RSI > LONG_TH
      SHORT when price < both EMAs by EPS and RSI < SHORT_TH

    Env:
      MOMENTUM_FX_EMA_FAST (50)
      MOMENTUM_FX_EMA_SLOW (200)
      MOMENTUM_FX_RSI_PERIOD (14)
      MOMENTUM_FX_RSI_LONG_TH (50)
      MOMENTUM_FX_RSI_SHORT_TH (40)
      MOMENTUM_FX_EPS (absolute price epsilon; default 0.00005 ~ 0.5 pip on EURUSD)
      MOMENTUM_FX_SL_PIPS / MOMENTUM_FX_TP_PIPS (optional; auto_decider will fill if omitted)
    """
    if df is None or df.empty or "close" not in df.columns:
        return None

    ema_fast_n = _env_int("MOMENTUM_FX_EMA_FAST", 50)
    ema_slow_n = _env_int("MOMENTUM_FX_EMA_SLOW", 200)
    rsi_p = _env_int("MOMENTUM_FX_RSI_PERIOD", 14)
    long_th = _env_int("MOMENTUM_FX_RSI_LONG_TH", 50)
    short_th = _env_int("MOMENTUM_FX_RSI_SHORT_TH", 40)
    eps = _env_float("MOMENTUM_FX_EPS", 0.00005)  # ~0.5 pip

    close = df["close"].astype(float)
    if len(close) < max(ema_slow_n, ema_fast_n, rsi_p) + 5:
        return None

    ema_fast = _ema(close, ema_fast_n)
    ema_slow = _ema(close, ema_slow_n)
    rsi = _rsi(close, rsi_p)

    last = {
        "price": float(close.iloc[-1]),
        "ema_fast": float(ema_fast.iloc[-1]),
        "ema_slow": float(ema_slow.iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
    }

    price = last["price"]
    ef, es = last["ema_fast"], last["ema_slow"]
    r = last["rsi"]

    why: list[str] = []
    long_ok = (price > max(ef, es) + eps) and (r > long_th)
    short_ok = (price < min(ef, es) - eps) and (r < short_th)

    if long_ok:
        return {
            "side": "LONG",
            "entry": price,
            # Let auto_decider fill SL/TP unless you prefer to set them here:
            "sl_pips": _env_float("MOMENTUM_FX_SL_PIPS", 0.0) or None,
            "tp_pips": _env_float("MOMENTUM_FX_TP_PIPS", 0.0) or None,
            "note": "momentum",
            "debug": {
                **last,
                "long_th": long_th,
                "short_th": short_th,
                "tf": timeframe,
                "len": int(len(df)),
                "eps": eps,
                "sl_source": "env_or_decider",
                "tp_source": "env_or_decider",
            },
            "why": ["LONG: price > both EMAs + eps and RSI>long_th"],
        }

    if short_ok:
        return {
            "side": "SHORT",
            "entry": price,
            "sl_pips": _env_float("MOMENTUM_FX_SL_PIPS", 0.0) or None,
            "tp_pips": _env_float("MOMENTUM_FX_TP_PIPS", 0.0) or None,
            "note": "momentum",
            "debug": {
                **last,
                "long_th": long_th,
                "short_th": short_th,
                "tf": timeframe,
                "len": int(len(df)),
                "eps": eps,
                "sl_source": "env_or_decider",
                "tp_source": "env_or_decider",
            },
            "why": ["SHORT: price < both EMAs - eps and RSI<short_th"],
        }

    # build no-trade explanation
    if price <= max(ef, es) + eps:
        why.append(f"no up-trend (price≤max(EMA)+eps; eps={eps})")
    if r <= long_th:
        why.append(f"RSI {r:.2f} <= long_th {long_th}")
    if price >= min(ef, es) - eps:
        why.append(f"no down-trend (price≥min(EMA)-eps; eps={eps})")
    if r >= short_th:
        why.append(f"RSI {r:.2f} >= short_th {short_th}")

    return {
        "side": "",
        "note": "no_trade",
        "debug": {
            **last,
            "long_th": long_th,
            "short_th": short_th,
            "tf": timeframe,
            "len": int(len(df)),
            "eps": eps,
            "sl_source": "default",
            "tp_source": "default",
        },
        "why": why,
    }
