# Flow Pressure QQQ Benchmark Mapping Correction v1

## Correct Mapping

```text
primary_target_benchmark = NDX
tradable_market_proxy = QQQ
leveraged_long_etf = TQQQ
leveraged_inverse_etf = SQQQ
```

TQQQ and SQQQ target the Nasdaq-100 Index exposure. QQQ is a tradable ETF proxy for research outcomes and liquidity, not the exact target benchmark for leveraged ETF rebalance-pressure mechanics.

## Required Reference Columns

```text
target_benchmark_instrument
market_proxy_instrument
is_proxy_underlying
proxy_relationship_description
benchmark_source_authority
benchmark_exact_or_proxy
```

## Production-Like Rules

- Theoretical rebalance pressure must use `target_benchmark_instrument=NDX`.
- `market_proxy_instrument=QQQ` is allowed as tradable outcome proxy.
- QQQ must not be accepted as exact target benchmark for TQQQ/SQQQ.
- If only QQQ is available, label the result `QQQ_proxy_only_descriptive_analysis`.
- Legacy synthetic fixtures may keep QQQ proxy mappings only when explicitly marked fixture-only.

## Expected Validation

| Case | Expected result |
|---|---|
| TQQQ -> NDX exact, proxy QQQ | pass |
| SQQQ -> NDX exact, proxy QQQ | pass |
| QQQ labelled market proxy | pass |
| TQQQ -> QQQ exact production mapping | reject |
| SQQQ -> QQQ exact production mapping | reject |
| Legacy QQQ proxy synthetic fixture | fixture-only, not real readiness |
