# Morita First Absorption Reversal v1

This is a research-only harness for testing whether former Morita S leaders that absorb selling for two consecutive sessions during a still-weak old-S universe produce a next-session rebound.

The implementation is isolated under `src/morita_first_absorption_reversal_v1` with standalone scripts. It does not modify scanner, notification, Webull, broker, or production execution code.

Primary adoption is intentionally fail-closed:

- Missing sealed point-in-time news/fundamental event evidence leaves candidates as `AMBIGUOUS`, not `CLEAN`.
- Missing historical option chains blocks option-performance claims.
- Intraday candidate bars are required before promoting proxy entry timings such as D1 90 minutes after open.

Run:

```powershell
python scripts/run_morita_first_absorption_reversal_backtest_v1.py
```

Outputs are written to `outputs/morita_first_absorption_reversal_v1/`.

