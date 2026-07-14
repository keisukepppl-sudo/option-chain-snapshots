# Morita Short v3.5.3 Claim Audit Report

Final decision: REJECT_HISTORICAL_EDGE_CONCENTRATION

## 09:45 Paired Sample
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

## Concentration Exclusions
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

## S vs A
| entry   | exit   | level          |   matched_market_episode_n |     s_mean |      a_mean |   s_minus_a_mean |   s_minus_a_median |   s_wins |   a_wins |   ties |   sign_test_p |
|:--------|:-------|:---------------|---------------------------:|-----------:|------------:|-----------------:|-------------------:|---------:|---------:|-------:|--------------:|
| Open    | D1     | candidate      |                         27 | 0.00490112 | 0.000818469 |      0.00408266  |        -0.00170913 |       12 |       15 |      0 |      0.701108 |
| Open    | D1     | ticker_episode |                         27 | 0.00109891 | 0.000214281 |      0.000884625 |         0.0022085  |       15 |       12 |      0 |      0.701108 |
| Open    | D1     | market_episode |                         27 | 0.00490112 | 0.000818469 |      0.00408266  |        -0.00170913 |       12 |       15 |      0 |      0.701108 |

## Independent Episode Gate
| rank   | entry   | exit   |   market_episode_n | profit_factor_gt_1   | median_gt_0   | leave_one_episode_sign_stable   | top3_not_strategy_dominating   | bootstrap_lower_bound_defensible   | paired_0945_supported   |   profit_factor |       median |   top3_positive_share |   bootstrap_mean_ci_low |   bootstrap_mean_ci_high | gate_status   |
|:-------|:--------|:-------|-------------------:|:---------------------|:--------------|:--------------------------------|:-------------------------------|:-----------------------------------|:------------------------|----------------:|-------------:|----------------------:|------------------------:|-------------------------:|:--------------|
| S      | Open    | D1     |                 29 | True                 | True          | False                           | False                          | False                              |                         |         1.4918  |  0.00183153  |              0.643284 |             -0.00933994 |                0.0248052 | FAIL          |
| S      | 09:45   | D1     |                  4 | True                 | True          | True                            | False                          | True                               | False                   |       inf       |  0.0137892   |              0.94085  |              0.00571953 |                0.0266781 | FAIL          |
| S+A    | Open    | D1     |                 35 | True                 | True          | False                           | False                          | False                              |                         |         1.32541 |  0.00476274  |              0.508153 |             -0.00567887 |                0.0127702 | FAIL          |
| S+A    | 09:45   | D1     |                  4 | True                 | False         | False                           | False                          | False                              | False                   |         2.44457 | -0.000445447 |              1        |             -0.00652204 |                0.0176096 | FAIL          |

## Safety
research_only=true; execution_allowed=false; live_order_allowed=false. No production scanner, broker, account, order, rank, threshold, or event-definition changes.
