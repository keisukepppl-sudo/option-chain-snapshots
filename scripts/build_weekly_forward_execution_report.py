from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_notification_v2.notification_state_machine import read_jsonl, state_paths, write_csv
from src.morita_notification_v2.weekly_report import build_weekly_rows


def main() -> int:
    paths = state_paths()
    rows = build_weekly_rows(
        read_jsonl(paths["ab_candidate_registry"]),
        read_jsonl(paths["alert_events"]),
        read_jsonl(paths["setup_registry"]),
        read_jsonl(paths["manual_acknowledgements"]),
    )
    output = paths["audit_output_dir"] / "weekly_forward_execution_summary.csv"
    write_csv(output, rows)
    print(json.dumps({"status": "weekly_forward_execution_report_completed", "output": str(output)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
