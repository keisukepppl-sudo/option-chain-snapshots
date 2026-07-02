# Vol-Control Transparent Replication v1

This module is a research-only transparent replication of a simple volatility-control allocation rule. It does not estimate actual manager flow, market impact, dealer positioning, or tradable signals.

## Scope

- Module: `market_bomb_vol_control_research_v1.py`
- Mode: `historical_descriptive_vol_control_replication`
- Eligibility: historical descriptive only
- Actionization: disabled
- Phase 1.3 readiness: not unlocked
- Phase 2 admission: not unlocked
- Release, backtest, notification, sizing, and trading: prohibited

## Canonical Inputs

Inputs live under:

`market_bomb_history/vol_control_research_v1/input/<input_id>/`

Required files:

- `source_manifest.json`
- `sources/benchmark_prices.csv`
- `sources/decision_schedule.csv`

Optional research context files:

- `sources/reference_exposure.csv`
- `sources/cot_weekly.csv`

`benchmark_prices.csv` columns:

`date,instrument,raw_close,raw_or_adjusted`

`decision_schedule.csv` columns:

`observation_date,effective_session,decision_timestamp_utc,session_source`

The decision schedule is explicit. The model refuses same-day or prior-day effective sessions because an observation-date close can only inform a next eligible session allocation proxy.

## Model Formula

The fixed model specs are in `config/vol_control_research_v1/model_specs.json`.

For each observation date:

1. Compute close-to-close simple return from the selected benchmark.
2. Compute rolling sample standard deviation using only returns through the observation date.
3. Annualize volatility with `sqrt(252)`.
4. Compute `target_exposure = target_volatility / realized_volatility`.
5. Clip target exposure to `[0.0, 1.0]`.
6. Compare target exposure with the prior valid target exposure.

Labels:

- `increase_risk`
- `reduce_risk`
- `unchanged`
- `input_unavailable`

Rows with insufficient history or non-positive realized volatility are marked `input_unavailable`.

## Benchmark Modes

- `ndx_exact_descriptive`: uses `NDX` rows only and records `benchmark_exact`.
- `qqq_proxy_only_descriptive`: uses `QQQ` rows only and records `proxy_only`.

The module never substitutes QQQ for NDX implicitly.

## Outputs

Runs are written under ignored local storage:

`market_bomb_history/vol_control_research_v1/historical_runs/<run_id>/`

Each run writes:

- `vol_control_input_validation_report.json`
- `vol_control_model_spec_snapshot.json`
- `vol_control_decision_timing_audit.csv`
- `vol_control_daily_exposure.csv`
- `vol_control_summary.md`
- `vol_control_limitations.md`
- `vol_control_run_receipt.json`
- `vol_control_content_manifest.json`

The content manifest supports tamper checks for the generated artifact set.

## Provenance And Characterization

New-generation vol-control artifacts record repository commit, module source hash, source manifest hash, and model registry hash. Legacy artifacts remain verifiable under their legacy compatibility behavior.

Cross-spec characterization is descriptive state-path analysis only. It uses six fixed NDX specifications and seven fixed windows. It has no external manager-flow ground truth and does not rank, select, accept, or reject a model.
