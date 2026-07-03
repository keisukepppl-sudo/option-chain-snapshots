# Phase 1.5F CTA And Vol-Control Interpretation Atlas v1

This package builds a local historical descriptive atlas from existing verified CTA and Vol-control artifacts.

## Scope

The generator reads only already-created artifacts supplied on the command line. It verifies each content manifest and receipt before reading output CSVs.

The fixed spec is:

`config/research_review_v1/phase1_5f_cta_vol_interpretation_spec.json`

The script is:

`scripts/build_phase1_5f_cta_vol_interpretation.py`

## Outputs

CTA outputs:

- `cta_artifact_integrity.csv`
- `cta_cot_metric_atlas.csv`
- `cta_state_transition_atlas.csv`
- `cta_pairwise_state_agreement.csv`
- `cta_multi_spec_disagreement_episodes.csv`
- `cta_top_state_divergence_observations.csv`

Vol-control outputs:

- `vol_control_artifact_integrity.csv`
- `vol_control_spec_characteristic_atlas.csv`
- `vol_control_pairwise_dispersion_atlas.csv`
- `vol_control_daily_cross_spec_spread.csv`
- `vol_control_top_cross_spec_dispersion_observations.csv`
- `vol_control_cross_spec_spread_distribution.csv`

The generated Markdown report keeps CTA and Vol-control in independent sections.

## Guardrails

The atlas preserves:

- `research_only=true`
- `actionization_allowed=false`
- `not_a_trading_signal=true`
- `predictive_pit_eligible=false`
- `phase2_eligible=false`
- `cross_module_metrics_computed=false`
- `cross_module_integration_performed=false`

The generator does not compute returns, PnL, future outcomes, CTA plus Vol-control joint metrics, model ranking, model selection, acceptance thresholds, releases, notifications, or execution instructions.

## Limitations

Leveraged Funds is broad, not CTA-only. NDX is a cash-index proxy for Nasdaq-100 consolidated futures COT. Availability alignment uses reconstructed availability and is not strict point-in-time.

Vol-control models are transparent rules, not observed manager positions.

The output is a state-path and dispersion description only.
