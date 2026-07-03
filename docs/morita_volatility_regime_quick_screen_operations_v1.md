# Morita Volatility-Regime Quick Screen Operations v1

## Fetch Authorized VXN

```powershell
python scripts/fetch_morita_vxn_history_v1.py `
  --start-date 2023-06-01 `
  --end-date 2026-07-02 `
  --output-dir market_bomb_history/morita_volatility_regime_v1/input
```

The fetcher has no symbol override. It rejects date ranges outside the
authorized `2023-06-01` to `2026-07-02` window.

## Run

```powershell
python scripts/build_morita_volatility_regime_quick_screen_v1.py `
  --run `
  --baseline-run-dir market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa `
  --vxn-input-dir market_bomb_history/morita_volatility_regime_v1/input `
  --output-dir outputs/morita_volatility_regime_quick_screen
```

## Verify

```powershell
python scripts/build_morita_volatility_regime_quick_screen_v1.py `
  --verify `
  --output-dir outputs/morita_volatility_regime_quick_screen
```

Verification fails if a required output is missing, changed, or if an extra file
exists inside the output directory outside the content manifest.

## Constraints

- Only `^VXN` external history is authorized.
- No VIX, option chains, skew, fundamentals, news, taxonomy data, or new Bot
  data.
- Theme/QQQ OHLCV must be located through baseline lineage only.
- No Bot rerun, option analysis, optimization, actionization, or live filter.
