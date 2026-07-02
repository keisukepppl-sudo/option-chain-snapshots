# Leveraged ETF Free Proxy Canonical Input Contract v1

This document locks the executable manual input contract for `leveraged_etf_free_directional_proxy_v1`.

The executable parser, validator, generated template, and tests are the source of truth. Legacy one-file-per-ticker names are not supported active input filenames.

## Canonical Directory Tree

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

Raw source files stay local and ignored by git.

## File Contract

| File | Required for validation | Required columns | Canonical key | Purpose |
|---|---:|---|---|---|
| `source_manifest.json` | yes | top-level metadata and `sources[]` | `input_id`, `relative_path` in each source | provenance, hash, and descriptive-only controls |
| `sources/benchmark_prices.csv` | yes | `date`, `instrument`, `raw_close`, `raw_or_adjusted` | `date`, `instrument` | NDX exact or QQQ proxy benchmark returns |
| `sources/benchmark_mapping.csv` | yes | `leveraged_etf`, `target_benchmark_instrument`, `market_proxy_instrument`, `target_leverage`, `directionality`, `benchmark_exact_or_proxy`, `is_proxy_underlying`, `mapping_source_authority` | `leveraged_etf` | TQQQ/SQQQ benchmark mapping |
| `sources/leveraged_etf_prices.csv` | no | `date`, `instrument`, `raw_close`, `raw_or_adjusted` | `date`, `instrument` | TQQQ/SQQQ reconciliation context |
| `sources/aum_or_capital.csv` | no | `date`, `instrument`, `aum_usd`, `shares_outstanding`, `nav_per_share`, `unit` | `date`, `instrument` | rough AUM-scaled proxy |
| `sources/split_history.csv` | no | `instrument`, `effective_date`, `split_ratio`, `source_authority` | `instrument`, `effective_date` | split diagnostics |

Extra CSV columns may be present, but required columns must keep these exact names.

## Manifest Source Fields

Every `source_manifest.json` source entry must include:

```text
input_id
dataset_type
instrument
relative_path
content_sha256
row_identifier_field
source_name
source_authority_type
source_qualification_status
historical_vintage_available
publication_timestamp_available
revision_history_available
is_synthetic_fixture
manual_export_timestamp_utc
manual_capture_timestamp_utc
raw_or_adjusted
corporate_action_treatment
coverage_start
coverage_end
notes
```

Accepted free-history label:

```text
source_qualification_status=historical_descriptive_only
predictive_pit_eligible=false
phase2_eligible=false
actionization_allowed=false
```

Forbidden strict labels:

```text
gold_point_in_time_eligible
silver_documented_schedule_eligible
ready_for_eod_next_session_research
```

For free historical packages, these fields must not claim point-in-time eligibility:

```text
historical_vintage_available=false
publication_timestamp_available=false
revision_history_available=false
```

Timestamps must be explicit UTC strings ending in `Z` when used for forward capture. Historical current-download timestamps must not be converted into historical availability timestamps.

## Benchmark Mapping Rules

NDX exact mode:

| Leveraged ETF | Target benchmark | Market proxy | Target leverage | Directionality | Exact/proxy | `is_proxy_underlying` |
|---|---|---|---:|---|---|---|
| `TQQQ` | `NDX` | `QQQ` | `3` | `long` | `benchmark_exact` | `false` |
| `SQQQ` | `NDX` | `QQQ` | `-3` | `inverse` | `benchmark_exact` | `false` |

QQQ proxy-only descriptive mode:

| Leveraged ETF | Target benchmark | Market proxy | Exact/proxy |
|---|---|---|---|
| `TQQQ` | `QQQ` | `QQQ` | `proxy_based` |
| `SQQQ` | `QQQ` | `QQQ` | `proxy_based` |

QQQ is not the exact target benchmark for TQQQ or SQQQ. It is proxy-only unless the run mode is explicitly `qqq_proxy_only_descriptive`.

## Price Basis and Split Rules

- `benchmark_prices.csv` holds NDX and/or QQQ rows in the same normalized file.
- `leveraged_etf_prices.csv` holds TQQQ and/or SQQQ rows in the same normalized file.
- `raw_or_adjusted` must be explicit and consistent within the benchmark instrument used by a run.
- Split treatment must be documented in the manifest `corporate_action_treatment` field.
- Split diagnostics require `split_history.csv`; they are not inferred from prices.

## AUM and Shares Times NAV

`aum_or_capital.csv` may provide either:

- `aum_usd`, or
- `shares_outstanding` and `nav_per_share`.

The module uses exact lagged rows only. AUM is never forward-filled, interpolated, or invented. `unit` must be `USD` or blank for AUM-scaled output.

## Minimum Useful Packages

| Capability | Minimum normalized inputs |
|---|---|
| NDX exact equal-weight direction | populated `source_manifest.json`, NDX rows in `benchmark_prices.csv`, TQQQ/SQQQ NDX exact rows in `benchmark_mapping.csv`, valid hashes, descriptive-only labels |
| QQQ proxy-only direction | populated `source_manifest.json`, QQQ rows in `benchmark_prices.csv`, TQQQ/SQQQ proxy rows in `benchmark_mapping.csv`, valid hashes, descriptive-only labels |
| AUM-scaled proxy | direction-capable package plus TQQQ/SQQQ rows in `aum_or_capital.csv` |
| Split-reconciled diagnostics | package plus TQQQ/SQQQ rows in `split_history.csv` |
| Forward PIT-lite snapshot intake | valid descriptive-only package with real local sources and UTC capture timestamp |

TQQQ/SQQQ rows in `leveraged_etf_prices.csv` are strongly recommended for reconciliation, but they are not required for equal-weight direction.

## Validator Failure Categories

The validator blocks at least these conditions:

- missing `source_manifest.json`;
- malformed or non-list `sources`;
- missing required manifest fields;
- duplicate source paths;
- missing source files;
- SHA-256 mismatch;
- non-`historical_descriptive_only` free-history status;
- forbidden strict eligibility labels;
- historical PIT claims from free current-history files;
- missing `benchmark_prices` or `benchmark_mapping` dataset;
- missing mapping columns;
- raw provider files tracked by git.

The inspect helper also reports missing normalized files, missing CSV headers, detected instruments, hash status, and supported capabilities without creating run artifacts.

## Deprecated Legacy Names

These planning filenames are deprecated and are not active input filenames:

```text
ndx_daily.csv
qqq_daily.csv
tqqq_daily.csv
sqqq_daily.csv
tqqq_aum_nav.csv
sqqq_aum_nav.csv
tqqq_splits.csv
sqqq_splits.csv
```

Use the normalized template generated by:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-template --input-id <opaque_input_id>
```

