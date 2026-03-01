from __future__ import annotations

from dataclasses import dataclass
from os import environ
from os import getenv
from pathlib import Path


@dataclass
class Settings:
    bot_mode: str = "testnet"
    base_symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    loop_interval_sec: int = 300
    confidence_floor: float = 0.72
    risk_per_trade: float = 0.005
    daily_max_loss: float = 0.02
    max_concurrent_positions: int = 1
    cooldown_min: int = 10
    max_spread_bps: float = 8.0
    max_fee_bps: float = 12.0
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_testnet: bool = True
    use_live_market_data: bool = False
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: tuple[str, ...] = ()
    telegram_poll_timeout_sec: int = 5
    db_path: str = "bot.sqlite3"
    logs_path: str = "logs/bot.log"

    @staticmethod
    def _as_bool(value: str | None, default: bool) -> bool:
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}



def _parse_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())



def _load_dotenv(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and getenv(key) is None:
            environ[key] = value



def load_settings() -> Settings:
    _load_dotenv()
    return Settings(
        bot_mode=getenv("BOT_MODE", "testnet"),
        base_symbol=getenv("BASE_SYMBOL", "BTC/USDT"),
        timeframe=getenv("TIMEFRAME", "1m"),
        loop_interval_sec=int(getenv("LOOP_INTERVAL_SEC", "300")),
        confidence_floor=float(getenv("CONFIDENCE_FLOOR", "0.72")),
        risk_per_trade=float(getenv("RISK_PER_TRADE", "0.005")),
        daily_max_loss=float(getenv("DAILY_MAX_LOSS", "0.02")),
        max_concurrent_positions=int(getenv("MAX_CONCURRENT_POSITIONS", "1")),
        cooldown_min=int(getenv("COOLDOWN_MIN", "10")),
        max_spread_bps=float(getenv("MAX_SPREAD_BPS", "8")),
        max_fee_bps=float(getenv("MAX_FEE_BPS", "12")),
        gemini_api_key=getenv("GEMINI_API_KEY", ""),
        gemini_model=getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        bybit_api_key=getenv("BYBIT_API_KEY", ""),
        bybit_api_secret=getenv("BYBIT_API_SECRET", ""),
        bybit_testnet=Settings._as_bool(getenv("BYBIT_TESTNET"), True),
        use_live_market_data=Settings._as_bool(getenv("USE_LIVE_MARKET_DATA"), False),
        coingecko_base_url=getenv("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3"),
        telegram_bot_token=getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_allowed_chat_ids=_parse_csv(getenv("TELEGRAM_ALLOWED_CHAT_IDS")),
        telegram_poll_timeout_sec=int(getenv("TELEGRAM_POLL_TIMEOUT_SEC", "5")),
        db_path=getenv("DB_PATH", "bot.sqlite3"),
        logs_path=getenv("LOGS_PATH", "logs/bot.log"),
    )
