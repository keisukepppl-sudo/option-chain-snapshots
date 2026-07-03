# Morita Put-Skew Quick Screen Operations v1

## Inspect Local Snapshot Archive

```powershell
python scripts/build_morita_put_skew_quick_screen_v1.py `
  --inspect-local-snapshot-archive
```

## Run

```powershell
python scripts/build_morita_put_skew_quick_screen_v1.py `
  --run `
  --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa `
  --output-dir outputs/morita_put_skew_quick_screen
```

## Verify

```powershell
python scripts/build_morita_put_skew_quick_screen_v1.py `
  --verify `
  --output-dir outputs/morita_put_skew_quick_screen
```

## Hard Boundaries

- No external options data.
- No provider, broker, or web API.
- No arbitrary option-file or OHLCV override.
- No DTE, moneyness, lag, cutoff, or threshold override.
- No option PnL, dealer model, Bot rule change, optimization, or actionization.
