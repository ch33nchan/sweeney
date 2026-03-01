from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Action, FeatureVector, LLMDecision


class LLMError(RuntimeError):
    pass


@dataclass
class GeminiClient:
    api_key: str
    model: str

    def _endpoint(self) -> str:
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )

    def _prompt(self, symbol: str, features: FeatureVector) -> str:
        return (
            "You are a strict crypto signal model. Reply only as JSON object with keys "
            "symbol, action (BUY|SELL|NO_TRADE), confidence (0..1), time_horizon_min (int), "
            "reason (<=280 chars). No markdown. "
            f"Input: symbol={symbol}, trend={features.trend:.6f}, volatility={features.volatility:.6f}, "
            f"spread_bps={features.spread_bps:.4f}, volume_zscore={features.volume_zscore:.6f}."
        )

    def decide(self, symbol: str, features: FeatureVector) -> LLMDecision:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is empty")

        payload = {
            "contents": [{"parts": [{"text": self._prompt(symbol, features)}]}],
            "generationConfig": {"temperature": 0.1},
        }
        req = Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc

        text = self._extract_text(data)
        return validate_llm_json(symbol, text)

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        candidates = response.get("candidates") or []
        if not candidates:
            raise LLMError("Gemini response has no candidates")
        content = candidates[0].get("content", {})
        parts = content.get("parts") or []
        if not parts:
            raise LLMError("Gemini response has no text parts")
        text = parts[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise LLMError("Gemini text part is empty")
        return text.strip()



def validate_llm_json(default_symbol: str, raw_text: str) -> LLMDecision:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LLMError("LLM output is not valid JSON") from exc

    symbol = str(payload.get("symbol") or default_symbol)
    action_raw = str(payload.get("action") or "NO_TRADE").upper()
    confidence_raw = payload.get("confidence", 0.0)
    time_horizon = int(payload.get("time_horizon_min", 5))
    reason = str(payload.get("reason") or "No reason")[:280]

    if action_raw not in {"BUY", "SELL", "NO_TRADE"}:
        raise LLMError("LLM output action invalid")

    confidence = float(confidence_raw)
    if confidence < 0.0 or confidence > 1.0:
        raise LLMError("LLM output confidence out of range")

    return LLMDecision(
        symbol=symbol,
        action=Action(action_raw),
        confidence=confidence,
        time_horizon_min=time_horizon,
        reason=reason,
    )
