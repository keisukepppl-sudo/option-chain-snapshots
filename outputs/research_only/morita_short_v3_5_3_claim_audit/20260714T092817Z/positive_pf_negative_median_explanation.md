# Positive PF / Negative Median Explanation

Candidate and ticker-episode PF can stay above 1 while the median is negative when a minority positive tail is large enough to offset frequent small losses.

| rank   | level          |   n |   profit_factor |      median |   negative_frequency |   gain_loss_asymmetry |   top_3_positive_share |   expected_shortfall_5pct |
|:-------|:---------------|----:|----------------:|------------:|---------------------:|----------------------:|-----------------------:|--------------------------:|
| S      | candidate      | 307 |         1.78712 | -0.00193877 |             0.517915 |               1.91995 |               0.208643 |                -0.120563  |
| S      | ticker_episode | 216 |         1.09167 | -0.00328582 |             0.532407 |               1.243   |               0.271154 |                -0.0931325 |
| A      | candidate      | 497 |         1.1232  | -0.00151785 |             0.511066 |               1.1789  |               0.122461 |                -0.0969256 |
| A      | ticker_episode | 353 |         1.18385 | -0.00189116 |             0.512748 |               1.25309 |               0.178131 |                -0.0830714 |
| S+A    | candidate      | 804 |         1.42321 | -0.00173641 |             0.513682 |               1.50714 |               0.118388 |                -0.108977  |
| S+A    | ticker_episode | 477 |         1.10018 | -0.00214535 |             0.524109 |               1.21701 |               0.146279 |                -0.0772297 |

Interpretation: this is a skew-dependent profile, not broad independent alpha. It must be stress-tested with concentration exclusions and episode-level gates before any forward tracking claim.
