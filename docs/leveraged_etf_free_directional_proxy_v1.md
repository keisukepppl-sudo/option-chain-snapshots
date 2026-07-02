# Leveraged ETF Free Directional Proxy v1

This module is research context only. It must not be used as a standalone buy/sell signal.

## Purpose

Daily-reset leveraged ETFs can act as short-horizon directional amplifiers. After a positive benchmark return, both long and inverse daily-reset leveraged ETFs mechanically tend toward benchmark buying to reset exposure. After a negative benchmark return, both tend toward benchmark selling.

This module estimates only a directional-amplifier proxy. It is not an estimate of actual ETF execution, AP activity, dealer inventory, market-maker hedging, or market impact.

## Benchmark Mapping

```text
primary_target_benchmark = NDX
tradable_market_proxy = QQQ
leveraged_long_etf = TQQQ
leveraged_inverse_etf = SQQQ
```

NDX exact mode and QQQ proxy-only mode are separated:

- `ndx_exact`: benchmark calculations use manually supplied NDX history.
- `qqq_proxy_only_descriptive`: QQQ can be used only as a descriptive market proxy.

Exact NDX observations and QQQ-proxy observations must not be silently combined.

## Formula

For daily-reset leverage `L`, capital `A`, and benchmark daily return `r`:

```text
estimated_rebalance_notional = L * (L - 1) * A * r
```

For the initial pair:

```text
TQQQ: L = +3 -> +6 * A * r
SQQQ: L = -3 -> +12 * A * r
```

Positive benchmark returns produce positive proxy notional. Negative benchmark returns produce negative proxy notional.

## Output Families

Equal-weight direction:

```text
equal_weight_directional_proxy = sign(r)
```

AUM-scaled proxy:

```text
sum(L_i * (L_i - 1) * A_i * r)
```

AUM is never forward-filled, interpolated, or invented. If exact permitted lagged capital is missing, the AUM-scaled output is unavailable.

## Canonical Manual Input Contract

The generated template is the active input contract:

```text
source_manifest.json
sources/benchmark_prices.csv
sources/benchmark_mapping.csv
sources/aum_or_capital.csv
sources/split_history.csv
sources/leveraged_etf_prices.csv
```

`benchmark_prices.csv` may contain NDX and QQQ rows. `leveraged_etf_prices.csv` may contain TQQQ and SQQQ rows. AUM or shares-times-NAV rows belong in `aum_or_capital.csv`.

Legacy per-ticker filenames are deprecated planning names and are not active input filenames. See `docs/leveraged_etf_free_proxy_canonical_input_contract_v1.md`.

## Neutral Threshold

Frozen policy:

```text
minimum_absolute_benchmark_return_for_direction = 0.001
```

If `abs(r) < 0.10%`, the daily label is `directional_amplifier_neutral`.

## Modes

Historical mode:

```text
mode=historical_free_descriptive_proxy
predictive_pit_eligible=false
phase2_eligible=false
```

Forward PIT-lite mode:

```text
mode=forward_pit_lite_observation
predictive_pit_eligible=false
phase2_eligible=false
actionization_allowed=false
```

Forward PIT-lite proves only that the operator possessed a local version by the recorded capture time. It does not prove issuer first-publication time.

## Strict Pipeline Boundary

Free-proxy artifacts cannot unlock:

- Phase 1.3 strict predictive readiness,
- Phase 2 admission,
- Flow release,
- Flow statistical backtest,
- notifications,
- trading or actionization.

No output may set `gold_point_in_time_eligible`, `silver_documented_schedule_eligible`, or `ready_for_eod_next_session_research`.
