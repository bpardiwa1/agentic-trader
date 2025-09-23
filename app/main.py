# app/main.py
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass
# app/main.py (imports)
import datetime
import json
import os
import re
from contextlib import suppress
from typing import Any, Literal

from fastapi import FastAPI, Query, Request
from pydantic import BaseModel

from app import config
from app.agents.auto_decider import decide_signal
from app.brokers import mt5_client as mt5c          # alias style
from app.brokers.mt5_client import warmup_history  # only if this exists (see step 3)
from app.exec.executor import execute_market_order as execute_order, close_all
from app.market.data import compute_context, get_rates  # ensure these exist (step 2)
from app.monitor.trailing import trail_positions
from app.risk.guards import risk_guard
from app.util.sizing import compute_lot, lots_override_for
from app.brokers.mt5_client import get_positions
from app.monitor.loss_monitor import monitor_and_close


# If you still call get_positions directly in main.py, either:
#  - change usages to mt5c.get_positions(...)
#  - OR add: from app.brokers.mt5_client import get_positions



try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# Optional: make MT5 import robust so app can start even if MT5 lib is missing
try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None  # type: ignore

app = FastAPI(title="Agentic Trader Universal")


# ----------------------------- Models -----------------------------------------


class MarketOrder(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT", "BUY", "SELL"]
    price: float | None = (
        None  # accepted by API; executor will use live tick if None/0
    )
    volume: float | None = None  # you can send volume or size
    size: float | None = None
    sl_pips: float | None = None
    tp_pips: float | None = None
    comment: str | None = None


# ----------------------------- Health & MT5 -----------------------------------


@app.get("/health")
def health():
    return {"ok": True, "mode": config.EXECUTION_MODE, "backend": config.BROKER_BACKEND}


@app.get("/mt5/ping")
def mt5_ping():
    # fixed: use the mt5c alias you already import
    return mt5c.init_and_login()


@app.get("/mt5/search_symbols")
def mt5_search_symbols(q: str = Query(..., min_length=1)):
    return mt5c.search_symbols(q)


@app.get("/mt5/is_open")
def mt5_is_open(symbol: str):
    return mt5c.is_symbol_trading_now(symbol)


@app.get("/mt5/symbol_info")
def mt5_symbol_info(symbol: str):
    return mt5c.symbol_info_dict(symbol)


# ----------------------------- Market Context ---------------------------------


@app.get("/market/context")
def market_context(symbol: str = "EURUSD", tf: str = "H1"):
    # fixed: compute_context is now properly imported
    return compute_context(symbol, tf, 300)


# ----------------------------- Sizing helpers ---------------------------------


def _lots_for(symbol: str, default_lots: float = 0.01) -> float:
    """Read LOTS_<SYMBOL> override from env (normalize to A-Z0-9 underscore)."""
    key = "LOTS_" + re.sub(r"[^A-Z0-9]+", "_", symbol.upper())
    try:
        return float(os.environ.get(key, str(default_lots)).split("#", 1)[0].strip())
    except Exception:
        return default_lots


def _default_lots() -> float:
    try:
        return float(
            os.environ.get("MT5_DEFAULT_LOTS", "0.01").split("#", 1)[0].strip()
        )
    except Exception:
        return 0.01


# ----------------------------- Agent Decide -----------------------------------


@app.get("/agents/decide")
def agents_decide(
    symbol: str,
    tf: str = "H1",
    agent: str = "auto",
    execute: bool = False,
):
    try:
        sig = decide_signal(symbol=symbol, timeframe=tf, agent=agent) or {}
        side = (sig.get("side") or "").upper()
        size_in = sig.get("size")  # may be None or non-float
        sl_pips = sig.get("sl_pips")
        tp_pips = sig.get("tp_pips")
        entry = sig.get("entry")
        note = sig.get("note") or sig.get("reason") or agent
    except Exception as e:
        return {"accepted": False, "error": f"strategy_error: {e}"}

    if side not in ("LONG", "SHORT"):
        return {
            "accepted": False,
            "note": "no trade signal",
            "debug": sig.get("debug"),
            "why": sig.get("why"),
        }

    # --- SIZING: env override -> strategy -> default ---
    default_lots = _default_lots()
    env_lots = lots_override_for(symbol, default_lots)
    override = (
        os.environ.get("OVERRIDE_STRATEGY_SIZE", "1").strip().lower()
        in ("1", "true", "yes")
    )

    # Resolve to a concrete float for mypy/runtime safety
    if size_in is None or override:
        resolved_size = env_lots
    else:
        try:
            resolved_size = float(size_in)
        except Exception:
            resolved_size = env_lots  # fallback if strategy returned something odd

    size = float(resolved_size)

    preview = {
        "symbol": symbol,
        "side": side,
        "size": size,
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "entry": entry,
        "timeframe": tf,
        "agent": agent,
        "note": note,
        "sizing": {
            "default_lots": default_lots,
            "env_lots": env_lots,
            "override": override,
        },
    }

    if not execute:
        return {"accepted": True, "preview": preview, "note": note}

    # Guardrails
    guard = risk_guard(symbol, side, sl_pips)
    if not guard["accepted"]:
        return {"accepted": False, "note": guard["note"], "preview": preview}

    try:
        order_res = execute_order(
            symbol=symbol,
            side=side,
            volume=size,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            comment=f"{agent}:{note}",
        )
        return {"accepted": True, "order": order_res, "note": note}
    except Exception as e:
        return {
            "accepted": True,
            "order": {"status": "error", "error": f"execution_error: {e}"},
            "note": note,
        }


# ----------------------------- Orders -----------------------------------------


@app.post("/orders/market")
def orders_market(order: MarketOrder):
    """Manual order with basic validation & caps (guardrails via env sizing)."""
    side = (order.side or "").upper()
    if side == "LONG":
        side = "BUY"
    elif side == "SHORT":
        side = "SELL"
    if side not in ("BUY", "SELL"):
        return {"status": "error", "error": "invalid_side"}

    # caps & defaults
    try:
        min_lot = float(os.getenv("MIN_LOT", "0.01"))
        max_lot = float(os.getenv("MAX_LOT", "1.0"))
        default_lots = float(os.getenv("MT5_DEFAULT_LOTS", "0.01"))
    except Exception:
        min_lot, max_lot, default_lots = 0.01, 1.0, 0.01

    explicit = order.volume or order.size
    lot_mode = (os.getenv("LOT_MODE", "fixed") or "fixed").lower()

    if explicit is not None:
        lot = float(explicit)
    elif lot_mode == "risk" and order.sl_pips not in (None, 0):
        lot = compute_lot(order.symbol, float(order.sl_pips), mode="risk")
    else:
        lot = lots_override_for(order.symbol, default_lots)

    # clamp
    lot = max(min_lot, min(max_lot, float(lot)))

    return execute_order(
        symbol=order.symbol,
        side=side,
        volume=float(lot),
        sl_pips=order.sl_pips,
        tp_pips=order.tp_pips,
        comment=order.comment or "manual",
    )


@app.post("/orders/close")
def orders_close(
    symbol: str | None = None,
    ticket: int | None = None,
    volume: float | None = None,
):
    # If ticket is provided, close that exact position directly via MT5
    if ticket is not None:
        if mt5 is None:
            return {
                "closed": 0,
                "reports": [],
                "message": "MetaTrader5 not available on this host",
            }
        pos_list = mt5.positions_get()
        if not pos_list:
            return {"closed": 0, "reports": [], "message": "no open positions"}
        target = [p for p in pos_list if getattr(p, "ticket", None) == ticket]
        if not target:
            return {"closed": 0, "reports": [], "message": f"ticket {ticket} not found"}
        p = target[0]
        order_type = (
            mt5.ORDER_TYPE_SELL
            if p.type == mt5.POSITION_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        tick = mt5.symbol_info_tick(p.symbol)
        if not tick:
            return {
                "closed": 0,
                "reports": [{"ticket": ticket, "status": "error", "error": "no_tick"}],
            }
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "position": p.ticket,
            "volume": float(volume or p.volume),
            "type": order_type,
            "price": price,
            "deviation": 50,
            "comment": "close_ticket",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        ok = bool(res and res.retcode == mt5.TRADE_RETCODE_DONE)
        return {
            "closed": 1 if ok else 0,
            "reports": [
                {
                    "ticket": ticket,
                    "status": "ok" if ok else "error",
                    "retcode": getattr(res, "retcode", None),
                }
            ],
        }

    # Otherwise close by symbol (or all) via broker layer
    return close_all(symbol=symbol, volume=volume)


# Unsafe direct market order (no guardrails). Renamed to avoid duplicate path.
@app.post("/orders/market/unsafe")
def orders_market_unsafe(order: MarketOrder):
    """Direct manual order (no guardrails)."""
    side = (order.side or "").upper()
    if side == "LONG":
        side = "BUY"
    elif side == "SHORT":
        side = "SELL"

    lot = order.volume or order.size or _default_lots()

    return execute_order(
        symbol=order.symbol,
        side=side,
        volume=float(lot),
        sl_pips=order.sl_pips,
        tp_pips=order.tp_pips,
        comment=order.comment or "manual",
    )


# ----------------------------- Positions --------------------------------------


@app.get("/positions")
def positions(symbol: str | None = None):
    if config.BROKER_BACKEND != "mt5":
        return {"ok": True, "positions": []}
    return get_positions(symbol)


@app.post("/positions/close_all")
def positions_close_all(symbol: str):
    return close_all(symbol=symbol)


# ----------------------------- Journal ----------------------------------------


@app.get("/journal/today")
def journal_today(limit: int = 50):
    day = datetime.datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(config.DATA_DIR, f"trades-{day}.json")
    if not os.path.exists(path):
        return {"ok": True, "summary": {"count": 0}, "trades": []}

    trades: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            with suppress(Exception):
                trades.append(json.loads(line))

    count = len(trades)
    wins = sum(1 for t in trades if str(t.get("status")) == "ok")
    paper = sum(1 for t in trades if t.get("paper"))
    return {
        "ok": True,
        "summary": {"count": count, "ok": wins, "paper": paper},
        "trades": trades[-limit:],
    }


# ----------------------------- Inspect (candles/lot) --------------------------

_TF_MAP: dict[str, Any] = {}
if mt5 is not None:
    _TF_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }


def _tf_to_mt5(tf: str) -> int:
    if mt5 is None:
        return 0
    return _TF_MAP.get((tf or "M15").upper(), mt5.TIMEFRAME_M15)


@app.get("/inspect/candles")
def inspect_candles(symbol: str, tf: str = "M15", n: int = 20):
    df = get_rates(symbol, tf, n)
    if df is None or getattr(df, "empty", False):
        return {"ok": False, "error": f"No data for {symbol} {tf}"}
    return {
        "ok": True,
        "symbol": symbol,
        "tf": tf,
        "count": len(df),
        "candles": df.tail(5).to_dict(orient="records"),  # show last 5 bars
    }


@app.get("/inspect/lot")
def inspect_lot(symbol: str):
    resolved = lots_override_for(symbol, float(os.getenv("MT5_DEFAULT_LOTS", "0.01")))
    key = "LOTS_" + re.sub(r"[^A-Z0-9]+", "_", symbol.upper())
    return {
        "symbol": symbol,
        "env_key": key,
        "env_val": os.getenv(key),
        "resolved": resolved,
    }


# ----------------------------- Monitors ---------------------------------------


@app.post("/monitor/loss")
def monitor_loss(symbols: str = ""):
    """
    POST /monitor/loss?symbols=EURUSD-ECNc,XAUUSD-ECNc
    Runs the loss monitor once for the given symbols (comma-separated).
    If blank, uses AGENT_SYMBOLS from env.
    """
    if not symbols:
        symbols = (os.getenv("AGENT_SYMBOLS") or "").strip()
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        return {"ok": False, "error": "no symbols provided"}
    report = monitor_and_close(syms)
    return {"ok": True, "report": report}


# ...top of file unchanged...

# --- helpers to parse query params ---
def _qbool(v, default=False):
    if v is None:
        return default
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "on"}

