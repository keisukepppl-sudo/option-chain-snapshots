# ChatGPT Bundle: Flow Pressure Phase 1.4A Vol-Control Transparent Replication

Use this as the single handoff prompt for the next ChatGPT/Codex review.

## Objective

Review the implementation of a standalone, research-only daily volatility-control transparent replication harness. The harness answers:

```text
Given a fixed volatility-target specification, what was the model exposure at each EOD decision point, and did target exposure rise, fall, or remain unchanged for the next eligible session?
```

It must remain descriptive research only.

## Implemented Files

- `market_bomb_vol_control_research_v1.py`
- `config/vol_control_research_v1/model_specs.json`
- `docs/vol_control_transparent_replication_v1.md`
- `docs/vol_control_operator_runbook_v1.md`
- `docs/vol_control_cot_sanity_check_contract_v1.md`
- `tests/test_market_bomb_vol_control_research_v1.py`
- `.gitignore`
- `outputs/flow_pressure_phase1_4a_vol_control_transparent_replication_report_20260702.md`

## CLI Surface

```powershell
python market_bomb_vol_control_research_v1.py build-vol-control-template --input-id <input_id>
python market_bomb_vol_control_research_v1.py inspect-vol-control-input-contract --input-id <input_id>
python market_bomb_vol_control_research_v1.py validate-vol-control-input --input-id <input_id>
python market_bomb_vol_control_research_v1.py run-vol-control-historical-descriptive --input-id <input_id> --benchmark-mode ndx_exact_descriptive --model-spec-id vc_daily_20d_target10_cap100_v1
python market_bomb_vol_control_research_v1.py verify-vol-control-run --run-artifact <run_artifact_path>
python market_bomb_vol_control_research_v1.py build-vol-control-cot-sanity-template --input-id <input_id>
python market_bomb_vol_control_research_v1.py inspect-vol-control-cot-sanity-input --input-id <input_id>
```

## Model Specs

Six fixed specs exist:

- `vc_daily_20d_target10_cap100_v1`
- `vc_daily_40d_target10_cap100_v1`
- `vc_daily_60d_target10_cap100_v1`
- `vc_daily_20d_target12_cap100_v1`
- `vc_daily_40d_target12_cap100_v1`
- `vc_daily_60d_target12_cap100_v1`

They use:

- daily frequency
- close-to-close simple returns
- rolling sample standard deviation
- annualization factor 252
- target volatility 10% or 12%
- trailing windows 20/40/60 sessions
- exposure floor 0.0
- exposure cap 1.0
- next eligible session timing
- no parameter fitting

## Timing Contract

- Observation-date close and trailing returns through `t` are the only allowed features.
- The output exposure is effective for the next eligible session.
- `feature_cutoff_date == observation_date`.
- Same-day or prior effective sessions are blocked.
- Changing a future price cannot change earlier decisions.

## Input Contract

Required:

- `source_manifest.json`
- `sources/benchmark_prices.csv`
- `sources/decision_schedule.csv`

Optional:

- `sources/reference_exposure.csv`
- `sources/cot_weekly.csv`

The harness blocks:

- content SHA mismatch
- duplicate benchmark keys
- mixed raw/adjusted basis
- missing schedule
- same-day effective session
- strict/PIT eligibility claims
- silent NDX/QQQ substitution
- tracked raw files under `market_bomb_history/vol_control_research_v1/`

## COT Boundary

COT is supported only as a weekly sanity-check input. It is not daily vol-control truth, not actual manager exposure, not market impact, and cannot unlock Phase 1.3, Phase 2, release, backtest, notification, trading, sizing, ranking, or execution.

## Validation Evidence

Focused test:

```text
16 passed in 6.22s
```

Full local test:

```text
389 passed, 2 skipped, 52 warnings in 1327.56s
```

CI:

```text
GitHub Actions evidence is reported in the final Codex response after push/check completion.
```

## Required Review Questions

1. Does the implementation preserve the research-only boundary?
2. Does the daily EOD timing convention prevent lookahead?
3. Are NDX exact and QQQ proxy modes sufficiently separated?
4. Are the fixed specs adequate for Phase 1.4A without tuning?
5. Are the input manifest and immutable artifact contracts strict enough?
6. Is the COT sanity-check boundary clear enough to prevent misuse?
7. Are any outputs accidentally actionizable?

## Confirmed Non-Actions

```text
no actual data ingestion
no network/provider/API/download/scrape
no raw market data committed
no strict Phase 1.3 or Phase 2
no release/backtest
no notification/trading/ranking/sizing/execution
no leveraged ETF rerun/reclassification/combination
```
