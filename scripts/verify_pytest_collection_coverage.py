from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.test_quality_v1 import DEFAULT_REGISTRY, collect_coverage, json_dumps, load_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify deterministic pytest shard coverage against canonical collection.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--json-output", default="")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    registry = load_registry(Path(args.registry))
    result = collect_coverage(registry, args.python)
    text = json_dumps(result)
    print(text)
    if args.json_output:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("coverage_equal") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