def _qfloat(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except Exception:
        return default

def _qint(v, default=None):
    if v is None or v == "":
        return default
    try:
        return int(float(v))
    except Exception:
        return default

# --- /monitor/trail (POST) ---
@app.post("/monitor/trail")
def monitor_trail(request: Request):
    qp = request.query_params

    # required
    symbols_raw = qp.get("symbols", "")
    syms = [s.strip() for s in symbols_raw.split(",") if s.strip()]
    if not syms:
        return {"ok": False, "error": "no symbols provided"}

    # optional overrides (all keyword-only in trail_positions)
    kwargs: dict[str, Any] = {}

    # booleans
    kwargs["force"] = _qbool(qp.get("force"), False)
    only_profit = qp.get("only_profit")
    req_bias = qp.get("req_bias")
    if only_profit is not None:
        kwargs["only_profit"] = _qbool(only_profit, True)
    if req_bias is not None:
        kwargs["req_bias"] = _qbool(req_bias, True)

    # strings
    mode = qp.get("mode")
    if mode:
        kwargs["mode"] = mode.upper()

    # numbers
    ap = _qint(qp.get("atr_period"))
    am = _qfloat(qp.get("atr_mult"))
    tp = _qfloat(qp.get("trail_pips"))
    sp = _qfloat(qp.get("start_pips"))
    lp = _qfloat(qp.get("lock_pips"))
    step = _qfloat(qp.get("step_pips"))
    fm = _qint(qp.get("freq_min"))

    if ap is not None:
        kwargs["atr_period"] = ap
    if am is not None:
        kwargs["atr_mult"] = am
    if tp is not None:
        kwargs["trail_pips"] = tp
    if sp is not None:
        kwargs["start_pips"] = sp
    if lp is not None:
        kwargs["lock_pips"] = lp
    if step is not None:
        kwargs["step_pips"] = step
    if fm is not None:
        kwargs["freq_min"] = fm

    # call the monitor
    try:
        return trail_positions(syms, **kwargs)
    except Exception as e:
        # keep the API resilient
        return {"ok": False, "error": f"trail_positions error: {e.__class__.__name__}: {e}"}


# ----------------------------- Warmup -----------------------------------------


@app.get("/mt5/warmup")
def mt5_warmup(
    symbol: str, tf: str = Query("M15"), bars: int = Query(600, ge=50, le=5000)
):
    return warmup_history(symbol, tf, bars)


@app.get("/mt5/warmup_many")
def mt5_warmup_many(
    symbols: str, tf: str = Query("M15"), bars: int = Query(600, ge=50, le=5000)
):
    results = []
    for s in [x.strip() for x in symbols.split(",") if x.strip()]:
        results.append(warmup_history(s, tf, bars))
    return {"ok": all(r.get("ok") for r in results), "results": results}


# ----------------------------- Momentum Inspector -----------------------------

import numpy as np


def _envf(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).split("#", 1)[0].strip())
    except Exception:
        return default


