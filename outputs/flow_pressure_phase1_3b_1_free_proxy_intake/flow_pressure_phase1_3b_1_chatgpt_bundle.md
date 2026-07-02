# ChatGPT Bundle: Flow Pressure Phase 1.3B.1 Free Proxy Intake and First Run

## Objective

Continue Phase 1.3B by performing a one-time manual free-data intake check, running the first historical descriptive leveraged ETF proxy analysis only if complete manually supplied real data exists, and starting forward snapshot capture only if a genuine current snapshot exists.

## Guardrails

- Do not fetch, download, scrape, synthesize, or infer data.
- Do not commit raw CSV/source documents.
- Do not change formulas, NDX/QQQ semantics, strict gates, or research-only controls.
- Do not run strict Phase 1.3 readiness, Phase 2, flow release/backtest, notifications, trading, sizing, ranking, CTA, or dealer logic.
- Keep `actionization_allowed=false`.

## Current Result

- Historical descriptive outcome: `historical_descriptive_input_incomplete`
- Forward snapshot outcome: `forward_snapshot_not_started`
- Trading signal: `false`
- Actionization: `false`
- Repo HEAD checked: `d0de6283d7be7f0a7d85a71a867ed54b3519389d`

## What Was Found

The local ignored intake root did not exist before this pass:

`market_bomb_history/leveraged_etf_free_proxy_v1/input/`

A header-only template was created:

`market_bomb_history/leveraged_etf_free_proxy_v1/input/manual_free_proxy_intake_20260701_template/`

The template is ignored by git and must not be interpreted as real market data.

## Template Contents

| File | Rows | Status |
|---|---:|---|
| `source_manifest.json` | n/a | template only |
| `sources/benchmark_prices.csv` | 0 | template only |
| `sources/benchmark_mapping.csv` | 0 | template only |
| `sources/aum_or_capital.csv` | 0 | template only |
| `sources/split_history.csv` | 0 | template only |
| `sources/leveraged_etf_prices.csv` | 0 | template only |

## Deprecated Planning-Name Inputs

Phase 1.3B.1 reported these older instruction-level names. They are now explicitly deprecated planning names, not active input filenames:

| File | Status |
|---|---|
| `source_manifest.json` | template only, sources empty |
| `sources/ndx_daily.csv` | missing |
| `sources/qqq_daily.csv` | missing |
| `sources/tqqq_daily.csv` | missing |
| `sources/sqqq_daily.csv` | missing |
| `sources/tqqq_aum_nav.csv` | missing |
| `sources/sqqq_aum_nav.csv` | missing |
| `sources/tqqq_splits.csv` | missing |
| `sources/sqqq_splits.csv` | missing |
| `sources/benchmark_mapping.csv` | template only, 0 rows |

The old minimum NDX exact planning names are also deprecated. The active contract uses `benchmark_prices.csv` and `benchmark_mapping.csv`.

## Implemented Normalized Contract

The current implementation expects these normalized files:

| File | Required role |
|---|---|
| `source_manifest.json` | provenance and integrity metadata |
| `sources/benchmark_prices.csv` | NDX and/or QQQ prices |
| `sources/benchmark_mapping.csv` | TQQQ/SQQQ benchmark mapping |
| `sources/aum_or_capital.csv` | AUM/capital proxy |
| `sources/split_history.csv` | split history |
| `sources/leveraged_etf_prices.csv` | TQQQ/SQQQ prices |

The generated template has these headers but no rows.

## Commands Run

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-template --input-id manual_free_proxy_intake_20260701_template
python -m pytest tests/test_market_bomb_leveraged_etf_free_proxy_v1.py -q --durations=30 --basetemp C:\t\lfp13b1 -o cache_dir=C:\t\c\lfp13b1
```

## Commands Not Run

- `validate-leveraged-etf-free-proxy-input`
- `run-leveraged-etf-free-proxy-historical`
- `verify-leveraged-etf-free-proxy-run`
- `ingest-leveraged-etf-free-proxy-forward-snapshot`

Reason: no complete manually supplied real input package exists. Running on a header-only template would produce invalid or misleading research output.

## Validation

Focused free proxy tests passed:

```text
34 passed
```

## Output Files Created

- `outputs/flow_pressure_phase1_3b_1_free_proxy_intake/free_proxy_input_inventory.csv`
- `outputs/flow_pressure_phase1_3b_1_free_proxy_intake/phase1_3b_1_content_manifest.json`
- `outputs/flow_pressure_phase1_3b_1_free_proxy_intake/flow_pressure_phase1_3b_1_intake_report.md`
- `outputs/flow_pressure_phase1_3b_1_free_proxy_intake/flow_pressure_phase1_3b_1_chatgpt_bundle.md`

## Next Instruction for Codex

Populate a new manual input folder with real free provider files under:

`market_bomb_history/leveraged_etf_free_proxy_v1/input/<opaque_input_id>/`

Then rerun:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id <opaque_input_id>
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <opaque_input_id> --benchmark-mode ndx_exact
python market_bomb_leveraged_etf_free_proxy_v1.py verify-leveraged-etf-free-proxy-run --run-artifact <exact_run_artifact_path>
```

If NDX exact data is unavailable but QQQ is valid and explicitly accepted, use:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <opaque_input_id> --benchmark-mode qqq_proxy_only_descriptive
```

Do not proceed to actionization, trading, alerts, sizing, ranking, CTA, or dealer integration from this phase.
