# Flow Pressure Phase 1.3A.1 Validation Closure Summary

## Outcome

`local_full_suite_passed`

Classification: `no_material_regression`

Phase 1.3A validation gap was closed locally. The earlier 3-minute and 5-minute local timeouts were insufficient execution budgets for the existing slow sealed-artifact and tamper-verification suites. A first rerun with a still-long Windows temp path reproduced `FileNotFoundError` in deep readiness artifact paths; rerunning with very short temp paths under `C:\t\...` resolved that environment issue.

## Preflight

| Item | Value |
|---|---|
| Baseline commit | `5043368f1868264d88f71864435409ec084c64eb` |
| Current base commit | `5043368f1868264d88f71864435409ec084c64eb` plus Phase 1.3A working-tree changes |
| Python | `Python 3.12.13` |
| Pytest | `pytest 9.1.1` |
| OS | `Microsoft Windows 11 Home 10.0.26200 64-bit` |
| Collection count current | 334 tests |
| Collection change vs baseline | +24 tests, explained by new source qualification suite |
| Raw staging/provider files tracked | none from `git ls-files market_bomb_history` |
| Compile check | passed for `market_bomb_flow_pressure_source_qualification_v1.py` and `market_bomb_flow_pressure_research_v0.py` |

## Local Test Results

| Suite | Result | Duration | Notes |
|---|---:|---:|---|
| New Phase 1.3A qualification suite | 24 passed | 1.313s | `--durations=30` |
| Existing Flow Pressure research suite | 35 passed, 1 skipped | 226.284s | passed with `--basetemp C:\t\r` |
| Statistical backtest suite | 9 passed | 65.606s | `--durations=30` |
| Phase 0 safety regression set | 82 passed, 1 skipped | 274.420s | includes notifications, research, statistical, CTA/Vol, qualification |
| Full local suite | 332 passed, 2 skipped, 52 warnings | 1019.136s | passed with `--basetemp C:\t\f` |

## Baseline Runtime Comparison

Material-runtime investigation threshold was defined before interpretation:

```text
Flag for investigation if current runtime exceeds baseline by both:
- 25% or more; and
- 120 seconds or more
```

| Suite | Baseline | Current | Delta | Classification |
|---|---:|---:|---:|---|
| Flow Pressure research suite | 188.102s | 226.284s | +38.182s / +20.3% | expected_runtime_variation |
| Full suite | 1021.003s | 1019.136s | -1.867s / -0.2% | no_material_regression |

The current full suite includes 24 additional tests and still ran slightly faster than baseline under the same interpreter and short-temp setup.

## Slow-Test Attribution

The slowest current full-suite tests are existing sealed-artifact, tamper-verification, fragility release, and market-impact integration tests. The new qualification suite does not appear in the slowest 80 full-suite tests. The slowest added qualification test was `test_raw_provider_data_not_tracked_by_git` at 0.08s.

Root-cause classification: `expected sealed artifact hashing / tamper verification / full data fixture creation`

Code changes for runtime: none.

## GitHub Actions Status

Pending at the time this local validation artifact was created. After commit/push, `ci_validation_receipt.json` must be updated with the actual workflow run result.

## Guardrail Confirmation

- No provider API/network/scrape added.
- No raw provider data fetched.
- No raw provider data committed.
- No real Phase 1.3 readiness run.
- No real release or Phase 2 study/backtest.
- No Fragility Score change.
- No notification/trading/actionization change.
- CTA and Dealer remain blocked.
- `actionization_allowed=false`.
