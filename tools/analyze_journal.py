# tools/analyze_journal.py
import datetime as dt
import json
import os
from collections import defaultdict

JOURNAL_DIR = os.environ.get("JOURNAL_DIR", "app/journal")
TODAY = dt.datetime.now().strftime("%Y-%m-%d")


def load_trades(date=TODAY, limit=None):
    path = os.path.join(JOURNAL_DIR, f"trades-{date}.json")
    trades = []
    if not os.path.exists(path):
        print(f"[warn] No journal for {date}: {path}")
        return trades
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except Exception:
                pass
    if limit:
        trades = trades[-limit:]
    return trades


def kpis(trades):
    # Expect entries to have: status ('ok'/'error'), symbol, side, price, sl, tp, profit (if you add later)
    n = len(trades)
    ok = sum(1 for t in trades if str(t.get("status")) == "ok")
    err = n - ok
    by_symbol = defaultdict(int)
    for t in trades:
        by_symbol[t.get("symbol", "?")] += 1

    # Profit stats if available
    profits = [float(t.get("profit", 0)) for t in trades if "profit" in t]
    gross_win = sum(p for p in profits if p > 0)
    gross_loss = -sum(p for p in profits if p < 0)
    win_rate = (sum(1 for p in profits if p > 0) / len(profits) * 100) if profits else 0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None
    net = sum(profits) if profits else 0

    # Drawdown on cumulative PnL if present
    dd = 0.0
    if profits:
        equity = 0
        peak = 0
        maxdd = 0
        for p in profits:
            equity += p
            peak = max(peak, equity)
            maxdd = min(maxdd, equity - peak)
        dd = maxdd

    return {
        "trades": n,
        "ok": ok,
        "error": err,
        "by_symbol": dict(by_symbol),
        "profit_samples": len(profits),
        "net_pnl": net,
        "win_rate_pct": win_rate,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "max_drawdown": dd,
    }


def print_report(k):
    print("\n=== DAILY PERFORMANCE ===")
    for k_, v in k.items():
        print(f"{k_:>15}: {v}")
    print("=========================\n")


if __name__ == "__main__":
    trades = load_trades()
    ks = kpis(trades)
    print_report(ks)
    # Optional: equity curve plot if matplotlib is installed and profit field exists
    try:
        profits = [float(t.get("profit", 0)) for t in trades if "profit" in t]
        if profits:
            import itertools

            import matplotlib.pyplot as plt

            equity = list(itertools.accumulate(profits))
            plt.figure()
            plt.plot(equity)
            plt.title(f"Equity Curve {TODAY}")
            plt.xlabel("Trade #")
            plt.ylabel("Cumulative PnL")
            plt.show()
    except Exception as e:
        print(f"[info] Skipping plot: {e}")
