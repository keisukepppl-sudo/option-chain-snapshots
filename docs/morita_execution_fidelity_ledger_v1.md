# Morita Execution Fidelity Ledger v1

This ledger audits whether manual fills match the user-declared Morita signal and manual order intent.

It is not a broker execution system and contains no live-order method.

## Linkage

Link priority:

1. Explicit broker/client mapping to intent or signal.
2. Exact local manual-order-intent link.
3. Deterministic candidate using underlying, option right, expiry, DTE band, and time context.
4. Otherwise `manual_link_required`.

Candidate links are never exact.

## Fidelity Checks

The ledger checks timing, DTE band, option right, premium-at-risk plan, and structured exit-reason availability. It never judges whether an exit was financially correct based on later prices.

No trade instruction is generated.
