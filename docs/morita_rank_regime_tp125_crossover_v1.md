# Morita Rank x Regime TP125 Crossover v1

This document defines the fixed research comparison for whether A-rank signals in NORMAL regime can be more attractive than S-rank signals in NARROW_LEADERSHIP regime under the same TP125 single-call reference contract.

## Fixed Inputs

- D metric: `broad_russell1000_cross_sectional_dispersion_20d`
- L metric: `broad_russell1000_qqq_minus_eqw_return_20d`
- D high cutoff: `0.1076297441118458`
- L high cutoff: `0.0211600633543862`
- NORMAL: D not high, regardless L.
- HIGH_DISPERSION: D high and L not high.
- NARROW_LEADERSHIP: D high and L high.

## Contract

- 60DTE call, target delta 0.6, fixed IV 60%.
- Entry markup 5%, exit haircut 5%.
- TP125 is an executable model-path high touch, capped to +125%.

## Interpretation

This is not a parameter search. It is a fixed crossover screen. Any live rule change requires a separate forward-tracking and production implementation task.
