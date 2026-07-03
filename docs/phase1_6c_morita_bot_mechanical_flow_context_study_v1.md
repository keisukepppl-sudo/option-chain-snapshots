# Phase 1.6C Morita Bot Mechanical-Flow Context Study

This layer joins a manifest-verified Phase 1.6B CTA / vol-control / leveraged ETF scale context panel to an already sealed Morita Bot signal/outcome artifact.

The study is historical and descriptive. It cannot generate Morita Bot rows, rerun option outcomes, alter S/A/B definitions, alter exits, create a composite score, or create an execution rule.

## Inputs

- `outputs/phase1_6b_cross_module_downside/`
- One existing Morita Bot artifact with:
  - receipt
  - content manifest
  - signal-level rows
  - signal-linked outcome rows
  - schema map
  - rule version or config hash

If the Morita source artifact is absent or ineligible, the script emits a controlled blocked output instead of reconstructing rows.

## Timing Rule

Mechanical-flow context is attached only where:

`Phase1.6B.observation_date == MoritaBot.signal_decision_date`

`next_effective_session` is not used as the decision-date key. Entry sessions must be after the decision date, and outcome timing must not precede entry.

## Outputs

All outputs are written under:

`outputs/phase1_6c_morita_bot_mechanical_flow_context/`

The output directory is manifest-verified and must not be inside `market_bomb_history`.

## Boundary

The output is not a selection decision, not a trading filter, not a sizing rule, not a causal result, and not a predictive model.
