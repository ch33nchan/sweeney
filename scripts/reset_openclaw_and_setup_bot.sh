#!/usr/bin/env bash
set -euo pipefail

# Fresh OpenClaw + bot setup for Ubuntu WSL.
# Run from repo root: bash scripts/reset_openclaw_and_setup_bot.sh

log() { printf "\n[%s] %s\n" "$(date +%H:%M:%S)" "$*"; }
warn() { printf "\n[WARN] %s\n" "$*"; }
err() { printf "\n[ERROR] %s\n" "$*"; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    exit 1
  fi
}

confirm() {
  local prompt="$1"
  read -r -p "$prompt [y/N]: " ans
  case "${ans,,}" in
    y|yes) return 0 ;;
    *) return 1 ;;
  esac
}

if [[ "${OSTYPE:-}" != linux* ]]; then
  err "This script is intended for Linux/WSL. Current OSTYPE=${OSTYPE:-unknown}"
  exit 1
fi

log "Starting OpenClaw reset + bot setup"
require_cmd curl
require_cmd python3

if ! command -v node >/dev/null 2>&1; then
  err "Node.js not found. Install Node.js 22+ first, then rerun this script."
  exit 1
fi

NODE_MAJOR="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
if [[ -z "$NODE_MAJOR" || "$NODE_MAJOR" -lt 22 ]]; then
  err "Node.js 22+ required. Found: $(node -v)"
  exit 1
fi

if confirm "Reset existing OpenClaw installation/state if found?"; then
  if command -v openclaw >/dev/null 2>&1; then
    log "OpenClaw detected. Attempting clean uninstall"

    set +e
    openclaw gateway stop >/dev/null 2>&1
    openclaw uninstall --all --yes --non-interactive >/dev/null 2>&1
    if [[ $? -ne 0 ]]; then
      warn "Standard uninstall flags failed, trying basic uninstall"
      openclaw uninstall >/dev/null 2>&1
    fi
    set -e
  else
    warn "openclaw CLI not found; applying filesystem/service cleanup"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    set +e
    systemctl --user disable --now openclaw-gateway.service >/dev/null 2>&1
    systemctl --user daemon-reload >/dev/null 2>&1
    set -e
  fi

  log "Removing local OpenClaw state directories"
  rm -rf "${OPENCLAW_STATE_DIR:-$HOME/.openclaw}" || true
  rm -rf "$HOME/.openclaw/workspace" || true
  rm -f "$HOME/.config/systemd/user/openclaw-gateway.service" || true

  log "Removing global package managers entries if present"
  set +e
  if command -v npm >/dev/null 2>&1; then npm rm -g openclaw >/dev/null 2>&1; fi
  if command -v pnpm >/dev/null 2>&1; then pnpm remove -g openclaw >/dev/null 2>&1; fi
  if command -v bun >/dev/null 2>&1; then bun remove -g openclaw >/dev/null 2>&1; fi
  set -e
fi

log "Installing OpenClaw fresh"
curl -fsSL https://openclaw.ai/install.sh | bash

if ! command -v openclaw >/dev/null 2>&1; then
  err "openclaw command still not found after install. Restart shell and rerun."
  exit 1
fi

log "Running OpenClaw onboard"
set +e
openclaw onboard --install-daemon
ONBOARD_RC=$?
set -e
if [[ $ONBOARD_RC -ne 0 ]]; then
  warn "onboard returned non-zero. You may need to complete auth manually with: openclaw onboard --install-daemon"
fi

log "Checking OpenClaw gateway status"
set +e
openclaw gateway status
set -e

log "Bootstrapping Python bot environment"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]

if [[ ! -f .env ]]; then
  cp .env.example .env
  warn "Created .env from template. Fill required secrets before live usage."
fi

log "Running unit tests"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v

log "Running one dry cycle"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m openclaw_bot.main run-once

cat <<'NEXT'

Setup complete.

Next steps:
1. Edit .env and set:
   - GEMINI_API_KEY
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_ALLOWED_CHAT_IDS
   - BYBIT_API_KEY / BYBIT_API_SECRET (only for BOT_MODE=live)
2. Keep BOT_MODE=testnet for at least 7 days.
3. Start bot loop:
   openclaw-bot run-loop --interval-sec 300
4. In Telegram, send: status
5. For live promotion, switch BOT_MODE=live and deposit only a small amount first.

NEXT
