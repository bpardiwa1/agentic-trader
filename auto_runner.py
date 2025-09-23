import datetime
import os
import time

import requests

API = os.environ.get("AGENT_API", "http://127.0.0.1:8001")
SYMBOLS = os.environ.get("AGENT_SYMBOLS", "EURUSD,XAUUSD").split(",")
TIMEFRAME = os.environ.get("AGENT_TF", "H1")
CADENCE_SEC = int(os.environ.get("AGENT_PERIOD_SEC", "60"))
VERBOSE = os.environ.get("VERBOSE", "false").lower() == "true"

MAX_OPEN_POSITIONS = int(os.environ.get("AGENT_MAX_OPEN", "6"))
MAX_PER_SYMBOL = int(os.environ.get("AGENT_MAX_PER_SYMBOL", "2"))
COOLDOWN_MIN = int(os.environ.get("AGENT_COOLDOWN_MIN", "30"))
BLOCK_SAME_SIDE = os.environ.get("AGENT_BLOCK_SAME_SIDE", "true").lower() == "true"
TRADING_START = os.environ.get("AGENT_TRADING_START", "00:00")
TRADING_END = os.environ.get("AGENT_TRADING_END", "23:59")

state = {s: {"last_trade_ts": None} for s in SYMBOLS}


def vprint(msg):
    if VERBOSE:
        print(msg)


def within_trading_window() -> bool:
    now = datetime.datetime.now()
    h, m = map(int, TRADING_START.split(":"))
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    h2, m2 = map(int, TRADING_END.split(":"))
    end = now.replace(hour=h2, minute=m2, second=0, microsecond=0)
    return start <= now <= end


def cooldown_ok(symbol: str) -> bool:
    lt = state[symbol]["last_trade_ts"]
    if not lt:
        return True
    delta = (datetime.datetime.now() - lt).total_seconds() / 60.0
    return delta >= COOLDOWN_MIN


def mark_traded(symbol: str):
    state[symbol]["last_trade_ts"] = datetime.datetime.now()


def get_positions(symbol: str | None = None) -> list:
    try:
        params = {"symbol": symbol} if symbol else None
        r = requests.get(f"{API}/positions", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        if (
            isinstance(data, dict)
            and data.get("ok")
            and isinstance(data.get("positions"), list)
        ):
            return data["positions"]
    except Exception as e:
        vprint(f"[positions] error: {e}")
    return []


def get_open_positions_count() -> int:
    return len(get_positions(None))


def get_symbol_positions(symbol: str) -> list:
    return get_positions(symbol)


def has_same_side_position(symbol: str, side: str) -> bool:
    side = (side or "").upper()
    for p in get_symbol_positions(symbol):
        s = (p.get("side") or "").upper()
        s = "LONG" if s in ("BUY", "LONG") else "SHORT" if s in ("SELL", "SHORT") else s
        if s == side:
            return True
    return False


def loop():
    print(
        f"[auto] Running. Symbols={SYMBOLS} TF={TIMEFRAME} Period={CADENCE_SEC}s (VERBOSE={'on' if VERBOSE else 'off'})"
    )
    while True:
        try:
            if not within_trading_window():
                vprint("[auto] Outside trading window; sleeping...")
                time.sleep(CADENCE_SEC)
                continue

            if get_open_positions_count() >= MAX_OPEN_POSITIONS:
                vprint("[auto] Max open positions reached; sleeping...")
                time.sleep(CADENCE_SEC)
                continue

            for s in SYMBOLS:
                try:
                    if len(get_symbol_positions(s)) >= MAX_PER_SYMBOL:
                        continue
                    if not cooldown_ok(s):
                        continue

                    prev = requests.get(
                        f"{API}/agents/decide",
                        params={
                            "symbol": s,
                            "tf": TIMEFRAME,
                            "agent": "auto",
                            "execute": "false",
                        },
                        timeout=30,
                    ).json()

                    if not prev or not prev.get("accepted"):
                        time.sleep(1)
                        continue

                    side = (
                        (prev.get("preview") or {}).get("side")
                        or (prev.get("signal") or {}).get("side")
                        or prev.get("side")
                    )
                    if BLOCK_SAME_SIDE and side and has_same_side_position(s, side):
                        time.sleep(1)
                        continue

                    res = requests.get(
                        f"{API}/agents/decide",
                        params={
                            "symbol": s,
                            "tf": TIMEFRAME,
                            "agent": "auto",
                            "execute": "true",
                        },
                        timeout=30,
                    ).json()

                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    accepted = res.get("accepted")
                    note = res.get("note") or res.get("reason")
                    order = res.get("order") or {}
                    status = order.get("status")
                    deal = order.get("deal")
                    # Only print a single concise line per decision by default
                    if VERBOSE or status == "ok":
                        print(
                            f"[{ts}] {s}: accepted={accepted} status={status} deal={deal} note={note}"
                        )
                    if accepted and order and status == "ok":
                        mark_traded(s)
                except Exception as e:
                    print(f"[ERR] {s}: {e}")
                time.sleep(2)

        except KeyboardInterrupt:
            print("Stopping auto runner...")
            break
        except Exception as e:
            print(f"[ERR] loop: {e}")
            time.sleep(CADENCE_SEC)


def market_open(symbol):
    try:
        r = requests.get(
            f"{API}/mt5/is_open", params={"symbol": symbol}, timeout=10
        ).json()
        return r.get("ok") and r.get("market_open_like")
    except Exception:
        return True  # fail-open if endpoint unavailable


# ...
for s in SYMBOLS:
    if not market_open(s):
        vprint(f"[auto] {s} appears closed; skipping")
        time.sleep(1)
        continue
    # continue with decide -> execute

if __name__ == "__main__":
    loop()
