# Flow Pressure QQQ Source Qualification Matrix v1

Phase 1.3A does not fetch or stage real data. It defines the source qualification standard that must be satisfied before Phase 1.3 real-data readiness can run.

## Benchmark Correction

| ETF | Primary target benchmark | Leverage | Direction | Tradable market proxy | Mapping status |
|---|---|---:|---|---|---|
| TQQQ | NDX | +3 | long | QQQ | benchmark_exact |
| SQQQ | NDX | -3 | inverse | QQQ | benchmark_exact |

QQQ is not the exact target benchmark for TQQQ or SQQQ. QQQ is retained as a tradable market proxy and research outcome proxy only.

Production-like readiness must not pass a `TQQQ -> QQQ` or `SQQQ -> QQQ` exact mapping. Legacy QQQ proxy fixtures may remain only when marked:

```text
legacy_proxy_fixture=true
is_synthetic_fixture=true
not_for_real_data_readiness=true
```

## Required Matrix Fields

```text
dataset_type
instrument
source_tier
provider_or_issuer
source_authority_type
economic_value_authority
historical_vintage_available
publication_timestamp_available
revision_history_available
availability_evidence_type
availability_evidence_reference
raw_or_adjusted
corporate_action_treatment
units
timezone
coverage_start
coverage_end
delivery_mechanism
manual_export_date
source_contract_eligible
predictive_pit_eligible
reconciliation_source
qualification_status
blocking_reason
```

## Initial Qualification Matrix

| Dataset | Primary source | Secondary source | Economic authority | PIT status | Predictive use | Blocker |
|---|---|---|---|---|---|---|
| NDX daily OHLC / close | Nasdaq or licensed index vendor | Licensed market data vendor | Nasdaq | unknown until timestamped vintage evidence exists | no | Need publication timestamp, revision ID, and raw/adjusted basis |
| QQQ daily OHLCV | Licensed market data vendor or exchange-sourced file | Nasdaq/institutional vendor | Market venue/vendor | proxy market data, not benchmark authority | conditional | Must not be used as exact TQQQ/SQQQ target |
| TQQQ daily OHLCV | Licensed market data vendor | ProShares/market data vendor | Market venue/vendor | unknown until row availability is proven | conditional | Need raw fields and split treatment |
| SQQQ daily OHLCV | Licensed market data vendor | ProShares/market data vendor | Market venue/vendor | unknown until row availability is proven | conditional | Need raw fields and split treatment |
| TQQQ NAV / shares / AUM | ProShares historical NAV/AUM export | Licensed ETF vendor | ProShares | authoritative if timing proven | conditional | Need publication time, revision ID, and vintage evidence |
| SQQQ NAV / shares / AUM | ProShares historical NAV/AUM export | Licensed ETF vendor | ProShares | authoritative if timing proven | conditional | Need publication time, revision ID, and vintage evidence |
| TQQQ split history | ProShares split history | Licensed ETF vendor | ProShares | silver or gold only with evidence | conditional | Need action ledger and availability timestamp |
| SQQQ split history | ProShares split history | Licensed ETF vendor | ProShares | silver or gold only with evidence | conditional | Need action ledger and availability timestamp |
| TQQQ/SQQQ target benchmark mapping | ProShares prospectus/fund documentation | SEC filing / licensed reference data | ProShares | documentary mapping | yes after validation | Must identify NDX, not QQQ |
| QQQ-to-NDX proxy relationship | Nasdaq/Invesco/fund docs | Licensed vendor | Invesco/Nasdaq | proxy relationship | descriptive/proxy only | Must be labelled proxy_based |

## Qualification Statuses

| Status | Predictive PIT eligible? | Meaning |
|---|---:|---|
| `gold_point_in_time_eligible` | yes | Row-level historical vintage, publication timestamp, revision identity, raw/adjusted policy, and reconciliation all pass |
| `silver_documented_schedule_eligible` | yes | Official/economic source plus documented publication schedule and conservative cutoff, but not full daily vintage |
| `authoritative_but_historical_vintage_unproven` | no | Official or issuer data exists but historical timing/revision proof is missing |
| `historical_descriptive_only` | no | Current revised history, unknown timing, or incomplete source relationship |
| `blocked_by_data_quality` | no | Material unresolved reconciliation break |
| `blocked_by_timing` | no | Row or revision was unavailable at the relevant decision time |

## Phase 1.3 Admission Rule

Proceed to Phase 1.3 readiness only when:

- NDX benchmark mapping is `benchmark_exact`.
- QQQ is separately labelled proxy.
- All required source families are qualified.
- Historical availability evidence is gold or approved silver.
- Unresolved material reconciliation count is zero.
- The operator has staged explicit source files and `decision_schedule.csv`.

If this cannot be satisfied, the correct outcome is `historical_descriptive_only`.
