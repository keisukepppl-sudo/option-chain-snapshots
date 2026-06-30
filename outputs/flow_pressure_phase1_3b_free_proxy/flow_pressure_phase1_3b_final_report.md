# Flow Pressure Phase 1.3B Final Report

## Outcome

`phase1_3b_free_leveraged_etf_proxy_complete`

Implemented a separate, research-only free leveraged-ETF directional-amplifier proxy for TQQQ/SQQQ. It supports historical descriptive runs and forward PIT-lite observation ledgers without weakening strict Phase 1.3 readiness, Phase 2 admission, release, backtest, notification, or trading gates.

## Start / Final Commit

- Start commit: `3d0b02088cc769a84f7ab02869d1775f8c6606c1`
- Final commit: pending commit at report creation

## Changed Files

- `.gitignore`
- `.github/workflows/ci.yml`
- `market_bomb_leveraged_etf_free_proxy_v1.py`
- `tests/test_market_bomb_leveraged_etf_free_proxy_v1.py`
- `docs/leveraged_etf_free_directional_proxy_v1.md`
- `docs/leveraged_etf_free_proxy_operator_runbook_v1.md`
- `docs/flow_pressure_research_program_v1.md`

## Module Design

The module is deliberately narrow:

```text
module_name=leveraged_etf_free_directional_proxy_v1
research_only=true
actionization_allowed=false
not_a_trading_signal=true
not_market_impact_estimate=true
not_dealer_inventory_estimate=true
```

It estimates daily directional amplification from daily-reset leveraged ETF mechanics. It does not observe actual ETF execution, creations/redemptions, AP activity, manager execution timing, derivatives usage, tracking error, fees, or dealer hedging.

## Formula

For leverage `L`, capital `A`, and benchmark daily return `r`:

```text
estimated_rebalance_notional = L * (L - 1) * A * r
```

Initial pair:

```text
TQQQ: L = +3 -> +6 * A * r
SQQQ: L = -3 -> +12 * A * r
```

Positive benchmark returns produce positive proxy notional; negative returns produce negative proxy notional.

## NDX / QQQ Treatment

```text
primary_target_benchmark = NDX
tradable_market_proxy = QQQ
```

- `ndx_exact` requires `benchmark_exact`.
- `qqq_proxy_only_descriptive` requires `proxy_based`.
- Exact NDX and QQQ proxy observations are not silently combined.
- TQQQ/SQQQ exact production mapping to QQQ is rejected.

## Modes

Historical:

```text
mode=historical_free_descriptive_proxy
predictive_pit_eligible=false
phase2_eligible=false
```

Forward PIT-lite:

```text
mode=forward_pit_lite_observation
predictive_pit_eligible=false
phase2_eligible=false
actionization_allowed=false
```

## Manual Local Input Checklist

Raw files stay under ignored local storage:

```text
market_bomb_history/leveraged_etf_free_proxy_v1/input/<input_id>/sources/
```

Supported manually supplied files:

- NDX or QQQ benchmark prices.
- TQQQ/SQQQ mapping evidence.
- TQQQ/SQQQ AUM, shares, or NAV history.
- TQQQ/SQQQ split history.

Current historical downloads remain `historical_descriptive_only`; they do not prove historical availability.

## CLI Commands

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-template --input-id <input_id>
python market_bomb_leveraged_etf_free_proxy_v1.py validate-leveraged-etf-free-proxy-input --input-id <input_id>
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <input_id> --benchmark-mode ndx_exact
python market_bomb_leveraged_etf_free_proxy_v1.py run-leveraged-etf-free-proxy-historical --input-id <input_id> --benchmark-mode qqq_proxy_only_descriptive
python market_bomb_leveraged_etf_free_proxy_v1.py ingest-leveraged-etf-free-proxy-forward-snapshot --input-id <input_id> --snapshot-date <YYYY-MM-DD> --capture-timestamp-utc <ISO8601Z>
python market_bomb_leveraged_etf_free_proxy_v1.py build-leveraged-etf-free-proxy-forward-observation --observation-date <YYYY-MM-DD>
python market_bomb_leveraged_etf_free_proxy_v1.py verify-leveraged-etf-free-proxy-run --run-artifact <exact_run_path>
python market_bomb_leveraged_etf_free_proxy_v1.py verify-leveraged-etf-free-proxy-forward-ledger --ledger-root <path>
```

## Validation

- New free proxy suite: `34 passed`
- Targeted safety suite with free proxy: `92 passed, 1 skipped`
- Full local suite: `366 passed, 2 skipped, 52 warnings`
- Compile check: passed for the new module and CI core modules.

## Known Limitations

- This is not a high-precision flow estimator.
- Historical free data cannot prove when historical AUM records became known.
- AUM-scaled proxy is unavailable when exact permitted lagged capital is absent.
- Forward PIT-lite records possession of local snapshots, not issuer first-publication time.

## Guardrail Confirmation

- No external data was fetched, downloaded, scraped, or queried.
- No provider API, SDK, browser automation, credential, or token was added.
- No raw provider data was committed.
- No strict Phase 1.3 readiness artifact was created.
- No Phase 2 admission, release, statistical backtest, notification, trading, sizing, execution, or actionization occurred.
- Fragility Score, CTA, Dealer, Morita notifications, and ranking logic were not changed.
- `actionization_allowed=false` remains enforced.
