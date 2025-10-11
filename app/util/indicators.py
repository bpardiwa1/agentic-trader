# app/util/indicators.py


import numpy as np

# -----------------------------
# Constants
# -----------------------------
EPSILON = 1e-12  # to avoid divide-by-zero


def compute_ema(prices: list[float], period: int) -> float:
    """
    Compute Exponential Moving Average (EMA).

    Args:
        prices: list of price values (latest at the end).
        period: EMA period.

    Returns:
        float: EMA value.
    """
    if len(prices) < period:
        return float("nan")

    # smoothing factor
    k = 2 / (period + 1)

    # start with simple average of first 'period' prices
    ema = float(np.mean(prices[:period]))

    # iterate through remaining prices
    for price in prices[period:]:
        ema = (price - ema) * k + ema

    return float(ema)


def compute_rsi(prices: list[float], period: int = 14) -> float:
    """
    Compute Relative Strength Index (RSI) using Wilder's smoothing.

    Args:
        prices: list of price values (latest at the end).
        period: lookback period (default 14).

    Returns:
        float: RSI value.
    """
    if len(prices) < period + 1:
        return float("nan")

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # initial average gain/loss
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    # Wilder’s smoothing
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    rs = avg_gain / (avg_loss + EPSILON)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return float(rsi)
