# Morita Notification v2 Operations

Register a confirmed setup:

```powershell
python scripts/register_live_setup.py --setup-json path/to/confirmed_setup.json
```

Run a notification cycle with local market data and an exchange-session calendar:

```powershell
python scripts/run_morita_notification_cycle.py --exchange-session-date 2026-07-10 --eligible-sessions-csv path/to/sessions.csv --market-data-csv path/to/market.csv
```

Acknowledge an exit:

```powershell
python scripts/ack_exit.py --setup-id SETUP_ID --reason time_stop --note "closed manually"
```

Build the weekly forward report:

```powershell
python scripts/build_weekly_forward_execution_report.py
```

Local state and audit outputs are ignored by git. Do not store credentials, account IDs, raw Webull exports, raw order IDs, or live order identifiers in committed files.
