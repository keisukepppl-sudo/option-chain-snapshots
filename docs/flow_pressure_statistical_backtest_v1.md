# Flow Pressure Statistical Backtest v1

This document defines the research-only statistical engine for sealed Flow Pressure releases.

The engine tests model-implied pressure proxies. It does not observe institutional orders, actual dealer positioning, or live fund activity. It does not modify Fragility Score and it does not create trading, alerting, ranking, sizing, notification, or execution behavior.

`actionization_allowed=false` is mandatory in every output.

## Research Question

The engine asks whether timing-valid Flow Pressure proxies show conservative statistical association with later outcomes:

- leveraged ETF theoretical rebalance pressure
- vol-control normalized deleveraging pressure
- pre-specified Fragility interaction cells when availability-valid Fragility records exist

CTA and Dealer/GEX remain blocked placeholders.

## Release Requirements

The engine consumes only a verified Flow Pressure release:

```text
features/flow_pressure_features.csv
canonical_input/flow_pressure_canonical_source_rows.csv
timing_audit.csv
release_core_metadata.json
release_content_manifest.json
parameter_registry.json
```

It never reads raw staging files and never fetches provider data.

## Timing-Valid Panel Construction

Each panel row retains:

```text
release_id
feature_row_id
instrument
underlying_instrument
module_name
decision_time
research_timing_class
feature_available_at_timestamp
feature_state
data_quality_state
timing_eligible
actionization_allowed
source_contract_version
methodology_version
parameter_registry_hash
target_name
target_start_timestamp
target_end_timestamp
target_value
outcome_available_at_timestamp
outcome_validity_state
```

The hard rule is:

```text
feature_available_at_timestamp <= decision_time < target_start_timestamp
```

Rows failing this rule are excluded with deterministic reason codes.

## Outcome Definitions

Daily outcomes are constructed from timing-eligible daily OHLC rows in the sealed release:

- `next_session_open_to_close_return`
- `next_session_close_to_close_return`
- `three_session_close_to_close_return`
- `five_session_close_to_close_return`
- `next_session_daily_range`
- `three_session_mae`
- `three_session_mfe`
- `five_session_mae`
- `five_session_mfe`
- `subsequent_realized_volatility`
- `conditional_drawdown`

Daily OHLC outcomes are not described as intraday close-window evidence.

## Chronological Split

Splits use unique eligible decision dates:

```text
train: earliest 60%
validation: next 20%
final_holdout: latest 20%
```

Rows sharing a decision date remain in the same split. Rows are never shuffled.

The final holdout is evaluated using frozen thresholds and frozen partitions.

## Train-Only Thresholds

The train partition derives:

- downside-tail thresholds by module, instrument, and outcome
- absolute-pressure quintile boundaries by module, instrument, and feature

These thresholds are saved in:

```text
derived_threshold_registry.json
partition_boundary_registry.json
```

Validation and holdout use these frozen values unchanged.

## Feature Partitions

Pre-specified partitions:

- adverse versus non-adverse Flow pressure
- negative / neutral / positive pressure
- train-derived absolute-pressure quintile

Leveraged ETF adverse pressure is negative normalized pressure. Vol-control adverse pressure is negative exposure change, meaning deleveraging pressure.

## Bootstrap Method

The supported method is:

```text
moving_block_bootstrap
```

Default block lengths:

```text
3, 5, 10 decision dates
```

Default seed:

```text
20260629
```

The resampling unit is `decision_date`; all rows associated with sampled dates remain grouped.

## Effect Sizes

For each pre-specified analysis, the engine reports:

- mean difference versus unconditional
- median difference versus unconditional
- downside-tail-rate difference versus unconditional
- risk ratio versus unconditional
- odds ratio versus unconditional
- standardized mean difference

Undefined ratios are reported as `not_estimable`, not infinity.

## Interactions

The pre-specified interaction grid is:

```text
Fragility: high / not_high
Flow pressure: adverse / non_adverse
```

If availability-valid Fragility records are unavailable, interaction outputs remain present but non-confirmatory.

## Evidence Labels

Allowed labels:

```text
blocked_by_data_quality
insufficient_data
insufficient_sample
no_reliable_evidence
exploratory_association
timing_valid_association_requiring_replication
```

The classifier is conservative. A positive-looking estimate is not enough. Timing validity, sample gates, validation/holdout alignment, bootstrap stability, and concentration checks must all pass before promotion beyond `no_reliable_evidence`.

No label authorizes trading.

## Multiple Testing

All tested slices are retained in:

```text
analysis_registry.csv
```

The best-looking slice must not be presented alone. Negative and inconclusive analyses remain part of the run.

## CLI

Run through the existing Flow CLI:

```powershell
python market_bomb_flow_pressure_research_v0.py run-flow-statistical-backtest --release-id <release_id>
python market_bomb_flow_pressure_research_v0.py verify-flow-statistical-backtest --release-id <release_id> --statistical-backtest-run-id <run_id>
```

Or through the companion module:

```powershell
python market_bomb_flow_pressure_statistical_backtest_v1.py run-flow-statistical-backtest --release-id <release_id>
python market_bomb_flow_pressure_statistical_backtest_v1.py verify-flow-statistical-backtest --release-id <release_id> --statistical-backtest-run-id <run_id>
```

## Output Dictionary

Required outputs:

```text
analysis_registry.csv
feature_outcome_panel.csv
chronological_split_manifest.json
derived_threshold_registry.json
partition_boundary_registry.json
statistical_summary.csv
effect_size_summary.csv
bootstrap_summary.csv
bootstrap_replicate_metadata.json
interaction_results.csv
interaction_difference_in_differences.csv
sample_stability_report.csv
outcome_coverage_report.csv
exclusion_reason_report.csv
evidence_classification.csv
holdout_results.csv
research_conclusion.md
```

The run also writes:

```text
statistical_backtest_content_manifest.json
statistical_backtest_receipt.json
frozen_statistical_backtest_spec.json
```

The verifier checks exact file set, hashes, release linkage, split and threshold registry hashes, analysis registry hash, deterministic seed metadata, and `actionization_allowed=false`.

## Failure States

The engine fails closed when:

- release verification fails
- timing audit contains ineligible rows
- output files are tampered
- undeclared output files appear
- actionization is enabled
- required outcomes cannot be constructed
- sample gates fail

## Limitations

This is a research system. It can report invalid data, insufficient sample, no reliable evidence, exploratory association, or a timing-valid association requiring replication. It cannot produce buy/sell advice or production market signals.
