from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .bot import TradingBot
from .whatsapp import WhatsAppAuthError, parse_webhook_command, verify_signature

logger = logging.getLogger(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    bot: TradingBot
    app_secret: str
    verify_token: str
    allowed_senders: tuple[str, ...]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/webhook":
            self.send_error(404)
            return

        query = parse_qs(parsed.query)
        mode = query.get("hub.mode", [""])[0]
        token = query.get("hub.verify_token", [""])[0]
        challenge = query.get("hub.challenge", [""])[0]

        if mode == "subscribe" and token == self.verify_token:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(challenge.encode("utf-8"))
            return

        self.send_error(403)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhook":
            self.send_error(404)
            return

        size = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(size)

        signature = self.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(self.app_secret, payload, signature):
            self.send_error(403, "Invalid signature")
            return

        try:
            command = parse_webhook_command(payload, self.allowed_senders)
            response = self.bot.apply_command(command)
            body = {"ok": True, "response": response}
            self._send_json(200, body)
        except WhatsAppAuthError as exc:
            self._send_json(403, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Webhook processing failed: %s", exc)
            self._send_json(400, {"ok": False, "error": str(exc)})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        logger.info("webhook " + format, *args)

    def _send_json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)



def serve_webhook(
    host: str,
    port: int,
    bot: TradingBot,
    app_secret: str,
    verify_token: str,
    allowed_senders: tuple[str, ...],
) -> None:
    class Handler(WebhookHandler):
        pass

    Handler.bot = bot
    Handler.app_secret = app_secret
    Handler.verify_token = verify_token
    Handler.allowed_senders = allowed_senders

    server = HTTPServer((host, port), Handler)
    logger.info("Webhook server running on %s:%s", host, port)
    server.serve_forever()
