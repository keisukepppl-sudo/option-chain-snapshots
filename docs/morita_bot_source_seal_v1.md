# Morita Bot Source Seal v1

This layer creates a local-only sealed Morita Bot source artifact for Phase 1.6C.

It does not change Morita Bot rules, generate new signals, optimize parameters, infer option outcomes, or create actionization. It only validates an eligible existing source lineage and materializes canonical signal/outcome rows with provenance.

The sealed artifact root is ignored:

`market_bomb_history/morita_bot_source_seal_v1/`

Required completed artifacts include signal events, signal outcomes, rule snapshot, timing contract, input lineage, validation report, receipt, manifest, and summary.

If no eligible candidate exists, the inventory and validation report stay blocked. No partial source artifact is promoted as complete.
