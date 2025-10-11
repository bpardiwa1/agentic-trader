"""
End-of-Trade Logger — Unified Version
-------------------------------------
✅ Creates CSV if missing
✅ Logs all closed deals (24h window)
✅ Appends daily summary with expectancy analytics
"""

import csv
import datetime as dt
import logging
import os
import sys
from collections.abc import Iterable
from typing import Any

import MetaTrader5 as _mt5
from dotenv import load_dotenv

mt5: Any = _mt5  # type: ignore

# ------------------------------------------------------------
# ENV + LOGGING
# ------------------------------------------------------------
asset = (sys.argv[1] if len(sys.argv) > 1 else "FX").upper()
env_path = f"app/env/.merged/env.{asset}.merged.env"
if not os.path.exists(env_path):
    print(f"❌ Env file not found for asset {asset}: {env_path}")
    sys.exit(1)
load_dotenv(dotenv_path=env_path)

ASSET = os.getenv("ASSET", asset)
LOG_DIR = os.getenv("LOG_DIR", f"logs/{ASSET.lower()}")
os.makedirs(LOG_DIR, exist_ok=True)
CSV_FILE = os.path.join(LOG_DIR, f"{ASSET.lower()}.trades.csv")
LOG_FILE = os.path.join(LOG_DIR, f"{ASSET.lower()}.trades.log")

logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)
logger.info(f"=== End Trade Logger started for {ASSET} ===")


# ------------------------------------------------------------
# MT5 INIT
# ------------------------------------------------------------
def init_mt5() -> bool:
    path = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    ok = mt5.initialize(path)
    if not ok:
        print("❌ MT5 init failed:", mt5.last_error())
        return False
    acc = mt5.account_info()
    if acc:
        print(f"✅ MT5 Connected: {acc.login} | {acc.server} | Bal={acc.balance:.2f}")
    else:
        print("⚠️ No active account.")
    return True


if not init_mt5():
    sys.exit(1)

# ------------------------------------------------------------
# CSV HEADER
# ------------------------------------------------------------
HEADER = ["DealID", "Date", "Symbol", "Volume", "Price", "Profit", "Commission", "Swap", "Comment"]


def ensure_csv_header():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            csv.writer(f).writerow(HEADER)
        print(f"🆕 Created {CSV_FILE}")


def existing_ids() -> set[str]:
    if not os.path.exists(CSV_FILE):
        return set()
    with open(CSV_FILE, newline="") as f:
        return {row["DealID"] for row in csv.DictReader(f) if row.get("DealID")}


# ------------------------------------------------------------
# FETCH DEALS
# ------------------------------------------------------------
def get_closed_deals(hours_back=24):
    now = dt.datetime.now()
    frm = now - dt.timedelta(hours=hours_back)
    deals = mt5.history_deals_get(frm, now)
    if not deals:
        print("No deals found.")
        return []
    return [d for d in deals if getattr(d, "entry", 0) == 1]  # only exit deals


# ------------------------------------------------------------
# APPEND DEALS
# ------------------------------------------------------------
def append_deals(deals, logged_ids):
    new, p_sum, wins = 0, 0.0, 0
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        for d in deals:
            deal_id = str(getattr(d, "ticket", ""))
            if deal_id in logged_ids:
                continue
            symbol = getattr(d, "symbol", "")
            vol = getattr(d, "volume", 0.0)
            price = getattr(d, "price", 0.0)
            profit = getattr(d, "profit", 0.0)
            comm = getattr(d, "commission", 0.0)
            swap = getattr(d, "swap", 0.0)
            comment = getattr(d, "comment", "")
            time_ = dt.datetime.fromtimestamp(getattr(d, "time", 0))
            w.writerow(
                [
                    deal_id,
                    time_.strftime("%Y-%m-%d %H:%M:%S"),
                    symbol,
                    vol,
                    price,
                    profit,
                    comm,
                    swap,
                    comment,
                ]
            )
            logger.info(f"[CLOSED] {symbol} vol={vol} price={price} profit={profit}")
            new += 1
            p_sum += profit
            if profit > 0:
                wins += 1
    if new:
        win_pct = 100 * wins / new
        print(f"✅ Logged {new} deals → Net P/L {p_sum:.2f} ({win_pct:.1f}% win rate)")
    else:
        print("No new deals to log.")
    return new


# ------------------------------------------------------------
# SUMMARY CALC
# ------------------------------------------------------------
def summarize_day(rows: Iterable[dict[str, str]], date_str: str) -> dict[str, int | float | str]:
    profits, wins, losses = [], [], []
    comm_sum = swap_sum = 0.0
    for r in rows:
        if r.get("DealID", "").startswith("SUMMARY-"):
            continue
        if not r.get("Date") or not r["Date"].startswith(date_str):
            continue
        p = float(r.get("Profit", 0) or 0)
        profits.append(p)
        if p > 0:
            wins.append(p)
        elif p < 0:
            losses.append(p)
        comm_sum += float(r.get("Commission", 0) or 0)
        swap_sum += float(r.get("Swap", 0) or 0)
    total = len(profits)
    if total == 0:
        return {}
    win_rate = len(wins) / total
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
    net = sum(profits) + comm_sum + swap_sum
    return {
        "date": date_str,
        "trades": total,
        "win%": win_rate * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "commission": comm_sum,
        "swap": swap_sum,
        "net": net,
    }


def append_daily_summary():
    if not os.path.exists(CSV_FILE):
        return
    with open(CSV_FILE, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    today = dt.datetime.now().strftime("%Y-%m-%d")
    dates = sorted({r["Date"][:10] for r in rows if r.get("Date")})
    existing = {r["DealID"] for r in rows if r["DealID"].startswith("SUMMARY-")}
    new = 0
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        for d in dates:
            if d == today:
                continue
            sid = f"SUMMARY-{d}"
            if sid in existing:
                continue
            s = summarize_day(rows, d)
            if not s:
                continue
            w.writerow(
                [
                    sid,
                    f"{d} 23:59:59",
                    "SUMMARY",
                    "",
                    "",
                    "",
                    f"{s['net']:.2f}",
                    f"{s['commission']:.2f}",
                    f"{s['swap']:.2f}",
                    f"trades={s['trades']}, win%={s['win%']:.1f}, "
                    f"avgWin={s['avg_win']:.2f}, avgLoss={s['avg_loss']:.2f}, "
                    f"exp={s['expectancy']:.2f}",
                ]
            )
            logger.info(f"📊 {d} → {s}")
            print(
                f"📊 {d} → Trades={s['trades']} | Win%={s['win%']:.1f} | "
                f"Exp={s['expectancy']:.2f} | Net={s['net']:.2f}"
            )
            new += 1
    if new:
        print(f"🧾 Daily summaries appended: {new}")
        logger.info(f"Daily summaries appended: {new}")


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    ensure_csv_header()
    logged_ids = existing_ids()
    deals = get_closed_deals()
    if deals:
        append_deals(deals, logged_ids)
    append_daily_summary()


if __name__ == "__main__":
    main()
    mt5.shutdown()
    print(f"✅ End Trade Logger finished for {ASSET}")