def _is_xau(symbol: str) -> bool:
    s = (symbol or "").upper()
    return "XAU" in s or "GOLD" in s


def _ema(values: list[float], period: int) -> list[float]:
    if period <= 1 or len(values) == 0:
        return values[:]
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for x in values[1:]:
        prev = out[-1]
        out.append(prev + k * (x - prev))
    return out


def _rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) < period + 1:
        return [50.0] * len(values)
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = _ema(gains, period)
    avg_loss = _ema(losses, period)
    rsi: list[float] = []
    for gain_avg, loss_avg in zip(avg_gain, avg_loss, strict=False):
        if loss_avg == 0:
            rsi.append(100.0)
        else:
            rs = gain_avg / loss_avg
            rsi.append(100.0 - (100.0 / (1.0 + rs)))
    pad = max(0, len(values) - len(rsi))
    return [50.0] * pad + rsi


def _tr(prev_close: float, high: float, low: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float]:
    if len(closes) == 0:
        return []
    trs: list[float] = [0.0]
    for i in range(1, len(closes)):
        trs.append(_tr(closes[i - 1], highs[i], lows[i]))
    return _ema(trs, period)


@app.get("/inspect/momentum")
def inspect_momentum(symbol: str, tf: str = Query("M15")):
    ok, payload = get_rates(symbol, tf, 300)
    if not ok:
        return {"ok": False, "note": payload}

    rates = payload["rates"]
    if rates is None or len(rates) < 50:
        return {"ok": False, "note": "not enough data", "len": 0}

    closes = np.array([r["close"] for r in rates], dtype=float)
    price = float(closes[-1])

    def ema(arr, n):
        k = 2 / (n + 1)
        out = [arr[0]]
        for x in arr[1:]:
            out.append(out[-1] + k * (x - out[-1]))
        return np.array(out)

    def rsi(arr, n=14):
        deltas = np.diff(arr)
        up = np.where(deltas > 0, deltas, 0.0)
        dn = np.where(deltas < 0, -deltas, 0.0)
        ru = ema(up, n)
        rd = ema(dn, n)
        rs = np.divide(ru, rd, out=np.zeros_like(ru), where=rd != 0)
        r = 100 - (100 / (1 + rs))
        r = np.concatenate([[50.0], r])
        return r

    ema_fast = ema(closes, int(os.getenv("MOMENTUM_FX_EMA_FAST", "50")))
    ema_slow = ema(closes, int(os.getenv("MOMENTUM_FX_EMA_SLOW", "200")))
    rsi14 = rsi(closes, int(os.getenv("MOMENTUM_FX_RSI_PERIOD", "14")))

    debug = {
        "len": len(rates),
        "price": price,
        "ema_fast_last": float(ema_fast[-1]),
        "ema_slow_last": float(ema_slow[-1]),
        "rsi_last": float(rsi14[-1]),
        "tf": tf,
    }
    return {"ok": True, "debug": debug}
