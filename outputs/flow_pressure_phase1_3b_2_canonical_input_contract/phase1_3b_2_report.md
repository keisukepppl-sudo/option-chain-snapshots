# Flow Pressure Phase 1.3B.2 Report

## Outcome

Phase 1.3B.2 locked the executable generated template as the canonical manual input contract for `leveraged_etf_free_directional_proxy_v1`.

- Start commit: `08e80427cfd4f4f8055f28429a9cdc3eea6c49fe`
- Raw data fetched: no
- Raw data committed: no
- Historical descriptive run against template-only data: no
- Strict Phase 1.3 / Phase 2 / release / backtest / notification / trading / actionization: not run
- `actionization_allowed`: remains `false`

## Canonical Input Layout

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

Legacy per-ticker names are deprecated and are not active input filenames.

## Code Changes

Added a local-only read-only helper:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id <opaque_input_id>
```

The helper:

- makes no network calls;
- transforms nothing;
- overwrites nothing;
- creates no proxy run, ledger, readiness artifact, or actionization artifact;
- reports expected, present, and missing normalized files;
- reports found headers and missing required headers;
- reports manifest entries and SHA-256 hash status;
- reports detected instruments and coverage;
- reports descriptive-only status;
- reports capability flags for NDX exact direction, QQQ proxy-only direction, AUM scale, split diagnostics, and forward snapshot ingestion.

## Documentation Added

- `docs/leveraged_etf_free_proxy_canonical_input_contract_v1.md`
- `docs/leveraged_etf_free_proxy_manual_data_prep_v1.md`
- `docs/leveraged_etf_free_proxy_contract_migration_v1.md`

## Documentation Updated

- `docs/leveraged_etf_free_directional_proxy_v1.md`
- `docs/leveraged_etf_free_proxy_operator_runbook_v1.md`
- `docs/flow_pressure_research_program_v1.md`
- `outputs/flow_pressure_phase1_3b_1_free_proxy_intake/flow_pressure_phase1_3b_1_chatgpt_bundle.md`
- `outputs/flow_pressure_phase1_3b_1_free_proxy_intake/flow_pressure_phase1_3b_1_intake_report.md`
- `outputs/flow_pressure_phase1_3b_1_free_proxy_intake/free_proxy_input_inventory.csv`

## Stale Locations Corrected

Active guidance now points to the normalized five-file layout. Phase 1.3B.1 outputs that listed per-ticker names were updated to mark those names as deprecated planning names.

Remaining occurrences of `TQQQ -> QQQ` / `SQQQ -> QQQ` in active docs are explicit rejection examples, not active exact-mapping instructions.

## Minimum Useful Data Prep

Minimum NDX exact direction package:

- populated `source_manifest.json`;
- NDX rows in `sources/benchmark_prices.csv`;
- TQQQ/SQQQ NDX exact mappings in `sources/benchmark_mapping.csv`;
- valid SHA-256 hashes;
- explicit `historical_descriptive_only` source classifications.

Recommended for reconciliation:

- TQQQ/SQQQ rows in `sources/leveraged_etf_prices.csv`.

Needed only for rough scale:

- TQQQ/SQQQ AUM, or shares plus NAV, in `sources/aum_or_capital.csv`.

Needed for split diagnostics:

- TQQQ/SQQQ rows in `sources/split_history.csv`.

## Validation

Focused free-proxy suite:

```text
41 passed
```

Full repository tests were run file-by-file because one-shot `pytest -q` exceeded the 15 minute local timeout while executing existing long Fragility tests. File-by-file results:

```text
373 passed, 2 skipped
```

The long Fragility files passed when given longer per-file timeouts:

```text
tests/test_market_bomb_fragility_data_release_v0.py: 22 passed, 1 skipped
tests/test_market_bomb_fragility_score_v0.py: 57 passed
```

Compile check:

```text
market_bomb_leveraged_etf_free_proxy_v1.py compiled successfully
```

## Safety Confirmation

- No external market data was acquired.
- No provider files were committed.
- `market_bomb_history/leveraged_etf_free_proxy_v1/` remains git-ignored.
- The helper does not create historical run artifacts.
- The helper does not alter `predictive_pit_eligible`, `phase2_eligible`, or `actionization_allowed`.
- Free history remains descriptive-only.
- Strict predictive gates are unchanged.

No output is a trade signal, alpha claim, market-impact conclusion, or permission to move to Phase 2.

