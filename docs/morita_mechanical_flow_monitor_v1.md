# Morita Mechanical Flow Monitor v1

## Purpose

`scripts/build_morita_mechanical_flow_monitor_v1.py` logs daily mechanical-flow context for research. It is a thermometer only.

It does not filter S signals, change rank logic, change sizing, create alerts, access broker/account data, or create orders.

## Inputs

The monitor reuses committed or locally generated `daily_flow_outputs/<date>/` files where present:

- `cta_signals.csv`
- `vol_control_proxy.csv`
- `leveraged_etf_aum_flows.csv` or `us_leveraged_etf_flows.csv`
- `market_down_rs.csv`
- `combined_mechanical_flow.csv`

Unavailable metric families are logged as unavailable with a reason. Values are not fabricated.

## Outputs

Runtime outputs are ignored under `outputs/morita_mechanical_flow_monitor_v1/`:

- `mechanical_flow_daily_context.csv`
- `mechanical_flow_metric_availability.csv`
- `mechanical_flow_source_lineage.json`
- `mechanical_flow_receipt.json`
- `mechanical_flow_content_manifest.json`
- `mechanical_flow_summary.md`

## Safety

Policy lives at `config/morita_mechanical_flow_monitor_v1/policy.json`.

Required flags:

- `research_only=true`
- `no_signal_filtering=true`
- `no_auto_execution=true`
- `broker_execution_enabled=false`
- `auto_trade_action_enabled=false`
- `pushover_emergency_enabled=false`
- rank, sizing, and notification changes disabled

The script refuses to run if these flags are changed.
