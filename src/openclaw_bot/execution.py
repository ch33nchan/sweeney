from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Action, TradeIntent


class ExchangeError(RuntimeError):
    pass


class ExchangeClient:
    def account_equity(self) -> float:
        raise NotImplementedError

    def place_order(self, intent: TradeIntent) -> str:
        raise NotImplementedError

    def close_all(self, symbol: str) -> int:
        raise NotImplementedError


@dataclass
class PaperExchangeClient(ExchangeClient):
    equity_usd: float = 20.0

    def account_equity(self) -> float:
        return self.equity_usd

    def place_order(self, intent: TradeIntent) -> str:
        side = "buy" if intent.action == Action.BUY else "sell"
        return f"paper-{side}-{int(time.time() * 1000)}"

    def close_all(self, symbol: str) -> int:
        return 1


@dataclass
class BybitRestClient(ExchangeClient):
    api_key: str
    api_secret: str
    testnet: bool = True
    recv_window_ms: int = 5000

    @property
    def base_url(self) -> str:
        return "https://api-testnet.bybit.com" if self.testnet else "https://api.bybit.com"

    def _ensure_credentials(self) -> None:
        if not self.api_key or not self.api_secret:
            raise ExchangeError("Bybit API credentials missing")

    def _signature(self, timestamp_ms: str, payload: str) -> str:
        raw = f"{timestamp_ms}{self.api_key}{self.recv_window_ms}{payload}"
        return hmac.new(self.api_secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()

    def _headers(self, payload: str) -> dict[str, str]:
        self._ensure_credentials()
        ts = str(int(time.time() * 1000))
        sign = self._signature(ts, payload)
        return {
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-SIGN": sign,
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": str(self.recv_window_ms),
        }

    def _parse_response(self, data: dict) -> dict:
        code = data.get("retCode")
        if code not in (0, "0", None):
            raise ExchangeError(f"Bybit API error retCode={code} retMsg={data.get('retMsg')}")
        result = data.get("result")
        if not isinstance(result, dict):
            raise ExchangeError(f"Bybit response missing result object: {data}")
        return result

    def _get_private(self, path: str, params: dict[str, str]) -> dict:
        query = urlencode(sorted(params.items()))
        headers = self._headers(query)
        url = f"{self.base_url}{path}?{query}"
        req = Request(url, headers=headers, method="GET")

        try:
            with urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ExchangeError(f"Bybit GET failed: {exc}") from exc

        return self._parse_response(data)

    def _post_private(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"))
        headers = self._headers(body)
        headers["content-type"] = "application/json"
        url = f"{self.base_url}{path}"
        req = Request(url, data=body.encode("utf-8"), headers=headers, method="POST")

        try:
            with urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ExchangeError(f"Bybit POST failed: {exc}") from exc

        return self._parse_response(data)

    @staticmethod
    def _extract_equity_from_wallet_result(result: dict) -> float:
        rows = result.get("list")
        if not isinstance(rows, list) or not rows:
            raise ExchangeError(f"Bybit wallet result list missing: {result}")

        account = rows[0] if isinstance(rows[0], dict) else {}

        for key in ("totalEquity", "totalWalletBalance", "totalAvailableBalance"):
            raw = account.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value

        coin_rows = account.get("coin")
        if isinstance(coin_rows, list):
            for coin in coin_rows:
                if not isinstance(coin, dict):
                    continue
                if str(coin.get("coin", "")).upper() != "USDT":
                    continue
                for key in ("equity", "walletBalance", "availableToWithdraw"):
                    raw = coin.get(key)
                    if raw is None:
                        continue
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        continue
                    if value >= 0:
                        return value

        raise ExchangeError(f"Could not parse Bybit wallet equity from result: {result}")

    def account_equity(self) -> float:
        result = self._get_private(
            "/v5/account/wallet-balance",
            {
                "accountType": "UNIFIED",
                "coin": "USDT",
            },
        )
        return self._extract_equity_from_wallet_result(result)

    def place_order(self, intent: TradeIntent) -> str:
        side = "Buy" if intent.action == Action.BUY else "Sell"
        result = self._post_private(
            "/v5/order/create",
            {
                "category": "spot",
                "symbol": intent.symbol.replace("/", ""),
                "side": side,
                "orderType": "Market",
                "qty": str(intent.quantity),
                "timeInForce": "IOC",
            },
        )
        order_id = result.get("orderId")
        if not order_id:
            raise ExchangeError(f"Bybit missing orderId in create response: {result}")
        return str(order_id)

    def close_all(self, symbol: str) -> int:
        result = self._post_private(
            "/v5/order/cancel-all",
            {
                "category": "spot",
                "symbol": symbol.replace("/", ""),
            },
        )
        payload = result.get("list")
        if isinstance(payload, list):
            return len(payload)
        return 0
