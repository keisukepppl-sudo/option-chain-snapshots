# Morita Outcome Distribution Audit v1

This audit describes closed monitoring-lot outcomes when enough fully auditable lots exist.

It is not a backtest, expectancy claim, strategy validation, strategy invalidation, or sizing recommendation.

## Sample Gates

Aggregate metrics require at least 30 closed monitoring lots. Rank and strategy metrics require at least 15 closed lots per group.

Below the gate:

```text
metrics_available=false
metrics_unavailable_reason=closed_lot_count_below_minimum
```

## Metrics

The audit reports distribution shape, profit factor, positive-return concentration, largest outcomes, and consecutive negative lot runs. It does not calculate Sharpe or optimize exits.
