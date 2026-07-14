# Short Forward Tracking Spec

Status: NOT_ACTIVATED_BY_V3_5_3_GATE
Final decision: REJECT_HISTORICAL_EDGE_CONCENTRATION

Allowed frozen candidates:
- S-only Open: disabled
- S-only 09:45: disabled

Fields to persist if activated:
- signal lineage
- entry eligibility
- entry timestamp
- price source
- D1/D2/D3/D5 outcome
- ticker episode
- market episode
- CAR-like special-event flag
- no-signal heartbeat

Live order status: prohibited.
Threshold optimization: prohibited.

Gate table:
| rank   | entry   | exit   |   market_episode_n | profit_factor_gt_1   | median_gt_0   | leave_one_episode_sign_stable   | top3_not_strategy_dominating   | bootstrap_lower_bound_defensible   | paired_0945_supported   |   profit_factor |       median |   top3_positive_share |   bootstrap_mean_ci_low |   bootstrap_mean_ci_high | gate_status   |
|:-------|:--------|:-------|-------------------:|:---------------------|:--------------|:--------------------------------|:-------------------------------|:-----------------------------------|:------------------------|----------------:|-------------:|----------------------:|------------------------:|-------------------------:|:--------------|
| S      | Open    | D1     |                 29 | True                 | True          | False                           | False                          | False                              |                         |         1.4918  |  0.00183153  |              0.643284 |             -0.00933994 |                0.0248052 | FAIL          |
| S      | 09:45   | D1     |                  4 | True                 | True          | True                            | False                          | True                               | False                   |       inf       |  0.0137892   |              0.94085  |              0.00571953 |                0.0266781 | FAIL          |
| S+A    | Open    | D1     |                 35 | True                 | True          | False                           | False                          | False                              |                         |         1.32541 |  0.00476274  |              0.508153 |             -0.00567887 |                0.0127702 | FAIL          |
| S+A    | 09:45   | D1     |                  4 | True                 | False         | False                           | False                          | False                              | False                   |         2.44457 | -0.000445447 |              1        |             -0.00652204 |                0.0176096 | FAIL          |
