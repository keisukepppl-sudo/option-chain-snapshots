# ChatGPT Handoff: Morita Narrow Leadership 2023 Replication

## Objective

Replicate the completed narrow-leadership 2x2 analysis on 2023 decision dates using frozen 2024-2026 state thresholds and the existing Morita formal baseline lineage.

## Result

- Status: `morita_narrow_leadership_2023_replication_completed`
- Label: `no_2023_s_signals_available_for_2x2_replication`
- Research decision: `cannot_confirm_or_refute_2024_2026_pattern_from_2023`
- Output directory: `outputs/morita_narrow_leadership_2023_replication`

## Guardrails

- Frozen thresholds only; no retuning.
- Existing local baseline/input artifacts only; no new market data download.
- No option P&L, no notification, no strategy/actionization change.

## Embedded Summary

# Morita Narrow Leadership 2023 Frozen-Threshold Replication v1

Status: `morita_narrow_leadership_2023_replication_completed`
Replication label: `no_2023_s_signals_available_for_2x2_replication`
Research decision: `cannot_confirm_or_refute_2024_2026_pattern_from_2023`

## Bottom Line

- 2023 eligible S complete signal count: `0`.
- The frozen 2024-2026 dispersion/leadership high cutoffs were inherited unchanged.
- No retuning, no option P&L, no live bot change, and no actionization were performed.

## Historical Coverage
| bucket | count | notes |
| --- | --- | --- |
| decision_dates_in_2023_window | 126 | formal baseline rejected audit plus signal dates |
| signal_rows_in_2023_window | 0 | formal baseline panel |
| s_signal_rows_in_2023_window | 0 | rank S only |
| complete_s_signal_rows_in_2023_window | 0 | eligible before state join |
| rejected_no_breakout_prefilter_candidate | 126 | formal baseline rejected audit |

## RS Warmup Diagnostic

The 2023 zero-signal result is driven by missing 252-session RS warmup history in the current input, not by an absence of breakout/volume candidates. The current production-style prefilter requires RS98 before scanner selection.

| metric | value |
| --- | --- |
| 2023_dates_with_any_rs_value | 0 |
| 2023_breakout_volume_candidate_rows_before_rs | 3712 |
| 2023_breakout_volume_rs98_candidate_rows | 0 |

## 2023 State Coverage
| metric | state | decision_date_count |
| --- | --- | --- |
| broad_russell1000_cross_sectional_dispersion_20d | low | 88 |
| broad_russell1000_cross_sectional_dispersion_20d | middle | 20 |
| broad_russell1000_cross_sectional_dispersion_20d | high | 18 |
| broad_russell1000_cross_sectional_dispersion_20d | metric_unavailable | 0 |
| broad_russell1000_qqq_minus_eqw_return_20d | low | 39 |
| broad_russell1000_qqq_minus_eqw_return_20d | middle | 51 |
| broad_russell1000_qqq_minus_eqw_return_20d | high | 36 |
| broad_russell1000_qqq_minus_eqw_return_20d | metric_unavailable | 0 |
| D_L_2x2_cell | B | 18 |
| D_L_2x2_cell | C | 36 |
| D_L_2x2_cell | D | 72 |

## 2023 S 2x2 Outcome Summary
| cell | cell_description | complete_signal_count | plus5_success_rate | breakout_low_breach_rate | timeout_rate | largest_single_ticker_share | top_five_ticker_share | unique_ticker_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | D_high_and_L_high | 0 |  |  |  |  |  | 0 |
| B | D_high_and_L_not_high | 0 |  |  |  |  |  | 0 |
| C | D_not_high_and_L_high | 0 |  |  |  |  |  | 0 |
| D | D_not_high_and_L_not_high | 0 |  |  |  |  |  | 0 |

## Required Comparisons
| scope | comparison | left_side | right_side | left_complete_signal_count | right_complete_signal_count | plus5_difference_pp | breach_difference_pp | timeout_difference_pp | directionally_adverse | comparison_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023_replication | A_vs_B | A | B | 0 | 0 |  |  |  | False | insufficient_sample |
| 2023_replication | A_vs_C | A | C | 0 | 0 |  |  |  | False | insufficient_sample |
| 2023_replication | A_vs_D | A | D | 0 | 0 |  |  |  | False | insufficient_sample |
| 2023_replication | A_vs_pooled_BCD | A | pooled_BCD | 0 | 0 |  |  |  | False | insufficient_sample |
| 2023_replication | C_vs_D | C | D | 0 | 0 |  |  |  | False | insufficient_sample |
| 2023_replication | B_vs_D | B | D | 0 | 0 |  |  |  | False | insufficient_sample |

## 2023 vs 2024-2026
| cell | metric | replication_2023 | prior_2024_2026_confirmation | comparison_status |
| --- | --- | --- | --- | --- |
| A | complete_signal_count | 0.000000 | 52.000000 | insufficient_2023_sample |
| A | plus5_success_rate |  | 0.423077 | insufficient_2023_sample |
| A | breakout_low_breach_rate |  | 0.557692 | insufficient_2023_sample |
| A | timeout_rate |  | 0.019231 | insufficient_2023_sample |
| B | complete_signal_count | 0.000000 | 77.000000 | insufficient_2023_sample |
| B | plus5_success_rate |  | 0.571429 | insufficient_2023_sample |
| B | breakout_low_breach_rate |  | 0.389610 | insufficient_2023_sample |
| B | timeout_rate |  | 0.038961 | insufficient_2023_sample |
| C | complete_signal_count | 0.000000 | 50.000000 | insufficient_2023_sample |
| C | plus5_success_rate |  | 0.680000 | insufficient_2023_sample |
| C | breakout_low_breach_rate |  | 0.280000 | insufficient_2023_sample |
| C | timeout_rate |  | 0.040000 | insufficient_2023_sample |
| D | complete_signal_count | 0.000000 | 129.000000 | insufficient_2023_sample |
| D | plus5_success_rate |  | 0.635659 | insufficient_2023_sample |
| D | breakout_low_breach_rate |  | 0.325581 | insufficient_2023_sample |
| D | timeout_rate |  | 0.038760 | insufficient_2023_sample |
