# CTA Transparent Trend Replication v1

This module is a standalone, research-only transparent CTA trend-model harness. It generates a normalized single-market trend-state path from fixed, predeclared rules.

It is not actual CTA positioning, not CTA AUM, not CTA dollar flow, not market impact, not a prediction ledger, and not a trading signal.

## Fixed Model Family

The registry is `config/cta_research_v1/model_specs.json`.

Initial specs:

- `cta_ts_20d_binary_v1`
- `cta_ts_60d_binary_v1`
- `cta_ts_120d_binary_v1`
- `cta_ts_20_60_120_equal_weight_v1`

All specs are daily close-to-close time-series momentum models with:

- exposure floor `-1.0`
- exposure cap `1.0`
- neutral band `0.0`
- daily EOD rebalance convention
- next eligible session effect
- `parameter_selection_status=predeclared_not_fitted`

## Single-Horizon Formula

For horizon `h`:

```text
trend_return_t(h) = close_t / close_(t-h) - 1
```

Exposure:

```text
+1.0 if trend_return_t(h) > 0
-1.0 if trend_return_t(h) < 0
 0.0 if trend_return_t(h) = 0
 unavailable if h prior observations do not exist
```

## Composite Formula

For horizons 20, 60, and 120:

```text
composite_score_t = (sign_20 + sign_60 + sign_120) / 3
```

Exposure is the sign of the fixed equal-weight composite score. Weights are not optimized.

## Timing

For observation date `t`, only closes through `t` can enter the decision. The target exposure at `t` is effective for the next eligible session. `feature_cutoff_date` must equal `observation_date`.

The module does not claim same-close execution and does not infer manager execution.

## Price-To-COT Relationship

Every market mapping must explicitly state one of:

- `direct_futures_match`
- `cash_index_proxy_for_futures_cot`
- `etf_proxy_for_futures_cot`

Proxy labels remain visible in outputs. A proxy price is never represented as a direct futures price.

## COT Eligibility Boundary

CTA baseline generation and COT-validation eligibility are separate. A market can produce valid no-COT CTA trend-state baselines while its COT mapping remains unresolved.

Unresolved or placeholder COT identifiers make `cot_validation_eligible=false`. They do not invalidate the CTA trend artifact, but they prevent COT validation. Once a confirmed mapping is manually staged, new CTA artifacts must be created so the mapping identity is bound into the artifact snapshot.
