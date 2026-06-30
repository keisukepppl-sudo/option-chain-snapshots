# Slow-Test Attribution

## Current Full Suite Slowest Tests

| Rank | Test | Duration | Attribution |
|---:|---|---:|---|
| 1 | `tests/test_market_bomb_market_impact_backtest_v1.py::test_v113_run_nonempty_actual_lineage_parity_and_bucket_fixture` | 59.24s | existing market impact integration / lineage parity |
| 2 | `tests/test_market_bomb_fragility_data_release_v0.py::test_run_score_creates_append_only_execution_outputs` | 46.29s | existing fragility release execution artifact generation |
| 3 | `tests/test_market_bomb_market_impact_backtest_v1.py::test_run_writes_outputs_and_actionization_false` | 43.50s | existing market impact output and guardrail test |
| 4 | `tests/test_market_bomb_fragility_data_release_v0.py::test_verify_execution_detects_output_tamper_extra_file_and_release_core_change` | 32.89s | existing tamper verification |
| 5 | `tests/test_market_bomb_fragility_data_release_v0.py::test_verify_staging_full_preflight_no_write_and_build_parity` | 31.65s | existing full preflight/build parity |
| 8 | `tests/test_market_bomb_flow_pressure_research_v0.py::test_qqq_phase1_readiness_runs_are_append_only` | 26.99s | existing QQQ readiness append-only sealed artifacts |

The new Phase 1.3A source qualification suite does not appear in the current full-suite slowest 80 tests.

## Added Suite Slowest Test

| Test | Duration | Attribution |
|---|---:|---|
| `tests/test_market_bomb_flow_pressure_source_qualification_v1.py::test_raw_provider_data_not_tracked_by_git` | 0.08s | git tracked-file safety check |

## Baseline vs Current

| Suite | Baseline | Current | Interpretation |
|---|---:|---:|---|
| Flow Pressure research suite | 188.102s | 226.284s | +38.182s / +20.3%, below investigation threshold |
| Full suite | 1021.003s | 1019.136s | current is slightly faster despite +24 tests |

## Root-Cause Classification

`expected_runtime_variation`

Slow tests are dominated by pre-existing sealed-artifact hashing, tamper verification, append-only readiness, and full fixture generation. No Phase 1.3A-introduced material runtime regression was found.

## Environment Finding

The failed current research run under `C:\tmp\option_chain_pytest_phase1_3a1_targeted` produced `FileNotFoundError` while writing deep readiness artifact paths. The same suite passed with `--basetemp C:\t\r`. This is a Windows path-length/temp-path issue, not a functional regression.

## Code Changes

No runtime code fix was needed for validation closure.

## Why Slow Tests Remain

The slow tests enforce immutable artifact, tamper detection, point-in-time, release integrity, and actionization guardrails. They should remain in the suite.
