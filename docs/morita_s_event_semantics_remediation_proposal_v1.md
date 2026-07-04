# Morita S Event Semantics Remediation Proposal v1

This is a proposal only. No implementation is included in the reconciliation audit.

Recommended future work:

1. Preserve raw formal S events unchanged.
2. Add a separate point-in-time event semantics layer with explicit columns for `base_breakout_id`, `base_start_date`, `base_breakout_date`, `cooldown_state`, and `dedupe_decision`.
3. Enforce any 20-session same-ticker cooldown only in a new derived population, not by rewriting historical raw events.
4. Require a point-in-time-safe base-id algorithm before classifying same-ticker reentries as valid new-base breakouts.
5. Retest fixed-IV performance on raw events, cooldown-filtered events, and base-id-filtered events before using any result for sizing research.

