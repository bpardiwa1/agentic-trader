
from pydantic import BaseModel


class Signal(BaseModel):
    symbol: str
    timeframe: str = "H1"
    strategy_id: str
    side: str  # LONG | SHORT
    confidence: float = 0.6
    entry: float
    sl: float
    tp: float
    size: float = 0.0
    idempotency_key: str = ""


class Order(BaseModel):
    symbol: str
    side: str  # LONG | SHORT
    price: float
    sl_pips: float = 200.0
    tp_pips: float = 400.0
    size: float | None = None


class TradingViewAlert(BaseModel):
    symbol: str
    price: float
    time: str
    alert_name: str | None = None
    message: str | None = None
