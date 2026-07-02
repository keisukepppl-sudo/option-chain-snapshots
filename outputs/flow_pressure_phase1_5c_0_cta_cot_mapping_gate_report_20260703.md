# Flow Pressure Phase 1.5C.0 CTA COT Mapping Gate Report

## Status

- Phase: `flow_pressure_phase1_5c_0_cta_cot_mapping_gate`
- Start commit: `2fea459d1beb3102e073354a9fb6e4892fbe8525`
- Final commit: see final Codex response
- Real COT data acquired/ingested: no
- CFTC lookup or identifier invention: no
- Local raw input/artifact modification: no

## Files Changed

- `market_bomb_cta_research_v1.py`
- `tests/test_market_bomb_cta_research_v1.py`
- `docs/cta_cot_mapping_evidence_gate_v1.md`
- `docs/cta_cot_weekly_external_validation_v1.md`
- `docs/cta_operator_runbook_v1.md`
- `docs/cta_transparent_trend_replication_v1.md`
- `outputs/flow_pressure_phase1_5c_0_cta_cot_mapping_gate_report_20260703.md`
- `flow_pressure_phase1_5c_0_cta_cot_mapping_gate_chatgpt_bundle.md`

## New Mapping Gate Behavior

- Placeholder COT identifiers hard-block validation before output directory creation.
- Current mapping must match CTA artifact mapping snapshot exactly.
- COT rows must match both mapped market name and mapped CFTC code.
- Requested reporting group must exist for the confirmed mapping.
- Future successful validation writes `cta_cot_mapping_eligibility_snapshot.json`.
- Validation verification requires mapping snapshot match and safety flags.

## Placeholder Policy

Rejected values include blank/null-like values, `pending_manual_cot_identification`, `pending`, `unknown`, `tbd`, `n/a`, `unresolved`, `placeholder`, and prefixed forms such as `pending_`, `unknown_`, `tbd_`, `placeholder_`, and `unresolved_`.

Stable blocking codes:

- `cot_market_name_placeholder`
- `cftc_market_code_placeholder`

Stable mapping and validation status codes:

- `cot_mapping_unresolved`
- `cot_validation_mapping_eligible`
- `cta_cot_mapping_placeholder_blocked`
- `cta_run_mapping_snapshot_mismatch`
- `cot_row_market_mapping_mismatch`
- `cot_reporting_group_not_found_for_confirmed_mapping`

## Boundary

CTA baseline validity and COT-validation eligibility are separate. Existing Phase 1.5B baselines remain valid CTA artifacts, but legacy artifacts without the new mapping-eligibility snapshot cannot be COT-validated.

## Existing Phase 1.5B Inspection

`manual_cta_ndx_20260702` inspects as:

```text
cot_mapping_status=cot_mapping_unresolved
cot_validation_eligible=false
blocking_codes=cot_market_name_placeholder,cftc_market_code_placeholder
cot_source_status=absent_or_header_only
```

One existing Phase 1.5B baseline artifact was reverified as CTA-valid:

```text
20260702T153929Z_294f9c1109fe: valid
```

## Test Evidence

Focused:

```text
python -m pytest tests/test_market_bomb_cta_research_v1.py -q --durations=30
27 passed in 9.96s
```

Full local:

```text
python -m pytest -q --durations=30
416 passed, 2 skipped, 52 warnings in 788.14s
```

CI evidence is reported in the final Codex response.

## Guardrails

```text
no COT data acquired/ingested
no CFTC lookup or identifier invention
no network/provider/API/download/scrape
no local raw input/artifact modification
no tuning/ranking/selection
no correlation study
no other-module integration
no strict Phase 1.3/Phase 2/release/backtest
no trading/notification/sizing/execution
actionization_allowed=false
```
