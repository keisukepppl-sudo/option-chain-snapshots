# ChatGPT Bundle: Flow Pressure Phase 1.3B.2 Canonical Input Contract

## Objective

Lock the actual implemented manual input contract for the free leveraged ETF directional proxy and remove ambiguity from older one-file-per-ticker planning instructions.

## Result

The executable generated template is now documented as canonical:

```text
start_commit=08e80427cfd4f4f8055f28429a9cdc3eea6c49fe
implementation_commit=0a59cbe49425821fca6a3fafd21ee2f32a3eab27
```

```text
market_bomb_history/
  leveraged_etf_free_proxy_v1/
    input/
      <opaque_input_id>/
        source_manifest.json
        sources/
          benchmark_prices.csv
          benchmark_mapping.csv
          aum_or_capital.csv
          split_history.csv
          leveraged_etf_prices.csv
```

Legacy names such as `ndx_daily.csv`, `tqqq_daily.csv`, and `tqqq_aum_nav.csv` are deprecated planning names and are not active input filenames.

## Code Change

Added a local-only helper:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id <opaque_input_id>
```

It is read-only and creates no run artifact. It reports:

- expected, present, and missing files;
- found headers and missing required headers;
- manifest entries and hash status;
- detected instruments and coverage;
- descriptive-only status;
- capability flags:
  - `ndx_exact_direction_possible`
  - `qqq_proxy_only_direction_possible`
  - `aum_scaled_possible`
  - `split_diagnostics_possible`
  - `forward_snapshot_ingestion_possible`

It always reports:

```text
actionization_allowed=false
predictive_pit_eligible=false
phase2_eligible=false
creates_run_artifact=false
```

## Docs Added

- `docs/leveraged_etf_free_proxy_canonical_input_contract_v1.md`
- `docs/leveraged_etf_free_proxy_manual_data_prep_v1.md`
- `docs/leveraged_etf_free_proxy_contract_migration_v1.md`

## Docs Updated

- `docs/leveraged_etf_free_directional_proxy_v1.md`
- `docs/leveraged_etf_free_proxy_operator_runbook_v1.md`
- `docs/flow_pressure_research_program_v1.md`
- Phase 1.3B.1 outputs were updated to mark old per-ticker names as deprecated planning names.

## Manual Data Prep Checklist

Minimum useful NDX exact direction run:

- populated `source_manifest.json`;
- NDX rows in `sources/benchmark_prices.csv`;
- TQQQ/SQQQ NDX exact rows in `sources/benchmark_mapping.csv`;
- valid hashes;
- `source_qualification_status=historical_descriptive_only`;
- `historical_vintage_available=false`;
- `publication_timestamp_available=false`;
- `revision_history_available=false`.

Recommended:

- TQQQ/SQQQ prices in `sources/leveraged_etf_prices.csv`.

Needed only for scale:

- TQQQ/SQQQ AUM or shares plus NAV in `sources/aum_or_capital.csv`.

Needed for split diagnostics:

- TQQQ/SQQQ split rows in `sources/split_history.csv`.

## Validation

Focused helper/free-proxy tests:

```text
41 passed
```

Full repository tests were run file-by-file because one-shot local `pytest -q` exceeded the 15 minute timeout on existing long Fragility tests:

```text
373 passed, 2 skipped
```

Long files passed when run with longer per-file timeout:

```text
tests/test_market_bomb_fragility_data_release_v0.py: 22 passed, 1 skipped
tests/test_market_bomb_fragility_score_v0.py: 57 passed
```

## Guardrails Confirmed

- No data was fetched, downloaded, scraped, synthesized, or inferred.
- No raw market data was committed.
- No historical proxy analysis was run on empty/template-only data.
- No strict Phase 1.3 readiness, Phase 2, Flow release, statistical backtest, notification, trading, sizing, ranking, or actionization was run.
- Free history remains descriptive-only.
- Strict predictive gates are unchanged.

## Next Step

Populate a real manual input folder with the normalized files, then run:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id <opaque_input_id>
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id <opaque_input_id>
```

Only after validation should a descriptive run be considered.
