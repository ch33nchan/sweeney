from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import (
    Action,
    BlockReason,
    Decision,
    RiskDecision,
    StrategySignal,
    TradeIntent,
)


@dataclass
class RiskPolicy:
    risk_per_trade: float
    daily_max_loss: float
    max_concurrent_positions: int
    cooldown_min: int
    max_spread_bps: float
    max_fee_bps: float


@dataclass
class PortfolioState:
    equity: float
    day_pnl_pct: float
    open_positions: int
    last_closed_trade_at: datetime | None


class RiskEngine:
    def __init__(self, policy: RiskPolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        signal: StrategySignal,
        state: PortfolioState,
        mark_price: float,
        estimated_fee_bps: float,
    ) -> tuple[RiskDecision, TradeIntent | None]:
        if signal.action == Action.NO_TRADE:
            return RiskDecision(Decision.BLOCK, BlockReason.OTHER, "No trade signal"), None

        if state.day_pnl_pct <= -abs(self.policy.daily_max_loss):
            return (
                RiskDecision(Decision.BLOCK, BlockReason.RISK_LIMIT, "Daily loss limit reached"),
                None,
            )

        if state.open_positions >= self.policy.max_concurrent_positions:
            return (
                RiskDecision(Decision.BLOCK, BlockReason.RISK_LIMIT, "Max open positions reached"),
                None,
            )

        if state.last_closed_trade_at is not None:
            min_next = state.last_closed_trade_at + timedelta(minutes=self.policy.cooldown_min)
            if datetime.now(timezone.utc) < min_next:
                return RiskDecision(Decision.BLOCK, BlockReason.COOLDOWN, "Cooldown active"), None

        if signal.features.spread_bps > self.policy.max_spread_bps:
            return RiskDecision(Decision.BLOCK, BlockReason.OTHER, "Spread too wide"), None

        if estimated_fee_bps > self.policy.max_fee_bps:
            return RiskDecision(Decision.BLOCK, BlockReason.OTHER, "Fee estimate too high"), None

        quantity = self.position_size(state.equity, mark_price)
        if quantity <= 0:
            return RiskDecision(Decision.BLOCK, BlockReason.MIN_NOTIONAL, "Below min notional"), None

        stop_loss, take_profit = self._sl_tp(signal.action, mark_price)
        intent = TradeIntent(
            symbol=signal.symbol,
            action=signal.action,
            quantity=quantity,
            price=mark_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=signal.confidence,
        )
        return RiskDecision(Decision.EXECUTE, None, "Passed risk checks"), intent

    def position_size(self, equity: float, mark_price: float) -> float:
        if equity <= 0 or mark_price <= 0:
            return 0.0
        risk_capital = equity * self.policy.risk_per_trade
        # Approximate 1% stop distance in spot mode.
        notional = risk_capital / 0.01
        if notional < 5:
            return 0.0
        return round(notional / mark_price, 8)

    @staticmethod
    def _sl_tp(action: Action, price: float) -> tuple[float, float]:
        if action == Action.BUY:
            return round(price * 0.99, 2), round(price * 1.015, 2)
        return round(price * 1.01, 2), round(price * 0.985, 2)
