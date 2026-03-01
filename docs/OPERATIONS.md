# Operations Runbook

## Safety Defaults
- Spot mode only in v1.
- `RISK_PER_TRADE=0.005`
- `DAILY_MAX_LOSS=0.02`
- `MAX_CONCURRENT_POSITIONS=1`
- Cooldown 10 minutes.

## Recommended Launch Sequence
1. Configure `.env` with Bybit testnet credentials and Telegram bot settings.
2. Start trading loop:
   - `openclaw-bot run-loop --interval-sec 300`
3. Send Telegram `status` command and confirm response.

## Incident Commands
- `pause`: stop trading decisions.
- `resume`: resume cycle processing.
- `close_all`: cancel open orders for the configured symbol.
- `set_risk 0.003`: tighten risk per trade.

## Promotion Criteria (Testnet -> Live)
- 7 consecutive days without crashes.
- No unauthorized command acceptance.
- All executed trades include stop/take levels.
- Drawdown remains within configured daily cap.

## Live-Mode Notes
- Live mode uses Bybit private wallet balance (`/v5/account/wallet-balance`) for equity.
- API `retCode` checks are enforced; non-zero response blocks execution.
