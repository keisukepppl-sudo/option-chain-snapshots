# ChatGPT Bundle: Flow Pressure Phase 1.3A Precision Data Sourcing

## Objective

Implement Phase 1.3A before retrying real-data intake. The goal is to fix the QQQ/TQQQ/SQQQ data-source design so Phase 1.3 cannot accidentally treat QQQ as the exact benchmark for TQQQ/SQQQ or treat current revised CSVs as historical PIT data.

## Repository Context

- Repository: `keisukepppl-sudo/option-chain-snapshots`
- Starting point requested: `5043368`
- Phase 1.3 prior result: `real_data_intake_incomplete`
- Phase 1.3A scope: source qualification, benchmark correction, PIT eligibility design, manual data acquisition runbook

## Implemented Changes

1. Added source qualification module:
   - `market_bomb_flow_pressure_source_qualification_v1.py`

2. Added config:
   - `market_bomb_config/flow_pressure_source_qualification_v1_policy.json`
   - `market_bomb_config/flow_pressure_source_qualification_v1_schema.json`

3. Added docs:
   - `docs/flow_pressure_qqq_source_qualification_matrix_v1.md`
   - `docs/flow_pressure_qqq_data_acquisition_runbook_v1.md`
   - `docs/flow_pressure_qqq_benchmark_mapping_correction_v1.md`
   - `docs/flow_pressure_qqq_price_basis_and_corporate_actions_policy.md`
   - `docs/flow_pressure_qqq_reconciliation_plan.md`
   - `docs/vendor_qualification_questionnaire.md`
   - `docs/proshares_publication_timing_inquiry.md`
   - `docs/real_data_intake_prerequisites.md`

4. Updated existing docs to avoid stale QQQ exact-mapping language:
   - `docs/flow_pressure_qqq_phase1_readiness_v1.md`
   - `docs/flow_pressure_operator_runbook_v1.md`

5. Added tests:
   - `tests/test_market_bomb_flow_pressure_source_qualification_v1.py`

6. Added review outputs:
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/qqq_source_qualification_matrix.csv`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/qqq_source_qualification_report.md`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/qqq_benchmark_mapping_validation.json`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/qqq_price_basis_and_corporate_actions_policy.md`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/qqq_reconciliation_plan.md`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/vendor_qualification_questionnaire.md`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/proshares_publication_timing_inquiry.md`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/real_data_intake_prerequisites.md`
   - `outputs/flow_pressure_phase1_3a_precision_data_sourcing/qualification_content_manifest.json`

## Benchmark Correction

Correct model:

```text
primary_target_benchmark = NDX
tradable_market_proxy = QQQ
leveraged_long_etf = TQQQ
leveraged_inverse_etf = SQQQ
```

Rules:

- TQQQ/SQQQ production-like target benchmark must be NDX.
- QQQ is a market proxy and research outcome proxy.
- TQQQ -> QQQ exact production mapping is rejected.
- SQQQ -> QQQ exact production mapping is rejected.
- Legacy QQQ proxy fixtures may remain only if synthetic and marked not for real readiness.

## Source Qualification

Allowed statuses:

```text
gold_point_in_time_eligible
silver_documented_schedule_eligible
authoritative_but_historical_vintage_unproven
historical_descriptive_only
blocked_by_data_quality
blocked_by_timing
```

Predictive Phase 1.3 readiness can only proceed with:

```text
gold_point_in_time_eligible
silver_documented_schedule_eligible
```

Current revised CSV exports without historical publication/revision evidence must remain:

```text
historical_descriptive_only
```

## Single Decision Time Boundary

`validate-flow-provider-contract --decision-time-utc ...` is allowed for:

- CSV schema validation
- type validation
- path containment
- manifest hash validation
- generic timestamp ordering checks

It is not allowed to prove:

- historical row-level timing eligibility
- historical AUM selection
- revision eligibility
- decision-date coverage
- predictive Phase 1 readiness
- Phase 2 admission

## Validation

Added synthetic-only test coverage for:

- TQQQ -> NDX exact mapping pass
- SQQQ -> NDX exact mapping pass
- QQQ proxy classification
- TQQQ/SQQQ -> QQQ exact production mapping rejection
- legacy QQQ proxy fixture-only handling
- gold/silver/descriptive qualification classification
- current export date not treated as historical availability
- single decision timestamp role separation
- later revision blocking historical decision rows
- raw/adjusted mismatch detection
- split ledger reconciliation
- unresolved discrepancy blocking predictive use
- AUM vs shares*NAV diagnostic retention
- artifact tamper detection
- raw provider data not tracked by git

Added test result:

```text
24 passed
```

Additional validation:

```text
tests/test_market_bomb_flow_pressure_statistical_backtest_v1.py: 9 passed
full pytest suite: timed out at 5 minutes
tests/test_market_bomb_flow_pressure_research_v0.py: timed out at 3 minutes
```

The timeout is recorded as an open validation gap, not as a pass.

## Guardrails

- No real data was fetched.
- No provider data was committed.
- No Phase 1.3 readiness was run.
- No Phase 2 study was run.
- No release/backtest/notification/trading output was created.
- Fragility Score, CTA, Dealer, and Morita production logic were not changed.
- `actionization_allowed=false`.

## Next Human Task

Before Phase 1.3 can be retried, manually stage a complete real-data package with:

- NDX daily market data
- QQQ daily market data
- TQQQ daily market data
- SQQQ daily market data
- TQQQ/SQQQ ProShares NAV/AUM/shares
- TQQQ/SQQQ split history
- benchmark mapping documentation
- explicit `decision_schedule.csv`
- source qualification evidence
- publication/revision/availability evidence
- reconciliation evidence

If gold or approved silver evidence is unavailable, the correct result is `historical_descriptive_only`, not Phase 2 admission.
