from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scanner.pushover_notify import send_pushover_message


MESSAGES = {
    "normal": "Breakout Bot Pushover normal test. If you see this, normal notification works.",
    "high": "Breakout Bot Pushover high-priority test. If this appears prominently, priority=1 works.",
    "emergency": "Breakout Bot EMERGENCY test. This should ring/repeat until acknowledged.",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--priority", choices=["normal", "high", "emergency"], default="normal")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    priority_value = {"normal": 0, "high": 1, "emergency": 2}[args.priority]
    title = {
        "normal": "Breakout Bot Normal Test",
        "high": "Breakout Bot High Priority Test",
        "emergency": "Breakout Bot Emergency Test",
    }[args.priority]
    print(
        json.dumps(
            {
                "PUSHOVER_ENABLED": os.environ.get("PUSHOVER_ENABLED", ""),
                "PUSHOVER_APP_TOKEN_exists": bool(os.environ.get("PUSHOVER_APP_TOKEN")),
                "PUSHOVER_USER_KEY_exists": bool(os.environ.get("PUSHOVER_USER_KEY")),
                "request_payload": {
                    "priority": priority_value,
                    "retry": 60 if priority_value == 2 else None,
                    "expire": 600 if priority_value == 2 else None,
                    "sound": "siren" if priority_value == 2 else None,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    result = send_pushover_message(
        args.message or MESSAGES[args.priority],
        title=title,
        priority=priority_value,
        retry=60,
        expire=600,
        sound="siren" if priority_value == 2 else None,
        raise_on_error=False,
    )
    print(
        json.dumps(
            {
                "pushover_api_response_status": result.get("status_code"),
                "pushover_api_response_body": result.get("text"),
                "safe_request_payload_sent": result.get("payload"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
