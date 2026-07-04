from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.morita_long_call_completion_research.engine import PAUSE_OUTPUT_DIR, build_pause_outputs, verify_pause_manifest  # noqa: E402


FORBIDDEN_OVERRIDES = ["--dte", "--delta", "--iv", "--markup", "--haircut", "--target", "--split", "--rank", "--state", "--threshold"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    if any(arg.split("=")[0] in FORBIDDEN_OVERRIDES for arg in argv):
        raise SystemExit("pause_research_rejects_parameter_override")
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output-dir", default=str(PAUSE_OUTPUT_DIR))
    args = parser.parse_args(argv)
    if not args.run and not args.verify:
        parser.error("one of --run or --verify is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.run:
        receipt = build_pause_outputs(Path(args.output_dir))
        print({"status": receipt["status"], "eligible_trade_count": receipt["eligible_trade_count"]})
    if args.verify:
        result = verify_pause_manifest(Path(args.output_dir))
        print(result)
        if not result["verified"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

