# Flow Pressure Phase 1.3B.1 Intake Report

## Final outcome

- Historical descriptive outcome: `historical_descriptive_input_incomplete`
- Forward snapshot outcome: `forward_snapshot_not_started`
- Actionization: `false`
- Trading signal: `false`
- Repo HEAD checked: `d0de6283d7be7f0a7d85a71a867ed54b3519389d`

## What was checked

The local ignored free-proxy intake area was checked:

`market_bomb_history/leveraged_etf_free_proxy_v1/input/`

No populated manual input package existed before this run. A header-only template was created at:

`market_bomb_history/leveraged_etf_free_proxy_v1/input/manual_free_proxy_intake_20260701_template/`

This template is intentionally ignored by git and contains no market data rows.

## Template files created

| File | Rows | Status |
|---|---:|---|
| `source_manifest.json` | n/a | template only |
| `sources/benchmark_prices.csv` | 0 | template only |
| `sources/benchmark_mapping.csv` | 0 | template only |
| `sources/aum_or_capital.csv` | 0 | template only |
| `sources/split_history.csv` | 0 | template only |
| `sources/leveraged_etf_prices.csv` | 0 | template only |

## Missing files for the instruction package

The instruction package expects these manually supplied files before a real first run:

| Required file | Status |
|---|---|
| `source_manifest.json` | template only, no real sources |
| `sources/ndx_daily.csv` | missing |
| `sources/qqq_daily.csv` | missing |
| `sources/tqqq_daily.csv` | missing |
| `sources/sqqq_daily.csv` | missing |
| `sources/tqqq_aum_nav.csv` | missing |
| `sources/sqqq_aum_nav.csv` | missing |
| `sources/tqqq_splits.csv` | missing |
| `sources/sqqq_splits.csv` | missing |
| `sources/benchmark_mapping.csv` | template only, 0 rows |

Minimum files for NDX exact direction output are still incomplete:

| Minimum file | Status |
|---|---|
| `source_manifest.json` | template only |
| `sources/ndx_daily.csv` | missing |
| `sources/tqqq_daily.csv` | missing |
| `sources/sqqq_daily.csv` | missing |
| `sources/benchmark_mapping.csv` | template only, 0 rows |

## Implemented module contract

The current implementation uses this normalized input contract:

| Implemented file | Required content |
|---|---|
| `source_manifest.json` | provenance for every source file |
| `sources/benchmark_prices.csv` | NDX and/or QQQ daily prices |
| `sources/benchmark_mapping.csv` | TQQQ/SQQQ to benchmark mapping |
| `sources/aum_or_capital.csv` | TQQQ/SQQQ AUM or capital proxy |
| `sources/split_history.csv` | TQQQ/SQQQ split history |
| `sources/leveraged_etf_prices.csv` | TQQQ/SQQQ daily prices |

The template has the correct headers for this implemented contract, but all CSV files have `0` data rows. Therefore it is not eligible for validation, historical run, verification, or forward snapshot ingestion.

## Commands run

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-template --input-id manual_free_proxy_intake_20260701_template
```

## Commands intentionally not run

- `validate-leveraged-etf-free-proxy-input`
- `run-leveraged-etf-free-proxy-historical`
- `verify-leveraged-etf-free-proxy-run`
- `ingest-leveraged-etf-free-proxy-forward-snapshot`

Reason: there is no manually supplied real provider/source data. Running the historical analysis on header-only templates would create misleading output.

## Validation

Code was not changed. The focused free proxy test suite passed:

```text
34 passed
```

## Required next action

Populate a new opaque input folder under:

`market_bomb_history/leveraged_etf_free_proxy_v1/input/<opaque_input_id>/`

Then provide either the instruction-shaped files or the implemented normalized files, with a real `source_manifest.json` that documents source authority, publication/revision state, raw vs adjusted treatment, corporate action treatment, and file hashes.

After that, the correct sequence is:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id <opaque_input_id>
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <opaque_input_id> --benchmark-mode ndx_exact
python market_bomb_leveraged_etf_free_proxy_v1.py verify-leveraged-etf-free-proxy-run --run-artifact <exact_run_artifact_path>
```
