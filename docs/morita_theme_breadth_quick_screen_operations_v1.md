# Morita Theme Breadth Quick Screen Operations v1

## Run

```powershell
python scripts/build_morita_theme_breadth_quick_screen_v1.py `
  --run `
  --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa `
  --output-dir outputs/morita_theme_breadth_quick_screen
```

## Verify

```powershell
python scripts/build_morita_theme_breadth_quick_screen_v1.py `
  --verify `
  --output-dir outputs/morita_theme_breadth_quick_screen
```

Verification fails if a required output is missing, changed, or if an extra file
exists inside the output directory outside the content manifest.

## Constraints

- No data download or provider access.
- No arbitrary OHLCV override.
- No scanner rerun.
- No baseline rebuild.
- No option PnL, DTE, strike, delta, IV, or slippage analysis.
- No regression, model fitting, parameter optimization, composite score, live
  filter, alert, sizing, exit, or trade recommendation.

## Expected Follow-Up Decision

Use the generated `breadth_summary.md` and ChatGPT bundle to decide whether
theme breadth is worth deeper validation. If relationships are weak,
inconsistent, sparse, or concentration-driven, freeze breadth and move research
attention to VXN/VIX.
