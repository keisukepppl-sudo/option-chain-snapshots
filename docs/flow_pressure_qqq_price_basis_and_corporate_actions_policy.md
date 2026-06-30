# Flow Pressure QQQ Price Basis and Corporate Actions Policy

## Required Price Fields

Keep raw and adjusted values separate:

```text
raw_open
raw_high
raw_low
raw_close
vendor_adjusted_close
price_adjustment_method
```

Do not mix raw and adjusted fields within one return series.

## Split Ledger

TQQQ and SQQQ split handling must be driven by an explicit corporate action ledger:

```text
corporate_action_id
instrument
action_type
effective_date
announcement_or_availability_timestamp
split_ratio
source_authority
source_row_id
source_file
dataset_version
```

## PIT Adjustment Rule

- Preserve raw prices.
- Preserve the action ledger.
- Recreate adjusted returns only through a documented transform.
- Do not treat a current vendor adjusted series as automatically point-in-time safe.
- Label returns as `raw_return` or `point_in_time_corporate_action_adjusted_return`.

## Blocking Conditions

Predictive qualification is blocked by:

- raw/adjusted mismatch between primary and secondary sources,
- split discontinuity without a ledger entry,
- unknown price basis,
- material unresolved price discrepancy,
- adjusted history that lacks historical vintage evidence.
