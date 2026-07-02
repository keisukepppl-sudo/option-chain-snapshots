# CTA COT Weekly External Validation v1

COT weekly validation is a coarse, post hoc external consistency study. It compares a fixed CTA model path with an externally supplied weekly COT position series.

COT is not CTA-only positioning, actual CTA AUM, daily CTA flow, intraday signal, causal market-impact proof, or a parameter-tuning target.

## Alignment Modes

The validation harness produces two explicit modes and never conflates them.

### As-Of Ex Post Only

`alignment_mode=as_of_ex_post_only`

This compares model exposure at the COT `position_as_of_date` with COT position reported for the same as-of date. It is ex post only and cannot be used as a historical decision input.

### Availability Monitoring Only

`alignment_mode=availability_monitoring_only`

This compares model state at or immediately before `available_timestamp_utc` with the newly available COT record. It cannot alter the historical CTA model path.

## Metrics

Metrics are reported only when minimum pair coverage is reached. The default minimum is 26 weekly pairs.

Metrics:

- level Pearson correlation
- level Spearman correlation
- change Pearson correlation
- change Spearman correlation
- level sign agreement rate
- change sign agreement rate
- gross turning-point agreement rate
- median turning-point lag in weeks

No automatic acceptance threshold is applied. A high in-sample correlation can be affected by mixed COT participants, proxy mismatch, common trend exposure, release lag, and overfitting risk. Cross-period and cross-market stability must be evaluated separately later.

## Boundary

COT never enters CTA daily signal construction. There is no daily COT interpolation, no model selection, no auto-promotion, no release, no backtest, no alert, and no trading instruction.

## Mapping Gate

COT validation cannot run until the selected mapping has manually evidenced, non-placeholder `cot_market_name` and `cftc_market_code` values. Pending identifiers are valid for no-COT baseline generation but hard-block validation before an artifact directory is created.

The current mapping must match the CTA run artifact mapping snapshot exactly, including the mapping identity hash. Legacy CTA artifacts without the mapping-eligibility snapshot remain valid CTA baselines, but they must be rerun after confirmed mapping is staged before COT validation can proceed.

COT rows must match the mapped market name and CFTC code. `market_id` alone is not sufficient. Proxy relations remain visible in validation outputs.
