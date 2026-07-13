# Legacy Result Difference Explanation

Input reconciliation: PASS.

The old 09:45 PF figures are not treated as targets. In this independent pass, full-population 09:45/10:00/10:30 results are only computed where real M15 bars exist; missing intraday bars are not synthesized.

Primary decomposition:
- v3.4.1 candidate 09:45 PF: legacy=3.369, current=1.4767890206995815; driver=Mostly unavailable because full-population M15 is not present; no synthetic intraday fill used.
- later small sample candidate S PF: legacy=1.269, current=1.7871216820426779; driver=Population expanded to current-condition S signals and daily D0 deterioration construction.
- later small sample candidate A PF: legacy=1.172, current=1.1232005737942077; driver=Population expanded to current-condition A signals and daily D0 deterioration construction.
- later small sample episode S PF: legacy=0.685, current=1.4918027554423428; driver=Candidate rows collapsed to market episodes.
- later small sample episode A PF: legacy=0.869, current=1.0065621176395692; driver=Candidate rows collapsed to market episodes.
- current daily proxy candidate S+A Open D1: legacy=nan, current=1.4232105090939549; driver=Daily-open proxy result; 09:45 formal comparison blocked where M15 is missing.
- current daily proxy market-episode S+A Open D1: legacy=nan, current=1.3254133958346932; driver=Independence adjustment result.
- input reconciliation: legacy=nan, current=1.0; driver=S/A/base count gate.
- constructed candidates: legacy=nan, current=804.0; driver=D0 deterioration found within 1-30 official sessions.
