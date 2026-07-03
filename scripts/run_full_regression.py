from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.test_quality_v1 import (
    DEFAULT_REGISTRY,
    build_pytest_command,
    cleanup_temp_root,
    create_short_temp_root,
    json_dumps,
    load_registry,
)


def print_command(command: list[str]) -> None:
    print("RUN:", " ".join(str(part) for part in command), flush=True)


def run_checked(command: list[str]) -> int:
    print_command(command)
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return int(completed.returncode)


def run_audit(args: argparse.Namespace) -> int:
    command = [
        args.python,
        "scripts/verify_pytest_collection_coverage.py",
        "--registry",
        args.registry,
        "--python",
        args.python,
    ]
    if args.artifacts_dir:
        Path(args.artifacts_dir).mkdir(parents=True, exist_ok=True)
        command.extend(["--json-output", str(Path(args.artifacts_dir) / "collection_coverage.json")])
    return run_checked(command)


def run_pytest_targets(args: argparse.Namespace, shard_id: str, targets: list[str]) -> int:
    temp_root = create_short_temp_root("p15e")
    started = time.perf_counter()
    try:
        command = build_pytest_command(args.python, targets, temp_root, durations=args.durations)
        result = run_checked(command)
        elapsed = time.perf_counter() - started
        if args.artifacts_dir:
            out = Path(args.artifacts_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{shard_id}_summary.json").write_text(
                json_dumps(
                    {
                        "shard_id": shard_id,
                        "returncode": result,
                        "elapsed_seconds": round(elapsed, 3),
                        "basetemp_parent": str(temp_root.parent),
                        "basetemp_cleaned": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        return result
    finally:
        cleanup_temp_root(temp_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic full-regression shards with short unique pytest temp roots.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--artifacts-dir", default="outputs/test_quality_v1")
    parser.add_argument("--durations", type=int, default=30)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--audit-only", action="store_true")
    group.add_argument("--all", action="store_true")
    group.add_argument("--shard", default="")
    group.add_argument("--windows-path-regression", action="store_true")
    args = parser.parse_args()

    registry = load_registry(Path(args.registry))
    if args.audit_only:
        return run_audit(args)
    if args.windows_path_regression:
        path_regression = registry["path_regression"]
        return run_pytest_targets(args, str(path_regression["shard_id"]), [str(target) for target in path_regression["pytest_targets"]])
    if args.shard:
        shards = {str(shard["shard_id"]): shard for shard in registry["shards"]}
        if args.shard not in shards:
            print(f"unknown shard: {args.shard}", file=sys.stderr)
            return 2
        shard = shards[args.shard]
        return run_pytest_targets(args, args.shard, [str(target) for target in shard["pytest_targets"]])
    if args.all:
        audit_code = run_audit(args)
        if audit_code != 0:
            return audit_code
        for shard in registry["shards"]:
            code = run_pytest_targets(args, str(shard["shard_id"]), [str(target) for target in shard["pytest_targets"]])
            if code != 0:
                return code
        return run_audit(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
