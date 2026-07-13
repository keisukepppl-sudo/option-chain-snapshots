INPUT:
S = 309
A = 504
S+A = 813
base candidates = 1147
reconciled = yes

INDEPENDENT COUNTS:
candidate n = 804.0
ticker episode n = 477.0
market episode n = 35.0

KEY RESULT:
best entry = Open D1 daily proxy
candidate PF = 1.42321
ticker-episode PF = 1.10018
market-episode PF = 1.32541
median = 0.00476274
top 3 episode contribution = 0.787635

DECISION:
0945_ADVANTAGE_REPLICATED, S_OUTPERFORMS_A_ROBUSTLY, NO_INDEPENDENT_EPISODE_ALPHA_CONFIRMED

# Executive conclusion
This audit is research-only. The S/A input count gate reconciled, and D0/D1 daily construction was completed where data allowed. Full-population 09:45/10:00/10:30 validation is not formal because real M15 coverage is limited to a small 2026 semiconductor subset.

# Input provenance
| metric          | expected   | actual     | status   |
|:----------------|:-----------|:-----------|:---------|
| S               | 309        | 309        | PASS     |
| A               | 504        | 504        | PASS     |
| S+A             | 813        | 813        | PASS     |
| base_candidates | 1147       | 1147       | PASS     |
| min_signal_date | 2023-01-04 | 2023-01-04 | PASS     |
| max_signal_date | 2026-07-02 | 2026-07-02 | PASS     |

# PIT / timestamp audit
No synthetic intraday bars were created. Missing M15 entries remain missing. Open uses daily open; 09:45/10:00/10:30 use only actual M15 bar-start opens.

