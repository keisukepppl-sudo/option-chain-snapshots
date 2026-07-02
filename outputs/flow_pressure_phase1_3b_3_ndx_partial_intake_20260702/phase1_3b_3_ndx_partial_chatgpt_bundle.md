# ChatGPT Bundle: Phase 1.3B.3 NDX Partial Intake

## Objective

Use the manually supplied local NDX workbook to begin Phase 1.3B.3 manual source intake, normalize only deterministic fields into the canonical five-file contract, and run the first NDX-exact descriptive proxy only if validation passes.

## Result

Main outcome:

```text
manual_raw_source_inputs_incomplete
```

Forward collection:

```text
forward_snapshot_not_started
```

NDX was normalized successfully, but the run is blocked because TQQQ/SQQQ -> NDX mapping evidence is still missing.

## Raw Source

Supplied file:

```text
C:/Users/keisu/Downloads/EODHist_20230703-20260702_NDX.xlsx
```

SHA-256:

```text
8ea462ee5448d2f1f2cbab7a19dfa8934d41204ca963b0ef9712b50f80fb52e1
```

Archived locally under ignored path:

```text
market_bomb_history/leveraged_etf_free_proxy_v1/manual_source_archive/manual_free_proxy_ndx_20260702/
```

Raw data was not committed.

## Normalization

Input ID:

```text
manual_free_proxy_ndx_20260702
```

Normalization run ID:

```text
norm_20260702T113715Z_c5b6788c
```

Canonical file produced locally:

```text
market_bomb_history/leveraged_etf_free_proxy_v1/input/manual_free_proxy_ndx_20260702/sources/benchmark_prices.csv
```

Transformation:

- `Trade Date` -> `date`
- constant `NDX` -> `instrument`
- `Index Value` -> `raw_close`
- constant `raw` -> `raw_or_adjusted`
- excluded rows with missing, nonnumeric, or nonpositive `Index Value`
- no imputation, forward-fill, backfill, interpolation, or availability timestamp inference

Counts:

```text
original_rows=753
normalized_ndx_rows=752
excluded_rows=1
coverage_start=2023-07-03
coverage_end=2026-07-01
```

The excluded row was the 2026-07-02 row with `Index Value=0.0`.

## Inspection

Command:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id manual_free_proxy_ndx_20260702
```

Key result:

```text
validation_status=blocked
benchmark_prices rows=752
benchmark_mapping rows=0
ndx_exact_direction_possible=false
creates_run_artifact=false
```

## Validation

Command:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id manual_free_proxy_ndx_20260702
```

Result:

```text
validation_status=blocked
missing_required_dataset=benchmark_mapping
```

## Not Run

These were intentionally not run:

- `run-leveraged-etf-free-proxy-historical --benchmark-mode ndx_exact`
- `verify-leveraged-etf-free-proxy-run`
- `ingest-leveraged-etf-free-proxy-forward-snapshot`

Reason: mapping evidence is missing, so an NDX-exact run would not be valid.

## Validation

Code was not changed. Focused free-proxy tests passed:

```text
41 passed
```

## Remaining Manual Inputs Needed

Required:

- TQQQ -> NDX mapping evidence;
- SQQQ -> NDX mapping evidence;
- populated `sources/benchmark_mapping.csv`;
- source manifest entries and hashes for the mapping evidence.

Recommended:

- TQQQ/SQQQ daily prices;
- TQQQ/SQQQ AUM/NAV/shares;
- TQQQ/SQQQ split history;
- QQQ daily price export for proxy context.

## Guardrails Confirmed

- No network/provider/API/download/scrape.
- No raw data committed.
- No fabricated mapping, AUM, split, or timestamp.
- No strict Phase 1.3, Phase 2, release, or backtest.
- No trading, notifications, ranking, sizing, execution, or actionization.
- CTA and Dealer remain out of scope.
- `actionization_allowed=false`.
