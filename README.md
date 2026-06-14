# Option Chain Snapshot via GitHub Actions

This repository automatically saves option-chain snapshots and now includes a Russell1000 Minervini-style scanner notification workflow.

## Files

- `option_snapshot_auto.py`: option-chain snapshot script
- `daily_flow_engine.py`: market-flow helper reports
- `scanner_notify.py`: daily Russell1000 scanner notification runner
- `discord_alert.py`: Discord Webhook sender
- `scanner/`: modular scanner calculations
- `config.yaml`: scanner and notification thresholds
- `requirements.txt`: Python dependencies
- `.github/workflows/option_snapshot.yml`: option snapshot schedule
- `.github/workflows/daily_scan.yml`: Russell1000 scanner notification schedule

## Russell1000 Discord Scanner

This scanner is for candidate discovery and decision support only. It does not place orders, connect to a brokerage API, or make automated trading decisions. A human must review the chart, option chain liquidity, spread width, earnings date, IV, and risk/reward before any trade decision.

Daily notification rule:

- Universe: Russell1000 via current iShares IWB holdings
- Trend Template PASS
- Standard RS >= 95
- Breakout RS >= 95
- Accumulation >= 30
- VCP >= 50
- Distance to Pivot <= 12%
- Defensive RS: no condition

Additional notification filters:

- 50-day average volume >= 2,000,000 shares
- Price >= $10
- Market-cap proxy >= $2B

Discord message behavior:

- If signals exist, candidates are sent to Discord.
- If no signals exist, Discord receives exactly `No signals today`.
- Signals are grouped in this order:

```text
🔥 S Rank
🚨 A Rank
⚠️ B Rank
```

Notification fields:

- Ticker
- Rank
- Total Score
- Standard RS
- Breakout RS
- Accumulation
- VCP
- Distance to Pivot
- 50-day average volume

## GitHub Actions Setup

1. Open the repository on GitHub.
2. Go to `Settings` -> `Secrets and variables` -> `Actions`.
3. Add a repository secret:

```text
Name: STOCK
Value: your Discord Webhook URL
```

Do not commit the webhook URL to code.

## Schedule

The scanner workflow runs once per weekday after the US regular session close:

```text
0 22 * * 1-5
```

This is around 07:00 JST.

## First Test

After adding the `STOCK` secret:

1. Open `Actions`.
2. Select `Daily Russell1000 Scanner`.
3. Click `Run workflow`.
4. Confirm the Discord channel receives either candidates or `No signals today`.

## Local Run

Run locally without sending Discord:

```bash
python scanner_notify.py --no-notify
```

Run locally with Discord:

```bash
STOCK="https://discord.com/api/webhooks/..." python scanner_notify.py
```

Outputs:

```text
scanner_alerts/YYYY-MM-DD/russell1000_momentum_candidates.csv
```

## Tests

```bash
pytest tests/test_notifications.py
```

## Existing Option Snapshot Workflow

Default option snapshot schedule is 06:30 JST on weekdays.

GitHub Actions cron uses UTC, so:

- 06:30 JST = 21:30 UTC previous day

Manual option snapshot run:

```text
GitHub -> Actions -> Option Chain Snapshot -> Run workflow
```
