from __future__ import annotations

from datetime import datetime, timezone
import unittest

from openclaw_bot.models import Action, FeatureVector, LLMDecision, MarketSnapshot
from openclaw_bot.strategy import StrategyEngine


class DummyModel:
    def __init__(self, decision: LLMDecision) -> None:
        self._decision = decision

    def decide(self, symbol: str, features: FeatureVector) -> LLMDecision:
        return self._decision



def _snapshot(trend_up: bool = True) -> MarketSnapshot:
    closes = []
    base = 100.0
    for idx in range(30):
        price = base + idx if trend_up else base - idx
        closes.append({"close": price, "volume": 10 + idx})
    return MarketSnapshot(
        symbol="BTC/USDT",
        bid=129.0,
        ask=130.0,
        last=129.5,
        candles=closes,
        volume_24h=1000.0,
        timestamp=datetime.now(timezone.utc),
    )


class StrategyTests(unittest.TestCase):
    def test_trend_alignment_blocks_counter_trend_buy(self) -> None:
        decision = LLMDecision(
            symbol="BTC/USDT",
            action=Action.BUY,
            confidence=0.9,
            time_horizon_min=5,
            reason="buy",
        )
        engine = StrategyEngine(model=DummyModel(decision), confidence_floor=0.72)
        signal = engine.build_signal(_snapshot(trend_up=False))
        self.assertEqual(signal.action, Action.NO_TRADE)
        self.assertIn("Trend filter", signal.reason)

    def test_confidence_floor_blocks_low_confidence(self) -> None:
        decision = LLMDecision(
            symbol="BTC/USDT",
            action=Action.BUY,
            confidence=0.5,
            time_horizon_min=5,
            reason="weak",
        )
        engine = StrategyEngine(model=DummyModel(decision), confidence_floor=0.72)
        signal = engine.build_signal(_snapshot(trend_up=True))
        self.assertEqual(signal.action, Action.NO_TRADE)
        self.assertEqual(signal.reason, "Confidence below floor")


if __name__ == "__main__":
    unittest.main()
