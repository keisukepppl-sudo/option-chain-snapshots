# Flow Pressure Research v0

`flow_pressure_research_v0` is an isolated, research-only layer for model-implied pressure proxies. It does not change Fragility Score formulas and it does not connect to Morita notifications, candidate ranking, trading, or execution.

All outputs are `model_implied_pressure`, never observed institutional flow. `actionization_allowed=false` is enforced throughout.

## Architecture

```text
local source CSV
  -> source_bundle_manifest.json
  -> validate-flow-provider-contract
  -> canonical_input
  -> timing_audit
  -> feature/release
  -> exploratory backtest
```

No command downloads data, scrapes websites, uses browser automation, provider SDKs, API keys, or credentials. Real provider exports must be copied manually into local staging.

## Modules

Implemented:

- Leveraged ETF rebalance pressure: theoretical rebalance pressure from observed AUM, ETF reference mapping, and underlying return.
- Vol-control deleveraging pressure: normalized exposure change from explicit return windows.

Blocked placeholders:

- CTA trend flow pressure: `methodology_incomplete`.
- Dealer hedge / gamma regime: `methodology_incomplete`.

## CLI

```powershell
python market_bomb_flow_pressure_research_v0.py build-flow-staging-template --staging-id template_001
python market_bomb_flow_pressure_research_v0.py validate-flow-provider-contract --staging-id fixture_flow --decision-time-utc 2020-02-20T22:00:00Z --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py audit-flow-timing --staging-id fixture_flow --decision-time-utc 2020-02-20T22:00:00Z --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py inspect-flow-source-coverage --staging-id fixture_flow --decision-time-utc 2020-02-20T22:00:00Z --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py verify-flow-staging --staging-id fixture_flow --now-utc 2020-02-20T22:00:00Z --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py build-flow-release --staging-id fixture_flow --now-utc 2020-02-20T22:00:00Z --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py verify-flow-release --release-id <release_id>
python market_bomb_flow_pressure_research_v0.py run-flow-backtest --release-id <release_id>
python market_bomb_flow_pressure_research_v0.py verify-flow-backtest --release-id <release_id> --backtest-run-id <run_id>
python market_bomb_flow_pressure_research_v0.py inspect-flow-release --release-id <release_id>
```

## Staging Layout

```text
market_bomb_history/
  flow_pressure_research_v0/
    staging/
      <staging_id>/
        source_bundle_manifest.json
        sources/
          prices_daily.csv
          prices_intraday.csv
          leveraged_etf_reference.csv
          leveraged_etf_aum.csv
          vol_control_returns.csv
```

`<staging_id>` must be an opaque local ID, not a provider name, account name, or secret.

## Manifest Contract

Each source must be declared before it is read:

```json
{
  "source_id": "leveraged_etf_aum",
  "source_name": "manual_provider_export_alias",
  "source_file": "sources/leveraged_etf_aum.csv",
  "relative_path": "sources/leveraged_etf_aum.csv",
  "dataset_type": "leveraged_etf_aum",
  "dataset_version": "provider_export_format_v1",
  "coverage_start_date": "YYYY-MM-DD",
  "coverage_end_date": "YYYY-MM-DD",
  "timezone": "UTC",
  "row_identifier_field": "source_row_id",
  "content_sha256": "<sha256>",
  "is_synthetic_fixture": false
}
```

The manifest also records:

- `source_contract_version=flow_provider_contract_v1`
- `research_timing_class`
- `decision_time_specification`

The validator rejects undeclared files, missing declared files, content hash mismatches, duplicate paths, path traversal, absolute paths, Windows drive paths, UNC paths, and symlinked staged files where supported.

## CSV Contracts

### Daily Price

Required columns:

```text
source_row_id,instrument,asset_class,market,market_timestamp,available_at_timestamp,source_as_of_timestamp,session_date,open,high,low,close,adjusted_close,volume,currency,source_name,source_file,dataset_version
```

Daily rows can support `eod_next_session`, `eod_after_close`, and `historical_descriptive_only`. They cannot support `intraday_close_window`.

### Intraday Price / Close Window

Required columns:

