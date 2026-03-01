from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from openclaw_bot.models import Action, FeatureVector, StrategySignal
from openclaw_bot.risk import PortfolioState, RiskEngine, RiskPolicy



def _signal(action: Action = Action.BUY) -> StrategySignal:
    return StrategySignal(
        symbol="BTC/USDT",
        action=action,
        confidence=0.9,
        reason="ok",
        features=FeatureVector(trend=0.1, volatility=0.001, spread_bps=2.0, volume_zscore=1.0),
    )



def _engine() -> RiskEngine:
    policy = RiskPolicy(
        risk_per_trade=0.005,
        daily_max_loss=0.02,
        max_concurrent_positions=1,
        cooldown_min=10,
        max_spread_bps=8,
        max_fee_bps=12,
    )
    return RiskEngine(policy)


class RiskTests(unittest.TestCase):
    def test_blocks_when_daily_loss_limit_hit(self) -> None:
        state = PortfolioState(equity=20, day_pnl_pct=-0.03, open_positions=0, last_closed_trade_at=None)
        decision, intent = _engine().evaluate(_signal(), state, mark_price=100, estimated_fee_bps=5)
        self.assertEqual(decision.decision.value, "BLOCK")
        self.assertEqual(decision.block_reason.value, "RISK_LIMIT")
        self.assertIsNone(intent)

    def test_blocks_on_cooldown(self) -> None:
        recent = datetime.now(timezone.utc) - timedelta(minutes=3)
        state = PortfolioState(equity=20, day_pnl_pct=0, open_positions=0, last_closed_trade_at=recent)
        decision, _ = _engine().evaluate(_signal(), state, mark_price=100, estimated_fee_bps=5)
        self.assertEqual(decision.block_reason.value, "COOLDOWN")


if __name__ == "__main__":
    unittest.main()
