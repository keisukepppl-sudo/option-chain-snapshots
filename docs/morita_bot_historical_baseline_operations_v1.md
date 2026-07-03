# Morita Bot Historical Baseline Operations v1

Run order:

1. Build the authorized tail input with `scripts/fetch_morita_bot_baseline_tail_ohlcv_v1.py`.
2. Run `scripts/build_morita_bot_historical_baseline_v1.py`.
3. Verify the generated baseline run manifest.
4. Seal the baseline using `scripts/build_morita_bot_source_seal_v1.py`.
5. Run Phase 1.6C with the sealed source artifact.

Generated raw inputs, baseline rows, manifests, and receipts are local ignored artifacts and must not be committed.
