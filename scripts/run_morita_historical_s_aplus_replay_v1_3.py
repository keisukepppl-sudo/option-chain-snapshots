from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
for import_root in [REPO_ROOT, SRC]:
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from research.historical_s_aplus_replay_v1_3 import parse_args, run_v1_3


def main() -> int:
    args = parse_args()
    output_root = args.output_dir if args.output_dir else None
    result = run_v1_3(REPO_ROOT, output_root=output_root)
    print(json.dumps({"output_dir": result.output_dir, "terminal_statuses": result.terminal_statuses}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
