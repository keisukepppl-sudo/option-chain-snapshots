# QQQ Phase 1.2 Readiness Hardening v1

Phase 1.2 hardens QQQ/TQQQ/SQQQ readiness before any real-data Phase 2 study.

## Explicit Schedule Path

Historical multi-date readiness requires an explicit manifest-declared schedule path:

```powershell
python market_bomb_flow_pressure_research_v0.py run-qqq-phase1-readiness `
  --staging-id <id> `
  --decision-schedule-file sources/decision_schedule.csv `
  --research-timing-class eod_next_session
```

Omitting `--decision-schedule-file` fails closed with
`explicit_decision_schedule_file_required_for_historical_readiness`.
The default `sources/decision_schedule.csv` is allowed only for explicit
synthetic fixture use with `--allow-default-synthetic-decision-schedule`.

## Candidate Audit

Readiness now writes:

- `row_level_timing_audit.csv`
- `historical_revision_selection_audit.csv`
- `historical_candidate_selection_audit.csv`

The candidate audit records every decision-date candidate that can affect
selection for the required observation family. It includes selected rows,
later unavailable revisions, stale AUM, rows outside validity, mapping
effectiveness failures, and timing/lineage failures.

Selected rows alone are not sufficient point-in-time evidence. The audit must
show why competing versions were not selected.

## Immutable Readiness Runs

Each readiness execution creates a unique run directory:

```text
market_bomb_history/flow_pressure_research_v0/staging/<staging_id>/readiness/qqq_tqqq_sqqq_phase1/<readiness_run_id>/
```

The run directory is append-only and contains:

- `readiness_receipt.json`
- `readiness_content_manifest.json`
- schedule validation
- all timing, revision, and candidate audits
- component, mapping, AUM, and coverage summaries
- readiness summary and Markdown report

`readiness_receipt.json` seals the semantic artifact hashes and requires:

- `row_level_decision_schedule_required=true`
- `row_level_timing_audit_verified=true`
- `historical_revision_selection_audit_verified=true`
- `candidate_selection_audit_verified=true`
- `actionization_allowed=false`
- `not_a_real_data_study=true`

## Phase 2 Admission Preflight

Phase 2 must not trust mutable staging state. It must name one explicit
readiness artifact:

```powershell
python market_bomb_flow_pressure_research_v0.py validate-phase2-qqq-admission `
  --readiness-artifact <readiness-run-path>
```

The preflight verifies the exact file set, content hashes, receipt linkage,
readiness status, audit verification flags, and `actionization_allowed=false`.
It creates no release, backtest, notification, or trading output.

Synthetic readiness is rejected for real Phase 2 unless explicitly allowed for
test-only checks.

## Boundary

This hardening patch does not fetch provider data, run Phase 2, run a real-data
study, run a backtest, modify Fragility Score, add alerts, or authorize trading.
CTA and Dealer inputs remain out of scope.
