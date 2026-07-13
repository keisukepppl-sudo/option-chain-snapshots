# Morita First Absorption Reversal v1 Backtest

## Conclusion

Decision: **HOLD / NOT ADOPTION READY**.

This run produced a daily underlying research backtest, but it did not produce an adoption-ready CLEAN strategy. The local repo has PIT-ish daily OHLCV and formal S history, but it does not have a sealed point-in-time news/fundamental audit source for these events and does not have historical option chains for the candidate trades. Therefore all detected candidates remain AMBIGUOUS for the fundamental filter, the primary CLEAN F/G analysis is empty, and option results are blocked rather than simulated as performance.

## Headline Counts

- S signal rows loaded: 381
- Daily price rows loaded: 4507
- Recent-S membership rows: 3453
- Candidate rows: 24
- Primary E rows before CLEAN filter: 0
- CLEAN primary rows: 0
- Option performance rows usable: 0

## Baseline Summary

| baseline_level              |   trades |   win_rate |   mean_return |   median_return |   profit_factor |   max_drawdown |   top5_removed_profit_factor |
|:----------------------------|---------:|-----------:|--------------:|----------------:|----------------:|---------------:|-----------------------------:|
| A_ADJUSTMENT_OLD_S_UNIVERSE |       24 |   0.458333 |    0.00436659 |     -0.00177582 |         1.45096 |     -0.0847079 |                     0.377088 |
| B_D0_ONLY                   |        4 |   0        |   -0.0184323  |     -0.016754   |         0       |     -0.0600342 |                   nan        |

## Data Quality

- Daily source: `data/pit/daily/core_semis_daily.parquet`
- Intraday source: `data/pit/intraday/core_semis_m15.parquet`; candidate-level intraday bars are unavailable, so D1 90m/final-60m entries are proxy-only and not used as verified intraday results.
- Fundamental event source: not found; AMBIGUOUS fail-closed classification.
- Option chain source: not found; option layer blocked.

## Answers To Required Review Questions

1. MKSI/AMAT-type detection: evaluated as case-study candidates where data exists, but not eligible for CLEAN confirmation without sealed PIT news audit.
2. Best entry timing: not adoption-grade; daily-only comparison is in `trade_level_underlying.csv`.
3. Best D2 exit timing: not adoption-grade; D2 open/close and D3 variants are tabulated.
4. Two-day absorption vs one-day: compare Baseline B and C in `parameter_sensitivity.csv` and summaries.
5. Old-S universe still weak condition: compare C and D.
6. Universe downside deceleration: compare D and E.
7. Sell efficiency vs volume decline: only daily sell-efficiency proxy is available.
8. Degross regime: price-only classification is provided, but fundamental confirmation is unavailable.
9. Tariff CLEAN classification: blocked without PIT news audit.
10. DeepSeek / earnings-shock cases: cannot be reliably separated without sealed event data.
11. Fakeout after D2: D2 and D3 exits are included for review.
12. Underlying vs call: underlying only is usable; call layer is blocked.
13. ATM/ITM/DTE stability: blocked by missing option chains.
14. IV crush effect: not estimated as performance.
15. Short-bot exit use: possible research input only, not wired to production.
16. Buy-the-dip vs call entry: should remain separate until CLEAN and options evidence exist.
17. Minimum live rule: no live rule recommended from this run.
