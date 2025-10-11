# ==============================================================
# Agentic Trader - Main Runtime
# Updated: 2025-10-08
# Purpose: Central orchestrator for trade automation, scheduling,
# guardrails, and detailed runtime diagnostics.
# ==============================================================

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import MetaTrader5 as _mt5
from dotenv import load_dotenv
from fastapi import FastAPI

from app.agents.auto_decider import _classify_asset, decide_signal
from app.brokers.mt5_client import place_order as mt5_place_order

# --------------------------------------------------------------
# Load environment dynamically
# --------------------------------------------------------------
asset = os.getenv("ASSET", "FX")
merged_env = os.path.join(os.path.dirname(__file__), "env", ".merged", f"env.{asset}.merged.env")

if os.path.exists(merged_env):
    load_dotenv(merged_env)
    print(f"[ENV] Loaded merged env: {merged_env}")
else:
    print(f"[ENV] No merged env found at {merged_env}")

mt5: Any = _mt5
app = FastAPI()
MYTZ = ZoneInfo("Asia/Kuala_Lumpur")

# --------------------------------------------------------------
# Logging
# --------------------------------------------------------------
LOG_ROOT = "logs"
os.makedirs(LOG_ROOT, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_ROOT, "agentic.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

LOG_DIRS = {
    "FX": os.path.join(LOG_ROOT, "fx"),
    "XAU": os.path.join(LOG_ROOT, "xau"),
    "INDEX": os.path.join(LOG_ROOT, "indices"),
    "EQUITY": os.path.join(LOG_ROOT, "equities"),
}
for path in LOG_DIRS.values():
    os.makedirs(path, exist_ok=True)

state_file = os.path.join(LOG_ROOT, "last_trade_state.json")


# --------------------------------------------------------------
# Helpers
# --------------------------------------------------------------
def _norm_symbol(s: str | None) -> str:
    """Normalize symbols to uppercase and consistent formatting."""
    if not s:
        return ""
    return s.strip().replace(" ", "").replace("-", "_").upper()


# --------------------------------------------------------------
# Helpers for log routing
# --------------------------------------------------------------
def _get_log_paths(symbol: str, env: dict[str, Any] | None):
    cls = _classify_asset(symbol, env)
    executed = os.path.join(LOG_DIRS.get(cls, LOG_ROOT), "trades.executed.log")
    rejected = os.path.join(LOG_DIRS.get(cls, LOG_ROOT), "trades.rejected.log")
    return executed, rejected


def _log_trade(kind: str, symbol: str, sig: dict[str, Any], env: dict[str, Any] | None = None):
    executed_log, rejected_log = _get_log_paths(symbol, env)
    ts = datetime.now(MYTZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{kind.upper()}] {symbol} -> {sig}\n"
    with open(executed_log if kind == "executed" else rejected_log, "a", encoding="utf-8") as f:
        f.write(line)


# --------------------------------------------------------------
# Persistent trade state
# --------------------------------------------------------------
def _save_state(state: dict[str, datetime]):
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump({k: v.astimezone(MYTZ).isoformat() for k, v in state.items()}, f)


def _load_state() -> dict[str, datetime]:
    if not os.path.exists(state_file):
        return {}
    try:
        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)
        return {k: datetime.fromisoformat(v) for k, v in data.items()}
    except Exception as e:
        logger.warning("Failed to load state: %s", e)
        return {}


# --------------------------------------------------------------
# Trading window and guardrails
# --------------------------------------------------------------
def within_trading_window(symbol: str, env: dict[str, Any]) -> bool:
    cls = _classify_asset(symbol, env)
    now = datetime.now(MYTZ)
    weekday = now.weekday() + 1
    current_time = now.time()

    defaults = {
        "FX": ("00:00", "23:59", "1,2,3,4,5"),
        "XAU": ("00:00", "23:59", "1,2,3,4,5"),
        "INDEX": ("21:30", "23:30", "1,2,3,4,5"),
    }

    start_t = datetime.strptime(
        env.get(f"{cls}_TRADING_WINDOW_START", defaults[cls][0]), "%H:%M"
    ).time()
    end_t = datetime.strptime(
        env.get(f"{cls}_TRADING_WINDOW_END", defaults[cls][1]), "%H:%M"
    ).time()
    days = [int(x) for x in env.get(f"{cls}_TRADING_DAYS", defaults[cls][2]).split(",")]
    return weekday in days and start_t <= current_time <= end_t


