# debug_plot.py
from __future__ import annotations

import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from app.market.data import get_rates  # uses your MT5 pipe

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    # Wilder’s smoothing
    roll_up = up.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    roll_dn = dn.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = roll_up / (roll_dn.replace(0, np.nan))
    return 100.0 - (100.0 / (1.0 + rs))

def main():
    p = argparse.ArgumentParser(description="Quick visual check of bars + EMA + RSI")
    p.add_argument("--symbol", default="XAUUSD-ECNc")
    p.add_argument("--tf", default="M15")
    p.add_argument("--bars", type=int, default=300)
    p.add_argument("--tail", type=int, default=120, help="how many candles to show")
    p.add_argument("--save", action="store_true", help="save PNGs next to script")
    args = p.parse_args()

    df = get_rates(args.symbol, args.tf, args.bars)
    if df is None or df.empty:
        print(f"[debug_plot] no data for {args.symbol} {args.tf}")
        return

    # Ensure expected columns
    for col in ("time", "open", "high", "low", "close"):
        if col not in df.columns:
            print(f"[debug_plot] missing column: {col}")
            return

    df = df.copy()
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi14"] = rsi(df["close"], 14)

    # Focus on most recent N candles for readability
    plot = df.tail(args.tail)

    title_base = f"{args.symbol} {args.tf}  (len={len(df)})"

    # ---- Figure 1: Price + EMA50/EMA200 ----
    plt.figure(figsize=(12, 6))
    plt.plot(plot["time"], plot["close"], label="Close")
    plt.plot(plot["time"], plot["ema50"], label="EMA50")
    plt.plot(plot["time"], plot["ema200"], label="EMA200")
    plt.title(f"{title_base} — Price & EMAs")
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.legend(loc="best")
    plt.tight_layout()
    if args.save:
        plt.savefig(f"plot_{args.symbol}_{args.tf}_price.png", dpi=120)
    plt.show()

    # ---- Figure 2: RSI(14) ----
    plt.figure(figsize=(12, 3.5))
    plt.plot(plot["time"], plot["rsi14"], label="RSI(14)")
    plt.axhline(70, linestyle="--")
    plt.axhline(50, linestyle="--")
    plt.axhline(30, linestyle="--")
    plt.title(f"{title_base} — RSI(14)")
    plt.xlabel("Time")
    plt.ylabel("RSI")
    plt.tight_layout()
    if args.save:
        plt.savefig(f"plot_{args.symbol}_{args.tf}_rsi.png", dpi=120)
    plt.show()

    # Print the latest snapshot used by the bot
    last = df.iloc[-1]
    print("\n=== Latest snapshot ===")
    print(
        {
            "symbol": args.symbol,
            "tf": args.tf,
            "price": float(last["close"]),
            "ema50": float(last["ema50"]),
            "ema200": float(last["ema200"]),
            "rsi14": float(last["rsi14"]),
            "len": len(df),
        }
    )

if __name__ == "__main__":
    main()
