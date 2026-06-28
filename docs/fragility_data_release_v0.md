# Fragility Data Release v0.2

This layer turns locally staged provider exports into an immutable, source-aware
input release for `market_bomb_fragility_score_v0.py`. It does not change the
v0.1.2 score formula, weights, thresholds, OOS definitions, or actionization
policy.

## Contract

- Input mode is local staged files only.
- Default network download, scraping, or provider fetch is not allowed.
- Raw provider exports are kept out of git.
- A release is immutable once built.
- Promotion to `active_release.json` is explicit and separate from build.
- `actionization_allowed=false` remains enforced in release and run receipts.

Ignored local paths:

```text
market_bomb_history/fragility_score_v0/staging/
market_bomb_history/fragility_score_v0/releases/
market_bomb_history/fragility_score_v0/active_release.json
```

## Staging Layout

Create a staging folder under:

```text
market_bomb_history/fragility_score_v0/staging/<staging_id>/
```

Required file:

```text
source_bundle_manifest.json
```

Source files are referenced by `relative_path` from the manifest. The preferred
layout is:

```text
sources/price_spy.csv
sources/price_qqq.csv
sources/price_soxx.csv
sources/vol_vix.csv
sources/vol_vix3m.csv
```

Required tickers for official `MARKET` score:

```text
SPY, QQQ, VIX, VIX3M
```

Optional tickers:

```text
SOXX, VIX9D
```

## Manifest Example

```json
{
  "artifact_version": "fragility_data_release_v0_2",
  "staging_id": "manual_export_20260628",
  "created_at_utc": "2026-06-28T00:00:00Z",
  "operator_attestation": {
    "personal_research_only": true,
    "terms_reviewed_by_operator": true,
    "do_not_commit_raw_data": true,
    "no_credentials_in_manifest": true
  },
  "sources": [
    {
      "source_id": "spy_price_provider_export",
      "ticker": "SPY",
      "asset_family": "equity_etf",
      "provider_name": "operator_supplied",
      "provider_dataset_name": "daily_price_history",
      "relative_path": "sources/price_spy.csv",
      "source_url_or_local_export_reference": "local/manual/export/SPY.csv",
      "terms_url_or_reference": "operator-reviewed-provider-terms",
      "terms_review_status": "operator_acknowledged",
      "allowed_usage_assertion": "personal_research_only",
      "retrieved_at_utc": "2026-06-28T00:00:00Z",
      "price_basis": "as_traded_close",
      "historical_effective_availability_policy": "assumed_nyse_close_plus_15_minutes_v0_2",
      "row_effective_timestamp_field": "",
      "source_timezone": "America/New_York",
      "expected_schema_profile": "daily_ohlcv_close"
    }
  ]
}
```

The terms attestation is an operator control and not legal advice. The builder
only verifies that the operator explicitly marked each required source as
reviewed for personal research use and that raw data is not intended for commit.

## Source CSV Columns

Required:

```text
session_date, close
```

Optional but retained when present:

```text
high, low, volume, source_as_of_timestamp_utc, effective_available_at_utc
```

If a timezone-aware `effective_available_at_utc` or configured
`row_effective_timestamp_field` is present, it is used with high availability
confidence. If not present, the row uses the NYSE close plus 15 minutes policy
from the repository calendar with medium confidence.

Timezone-naive effective timestamps, non-NYSE session dates, duplicate
same-source session rows, and non-positive close values are excluded.

## Commands

Verify staging:

```powershell
python market_bomb_fragility_data_release_v0.py verify-staging --staging-id <staging_id>
```

Build immutable release:

```powershell
python market_bomb_fragility_data_release_v0.py build-release --staging-id <staging_id>
```

Verify release:

```powershell
python market_bomb_fragility_data_release_v0.py verify-release --release-id <release_id>
```

Promote release:

```powershell
python market_bomb_fragility_data_release_v0.py promote-release --release-id <release_id>
```

Run scorer on a specific release:

```powershell
python market_bomb_fragility_data_release_v0.py run-score --release-id <release_id>
```

Run scorer on the active release:

```powershell
python market_bomb_fragility_data_release_v0.py run-active-score
```

## Release Outputs

Each release writes:

```text
canonical_input/
source_attestations.csv
source_file_inventory.csv
source_schema_audit.csv
source_coverage_audit.csv
source_availability_policy_audit.csv
source_terms_audit.csv
source_cross_source_audit.csv
release_quality_gate.csv
release_receipt.json
fragility_outputs/
fragility_real_history_oos_release_summary.md
```

`run-score` and `run-active-score` also write:

```text
fragility_score_execution_receipt_v0.json
```

## Freshness And Promotion

The release gate requires the latest completed NYSE session to be present for
all required sources unless an explicit stale override is used. Stale releases
can still be inspected as historical reconstructions, but they should not be
presented as current market state.

The builder uses the repository NYSE calendar. Historical row availability is
based on source row timestamps when supplied; otherwise it is reconstructed as
NYSE regular close plus 15 minutes.

## Operational Boundary

This release layer is a data provenance and reproducibility gate. It does not
authorize live trading, alerts, sizing, or scanner integration. Any downstream
use must continue to treat the score as descriptive until a separate
actionization review changes that policy.
