# CTA COT Mapping Evidence Gate v1

This gate separates CTA baseline validity from COT-validation eligibility.

An unresolved COT mapping is valid for no-COT CTA baseline generation, but it is forbidden for COT validation. A CTA trend artifact can remain a valid descriptive baseline while being ineligible for COT validation.

## Placeholder Policy

The COT mapping gate rejects blank, null-like, pending, unknown, TBD, unresolved, placeholder, and manual-identification-required values for:

- `cot_market_name`
- `cftc_market_code`

It also rejects placeholder-style prefixes such as:

- `pending_`
- `unknown_`
- `tbd_`
- `placeholder_`
- `unresolved_`

Stable blocking codes:

- `cot_market_name_placeholder`
- `cftc_market_code_placeholder`

No CFTC code or market name is inferred automatically.

Stable mapping status codes:

- `cot_mapping_unresolved`
- `cot_validation_mapping_eligible`

Stable validation block codes:

- `cta_cot_mapping_placeholder_blocked`
- `cta_run_mapping_snapshot_mismatch`
- `cot_row_market_mapping_mismatch`
- `cot_reporting_group_not_found_for_confirmed_mapping`

## Eligibility

COT validation is eligible only when:

- current mapping has non-placeholder COT market name;
- current mapping has non-placeholder CFTC market code;
- relation is one of the allowed explicit labels;
- CTA artifact mapping snapshot exactly matches the current mapping identity;
- COT source exists and validates;
- every selected COT row matches both mapped market name and mapped CFTC code;
- requested reporting group exists;
- timing fields validate.

The mapping identity hash is a stable hash of:

- `market_id`
- `price_instrument`
- `cot_market_name`
- `cftc_market_code`
- `price_to_cot_relation`

## Legacy Artifacts

Legacy CTA artifacts without the mapping-eligibility snapshot remain valid CTA baselines if their content manifest and safety flags verify. They cannot be used for COT validation and must be rerun after manually evidenced mapping is staged.

## COT Row Matching

COT validation must not rely on `market_id` alone. Every selected COT row must match the mapped COT market name and CFTC code. Mixed matching and mismatching rows block the entire validation.

## Non-Claims

This gate does not acquire COT data, perform CFTC lookup, calculate correlations, select models, tune parameters, create market-impact evidence, or authorize trading.

## Read-Only Intake Gate

`validate-cta-cot-intake` validates a staged canonical COT input before CTA artifacts are created. It is intentionally separate from `run-cta-cot-weekly-external-validation`.

The intake gate requires:

- manifest hash validity;
- confirmed non-placeholder mapping;
- selected COT rows matching mapped market name and CFTC code;
- exact requested reporting group;
- unique `market_id + position_as_of_date + reporting_group` keys;
- valid timestamps with `available_timestamp_utc >= publication_timestamp_utc`;
- positive open interest.

It does not read historical CTA artifacts and does not compute COT comparison statistics.
