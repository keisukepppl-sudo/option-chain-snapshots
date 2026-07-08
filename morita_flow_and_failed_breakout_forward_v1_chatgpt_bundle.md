# Morita Flow And Failed Breakout Forward v1 ChatGPT Bundle

## Completion Status

Implementation completed on branch `research/flow-failed-breakout-forward-v1`.

Final Git commit hash is reported in the final Codex response because this bundle is included in that commit.

## Scope

This change adds two research-only forward logging modules:

- Mechanical Flow Monitor v1
- Failed Breakout Short Forward Logger v1

No live trading behavior is activated.

## Source Lineage

Mechanical-flow metrics are read only from existing repo/local daily flow artifacts under `daily_flow_outputs/<date>/` when available. Missing families are logged as unavailable with a reason.

Failed-breakout lineage:

- RS source: caller-supplied RS panel
- Breakout source: policy-documented scanner rule, `scanner.breakout.detect_breakout close_above_prior_65d_high_with_volume`
- Regime source: caller-supplied same-date D/L regime panel
- Outcome source: caller-supplied OHLCV price panel

## Inherited D/L Thresholds

- `D_high_cutoff = 0.1076297441118458`
- `L_high_cutoff = 0.0211600633543862`

The failed-breakout logger verifies these values and their lineage before running. A modified D/L threshold fails closed.

## Policies And Safety Flags

Policy files:

- `config/morita_mechanical_flow_monitor_v1/policy.json`
- `config/morita_failed_breakout_short_forward_v1/policy.json`

Required state:

- `mode=research_logging_only`
- broker execution disabled
- automatic trade actions disabled
- Pushover emergency disabled
- live short signal disabled
- put alert disabled
- Long S logic changes disabled
- rank/universe rule changes disabled
- regime sizing policy changes disabled

## Failed-Breakout Trigger

Breakout candidate:

- same-day regime is `HIGH_DISPERSION` or `NARROW_LEADERSHIP`
- close is above prior 65-session high
- volume multiple meets the policy minimum
- RS bucket is `RS90_95`, `RS96_97`, or `RS98_PLUS`

Primary failed-breakout trigger:

- close below breakout-day low within 10 trading sessions after breakout
- hypothetical entry is next session open after the first failure close

Diagnostic only:

- intraday low below breakout-day low is recorded but does not create the primary entry by itself

## Output Files

Mechanical flow output directory:

- `outputs/morita_mechanical_flow_monitor_v1/`

Required files:

- `mechanical_flow_daily_context.csv`
- `mechanical_flow_metric_availability.csv`
- `mechanical_flow_source_lineage.json`
- `mechanical_flow_receipt.json`
- `mechanical_flow_content_manifest.json`
- `mechanical_flow_summary.md`

Failed-breakout output directory:

- `outputs/morita_failed_breakout_short_forward_v1/`

Required files:

- `failed_breakout_candidate_watchlist.csv`
- `failed_breakout_entry_log.csv`
- `failed_breakout_forward_outcomes.csv`
- `failed_breakout_regime_summary.csv`
- `failed_breakout_rs_bucket_summary.csv`
- `failed_breakout_source_lineage.json`
- `failed_breakout_receipt.json`
- `failed_breakout_content_manifest.json`
- `failed_breakout_summary.md`

## Compact Examples

Candidate example fields:

```text
ticker=AAA, RS_bucket=RS90_95, regime_state=HIGH_DISPERSION, source_scanner_rule=close_above_prior_65d_high_with_volume
```

Entry example fields:

```text
failure_trigger=close_below_breakout_day_low, research_status=forward_research_only, no_live_signal=true, no_broker_action=true
```

Option modeling:

```text
option_model_status=not_implemented_in_forward_logger_v1
```

No raw OHLCV matrix, account data, broker data, credentials, or order IDs are included in this bundle.

## Tests

Focused:

- `python -m pytest tests/test_morita_mechanical_flow_monitor_v1.py -q --durations=30`
- `python -m pytest tests/test_morita_failed_breakout_short_forward_v1.py -q --durations=30`

Full regression was verified through the repo shard runner after direct `python -m pytest -q` exceeded local wall-clock limits:

- `flow_pressure_core`: 36 passed
- `fragility`: 79 passed, 1 skipped
- `market_impact`: 128 passed
- `flow_pressure_adjacent`: 186 passed
- `cta_vol_environment_notifications`: 100 passed
- collection coverage audit: 530 collected, 530 covered, 0 missing, 0 unexpected, 0 duplicates

## CI

CI status is reported in the final Codex response after the commit is pushed or checked.

## Explicit Confirmations

- No live long S logic changed.
- No rank or universe rule changed.
- No threshold was retuned.
- No live short signal was activated.
- No put alert was activated.
- No broker, account, or order path was accessed.
- All new outputs are research-only.
