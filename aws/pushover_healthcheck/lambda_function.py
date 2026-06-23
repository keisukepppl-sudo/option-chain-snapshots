from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo


PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
JST = ZoneInfo("Asia/Tokyo")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _pushover_payload(event: dict | None = None) -> dict[str, str | int]:
    event = event or {}
    now_jst = datetime.now(tz=JST).strftime("%Y-%m-%d %H:%M:%S JST")
    token = os.environ.get("PUSHOVER_APP_TOKEN") or os.environ.get("PUSHOVER_API_TOKEN")
    if not token:
        raise RuntimeError("Missing required environment variable: PUSHOVER_APP_TOKEN or PUSHOVER_API_TOKEN")
    user_key = _required_env("PUSHOVER_USER_KEY")

    priority = int(os.environ.get("PUSHOVER_PRIORITY", event.get("priority", 2)))
    retry = int(os.environ.get("PUSHOVER_RETRY", event.get("retry", 60)))
    expire = int(os.environ.get("PUSHOVER_EXPIRE", event.get("expire", 600)))
    sound = str(os.environ.get("PUSHOVER_SOUND", event.get("sound", "climb")))
    title = str(os.environ.get("PUSHOVER_TITLE", event.get("title", "AWS 04:30 Health Check")))
    message = str(
        event.get(
            "message",
            (
                "AWS EventBridge -> Lambda -> Pushover health check.\n"
                "If this arrived near 04:30 JST, AWS notification path works.\n"
                f"actual_run_time_jst: {now_jst}"
            ),
        )
    )

    payload: dict[str, str | int] = {
        "token": token,
        "user": user_key,
        "title": title,
        "message": message,
        "priority": priority,
        "sound": sound,
    }
    if priority == 2:
        payload["retry"] = retry
        payload["expire"] = expire
    return payload


def _safe_payload_for_log(payload: dict[str, str | int]) -> dict[str, str | int | bool]:
    safe = dict(payload)
    safe["token_exists"] = bool(safe.pop("token", ""))
    safe["user_key_exists"] = bool(safe.pop("user", ""))
    return safe


def send_pushover(payload: dict[str, str | int]) -> dict[str, str | int]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(PUSHOVER_API_URL, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
        return {"status_code": response.status, "body": body}


def lambda_handler(event, context):
    event = event or {}
    enabled = _truthy(os.environ.get("PUSHOVER_ENABLED", "true"))
    payload = _pushover_payload(event)
    safe_payload = _safe_payload_for_log(payload)

    print(
        json.dumps(
            {
                "pushover_enabled": enabled,
                "safe_payload": safe_payload,
                "event": event,
            },
            ensure_ascii=False,
            default=str,
        )
    )

    if not enabled:
        return {"sent": False, "reason": "PUSHOVER_ENABLED is false", "safe_payload": safe_payload}

    result = send_pushover(payload)
    print(json.dumps({"pushover_result": result}, ensure_ascii=False, default=str))
    return {"sent": True, "result": result, "safe_payload": safe_payload}
