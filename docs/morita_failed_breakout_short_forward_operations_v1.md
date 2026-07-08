# Morita Failed Breakout Short Forward Operations v1

## Default Operation

The forward research loggers are disabled by default in the production scanner entrypoint.

Set `MORITA_FORWARD_RESEARCH_LOGGERS_ENABLED=1` only when research logging is intentionally enabled.

Mechanical flow can run from existing `daily_flow_outputs`. Failed-breakout logging requires explicit CSV inputs:

- `MORITA_FAILED_BREAKOUT_PRICE_PANEL`
- `MORITA_FAILED_BREAKOUT_RS_PANEL`
- `MORITA_FAILED_BREAKOUT_REGIME_PANEL`

If those three paths are not provided, the production hook only runs mechanical-flow logging.

## Commands

Mechanical flow:

```bash
python scripts/build_morita_mechanical_flow_monitor_v1.py
```

Failed breakout forward logger:

```bash
python scripts/build_morita_failed_breakout_short_forward_v1.py --price-panel prices.csv --rs-panel rs.csv --regime-panel regime.csv
```

Review completed outcomes:

```bash
python scripts/build_morita_failed_breakout_short_forward_review_v1.py
```

## Safety Checks

Before promoting any research idea, verify:

- policy safety flags remain disabled for broker, account, put alert, live short signal, and automatic execution paths
- Long S rank, universe, breakout, volume, cooldown, TP125, and regime sizing policies are unchanged
- runtime outputs remain ignored and untracked
- review summaries use completed outcomes only

No rule is auto-promoted by this module.
