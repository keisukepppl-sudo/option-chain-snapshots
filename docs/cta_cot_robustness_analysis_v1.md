# CTA COT Robustness Analysis v1

This analysis is historical descriptive external consistency research only.

It requires exactly four predeclared CTA COT validation artifacts for:

- `cta_ts_20d_binary_v1`
- `cta_ts_60d_binary_v1`
- `cta_ts_120d_binary_v1`
- `cta_ts_20_60_120_equal_weight_v1`

The input must be the confirmed NDX cash-index proxy to `NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE`, with literal CFTC Contract Market Code `20974+`. The `leveraged_funds` COT group is not CTA-only and is not actual CTA flow.

The robustness summary keeps `as_of_ex_post_only` and `availability_monitoring_only` separate. Window changes are recomputed inside each window, and the first retained row has no carried-in change from outside the window.

The fixed windows are full covered period, pre-2025, from-2025, calendar 2024, calendar 2025, calendar 2023 H2, and calendar 2026 YTD.

No ranking, winner, pass/fail, acceptance threshold, model selection, trading signal, strict PIT claim, Phase 2 admission, sizing, notification, or execution is produced.
