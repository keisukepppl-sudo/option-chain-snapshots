# Morita Short v3.5.2 Independent Audit Report

Run ID: 20260713T190155Z
Output directory: C:\Users\keisu\Documents\Codex\2026-06-25\bot-rs-2-1-2-historical\work\morita_short_v3_5_2_independent_audit_20260714\outputs\research_only\morita_short_v3_5_2_independent_audit\20260713T190155Z
Input reconciled: True
Decision: 0945_ADVANTAGE_REPLICATED, S_OUTPERFORMS_A_ROBUSTLY, NO_INDEPENDENT_EPISODE_ALPHA_CONFIRMED

## Counts
| metric                               |   value |
|:-------------------------------------|--------:|
| raw signal rows                      |     813 |
| constructed candidates               |     804 |
| unique ticker-date                   |     525 |
| unique ticker episodes               |     477 |
| unique market episodes               |      35 |
| median candidates per market episode |      16 |
| max candidates per market episode    |      85 |

## Primary Open D1 Matrix
| rank   | level            |   n |   profit_factor |      median |   top_3_contribution_share |
|:-------|:-----------------|----:|----------------:|------------:|---------------------------:|
| S      | candidate        | 307 |        1.78712  | -0.00193877 |                   0.208643 |
| A      | candidate        | 497 |        1.1232   | -0.00151785 |                   0.122461 |
| S+A    | candidate        | 804 |        1.42321  | -0.00173641 |                   0.118388 |
| S      | ticker_episode   | 216 |        1.09167  | -0.00328582 |                   0.271154 |
| A      | ticker_episode   | 353 |        1.18385  | -0.00189116 |                   0.178131 |
| S+A    | ticker_episode   | 477 |        1.10018  | -0.00214535 |                   0.146279 |
| S      | market_episode   |  29 |        1.4918   |  0.00183153 |                   0.643284 |
| A      | market_episode   |  33 |        1.00656  |  0.00611067 |                   0.341433 |
| S+A    | market_episode   |  35 |        1.32541  |  0.00476274 |                   0.508153 |
| S      | weakest_selected |  29 |        1.62368  |  0.00939781 |                   0.392188 |
| A      | weakest_selected |  33 |        0.545336 | -0.00785019 |                   0.680273 |
| S+A    | weakest_selected |  35 |        0.80459  | -0.00279014 |                   0.539405 |

## Concentration
| concentration_axis   |   group_count |   top_1_share_of_positive_pnl |   top_3_share_of_positive_pnl |   top_5_share_of_positive_pnl | largest_positive_group   |   largest_positive_group_return_sum |
|:---------------------|--------------:|------------------------------:|------------------------------:|------------------------------:|:-------------------------|------------------------------------:|
| ticker               |           143 |                      0.610736 |                      0.70882  |                      0.754563 | CAR                      |                             7.73536 |
| ticker_episode       |           477 |                      0.414149 |                      0.45625  |                      0.489533 | TE5_CAR_0002             |                             7.5443  |
| market_episode       |            35 |                      0.647075 |                      0.787635 |                      0.874353 | ME_0034                  |                             7.29058 |

## Safety
research_only=true; execution_allowed=false; live_order_allowed=false; broker/account/order paths were not used.
