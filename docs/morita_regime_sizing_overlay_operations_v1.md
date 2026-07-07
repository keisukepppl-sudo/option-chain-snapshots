# Morita Regime Sizing Overlay Operations v1

## Operational Role

This overlay is a risk-budget display layer for S notifications. It is not an order system.

Allowed behavior:

- add regime state to S notifications;
- add suggested maximum premium allocation to S notifications;
- log S overlay decisions;
- produce forward-review summaries.

Disallowed behavior:

- suppress S signals;
- change S/A/B rank;
- fetch broker account data;
- calculate buying power;
- place or preview orders;
- auto-adjust policy values from forward-review results.

## Notification Behavior

Only S notifications receive the overlay block.

A/B notifications remain watchlist notifications. Their eligibility and text are not changed by this overlay except for the existing surrounding scanner behavior.

## Data Fallback

If the exact decision-date D/L state is missing, stale, future-dated, or not verifiable, the overlay fails closed:

```text
REGIME_UNAVAILABLE_CONSERVATIVE
suggested max premium = 20%
rolling 10-session new-S cap = 40%
50% exception = disabled
```

The S signal is still emitted.

## Rolling Sleeve Cap

The rolling sleeve cap measures newly opened or recommended S risk inside the current decision session plus the preceding nine trading decision sessions.

When an actual execution ledger is supplied and contains confirmed S fills, confirmed initial premium allocation is used.

When no such ledger exists, the overlay uses prior emitted recommendations only and labels the result:

```text
rolling_budget_source=RECOMMENDATION_ONLY
```

This is advisory bookkeeping, not realized exposure.

## Forward Review

The forward review report is generated on demand by:

```powershell
python scripts/build_morita_regime_sizing_overlay_forward_review_v1.py
```

The review creates `regime_overlay_forward_review.csv` and does not change policy values.

Manual review milestones:

- 25 complete `NARROW_LEADERSHIP` S outcomes
- 50 complete `HIGH_DISPERSION` S outcomes

At milestones, review the report manually. Do not let the code auto-change allocation rules.
