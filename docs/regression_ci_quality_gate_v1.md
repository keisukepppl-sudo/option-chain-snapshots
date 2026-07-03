# Regression CI Quality Gate v1

This gate proves repository-wide pytest coverage through deterministic shards.

## Scope

The committed registry is `config/test_quality_v1/full_regression_shards.json`.

The canonical collection command is:

```powershell
python -m pytest --collect-only -q
```

Each collected test must belong to exactly one primary shard. The audit fails on duplicate, missing, or unexpected node IDs.

## Local Commands

Collection audit only:

```powershell
python scripts/run_full_regression.py --audit-only
```

Run one shard:

```powershell
python scripts/run_full_regression.py --shard flow_pressure_core
```

Run all primary shards:

```powershell
python scripts/run_full_regression.py --all
```

Run the Windows path-regression target set:

```powershell
python scripts/run_full_regression.py --windows-path-regression
```

## Windows Temp Strategy

The QQQ Phase 1 readiness tests create deep immutable artifact paths below `tmp_path`. On Windows, the default pytest temp root can exceed the practical 260-character path boundary and surface as `FileNotFoundError` even after parent creation.

The runner creates a short unique pytest `--basetemp` per shard. On Windows it first tries a writable `C:\t` parent, creates a unique `p15e_<id>` child, passes it to pytest, and removes only that unique child after the shard finishes. If that parent is not writable, it falls back to the platform temp directory.

This is a test orchestration fix. It does not change production artifact identity or market research semantics.

## CI Policy

The CI workflow has:

1. setup / syntax checks;
2. exact collection coverage audit;
3. deterministic primary regression shards;
4. additive Windows path-regression job;
5. completion summary.

The workflow must not use `continue-on-error`, failure masking, broad deselection, or ignore flags.

## Artifact Policy

Only test-quality outputs from `outputs/test_quality_v1` may be uploaded. The workflow must not upload `market_bomb_history`, raw provider data, canonical market inputs, releases, backtests, notifications, or trading artifacts.

## Guardrails

This quality gate is not a market research result, not a trading signal, not model selection, not Phase 2 admission, and not actionization permission.
