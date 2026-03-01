from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class CommandType(str, Enum):
    STATUS = "STATUS"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CLOSE_ALL = "CLOSE_ALL"
    SET_RISK = "SET_RISK"


class Decision(str, Enum):
    EXECUTE = "EXECUTE"
    BLOCK = "BLOCK"


class BlockReason(str, Enum):
    RISK_LIMIT = "RISK_LIMIT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    API_HEALTH = "API_HEALTH"
    COOLDOWN = "COOLDOWN"
    MIN_NOTIONAL = "MIN_NOTIONAL"
    OTHER = "OTHER"


@dataclass
class MarketSnapshot:
    symbol: str
    bid: float
    ask: float
    last: float
    candles: list[dict[str, float]]
    volume_24h: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FeatureVector:
    trend: float
    volatility: float
    spread_bps: float
    volume_zscore: float


@dataclass
class LLMDecision:
    symbol: str
    action: Action
    confidence: float
    time_horizon_min: int
    reason: str


@dataclass
class StrategySignal:
    symbol: str
    action: Action
    confidence: float
    reason: str
    features: FeatureVector
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TradeIntent:
    symbol: str
    action: Action
    quantity: float
    price: float
    stop_loss: float
    take_profit: float
    confidence: float


@dataclass
class RiskDecision:
    decision: Decision
    block_reason: BlockReason | None
    details: str


@dataclass
class CommandEnvelope:
    command_type: CommandType
    issued_by: str
    issued_at: datetime
    params: dict[str, Any]


@dataclass
class BotStatus:
    bot_paused: bool
    equity: float
    day_pnl_pct: float
    open_positions: int
    last_signal: StrategySignal | None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
