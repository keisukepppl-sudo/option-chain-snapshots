from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from morita_unified_flow_v3_8_pit_band_recovery.engine import run_v3_8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Morita Unified Flow v3.8 PIT band recovery.")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = run_v3_8(REPO_ROOT, output_dir=args.output_dir)
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

