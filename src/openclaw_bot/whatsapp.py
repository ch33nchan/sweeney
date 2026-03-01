from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import CommandEnvelope, CommandType


class WhatsAppAuthError(RuntimeError):
    pass


class WhatsAppCommandError(RuntimeError):
    pass


@dataclass
class WhatsAppConfig:
    app_secret: str
    verify_token: str
    allowed_senders: tuple[str, ...]



def verify_signature(app_secret: str, payload: bytes, received_signature: str) -> bool:
    if not app_secret or not received_signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", received_signature)



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
            raise WhatsAppCommandError("set_risk requires numeric value") from exc
        if value <= 0 or value > 0.05:
            raise WhatsAppCommandError("set_risk must be between 0 and 0.05")
        return CommandType.SET_RISK, {"risk_per_trade": value}

    raise WhatsAppCommandError("Unsupported command")



def parse_webhook_command(raw_payload: bytes, allowed_senders: tuple[str, ...]) -> CommandEnvelope:
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WhatsAppCommandError("Invalid JSON payload") from exc

    entry = (payload.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value") or {}
    messages = value.get("messages") or []
    if not messages:
        raise WhatsAppCommandError("No messages found")

    msg = messages[0]
    sender = str(msg.get("from") or "")
    text = ((msg.get("text") or {}).get("body") or "").strip()
    if not sender or not text:
        raise WhatsAppCommandError("Missing sender or text")

    if allowed_senders and sender not in allowed_senders:
        raise WhatsAppAuthError("Sender not allowed")

    cmd_type, params = parse_command_text(text)
    return CommandEnvelope(
        command_type=cmd_type,
        issued_by=sender,
        issued_at=datetime.now(timezone.utc),
        params=params,
    )
