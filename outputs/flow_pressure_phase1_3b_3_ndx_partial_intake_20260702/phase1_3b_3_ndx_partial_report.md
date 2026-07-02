# Flow Pressure Phase 1.3B.3 NDX Partial Intake Report

## Outcome

Main outcome: `manual_raw_source_inputs_incomplete`

Forward collection: `forward_snapshot_not_started`

Start commit: `fbc66e0b874b3ea754ec1c00cc0f0da1072c22ed`

The supplied NDX workbook was archived locally and normalized into the canonical contract, but the first NDX-exact descriptive run remains blocked because TQQQ/SQQQ -> NDX mapping evidence is not supplied.

## Supplied Raw Source

| Field | Value |
|---|---|
| Raw file | `EODHist_20230703-20260702_NDX.xlsx` |
| SHA-256 | `8ea462ee5448d2f1f2cbab7a19dfa8934d41204ca963b0ef9712b50f80fb52e1` |
| Size | `51,885` bytes |
| Archived under | `market_bomb_history/leveraged_etf_free_proxy_v1/manual_source_archive/manual_free_proxy_ndx_20260702/` |
| Raw committed | no |

The copy timestamp proves only local possession. It does not prove historical publication timing or historical point-in-time availability.

## Normalization

Input ID:

```text
manual_free_proxy_ndx_20260702
```

Normalization run ID:

```text
norm_20260702T113715Z_c5b6788c
```

Deterministic transformation:

- `Trade Date` -> `date`
- constant `NDX` -> `instrument`
- `Index Value` -> `raw_close`
- constant `raw` -> `raw_or_adjusted`
- rows with missing, nonnumeric, or nonpositive `Index Value` were excluded
- no forward fill, backfill, interpolation, or timestamp inference

Row counts:

| Metric | Count |
|---|---:|
| Original rows | 753 |
| Normalized NDX rows | 752 |
| Excluded rows | 1 |

Coverage:

```text
2023-07-03 to 2026-07-01
```

The excluded row is the 2026-07-02 row with `Index Value=0.0`; it was not filled or inferred.

Canonical file created locally:

```text
market_bomb_history/leveraged_etf_free_proxy_v1/input/manual_free_proxy_ndx_20260702/sources/benchmark_prices.csv
```

Canonical file SHA-256:

```text
005717af54d31542ec9a41937db5fae7e82d6508519b57652d15bb30904f5ada
```

## Inspection Result

Read-only inspect command:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id manual_free_proxy_ndx_20260702
```

Result:

```text
validation_status=blocked
benchmark_prices rows=752
benchmark_prices instrument=NDX
benchmark_prices coverage_start=2023-07-03
benchmark_prices coverage_end=2026-07-01
benchmark_mapping rows=0
ndx_exact_direction_possible=false
aum_scaled_possible=false
split_diagnostics_possible=false
forward_snapshot_ingestion_possible=false
creates_run_artifact=false
```

Manifest status:

```text
descriptive_only_status=valid
benchmark_prices hash_status=match
predictive_pit_eligible=false
phase2_eligible=false
actionization_allowed=false
```

## Validator Result

Validation command:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id manual_free_proxy_ndx_20260702
```

Result:

```text
validation_status=blocked
missing_required_dataset=benchmark_mapping
```

## Why No Run Was Created

Minimum NDX exact direction still requires:

- TQQQ -> NDX mapping evidence;
- SQQQ -> NDX mapping evidence;
- populated `sources/benchmark_mapping.csv` with valid hashes and descriptive-only provenance.

Without that mapping, an NDX exact historical run would not be reproducible or semantically valid.

## Validation

Code was not changed. Focused free-proxy tests passed:

```text
41 passed
```

## Guardrails

- No network/provider/API/download/scrape was used.
- No raw source file was committed.
- No fabricated mapping, AUM, split, or timestamp was created.
- No historical descriptive run was created.
- No strict Phase 1.3, Phase 2, release, or backtest was run.
- No trading, notifications, ranking, sizing, execution, or actionization was run.
- CTA and Dealer remain out of scope.
- `actionization_allowed=false`.

No output is a trading recommendation, alpha claim, market-impact conclusion, or permission to proceed to strict predictive research.
