# Morita First Absorption Reversal Methodology v1

## Universe

For each session, the harness includes tickers with a prior Morita S signal that is at least 20 and at most 126 trading sessions old. The current local run is limited by available PIT semis daily data.

## D0 / D1 Absorption

D0 and D1 require positive open-to-close return, high close location, relative strength versus old-S peer median, relative strength versus SOXX, and an existing drawdown from the prior 60-session high.

## Universe Weakness

D1 requires the old-S universe two-session median return to remain below the configured threshold and at least half of the active old-S universe to be down. A separate sell-pressure-fading flag compares D1 versus D0 median return, new-low count, and sell-efficiency proxy.

## Fundamental Filter

The primary study requires `CLEAN` events. If no sealed point-in-time event audit source is present, every candidate remains `AMBIGUOUS`. This is deliberate to prevent hindsight promotion.

## Option Layer

Options are blocked unless historical option chains are present. The harness does not use Black-Scholes estimates to manufacture adoption results when the underlying signal and CLEAN filter are not already acceptable.

