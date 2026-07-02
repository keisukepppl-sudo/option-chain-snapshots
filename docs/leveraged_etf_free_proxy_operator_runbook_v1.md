# Leveraged ETF Free Proxy Operator Runbook v1

This runbook describes manual local use only. Codex must not fetch, download, scrape, browse, call APIs, add SDKs, or store credentials for this module.

## Ignored Local Layout

```text
market_bomb_history/
  leveraged_etf_free_proxy_v1/
    input/<opaque_input_id>/
      source_manifest.json
      sources/
        benchmark_prices.csv
        benchmark_mapping.csv
        aum_or_capital.csv
        split_history.csv
        leveraged_etf_prices.csv
    historical_runs/<run_id>/
    forward_ledger/
      snapshots/
      observations/
```

Raw source files stay local and ignored by git.

## Build Templates

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-template --input-id <opaque_input_id>
```

Populate the generated CSVs manually and update `source_manifest.json` with hashes and descriptive-only qualification.

The normalized generated files are the active contract. Legacy per-ticker names such as `ndx_daily.csv`, `tqqq_daily.csv`, or `tqqq_aum_nav.csv` are deprecated planning names and are not supported active input filenames.

## Inspect the Contract

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id <opaque_input_id>
```

This command is local-only and read-only. It creates no proxy run, no forward ledger, no strict readiness artifact, and no actionization artifact.

It reports:

- expected, present, and missing normalized files;
- found headers and missing required headers;
- manifest entries and SHA-256 hash status;
- detected instruments and coverage;
- descriptive-only status;
- whether the package supports NDX exact direction, QQQ proxy-only direction, AUM scale, split diagnostics, and forward PIT-lite snapshot ingestion.

## Validate Inputs

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id <opaque_input_id>
```

Validation checks containment, manifest fields, file hashes, descriptive-only classification, mapping, and raw provider files not tracked by git.

## Historical Descriptive Run

Exact NDX:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <opaque_input_id> --benchmark-mode ndx_exact
```

QQQ proxy-only:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <opaque_input_id> --benchmark-mode qqq_proxy_only_descriptive
```

Every run is descriptive-only and creates no strict readiness artifact.

## Forward PIT-Lite Snapshot

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py ingest-leveraged-etf-free-proxy-forward-snapshot --input-id <opaque_input_id> --snapshot-date <YYYY-MM-DD> --capture-timestamp-utc <ISO8601Z>
```

Snapshots are append-only. A duplicate snapshot ID with a different source hash is rejected.

## Forward Observation

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-forward-observation --observation-date <YYYY-MM-DD>
```

The observation uses captured lineage. Missing prior capital snapshot yields unavailable output, not substitution.

## Verification

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py verify-leveraged-etf-free-proxy-run --run-artifact <exact_run_path>
python market_bomb_leveraged_etf_free_proxy_v1.py verify-leveraged-etf-free-proxy-forward-ledger --ledger-root <path>
```

## Required Labels

```text
module_name=leveraged_etf_free_directional_proxy_v1
research_only=true
actionization_allowed=false
not_a_trading_signal=true
not_market_impact_estimate=true
not_dealer_inventory_estimate=true
```

## Reference Docs

- `docs/leveraged_etf_free_proxy_canonical_input_contract_v1.md`
- `docs/leveraged_etf_free_proxy_manual_data_prep_v1.md`
- `docs/leveraged_etf_free_proxy_contract_migration_v1.md`