```text
source_row_id,instrument,asset_class,market,bar_start_timestamp,bar_end_timestamp,available_at_timestamp,source_as_of_timestamp,open,high,low,close,volume,bar_interval_seconds,currency,source_name,source_file,dataset_version
```

`intraday_close_window` requires timing-eligible intraday rows. Daily rows are never promoted into close-window eligibility.

### Leveraged ETF Reference

Required columns:

```text
source_row_id,etf_instrument,underlying_instrument,target_leverage,directionality,asset_class,market,effective_start_timestamp,effective_end_timestamp,available_at_timestamp,source_as_of_timestamp,source_name,source_file,dataset_version
```

`target_leverage` must be finite and non-zero. `directionality` must be `long` or `inverse`. Overlapping mappings for the same ETF are blocked.

### Leveraged ETF AUM / NAV / Shares

Required columns:

```text
source_row_id,etf_instrument,as_of_timestamp,available_at_timestamp,source_as_of_timestamp,aum_usd,shares_outstanding,nav_per_share,currency,publication_status,valid_until_timestamp,source_name,source_file,dataset_version
```

The row must include `aum_usd` or both `shares_outstanding` and `nav_per_share`. If both are present, both are preserved. Missing AUM is never fabricated.

### Vol-Control Returns

Required columns:

```text
source_row_id,instrument,asset_class,market,return_start_timestamp,return_end_timestamp,available_at_timestamp,source_as_of_timestamp,simple_return,log_return,price_basis,source_name,source_file,dataset_version
```

At least one return field must be finite. A calculation series may use only one explicit `price_basis`. Missing returns are not bridged or imputed.

## Timing Classes

Allowed values:

- `eod_next_session`
- `eod_after_close`
- `intraday_close_window`
- `historical_descriptive_only`

Provider publication time matters more than the timestamp printed on a data row. A row is `timing_eligible` only if the exact row was available by `decision_time`. Rows known later are `timing_ineligible` and appear in `timing_audit.csv`.

Example:

- A daily close has `market_timestamp=2020-02-20T21:00:00Z`.
- The provider publishes the export at `available_at_timestamp=2020-02-20T21:45:00Z`.
- A `decision_time=2020-02-20T21:10:00Z` cannot use that row.
- A `decision_time=2020-02-20T22:00:00Z` can use that row for EOD research, but not as proof of intraday close-window availability.

## AUM Freshness Policy

The latest previously published AUM row may be selected only when:

- it is an observed staged row;
- `available_at_timestamp <= decision_time`;
- `valid_until_timestamp` exists;
- `valid_until_timestamp >= decision_time`;
- the age is within `max_aum_observation_age_days`;
- the output records `selected_aum_source_row_id`, `aum_observation_age`, and `aum_selection_rule`.

If no row qualifies, the feature is `insufficient_coverage`.

## Release Outputs

- `release_core_metadata.json`
- `release_content_manifest.json`
- `release_receipt.json`
- `source_file_inventory.csv`
- `source_coverage_audit.csv`
- `source_timeliness_audit.csv`
- `provider_contract_validation_report.json`
- `timing_audit.csv`
- `feature_quality_gate.csv`
- `module_methodology.json`
- `parameter_registry.json`
- `backtest_spec.json`
- `backtest_results.csv`
- `backtest_summary.md`
- `explicit_limitations.md`
- `canonical_input/flow_pressure_canonical_source_rows.csv`
- `features/flow_pressure_features.csv`

## Provider Onboarding Checklist

1. Create a template with `build-flow-staging-template`.
2. Copy provider exports into `sources/` manually.
3. Record every file in `source_bundle_manifest.json`.
4. Compute and record `content_sha256`.
5. Verify all timestamps are timezone-aware.
6. Confirm `available_at_timestamp` is the earliest time the exact row could have been known.
7. Run `validate-flow-provider-contract`.
8. Run `audit-flow-timing`.
9. Run `inspect-flow-source-coverage`.
10. Only then build a research release.

## Known Limits

- No observed flows.
- Provider revisions can invalidate prior exports.
- AUM cadence can constrain inference.
- Daily data cannot support close-window claims.
- CTA and Dealer remain incomplete.
- Research eligibility, predictive evidence, and trading permission are separate. This layer implements only research eligibility.
