from __future__ import annotations

import os
from typing import Any, Protocol

import requests


PUSHOVER_MESSAGES_URL = "https://api.pushover.net/1/messages.json"


class HTTPSession(Protocol):
    def post(self, url: str, data: dict[str, Any], timeout: int) -> Any:
        ...


def env_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def pushover_enabled(env_var: str = "PUSHOVER_ENABLED") -> bool:
    return env_enabled(os.environ.get(env_var))


def send_pushover_emergency(
    message: str,
    title: str = "A\u7d1a Breakout Alert",
    app_token: str | None = None,
    user_key: str | None = None,
    timeout: int = 20,
    session: HTTPSession | None = None,
) -> None:
    token = app_token or os.environ.get("PUSHOVER_APP_TOKEN", "")
    user = user_key or os.environ.get("PUSHOVER_USER_KEY", "")
    if not token or not user:
        raise ValueError("Pushover token/user key are required. Set PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY.")

    payload = {
        "token": token,
        "user": user,
        "title": title,
        "message": _truncate(message),
        "priority": 2,
        "retry": 60,
        "expire": 1800,
        "sound": "siren",
    }
    http = session or requests
    response = http.post(PUSHOVER_MESSAGES_URL, data=payload, timeout=timeout)
    if getattr(response, "status_code", 200) >= 400:
        text = getattr(response, "text", "")
        raise RuntimeError(f"Pushover emergency notification failed: {response.status_code} {text}")


def _truncate(message: str, max_len: int = 1024) -> str:
    if len(message) <= max_len:
        return message
    suffix = "\n... truncated. See Discord/CSV for full scanner details."
    return message[: max_len - len(suffix)] + suffix
