# QQQ Price Basis and Corporate Actions Policy

Use the canonical policy in `docs/flow_pressure_qqq_price_basis_and_corporate_actions_policy.md`.

Summary:

- Preserve raw prices.
- Preserve vendor adjusted close separately.
- Preserve an explicit TQQQ/SQQQ split ledger.
- Do not treat current adjusted history as PIT-safe.
- Block predictive qualification on unresolved raw/adjusted mismatch or missing split ledger.
