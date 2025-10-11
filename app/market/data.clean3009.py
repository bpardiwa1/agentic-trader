# app/market/data.py
from __future__ import annotations

import contextlib
import datetime as dt
import os
import re
from typing import Any

import MetaTrader5 as _mt5  # type: ignore
import numpy as np
import pandas as pd

try:
    from app.brokers import mt5_client as mt5c

    _HAS_MT5C = True
except Exception:
    mt5c = None  # type: ignore
    _HAS_MT5C = False

# Treat MT5 as dynamic for Pylance (silences attr warnings like .initialize, .symbol_info, etc.)
mt5: Any = _mt5

# -----------------------------
# Constants
# -----------------------------
TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

COOLDOWN_MINUTES = 5
BOLL_PERIOD = 20
RSI_UP = 55
RSI_DOWN = 45


# -----------------------------
# Init / Symbol resolution
# -----------------------------
def _ensure_initialized() -> None:
    try:
        if _HAS_MT5C and mt5c is not None and hasattr(mt5c, "init_and_login"):
            mt5c.init_and_login()
    except Exception:
        pass
    with contextlib.suppress(Exception):
        mt5.initialize()
        mt5.initialize()


def _env_alias(symbol: str) -> str:
    """Resolve symbol alias from env (SYMBOL_ALIAS_EURUSD_ECNC=EURUSD)."""
    key = "SYMBOL_ALIAS_" + re.sub(r"[^A-Z0-9]+", "_", symbol.upper())
    return (os.getenv(key) or symbol).strip()


def _resolve_symbol(symbol: str) -> str:
    """
    Try to resolve to a valid MT5 symbol:
      1. Env alias
      2. Exact match
      3. Drop suffix after '-' (EURUSD-ECNc → EURUSD)
      4. Search via mt5_client if available
    """
    alias = _env_alias(symbol)

    if mt5.symbol_info(alias) is not None:
        return alias

    base = symbol.split("-", 1)[0]
    if mt5.symbol_info(base) is not None:
        return base

    if _HAS_MT5C and mt5c is not None and hasattr(mt5c, "search_symbols"):
        try:
            hits = mt5c.search_symbols(base)
            cands: list[str] = []
            if isinstance(hits, list):
                for h in hits:
                    if isinstance(h, str):
                        cands.append(h)
                    elif isinstance(h, dict):
                        name = h.get("name") or h.get("symbol") or h.get("Symbol")
                        if isinstance(name, str):
                            cands.append(name)
            for cand in cands:
                if cand.upper().startswith(base.upper()):
                    return cand
            if cands:
                return cands[0]
        except Exception:
            pass

    return symbol


def _select_symbol(sym: str) -> bool:
    """Try to select symbol in MT5, nudging history once if needed."""
    if mt5.symbol_select(sym, True):
        return True
    try:
        end = dt.datetime.now()
        start = end - dt.timedelta(days=10)
        mt5.history_select(start, end)
        return bool(mt5.symbol_select(sym, True))
    except Exception:
        return False


# -----------------------------
# Public data fetchers
# -----------------------------
def _tf_to_mt5(tf: str) -> int:
    return TF_MAP.get((tf or "M15").upper(), mt5.TIMEFRAME_M15)


def get_rates(symbol: str, tf: str = "M15", n: int = 300) -> pd.DataFrame:
    """Fetch OHLCV rates for (symbol, timeframe). Returns DataFrame or empty DataFrame."""
    _ensure_initialized()
    resolved = _resolve_symbol(symbol)
    if not _select_symbol(resolved):
        return pd.DataFrame()

    timeframe = _tf_to_mt5(tf)
    rates = mt5.copy_rates_from_pos(resolved, timeframe, 0, n)

    if not rates or len(rates) == 0:
        end = dt.datetime.now()
        start = end - dt.timedelta(days=10)
        mt5.history_select(start, end)
        rates = mt5.copy_rates_from_pos(resolved, timeframe, 0, n)

    if not rates or len(rates) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s")
    df.attrs["symbol"] = resolved
    df.attrs["requested_symbol"] = symbol
    df.attrs["tf"] = tf
    return df


