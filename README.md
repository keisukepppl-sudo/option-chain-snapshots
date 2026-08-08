# Option Chain Snapshot via GitHub Actions

This repository automatically saves option-chain snapshots for:

- QQQ
- SPY
- SOXX
- SMH
- MU
- DRAM

## Files

- `option_snapshot_auto.py`: snapshot script
- `daily_flow_engine.py`: market-flow helper reports
- `minervini_scanner.py`: Phase 1 Minervini breakout scanner
- `scanner_notify.py`: daily Russell1000 options-momentum scanner notification
- `discord_alert.py`: Discord Webhook sender
- `scanner/`: modular scanner calculations
- `requirements.txt`: Python dependencies
- `.github/workflows/option_snapshot.yml`: GitHub Actions schedule
- `.github/workflows/daily_scan.yml`: post-close scanner notification schedule

## Schedule

Default schedule is 06:30 JST on weekdays.

GitHub Actions cron uses UTC, so:

- 06:30 JST = 21:30 UTC previous day

## Manual option snapshot run

GitHub -> Actions -> Option Chain Snapshot -> Run workflow

## Option snapshot output

```text
option_chain_snapshots/
  QQQ/
  SPY/
  SOXX/
  SMH/
  MU/
  DRAM/
```

## Minervini breakout scanner

The scanner is candidate discovery and decision support only. It does not place
orders or connect to a brokerage API.

Run:

```bash
python minervini_scanner.py --tickers AAPL MSFT NVDA META AMZN GOOGL AVGO MU DRAM --benchmark QQQ
```

Outputs:

```text
minervini_outputs/YYYY-MM-DD/minervini_candidates.csv
minervini_outputs/YYYY-MM-DD/minervini_candidates.html
```

Phase 1 modules:

- `scanner/trend_template.py`: Minervini trend template
- `scanner/trend.py`: compatibility alias for trend-template imports
- `scanner/universe.py`: price, liquidity, market-cap, and simple security-type filters
- `scanner/rs.py`: Standard RS, Defensive RS, Breakout RS
- `scanner/breakout.py`: pivot, breakout, near-breakout, failed-breakout flag
- `scanner/vcp.py`: VCP-like contraction and dry-up score
- `scanner/accumulation.py`: accumulation score
- `scanner/scoring.py`: total score and A/B/C rank classification

Rank meanings:

- `S`: Early Entry Candidate. This is a watch candidate just before a possible
  breakout, not an automated trading signal. S Rank v2 requires Trend Template
  pass, Standard RS >= 80, Breakout RS >= 80, Accumulation >= 60, VCP >= 45,
  near-breakout status, and distance to pivot <= 5%.
- `A`: breakout alert.
- `B`: setup alert.
- `C`: CSV/HTML only.

Alert priority is `S > A > B > C`.

Defensive RS and volume dry-up are quality bonuses, not mandatory S Rank gates:
Defensive RS >= 80 adds 5 points, Defensive RS >= 90 adds 10 points, and volume
dry-up adds a 5-point quality bonus.

Thresholds are centralized in `config.yaml`.

## Russell1000 Discord notifications

This notification flow is the Production Momentum System for call-vertical
candidate discovery only. It does not place orders, connect to a brokerage API,
or make automated trading decisions. A human must review earnings quality,
theme, valuation, IV, option-chain liquidity, spread width, and risk/reward
before any trade decision.

Production mode is enabled in `config.yaml`:

```yaml
notify:
  mode: production_momentum
```

The scanner first records broad research candidates using:

- Universe: Russell1000 via current iShares IWB holdings
- Standard RS > 98
- Intraday latest price > prior 20-day High
- Intraday volume pace >= 1.2x versus the 50-day average daily volume pace

Those broad candidates are shadow/research rows, not automatically actionable
notifications. Discord and Pushover candidate notifications require S or A rank
and every `strict_notification_gate` condition:

- latest price above the prior 65-session high
- time-of-day adjusted RVOL >= 1.5x, using a U-shaped regular-session volume curve
- the two most recent completed 5-minute bars both closed above the 65-session pivot
- price above VWAP and at or above the session open
- price within 1% of the intraday high
- QQQ above its 20-day EMA

