# run_auto_guarded.py
from __future__ import annotations

import os
import time
import logging
from typing import List, Dict, Any

from dotenv import load_dotenv

# ensure .env is loaded
load_dotenv()

from app.agents.auto_decider import decide_signal
from app.exec.executor import place_order
from app.risk.guards import risk_guard

# optional: if you have an is_open endpoint/helper use it; otherwise we rely on guards
try:
    from app.brokers.mt5_client import is_symbol_trading_now  # type: ignore
except Exception:
    def is_symbol_trading_now(symbol: str) -> Dict[str, Any]:
        return {"tradable": True, "market_open": True, "note": "fallback"}

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(message)s")

def _split_symbols(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]

def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}

def main() -> None:
    timeframe = os.getenv("AGENT_TIMEFRAME", "M15")
    period_sec = int(os.getenv("AGENT_PERIOD_SEC", "60"))

    logging.info(f"[auto] starting loop. TF={timeframe} Period={period_sec}s")

    while True:
        # re-read symbols each tick so edits to .env take effect on next cycle
        raw_syms = os.getenv("AGENT_SYMBOLS", "")
        symbols = _split_symbols(raw_syms)

        logging.info(f"[auto] tick; AGENT_SYMBOLS='{raw_syms}' -> {symbols or '[]'}")

        if not symbols:
            logging.warning("[auto] no symbols configured; sleeping")
            time.sleep(period_sec)
            continue

        for sym in symbols:
            # loud market check
            try:
                m = is_symbol_trading_now(sym)
                logging.info(f"[auto][market] {sym} tradable={m.get('tradable')} open={m.get('market_open')} note={m.get('note')}")
            except Exception as exc:
                logging.info(f"[auto][market] {sym} market-check error: {exc}")

            try:
                sig = decide_signal(sym, timeframe, agent="auto") or {}
            except Exception as exc:
                logging.exception(f"[auto] decide_signal crashed for {sym}: {exc}")
                continue

            side = (sig.get("side") or "").upper()
            why = sig.get("why")
            debug = sig.get("debug")

            # Always show decide logs per symbol so you see EURUSD and XAUUSD every time
            if side:
                logging.info(f"[auto][debug] {sym} side={side} why={why} debug={debug}")
            else:
                logging.info(f"[auto][debug] {sym} no-trade why={why} debug={debug}")

            if not side:
                logging.info(f"[auto] {sym} no signal ({sig.get('note')})")
                continue

            # Risk guard (will also log cooldown/blocks)
            g = risk_guard(sym, side, sig.get("sl_pips"))
            if not g.get("accepted"):
                logging.info(f"[auto] {sym} blocked -> {g}")
                continue

            # Place order (compat adapter handles both dict + legacy signatures)
            res = place_order(sym, sig)
            if res.get("status") == "ok":
                logging.info(f"[auto] {sym} placed -> {res}")
            else:
                logging.info(f"[auto] {sym} place error -> {res}")

        time.sleep(period_sec)

if __name__ == "__main__":
    main()
