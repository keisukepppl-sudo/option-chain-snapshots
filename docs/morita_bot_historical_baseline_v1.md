# Morita Bot Historical Baseline v1

This baseline replays the current Morita Bot production signal path over a stitched daily OHLCV history.

The signal path imports the current scanner pipeline and production selection code:

- `scanner.pipeline.scan_universe`
- `scanner_notify.select_candidates`
- `scripts.production_scanner_entry` final adjusted score and `alert_rank`

The baseline is underlying-only. It does not calculate option P&L, DTE, strike, delta, fills, ranking optimization, sizing, notifications, or live trading actions.

Universe status is `static_historical_proxy`. Data source status is `stitched_local_history_plus_authorized_tail`.