# Rank x entry x exit table
| rank   | entry   | exit   | level            |   n |   profit_factor |       median |   top_3_contribution_share |
|:-------|:--------|:-------|:-----------------|----:|----------------:|-------------:|---------------------------:|
| S      | Open    | D1     | candidate        | 307 |        1.78712  | -0.00193877  |                  0.208643  |
| S      | Open    | D2     | candidate        | 306 |        1.76162  | -0.00515325  |                  0.183315  |
| S      | Open    | D3     | candidate        | 305 |        1.66081  | -0.0109927   |                  0.191491  |
| S      | Open    | D5     | candidate        | 305 |        1.4151   | -0.0158322   |                  0.16876   |
| S      | 09:45   | D1     | candidate        |  16 |        2.32189  |  0.00779357  |                  0.621262  |
| S      | 09:45   | D2     | candidate        |  16 |        2.14196  | -0.000490338 |                  0.862086  |
| S      | 09:45   | D3     | candidate        |  15 |        0.523126 | -0.0261102   |                  1         |
| S      | 09:45   | D5     | candidate        |  15 |        0.773478 | -0.0561798   |                  0.889504  |
| S      | 10:00   | D1     | candidate        |  16 |        2.25164  |  0.010462    |                  0.611046  |
| S      | 10:00   | D2     | candidate        |  16 |        1.9659   | -0.00340962  |                  0.864054  |
| S      | 10:00   | D3     | candidate        |  15 |        0.49418  | -0.0256815   |                  0.948633  |
| S      | 10:00   | D5     | candidate        |  15 |        0.722628 | -0.0386751   |                  0.939398  |
| S      | 10:30   | D1     | candidate        |  16 |        1.45649  |  0.00128735  |                  0.720238  |
| S      | 10:30   | D2     | candidate        |  16 |        1.5326   | -0.0147512   |                  0.858033  |
| S      | 10:30   | D3     | candidate        |  15 |        0.452966 | -0.037708    |                  0.936791  |
| S      | 10:30   | D5     | candidate        |  15 |        0.659169 | -0.037838    |                  0.951387  |
| A      | Open    | D1     | candidate        | 497 |        1.1232   | -0.00151785  |                  0.122461  |
| A      | Open    | D2     | candidate        | 492 |        0.897998 | -0.00844917  |                  0.16125   |
| A      | Open    | D3     | candidate        | 491 |        0.900397 | -0.0117681   |                  0.158222  |
| A      | Open    | D5     | candidate        | 489 |        0.861076 | -0.00663913  |                  0.168356  |
| A      | 09:45   | D1     | candidate        |  41 |        1.27244  | -0.00443026  |                  0.375555  |
| A      | 09:45   | D2     | candidate        |  37 |        0.49789  | -0.0194178   |                  0.798582  |
| A      | 09:45   | D3     | candidate        |  36 |        0.455212 | -0.0292554   |                  0.564929  |
| A      | 09:45   | D5     | candidate        |  34 |        0.470101 | -0.0369957   |                  0.423195  |
| A      | 10:00   | D1     | candidate        |  41 |        1.0255   | -0.00239388  |                  0.399258  |
| A      | 10:00   | D2     | candidate        |  37 |        0.429421 | -0.0298072   |                  0.801212  |
| A      | 10:00   | D3     | candidate        |  36 |        0.413114 | -0.0423481   |                  0.574181  |
| A      | 10:00   | D5     | candidate        |  34 |        0.42478  | -0.0508028   |                  0.417628  |
| A      | 10:30   | D1     | candidate        |  41 |        0.811697 | -9.57579e-05 |                  0.343043  |
| A      | 10:30   | D2     | candidate        |  37 |        0.486567 | -0.0319762   |                  0.663459  |
| A      | 10:30   | D3     | candidate        |  36 |        0.491109 | -0.0385924   |                  0.566009  |
| A      | 10:30   | D5     | candidate        |  34 |        0.493698 | -0.0413108   |                  0.3605    |
| S+A    | Open    | D1     | candidate        | 804 |        1.42321  | -0.00173641  |                  0.118388  |
| S+A    | Open    | D2     | candidate        | 798 |        1.27053  | -0.00781415  |                  0.109639  |
| S+A    | Open    | D3     | candidate        | 796 |        1.23726  | -0.0117681   |                  0.113871  |
| S+A    | Open    | D5     | candidate        | 794 |        1.12055  | -0.0106185   |                  0.0998144 |
| S+A    | 09:45   | D1     | candidate        |  57 |        1.47679  | -0.00443026  |                  0.278992  |
| S+A    | 09:45   | D2     | candidate        |  53 |        0.821617 | -0.00739686  |                  0.576338  |
| S+A    | 09:45   | D3     | candidate        |  51 |        0.476718 | -0.0262073   |                  0.46444   |
| S+A    | 09:45   | D5     | candidate        |  49 |        0.554703 | -0.0395065   |                  0.366637  |
| S+A    | 10:00   | D1     | candidate        |  57 |        1.22439  | -0.000832759 |                  0.282397  |
| S+A    | 10:00   | D2     | candidate        |  53 |        0.729046 | -0.012878    |                  0.568595  |
| S+A    | 10:00   | D3     | candidate        |  51 |        0.438023 | -0.0399661   |                  0.441314  |
| S+A    | 10:00   | D5     | candidate        |  49 |        0.504694 | -0.0446052   |                  0.379955  |
| S+A    | 10:30   | D1     | candidate        |  57 |        0.916846 | -9.57579e-05 |                  0.254175  |
| S+A    | 10:30   | D2     | candidate        |  53 |        0.722922 | -0.0265266   |                  0.502592  |
| S+A    | 10:30   | D3     | candidate        |  51 |        0.478664 | -0.037708    |                  0.424616  |
| S+A    | 10:30   | D5     | candidate        |  49 |        0.539051 | -0.037838    |                  0.336417  |
| S      | Open    | D1     | ticker_episode   | 216 |        1.09167  | -0.00328582  |                  0.271154  |
| S      | Open    | D2     | ticker_episode   | 215 |        1.12631  | -0.00770262  |                  0.277033  |
| S      | Open    | D3     | ticker_episode   | 214 |        1.08967  | -0.0102673   |                  0.290322  |
| S      | Open    | D5     | ticker_episode   | 214 |        0.939132 | -0.0156596   |                  0.232056  |
| S      | 09:45   | D1     | ticker_episode   |  14 |        2.73449  |  0.00779357  |                  0.655451  |
| S      | 09:45   | D2     | ticker_episode   |  14 |        2.10827  | -0.000490338 |                  0.895731  |
| S      | 09:45   | D3     | ticker_episode   |  13 |        0.443494 | -0.0261102   |                  1         |
| S      | 09:45   | D5     | ticker_episode   |  13 |        0.690636 | -0.0561798   |                  0.890763  |
| S      | 10:00   | D1     | ticker_episode   |  14 |        2.78693  |  0.00864916  |                  0.687817  |
| S      | 10:00   | D2     | ticker_episode   |  14 |        1.87555  | -0.00861579  |                  0.886198  |
| S      | 10:00   | D3     | ticker_episode   |  13 |        0.399141 | -0.0189758   |                  0.926668  |
| S      | 10:00   | D5     | ticker_episode   |  13 |        0.620546 | -0.0386751   |                  0.940851  |
| S      | 10:30   | D1     | ticker_episode   |  14 |        1.36603  |  0.00128735  |                  0.754303  |
| S      | 10:30   | D2     | ticker_episode   |  14 |        1.38394  | -0.0172709   |                  0.912145  |
| S      | 10:30   | D3     | ticker_episode   |  13 |        0.359109 | -0.0482917   |                  0.912526  |
| S      | 10:30   | D5     | ticker_episode   |  13 |        0.53637  | -0.037838    |                  1         |
| A      | Open    | D1     | ticker_episode   | 353 |        1.18385  | -0.00189116  |                  0.178131  |
| A      | Open    | D2     | ticker_episode   | 351 |        0.939374 | -0.00811945  |                  0.223812  |
| A      | Open    | D3     | ticker_episode   | 350 |        0.917774 | -0.00988361  |                  0.213896  |
| A      | Open    | D5     | ticker_episode   | 348 |        0.931253 | -0.00988182  |                  0.219862  |
| A      | 09:45   | D1     | ticker_episode   |  27 |        1.24966  | -0.00443026  |                  0.516737  |
| A      | 09:45   | D2     | ticker_episode   |  26 |        0.622901 | -0.0155778   |                  0.864505  |
| A      | 09:45   | D3     | ticker_episode   |  25 |        0.45435  | -0.0261102   |                  0.795619  |
| A      | 09:45   | D5     | ticker_episode   |  23 |        0.563656 | -0.0297508   |                  0.59965   |
| A      | 10:00   | D1     | ticker_episode   |  27 |        0.906617 | -0.00239388  |                  0.554335  |
| A      | 10:00   | D2     | ticker_episode   |  26 |        0.526794 | -0.0174377   |                  0.878894  |
| A      | 10:00   | D3     | ticker_episode   |  25 |        0.39023  | -0.0365493   |                  0.739677  |
| A      | 10:00   | D5     | ticker_episode   |  23 |        0.49264  | -0.0341199   |                  0.612663  |
| A      | 10:30   | D1     | ticker_episode   |  27 |        0.765923 | -9.57579e-05 |                  0.555633  |
| A      | 10:30   | D2     | ticker_episode   |  26 |        0.586198 | -0.0248561   |                  0.768595  |
| A      | 10:30   | D3     | ticker_episode   |  25 |        0.481133 | -0.0298822   |                  0.682163  |
| A      | 10:30   | D5     | ticker_episode   |  23 |        0.573857 | -0.0317479   |                  0.533115  |
| S+A    | Open    | D1     | ticker_episode   | 477 |        1.10018  | -0.00214535  |                  0.146279  |
| S+A    | Open    | D2     | ticker_episode   | 474 |        0.996253 | -0.00781415  |                  0.17559   |
| S+A    | Open    | D3     | ticker_episode   | 473 |        0.933806 | -0.0114465   |                  0.172945  |
| S+A    | Open    | D5     | ticker_episode   | 471 |        0.882612 | -0.011732    |                  0.171957  |
| S+A    | 09:45   | D1     | ticker_episode   |  32 |        1.32282  |  0.000594575 |                  0.437905  |
| S+A    | 09:45   | D2     | ticker_episode   |  31 |        0.641339 | -0.0194178   |                  0.816235  |
| S+A    | 09:45   | D3     | ticker_episode   |  30 |        0.371062 | -0.0292068   |                  0.724343  |
| S+A    | 09:45   | D5     | ticker_episode   |  28 |        0.453664 | -0.0478432   |                  0.583599  |
| S+A    | 10:00   | D1     | ticker_episode   |  32 |        1.04884  | -0.00123225  |                  0.469134  |
| S+A    | 10:00   | D2     | ticker_episode   |  31 |        0.559847 | -0.0201407   |                  0.811455  |
| S+A    | 10:00   | D3     | ticker_episode   |  30 |        0.341072 | -0.041315    |                  0.649395  |
| S+A    | 10:00   | D5     | ticker_episode   |  28 |        0.406272 | -0.0448662   |                  0.601793  |
| S+A    | 10:30   | D1     | ticker_episode   |  32 |        0.774845 | -0.00144816  |                  0.528094  |
| S+A    | 10:30   | D2     | ticker_episode   |  31 |        0.590699 | -0.0188516   |                  0.711114  |
| S+A    | 10:30   | D3     | ticker_episode   |  30 |        0.407241 | -0.0403446   |                  0.585423  |
| S+A    | 10:30   | D5     | ticker_episode   |  28 |        0.454768 | -0.0348354   |                  0.545716  |
| S      | Open    | D1     | market_episode   |  29 |        1.4918   |  0.00183153  |                  0.643284  |
| S      | Open    | D2     | market_episode   |  29 |        2.28904  |  0.00222748  |                  0.632678  |
| S      | Open    | D3     | market_episode   |  29 |        2.33208  |  0.000670127 |                  0.595247  |
| S      | Open    | D5     | market_episode   |  29 |        1.42482  |  0.00370084  |                  0.613113  |
| S      | 09:45   | D1     | market_episode   |   4 |      inf        |  0.0137892   |                  0.94085   |
| S      | 09:45   | D2     | market_episode   |   4 |        3.32815  |  0.0339774   |                  1         |
| S      | 09:45   | D3     | market_episode   |   4 |        1.96817  |  0.0194842   |                  1         |
| S      | 09:45   | D5     | market_episode   |   4 |        3.86157  |  0.0617398   |                  1         |
| S      | 10:00   | D1     | market_episode   |   4 |       16.6661   |  0.0104238   |                  1         |
| S      | 10:00   | D2     | market_episode   |   4 |        2.57572  |  0.02806     |                  1         |
| S      | 10:00   | D3     | market_episode   |   4 |        1.52454  |  0.00594861  |                  1         |
| S      | 10:00   | D5     | market_episode   |   4 |        3.17693  |  0.0475567   |                  1         |
| S      | 10:30   | D1     | market_episode   |   4 |        5.48072  |  0.0093148   |                  1         |
| S      | 10:30   | D2     | market_episode   |   4 |        2.30717  |  0.021276    |                  1         |
| S      | 10:30   | D3     | market_episode   |   4 |        1.48543  |  0.00657829  |                  1         |
| S      | 10:30   | D5     | market_episode   |   4 |        2.92004  |  0.0482333   |                  1         |
| A      | Open    | D1     | market_episode   |  33 |        1.00656  |  0.00611067  |                  0.341433  |
| A      | Open    | D2     | market_episode   |  33 |        0.7593   | -0.0058059   |                  0.526813  |
| A      | Open    | D3     | market_episode   |  33 |        0.752657 | -0.00649066  |                  0.522538  |
| A      | Open    | D5     | market_episode   |  33 |        1.02269  | -0.0090489   |                  0.552238  |
| A      | 09:45   | D1     | market_episode   |   4 |        0.893581 | -0.00684255  |                  1         |
| A      | 09:45   | D2     | market_episode   |   4 |        0        | -0.0198984   |                nan         |
| A      | 09:45   | D3     | market_episode   |   4 |        0.273164 | -0.0227868   |                  1         |
| A      | 09:45   | D5     | market_episode   |   4 |        0.81482  | -0.0123131   |                  1         |
| A      | 10:00   | D1     | market_episode   |   4 |        0.484988 | -0.00897717  |                  1         |
| A      | 10:00   | D2     | market_episode   |   4 |        0        | -0.0210575   |                nan         |
| A      | 10:00   | D3     | market_episode   |   4 |        0.176539 | -0.0252998   |                  1         |
| A      | 10:00   | D5     | market_episode   |   4 |        0.641138 | -0.0179202   |                  1         |
| A      | 10:30   | D1     | market_episode   |   4 |        0.367812 | -0.00471009  |                  1         |
| A      | 10:30   | D2     | market_episode   |   4 |        0        | -0.0176128   |                nan         |
| A      | 10:30   | D3     | market_episode   |   4 |        0.320637 | -0.0217744   |                  1         |
| A      | 10:30   | D5     | market_episode   |   4 |        0.824873 | -0.00822959  |                  1         |
| S+A    | Open    | D1     | market_episode   |  35 |        1.32541  |  0.00476274  |                  0.508153  |
| S+A    | Open    | D2     | market_episode   |  35 |        1.28855  |  0.000541123 |                  0.483607  |
| S+A    | Open    | D3     | market_episode   |  35 |        1.298    | -0.00316884  |                  0.559254  |
| S+A    | Open    | D5     | market_episode   |  35 |        1.07605  | -0.00778616  |                  0.467004  |
| S+A    | 09:45   | D1     | market_episode   |   4 |        2.44457  | -0.000445447 |                  1         |
| S+A    | 09:45   | D2     | market_episode   |   4 |        0.603348 | -0.00487892  |                  1         |
| S+A    | 09:45   | D3     | market_episode   |   4 |        0.38722  | -0.0134025   |                  1         |
| S+A    | 09:45   | D5     | market_episode   |   4 |        1.25675  | -0.000383149 |                  1         |
| S+A    | 10:00   | D1     | market_episode   |   4 |        0.774712 | -0.00389403  |                  1         |
| S+A    | 10:00   | D2     | market_episode   |   4 |        0.198599 | -0.00735388  |                  1         |
| S+A    | 10:00   | D3     | market_episode   |   4 |        0.217584 | -0.0222316   |                  1         |
| S+A    | 10:00   | D5     | market_episode   |   4 |        1.04605  | -0.00420993  |                  1         |
| S+A    | 10:30   | D1     | market_episode   |   4 |        0.545255 | -0.00470767  |                  1         |
| S+A    | 10:30   | D2     | market_episode   |   4 |        0.292069 | -0.0108873   |                  1         |
| S+A    | 10:30   | D3     | market_episode   |   4 |        0.360063 | -0.0174199   |                  1         |
| S+A    | 10:30   | D5     | market_episode   |   4 |        1.17509  |  0.00286807  |                  1         |
| S      | Open    | D1     | weakest_selected |  29 |        1.62368  |  0.00939781  |                  0.392188  |
| S      | Open    | D2     | weakest_selected |  29 |        1.9078   |  0.00816718  |                  0.480047  |
| S      | Open    | D3     | weakest_selected |  29 |        1.7465   |  0.00389524  |                  0.624348  |
| S      | Open    | D5     | weakest_selected |  29 |        1.3579   |  0.00826444  |                  0.579639  |
| S      | 09:45   | D1     | weakest_selected |   4 |        1.06799  |  0.0146524   |                  1         |
| S      | 09:45   | D2     | weakest_selected |   4 |        4.71875  |  0.0376151   |                  1         |
| S      | 09:45   | D3     | weakest_selected |   4 |       31.7836   |  0.0867422   |                  1         |
| S      | 09:45   | D5     | weakest_selected |   4 |        8.75247  |  0.146035    |                  1         |
| S      | 10:00   | D1     | weakest_selected |   4 |        1.17284  |  0.00559016  |                  1         |
| S      | 10:00   | D2     | weakest_selected |   4 |        5.39024  |  0.0502241   |                  1         |
| S      | 10:00   | D3     | weakest_selected |   4 |      inf        |  0.0693338   |                  0.948633  |
| S      | 10:00   | D5     | weakest_selected |   4 |       13.9547   |  0.127603    |                  1         |
| S      | 10:30   | D1     | weakest_selected |   4 |        1.59827  |  0.00265441  |                  1         |
| S      | 10:30   | D2     | weakest_selected |   4 |        6.22487  |  0.0580957   |                  1         |
| S      | 10:30   | D3     | weakest_selected |   4 |      inf        |  0.0678871   |                  0.940546  |
| S      | 10:30   | D5     | weakest_selected |   4 |       16.995    |  0.12428     |                  1         |
| A      | Open    | D1     | weakest_selected |  33 |        0.545336 | -0.00785019  |                  0.680273  |
| A      | Open    | D2     | weakest_selected |  33 |        0.952353 | -0.0141514   |                  0.792818  |
| A      | Open    | D3     | weakest_selected |  33 |        0.79706  | -0.0155563   |                  0.737736  |
| A      | Open    | D5     | weakest_selected |  33 |        2.06504  |  0.00114638  |                  0.780194  |
| A      | 09:45   | D1     | weakest_selected |   4 |       20.0584   |  0.0220173   |                  1         |
| A      | 09:45   | D2     | weakest_selected |   4 |        3.54358  | -0.0161809   |                  1         |
| A      | 09:45   | D3     | weakest_selected |   4 |        1.73474  | -0.00066755  |                  1         |
| A      | 09:45   | D5     | weakest_selected |   4 |        3.82679  |  0.0904869   |                  1         |
| A      | 10:00   | D1     | weakest_selected |   4 |       19.9629   |  0.00891849  |                  1         |
| A      | 10:00   | D2     | weakest_selected |   4 |        2.68768  | -0.0231203   |                  1         |
| A      | 10:00   | D3     | weakest_selected |   4 |        1.30969  | -0.0147393   |                  1         |
| A      | 10:00   | D5     | weakest_selected |   4 |        3.56522  |  0.0751323   |                  1         |
| A      | 10:30   | D1     | weakest_selected |   4 |      550.89     |  0.00265441  |                  1         |
| A      | 10:30   | D2     | weakest_selected |   4 |        2.91815  | -0.0168105   |                  1         |
| A      | 10:30   | D3     | weakest_selected |   4 |        1.40696  | -0.00504752  |                  1         |
| A      | 10:30   | D5     | weakest_selected |   4 |        3.52745  |  0.0856799   |                  1         |
| S+A    | Open    | D1     | weakest_selected |  35 |        0.80459  | -0.00279014  |                  0.539405  |
| S+A    | Open    | D2     | weakest_selected |  35 |        1.5508   | -0.00125155  |                  0.644236  |
| S+A    | Open    | D3     | weakest_selected |  35 |        1.08225  | -0.00781918  |                  0.624753  |
| S+A    | Open    | D5     | weakest_selected |  35 |        1.45616  | -0.0112011   |                  0.760434  |
| S+A    | 09:45   | D1     | weakest_selected |   4 |        1.53978  |  0.0220173   |                  1         |
| S+A    | 09:45   | D2     | weakest_selected |   4 |        3.42526  | -0.0161809   |                  1         |
| S+A    | 09:45   | D3     | weakest_selected |   4 |        4.05993  |  0.0102704   |                  1         |
| S+A    | 09:45   | D5     | weakest_selected |   4 |        5.34353  |  0.0904869   |                  1         |
| S+A    | 10:00   | D1     | weakest_selected |   4 |        1.27744  |  0.00559016  |                  1         |
| S+A    | 10:00   | D2     | weakest_selected |   4 |        3.1941   | -0.0155175   |                  1         |
| S+A    | 10:00   | D3     | weakest_selected |   4 |        3.36952  |  0.0167563   |                  1         |
| S+A    | 10:00   | D5     | weakest_selected |   4 |        7.58389  |  0.0751323   |                  1         |
| S+A    | 10:30   | D1     | weakest_selected |   4 |        2.11396  |  0.00265441  |                  1         |
| S+A    | 10:30   | D2     | weakest_selected |   4 |        4.18156  | -0.00371387  |                  1         |
| S+A    | 10:30   | D3     | weakest_selected |   4 |        5.20582  |  0.0218806   |                  1         |
| S+A    | 10:30   | D5     | weakest_selected |   4 |        9.51936  |  0.0856799   |                  1         |

