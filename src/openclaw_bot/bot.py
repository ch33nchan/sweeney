from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import Settings
from .execution import ExchangeClient
from .market_data import MarketDataService
from .models import Action, BotStatus, CommandEnvelope, CommandType, StrategySignal
from .notifier import Notifier
from .risk import PortfolioState, RiskEngine, RiskPolicy
from .storage import SQLiteStore
from .strategy import StrategyEngine

logger = logging.getLogger(__name__)


@dataclass
class BotState:
    paused: bool = False
    risk_per_trade_override: float | None = None
    last_signal: StrategySignal | None = None
    last_heartbeat_at: datetime | None = None


class TradingBot:
    def __init__(
        self,
        settings: Settings,
        market_data: MarketDataService,
        strategy: StrategyEngine,
        risk_engine: RiskEngine,
        exchange: ExchangeClient,
        store: SQLiteStore,
        notifier: Notifier,
    ) -> None:
        self.settings = settings
        self.market_data = market_data
        self.strategy = strategy
        self.risk_engine = risk_engine
        self.exchange = exchange
        self.store = store
        self.notifier = notifier
        self.state = BotState()

    def apply_command(self, cmd: CommandEnvelope) -> str:
        self.store.save_command(cmd.command_type.value, cmd.issued_by, cmd.params)

        if cmd.command_type == CommandType.STATUS:
            status = self.status()
            return (
                f"paused={status.bot_paused} equity={status.equity:.2f} "
                f"day_pnl={status.day_pnl_pct:.3f} open_positions={status.open_positions}"
            )
        if cmd.command_type == CommandType.PAUSE:
            self.state.paused = True
            return "Bot paused"
        if cmd.command_type == CommandType.RESUME:
            self.state.paused = False
            return "Bot resumed"
        if cmd.command_type == CommandType.CLOSE_ALL:
            closed = self.exchange.close_all(self.settings.base_symbol)
            return f"close_all requested, positions closed={closed}"
        if cmd.command_type == CommandType.SET_RISK:
            new_risk = float(cmd.params["risk_per_trade"])
            self.state.risk_per_trade_override = new_risk
            self.risk_engine.policy = RiskPolicy(
                risk_per_trade=new_risk,
                daily_max_loss=self.risk_engine.policy.daily_max_loss,
                max_concurrent_positions=self.risk_engine.policy.max_concurrent_positions,
                cooldown_min=self.risk_engine.policy.cooldown_min,
                max_spread_bps=self.risk_engine.policy.max_spread_bps,
                max_fee_bps=self.risk_engine.policy.max_fee_bps,
            )
            return f"risk_per_trade updated to {new_risk:.4f}"

        return "Unsupported command"

    def status(self) -> BotStatus:
        equity = self.exchange.account_equity()
        open_positions = self.store.count_open_positions()
        day_pnl_pct = 0.0
        return BotStatus(
            bot_paused=self.state.paused,
            equity=equity,
            day_pnl_pct=day_pnl_pct,
            open_positions=open_positions,
            last_signal=self.state.last_signal,
        )

    def run_cycle(self) -> str:
        if self.state.paused:
            logger.info("Cycle skipped: bot paused")
            return "paused"

        snap = self.market_data.snapshot(self.settings.base_symbol, self.settings.timeframe)
        signal = self.strategy.build_signal(snap)
        self.state.last_signal = signal

        self.store.save_signal(
            symbol=signal.symbol,
            action=signal.action.value,
            confidence=signal.confidence,
            reason=signal.reason,
            features={
                "trend": signal.features.trend,
                "volatility": signal.features.volatility,
                "spread_bps": signal.features.spread_bps,
                "volume_zscore": signal.features.volume_zscore,
            },
        )

        equity = self.exchange.account_equity()
        day_pnl_pct = 0.0
        portfolio = PortfolioState(
            equity=equity,
            day_pnl_pct=day_pnl_pct,
            open_positions=self.store.count_open_positions(),
            last_closed_trade_at=self.store.last_closed_trade_time(),
        )

        decision, intent = self.risk_engine.evaluate(
            signal=signal,
            state=portfolio,
            mark_price=snap.last,
            estimated_fee_bps=10.0,
        )

        if decision.decision.value == "BLOCK":
            self.store.save_risk_event(decision.block_reason.value if decision.block_reason else "OTHER", decision.details)
            logger.info("Trade blocked: %s", decision.details)
            self._maybe_heartbeat(equity, day_pnl_pct)
            return f"blocked:{decision.details}"

        assert intent is not None
        order_id = self.exchange.place_order(intent)
        local_order_id = self.store.save_order(
            symbol=intent.symbol,
            side=intent.action.value,
            quantity=intent.quantity,
            price=intent.price,
            status="PLACED",
            exchange_order_id=order_id,
        )
        self.store.save_fill(local_order_id, intent.price, intent.quantity, fee=0.0)
        self.store.save_position(intent.symbol, intent.action.value, intent.quantity, intent.price, status="OPEN")

        text = (
            f"TRADE {intent.action.value} {intent.symbol} qty={intent.quantity} "
            f"price={intent.price} conf={intent.confidence:.2f}"
        )
        try:
            self.notifier.send_text(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Notifier failure: %s", exc)

        self._maybe_heartbeat(equity, day_pnl_pct)
        logger.info("Order placed %s", order_id)
        return f"executed:{order_id}"

    def _maybe_heartbeat(self, equity: float, day_pnl_pct: float) -> None:
        now = datetime.now(timezone.utc)
        if self.state.last_heartbeat_at and now - self.state.last_heartbeat_at < timedelta(minutes=15):
            return
        self.store.save_pnl_snapshot(equity, day_pnl_pct)
        self.state.last_heartbeat_at = now
        try:
            self.notifier.send_text(
                f"HEARTBEAT paused={self.state.paused} equity={equity:.2f} day_pnl={day_pnl_pct:.3f}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Heartbeat notify failure: %s", exc)
