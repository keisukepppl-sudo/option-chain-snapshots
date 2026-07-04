from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_notification_v2.cycle import acknowledge_exit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-id", required=True)
    parser.add_argument("--reason", required=True, choices=["time_stop", "manual_close", "partial_reduce", "broker_sync_unavailable", "other_documented"])
    parser.add_argument("--note", default="")
    parser.add_argument("--source", default="manual")
    args = parser.parse_args()
    print(json.dumps(acknowledge_exit(args.setup_id, args.reason, args.note, args.source), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
