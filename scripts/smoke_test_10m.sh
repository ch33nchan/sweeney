#!/usr/bin/env bash
set -euo pipefail

# 10-minute single-terminal smoke test.
# - starts trading loop + telegram agent in background
# - sends command sequence to telegram bot
# - runs 10 minutes
# - prints pass/fail summary

log() { printf "[%s] %s\n" "$(date +%H:%M:%S)" "$*"; }
err() { printf "[ERROR] %s\n" "$*" >&2; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing command: $1"
    exit 1
  fi
}

cleanup() {
  set +e
  if [[ -n "${LOOP_PID:-}" ]] && kill -0 "$LOOP_PID" >/dev/null 2>&1; then
    kill "$LOOP_PID" >/dev/null 2>&1
  fi
  if [[ -n "${AGENT_PID:-}" ]] && kill -0 "$AGENT_PID" >/dev/null 2>&1; then
    kill "$AGENT_PID" >/dev/null 2>&1
  fi
  wait >/dev/null 2>&1 || true
}
trap cleanup EXIT

require_cmd python3
require_cmd curl

if [[ ! -f ".env" ]]; then
  err ".env not found. Run: cp .env.example .env"
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  err ".venv not found. Run setup first."
  exit 1
fi

# Load environment variables from .env
set -a
# shellcheck disable=SC1091
source .env
set +a

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required in .env}"
: "${TELEGRAM_ALLOWED_CHAT_IDS:?TELEGRAM_ALLOWED_CHAT_IDS is required in .env}"

CHAT_ID="${TELEGRAM_ALLOWED_CHAT_IDS%%,*}"
if [[ -z "$CHAT_ID" ]]; then
  err "Could not parse first TELEGRAM_ALLOWED_CHAT_IDS value"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

mkdir -p logs
RUN_ID="smoke_$(date +%Y%m%d_%H%M%S)"
RUN_DIR="logs/${RUN_ID}"
mkdir -p "$RUN_DIR"
LOOP_LOG="$RUN_DIR/run-loop.log"
AGENT_LOG="$RUN_DIR/run-telegram-agent.log"
SUMMARY="$RUN_DIR/summary.txt"

log "Running unit tests"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v >"$RUN_DIR/tests.log" 2>&1

log "Starting bot loop (interval 30s)"
openclaw-bot run-loop --interval-sec 30 >"$LOOP_LOG" 2>&1 &
LOOP_PID=$!

log "Starting telegram agent"
openclaw-bot run-telegram-agent >"$AGENT_LOG" 2>&1 &
AGENT_PID=$!

sleep 5

send_cmd() {
  local cmd="$1"
  curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${CHAT_ID}\",\"text\":\"${cmd}\"}" >/dev/null
  log "Sent command: ${cmd}"
}

log "Sending command sequence"
send_cmd "status"
sleep 6
send_cmd "pause"
sleep 6
send_cmd "status"
sleep 6
send_cmd "resume"
sleep 6
send_cmd "set_risk 0.003"
sleep 6
send_cmd "status"

log "Running for 10 minutes"
sleep 600

log "Stopping background processes"
cleanup
trap - EXIT

log "Collecting summary"
python3 - <<'PY' > "$RUN_DIR/db_summary.txt"
import sqlite3
from pathlib import Path

db = Path("bot.sqlite3")
if not db.exists():
    print("db_exists=false")
    raise SystemExit(0)

conn = sqlite3.connect(str(db))
cur = conn.cursor()

def count(table):
    cur.execute(f"select count(*) from {table}")
    return cur.fetchone()[0]

print("db_exists=true")
for table in ["agent_commands", "signals", "orders", "risk_events", "pnl_snapshots"]:
    try:
        print(f"{table}={count(table)}")
    except Exception:
        print(f"{table}=ERR")

conn.close()
PY

ERROR_LINES=$(rg -n "Traceback|ERROR|Exception" "$LOOP_LOG" "$AGENT_LOG" -S || true)
CMD_COUNT=$(python3 - <<'PY'
import sqlite3
try:
    conn = sqlite3.connect("bot.sqlite3")
    cur = conn.cursor()
    cur.execute("select count(*) from agent_commands")
    print(cur.fetchone()[0])
    conn.close()
except Exception:
    print(-1)
PY
)

PASS=true
if [[ "$CMD_COUNT" -lt 6 ]]; then
  PASS=false
fi
if [[ -n "$ERROR_LINES" ]]; then
  PASS=false
fi

{
  echo "run_dir=$RUN_DIR"
  echo "loop_log=$LOOP_LOG"
  echo "agent_log=$AGENT_LOG"
  echo "agent_commands_count=$CMD_COUNT"
  echo "errors_found=$([[ -n "$ERROR_LINES" ]] && echo yes || echo no)"
  if [[ "$PASS" == true ]]; then
    echo "result=PASS"
  else
    echo "result=FAIL"
  fi
} | tee "$SUMMARY"

if [[ -n "$ERROR_LINES" ]]; then
  echo
  echo "---- error lines ----"
  echo "$ERROR_LINES"
fi

echo
echo "Smoke test complete. Summary: $SUMMARY"
