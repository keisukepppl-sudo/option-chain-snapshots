# Flow Pressure Real Data Study v1

This document defines the first timing-valid real-data study for Flow Pressure Research v0. It is research-only. It does not add alerts, rankings, execution logic, Morita Bot integration, or Fragility Score changes.

`actionization_allowed=false` is mandatory for every release, backtest, and conclusion artifact.

## Research Questions

1. Does model-implied leveraged ETF rebalance pressure contain measurable information about subsequent underlying ETF/index returns under point-in-time timing rules?
2. Does model-implied vol-control pressure add descriptive information to later downside-tail outcomes, without changing Fragility Score?

The study does not observe institutional orders, dealer hedging, or causality.

## Data Scope

Required source contract:

```text
flow_provider_contract_v1
```

Required staged daily files:

```text
prices_daily.csv
leveraged_etf_reference.csv
leveraged_etf_aum.csv
vol_control_returns.csv
```

The files must live under:

```text
market_bomb_history/flow_pressure_research_v0/staging/<staging_id>/sources/
```

Raw provider files are local-only and must not be committed.

## Universe

Primary leveraged ETF mappings:

| Underlying | Long leveraged ETF | Inverse leveraged ETF | Priority |
|---|---|---|---:|
| QQQ | TQQQ | SQQQ | 1 |
| SOXX or configured semiconductor proxy | SOXL | SOXS | 1 |
| SPY | UPRO | SPXU | 2 |

Mappings are eligible only when explicitly declared in `leveraged_etf_reference.csv`.

Primary vol-control instruments:

```text
SPY
QQQ
optional explicit semiconductor proxy
```

## Timing Policy

The initial study uses:

```text
research_timing_class=eod_next_session
```

Every included row must prove:

```text
feature_available_at_timestamp <= decision_time < target_start_timestamp
```

Daily data cannot support `intraday_close_window` conclusions. If intraday close-window is requested with daily-only inputs, the run must block or mark the study as insufficient coverage.

## AUM Selection Policy

For leveraged ETF features, select only an observed AUM/NAV/shares row that satisfies:

- `available_at_timestamp <= decision_time`
- `valid_until_timestamp >= decision_time`
- row hash and lineage are valid
- observation age is within the configured freshness policy

AUM must not be forward-filled, duplicated into synthetic future rows, inferred from price alone, or substituted from another undeclared source.

## Feature Policy

Leveraged ETF pressure:

- ETF-level theoretical rebalance pressure
- underlying aggregate normalized pressure
- long and inverse contributions preserved separately
- selected AUM source row ID retained
- AUM observation age retained

Vol-control pressure:

- existing deterministic 20-session and 60-session specifications
- EWMA only when already deterministically configured
- no final-holdout parameter tuning
- no optimized ensemble in this phase

CTA and Dealer modules remain blocked placeholders.

## Backtest Protocol

Chronological split:

```text
train: earliest 60%
validation: next 20%
final_holdout: latest 20%
```

The final holdout must not be used for parameter selection. If sample size is too small, classify results as descriptive or insufficient rather than compressing the protocol silently.

Outcomes include:

- next-session close-to-close return
- three-session close-to-close return
- downside-tail indicator
- maximum adverse excursion
- maximum favorable excursion

## Required Commands

Recommended explicit sequence:

```powershell
python market_bomb_flow_pressure_research_v0.py build-flow-staging-template --staging-id <staging_id>
python market_bomb_flow_pressure_research_v0.py validate-flow-provider-contract --staging-id <staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py audit-flow-timing --staging-id <staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py inspect-flow-source-coverage --staging-id <staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py verify-flow-staging --staging-id <staging_id> --now-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py build-flow-release --staging-id <staging_id> --now-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py verify-flow-release --release-id <release_id>
python market_bomb_flow_pressure_research_v0.py run-flow-backtest --release-id <release_id>
python market_bomb_flow_pressure_research_v0.py verify-flow-backtest --release-id <release_id> --backtest-run-id <run_id>
```

Convenience sequence:

```powershell
python market_bomb_flow_pressure_research_v0.py run-flow-real-data-study --staging-id <staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
```

The convenience command must call the validation, timing audit, source coverage inspection, staging verification, release build, release verification, backtest run, and backtest verification gates in order.

## Required Release Outputs

```text
provider_contract_validation_report.json
timing_audit.csv
timing_audit_summary.json
source_coverage_by_instrument.csv
source_coverage_by_dataset.csv
aum_selection_audit.csv
research_timing_eligibility_summary.md
```

## Required Backtest Outputs

```text
backtest_study_spec.json
chronological_split_manifest.json
feature_partition_definitions.json
outcome_coverage_report.csv
exclusion_reason_report.csv
aum_observation_age_summary.csv
interaction_results.csv
bootstrap_summary.csv
holdout_results.csv
research_conclusion.md
```

`research_conclusion.md` must start with:

```text
This is a timing-valid, research-only analysis of model-implied pressure proxies.  
It does not observe actual institutional or dealer orders, does not authorize trading, and does not modify Fragility Score.
```

## Failure Conditions

Block the run when any of the following occurs:

- provider contract validation fails
- timing audit has blocked or ineligible rows
- timestamps are missing timezone information
- a row is available after the decision time
- source hash mismatches
- undeclared raw files exist
- required declared files are missing
- AUM validity windows are missing or stale
- mapping coverage is missing or ambiguous
- daily-only data is used for intraday close-window claims
- CTA or Dealer sources are attempted
- `actionization_allowed` is not exactly `false`

## Limitations

This study is descriptive and timing-valid, not production trading evidence. Directional results require replication, larger samples, and a separate future promotion review before any operational use.
