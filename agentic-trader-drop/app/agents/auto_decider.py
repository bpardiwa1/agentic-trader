# app/agents/auto_decider.py
from __future__ import annotations
import os, logging
from typing import Any, Optional
import pandas as pd

from app.market.data import get_rates
from app.strategies.momentum import momentum_signal
try:
    from app.strategies.xau_momentum import xau_momentum_signal
except Exception:
    xau_momentum_signal = None  # type: ignore
try:
    from app.strategies.indices_momentum import indices_momentum_signal
except Exception:
    indices_momentum_signal = None  # type: ignore
try:
    from app.strategies.equities_momentum import equities_momentum_signal
except Exception:
    equities_momentum_signal = None  # type: ignore

def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}
def _env_float(name: str, default: float) -> float:
    try: return float((os.getenv(name) or str(default)).split("#", 1)[0].strip())
    except Exception: return default
def _env_int(name: str, default: int) -> int:
    try: return int(float((os.getenv(name) or str(default)).split("#", 1)[0].strip()))
    except Exception: return default

def _normalize_key(s: str) -> str:
    import re; return re.sub(r"[^A-Z0-9]+", "_", (s or "").upper())
def _symbol_alias(symbol: str) -> str:
    base = symbol.split(".", 1)[0]
    key = f"SYMBOL_ALIAS_{_normalize_key(base)}"
    return os.getenv(key, symbol).strip()
def _per_symbol_lots(symbol: str, fallback: float) -> float:
    key = f"LOTS_{_normalize_key(symbol)}"; val = os.getenv(key)
    if val is not None:
        try: return float(val)
        except Exception: pass
    try: return float((os.getenv("MT5_DEFAULT_LOTS") or str(fallback)).split("#", 1)[0].strip())
    except Exception: return fallback
def _strategy_for(symbol: str) -> str:
    base = symbol.split(".", 1)[0]
    key = f"STRATEGY_{_normalize_key(base)}"
    return (os.getenv(key) or os.getenv("STRATEGY_DEFAULT") or "MOMENTUM").strip().upper()

_LOG_LEVEL = (os.getenv("LOG_LEVEL") or ("DEBUG" if _env_bool("VERBOSE", False) else "INFO")).upper()
logging.basicConfig(level=getattr(logging, _LOG_LEVEL, logging.INFO), format="%(message)s")
def _log_decider(msg: str) -> None:
    if _LOG_LEVEL in ("DEBUG", "INFO"):
        logging.info(msg)

def decide_signal(symbol: str, timeframe: str = "M15", agent: str = "auto") -> dict[str, Any]:
    routed_symbol = _symbol_alias(symbol)

    # Pull bars
    try:
        df: Optional[pd.DataFrame] = get_rates(routed_symbol, timeframe, 300)
    except Exception as exc:
        _log_decider(f"[decide] {routed_symbol} tf={timeframe} get_rates error: {exc}")
        return {"side": "", "note": "no_data", "debug": {"error": f"get_rates exception: {exc}"}, "why": ["could not fetch rates"]}

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        _log_decider(f"[decide] {routed_symbol} tf={timeframe} no bars")
        return {"side": "", "note": "no_data", "debug": {"error": "empty DataFrame"}, "why": ["no data"]}

    _log_decider(f"[decide] {routed_symbol} tf={timeframe} bars={len(df)} close={float(df['close'].iloc[-1]):.5f}")

    # Bypass (testing)
    if _env_bool("STRATEGY_BYPASS", False):
        side = (os.getenv("BYPASS_SIDE") or "LONG").strip().upper()
        size = _env_float("BYPASS_SIZE", 0.0) or _per_symbol_lots(routed_symbol, 0.01)
        preview = {
            "symbol": routed_symbol, "side": side, "size": size,
            "sl_pips": _env_float("BYPASS_SL_PIPS", 0.0) or None,
            "tp_pips": _env_float("BYPASS_TP_PIPS", 0.0) or None,
            "entry": float(df["close"].iloc[-1]),
            "timeframe": timeframe, "agent": agent, "note": "bypass",
        }
        only_when_exec = _env_bool("BYPASS_REQUIRE_EXECUTE", True)
        _log_decider(f"[decide] BYPASS {routed_symbol} -> {preview}")
        return {
            "side": side if not only_when_exec else "",
            "note": "bypass" if not only_when_exec else "preview (bypass; requires execute)",
            "preview": preview, "debug": {"bypass": True},
        }

    # Strategy routing
    strategy_id = _strategy_for(routed_symbol)
    S = strategy_id
    sig: Optional[dict[str, Any]] = None

    try:
        if S == "MOMENTUM" and "XAU" in _normalize_key(routed_symbol) and xau_momentum_signal:
            sig = xau_momentum_signal(routed_symbol, timeframe, df)
        elif S == "MOMENTUM":
            sig = momentum_signal(routed_symbol, timeframe, df)
        elif S == "INDICES_MOMENTUM" and indices_momentum_signal:
            sig = indices_momentum_signal(routed_symbol, timeframe, df)
        elif S == "EQUITIES_MOMENTUM" and equities_momentum_signal:
            sig = equities_momentum_signal(routed_symbol, timeframe, df)
        else:
            why = [f"strategy {strategy_id} not implemented"]
            _log_decider(f"[decide] {routed_symbol} -> no_trade; why={why}")
            return {"side": "", "note": "no_trade", "debug": {"reason": "unsupported strategy"}, "why": why}
    except Exception as exc:
        _log_decider(f"[decide] {routed_symbol} strategy error: {exc}")
        return {"side": "", "note": "no_trade", "debug": {"error": f"strategy_error: {exc}"}, "why": [str(exc)]}

    if not sig:
        _log_decider(f"[decide] {routed_symbol} -> no signal (strategy returned None)")
        return {"side": "", "note": "no_trade", "debug": {"reason": "no signal"}, "why": ["no signal"]}

    # Default lot size if missing
    if "size" not in sig or sig.get("size") is None:
        sig["size"] = _per_symbol_lots(routed_symbol, 0.01)

    # SL/TP fallbacks (kept as-is; strategies already try to set)
    is_gold = "XAU" in _normalize_key(routed_symbol)
    has_sl = sig.get("sl_pips") is not None
    has_tp = sig.get("tp_pips") is not None
    if is_gold:
        if not has_sl: sig["sl_pips"] = float(_env_int("MOMENTUM_XAU_SL_PIPS", 300)); sig.setdefault("debug", {})["sl_source"] = "default"
        if not has_tp: sig["tp_pips"] = float(_env_int("MOMENTUM_XAU_TP_PIPS", 450)); sig.setdefault("debug", {})["tp_source"] = "default"
    else:
        if not has_sl: sig["sl_pips"] = float(_env_int("MOMENTUM_FX_SL_PIPS", 40));  sig.setdefault("debug", {})["sl_source"] = "default"
        if not has_tp: sig["tp_pips"] = float(_env_int("MOMENTUM_FX_TP_PIPS", 90));  sig.setdefault("debug", {})["tp_source"] = "default"

    sig.setdefault("symbol", routed_symbol); sig.setdefault("timeframe", timeframe); sig.setdefault("agent", agent)
    _log_decider(f"[decide] {routed_symbol} -> side={sig.get('side')} sl={sig.get('sl_pips')} tp={sig.get('tp_pips')} why={sig.get('why')} debug={sig.get('debug')}")

    side = (sig.get("side") or "").upper()
    if side not in ("LONG", "SHORT"):
        return {"side": "", "note": "no_trade", "debug": sig.get("debug"), "why": sig.get("why") or ["conditions not met"]}

    return sig
