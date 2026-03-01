from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_data import ExchangeMarketClient, MarketDataError


@dataclass
class BybitPublicMarketClient(ExchangeMarketClient):
    testnet: bool = True

    @property
    def base_url(self) -> str:
        return "https://api-testnet.bybit.com" if self.testnet else "https://api.bybit.com"

    def _get(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        req = Request(url, headers={"accept": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise MarketDataError(f"Bybit GET failed: {exc}") from exc

    @staticmethod
    def _fmt_symbol(symbol: str) -> str:
        return symbol.replace("/", "")

    def fetch_orderbook_top(self, symbol: str) -> tuple[float, float]:
        data = self._get(
            "/v5/market/orderbook",
            {"category": "spot", "symbol": self._fmt_symbol(symbol), "limit": "1"},
        )
        result = data.get("result", {})
        bid = float(result.get("b", [[0]])[0][0])
        ask = float(result.get("a", [[0]])[0][0])
        return bid, ask

    def fetch_last_price(self, symbol: str) -> float:
        data = self._get(
            "/v5/market/tickers",
            {"category": "spot", "symbol": self._fmt_symbol(symbol)},
        )
        lst = data.get("result", {}).get("list", [{}])
        return float(lst[0].get("lastPrice", 0.0))

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 100) -> list[dict[str, float]]:
        interval = "1" if timeframe == "1m" else "5"
        data = self._get(
            "/v5/market/kline",
            {
                "category": "spot",
                "symbol": self._fmt_symbol(symbol),
                "interval": interval,
                "limit": str(limit),
            },
        )
        rows = data.get("result", {}).get("list", [])
        candles: list[dict[str, float]] = []
        for row in reversed(rows):
            candles.append(
                {
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        return candles

    def fetch_volume_24h(self, symbol: str) -> float:
        data = self._get(
            "/v5/market/tickers",
            {"category": "spot", "symbol": self._fmt_symbol(symbol)},
        )
        lst = data.get("result", {}).get("list", [{}])
        return float(lst[0].get("turnover24h", 0.0))
