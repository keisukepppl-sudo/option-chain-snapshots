# Flow Pressure QQQ Phase 1 Readiness v1

This phase implements local readiness validation for the first QQQ proxy family:

```text
Primary target benchmark: NDX
Tradable market proxy: QQQ
Long leveraged ETF: TQQQ
Inverse leveraged ETF: SQQQ
```

It answers only whether manually staged local data is eligible for a timing-valid `eod_next_session` research study. It does not run a backtest, produce alpha evidence, authorize trading, modify Fragility Score, or create Morita notifications.

## Required Manual Exports

The operator must manually stage these CSV files under:

```text
market_bomb_history/flow_pressure_research_v0/staging/<opaque_staging_id>/sources/
```

Required files:

```text
prices_daily.csv
leveraged_etf_reference.csv
leveraged_etf_aum.csv
vol_control_returns.csv
```

Required content:

- `prices_daily.csv`: NDX, QQQ, TQQQ, and SQQQ daily OHLCV or close rows as applicable.
- `leveraged_etf_reference.csv`: explicit `TQQQ -> NDX` and `SQQQ -> NDX` target benchmark mappings, with QQQ separately labelled as market proxy.
- `leveraged_etf_aum.csv`: observed TQQQ and SQQQ AUM, or shares plus NAV.
- `vol_control_returns.csv`: QQQ returns with one explicit basis.

Raw provider exports must stay local. Do not commit provider data, credentials, account IDs, API keys, or customer identifiers.

## Timing Policy

Only this timing class is supported:

```text
eod_next_session
```

Rows must prove point-in-time availability:

```text
available_at_timestamp <= decision_time
```

A date label is not proof of availability. Unknown publication timing blocks predictive readiness. Daily data cannot support `intraday_close_window`.

## AUM Freshness

The latest selected AUM row must be an observed staged source row satisfying:

```text
available_at_timestamp <= decision_time
valid_until_timestamp >= decision_time
aum_observation_age <= max_aum_observation_age_days
```

AUM is never fabricated, forward-filled, repeated into synthetic daily rows, or inferred from price. If both `aum_usd` and `shares_outstanding * nav_per_share` exist and materially disagree, the diagnostic is surfaced.

## Coverage Gate

Configured policy:

```text
minimum coverage: 3 years
preferred coverage: 5 years
minimum eligible sessions after warm-up: 250
```

Coverage is checked separately for:

```text
QQQ daily prices
TQQQ daily prices
SQQQ daily prices
TQQQ AUM
SQQQ AUM
QQQ vol-control returns
```

One valid series does not make the family ready.

## Commands

Create a template:

```powershell
python market_bomb_flow_pressure_research_v0.py build-flow-staging-template --staging-id <opaque_staging_id>
```

After manually populating the CSV files and manifest hashes, run:

```powershell
python market_bomb_flow_pressure_research_v0.py validate-flow-provider-contract --staging-id <opaque_staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py audit-flow-timing --staging-id <opaque_staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py inspect-flow-source-coverage --staging-id <opaque_staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py run-qqq-phase1-readiness --staging-id <opaque_staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py verify-qqq-phase1-readiness --staging-id <opaque_staging_id>
```

Phase 1 stops here. Do not run these commands until a separate Phase 2 instruction is given:

```text
build-flow-release
run-flow-real-data-study
run-flow-statistical-backtest
```

## Readiness Outputs

The readiness-only command writes artifacts under:

```text
market_bomb_history/flow_pressure_research_v0/staging/<opaque_staging_id>/readiness/qqq_tqqq_sqqq_phase1/
```

Required outputs:

```text
provider_contract_validation_report.json
timing_audit.csv
timing_audit_summary.json
source_coverage_by_instrument.csv
source_coverage_by_dataset.csv
aum_selection_audit.csv
research_timing_eligibility_summary.md
real_data_readiness_report.md
qqq_phase1_component_status.csv
mapping_validation.csv
aum_freshness_summary.csv
qqq_phase1_readiness_summary.json
readiness_content_manifest.json
```

`readiness_content_manifest.json` seals the readiness artifacts. `verify-qqq-phase1-readiness` detects tampering, missing files, and file-set changes.

## Status Meanings

Allowed final statuses:

```text
ready_for_eod_next_session_research
insufficient_coverage
blocked_by_data_quality
blocked_by_timing
blocked_by_mapping
historical_descriptive_only
```

`ready_for_eod_next_session_research` is data readiness only. It is not a backtest result, predictive finding, trading permission, or production signal.

## Component Table

The report includes:

| Component | Required | Coverage | Timing | Mapping | AUM freshness | Status | Blocking reason |
|---|---:|---|---|---|---|---|---|
| QQQ daily prices | yes | audited | audited | n/a | n/a | readiness status | reason |
| TQQQ daily prices | yes | audited | audited | audited | n/a | readiness status | reason |
| SQQQ daily prices | yes | audited | audited | audited | n/a | readiness status | reason |
| TQQQ AUM | yes | audited | audited | n/a | audited | readiness status | reason |
| SQQQ AUM | yes | audited | audited | n/a | audited | readiness status | reason |
| QQQ vol-control returns | yes | audited | audited | n/a | n/a | readiness status | reason |

## Explicit Boundary

This report validates data readiness only.
It does not run a backtest, establish predictive value, authorize trading,
or modify Fragility Score.

CTA and Dealer remain blocked and out of scope in Phase 1.
