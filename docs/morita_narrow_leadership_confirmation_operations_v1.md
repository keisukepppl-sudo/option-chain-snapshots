# Morita Narrow Leadership Confirmation Operations v1

Run:

```powershell
python scripts/build_morita_narrow_leadership_confirmation_v1.py --run --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa --dispersion-output-dir outputs/morita_realized_dispersion_quick_screen --output-dir outputs/morita_narrow_leadership_confirmation
python scripts/build_morita_narrow_leadership_confirmation_v1.py --verify --output-dir outputs/morita_narrow_leadership_confirmation
```

The analysis uses inherited full-sample ex-post tercile states only. It is not a live threshold or predictive rule.
