# Morita S Single-Call Reference Operations v1

Run the reference engine:

```powershell
python scripts/build_morita_s_single_call_reference_v1.py `
  --run `
  --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa `
  --output-dir outputs/morita_s_single_call_reference_v1
```

Run the TP comparison:

```powershell
python scripts/build_morita_s_tp_comparison_v2.py `
  --run `
  --reference-model-output-dir outputs/morita_s_single_call_reference_v1 `
  --output-dir outputs/morita_s_tp_comparison_v2
```

Verify both manifests:

```powershell
python scripts/build_morita_s_single_call_reference_v1.py --verify --output-dir outputs/morita_s_single_call_reference_v1
python scripts/build_morita_s_tp_comparison_v2.py --verify --output-dir outputs/morita_s_tp_comparison_v2
```

Do not pass parameter overrides. DTE, delta, IV, costs, targets, staged split, progress rule, max hold, rank, and OHLCV lineage are frozen.
