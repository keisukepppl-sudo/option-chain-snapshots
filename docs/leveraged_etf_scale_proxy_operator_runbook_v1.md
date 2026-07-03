# Leveraged ETF Scale Proxy Operator Runbook v1

## Scope

Use this runbook only for the standalone TQQQ/SQQQ capital-scaled mechanical proxy. Do not alter legacy free-proxy, CTA, Vol-control, dealer, 0DTE, market-impact, or Phase 1.5F artifacts.

## Source Qualification

1. Capture only official ProShares or SEC materials.
2. Store raw captures under:
   `market_bomb_history/leveraged_etf_scale_proxy_v1/manual_source_archive/<input_id>/`
3. Record SHA-256, acquisition UTC timestamp, source authority, claimed coverage, frequency, source tier, and qualification decision.
4. Do not treat capture time as historical availability.
5. Treat current snapshots as current snapshots only.
6. Treat SEC periodic records as anchor evidence only.

## Canonical Input

Create:

- `sources/benchmark_prices.csv`
- `sources/benchmark_mapping.csv`
- `sources/capital_observations.csv`
- `sources/leveraged_etf_prices.csv`
- `sources/split_history.csv`
- `sources/scale_source_evidence.json`
- `source_manifest.json`

Use `reported_aum_usd` as the selected capital input when reported AUM and shares times NAV both reconcile within 0.5%.

## Commands

Build a template:

`python market_bomb_leveraged_etf_scale_proxy_v1.py build-leveraged-etf-scale-template --input-id <input_id>`

Inspect:

`python market_bomb_leveraged_etf_scale_proxy_v1.py inspect-leveraged-etf-scale-input --input-id <input_id>`

Validate:

`python market_bomb_leveraged_etf_scale_proxy_v1.py validate-leveraged-etf-scale-input --input-id <input_id>`

Run only when validation passes and coverage is at least 90%:

`python market_bomb_leveraged_etf_scale_proxy_v1.py run-leveraged-etf-scale-historical-descriptive --input-id <input_id> --benchmark-mode ndx_exact --model-spec-id tqqq_sqqq_static_daily_reset_scale_v1`

Verify:

`python market_bomb_leveraged_etf_scale_proxy_v1.py verify-leveraged-etf-scale-run --run-artifact <exact_run_artifact_path>`

## Blocking Conditions

Stop without creating a historical run when:

- direct daily qualified capital is unavailable for either TQQQ or SQQQ;
- exact prior-session capital coverage is below 90%;
- AUM versus shares times NAV reconciliation exceeds 0.5%;
- QQQ proxy mapping is present;
- historical PIT eligibility is claimed without source proof;
- raw or canonical local data is tracked by git.

## Guardrails

Do not create trading, notification, sizing, execution, release, backtest, model-selection, ranking, or cross-module integration logic from this artifact.
