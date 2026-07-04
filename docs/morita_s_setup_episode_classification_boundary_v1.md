# Morita S Setup-Episode Classification Boundary v1

This layer is historical/backfill state architecture only.

It does not:

- change scanner conditions;
- change S rank thresholds;
- change production notifications;
- create orders;
- run return, PF, MAE, DD, or portfolio studies;
- define A/B entries;
- define a new continuation strategy.

`INITIAL_OBSERVED_BREAKOUT` means first observed in the available formal current-S history. It does not claim lifetime first breakout.

`VALID_REBREAKOUT` requires source-proven base/reset evidence. A gap greater than 20 eligible sessions alone is not enough.

`EXTENDED_NO_NEW_BASE` means a repeated same-ticker raw S with documented continuity and no source-proven fresh-base evidence.

`UNRESOLVED` is a valid final state when point-in-time evidence is insufficient.
