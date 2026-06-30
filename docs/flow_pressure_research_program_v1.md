# Flow Pressure Research Program v1

This program is a phased research-only path for Flow Pressure work.

It does not modify Fragility Score formulas, Morita notifications, candidate ranking, trading, sizing, or execution. Every research output remains non-actionable:

```text
actionization_allowed=false
raw_provider_data_committed=false
is_observed_flow=false
is_model_estimate=true
```

## Phase Order

Phases must be completed in order:

1. Phase 0: CI stabilization.
2. Phase 1: real-data readiness and manual local staging.
3. Phase 2: first QQQ / SOXL-family timing-valid study.
4. Phase 3: reproducibility and independent replication gate.
5. Phase 4: CTA data contract and research implementation.
6. Phase 5: dealer gamma-regime data contract and research implementation.

Do not start a later phase until the prior phase has a documented pass gate.

## Phase 0 Result

Phase 0 stabilizes local and CI test execution before additional research changes.

Audit findings:

- `requirements.txt` already declares runtime/test imports including `requests`, `beautifulsoup4`, and `pytest`.
- No dedicated clean test-install route existed before this phase.
- No repository-level pytest collection config existed, so default pytest collection could include non-test scripts such as `scripts/pushover_test.py`.
- Notification tests now use injected HTTP sessions and deterministic mocks for Discord and Pushover. They do not require live webhook URLs, Pushover tokens, or real network calls.
- The slow Fragility release suite is slow because it repeatedly builds, verifies, tampers, and re-verifies sealed release artifacts. The slow behavior is expected integrity coverage, not a live-network dependency or collection failure.

Phase 0 implementation:

- Added `requirements-dev.txt` as the clean development/test install route.
- Added `pytest.ini` to collect only `tests/test_*.py`.
- Added `.github/workflows/ci.yml` for push and pull request CI.
- Made notification modules import optional network dependencies only when a real HTTP session is needed.
- Added a mocked Pushover notification unit test.

Phase 0 CI route:

```powershell
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -m py_compile market_bomb_flow_pressure_research_v0.py market_bomb_flow_pressure_statistical_backtest_v1.py market_bomb_fragility_data_release_v0.py market_bomb_fragility_score_v0.py market_bomb_phase3_2_cta_vol_proxy.py discord_alert.py scanner/pushover_notify.py
python -m pytest tests/test_notifications.py tests/test_market_bomb_flow_pressure_research_v0.py tests/test_market_bomb_flow_pressure_statistical_backtest_v1.py tests/test_market_bomb_phase3_2_cta_vol_proxy.py -q
python -m pytest -q --durations=20
```

## Fragility Slow-Suite Note

The Fragility release suite completed locally under the documented long timeout:

```text
tests/test_market_bomb_fragility_data_release_v0.py
22 passed, 1 skipped in 306.66s
```

The slowest tests were release build/verify and tamper-detection paths, with individual test durations around 12 to 44 seconds. These tests are intentionally retained in the full suite because they protect release immutability, exact-file-set validation, stale data behavior, and tamper detection.

## Phase 1 Gate

Phase 1 may start only after the full suite passes with:

```powershell
python -m pytest -q
```

Phase 1 must keep real provider data local-only. It may add readiness templates, validation, timing audit, coverage reports, and operator documentation, but it must not fetch provider data or claim a real-data result when no valid local real data exists.

## Phase 1 QQQ Readiness

Phase 1 adds a readiness-only workflow for QQQ/TQQQ/SQQQ:

```powershell
python market_bomb_flow_pressure_research_v0.py run-qqq-phase1-readiness --staging-id <opaque_staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py verify-qqq-phase1-readiness --staging-id <opaque_staging_id>
```

The workflow writes `real_data_readiness_report.md` and related CSV/JSON audits under the staging directory. It does not build a release, run a real-data study, run a statistical backtest, alter Fragility Score, or create trading/notification behavior.

## QQQ Phase 1.1 PIT Readiness

QQQ/TQQQ/SQQQ Phase 1 historical readiness requires a manifest-declared `decision_schedule.csv` and row-level point-in-time audit outputs. Use `run-qqq-phase1-readiness --decision-schedule-file sources/decision_schedule.csv`; do not use a single global decision timestamp for multi-date historical readiness. See `docs/flow_pressure_qqq_phase1_point_in_time_audit_v1.md`.

## QQQ Phase 1.2 Hardening

Phase 1.2 requires explicit schedule paths, immutable run-scoped readiness artifacts, and a complete candidate-selection audit. Phase 2 admission must use `validate-phase2-qqq-admission --readiness-artifact <readiness-run-path>` against one sealed readiness run. The admission command is a preflight only; it does not build a release, run a study, run a backtest, change scores, or enable actionization. See `docs/flow_pressure_qqq_phase1_hardening_v1.md`.

## Phase 1.3A Source Qualification

Phase 1.3A corrects the QQQ/TQQQ/SQQQ data-source design before real-data intake:

```text
primary_target_benchmark = NDX
tradable_market_proxy = QQQ
```

TQQQ and SQQQ must not be treated as exact QQQ benchmark mappings in production-like readiness. Current revised historical exports without publication/revision evidence remain descriptive only.

## Phase 1.3B Free Leveraged-ETF Proxy

Phase 1.3B adds a separate free-data directional-amplifier proxy for TQQQ/SQQQ. It estimates only the sign and rough mechanical scale of daily-reset rebalance pressure:

```text
estimated_rebalance_notional = L * (L - 1) * A * r
```

Supported modes:

```text
historical_free_descriptive_proxy
forward_pit_lite_observation
```

This module is research context only. It must not be used as a standalone buy/sell signal. It cannot unlock Phase 1.3 strict readiness, Phase 2 admission, Flow release, Flow statistical backtest, notifications, trading, sizing, execution, or actionization.

See:

- `docs/leveraged_etf_free_directional_proxy_v1.md`
- `docs/leveraged_etf_free_proxy_operator_runbook_v1.md`
