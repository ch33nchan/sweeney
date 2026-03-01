from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .bot import TradingBot
from .models import CommandEnvelope, CommandType

logger = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


class TelegramAuthError(TelegramError):
    pass


class TelegramCommandError(TelegramError):
    pass



def parse_command_text(text: str) -> tuple[CommandType, dict]:
    normalized = " ".join(text.strip().lower().split())

    if normalized == "status":
        return CommandType.STATUS, {}
    if normalized == "pause":
        return CommandType.PAUSE, {}
    if normalized == "resume":
        return CommandType.RESUME, {}
    if normalized == "close_all":
        return CommandType.CLOSE_ALL, {}
    if normalized.startswith("set_risk "):
        try:
            value = float(normalized.split(" ", 1)[1])
        except ValueError as exc:
            raise TelegramCommandError("set_risk requires numeric value") from exc
        if value <= 0 or value > 0.05:
            raise TelegramCommandError("set_risk must be between 0 and 0.05")
        return CommandType.SET_RISK, {"risk_per_trade": value}

    raise TelegramCommandError("Unsupported command")



def parse_update_command(update: dict, allowed_chat_ids: tuple[str, ...]) -> CommandEnvelope | None:
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return None

    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    text = str(message.get("text") or "").strip()
    if not chat_id or not text:
        return None

    if allowed_chat_ids and chat_id not in allowed_chat_ids:
        raise TelegramAuthError("chat not allowed")

    cmd_type, params = parse_command_text(text)
    return CommandEnvelope(
        command_type=cmd_type,
        issued_by=chat_id,
        issued_at=datetime.now(timezone.utc),
        params=params,
    )


@dataclass
class TelegramControlPlane:
    bot_token: str
    allowed_chat_ids: tuple[str, ...]
    poll_timeout_sec: int = 5
    offset: int | None = None

    def _api_get(self, method: str, params: dict[str, str | int]) -> dict:
        query = urlencode(params)
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}?{query}"
        req = Request(url, headers={"accept": "application/json"}, method="GET")
        try:
            with urlopen(req, timeout=max(self.poll_timeout_sec + 3, 8)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise TelegramError(f"Telegram API call failed: {exc}") from exc

        if not data.get("ok"):
            raise TelegramError(f"Telegram API response not ok: {data}")
        return data

    def _api_post(self, method: str, payload: dict) -> dict:
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise TelegramError(f"Telegram API call failed: {exc}") from exc

        if not data.get("ok"):
            raise TelegramError(f"Telegram API response not ok: {data}")
        return data

    def send_text(self, chat_id: str, text: str) -> None:
        self._api_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:4096],
                "disable_web_page_preview": True,
            },
        )

    def fetch_updates(self) -> list[dict]:
        params: dict[str, str | int] = {
            "timeout": self.poll_timeout_sec,
            "allowed_updates": json.dumps(["message", "edited_message"]),
        }
        if self.offset is not None:
            params["offset"] = self.offset
        data = self._api_get("getUpdates", params)
        updates = data.get("result")
        if not isinstance(updates, list):
            return []
        return updates

    def poll_and_apply(self, bot: TradingBot) -> int:
        processed = 0
        updates = self.fetch_updates()

        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self.offset = update_id + 1

            message = update.get("message") or update.get("edited_message") or {}
            chat_id = str((message.get("chat") or {}).get("id") or "")

            try:
                cmd = parse_update_command(update, self.allowed_chat_ids)
                if cmd is None:
                    continue
                response = bot.apply_command(cmd)
                self.send_text(cmd.issued_by, response)
                processed += 1
            except TelegramAuthError as exc:
                logger.warning("Telegram unauthorized command: %s", exc)
                if chat_id:
                    self.send_text(chat_id, "Unauthorized chat id")
            except TelegramCommandError as exc:
                if chat_id:
                    self.send_text(chat_id, f"Invalid command: {exc}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Telegram command processing failed: %s", exc)
                if chat_id:
                    self.send_text(chat_id, "Command failed")

        return processed
