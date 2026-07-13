# ChatGPT Review Bundle - Morita First Absorption Reversal v1

## Objective
Test whether former Morita S leaders showing two consecutive absorption days during a still-weak old-S universe can capture the next-day rebound.

## Guardrails
- Research-only.
- No live orders, no Webull connection, no production scanner changes.
- Point-in-time discipline enforced by using only S signals known by each event date and prior/current daily bars.
- Missing news/fundamental evidence fails closed to AMBIGUOUS, not CLEAN.
- Missing option chains block option-performance claims.

## Conclusion
HOLD / NOT ADOPTION READY. The daily underlier harness exists and generated reviewable artifacts, but the adoption gate is blocked by missing sealed PIT fundamental audit data and missing option chains.

## Key Outputs
- `signal_candidates.csv`
- `trade_level_underlying.csv`
- `fundamental_filter_audit.csv`
- `parameter_sensitivity.csv`
- `backtest_report.md`
- `receipt.json`

## Baseline Snapshot
| baseline_level              |   trades |   win_rate |   mean_return |   median_return |   profit_factor |   max_drawdown |   top5_removed_profit_factor |
|:----------------------------|---------:|-----------:|--------------:|----------------:|----------------:|---------------:|-----------------------------:|
| A_ADJUSTMENT_OLD_S_UNIVERSE |       24 |   0.458333 |    0.00436659 |     -0.00177582 |         1.45096 |     -0.0847079 |                     0.377088 |
| B_D0_ONLY                   |        4 |   0        |   -0.0184323  |     -0.016754   |         0       |     -0.0600342 |                   nan        |

## Validation
The run receipt records source hashes, row counts, and safety flags. Targeted tests cover safety flags, fail-closed fundamental handling, and trade summary behavior.

## Limitations
- Candidate-level 5m/15m bars are unavailable; only SOXX intraday exists locally.
- News/fundamental event audit is unavailable, so CLEAN primary analysis has zero rows.
- Historical option chains are unavailable, so options are blocked.
- Daily data starts in 2022 for the local PIT semis panel; COVID case study is unavailable.

## Next Codex Instruction
Acquire or build a sealed point-in-time event audit table with ticker, public timestamp, source, headline/event, and CLEAN/AMBIGUOUS/SHOCK classification made before outcome review. Then rerun this exact harness without changing thresholds, and only after CLEAN underlier PF is acceptable add historical option-chain validation.
