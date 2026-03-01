from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .llm import LLMError
from .models import Action, FeatureVector, LLMDecision, MarketSnapshot, StrategySignal


class StrategyError(RuntimeError):
    pass


class DecisionModel:
    def decide(self, symbol: str, features: FeatureVector) -> LLMDecision:
        raise NotImplementedError


@dataclass
class StrategyEngine:
    model: DecisionModel
    confidence_floor: float

    def compute_features(self, snap: MarketSnapshot) -> FeatureVector:
        closes = [c["close"] for c in snap.candles if "close" in c]
        volumes = [c.get("volume", 0.0) for c in snap.candles]

        if len(closes) < 20:
            raise StrategyError("Not enough candles to compute features")

        first = closes[0]
        last = closes[-1]
        trend = ((last - first) / first) if first > 0 else 0.0

        returns: list[float] = []
        for idx in range(1, len(closes)):
            prev = closes[idx - 1]
            if prev <= 0:
                continue
            returns.append((closes[idx] - prev) / prev)

        volatility = statistics.pstdev(returns) if returns else 0.0
        spread_bps = ((snap.ask - snap.bid) / snap.last) * 10_000 if snap.last > 0 else math.inf

        volume_mean = statistics.fmean(volumes) if volumes else 0.0
        volume_std = statistics.pstdev(volumes) if len(volumes) > 1 else 0.0
        vol_latest = volumes[-1] if volumes else 0.0
        volume_z = ((vol_latest - volume_mean) / volume_std) if volume_std > 0 else 0.0

        return FeatureVector(
            trend=trend,
            volatility=volatility,
            spread_bps=spread_bps,
            volume_zscore=volume_z,
        )

    def build_signal(self, snap: MarketSnapshot) -> StrategySignal:
        features = self.compute_features(snap)

        try:
            decision = self.model.decide(snap.symbol, features)
        except LLMError:
            decision = LLMDecision(
                symbol=snap.symbol,
                action=Action.NO_TRADE,
                confidence=0.0,
                time_horizon_min=5,
                reason="LLM unavailable or malformed output",
            )

        # Deterministic trend alignment gate.
        if decision.action == Action.BUY and features.trend < 0:
            return StrategySignal(
                symbol=snap.symbol,
                action=Action.NO_TRADE,
                confidence=0.0,
                reason="Trend filter blocked BUY",
                features=features,
            )
        if decision.action == Action.SELL and features.trend > 0:
            return StrategySignal(
                symbol=snap.symbol,
                action=Action.NO_TRADE,
                confidence=0.0,
                reason="Trend filter blocked SELL",
                features=features,
            )

        if decision.confidence < self.confidence_floor:
            return StrategySignal(
                symbol=snap.symbol,
                action=Action.NO_TRADE,
                confidence=decision.confidence,
                reason="Confidence below floor",
                features=features,
            )

        return StrategySignal(
            symbol=snap.symbol,
            action=decision.action,
            confidence=decision.confidence,
            reason=decision.reason,
            features=features,
        )
