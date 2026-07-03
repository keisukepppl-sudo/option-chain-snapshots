# Morita Realized Dispersion Quick Screen Operations v1

## Run

```powershell
python scripts/build_morita_realized_dispersion_quick_screen_v1.py `
  --run `
  --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa `
  --output-dir outputs/morita_realized_dispersion_quick_screen
```

## Verify

```powershell
python scripts/build_morita_realized_dispersion_quick_screen_v1.py `
  --verify `
  --output-dir outputs/morita_realized_dispersion_quick_screen
```

## Constraints

- No network, provider, or external intake.
- No arbitrary OHLCV path override.
- No option, skew, VIX, VXN, implied-correlation, or dealer model input.
- No Bot rerun, rule change, optimization, composite score, or actionization.
