# Morita Regime Sizing Overlay v1

`morita_regime_sizing_overlay_v1` is a notification and logging overlay for existing Morita Bot S signals.

It does not change signal eligibility. It does not change RS, score, rank, breakout logic, volume logic, cooldown, theme logic, entry timing, exit logic, TP logic, or universe membership.

## Inputs

The overlay reuses the existing realized-dispersion and narrow-leadership artifacts:

- `outputs/morita_realized_dispersion_quick_screen/`
- `outputs/morita_narrow_leadership_confirmation/`
- `outputs/morita_narrow_leadership_2023_frozen_replication_v2/`

The inherited high thresholds are loaded from `outputs/morita_realized_dispersion_quick_screen/realized_dispersion_state_cutoffs.csv`:

- `broad_russell1000_cross_sectional_dispersion_20d >= 0.1076297441118458`
- `broad_russell1000_qqq_minus_eqw_return_20d >= 0.0211600633543862`

These values are verified against the source artifact. They are not recalibrated by the overlay.

## Regime Classification

| Regime | Definition |
| --- | --- |
| `NORMAL` | D is not high, regardless of L, or L-high only |
| `HIGH_DISPERSION` | D high and L not high |
| `NARROW_LEADERSHIP` | D high and L high |
| `REGIME_UNAVAILABLE_CONSERVATIVE` | D/L state, source lineage, or timing validation is unavailable |

The join is exact:

```text
regime_observation_date == signal_decision_date
```

Missing state fails closed to `REGIME_UNAVAILABLE_CONSERVATIVE`.

## Sizing Policy

| Regime | Suggested max/base premium | Rolling 10-session new-S cap | 50% exception |
| --- | ---: | ---: | --- |
| `NORMAL` | 30% base | none | existing-rule-dependent |
| `HIGH_DISPERSION` | 20% max | 40% | disabled |
| `NARROW_LEADERSHIP` | 15% max | 30% | disabled |
| `REGIME_UNAVAILABLE_CONSERVATIVE` | 20% max | 40% | disabled |

The rolling sleeve cap uses the current decision session plus the preceding nine trading decision sessions.

If confirmed execution data are unavailable, prior emitted overlay recommendations are used only as advisory bookkeeping and are labeled `RECOMMENDATION_ONLY`.

## Outputs

Runtime outputs are written under `outputs/morita_regime_sizing_overlay_v1/`:

- `regime_overlay_daily_state.csv`
- `regime_overlay_signal_decisions.csv`
- `regime_overlay_rolling_sleeve_ledger.csv`
- `regime_overlay_forward_review.csv`
- `regime_overlay_receipt.json`
- `regime_overlay_content_manifest.json`
- `regime_overlay_summary.md`

No broker credentials, account IDs, cash balances, buying power, order IDs, or personal account data are written.
