# Morita Portfolio Survival Ledger v1

This ledger measures portfolio survival conditions for the manual Morita momentum-call process.

It is advisory-only. It does not approve, block, size, submit, cancel, amend, or close any order.

## Scope

The survival ledger consumes canonical account snapshots, position snapshots, monitoring lots, and local Morita signal/intent links. Unknown values remain unavailable and are never zero-filled or inferred.

## S/A/B Reference

The current reference values are `S=40`, `A=15`, and `B=10`. The denominator is intentionally unset:

```text
rank_reference_unit=UNSET_REQUIRED
```

Until explicitly configured by the user, rank allocation output remains `unconfigured_reference_unit`.

## Outputs

The ledger reports premium-at-risk, concentration, high-water-mark drawdown, open position counts, rank/theme/underlying distributions, data completeness, and advisory alert codes.

Allowed advisory labels are descriptive only, such as `survival_data_incomplete`, `concentration_watch`, `drawdown_watch`, and `drawdown_critical`.

No trading instruction is generated.
