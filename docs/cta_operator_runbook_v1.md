# CTA Operator Runbook v1

Phase 1.5A has no real data acquisition. All committed fixtures must be synthetic.

## Build Template

```powershell
python market_bomb_cta_research_v1.py build-cta-template --input-id <input_id>
```

Populate manually:

- `sources/daily_market_prices.csv`
- `sources/market_mapping.csv`
- `sources/decision_schedule.csv`
- `source_manifest.json`

`sources/cot_weekly.csv` is optional for the base CTA run and required only for COT external validation.

## Inspect And Validate

```powershell
python market_bomb_cta_research_v1.py inspect-cta-input-contract --input-id <input_id>
python market_bomb_cta_research_v1.py validate-cta-input --input-id <input_id>
```

Validation checks hashes, strict-readiness claims, duplicate price keys, raw/adjusted basis mixing, mapping relation labels, schedule timing, and tracked ignored-history files.

## Run One Fixed CTA Spec

```powershell
python market_bomb_cta_research_v1.py run-cta-historical-descriptive --input-id <input_id> --market-id <market_id> --model-spec-id cta_ts_60d_binary_v1
```

Run exactly one predeclared spec at a time. Do not tune, rank, or promote.

## Verify Exact Artifact

```powershell
python market_bomb_cta_research_v1.py verify-cta-run --run-artifact <exact_run_artifact_path>
```

No latest-run shortcut is supported.

## COT Validation

```powershell
python market_bomb_cta_research_v1.py build-cta-cot-validation-template --input-id <input_id>
python market_bomb_cta_research_v1.py inspect-cta-cot-validation-input --input-id <input_id>
python market_bomb_cta_research_v1.py run-cta-cot-weekly-external-validation --cta-run-artifact <exact_cta_run_artifact_path> --input-id <input_id> --market-id <market_id> --cot-reporting-group <exact_reporting_group>
python market_bomb_cta_research_v1.py verify-cta-cot-validation --validation-artifact <exact_validation_artifact_path>
```

COT validation is ex post external validation only. It is not ground truth and cannot alter the CTA model path.

Before running validation, inspect mapping eligibility. Placeholder COT market names or CFTC codes block validation. The CTA artifact must have been created after the confirmed mapping was staged, because the current mapping identity must match the artifact mapping snapshot.

Do not use a legacy baseline artifact for COT validation. Legacy baselines can remain valid CTA trend artifacts, but COT validation requires a fresh CTA run with confirmed mapping metadata.

For a newly staged COT source, first run the read-only intake gate:

```powershell
python market_bomb_cta_research_v1.py validate-cta-cot-intake --input-id <input_id> --market-id <market_id> --cot-reporting-group <group>
```

Only `cot_intake_validation_status=valid` means the input is ready for a later CTA rerun. This is not permission to run COT validation, tune a model, issue a signal, or claim actual CTA positioning.
