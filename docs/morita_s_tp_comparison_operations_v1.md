# Morita S TP Comparison Operations v1

Run:

```powershell
python scripts/build_morita_s_tp_comparison_v1.py `
  --run `
  --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa `
  --output-dir outputs/morita_s_tp_comparison
```

Verify:

```powershell
python scripts/build_morita_s_tp_comparison_v1.py `
  --verify `
  --output-dir outputs/morita_s_tp_comparison
```

The command rejects fixed-spec overrides for DTE, delta, strike, IV, cost, target, split, hold, and rank. It must not download new market data, emit live alerts, change stops, or create trading instructions.

When the canonical single-call path engine is later committed, connect it behind the same entry denominator and independent terminal contract. Do not infer TP100 vs TP125 from the legacy 2026-06-17 `call_backtest` outputs.
