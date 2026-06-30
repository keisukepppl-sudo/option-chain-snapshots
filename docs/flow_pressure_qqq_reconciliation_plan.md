# Flow Pressure QQQ Reconciliation Plan

## Price Reconciliation

Compare primary and secondary sources for:

```text
NDX
QQQ
TQQQ
SQQQ
```

Check:

- session date,
- raw OHLC,
- volume,
- split date,
- return continuity before and after splits,
- raw/adjusted basis,
- close definition and venue.

Differences must be classified as:

1. raw/adjusted mismatch,
2. split treatment,
3. source correction or revision,
4. unit/venue/close-definition difference,
5. unresolved material discrepancy.

Do not average, overwrite, or silently choose the favorable source.

## AUM / NAV / Shares Reconciliation

Primary authority is ProShares where available. Compare:

```text
official AUM
official shares * official NAV
secondary vendor AUM
secondary vendor shares
secondary vendor NAV
```

Output:

```text
aum_relative_difference
share_relative_difference
nav_relative_difference
unit_conversion_applied
reconciliation_status
discrepancy_explanation
```

Secondary vendor values are diagnostic only. They must not overwrite ProShares values.

## Blocking Rule

Any unresolved material discrepancy blocks predictive qualification. The correct status is `blocked_by_data_quality` or `historical_descriptive_only`, not a forced readiness pass.
