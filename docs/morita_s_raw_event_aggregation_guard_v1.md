# Morita S Raw Event Aggregation Guard v1

Raw S events are notification events, not automatically independent trades.

Same-ticker raw S events may belong to the same setup episode. A future report must not call the full raw current-S event stream `initial breakout performance`, `S strategy PF`, or `S strategy DD` unless it explicitly stratifies by `setup_episode_classification`.

Required for future S performance research:

- show `setup_episode_classification` counts;
- show unresolved share;
- keep same-ticker repeated notifications visible;
- state whether any `VALID_REBREAKOUT` rows are source-proven;
- block portfolio/DD research until episode classification is stable.

In short: portfolio/DD research is blocked until episode classification is stable.

This is a reporting and data-contract guard only. It does not change scanner, rank, notification, order, or portfolio logic.
