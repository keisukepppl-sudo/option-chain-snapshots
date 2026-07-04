# Morita S TP100 vs TP125 Comparison v1

This module is a fixed descriptive comparison shell for S-rank single-call exits:

- TP100: full exit at the first modeled net option return >= +100%.
- TP125: full exit at the first modeled net option return >= +125%.
- STAGED_100_125: 50% exit at +100%, remaining 50% at +125% or the independent terminal.

The module intentionally fails closed unless a committed canonical single-call daily valuation path engine can be replayed on the formal Morita S baseline:

`market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa`

The current formal baseline is verified for signal identity and underlying outcome lineage, but it does not include daily modeled single-call net-return paths. Legacy call backtest CSVs were detected in an accessible older workspace, but they are a limited older research sample and are not compatible with the formal S baseline.

Therefore the correct current status is:

`canonical_single_call_model_not_reproducible_on_formal_S_baseline`

This is not a TP100 or TP125 performance conclusion.

