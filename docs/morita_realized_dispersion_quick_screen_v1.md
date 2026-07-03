# Morita Realized Dispersion Quick Screen v1

This module is a descriptive quick screen for Morita Bot outcomes versus local
realized cross-sectional dispersion, participation, equal-weight volatility,
average-correlation proxy, and QQQ-minus-equal-weight divergence.

It uses only the verified Morita baseline and the local OHLCV input referenced
by that baseline's `source_input_lineage.json`. It does not download data,
use option/implied-correlation data, rebuild the Bot baseline, fit models,
optimize thresholds, or create a live rule.

## Baskets

- `broad_russell1000_local_proxy`: locally available OHLCV tickers, excluding
  benchmark-like symbols such as QQQ.
- `semiconductor_core`: reused from the existing static breadth basket.
- `ai_infrastructure_extended`: reused from the existing static breadth basket.

These are static research proxies, not point-in-time constituent claims.

## Metrics

All metrics are calculated using trailing 20-session close-to-close returns
ending at the signal decision date:

- Cross-sectional dispersion of 20-session total returns.
- Percent of valid members with positive 20-session return.
- Equal-weight realized volatility.
- Transparent realized average-correlation proxy.
- QQQ minus basket equal-weight 20-session return.

## Interpretation

Labels are descriptive triage labels only. They are not p-values, forecasts,
filters, alerts, sizing rules, exit rules, or trading recommendations.
