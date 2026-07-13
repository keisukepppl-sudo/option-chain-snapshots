# Reproduction Commands

```powershell
python scripts/run_morita_short_v3_5_2_independent_audit.py `
  --signal-calendar 'C:\Users\keisu\Documents\Codex\2026-07-11\files-mentioned-by-the-user-morita\outputs\morita_current_conditions_sa_signal_calendar_latest.csv' `
  --source-receipt 'C:\Users\keisu\Documents\Codex\2026-07-11\files-mentioned-by-the-user-morita\outputs\morita_current_conditions_sa_rebuild_v1_run_receipt_latest.json' `
  --daily-ohlcv 'C:\Users\keisu\Documents\Codex\2026-06-25\bot-rs-2-1-2-historical\work\option-chain-snapshots-main\outputs\morita_2023_rs_warmup_retest_v1\input\morita_baseline_2022warmup_2023_2026_v1\sources\daily_ohlcv_merged.csv' `
  --m15-bars 'C:\Users\keisu\Documents\Codex\2026-06-25\bot-rs-2-1-2-historical\work\option-chain-snapshots-main\data\intraday\normalized\webull_semis_m15.parquet' `
  --output-dir 'C:\Users\keisu\Documents\Codex\2026-06-25\bot-rs-2-1-2-historical\work\morita_short_v3_5_2_independent_audit_20260714\outputs\research_only\morita_short_v3_5_2_independent_audit\20260713T190155Z'
pytest tests/test_morita_short_v3_5_2_independent_audit.py -q
```
