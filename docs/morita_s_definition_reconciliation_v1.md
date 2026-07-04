# Morita S Definition Reconciliation v1

This audit separates raw formal S events from research-only event semantics such as first-breakout-only, ticker cooldown, and new-base reentry.

The audit does not optimize, alter live alerts, change rank rules, change sizing, or modify formal history.

Current finding to preserve until separately remediated: the formal S baseline stores an event stream keyed by date, entry session, ticker, rank, and rule hash. It does not persist a base identifier and does not enforce a documented 20-session same-ticker cooldown in the exported formal S rows.

Legacy vertical and breakout research artifacts can be used as price-movement or outcome-lineage support after ticker/date key reconciliation. They must not be treated as direct single-call PF evidence because the payoff structure, parameter grid, and source-seal status differ from the fixed-IV S reference model.
