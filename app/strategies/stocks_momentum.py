# app/agents/auto_decider.py
from collections.abc import Callable
from typing import Any

from app.strategies import fx_momentum, index_breakout, stocks_momentum, xau_momentum

# registry: first match that returns True wins
REGISTRY: list[
    tuple[Callable[[str], bool], Callable[[str, str], dict[str, Any] | None]]
] = [
    (lambda s: s.upper().startswith("XAU"), xau_momentum.signal),  # Gold
    (lambda s: s.upper().startswith("EURUSD"), fx_momentum.signal),  # EURUSD FX
    (lambda s: s in ("MSFT", "AAPL", "NVDA"), stocks_momentum.signal),  # Stocks
    (lambda s: s.startswith("NAS100"), index_breakout.signal),  # Index
]


def decide_signal(
    symbol: str, timeframe: str = "M15", agent: str = "auto"
) -> dict[str, Any] | None:
    sym = symbol.upper()
    for predicate, strat in REGISTRY:
        if predicate(sym):
            return strat(symbol, timeframe)
    # fallback: FX
    return fx_momentum.signal(symbol, timeframe)
