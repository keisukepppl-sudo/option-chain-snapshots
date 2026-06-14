# Option Chain Snapshot via GitHub Actions

This repository automatically saves option-chain snapshots and includes a Russell1000 production momentum scanner notification workflow.

## Files

- `option_snapshot_auto.py`: option-chain snapshot script
- `daily_flow_engine.py`: market-flow helper reports
- `scanner_notify.py`: daily Russell1000 production momentum notification runner
- `discord_alert.py`: Discord Webhook sender
- `scanner/`: modular scanner calculations
- `config.yaml`: scanner and notification thresholds
- `requirements.txt`: Python dependencies
- `.github/workflows/option_snapshot.yml`: option snapshot schedule
- `.github/workflows/daily_scan.yml`: Russell1000 scanner notification schedule

## Production Momentum Scanner

This scanner is for candidate discovery and decision support only. It does not place orders, connect to a brokerage API, or make automated trading decisions. A human must review the chart, option chain liquidity, spread width, earnings date, IV, theme, valuation, and risk/reward before any trade decision.

Current production notification rule:

- Universe: Russell1000 via current iShares IWB holdings
- RS >= 98
- Close > prior 20-day High
- Volume Multiple >= 1.2
- Market Cap is **not** an exclusion filter
- Option Liquidity is checked after the initial candidate filter

Why Market Cap is display-only:

- Phase 11 OOS validation showed the old 2B-20B preference did not hold in 2025+.
- Therefore Market Cap is shown as context, not used as a hard filter.
- Buckets shown: `<2B`, `2B-20B`, `20B-50B`, `50B-200B`, `200B+`, `Unknown`.

Discord notification behavior:

- `S級`: production momentum candidate with option liquidity OK.
- `A級`: production momentum candidate requiring human review because option liquidity is weak, unavailable, or unchecked.
- If no signals exist, Discord receives exactly `No signals today`.

Notification fields:

- Ticker
- Rank
- RS / Breakout RS
- Close / prior 20-day High pivot
- Volume Multiple
- 50-day average volume
- Market Cap and Market Cap Bucket
- Gap % when available
- Option Liquidity
- IV
- Suggested 60DTE ATM/+15% and ATM/+20% call vertical candidates
- Exit rule display
- Risk flags

Risk flags:

- Gap > 15%
- Market Cap < 2B or unknown
- Volume >= 2x
- Volume >= 3x
- Option Liquidity weak
- IV > 100%

Suggested option structure:

- Default: 60DTE ATM/+15% and 60DTE ATM/+20% call vertical candidates.
- If IV >= 100%, ATM/+15% is emphasized and ATM/+20% becomes secondary.

Exit rule shown in notification:

- Basic profit take: +125% option P/L.
- If the human review confirms Semiconductor / Software theme: 10 trading days after entry, exit if the underlying has not gained at least +5%.

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
