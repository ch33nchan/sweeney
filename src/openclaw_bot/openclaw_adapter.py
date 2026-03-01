from __future__ import annotations

from dataclasses import dataclass

from .models import FeatureVector, LLMDecision


@dataclass
class OpenClawDecisionBridge:
    """Placeholder for native OpenClaw tool-orchestration integration.

    In this scaffold the class delegates to an injected decision model.
    """

    delegate: object

    def decide(self, symbol: str, features: FeatureVector) -> LLMDecision:
        return self.delegate.decide(symbol, features)