A missing input fails closed. A candidate that misses any strict condition is
kept in the daily/excluded CSV with `notification_gate_reasons`, but it is not
sent. The configured 50% final-conversion value is an operating calibration
target, not a guarantee; the intended measurement is whether an actionable
intraday notification remains S/A at the final pre-close scan.

Market cap is not an exclusion filter in `production_momentum` mode. It is
displayed as a bucket and quality note because Phase 11 out-of-sample validation
showed weak 2025+ results for the 2B-20B bucket while 50B-200B and 200B+ were
stronger. These stronger buckets are highlighted, but candidates are not limited
to them.

Danger flags are displayed but do not automatically block A-grade monitoring:

- Gap > 15%
- Market Cap < $2B
- Market Cap unknown
- Option Liquidity insufficient or unavailable
- IV >= 100%
- Earnings check required when the opening gap is large

Run locally without sending Discord:

```bash
python scanner_notify.py --no-notify
```

Run and send Discord:

```bash
STOCK="https://discord.com/api/webhooks/..." python scanner_notify.py
```

Outputs:

```text
scanner_alerts/YYYY-MM-DD/russell1000_momentum_candidates.csv
```

Discord notifications include ticker, company name, S/A rank, RS, latest price,
breakout basis, volume pace multiple, volume >=2.0 and >=3.0 flags, gap %, market
cap, market-cap bucket, market-cap quality note, option-liquidity status, IV,
ATM/+15% and ATM/+20% vertical candidates, RS98 breadth regime, exit rules,
20-day high breakout date, breakout price, prior 20-day high, and danger flags.
If no signal passes the filters, Discord receives exactly:

```text
No signals today
```

Signals are grouped in this order:

```text
S-grade: Option Candidate
A-grade: Watch Candidate
B-grade: Late Confirmation
C-grade: Research Watch
```

Option liquidity uses Yahoo Finance option-chain data when available. The
default heuristic checks a 45-100DTE call chain near 60DTE, then verifies
ATM/+15% and ATM/+20% vertical candidates using open interest and bid/ask spread
width. If IV is >= 100%, the notification emphasizes ATM/+15% as an alternative.
If the option chain is unavailable, the candidate remains visible with an
`Option Liquidity unavailable` danger flag instead of stopping the whole
notification job.

GitHub Actions runs the production momentum checks at:

```text
30 13 * * 1-5  # 22:30 JST intraday normal
0 14 * * 1-5   # 23:00 JST intraday high if S/A/B
15 19 * * 1-5  # 04:15 JST pre-close Emergency window
25 19 * * 1-5  # 04:25 JST pre-close Emergency window
35 19 * * 1-5  # 04:35 JST pre-close Emergency window
```

GitHub Actions cron uses UTC.

Intraday checks use latest intraday price and completed 5-minute bars, not daily
close. At 10:00 ET the strict RVOL denominator assumes about 17% of normal daily
volume has traded; the legacy linear clock-time denominator was only about 7.7%
and could materially overstate opening RVOL.

### Production momentum alert scoring

Production notifications must not use future follow-through information. The
notification rank uses:

```text
production_live_score = conviction_score - day10_subscore
production_adjusted_score = production_live_score - 5 if time_adjusted_volume_multiple < 1.5 else production_live_score
```

If `conviction_score` is not present, the bot reconstructs `production_live_score` from
scan-time information only: RS, time-adjusted volume multiple, accumulation, 20-day breakout
excess, sector/theme proxy, and market-cap bucket. The notification layer
checks for forbidden columns such as `day10`, `day20`, `future`, `exit_pnl`,
and `trade_max_drawdown`, and prints diagnostics for any detected leakage.

Ranks and suggested size:

- `S`: production_adjusted_score >= 50, suggested size 60%
- `A`: 40 <= production_adjusted_score < 50, suggested size 50%
- `B`: 30 <= production_adjusted_score < 40, suggested size 40%
- `C`: 25 <= production_adjusted_score < 30, suggested size 30%
- `D`: production_adjusted_score < 25, no trade / no realtime alert

Hard notification exclusions:

- Biotech / Healthcare
- gap >= 10%
- production_adjusted_score < 25
- price < 5
- any failed `strict_notification_gate` condition

