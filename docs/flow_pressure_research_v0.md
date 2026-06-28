# Flow Pressure Research v0

`flow_pressure_research_v0` is an isolated research layer for model-implied market flow pressure proxies. It does not change Fragility Score formulas and it does not connect to trading, alerts, or actionization.

## Scope

Implemented in this release:

- Leveraged ETF rebalance pressure: theoretical rebalance pressure from prior available AUM, target leverage, and underlying return.
- Vol-control deleveraging pressure: normalized target-vol exposure change from realized volatility windows.

Explicit placeholders:

- CTA trend flow pressure.
- Dealer hedge / gamma regime.

All outputs are proxy estimates. They are not observed institutional flow, dealer positioning, or real CTA/vol-control order flow. `actionization_allowed=false` is enforced throughout.

## CLI

```powershell
python market_bomb_flow_pressure_research_v0.py verify-flow-staging --staging-id fixture_flow --now-utc 2020-02-20T22:00:00Z
python market_bomb_flow_pressure_research_v0.py build-flow-release --staging-id fixture_flow --now-utc 2020-02-20T22:00:00Z
python market_bomb_flow_pressure_research_v0.py verify-flow-release --release-id <release_id>
python market_bomb_flow_pressure_research_v0.py run-flow-backtest --release-id <release_id>
python market_bomb_flow_pressure_research_v0.py verify-flow-backtest --release-id <release_id> --backtest-run-id <run_id>
python market_bomb_flow_pressure_research_v0.py inspect-flow-release --release-id <release_id>
```

## Safety Model

- Local staging only. No network fetch and no scraping.
- Staging paths reject traversal, absolute paths, Windows drives, UNC paths, duplicate paths, and symlinks.
- Timestamps must be timezone-aware and are normalized to UTC.
- `available_at_timestamp` must not be after the decision time.
- `market_timestamp` and `source_as_of_timestamp` must not be after `available_at_timestamp`.
- Release construction writes into `.building_*`, seals metadata, content manifest, and receipt, then exposes the final release directory.
- `verify-flow-release` validates the immutable core file set, hashes, release metadata, quality gate, required feature fields, and `actionization_allowed=false`.
- `verify-flow-staging` performs a dry preflight in a temporary copied root and does not write persistent releases in the source repo.

## Release Outputs

- `release_core_metadata.json`
- `release_content_manifest.json`
- `release_receipt.json`
- `source_coverage_audit.csv`
- `source_timeliness_audit.csv`
- `feature_quality_gate.csv`
- `module_methodology.json`
- `parameter_registry.json`
- `backtest_spec.json`
- `backtest_results.csv`
- `backtest_summary.md`
- `explicit_limitations.md`
- `canonical_input/flow_pressure_canonical_source_rows.csv`
- `features/flow_pressure_features.csv`

## Onboarding Real Provider Data

Before adding real provider data, each staged source must include source name, file reference, source-as-of timestamp, available-at timestamp, market timestamp, instrument, asset class, dataset version, coverage range, and a local relative path. Missing data should remain missing; do not forward-fill, coalesce sources, or infer availability.
