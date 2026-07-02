# Flow Pressure Phase 1.5A CTA Transparent COT Validation Harness Report

## Status

- Phase: `flow_pressure_phase1_5a_cta_transparent_cot_validation_harness`
- Start commit: `02b8deca25aed0629c62cce3ac094a56b497cc8f`
- Final commit: see final Codex response
- Actual data ingested: no
- Network/provider/API/download/scrape: no
- Raw data committed: no
- Release/backtest/notification/trading/ranking/sizing/execution: no

## Files Added Or Updated

- `.gitignore`
- `market_bomb_cta_research_v1.py`
- `config/cta_research_v1/model_specs.json`
- `docs/cta_transparent_trend_replication_v1.md`
- `docs/cta_cot_weekly_external_validation_v1.md`
- `docs/cta_operator_runbook_v1.md`
- `tests/test_market_bomb_cta_research_v1.py`
- `outputs/flow_pressure_phase1_5a_cta_transparent_cot_validation_report_20260702.md`
- `outputs/flow_pressure_phase1_5a_cta_transparent_cot_validation_chatgpt_bundle_20260702.md`

## CLI Commands

```powershell
python market_bomb_cta_research_v1.py build-cta-template --input-id <input_id>
python market_bomb_cta_research_v1.py inspect-cta-input-contract --input-id <input_id>
python market_bomb_cta_research_v1.py validate-cta-input --input-id <input_id>
python market_bomb_cta_research_v1.py run-cta-historical-descriptive --input-id <input_id> --market-id <market_id> --model-spec-id cta_ts_60d_binary_v1
python market_bomb_cta_research_v1.py verify-cta-run --run-artifact <exact_run_artifact_path>
python market_bomb_cta_research_v1.py build-cta-cot-validation-template --input-id <input_id>
python market_bomb_cta_research_v1.py inspect-cta-cot-validation-input --input-id <input_id>
python market_bomb_cta_research_v1.py run-cta-cot-weekly-external-validation --cta-run-artifact <exact_cta_run_artifact_path> --input-id <input_id> --market-id <market_id> --cot-reporting-group <exact_reporting_group>
python market_bomb_cta_research_v1.py verify-cta-cot-validation --validation-artifact <exact_validation_artifact_path>
```

## Fixed CTA Model Registry

- `cta_ts_20d_binary_v1`
- `cta_ts_60d_binary_v1`
- `cta_ts_120d_binary_v1`
- `cta_ts_20_60_120_equal_weight_v1`

All are daily close-to-close time-series momentum specs with fixed horizons, no fitting, no model selection, exposure in `[-1.0, 1.0]`, and next-session effect.

## Timing Contract

Only closes through observation date `t` can enter the model decision at `t`. The target exposure becomes effective on the next eligible session. `feature_cutoff_date` equals `observation_date`; same-day effective sessions are blocked.

## Input Contract

Required for CTA:

- `source_manifest.json`
- `sources/daily_market_prices.csv`
- `sources/market_mapping.csv`
- `sources/decision_schedule.csv`

Required only for COT external validation:

- `sources/cot_weekly.csv`

## COT Validation Boundary

COT validation supports:

- `as_of_ex_post_only`
- `availability_monitoring_only`

COT is never used in CTA signal construction. Metrics are external, post hoc, and do not imply automatic acceptance, model selection, market impact, or trading action.

## Test Evidence

Focused:

```text
python -m pytest tests/test_market_bomb_cta_research_v1.py -q --durations=30
16 passed in 14.02s
```

Full local and CI evidence are reported in the final Codex response.

Full local:

```text
python -m pytest -q --durations=30 --basetemp C:\t\full15a -o cache_dir=C:\t\c\full15a
405 passed, 2 skipped, 52 warnings in 1743.17s
```

## Guardrail Confirmation

```text
no actual data ingested
no network/provider/API/download/scrape
no raw data committed
no leveraged-ETF or vol-control modification/rerun
no strict Phase 1.3 or Phase 2
no release/backtest
no parameter fitting or model selection
no trading/notification/ranking/sizing/execution
actionization_allowed=false
```
