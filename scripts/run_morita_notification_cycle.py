from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_notification_v2.cycle import read_csv_rows, run_notification_cycle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange-session-date", required=True)
    parser.add_argument("--eligible-sessions-csv", required=True, help="CSV with exchange_session_date column")
    parser.add_argument("--market-data-csv", help="Optional local daily rows: ticker,exchange_session_date,high,low,close,source")
    parser.add_argument("--narrow-status-csv", help="Optional local rows: ticker,narrow_leadership_status")
    args = parser.parse_args()
    with Path(args.eligible_sessions_csv).open("r", newline="", encoding="utf-8") as f:
        sessions = [row["exchange_session_date"] for row in csv.DictReader(f)]
    market = read_csv_rows(Path(args.market_data_csv)) if args.market_data_csv else []
    narrow = read_csv_rows(Path(args.narrow_status_csv)) if args.narrow_status_csv else []
    print(json.dumps(run_notification_cycle(args.exchange_session_date, sessions, market, narrow), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
