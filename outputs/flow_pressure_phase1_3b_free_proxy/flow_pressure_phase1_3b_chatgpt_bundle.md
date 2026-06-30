# ChatGPT Bundle: Flow Pressure Phase 1.3B Free Leveraged-ETF Directional Proxy

## Objective

Implement a free, research-only leveraged-ETF directional-amplifier proxy for TQQQ/SQQQ.

The goal is useful free context, not a high-precision flow estimator and not a trading signal.

## Implemented

Added:

- `market_bomb_leveraged_etf_free_proxy_v1.py`
- `tests/test_market_bomb_leveraged_etf_free_proxy_v1.py`
- `docs/leveraged_etf_free_directional_proxy_v1.md`
- `docs/leveraged_etf_free_proxy_operator_runbook_v1.md`

Updated:

- `.gitignore`
- `.github/workflows/ci.yml`
- `docs/flow_pressure_research_program_v1.md`

## Core Model

For daily-reset leverage `L`, capital `A`, and benchmark daily return `r`:

```text
estimated_rebalance_notional = L * (L - 1) * A * r
```

For the first pair:

```text
TQQQ: L = +3 -> +6 * A * r
SQQQ: L = -3 -> +12 * A * r
```

Therefore both TQQQ and SQQQ mechanically point in the same procyclical direction:

- positive benchmark return -> positive proxy notional,
- negative benchmark return -> negative proxy notional.

## Benchmark Treatment

```text
primary_target_benchmark = NDX
tradable_market_proxy = QQQ
```

Rules:

- `ndx_exact` requires NDX and `benchmark_exact`.
- `qqq_proxy_only_descriptive` is allowed only as proxy-based descriptive analysis.
- TQQQ/SQQQ exact production mapping to QQQ is rejected.
- Exact NDX and QQQ proxy observations cannot be silently combined.

## Modes

Historical descriptive mode:

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

Forward PIT-lite proves only that the operator had a local file by the capture timestamp. It does not prove original issuer publication time.

## AUM Rules

- Do not forward-fill AUM.
- Do not interpolate AUM.
- Do not infer AUM from price.
- Missing permitted lagged capital -> `aum_scale_unavailable`.
- Equal-weight direction can still be produced, but must not be called AUM-scaled.

## CLI

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

```text
new free proxy suite: 34 passed
targeted safety suite: 92 passed, 1 skipped
full local suite: 366 passed, 2 skipped, 52 warnings
```

GitHub Actions:

```text
implementation commit: afa16d883657894409bb37e1e2adac3f03043d5e
workflow: CI
run: https://github.com/keisukepppl-sudo/option-chain-snapshots/actions/runs/28457672585
job: tests
job conclusion: success
started: 2026-06-30T15:53:56Z
completed: 2026-06-30T16:09:23Z
```

## Final Judgment

The model can describe the sign and rough mechanical scale of daily-reset leveraged-ETF rebalancing, but free historical data cannot prove when historical AUM records became known. Therefore history is descriptive only.

No output is a trading recommendation, alpha claim, market-impact estimate, dealer inventory estimate, or authorization to use this proxy as a standalone signal.

## Guardrails

- No external data fetched.
- No API/scraper/browser automation added.
- No raw provider data committed.
- No strict Phase 1.3 readiness run.
- No Phase 2 admission.
- No release or statistical backtest.
- No notification/trading/actionization.
- CTA and Dealer remain blocked.
- `actionization_allowed=false`.
