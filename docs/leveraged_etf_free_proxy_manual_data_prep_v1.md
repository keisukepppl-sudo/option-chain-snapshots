# Leveraged ETF Free Proxy Manual Data Preparation v1

This is a human-first, no-network workflow. Codex must not fetch, download, scrape, browse, call provider APIs, add credentials, or synthesize market data.

## Step A: Build the Template

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-template --input-id <opaque_input_id>
```

This creates the canonical normalized files under:

```text
market_bomb_history/leveraged_etf_free_proxy_v1/input/<opaque_input_id>/
```

The generated files are header-only until a human populates them.

## Step B: Acquire Files Manually Outside the Repo

Acquire and review source files manually:

```text
NDX daily market-price export
QQQ daily market-price export, optional proxy context
TQQQ daily market-price export
SQQQ daily market-price export
ProShares TQQQ/SQQQ Historical NAV, shares, or AUM export, optional for scale
ProShares TQQQ/SQQQ split history, when needed
TQQQ/SQQQ benchmark documentation
```

Keep provider exports, screenshots, correspondence, and raw documents outside git.

## Step C: Populate Normalized Files

| Human source extract | Canonical destination | Purpose | Needed for |
|---|---|---|---|
| NDX daily prices | `sources/benchmark_prices.csv` | exact target return | NDX exact direction |
| QQQ daily prices | `sources/benchmark_prices.csv` | proxy/outcome context | optional or proxy-only |
| TQQQ daily prices | `sources/leveraged_etf_prices.csv` | reconciliation | recommended |
| SQQQ daily prices | `sources/leveraged_etf_prices.csv` | reconciliation | recommended |
| TQQQ mapping evidence | `sources/benchmark_mapping.csv` | NDX, +3, long, QQQ proxy | all NDX exact runs |
| SQQQ mapping evidence | `sources/benchmark_mapping.csv` | NDX, -3, inverse, QQQ proxy | all NDX exact runs |
| TQQQ/SQQQ NAV, AUM, or shares | `sources/aum_or_capital.csv` | rough scale | AUM-scaled output |
| TQQQ/SQQQ split history | `sources/split_history.csv` | continuity diagnostics | when applicable |

## Step D: Complete Manifest Provenance

For every populated local file, add one `sources[]` entry in `source_manifest.json`.

Required free-history settings:

```text
source_qualification_status=historical_descriptive_only
historical_vintage_available=false
publication_timestamp_available=false
revision_history_available=false
predictive_pit_eligible=false
phase2_eligible=false
```

Do not fabricate:

- historical availability time;
- publication or revision timing;
- source authority;
- units;
- coverage;
- benchmark semantics;
- corporate action treatment.

Every manifest `content_sha256` must match the local file.

## Step E: Inspect Before Validation

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id <opaque_input_id>
```

The helper is local-only and read-only. It reports:

- expected, present, and missing files;
- found headers and missing required headers;
- manifest entries and hashes;
- detected instruments and date coverage;
- descriptive-only status;
- capability flags for NDX exact, QQQ proxy-only, AUM scale, split diagnostics, and forward snapshot ingestion.

It creates no proxy run, no ledger, and no readiness artifact.

## Step F: Validate

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id <opaque_input_id>
```

Validation must pass before any descriptive run.

## Step G: Historical Descriptive Run

NDX exact:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <opaque_input_id> --benchmark-mode ndx_exact
```

QQQ proxy-only descriptive fallback:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <opaque_input_id> --benchmark-mode qqq_proxy_only_descriptive
```

Do not run either command against header-only templates.

## Step H: Verify the Exact Artifact

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py verify-leveraged-etf-free-proxy-run --run-artifact <exact_run_path>
```

## Minimum Useful Checklist

Minimum useful NDX exact direction run:

- populated `source_manifest.json`;
- NDX rows in `benchmark_prices.csv`;
- TQQQ/SQQQ NDX exact mappings in `benchmark_mapping.csv`;
- valid hashes;
- explicit `historical_descriptive_only` classifications.

Strongly recommended:

- TQQQ/SQQQ rows in `leveraged_etf_prices.csv` for reconciliation and split checks.

Needed only for rough scale:

- TQQQ/SQQQ AUM, or shares plus NAV, in `aum_or_capital.csv`.

No free-data run may enter strict Phase 1.3 readiness, Phase 2, Flow release, statistical backtest, notification, trading, or actionization.

