from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.morita_single_call_reference.s_single_call_reference_engine import (
    DEFAULT_BASELINE_DIR,
    DEFAULT_REFERENCE_OUTPUT_DIR,
    REFERENCE_REQUIRED_FILES,
    assert_no_actionization,
    build_reference_outputs,
    verify_manifest,
)


FORBIDDEN_OVERRIDES = ["--dte", "--delta", "--iv", "--markup", "--haircut", "--target", "--split", "--progress", "--max-holding", "--rank", "--ohlcv"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    if any(arg.split("=")[0] in FORBIDDEN_OVERRIDES for arg in argv):
        raise SystemExit("fixed_reference_model_rejects_parameter_override")
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline-run-dir", default=str(DEFAULT_BASELINE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_REFERENCE_OUTPUT_DIR))
    args = parser.parse_args(argv)
    if not args.run and not args.verify:
        parser.error("one of --run or --verify is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.run:
        receipt = build_reference_outputs(Path(args.baseline_run_dir), Path(args.output_dir))
        print({"status": receipt["status"], "eligible_trade_count": receipt["eligible_trade_count"], "path_coverage_rate": receipt["path_coverage_rate"]})
    if args.verify:
        result = verify_manifest(Path(args.output_dir), "s_single_call_reference_content_manifest.json", REFERENCE_REQUIRED_FILES)
        assert_no_actionization(Path(args.output_dir))
        print(result)
        if not result["verified"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
