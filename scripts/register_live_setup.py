from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_notification_v2.cycle import register_setup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-json", required=True, help="JSON file with a confirmed Webull fill or manual entry registration")
    args = parser.parse_args()
    payload = json.loads(Path(args.setup_json).read_text(encoding="utf-8"))
    print(json.dumps(register_setup(payload), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