# Candidate vs episode comparison
| rank   | level            |   n |   profit_factor |      median |
|:-------|:-----------------|----:|----------------:|------------:|
| S      | candidate        | 307 |        1.78712  | -0.00193877 |
| A      | candidate        | 497 |        1.1232   | -0.00151785 |
| S+A    | candidate        | 804 |        1.42321  | -0.00173641 |
| S      | ticker_episode   | 216 |        1.09167  | -0.00328582 |
| A      | ticker_episode   | 353 |        1.18385  | -0.00189116 |
| S+A    | ticker_episode   | 477 |        1.10018  | -0.00214535 |
| S      | market_episode   |  29 |        1.4918   |  0.00183153 |
| A      | market_episode   |  33 |        1.00656  |  0.00611067 |
| S+A    | market_episode   |  35 |        1.32541  |  0.00476274 |
| S      | weakest_selected |  29 |        1.62368  |  0.00939781 |
| A      | weakest_selected |  33 |        0.545336 | -0.00785019 |
| S+A    | weakest_selected |  35 |        0.80459  | -0.00279014 |

# S vs A
S market-episode Open/D1 PF=1.4918; A market-episode Open/D1 PF=1.00656.

# 09:45 replication
Formal 09:45 replication is limited to real M15-covered rows only; absent full-population M15, the gate cannot be promoted to formal validation.

