# Flow Pressure QQQ Data Acquisition Runbook v1

Codex must not acquire data in Phase 1.3A. The operator manually obtains files and records source evidence.

## Manual Package

Required local source files:

```text
NDX daily market data
QQQ daily market data
TQQQ daily market data
SQQQ daily market data
TQQQ Historical NAV/AUM/shares
SQQQ Historical NAV/AUM/shares
TQQQ Split History
SQQQ Split History
TQQQ/SQQQ benchmark documentation
decision_schedule.csv
source_bundle_manifest.json
```

Raw provider files must not be committed.

## Acquisition Log

For each manually obtained source file, record:

```text
manual_download_timestamp_utc
source_page_name
source_file_name
content_sha256
operator_alias
known_source_update_schedule
notes
```

The operator download timestamp is not the historical row `available_at_timestamp`.

## Vendor Qualification Questions

Ask every vendor whether flat-file exports include:

1. Economic as-of date.
2. Original publication or available timestamp.
3. Revision/version identifier.
4. Historical vintage or revision history.
5. Raw versus corporate-action-adjusted fields.
6. Split treatment.
7. Field definitions and units.
8. Coverage and update cadence.

Manual flat-file export is sufficient. No API integration is requested.

## Readiness Stop Rule

After the operator stages a complete real package, Codex may validate Phase 1.3 readiness only. It must not run Phase 2, build a release, run a statistical backtest, send notifications, or mark actionization allowed.
