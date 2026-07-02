# Flow Pressure Phase 1.4A Vol-Control Transparent Replication Report

## Status

- Phase: `flow_pressure_phase1_4a_vol_control_transparent_replication`
- Start commit: `9df0bf596c4c7f8b27ba0d99f2312de7f1e43a1d`
- Final commit: see final Codex response for the exact delivered commit SHA
- Branch: `main`
- Actual data ingested: no
- Network/provider/API/download/scrape: no
- Raw market data committed: no
- Release/backtest/notification/trading/ranking/sizing/execution: no

## Files Added Or Updated

- `.gitignore`
- `market_bomb_vol_control_research_v1.py`
- `config/vol_control_research_v1/model_specs.json`
- `docs/vol_control_transparent_replication_v1.md`
- `docs/vol_control_operator_runbook_v1.md`
- `docs/vol_control_cot_sanity_check_contract_v1.md`
- `tests/test_market_bomb_vol_control_research_v1.py`
- `outputs/flow_pressure_phase1_4a_vol_control_transparent_replication_report_20260702.md`
- `outputs/flow_pressure_phase1_4a_vol_control_transparent_replication_chatgpt_bundle_20260702.md`

## CLI Added

```powershell
python market_bomb_vol_control_research_v1.py build-vol-control-template --input-id <input_id>
python market_bomb_vol_control_research_v1.py inspect-vol-control-input-contract --input-id <input_id>
python market_bomb_vol_control_research_v1.py validate-vol-control-input --input-id <input_id>
python market_bomb_vol_control_research_v1.py run-vol-control-historical-descriptive --input-id <input_id> --benchmark-mode ndx_exact_descriptive --model-spec-id vc_daily_20d_target10_cap100_v1
python market_bomb_vol_control_research_v1.py verify-vol-control-run --run-artifact <run_artifact_path>
python market_bomb_vol_control_research_v1.py build-vol-control-cot-sanity-template --input-id <input_id>
python market_bomb_vol_control_research_v1.py inspect-vol-control-cot-sanity-input --input-id <input_id>
```

## Fixed Registered Specs

All specs are daily, close-to-close simple return, rolling sample standard deviation annualized by 252, exposure floor 0.0, exposure cap 1.0, next eligible session execution assumption, no fitting.

- `vc_daily_20d_target10_cap100_v1`
- `vc_daily_40d_target10_cap100_v1`
- `vc_daily_60d_target10_cap100_v1`
- `vc_daily_20d_target12_cap100_v1`
- `vc_daily_40d_target12_cap100_v1`
- `vc_daily_60d_target12_cap100_v1`

## Timing Convention

For observation date `t`, the model uses only the close and trailing returns through `t`. The resulting target exposure is treated as a next eligible session allocation proxy. `feature_cutoff_date` equals `observation_date`, and `effective_session` must be strictly later than `observation_date`.

## Input Contract

Required:

- `source_manifest.json`
- `sources/benchmark_prices.csv`
- `sources/decision_schedule.csv`

Optional:

- `sources/reference_exposure.csv`
- `sources/cot_weekly.csv`

The module blocks hash mismatches, duplicate benchmark keys, mixed raw/adjusted basis, missing schedule, same-day effective sessions, strict/PIT eligibility claims, and tracked raw files under the ignored vol-control history root.

## COT Boundary

COT is only a coarse weekly sanity-check input. It is not a daily vol-control label, not manager ground truth, not a market-impact source, and not allowed to unlock actionization, Phase 1.3, Phase 2, releases, backtests, or alerts.

## Test Evidence

Focused:

```text
python -m pytest tests/test_market_bomb_vol_control_research_v1.py -q --durations=30 -o cache_dir=C:\t\c\vc14a
16 passed in 6.22s
```

Full local:

```text
python -m pytest -q --durations=30 --basetemp C:\t\full14a -o cache_dir=C:\t\c\full14a
389 passed, 2 skipped, 52 warnings in 1327.56s
```

CI:

```text
GitHub Actions evidence is reported in the final Codex response after push/check completion.
```

## Confirmations

```text
no network/provider/API/download/scrape
no raw market data committed
no strict Phase 1.3 or Phase 2
no release/backtest
no trading/notification/ranking/sizing/execution
leveraged ETF NDX-exact descriptive run was not modified, rerun, reclassified, or combined
actionization_allowed=false
```