Every scan candidate is still saved to research logs:

- `daily_scan_log_YYYYMMDD_HHMM.csv`
- `notified_candidates_YYYYMMDD_HHMM.csv`
- `excluded_candidates_YYYYMMDD_HHMM.csv`
- `notification_diagnostics_YYYYMMDD_HHMM.json`

### Pushover alerts

Pushover is an optional additional channel. Candidate payloads use the same
strict S/A eligibility as Discord. The current production schedule is:

- Fixed-JST Cloud Run checkpoints send S/A status; the first actionable signal
  needs two completed 5-minute bars.
- 15:15-15:40 ET wake checks send Emergency only for a strict-gate S that was
  absent from the 24:00 JST execution baseline.
- The 10:15 JST final-status GitHub workflow runs Tuesday-Saturday UTC/JST so
  Friday's U.S. session is included.

Emergency payload uses `priority=2`, `retry=60`, `expire=600`, and
`sound=siren`.

Emergency duplicate suppression is saved in
`notification_sent_state_YYYYMMDD.json`. The bot skips repeat Emergency
notifications for the same ticker during the same pre-close window unless a new
S/A/B candidate appears, rank improves, `production_adjusted_score` improves
materially, or the previous Pushover send failed.

Manual Pushover tests are available from the `Pushover Test` GitHub Actions
workflow. Select `normal`, `high`, or `emergency`; emergency testing is manual
only.

For phone-side Emergency reliability, verify these settings in the Pushover app
and OS notification settings:

- Pushover notifications are allowed.
- Sound is allowed.
- Critical Alerts / important notifications are enabled if your OS exposes that
  setting.
- Do Not Disturb / Focus mode allows Pushover.
- Pushover app Emergency notifications are configured to make sound.
- Run the `Pushover Test` workflow with `emergency` and confirm it repeats until
  acknowledged.

GitHub Actions scheduled jobs can still start late under platform load. The
04:15 / 04:25 / 04:35 JST schedule reduces but does not eliminate that risk.

Create a Pushover app:

1. Open your Pushover dashboard.
2. Create an application/API token.
3. Copy the app token and your user key.

Add GitHub Actions secrets:

```text
PUSHOVER_ENABLED=true
PUSHOVER_APP_TOKEN=your Pushover application token
PUSHOVER_USER_KEY=your Pushover user key
```

If `PUSHOVER_ENABLED` is missing or not truthy, no Pushover request is made.

### GitHub Actions setup

1. Open GitHub repository settings.
2. Go to `Secrets and variables` -> `Actions`.
3. Add a repository secret for Discord:

```text
Name: STOCK
Value: your Discord Webhook URL
```

Do not commit the webhook URL to code.

4. Optionally add Pushover secrets:

```text
Name: PUSHOVER_ENABLED
Value: true

Name: PUSHOVER_APP_TOKEN
Value: your Pushover application token

Name: PUSHOVER_USER_KEY
Value: your Pushover user key
```

Do not commit Pushover credentials to code.

### First test

Run locally without sending Discord:

```bash
python scanner_notify.py --no-notify
```

Run locally with Discord:

```bash
STOCK="https://discord.com/api/webhooks/..." python scanner_notify.py
```

Run locally with Discord plus Pushover:

```bash
STOCK="https://discord.com/api/webhooks/..." \
PUSHOVER_ENABLED=true \
PUSHOVER_APP_TOKEN="..." \
PUSHOVER_USER_KEY="..." \
python scanner_notify.py
```

Run in GitHub:

1. Open `Actions`.
2. Select `Daily Russell1000 Scanner`.
3. Click `Run workflow`.
4. Confirm the Discord channel receives either scanner candidates or `No signals today`.

Run tests:

```bash
pytest tests/test_notifications.py tests/test_pushover_notify.py
```

The notification layer is intentionally small: `discord_alert.py` exposes
`send_discord_alert(message)`, and `scanner/pushover_notify.py` exposes
`send_pushover_emergency(message)`, so future channels can be added without
changing scanner logic.

### Phase 9 research outputs

The production rule research is written to:

```text
outputs/minervini_factor_contribution/phase9_production_momentum_system/
```

Key files:

- `phase9_production_momentum_system_report.md`
- `gap_analysis_summary.csv`
- `iv_sensitivity_summary.csv`
- `regime_filter_summary.csv`

## Market Structure Dashboard

The market structure dashboard is separate from the Minervini scanner. It
generates a static HTML dashboard plus CSV snapshots for:

- Market Overview: QQQ, SPY, MU, DRAM, moving averages, VIX, market regime
- GEX Dashboard: Net GEX, Gamma Flip, Near/Far/Overall Call and Put Walls, GEX by strike
- Gamma Pinning: 0DTE, 1DTE, Weekly pinning and expected ranges
- Volatility Surface: QQQ, SPY, MU, DRAM ATM IV, surface proxy IV rank, skew, heatmap
- CTA / Vol Control: moving-average trend and volatility regime signals
- Leveraged ETF Flow: AUM proxy, daily return, leverage, rebalance flow estimate
- Korea: KOSPI/KOSPI200/Samsung Electronics/SK Hynix overview and Korea ETF flow when available

Run:

```bash
python market_structure_dashboard.py
```

Open:

```text
dashboard/index.html
```

Daily entry point:

```text
dashboard/index.html
```

Open this file first. It is the only daily entry point and contains tabs for
Overview, GEX All, GEX 0DTE, GEX 1DTE, GEX Weekly, GEX by Volume, GEX by Open
Interest, Vol Surface, CTA / Vol Control, ETF Flow, Korea, Data Quality, and
Methodology. The files under `charts/*.html` are still generated for detailed
full-screen review, but they are also embedded or linked inside
`dashboard/index.html`.

For a normal browser URL instead of a `file://` path, run:

```text
serve_dashboard.cmd
```

Then open:

```text
http://127.0.0.1:8010/dashboard/index.html
```

This local URL works in Chrome/Edge on the same PC while the command window is
open. For an internet-accessible `https://...` URL, publish the generated
dashboard with GitHub Pages or another static hosting service.

Outputs:

```text
output/latest_market_snapshot.csv
output/latest_gex_levels.csv
output/latest_gamma_flip.csv
output/latest_gex_levels_raw.csv
output/latest_gex_levels_display.csv
output/latest_gex_pressure_zones.csv
output/latest_gamma_pinning.csv
output/latest_vol_surface.csv
output/latest_cta_vol_control.csv
output/latest_etf_flows.csv
output/latest_korea_market.csv
output/data_quality_report.csv
output/diagnostics_report.md
output/vol_surface/
charts/gex_profile_all.html
charts/gex_profile_0dte.html
charts/gex_profile_1dte.html
charts/gex_profile_weekly.html
charts/gex_by_volume.html
charts/gex_by_open_interest.html
charts/vol_surface_heatmap.html
charts/term_structure.html
charts/skew.html
dashboard/index.html
dashboard/assets/
```

If an upstream data point is missing, the dashboard displays `N/A` and continues
building the rest of the page.

### Market dashboard definitions

GEX is an estimate, not an exchange-published value. The dashboard uses:

```text
option gamma * open interest * 100 * spot^2 * 1%
```

Calls are treated as positive gamma exposure and puts as negative gamma
exposure.

Gamma Flip is estimated by sweeping a virtual spot from 0.75x to 1.25x of the
current spot, recalculating total net GEX across the option chain at each
virtual spot, and interpolating the zero crossing. If there is no zero crossing
in that grid, Gamma Flip is shown as `N/A`.

The dashboard keeps full strike-level GEX in `latest_gex_levels_raw.csv`.
For visual charts and dashboard tables, `latest_gex_levels_display.csv` keeps a
short readable subset:

- Top Positive GEX: top 10 positive net-GEX strikes per ticker/bucket/weighting.
- Top Negative GEX: top 10 negative net-GEX strikes per ticker/bucket/weighting.
- Near Spot GEX: top 10 absolute-GEX strikes within spot +/-3%.
- Key Levels: nearest strikes to Spot, Gamma Flip, Near Call Wall, Near Put
  Wall, Far Call Wall, and Far Put Wall.

Standalone GEX charts are written to `charts/` for 0DTE, 1DTE, Weekly, All
Expirations, open-interest weighting, and volume weighting.