def _check_guardrails(symbol: str, open_positions, max_open, max_per_symbol, cooldown_min):
    sym_key = _norm_symbol(symbol)
    total_open = len(open_positions) or 0

    # Normalize MT5 position symbols before comparing
    sym_positions = []
    for p in open_positions or []:
        try:
            psym = _norm_symbol(getattr(p, "symbol", ""))
        except Exception:
            psym = ""
        if psym == sym_key:
            sym_positions.append(p)

    if total_open >= max_open:
        return f"max open positions reached ({total_open}/{max_open})"
    if len(sym_positions) >= max_per_symbol:
        return f"max open positions per symbol reached ({len(sym_positions)}/{max_per_symbol})"

    last_time = last_trade_time.get(sym_key)
    if last_time and (datetime.now(MYTZ) - last_time).total_seconds() < cooldown_min * 60:
        return "cooldown active"

    logger.debug(
        "[GUARDRAILS] %s -> total_open=%s sym_open=%s cooldown=%s",
        symbol,
        total_open,
        len(sym_positions),
        (datetime.now(MYTZ) - last_trade_time[sym_key]).total_seconds()
        if sym_key in last_trade_time and last_trade_time[sym_key] is not None
        else None,
    )
    return None


# --------------------------------------------------------------
# Unified order execution (with enhanced order normalization)
# --------------------------------------------------------------
def place_order(symbol: str, sig: dict[str, Any]):
    """Unified execution wrapper delegating to app.brokers.mt5_client.place_order()."""
    try:
        preview = sig.get("preview", {})
        side = preview.get("side", "").upper()
        if not side:
            return {"ok": False, "error": "missing_side"}

        order_req = {
            "symbol": symbol,
            "side": side,
            "sl_pips": float(preview.get("sl_pips", 0)),
            "tp_pips": float(preview.get("tp_pips", 0)),
        }

        result = mt5_place_order(order_req)

        # --- Normalize order ID so logs never show 'None' ---
        if isinstance(result, dict):
            if "order" not in result and "ticket" in result:
                result["order"] = result["ticket"]
            elif "order" not in result and isinstance(result.get("result"), dict):
                order_id = result["result"].get("order") or result["result"].get("deal")
                if order_id:
                    result["order"] = order_id
            if "order" not in result:
                result["order"] = "<unknown>"

        return result

    except Exception as e:
        logger.exception("Error in place_order for %s: %s", symbol, e)
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------
# Trade loop
# --------------------------------------------------------------
last_trade_time: dict[str, datetime] = _load_state()
last_regime_state: dict[str, str] = {}
startup_time = datetime.now(MYTZ)


