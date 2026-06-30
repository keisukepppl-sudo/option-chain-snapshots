# ChatGPT Bundle: Flow Pressure Phase 1.3A.1 Validation Closure

## Objective

Close the validation gap left after Phase 1.3A. The prior short local runs timed out at 3 and 5 minutes, so this phase reran tests with adequate runtime, attributed slow tests, compared baseline `5043368` against current Phase 1.3A changes, and prepared CI validation artifacts.

## Scope

Validation only. No real-data intake, no Phase 2, no provider data, no release, no backtest study, no notifications, no trading/actionization.

## Preflight

- Python: `Python 3.12.13`
- Pytest: `pytest 9.1.1`
- OS: `Microsoft Windows 11 Home 10.0.26200 64-bit`
- Current collection: `334 tests`
- Baseline collection: `310 tests`
- Collection change: `+24`, explained by new Phase 1.3A qualification tests
- Compile checks: passed
- Raw staging tracked by git: none

## Key Environment Finding

Using `C:\tmp\option_chain_pytest_phase1_3a1_targeted` was still too long for deep Windows readiness artifact paths and caused `FileNotFoundError`.

Using very short temp paths under `C:\t\...` resolved the issue.

## Test Results

| Suite | Result | Duration |
|---|---:|---:|
| New Phase 1.3A qualification suite | 24 passed | 1.313s |
| Existing Flow Pressure research suite | 35 passed, 1 skipped | 226.284s |
| Statistical backtest suite | 9 passed | 65.606s |
| Phase 0 safety regression set | 82 passed, 1 skipped | 274.420s |
| Full local suite | 332 passed, 2 skipped, 52 warnings | 1019.136s |

## Baseline Comparison

| Suite | Baseline `5043368` | Current Phase 1.3A | Classification |
|---|---:|---:|---|
| Flow Pressure research suite | 188.102s | 226.284s | expected runtime variation |
| Full suite | 1021.003s | 1019.136s | no material regression |

Pre-run investigation threshold:

```text
current runtime exceeds baseline by both 25%+ and 120s+
```

No suite crossed this threshold.

## Slow-Test Attribution

Slow tests are existing sealed-artifact, tamper-verification, release-integrity, and market-impact integration tests. The new qualification suite does not appear in the slowest 80 full-suite tests. No runtime code fix was needed.

## Local Conclusion

```text
local_full_suite_passed
no_material_regression
```

## CI Status

GitHub Actions passed for commit:

```text
851609f74b93a601be811db7883bc1d5bfcbed39
```

Workflow:

```text
CI
run: https://github.com/keisukepppl-sudo/option-chain-snapshots/actions/runs/28451107788
job: tests
job status: completed / success
started: 2026-06-30T14:15:30Z
completed: 2026-06-30T14:28:04Z
```

The workflow includes targeted safety suites and full test suite steps.

## Guardrails

- No provider API/network/scrape added.
- No raw provider data fetched or committed.
- No real Phase 1.3 readiness run.
- No real release or Phase 2 study/backtest.
- No Fragility Score change.
- No notification/trading/actionization.
- CTA and Dealer remain blocked.
- `actionization_allowed=false`.
