# Morita Theme Breadth Quick Screen v1

This module is a one-pass descriptive research screen. It asks whether static
semiconductor and AI-infrastructure breadth states have a large, directionally
consistent relationship with existing Morita Bot underlying outcomes.

The module does not rebuild the Morita baseline, rerun the scanner, fetch data,
run option PnL, fit a model, optimize thresholds, change ranks, or create a
live filter. Basket membership is a static research proxy and is not a
point-in-time sector-membership claim.

## Inputs

- Verified Morita Bot formal historical baseline run directory.
- `source_input_lineage.json` inside that run directory.
- Local OHLCV input referenced by `source_input_lineage.json`.
- Static baskets in `config/morita_theme_breadth_v1/static_research_baskets_v1.json`.

The script intentionally has no CLI option for an arbitrary OHLCV path. OHLCV
must be discovered through the verified baseline lineage.

## Outputs

The run writes to `outputs/morita_theme_breadth_quick_screen/`:

- `breadth_daily_panel.csv`
- `breadth_signal_context_panel.csv`
- `breadth_state_cutoffs.csv`
- `breadth_outcome_summary.csv`
- `breadth_rank_summary.csv`
- `breadth_scope_coverage.csv`
- `breadth_concentration_diagnostics.csv`
- `breadth_receipt.json`
- `breadth_content_manifest.json`
- `breadth_summary.md`

It also writes a Git-safe ChatGPT handoff bundle:
`morita_theme_breadth_quick_screen_chatgpt_bundle.md`.

## Outcome Handling

Binary rates use only rows where `outcome_status == complete`. Same-session
barrier collisions and incomplete horizons remain in coverage diagnostics but
are not counted as success, breach, or timeout.

If the verified baseline does not contain
`maximum_adverse_excursion_10_sessions`, the output still includes
`median_mae_10_sessions` as an empty field and records
`mae_unavailable_from_baseline` in the receipt and rank summary. No MAE value is
inferred.

## Interpretation

Labels are triage labels only:

- `potentially_material_relationship`
- `inconsistent_relationship`
- `no_visible_relationship`
- `insufficient_sample`

They are not p-values, forecasts, filters, alerts, sizing rules, exit rules, or
trading recommendations.