async def trade_loop():
    symbols = os.getenv("AGENT_SYMBOLS", "EURUSD-ECNc").split(",")
    period = int(os.getenv("AGENT_PERIOD_SEC", "60"))
    cooldown_min = int(os.getenv("AGENT_COOLDOWN_MIN", "2"))
    max_per_symbol = int(os.getenv("AGENT_MAX_PER_SYMBOL", "2"))
    max_open = int(os.getenv("AGENT_MAX_OPEN", "6"))
    grace_min = int(os.getenv("AGENT_STARTUP_GRACE_MIN", "3"))
    require_new_regime = os.getenv("AGENT_REQUIRE_NEW_REGIME", "false").lower() == "true"
    verbose = os.getenv("VERBOSE", "true").lower() == "true"

    logger.info("Starting trade loop for symbols: %s", symbols)
    grace_logged = False

    async def handle_symbol(symbol, open_positions):
        env = dict(os.environ)
        if not within_trading_window(symbol, env):
            _log_trade("rejected", symbol, {"reason": "outside trading window"}, env)
            return

        reason = _check_guardrails(symbol, open_positions, max_open, max_per_symbol, cooldown_min)
        if reason:
            _log_trade("rejected", symbol, {"reason": reason}, env)
            return

        sig = decide_signal(symbol=symbol, timeframe=os.getenv("AGENT_TIMEFRAME", "H1"), env=env)
        preview = sig.get("preview", {})
        dbg = preview.get("debug", {})

        if verbose:
            logger.info(
                "[DEBUG] %s regime=%s | side=%s | EMA_FAST=%.5f | EMA_SLOW=%.5f | RSI=%.2f | eps=%.5f | why=%s",
                symbol,
                preview.get("note", ""),
                preview.get("side", ""),
                dbg.get("ema_fast", 0.0),
                dbg.get("ema_slow", 0.0),
                dbg.get("rsi", 0.0),
                dbg.get("eps", 0.0),
                preview.get("why", []),
            )

        current_regime = preview.get("note", "")
        if require_new_regime and last_regime_state.get(symbol) == current_regime:
            _log_trade("rejected", symbol, {"reason": "same regime"}, env)
            return
        last_regime_state[symbol] = current_regime

        if sig.get("accepted") and preview.get("side"):
            current_positions = mt5.positions_get() or []
            reason = _check_guardrails(
                symbol, current_positions, max_open, max_per_symbol, cooldown_min
            )
            if reason:
                _log_trade("rejected", symbol, {"reason": reason}, env)
                return

            result = place_order(symbol, sig)
            if result.get("ok"):
                logger.info(
                    "[EXECUTED] %s -> %s %s | SL=%.1f TP=%.1f | why=%s | order=%s ret=%s",
                    symbol,
                    preview.get("note", ""),
                    preview.get("side", ""),
                    preview.get("sl_pips", 0),
                    preview.get("tp_pips", 0),
                    preview.get("why", []),
                    result.get("order"),
                    result.get("retcode"),
                )
                sym_key = _norm_symbol(symbol)
                last_trade_time[sym_key] = datetime.now(MYTZ)
                _save_state(last_trade_time)
                _log_trade("executed", symbol, {"signal": sig, "broker": result}, env)
            else:
                logger.warning("[%s] order failed: %s", symbol, result.get("error"))
                _log_trade("rejected", symbol, {"signal": sig, "error": result}, env)
        else:
            _log_trade("rejected", symbol, sig, env)

    while True:
        try:
            if (datetime.now(MYTZ) - startup_time).total_seconds() < grace_min * 60:
                logger.info("[SKIP] Startup grace period active")
                await asyncio.sleep(period)
                continue
            if not grace_logged:
                logger.info("[TIME] Grace period ended — trading active")
                grace_logged = True

            open_positions = mt5.positions_get() or []
            for symbol in symbols:
                await handle_symbol(symbol, open_positions)

        except Exception as e:
            logger.exception("Error in trade_loop: %s", e)

        for h in logger.handlers:
            with contextlib.suppress(Exception):
                h.flush()
        await asyncio.sleep(period)


# --------------------------------------------------------------
# FastAPI endpoints
# --------------------------------------------------------------
tasks: list[asyncio.Task] = []


@app.on_event("startup")
async def startup_event():
    logger.info("===== ENV DEBUG DUMP =====")
    for k, v in os.environ.items():
        if k.startswith(("INDICES_", "FX_", "XAU_")):
            logger.info("%s=%s", k, v)
    logger.info("==========================")

    tasks.append(asyncio.create_task(trade_loop()))


@app.get("/agents/decide")
def decide_agent(symbol: str, agent: str | None = None) -> dict[str, Any]:
    return decide_signal(
        symbol=symbol,
        timeframe=os.getenv("AGENT_TIMEFRAME", "H1"),
        agent=agent,
        env=dict(os.environ),
    ) or {"accepted": False, "error": "no signal"}


@app.get("/mt5/ping")
def mt5_ping() -> dict[str, Any]:
    try:
        tick = mt5.symbol_info_tick("EURUSD")
        return {"ok": True, "tick": tick._asdict() if tick else None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/health")
def health():
    return {"ok": True, "status": "running"}
