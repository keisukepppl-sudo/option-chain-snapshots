# Flow Pressure Real Provider Onboarding Design v0

## Files

Changed or added files:

- `market_bomb_flow_pressure_research_v0.py`
- `market_bomb_config/flow_pressure_research_v0_policy.json`
- `market_bomb_config/flow_pressure_research_v0_schema.json`
- `docs/flow_pressure_research_v0.md`
- `docs/flow_pressure_real_provider_onboarding_design_v0.md`
- `tests/test_market_bomb_flow_pressure_research_v0.py`

No Fragility Score, notification, Morita, or execution files are changed.

## Timing Model

Every staged source row has an `available_at_timestamp`. A row is `timing_eligible` only when its availability timestamp is not after the declared `decision_time`. The economic timestamp on the row is not enough to prove the data was known.

Allowed `research_timing_class` values:

- `eod_next_session`
- `eod_after_close`
- `intraday_close_window`
- `historical_descriptive_only`

Daily data can support `eod_next_session`, `eod_after_close`, or `historical_descriptive_only`. It cannot support `intraday_close_window`. Intraday close-window runs require declared intraday bars that are available before the studied decision time.

## Daily Versus Close-Window Eligibility

`eod_next_session` means all inputs were known after their provider availability time and the research target starts no earlier than the next eligible session. `eod_after_close` is after the relevant close and source publication time. `intraday_close_window` requires time-resolved bars; daily bars never fall back into close-window eligibility.

## AUM Without Forward Fill

Leveraged ETF AUM selection may use the most recent previously published observed AUM row only when:

- the row itself is observed input;
- `available_at_timestamp <= decision_time`;
- `valid_until_timestamp` exists;
- `valid_until_timestamp >= decision_time`;
- observation age is within `max_aum_observation_age_days`;
- the output records `aum_observation_age` and `aum_selection_rule`.

If no row passes those checks, the feature is `insufficient_coverage`. No current-day AUM is fabricated from price unless shares and NAV are both observed in the same staged row.

## Failure States

User-facing diagnostics use:

- `timing_ineligible`
- `insufficient_coverage`
- `methodology_incomplete`
- `blocked`
- `available_after_decision_time`
- `as_of_after_available_at`
- `missing_validity_window`
- `stale_observation`
- `missing_reference_mapping`
- `incomplete_return_window`
- `source_hash_mismatch`

## Test Plan

Tests cover:

- template generation without provider data;
- required column and numeric validation;
- hash mismatch and undeclared raw files;
- timezone and timestamp ordering failures;
- daily data rejected for close-window timing;
- AUM validity and stale selection failures;
- leveraged ETF long/inverse sign behavior;
- vol-control incomplete-window blocking;
- release/backtest timing audit tamper and extra-file detection;
- CTA/Dealer methodology-incomplete rejection.
