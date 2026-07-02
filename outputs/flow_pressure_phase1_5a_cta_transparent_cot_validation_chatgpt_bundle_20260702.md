# ChatGPT Bundle: Flow Pressure Phase 1.5A CTA Transparent COT Validation Harness

Use this as the single handoff prompt for review.

## Objective

Review a standalone, research-only CTA trend-model module plus separate weekly COT external-validation harness.

The CTA model produces a normalized single-market trend-state path:

```text
-1.0 = normalized risk-off / short trend state
 0.0 = neutral / unavailable
+1.0 = normalized risk-on / long trend state
```

COT validation is a coarse external comparator only. It is not CTA ground truth, not actual flow, not market impact, and not a parameter-tuning target.

## Implemented Files

- `market_bomb_cta_research_v1.py`
- `config/cta_research_v1/model_specs.json`
- `docs/cta_transparent_trend_replication_v1.md`
- `docs/cta_cot_weekly_external_validation_v1.md`
- `docs/cta_operator_runbook_v1.md`
- `tests/test_market_bomb_cta_research_v1.py`
- `.gitignore`
- `outputs/flow_pressure_phase1_5a_cta_transparent_cot_validation_report_20260702.md`

## CLI Surface

```powershell
python market_bomb_cta_research_v1.py build-cta-template --input-id <input_id>
python market_bomb_cta_research_v1.py inspect-cta-input-contract --input-id <input_id>
python market_bomb_cta_research_v1.py validate-cta-input --input-id <input_id>
python market_bomb_cta_research_v1.py run-cta-historical-descriptive --input-id <input_id> --market-id <market_id> --model-spec-id <model_spec_id>
python market_bomb_cta_research_v1.py verify-cta-run --run-artifact <exact_run_artifact_path>
python market_bomb_cta_research_v1.py build-cta-cot-validation-template --input-id <input_id>
python market_bomb_cta_research_v1.py inspect-cta-cot-validation-input --input-id <input_id>
python market_bomb_cta_research_v1.py run-cta-cot-weekly-external-validation --cta-run-artifact <exact_cta_run_artifact_path> --input-id <input_id> --market-id <market_id> --cot-reporting-group <exact_reporting_group>
python market_bomb_cta_research_v1.py verify-cta-cot-validation --validation-artifact <exact_validation_artifact_path>
```

## Fixed Model Registry

- `cta_ts_20d_binary_v1`
- `cta_ts_60d_binary_v1`
- `cta_ts_120d_binary_v1`
- `cta_ts_20_60_120_equal_weight_v1`

All specs are predeclared, not fitted. No weights, thresholds, horizons, or model choices are optimized.

## Daily Timing Contract

- Observation at `t` uses closes through `t` only.
- Exposure at `t` is effective next eligible session.
- `feature_cutoff_date == observation_date`.
- Same-day effective sessions are rejected.
- Future price changes cannot alter prior decisions.

## Input Contract

CTA run requires:

- `daily_market_prices.csv`
- `market_mapping.csv`
- `decision_schedule.csv`
- `source_manifest.json`

COT validation additionally requires:

- `cot_weekly.csv`

`market_mapping.csv` must preserve relation labels:

- `direct_futures_match`
- `cash_index_proxy_for_futures_cot`
- `etf_proxy_for_futures_cot`

## COT Validation

Two alignment modes are implemented:

- `as_of_ex_post_only`
- `availability_monitoring_only`

Metrics include level/change correlations, sign agreement rates, and turning-point lag metrics. Metrics are unavailable, not fabricated, when coverage is below 26 weekly pairs.

No automatic acceptance threshold is applied. A high in-sample correlation alone is not sufficient.

## Test Evidence

Focused:

```text
16 passed in 14.02s
```

Full local and CI evidence are reported in the final Codex response.

Full local:

```text
405 passed, 2 skipped, 52 warnings in 1743.17s
```

## Guardrails

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
