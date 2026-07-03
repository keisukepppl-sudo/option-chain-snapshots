# Morita Volatility-Regime Quick Screen v1

This module is a descriptive triage study for Morita Bot outcomes versus:

- NASDAQ-specific implied volatility through `^VXN`.
- Semiconductor-core equal-weight realized volatility.
- AI-infrastructure equal-weight realized volatility.
- Each theme realized-volatility ratio to QQQ realized volatility.

It does not rebuild the Morita baseline, rerun the scanner, change Bot rules,
run option-chain or skew analysis, optimize parameters, create a composite
score, or produce a live trading filter.

## Data Boundary

The only authorized new external input is Yahoo Finance daily `^VXN` history
from `2023-06-01` through `2026-07-02`, interval `1d`, raw unadjusted settings.
Theme and QQQ realized volatility are computed only from the local OHLCV input
referenced by the verified Morita baseline `source_input_lineage.json`.

If VXN intake fails or is inadequate, the builder can still run theme-volatility
analysis and labels VXN as unavailable.

## Outcome Boundary

Binary rates use only baseline rows where `outcome_status == complete`.
Same-session collisions and incomplete horizons remain in diagnostics and are
not treated as target, stop, or timeout.

The verified baseline does not expose MAE for this study. Output receipts use
`mae_status=unavailable_from_baseline`.

## Interpretation

Labels are triage labels only:

- `potentially_material_relationship`
- `inconsistent_relationship`
- `no_visible_relationship`
- `insufficient_sample`

They are not forecasts, p-values, filters, alerts, sizing rules, stop rules,
or recommendations.
