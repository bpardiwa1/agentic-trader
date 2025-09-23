# app/monitor/trailing.py
from __future__ import annotations

import os
import time
from typing import Any

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from app.agents.auto_decider import decide_signal
from app.brokers.mt5_client import get_positions, init_and_login
from app.market.data import get_rates
from app.util.pricing import price_delta_from_pips

_TRUE = {"1", "true", "yes", "on"}


def _bool(name: str, dflt: bool) -> bool:
    raw = (os.getenv(name) or ("1" if dflt else "0")).strip().lower()
    return raw in _TRUE


def _f(name: str, dflt: float) -> float:
    try:
        return float((os.getenv(name) or str(dflt)).split("#", 1)[0].strip())
    except Exception:
        return dflt


def _i(name: str, dflt: int) -> int:
    try:
        return int(float((os.getenv(name) or str(dflt)).split("#", 1)[0].strip()))
    except Exception:
        return dflt


def _now_min() -> int:
    return int(time.time() // 60)


# in-process cooldown per symbol to avoid hammering MT5
_COOLDOWN: dict[str, int] = {}


def _digits(symbol: str) -> int:
    info = mt5.symbol_info(symbol)
    return info.digits if info else 5


def _point(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    return info.point if info else 0.00001


def _pip_size(symbol: str) -> float:
    """Rough pip size: 0.0001 for FX with 5 digits; 0.1 for XAU; falls back to point*10."""
    symbol_upper = symbol.upper()
    if "XAU" in symbol_upper:
        return 0.1
    digits = _digits(symbol)
    if digits >= 5:
        return 0.0001
    return _point(symbol) * 10.0


def _normalize_rates(result: Any) -> pd.DataFrame | None:
    """
    Normalize get_rates return value to a DataFrame with ['high','low','close'].
    """
    if result is None:
        return None
    if isinstance(result, pd.DataFrame):
        return result
    if isinstance(result, tuple) and len(result) == 2:
        ok, payload = result
        if not ok or not isinstance(payload, dict):
            return None
        rates = payload.get("rates")
        if rates is None:
            return None
        return pd.DataFrame(rates)
    if isinstance(result, dict) and "rates" in result:
        return pd.DataFrame(result["rates"])
    return None


def _atr(symbol: str, tf: str, period: int) -> float | None:
    result = get_rates(symbol, tf, max(300, period + 50))
    df = _normalize_rates(result)
    if df is None or df.empty:
        return None

    try:
        highs = df["high"].to_numpy(float)
        lows = df["low"].to_numpy(float)
        closes = df["close"].to_numpy(float)
    except Exception:
        return None

    if len(closes) < period + 2:
        return None

    true_ranges = np.empty(len(closes))
    true_ranges[0] = np.nan
    for idx in range(1, len(closes)):
        tr = max(
            highs[idx] - lows[idx],
            abs(highs[idx] - closes[idx - 1]),
            abs(lows[idx] - closes[idx - 1]),
        )
        true_ranges[idx] = tr

    out = np.empty(len(closes))
    out[:period] = np.nan
    out[period] = np.nanmean(true_ranges[1 : period + 1])
    for idx in range(period + 1, len(closes)):
        out[idx] = (out[idx - 1] * (period - 1) + true_ranges[idx]) / period
    return float(out[-1])


def _price(symbol: str) -> dict[str, float] | None:
    tick_info = mt5.symbol_info_tick(symbol)
    if not tick_info:
        return None
    return {
        "bid": float(tick_info.bid),
        "ask": float(tick_info.ask),
        "last": float(tick_info.last),
    }


def _modify_sl(ticket: int, new_sl: float) -> dict[str, Any]:
    """Modify SL only (keep TP unchanged)."""
    pos = next((p for p in mt5.positions_get() or [] if p.ticket == ticket), None)
    if not pos:
        return {"status": "error", "error": "position_not_found"}
    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": int(ticket),
        "symbol": pos.symbol,
        "sl": float(new_sl),
        "tp": pos.tp,
        "magic": pos.magic,
        "comment": "trail",
        "type": pos.type,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    res = mt5.order_send(req)
    if res is None:
        return {"status": "error", "error": "order_send_none"}
    return {
        "status": (
            "ok"
            if res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
            else "error"
        ),
        "retcode": res.retcode,
        "comment": getattr(res, "comment", ""),
    }


def _pip_distance(symbol: str, p1: float, p2: float) -> float:
    pip_sz = _pip_size(symbol)
    return abs(p1 - p2) / pip_sz if pip_sz else 0.0


def trail_positions(
    symbols: list[str],
    *,
    # overrides coming from query parameters (all optional)
    force: bool = False,
    mode: str | None = None,
    atr_period: int | None = None,
    atr_mult: float | None = None,
    trail_pips: float | None = None,
    start_pips: float | None = None,
    lock_pips: float | None = None,
    step_pips: float | None = None,
    req_bias: bool | None = None,
    tf: str | None = None,
    freq_min: int | None = None,
) -> dict[str, Any]:
    """
    Trailing stop manager.

    If `force=True`, cooldown is bypassed and the provided override
    parameters (mode, *_pips, atr_*, req_bias, tf) are applied for this call only.
    """
    if not _bool("TRAIL_ENABLE", True) and not force:
        return {"ok": True, "note": "disabled", "actions": []}

    # Resolve effective settings (overrides take precedence)
    eff_tf = (tf or os.getenv("TRAIL_TF") or "M15")
    eff_mode = (mode or (os.getenv("TRAIL_MODE") or "ATR")).upper()
    eff_atr_period = int(atr_period if atr_period is not None else _i("TRAIL_ATR_PERIOD", 14))
    eff_atr_mult = float(atr_mult if atr_mult is not None else _f("TRAIL_ATR_MULT", 2.0))
    eff_trail_pips = float(trail_pips if trail_pips is not None else _f("TRAIL_PIPS", 60.0))
    eff_start_pips = float(start_pips if start_pips is not None else _f("TRAIL_START_PROFIT_PIPS", 30.0))
    eff_lock_pips = float(lock_pips if lock_pips is not None else _f("TRAIL_LOCK_PROFIT_PIPS", 5.0))
    eff_step_pips = float(step_pips if step_pips is not None else _f("TRAIL_STEP_PIPS", 5.0))
    eff_only_profit = _bool("TRAIL_ONLY_IN_PROFIT", True)  # not exposed as override for now
    eff_req_bias = bool(req_bias if req_bias is not None else _bool("TRAIL_REQUIRE_BIAS", True))
    eff_freq_min = int(0 if force else (freq_min if freq_min is not None else _i("TRAIL_FREQUENCY_MIN", 2)))

    actions: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []

    # Make sure broker session is ready
    try:
        init_and_login()
    except Exception:
        pass

    now_min = _now_min()

    for symbol in symbols:
        last_run = _COOLDOWN.get(symbol, 0)
        if not force and (now_min - last_run < eff_freq_min):
            inspected.append({"symbol": symbol, "skip": "cooldown"})
            continue

        positions = get_positions(symbol) or []
        # Normalize positions to list[dict]
        if isinstance(positions, dict):
            positions = [positions]
        elif not isinstance(positions, list):
            # unexpected shape -> skip safely
            inspected.append({"symbol": symbol, "error": f"positions_unexpected:{type(positions)}"})
            _COOLDOWN[symbol] = now_min
            continue
        positions = [p for p in positions if isinstance(p, dict)]

        if not positions:
            inspected.append({"symbol": symbol, "positions": 0})
            _COOLDOWN[symbol] = now_min
            continue

        ticks = _price(symbol)
        if not ticks:
            inspected.append({"symbol": symbol, "error": "no_tick"})
            _COOLDOWN[symbol] = now_min
            continue

        # compute trail distance for this symbol
        if eff_mode == "ATR":
            a = _atr(symbol, eff_tf, eff_atr_period)
            if a is None or a <= 0:
                inspected.append({"symbol": symbol, "error": "atr_unavailable"})
                _COOLDOWN[symbol] = now_min
                continue
            distance = a * eff_atr_mult
        else:  # PIPS
            distance = price_delta_from_pips(symbol, eff_trail_pips)

        for pos in positions:
            ticket_val = pos.get("ticket")
            try:
                ticket = int(ticket_val) if ticket_val is not None else None
            except Exception:
                ticket = None
            if ticket is None:
                inspected.append({"symbol": symbol, "skip": "no_ticket"})
                continue

            side = (pos.get("side") or pos.get("type_desc") or "").upper()  # BUY/SELL/LONG/SHORT
            entry = float(pos.get("price_open", 0.0) or 0.0)
            cur = float(pos.get("price_current", ticks["bid" if side in ("SELL", "SHORT") else "ask"]))

            # profit in pips
            prof_pips = _pip_distance(symbol, cur, entry)
            in_profit = (cur > entry) if side in ("BUY", "LONG") else (cur < entry)

            # gating
            if eff_only_profit and not in_profit:
                inspected.append({"symbol": symbol, "ticket": ticket, "skip": "not_in_profit"})
                continue
            if eff_only_profit and in_profit and prof_pips < eff_start_pips:
                inspected.append({"symbol": symbol, "ticket": ticket, "skip": f"profit<{eff_start_pips}p"})
                continue

            # Optional strategy bias alignment
            if eff_req_bias:
                try:
                    sig = decide_signal(symbol=symbol, timeframe=eff_tf, agent="trail") or {}
                    new_side = (sig.get("side") or "").upper()
                    want_long = side in ("BUY", "LONG")
                    aligned = (want_long and new_side == "LONG") or ((not want_long) and new_side == "SHORT")
                    if not aligned:
                        inspected.append({"symbol": symbol, "ticket": ticket, "skip": "bias_not_aligned"})
                        continue
                except Exception as exc:
                    inspected.append({"symbol": symbol, "ticket": ticket, "skip": f"bias_error:{exc}"})
                    continue

            # desired SL price
            if side in ("BUY", "LONG"):
                target_sl = cur - distance
                if eff_only_profit:
                    # lock at least some profit once trailing starts
                    lock = entry + price_delta_from_pips(symbol, eff_lock_pips)
                    target_sl = max(target_sl, lock)
                current_sl = float(pos.get("sl", 0.0) or 0.0)
                # only tighten (never widen)
                if current_sl and target_sl <= current_sl:
                    inspected.append({"symbol": symbol, "ticket": ticket, "skip": "no_improvement"})
                    continue
                if current_sl and _pip_distance(symbol, target_sl, current_sl) < eff_step_pips:
                    inspected.append({"symbol": symbol, "ticket": ticket, "skip": f"<{eff_step_pips}p_step"})
                    continue

            else:  # SELL/SHORT
                target_sl = cur + distance
                if eff_only_profit:
                    lock = entry - price_delta_from_pips(symbol, eff_lock_pips)
                    target_sl = min(target_sl, lock)
                current_sl = float(pos.get("sl", 0.0) or 0.0)
                if current_sl and target_sl >= current_sl:
                    inspected.append({"symbol": symbol, "ticket": ticket, "skip": "no_improvement"})
                    continue
                if current_sl and _pip_distance(symbol, target_sl, current_sl) < eff_step_pips:
                    inspected.append({"symbol": symbol, "ticket": ticket, "skip": f"<{eff_step_pips}p_step"})
                    continue

            res = _modify_sl(ticket, float(target_sl))
            actions.append(
                {
                    "symbol": symbol,
                    "ticket": ticket,
                    "side": side,
                    "from": current_sl,
                    "to": float(target_sl),
                    "result": res,
                }
            )

        _COOLDOWN[symbol] = now_min

    return {
        "ok": True,
        "mode": eff_mode,
        "tf": eff_tf,
        "actions": actions,
        "inspected": inspected,
        "freq_min": eff_freq_min,
        "forced": bool(force),
        "params": {
            "atr_period": eff_atr_period,
            "atr_mult": eff_atr_mult,
            "trail_pips": eff_trail_pips,
            "start_pips": eff_start_pips,
            "lock_pips": eff_lock_pips,
            "step_pips": eff_step_pips,
        },
    }
