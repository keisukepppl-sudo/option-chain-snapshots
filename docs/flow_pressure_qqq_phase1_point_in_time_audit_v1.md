# QQQ Phase 1 Row-Level Point-In-Time Audit v1

Phase 1 historical readiness now requires a manifest-declared `decision_schedule.csv`. A single global `--decision-time-utc` is no longer accepted for multi-date historical readiness.

## Decision Schedule Contract

Required columns:

- `decision_schedule_row_id`
- `decision_date`
- `decision_time_utc`
- `target_session_date`
- `target_start_timestamp_utc`
- `research_timing_class`
- `decision_time_policy_version`
- `schedule_generation_method`
- `schedule_source_description`
- `is_synthetic_fixture`
- `source_name`
- `source_file`
- `dataset_version`

Allowed `schedule_generation_method` values are `manual_explicit_schedule`, `validated_observed_session_sequence`, and `synthetic_fixture`. Phase 1.1 permits only `eod_next_session`.

## Required Outputs

`run-qqq-phase1-readiness` writes the existing readiness artifacts plus:

- `decision_schedule_validation_report.json`
- `row_level_timing_audit.csv`
- `historical_revision_selection_audit.csv`

The row-level audit records decision date, target session, source row identity, publication/revision identity, availability evidence, timing eligibility, selection eligibility, selected feature row, and exclusion reason.

## Readiness Rules

Rows are predictive-ready only when their availability evidence is one of:

- `source_observed_timestamp`
- `provider_documented_publication_schedule`
- `provider_versioned_export`

Committed synthetic tests may use `synthetic_fixture`. `operator_unverified` and `unknown` availability evidence block predictive readiness.

For each decision row, the selector chooses the latest legally available source row at `decision_time_utc`; later revisions are excluded but remain visible in `historical_revision_selection_audit.csv`.

## CLI

```powershell
python market_bomb_flow_pressure_research_v0.py build-qqq-phase1-decision-schedule-template --staging-id <id>
python market_bomb_flow_pressure_research_v0.py validate-qqq-phase1-decision-schedule --staging-id <id> --decision-schedule-file sources/decision_schedule.csv
python market_bomb_flow_pressure_research_v0.py run-qqq-phase1-readiness --staging-id <id> --decision-schedule-file sources/decision_schedule.csv
python market_bomb_flow_pressure_research_v0.py verify-qqq-phase1-readiness --staging-id <id>
```

## Boundary

This is readiness validation only. It does not run the real-data study, does not run a backtest, does not create a release, does not authorize trading, and does not modify Fragility Score.
