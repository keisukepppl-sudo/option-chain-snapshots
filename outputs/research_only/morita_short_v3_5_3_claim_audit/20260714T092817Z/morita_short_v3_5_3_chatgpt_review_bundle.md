INPUT:
v3.5.2 decisions treated as hypotheses = 0945_ADVANTAGE_REPLICATED; S_OUTPERFORMS_A_ROBUSTLY
primary retained decision = NO_INDEPENDENT_EPISODE_ALPHA_CONFIRMED

KEY RESULT:
S Open gate = FAIL
S 09:45 gate = FAIL
final decision = REJECT_HISTORICAL_EDGE_CONCENTRATION

DECISION:
REJECT_HISTORICAL_EDGE_CONCENTRATION

# Executive conclusion
The concentration falsification audit does not support promoting the historical edge. The prior 09:45 and S>A labels should remain hypotheses, not adopted conclusions.

# 09:45 paired result
| rank   | level            |   paired_n |   mean_difference |   median_difference |   open_pf |   entry_pf |   sign_test_p |
|:-------|:-----------------|-----------:|------------------:|--------------------:|----------:|-----------:|--------------:|
| S      | candidate        |         16 |      -0.00651653  |         -0.00505829 |   2.5923  |   2.32189  |      0.210114 |
| S      | ticker_episode   |         14 |      -0.00636714  |         -0.00897448 |   2.89071 |   2.73449  |      0.42395  |
| S      | market_episode   |          4 |      -0.0510062   |         -0.0194078  |  48.162   | inf        |      0.625    |
| S      | weakest_selected |          4 |      -0.0172209   |         -0.00811395 |   8.87686 |   1.06799  |      1        |
| A      | candidate        |         41 |       0.00275518  |          0.00557844 |   1.06514 |   1.27244  |      0.755229 |
| A      | ticker_episode   |         27 |       0.00135494  |         -0.0012792  |   1.12817 |   1.24966  |      1        |
| A      | market_episode   |          4 |      -0.0109409   |         -0.0100842  |   3.32515 |   0.893581 |      0.625    |
| A      | weakest_selected |          4 |       0.0313071   |          0.0360724  |   0.13804 |  20.0584   |      0.125    |
| S+A    | candidate        |         57 |       0.000152597 |         -0.0012792  |   1.37391 |   1.47679  |      0.791366 |
| S+A    | ticker_episode   |         32 |      -0.0024357   |         -0.00337417 |   1.51403 |   1.32282  |      0.596615 |
| S+A    | market_episode   |          4 |      -0.0327917   |         -0.0114279  |  11.451   |   2.44457  |      0.625    |
| S+A    | weakest_selected |          4 |       0.0179867   |          0.0360724  |   0.13804 |   1.53978  |      0.625    |

# Concentration risk
| scenario                               |   n |   profit_factor |      median |   market_episode_count |
|:---------------------------------------|----:|----------------:|------------:|-----------------------:|
| baseline                               |  35 |        1.32541  |  0.00476274 |                     35 |
| exclude CAR                            |  35 |        0.870352 |  0.00392562 |                     35 |
| exclude TE5_CAR_0002                   |  35 |        0.906305 |  0.00392562 |                     35 |
| exclude ME_0034                        |  34 |        0.921366 |  0.00434418 |                     34 |
| exclude CAR + ME_0034                  |  34 |        0.884232 |  0.00434418 |                     34 |
| exclude top 1 positive market episode  |  34 |        0.921366 |  0.00434418 |                     34 |
| exclude top 3 positive market episodes |  32 |        0.651901 |  0.00210632 |                     32 |
| exclude top 5 positive market episodes |  30 |        0.522827 | -0.00189314 |                     30 |

# CAR / ME_0034 forensic
| subject   | date_range             | tickers                                                                                                                              | rank_composition   |   candidate_count |   pnl_contribution | data_coverage                                              | duplicate_overlap           | market_shock                                                         | news_regime                                 | classification                                  | corporate_action   | bankruptcy_distress   | data_error                        | split        | price_adjustment_issue                                                                                                    | extreme_gap   | repeated_overlapping_signals   | same_economic_episode_duplication   |
|:----------|:-----------------------|:-------------------------------------------------------------------------------------------------------------------------------------|:-------------------|------------------:|-------------------:|:-----------------------------------------------------------|:----------------------------|:---------------------------------------------------------------------|:--------------------------------------------|:------------------------------------------------|:-------------------|:----------------------|:----------------------------------|:-------------|:--------------------------------------------------------------------------------------------------------------------------|:--------------|:-------------------------------|:------------------------------------|
| CAR       | 2025-06-27..2026-04-22 | CAR                                                                                                                                  | A:4|S:11           |                15 |            7.73536 | daily_open_close_available; local source basis unspecified | repeated ticker signals     |                                                                      | not externally verified in this local audit | SPECIAL_TICKER_CONCENTRATION_DO_NOT_GENERALIZE  | not verified       | not verified          | not detected by null/return audit | not verified | basis=local_cached_existing_history_basis_unspecified|raw_unadjusted_provider_tail|yahoo_2022_rs_warmup_auto_adjust_false | False         | True                           | True                                |
| ME_0034   | 2026-04-15..2026-06-08 | AA|ALAB|ALB|AMD|AMKR|ASTS|CAR|COHR|DELL|ECG|FLEX|GEV|GFS|GLW|HPE|INTC|IRDM|LITE|LRCX|MKSI|MRVL|MTSI|MTZ|MU|ON|RKLB|RVMD|SNDK|TER|WDC | A:33|S:32          |                65 |            7.29058 | daily_open_close_available; M15_subset_only                | same_market_episode_cluster | calendar-proximity market episode; QQQ context in market_episode_map | not externally verified in this local audit | SPECIAL_CONCENTRATION_EPISODE_DO_NOT_GENERALIZE |                    |                       |                                   |              | basis_unspecified_source                                                                                                  |               | True                           | True                                |

