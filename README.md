# OpenClaw + Telegram Trading Bot (Free-First Scaffold)

This repository implements a risk-first trading bot scaffold for:
- Windows + WSL2 runtime
- Bybit testnet-first rollout, then live spot
- Gemini-based signal scoring with strict validation
- Telegram Bot commands for control and notifications
- SQLite persistence and deterministic risk gates

## Important
No part of this project guarantees profit. The bot defaults to conservative risk controls and can block trades.

## Features
- `market_data`: candles/orderbook/trades from exchange interface and optional CoinGecko context.
- `strategy`: deterministic features + validated LLM output.
- `risk`: deterministic pre-trade checks and position sizing.
- `execution`: `PaperExchangeClient` and Bybit private REST client.
- `telegram`: command parsing, allowed-chat enforcement, long-poll control plane.
- `storage`: SQLite schema for signals/orders/fills/positions/risk events/commands/pnl snapshots.
- `bot`: orchestrator loop, heartbeat notifications, kill-switch hooks.

## Quick Start (WSL2)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m openclaw_bot.main run-once
```

## Fresh WSL Reset + Setup
Use this if you want to wipe old OpenClaw and start clean:
```bash
bash scripts/reset_openclaw_and_setup_bot.sh
```

## Single-Terminal 10-Min Smoke Test
Use this when you cannot open multiple WSL tabs:
```bash
bash scripts/smoke_test_10m.sh
```
It runs unit tests, starts both bot processes in background, asks you to send Telegram commands from your phone/client, waits 10 minutes, and prints a pass/fail summary.

## Commands
- `openclaw-bot run-once`: one decision cycle.
- `openclaw-bot run-loop --interval-sec 300`: repeating cycles (+ Telegram command polling when configured).
- `openclaw-bot run-telegram-agent`: Telegram control loop only.

## Telegram Commands
- `status`
- `pause`
- `resume`
- `close_all`
- `set_risk 0.003`

## Environment
See `.env.example` for required keys.