def get_rates_df(symbol: str, tf: str = "M15", n: int = 300) -> pd.DataFrame | None:
    """Wrapper returning DataFrame or None."""
    df = get_rates(symbol, tf, n)
    return None if df.empty else df


# -----------------------------
# Lightweight TA helpers
# -----------------------------
def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    if len(arr) == 0:
        return np.array([])
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(arr: np.ndarray, period: int = 14) -> np.ndarray:
    if len(arr) < period + 1:
        return np.full(len(arr), np.nan)
    delta = np.diff(arr)
    up = np.maximum(delta, 0.0)
    dn = -np.minimum(delta, 0.0)
    roll_up = np.empty(len(arr))
    roll_dn = np.empty(len(arr))
    roll_up[:period] = np.nan
    roll_dn[:period] = np.nan
    roll_up[period] = up[:period].mean()
    roll_dn[period] = dn[:period].mean()
    for i in range(period + 1, len(arr)):
        roll_up[i] = (roll_up[i - 1] * (period - 1) + up[i - 1]) / period
        roll_dn[i] = (roll_dn[i - 1] * (period - 1) + dn[i - 1]) / period
    rs = roll_up / np.where(roll_dn == 0, np.nan, roll_dn)
    out = 100.0 - (100.0 / (1.0 + rs))
    out[:period] = np.nan
    return out


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    if len(closes) < period + 1:
        return np.full(len(closes), np.nan)
    trs = np.empty(len(closes))
    trs[0] = np.nan
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs[i] = tr
    out = np.empty(len(closes))
    out[:period] = np.nan
    out[period] = np.nanmean(trs[1 : period + 1])
    for i in range(period + 1, len(closes)):
        out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
    return out


# -----------------------------
# Public: compute_context
# -----------------------------
def compute_context(symbol: str, tf: str = "H1", count: int = 300) -> dict[str, Any]:
    """
    Compute compact market summary:
      price, EMA50/200, RSI14, ATR%, Bollinger width %, regime.
    """
    df = get_rates(symbol, tf, count)
    if df is None or df.empty:
        return {"symbol": symbol, "timeframe": tf, "ok": False, "error": "no_data"}

    closes = df["close"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)

    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)

    price = float(closes[-1])
    e50 = float(ema50[-1])
    e200 = float(ema200[-1])
    rlast = float(rsi14[-1])
    alast = float(atr14[-1])

    # Bollinger bands width (%)
    if len(closes) >= BOLL_PERIOD:
        roll = pd.Series(closes)
        m20 = roll.rolling(BOLL_PERIOD).mean().to_numpy()
        s20 = roll.rolling(BOLL_PERIOD).std(ddof=0).to_numpy()
        upper = m20[-1] + 2.0 * s20[-1]
        lower = m20[-1] - 2.0 * s20[-1]
        bb_width_pct = float((upper - lower) / price) if price else float("nan")
    else:
        bb_width_pct = float("nan")

    atr_pct = float(alast / price) if price else float("nan")

    # Simple regime
    if e50 > e200 and rlast > RSI_UP:
        regime, notes = "TRENDING_UP", "EMA50>EMA200 and RSI>55"
    elif e50 < e200 and rlast < RSI_DOWN:
        regime, notes = "TRENDING_DOWN", "EMA50<EMA200 and RSI<45"
    else:
        regime, notes = "RANGE/MIXED", "mixed EMA/RSI state"

    resolved = df.attrs.get("symbol", symbol)
    return {
        "ok": True,
        "symbol": resolved,
        "requested": symbol,
        "timeframe": tf,
        "price": price,
        "ema50": e50,
        "ema200": e200,
        "rsi14": rlast,
        "atr_pct": atr_pct,
        "bb_width_pct": bb_width_pct,
        "regime": regime,
        "notes": notes,
    }
