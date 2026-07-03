# Leveraged ETF Scale Proxy v1

This module builds a standalone historical descriptive capital-scaled mechanical rebalance proxy for TQQQ and SQQQ.

It is separate from `leveraged_etf_free_directional_proxy_v1`. The legacy free proxy remains a direction-only baseline and is not upgraded by this module.

## Instruments And Mapping

- TQQQ maps to NDX with target leverage `+3.0`.
- SQQQ maps to NDX with target leverage `-3.0`.
- QQQ proxy mode is not allowed in this phase.

## Formula

The fixed static daily-reset approximation is:

`mechanical_rebalance_notional_proxy = L * (L - 1) * prior_session_capital * benchmark_return`

The prior capital date must equal the exact prior observed NDX session. Same-day, latest-prior carry, interpolation, future values, and zero substitution are not allowed.

## Capital Stock Versus Real Flow

The proxy uses capital stock as scale context. It is not actual ETF creation/redemption flow, shareholder flow, authorized participant flow, manager trade blotter, derivatives notional, dealer hedge, market impact, forecast, or a trading signal.

## Source Quality

Only official issuer or regulator sources are allowed for qualification. Daily capital input requires direct daily issuer evidence with reported AUM, or shares outstanding plus NAV under a stable as-of convention.

SEC periodic records can provide identity or anchor evidence only. Monthly, quarterly, or annual records are not converted into daily capital observations.

## Validation Gates

- NDX exact mapping only.
- TQQQ and SQQQ daily capital must both be present.
- Reported AUM plus shares times NAV must reconcile within 0.5% when both are present.
- Exact lagged-capital coverage must be at least 90% for TQQQ, SQQQ, and combined overlap.
- shares times NAV as the capital path requires documented split history.
- Reported AUM is selected when reported AUM and shares times NAV both reconcile.

## Safety Flags

Every run remains:

- `research_only=true`
- `actionization_allowed=false`
- `not_a_trading_signal=true`
- `predictive_pit_eligible=false`
- `phase2_eligible=false`
- `release_created=false`
- `backtest_run=false`

No output unlocks strict PIT, Phase 1.3 readiness, Phase 2, release promotion, notifications, sizing, execution, model ranking, or cross-module integration.
