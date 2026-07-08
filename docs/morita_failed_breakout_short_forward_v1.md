# Morita Failed Breakout Short Forward Logger v1

## Purpose

`scripts/build_morita_failed_breakout_short_forward_v1.py` logs failed-breakout short research candidates only.

It does not create live short signals, put alerts, broker calls, account access, orders, or automatic execution.

## Regime Gate

The logger loads inherited regime thresholds from `config/morita_failed_breakout_short_forward_v1/policy.json` and verifies lineage before use:

- `D_high_cutoff=0.1076297441118458`
- `L_high_cutoff=0.0211600633543862`

Regime mapping:

- `NORMAL`: D is not high
- `HIGH_DISPERSION`: D is high and L is not high
- `NARROW_LEADERSHIP`: D is high and L is high

The regime row must match `decision_date` exactly. Future regime values are not used.

## RS Buckets

- `RS90_95`: `90.0 <= RS < 96.0`
- `RS96_97`: `96.0 <= RS < 98.0`
- `RS98_PLUS`: `RS >= 98.0`
- `RS_BELOW_90`: reconciliation only

Thresholds are fixed and not optimized.

## Candidate And Failure Rules

Breakout candidate:

- close above prior 65-session high
- volume multiple meets the policy minimum
- same-day regime is `HIGH_DISPERSION` or `NARROW_LEADERSHIP`
- RS bucket is at least `RS90_95`

Primary failed-breakout trigger:

- close below breakout-day low within 10 trading sessions after breakout
- hypothetical entry is next session open after the failure close

Diagnostic-only trigger:

- intraday low below breakout-day low within the tracking window
- this does not create the primary entry unless close also confirms below breakout-day low

## Outputs

Runtime outputs are ignored under `outputs/morita_failed_breakout_short_forward_v1/`:

- `failed_breakout_candidate_watchlist.csv`
- `failed_breakout_entry_log.csv`
- `failed_breakout_forward_outcomes.csv`
- `failed_breakout_regime_summary.csv`
- `failed_breakout_rs_bucket_summary.csv`
- `failed_breakout_source_lineage.json`
- `failed_breakout_receipt.json`
- `failed_breakout_content_manifest.json`
- `failed_breakout_summary.md`

Option modeling is not implemented in v1 and is recorded as `option_model_status=not_implemented_in_forward_logger_v1`.
