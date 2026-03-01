from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class NotifyError(RuntimeError):
    pass


class Notifier:
    def send_text(self, text: str) -> None:
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    def send_text(self, text: str) -> None:
        print(text)


@dataclass
class TelegramNotifier(Notifier):
    bot_token: str
    chat_id: str

    def send_text(self, text: str) -> None:
        if not self.bot_token or not self.chat_id:
            raise NotifyError("Telegram notifier not configured")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text[:4096],
            "disable_web_page_preview": True,
        }
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise NotifyError(f"Telegram notify failed: {exc}") from exc

        if not data.get("ok"):
            raise NotifyError(f"Telegram notify rejected: {data}")
