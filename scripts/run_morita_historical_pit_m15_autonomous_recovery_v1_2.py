from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.research.pit_recovery.autonomous_recovery_v1_2 import run_v1_2


MODES = [
    "inspect-environment",
    "recover-github-evidence",
    "reaudit-signal-authority",
    "recover-pit-universe",
    "prepare-deterministic-rerun",
    "run-deterministic-rerun",
    "probe-webull-m15",
    "find-webull-retention-boundary",
    "backfill-signal-event-windows",
    "research-alternative-vendors",
    "join-authoritative-signals-m15",
    "recheck-short-readiness",
    "generate-user-action-file",
    "generate-review-bundle",
    "full-autonomous-run",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Morita Historical PIT + M15 autonomous recovery v1.2.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    for mode in MODES:
        parser.add_argument(f"--{mode}", action="store_true")
    return parser.parse_args()


def selected_mode(args: argparse.Namespace) -> str:
    selected = [mode for mode in MODES if getattr(args, mode.replace("-", "_"))]
    return selected[0] if selected else "full-autonomous-run"


def main() -> int:
    args = parse_args()
    result = run_v1_2(args.repo_root, output_root=args.output_root, run_id=args.run_id, mode=selected_mode(args))
    print(json.dumps({"output_dir": result.output_dir, "terminal_statuses": result.terminal_statuses}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
