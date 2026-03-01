from __future__ import annotations

import unittest

from openclaw_bot.models import CommandType
from openclaw_bot.telegram import (
    TelegramAuthError,
    TelegramCommandError,
    parse_command_text,
    parse_update_command,
)


class TelegramTests(unittest.TestCase):
    def test_parse_set_risk(self) -> None:
        cmd, params = parse_command_text("set_risk 0.01")
        self.assertEqual(cmd, CommandType.SET_RISK)
        self.assertEqual(params["risk_per_trade"], 0.01)

    def test_rejects_unknown_command(self) -> None:
        with self.assertRaises(TelegramCommandError):
            parse_command_text("do_magic")

    def test_rejects_unauthorized_chat(self) -> None:
        update = {
            "update_id": 10,
            "message": {"chat": {"id": 999}, "text": "status"},
        }
        with self.assertRaises(TelegramAuthError):
            parse_update_command(update, allowed_chat_ids=("123",))

    def test_parses_authorized_message(self) -> None:
        update = {
            "update_id": 11,
            "message": {"chat": {"id": 123}, "text": "status"},
        }
        cmd = parse_update_command(update, allowed_chat_ids=("123",))
        self.assertIsNotNone(cmd)
        assert cmd is not None
        self.assertEqual(cmd.command_type, CommandType.STATUS)
        self.assertEqual(cmd.issued_by, "123")


if __name__ == "__main__":
    unittest.main()
