from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass

from .bot import TradingBot
from .bybit_market import BybitPublicMarketClient
from .config import Settings, load_settings
from .execution import BybitRestClient, PaperExchangeClient
from .llm import GeminiClient
from .logging_utils import setup_logging
from .market_data import ExchangeMarketClient, MarketDataService
from .models import Action, FeatureVector, LLMDecision
from .notifier import ConsoleNotifier, TelegramNotifier
from .openclaw_adapter import OpenClawDecisionBridge
from .risk import RiskEngine, RiskPolicy
from .storage import SQLiteStore
from .strategy import StrategyEngine
from .telegram import TelegramControlPlane

logger = logging.getLogger(__name__)


@dataclass
class HeuristicDecisionModel:
    """Fallback model for local dry-runs when LLM is unavailable."""

    def decide(self, symbol: str, features: FeatureVector) -> LLMDecision:
        if features.trend > 0 and features.volatility < 0.005:
            action = Action.BUY
            confidence = min(0.65 + abs(features.trend) * 10, 0.85)
            reason = "Positive trend and controlled volatility"
        elif features.trend < 0 and features.volatility < 0.005:
            action = Action.SELL
            confidence = min(0.65 + abs(features.trend) * 10, 0.85)
            reason = "Negative trend and controlled volatility"
        else:
            action = Action.NO_TRADE
            confidence = 0.4
            reason = "Noisy conditions"

        return LLMDecision(
            symbol=symbol,
            action=action,
            confidence=confidence,
            time_horizon_min=5,
            reason=reason,
        )


@dataclass
class PaperMarketClient(ExchangeMarketClient):
    seed_price: float = 100_000.0

    def fetch_orderbook_top(self, symbol: str) -> tuple[float, float]:
        return self.seed_price - 5, self.seed_price + 5

    def fetch_last_price(self, symbol: str) -> float:
        return self.seed_price

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 100) -> list[dict[str, float]]:
        candles: list[dict[str, float]] = []
        price = self.seed_price * 0.98
        for idx in range(limit):
            price = price * (1.0002 if idx % 3 else 1.0006)
            candles.append(
                {
                    "open": round(price * 0.999, 2),
                    "high": round(price * 1.001, 2),
                    "low": round(price * 0.998, 2),
                    "close": round(price, 2),
                    "volume": float(100 + idx),
                }
            )
        return candles

    def fetch_volume_24h(self, symbol: str) -> float:
        return 1_000_000.0



def build_runtime() -> tuple[TradingBot, TelegramControlPlane | None, Settings]:
    settings = load_settings()
    setup_logging(settings.logs_path)

    store = SQLiteStore(settings.db_path)

    if settings.bot_mode == "testnet":
        exchange = PaperExchangeClient()
    else:
        exchange = BybitRestClient(
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            testnet=settings.bybit_testnet,
        )

    if settings.bot_mode == "testnet" and not settings.use_live_market_data:
        market_exchange = PaperMarketClient()
    else:
        market_exchange = BybitPublicMarketClient(testnet=settings.bybit_testnet)
    market_data = MarketDataService(market_exchange)

    if settings.gemini_api_key:
        model = GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
    else:
        model = HeuristicDecisionModel()

    model = OpenClawDecisionBridge(delegate=model)

    strategy = StrategyEngine(model=model, confidence_floor=settings.confidence_floor)
    risk_policy = RiskPolicy(
        risk_per_trade=settings.risk_per_trade,
        daily_max_loss=settings.daily_max_loss,
        max_concurrent_positions=settings.max_concurrent_positions,
        cooldown_min=settings.cooldown_min,
        max_spread_bps=settings.max_spread_bps,
        max_fee_bps=settings.max_fee_bps,
    )
    risk_engine = RiskEngine(risk_policy)

    default_chat = settings.telegram_allowed_chat_ids[0] if settings.telegram_allowed_chat_ids else ""
    if settings.telegram_bot_token and default_chat:
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=default_chat,
        )
    else:
        notifier = ConsoleNotifier()

    bot = TradingBot(
        settings=settings,
        market_data=market_data,
        strategy=strategy,
        risk_engine=risk_engine,
        exchange=exchange,
        store=store,
        notifier=notifier,
    )

    control_plane: TelegramControlPlane | None = None
    if settings.telegram_bot_token and settings.telegram_allowed_chat_ids:
        control_plane = TelegramControlPlane(
            bot_token=settings.telegram_bot_token,
            allowed_chat_ids=settings.telegram_allowed_chat_ids,
            poll_timeout_sec=max(1, settings.telegram_poll_timeout_sec),
        )

    return bot, control_plane, settings



def _run_once() -> int:
    bot, _, _ = build_runtime()
    result = bot.run_cycle()
    print(result)
    return 0



def _run_loop(interval_sec: int, disable_telegram: bool = False) -> int:
    bot, control_plane, _ = build_runtime()
    while True:
        try:
            if control_plane is not None and not disable_telegram:
                control_plane.poll_and_apply(bot)
            print(bot.run_cycle())
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cycle failed: %s", exc)
        time.sleep(interval_sec)



def _run_telegram_agent() -> int:
    bot, control_plane, settings = build_runtime()
    if control_plane is None:
        raise SystemExit(
            "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS in .env"
        )

    logger.info("Telegram agent loop started")
    while True:
        try:
            handled = control_plane.poll_and_apply(bot)
            if handled == 0:
                time.sleep(max(1, settings.telegram_poll_timeout_sec))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram agent failed: %s", exc)
            time.sleep(2)



def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw Telegram trading bot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run-once")

    loop_cmd = sub.add_parser("run-loop")
    loop_cmd.add_argument("--interval-sec", type=int, default=300)
    loop_cmd.add_argument("--disable-telegram", action="store_true")

    sub.add_parser("run-telegram-agent")

    args = parser.parse_args()

    if args.cmd == "run-once":
        return _run_once()
    if args.cmd == "run-loop":
        return _run_loop(interval_sec=args.interval_sec, disable_telegram=args.disable_telegram)
    if args.cmd == "run-telegram-agent":
        return _run_telegram_agent()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
