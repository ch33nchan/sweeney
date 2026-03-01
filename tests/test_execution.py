from __future__ import annotations

import unittest

from openclaw_bot.execution import BybitRestClient, ExchangeError


class ExecutionTests(unittest.TestCase):
    def test_extract_equity_total_equity(self) -> None:
        result = {
            "list": [
                {
                    "totalEquity": "19.87",
                    "coin": [],
                }
            ]
        }
        value = BybitRestClient._extract_equity_from_wallet_result(result)
        self.assertEqual(value, 19.87)

    def test_extract_equity_coin_fallback(self) -> None:
        result = {
            "list": [
                {
                    "totalEquity": "0",
                    "coin": [{"coin": "USDT", "walletBalance": "20.3"}],
                }
            ]
        }
        value = BybitRestClient._extract_equity_from_wallet_result(result)
        self.assertEqual(value, 20.3)

    def test_extract_equity_raises_on_invalid_payload(self) -> None:
        with self.assertRaises(ExchangeError):
            BybitRestClient._extract_equity_from_wallet_result({"list": []})


if __name__ == "__main__":
    unittest.main()
