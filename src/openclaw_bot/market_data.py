from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import MarketSnapshot


class MarketDataError(RuntimeError):
    pass


class ExchangeMarketClient:
    """Exchange data interface used by strategy engine."""

    def fetch_orderbook_top(self, symbol: str) -> tuple[float, float]:
        raise NotImplementedError

    def fetch_last_price(self, symbol: str) -> float:
        raise NotImplementedError

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 100) -> list[dict[str, float]]:
        raise NotImplementedError

    def fetch_volume_24h(self, symbol: str) -> float:
        raise NotImplementedError


@dataclass
class CoinGeckoClient:
    base_url: str

    def fetch_macro_context(self, coin_id: str = "bitcoin") -> dict[str, float]:
        url = f"{self.base_url}/coins/{coin_id}"
        req = Request(url, headers={"accept": "application/json"})
        try:
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise MarketDataError(f"CoinGecko request failed: {exc}") from exc

        mkt = data.get("market_data", {})
        return {
            "price_change_pct_24h": float(mkt.get("price_change_percentage_24h", 0.0) or 0.0),
            "market_cap_change_pct_24h": float(
                mkt.get("market_cap_change_percentage_24h", 0.0) or 0.0
            ),
        }


class MarketDataService:
    def __init__(self, exchange: ExchangeMarketClient) -> None:
        self.exchange = exchange

    def snapshot(self, symbol: str, timeframe: str, candle_limit: int = 100) -> MarketSnapshot:
        bid, ask = self.exchange.fetch_orderbook_top(symbol)
        last = self.exchange.fetch_last_price(symbol)
        candles = self.exchange.fetch_candles(symbol, timeframe, candle_limit)
        volume_24h = self.exchange.fetch_volume_24h(symbol)
        return MarketSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            candles=candles,
            volume_24h=volume_24h,
            timestamp=datetime.now(timezone.utc),
        )
