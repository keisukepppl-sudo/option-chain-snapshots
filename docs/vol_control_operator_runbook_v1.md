# Vol-Control Operator Runbook v1

This runbook is for local research-only operation. Do not use this module for alerts, trading, backtests, releases, ranking, sizing, or any production decision.

## Build Empty Input Template

```powershell
python market_bomb_vol_control_research_v1.py build-vol-control-template --input-id <input_id>
```

This creates the canonical input folder and empty CSV templates.

## Inspect Input Contract

```powershell
python market_bomb_vol_control_research_v1.py inspect-vol-control-input-contract --input-id <input_id>
```

Inspection does not create a run artifact. It reports file presence, headers, manifest entries, hash status, and validation diagnostics.

## Validate Input

```powershell
python market_bomb_vol_control_research_v1.py validate-vol-control-input --input-id <input_id>
```

Validation blocks on:

- Missing required datasets
- Header mismatch
- Content hash mismatch
- Duplicate benchmark keys
- Mixed raw/adjusted basis for one instrument
- Missing explicit decision schedule
- Same-day or prior-day effective session
- Strict or PIT eligibility claims
- Tracked raw files under `market_bomb_history/vol_control_research_v1`

## Run Historical Descriptive Replication

```powershell
python market_bomb_vol_control_research_v1.py run-vol-control-historical-descriptive --input-id <input_id> --benchmark-mode ndx_exact_descriptive --model-spec-id vc_daily_20d_target10_cap100_v1
```

Allowed benchmark modes:

- `ndx_exact_descriptive`
- `qqq_proxy_only_descriptive`

Allowed model specs are listed in `config/vol_control_research_v1/model_specs.json`.

## Verify Run Artifact

```powershell
python market_bomb_vol_control_research_v1.py verify-vol-control-run --run-artifact <run_artifact_path>
```

Verification checks the content manifest and confirms actionization, Phase 2, release, and backtest flags remain false.

## Hard Boundaries

- Do not infer missing prices.
- Do not forward-fill benchmark prices.
- Do not combine this output with leveraged ETF flow outputs.
- Do not treat the output as actual vol-control manager exposure.
- Do not create releases or notifications from this module.

## Cross-Spec Characterization

For six-spec NDX characterization, run fresh artifacts for the six predeclared specs, verify each artifact, then run `run-vol-control-cross-spec-characterization`. The characterization summary must remain descriptive and must not contain raw daily prices, returns, PnL, Sharpe, alpha, ranking, selection, or trading guidance.
