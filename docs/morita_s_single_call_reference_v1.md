# Morita S Single-Call Reference v1

This module builds a synthetic fixed-IV Black-Scholes daily-bar reference model for the formal Morita S cohort.

It is explicitly:

- `synthetic_fixed_iv_reference_model=true`
- `not_historical_option_fill_reconstruction=true`
- `not_live_execution_estimate=true`

The model uses the formal baseline entry price, local OHLCV lineage from `source_input_lineage.json`, a continuous theoretical delta-0.60 strike, 60 calendar DTE, IV 60%, entry markup 5%, and exit haircut 5%.

Breakout-day low is diagnostic only. There is no hard stop. The independent terminal is the formal Day10 +5% gate, then max 30 eligible sessions or option expiry / missing path data.

