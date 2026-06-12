# Option Chain Snapshot via GitHub Actions

This repository automatically saves option-chain snapshots for:

- QQQ
- SPY
- SOXX
- SMH
- MU
- DRAM

## Files

- `option_snapshot_auto.py`: snapshot script
- `requirements.txt`: Python dependencies
- `.github/workflows/option_snapshot.yml`: GitHub Actions schedule

## Schedule

Default schedule is 06:30 JST on weekdays.

GitHub Actions cron uses UTC, so:

- 06:30 JST = 21:30 UTC previous day

## Manual run

GitHub → Actions → Option Chain Snapshot → Run workflow

## Output

```text
option_chain_snapshots/
  QQQ/
  SPY/
  SOXX/
  SMH/
  MU/
  DRAM/
```
