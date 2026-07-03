# Morita S Risk Profile Operations v1

Run:

```powershell
python scripts/build_morita_s_risk_profile_v1.py --run --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa --output-dir outputs/morita_s_risk_profile
python scripts/build_morita_s_risk_profile_v1.py --verify --output-dir outputs/morita_s_risk_profile
```

The script rejects arbitrary OHLCV, entry, stop, threshold, and provider overrides. All execution-related gap results are daily-open proxies only.
