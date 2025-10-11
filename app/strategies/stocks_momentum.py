# app/strategies/stocks_momentum.py
from __future__ import annotations

from typing import Any

import pandas as pd

from app.strategies.equities_momentum import equities_momentum_signal
from app.strategies.fx_momentum import momentum_signal as fx_momentum_signal
from app.strategies.indices_momentum import indices_momentum_signal
from app.strategies.xau_momentum import xau_momentum_signal


def stocks_momentum_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    env: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Dispatcher: route stocks/indices/fx/xau symbols to the right momentum strategy.
    """

    symu = symbol.upper()

    if symu.endswith(("USD", "JPY", "EUR", "GBP")):
        # FX → needs (symbol, timeframe, df)
        return fx_momentum_signal(symbol, timeframe, df)

    if "XAU" in symu or "GOLD" in symu:
        # Gold → needs (df, symbol, env)
        return xau_momentum_signal(df, symbol, env)

    if symu in ("US30", "NAS100", "GER40", "SPX500"):
        # Indices → needs (df, symbol, env)
        return indices_momentum_signal(df, symbol, env)

    # Default: equities → needs (symbol, timeframe, df)
    return equities_momentum_signal(symbol, timeframe, df)
