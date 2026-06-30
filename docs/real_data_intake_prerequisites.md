# Real Data Intake Prerequisites

Do not run Phase 1.3 readiness until all prerequisites are satisfied.

## Required Evidence

- NDX benchmark mapping is `benchmark_exact`.
- QQQ is labelled as `market_proxy_instrument`, not exact target benchmark.
- Source qualification matrix exists for every required source family.
- Historical availability evidence is gold or approved silver.
- Raw/adjusted price basis is explicit.
- Corporate action ledger exists for TQQQ and SQQQ splits.
- AUM/NAV/shares publication and revision evidence exists.
- Material reconciliation breaks are zero.
- `decision_schedule.csv` is explicit and non-synthetic for real readiness.
- Raw provider data remains local and uncommitted.

## Allowed Outcomes

```text
ready_for_eod_next_session_research
insufficient_coverage
blocked_by_data_quality
blocked_by_timing
blocked_by_mapping
historical_descriptive_only
real_data_intake_incomplete
```

## Guardrails

```text
actionization_allowed=false
raw_provider_data_committed=false
is_observed_flow=false
is_model_estimate=true
not_a_real_data_study=true
```

Do not fetch data, create a release, run Phase 2, run a statistical backtest, send notifications, or authorize trading.
