# Morita Put-Skew Quick Screen v1

This module is a bounded local-archive quick screen for Morita Bot outcomes
versus QQQ index put skew, single-name put skew, and single-name minus QQQ
relative skew.

It uses only existing local option-chain snapshot files. It does not download
options data, call providers, reconstruct IV, infer dealer hedging, run option
PnL, optimize thresholds, change Bot rules, or create a live trading filter.

## Skew Definition

For each ticker and snapshot date:

- Select one expiration from 21 to 45 calendar DTE, closest to 30 DTE.
- ATM IV is the average of the closest ATM call and/or put within +/-3% of spot.
- OTM put IV is the put closest to 90% moneyness, restricted to 85%-95%.
- `put_skew_abs = otm_put_iv - atm_iv`.
- `put_skew_normalized = put_skew_abs / atm_iv`.

Only direct provider IV is used. Missing IV is not estimated.

## Timing

For each signal decision date, the script uses only the closest snapshot at or
before the signal decision date. Date-only snapshots are treated as
`snapshot_date_end_of_day_proxy`. Maximum lag is one baseline trading session.

## Outputs

The run writes:

- `skew_source_availability.csv`
- `skew_snapshot_coverage.csv`
- `skew_daily_index_panel.csv`
- `skew_signal_context_panel.csv`
- `skew_state_cutoffs.csv`
- `skew_outcome_summary.csv`
- `skew_rank_summary.csv`
- `skew_joint_index_single_name_summary.csv`
- `skew_quality_tier_summary.csv`
- `skew_receipt.json`
- `skew_content_manifest.json`
- `skew_summary.md`

It also writes `morita_put_skew_quick_screen_chatgpt_bundle.md`.

If local snapshot coverage is inadequate, the output reports controlled
coverage failure rather than fabricating data.
