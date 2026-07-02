# ChatGPT Bundle: Flow Pressure Phase 1.5C.0 CTA COT Mapping Gate

Use this as the single handoff prompt for review.

## Objective

Review the CTA COT mapping-evidence eligibility gate and artifact-binding hardening.

The goal is to ensure `run-cta-cot-weekly-external-validation` cannot run until a non-placeholder COT mapping is manually evidenced, manifest-linked, and bound to the CTA run artifact.

## Implemented Behavior

- `is_placeholder_cot_identifier(value)` rejects blank, null-like, pending, unknown, TBD, unresolved, placeholder, and prefix placeholder forms.
- `evaluate_cot_mapping_eligibility(mapping_row)` emits:
  - `cot_mapping_status`
  - `cot_validation_eligible`
  - `blocking_codes`
  - `mapping_identity_hash`
- Future CTA run artifacts include mapping eligibility fields in:
  - `cta_market_mapping_snapshot.json`
  - `cta_run_receipt.json`
- COT validation preflight blocks before artifact creation when mapping is unresolved, snapshot is legacy/mismatched, rows mismatch mapping, or reporting group is absent.
- Future successful validation writes `cta_cot_mapping_eligibility_snapshot.json`.
- Validation verification requires mapping snapshot match and required safety flags.

Stable status/block codes:

- `cot_mapping_unresolved`
- `cot_validation_mapping_eligible`
- `cta_cot_mapping_placeholder_blocked`
- `cta_run_mapping_snapshot_mismatch`
- `cot_row_market_mapping_mismatch`
- `cot_reporting_group_not_found_for_confirmed_mapping`

## Existing Baseline Boundary

Existing Phase 1.5B CTA baselines remain valid CTA artifacts. They are COT-ineligible because they have pending COT identifiers and legacy mapping snapshots.

Inspection for `manual_cta_ndx_20260702` reports:

```text
cot_mapping_status=cot_mapping_unresolved
cot_validation_eligible=false
blocking_codes=cot_market_name_placeholder,cftc_market_code_placeholder
cot_source_status=absent_or_header_only
```

## Snapshot Binding Rule

Current mapping must exactly match the CTA artifact mapping snapshot:

- `market_id`
- `price_instrument`
- `cot_market_name`
- `cftc_market_code`
- `price_to_cot_relation`
- `mapping_identity_hash`

Legacy missing fields block COT validation but do not invalidate CTA baseline verification.

## COT Row Matching Rule

Every selected COT row must match:

- mapped COT market name
- mapped CFTC code

`market_id` alone is insufficient. Mixed matching and mismatching rows block the entire validation.

## Tests

Focused:

```text
27 passed in 9.96s
```

Full local:

```text
416 passed, 2 skipped, 52 warnings in 788.14s
```

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