Wall definitions:

- Near Call Wall: largest positive call GEX strike within spot +/-10%.
- Near Put Wall: largest negative put GEX strike within spot +/-10%.
- Far Call Wall: important call GEX wall more than +/-10% away.
- Far Put Wall: important put GEX wall more than +/-10% away.
- Overall Call Wall / Overall Put Wall: reference-only full-chain walls.

Dashboard main cards use Near Call Wall and Near Put Wall. Far and Overall walls
are reference levels, not immediate daily pinning levels.

Dealer hedge interpretation:

- Positive Gamma: dealers sell rallies and buy dips, which can create range or
  pinning pressure.
- Negative Gamma: dealers buy rallies and sell dips, which can amplify trend
  and volatility.

Gamma Pinning uses the prepared GEX rows but does not treat every high-OI strike
as a pin candidate. Pinning is based on positive GEX distance from spot and the
overall dealer regime:

- `Strong Pinning Candidate`: major positive GEX within +/-3% and net GEX is positive.
- `Moderate Pinning Candidate`: major positive GEX within +/-5% and net GEX is positive.
- `Mixed / Unstable Pinning`: a near positive wall exists, but net GEX/dealer
  regime is negative.
- `Not Near`: the wall is not close enough for immediate pinning pressure.
- `Far Gamma Wall`: a strike more than +/-10% away. It is displayed as an
  arrival resistance/attraction candidate, not immediate pinning pressure.

Pressure zones are summarized in `latest_gex_pressure_zones.csv`:
Strong Positive GEX Zone, Strong Negative GEX Zone, Near Spot Gamma Zone, Far
Gamma Wall, and Far Positive Wall.

Volatility Surface uses Yahoo Finance option-chain `impliedVolatility`. The
dashboard heatmap groups contracts by moneyness buckets from 0.70x to 1.30x in
0.05 increments. Empty cells mean no usable IV was available for that expiration
and moneyness bucket. ATM IV, Surface IV Rank Proxy, Surface IV Percentile Proxy,
term structure, and 90 put / 110 call skew are shown separately. The rank and
percentile values are cross-sectional surface proxies from the currently
available option chain, not a historical one-year IV Rank.

Trend Regime and Vol Regime are separate:

- Trend Regime uses QQQ/SPY price vs 20MA, 50MA, and 200MA.
- Vol Regime uses VIX and 20-day realized volatility.
- Combined Regime describes mixed states such as `Bull trend, but vol-risk elevated`.

CTA / Vol Control is a rule-based market-structure estimate:

- CTA pressure uses price vs 20MA, 50MA, and 200MA.
- Vol Control is `Risk-Off` when VIX >= 25 or RV20 >= 25%.
- Vol Control is `Risk-On` when VIX < 18 and RV20 < 20%.
- Otherwise it is `Neutral`.

Leveraged ETF Flow uses Yahoo Finance ETF AUM fields when available:
`totalAssets`, then `netAssets`, then a market-cap or shares x price fallback.
The rebalance estimate uses:

```text
estimated_underlying_return = ETF daily return / leverage
estimated_rebalance_flow = AUM * leverage * (leverage - 1) * estimated_underlying_return
```

The pressure label is `estimated_underlying_pressure`: `Underlying Buy
Pressure`, `Underlying Sell Pressure`, or `Neutral`. This is a simplified
mechanical estimate of potential pressure on the underlying basket, not a direct
ETF-share buy/sell signal. It does not observe actual fund trades,
creations/redemptions, swap financing, intraday path dependency, or manager
discretion. If AUM cannot be retrieved, the dashboard keeps running, shows
`N/A`, and records the reason in `output/data_quality_report.csv` and
`output/diagnostics_report.md`.

Korea Market data is configured in `config.yaml` under `market_dashboard`.
KOSPI/KOSPI200/Samsung Electronics/SK Hynix use price history and moving
averages. Korea option-chain GEX and Vol Surface fields remain `N/A` when
option-chain data is unavailable from Yahoo Finance. Korea rows include
exchange, currency, raw close, adjusted close, and a price-scale sanity check.
Korea prices may be affected by Yahoo Finance adjustment, currency, and
exchange-specific quoting conventions.