# Robustness
Leave-one-year, leave-one-ticker, leave-one-episode, bootstrap, and segment tables are emitted as CSV artifacts.

# Concentration
| concentration_axis   |   group_count |   top_1_share_of_positive_pnl |   top_3_share_of_positive_pnl |   top_5_share_of_positive_pnl | largest_positive_group   |   largest_positive_group_return_sum |
|:---------------------|--------------:|------------------------------:|------------------------------:|------------------------------:|:-------------------------|------------------------------------:|
| ticker               |           143 |                      0.610736 |                      0.70882  |                      0.754563 | CAR                      |                             7.73536 |
| ticker_episode       |           477 |                      0.414149 |                      0.45625  |                      0.489533 | TE5_CAR_0002             |                             7.5443  |
| market_episode       |            35 |                      0.647075 |                      0.787635 |                      0.874353 | ME_0034                  |                             7.29058 |

# Legacy-result reconciliation
Legacy PF values are comparison targets only. Difference decomposition is in legacy_result_difference_explanation.md.

# Limitations
Daily OHLCV source is local cached data with basis unspecified; historical universe is static/proxy, so this is not a formal survivorship-safe backtest.

# Safety
SHORT_PRODUCTION_READY, SHORT_LIVE_READY, and FORMAL_SURVIVORSHIP_SAFE_BACKTEST are intentionally not used.

# Git / tests
Targeted tests are included for the runner. test_summary.csv is updated after the test command is run.

# Exact next step
Use the emitted CSVs to decide whether to acquire full PIT M15 for all current-condition S/A candidates; do not route this into production.
