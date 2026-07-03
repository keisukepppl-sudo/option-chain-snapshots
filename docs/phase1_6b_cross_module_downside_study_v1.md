# Phase 1.6B Cross-Module Downside Study

This read-only layer performs an NDX historical ex-post cross-module downside-conditioned descriptive study across:

- CTA transparent trend states.
- Vol-control transparent exposure changes.
- TQQQ/SQQQ leveraged ETF capital-scale proxy.

The study reads only manifest-verified source artifacts and writes only to `outputs/phase1_6b_cross_module_downside/`.

## Interpretation Boundary

This is not a composite score, ranking, model selection, forecast, causal estimate, market-impact estimate, actionization gate, notification, sizing rule, execution rule, or trading system.

The output preserves:

- `research_only=true`
- `actionization_allowed=false`
- `not_a_trading_signal=true`
- `predictive_pit_eligible=false`
- `phase2_eligible=false`
- `cross_module_composite_score_created=false`
- `cross_module_actionization_created=false`

## Time Alignment

CTA and Vol-control observations are computed through observation date `t` and aligned to the next eligible session `t+1`.

The leveraged ETF realized same-day notional proxy includes same-day NDX return by construction. For cross-module descriptive categories the study uses only lagged capital sensitivity:

```text
combined_mechanical_sensitivity =
  6 * tqqq_lagged_capital_usd + 12 * sqqq_lagged_capital_usd
```

The realized same-day proxy identity is audited separately:

```text
combined_rebalance_notional_proxy =
  combined_mechanical_sensitivity * same_day_ndx_return
```

## Fixed Windows And Gates

The committed spec defines seven fixed windows and fixed gates:

- minimum pair count for correlations: `60`
- minimum condition count: `20`
- minimum joint cell count: `20`
- minimum next-session source alignment ratio: `0.90`
- ETF sensitivity Q4 threshold: full-sample ex-post `0.75` quantile

No model-specific threshold optimization is performed.

## Outputs

The output directory contains:

- source artifact integrity audit
- source alignment audit
- local daily panel without raw price fields
- fixed outcome definitions
- model-by-model association summary
- conditioned downside summary
- three-layer joint condition summary
- ETF mechanical identity audit
- window coverage
- receipt, limitations, summary, and content manifest

The verifier checks the output content manifest and rejects missing, changed, or extra files.

## Limitations

Results are in-sample, ex-post historical associations. Forward five-session outcomes overlap. Source vintages do not create strict PIT eligibility. The sample is NDX-only. No causal, predictive, actual flow, or market-impact claim is made.