# S vs A result
| weighting        | rank   |   n |   profit_factor |      median |   market_episode_count |
|:-----------------|:-------|----:|----------------:|------------:|-----------------------:|
| candidate        | S      | 307 |        1.78712  | -0.00193877 |                     29 |
| candidate        | A      | 497 |        1.1232   | -0.00151785 |                     33 |
| ticker_episode   | S      | 216 |        1.09167  | -0.00328582 |                     29 |
| ticker_episode   | A      | 353 |        1.18385  | -0.00189116 |                     33 |
| market_episode   | S      |  29 |        1.4918   |  0.00183153 |                     29 |
| market_episode   | A      |  33 |        1.00656  |  0.00611067 |                     33 |
| weakest_selected | S      |  29 |        1.62368  |  0.00939781 |                     29 |
| weakest_selected | A      |  33 |        0.545336 | -0.00785019 |                     33 |

# Negative median / positive PF
| rank   | level          |   n |   profit_factor |      median |   negative_frequency |   gain_loss_asymmetry |   top_3_positive_share |
|:-------|:---------------|----:|----------------:|------------:|---------------------:|----------------------:|-----------------------:|
| S      | candidate      | 307 |         1.78712 | -0.00193877 |             0.517915 |              1.91995  |               0.208643 |
| S      | ticker_episode | 216 |         1.09167 | -0.00328582 |             0.532407 |              1.243    |               0.271154 |
| S      | market_episode |  29 |         1.4918  |  0.00183153 |             0.482759 |              1.39235  |               0.643284 |
| A      | candidate      | 497 |         1.1232  | -0.00151785 |             0.511066 |              1.1789   |               0.122461 |
| A      | ticker_episode | 353 |         1.18385 | -0.00189116 |             0.512748 |              1.25309  |               0.178131 |
| A      | market_episode |  33 |         1.00656 |  0.00611067 |             0.393939 |              0.654265 |               0.341433 |
| S+A    | candidate      | 804 |         1.42321 | -0.00173641 |             0.513682 |              1.50714  |               0.118388 |
| S+A    | ticker_episode | 477 |         1.10018 | -0.00214535 |             0.524109 |              1.21701  |               0.146279 |
| S+A    | market_episode |  35 |         1.32541 |  0.00476274 |             0.428571 |              0.99406  |               0.508153 |

# Independent episode alpha gate
| rank   | entry   | exit   |   market_episode_n | profit_factor_gt_1   | median_gt_0   | leave_one_episode_sign_stable   | top3_not_strategy_dominating   | bootstrap_lower_bound_defensible   | paired_0945_supported   |   profit_factor |       median |   top3_positive_share |   bootstrap_mean_ci_low |   bootstrap_mean_ci_high | gate_status   |
|:-------|:--------|:-------|-------------------:|:---------------------|:--------------|:--------------------------------|:-------------------------------|:-----------------------------------|:------------------------|----------------:|-------------:|----------------------:|------------------------:|-------------------------:|:--------------|
| S      | Open    | D1     |                 29 | True                 | True          | False                           | False                          | False                              |                         |         1.4918  |  0.00183153  |              0.643284 |             -0.00933994 |                0.0248052 | FAIL          |
| S      | 09:45   | D1     |                  4 | True                 | True          | True                            | False                          | True                               | False                   |       inf       |  0.0137892   |              0.94085  |              0.00571953 |                0.0266781 | FAIL          |
| S+A    | Open    | D1     |                 35 | True                 | True          | False                           | False                          | False                              |                         |         1.32541 |  0.00476274  |              0.508153 |             -0.00567887 |                0.0127702 | FAIL          |
| S+A    | 09:45   | D1     |                  4 | True                 | False         | False                           | False                          | False                              | False                   |         2.44457 | -0.000445447 |              1        |             -0.00652204 |                0.0176096 | FAIL          |

# Forward tracking
No live order route is enabled. Forward tracking is not activated unless the gate status explicitly passes.

# Exact next step
Keep this as research-only evidence. Do not generalize CAR or ME_0034-dominated historical performance into production readiness.
