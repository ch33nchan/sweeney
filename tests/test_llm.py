from __future__ import annotations

import unittest

from openclaw_bot.llm import LLMError, validate_llm_json
from openclaw_bot.models import Action


class LLMValidationTests(unittest.TestCase):
    def test_validate_llm_json_happy_path(self) -> None:
        raw = (
            '{"symbol":"BTC/USDT","action":"BUY","confidence":0.81,'
            '"time_horizon_min":10,"reason":"signal"}'
        )
        decision = validate_llm_json("BTC/USDT", raw)
        self.assertEqual(decision.action, Action.BUY)
        self.assertEqual(decision.confidence, 0.81)

    def test_validate_llm_json_rejects_bad_confidence(self) -> None:
        raw = '{"symbol":"BTC/USDT","action":"BUY","confidence":1.2,"time_horizon_min":5,"reason":"x"}'
        with self.assertRaises(LLMError):
            validate_llm_json("BTC/USDT", raw)


if __name__ == "__main__":
    unittest.main()
