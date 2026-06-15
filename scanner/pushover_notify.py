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


def send_pushover_message(
    message: str,
    title: str = "Breakout Bot Alert",
    priority: int = 0,
    app_token: str | None = None,
    user_key: str | None = None,
    retry: int | None = None,
    expire: int | None = None,
    sound: str | None = None,
    timeout: int = 20,
    session: HTTPSession | None = None,
    raise_on_error: bool = True,
) -> dict[str, Any]:
    token = app_token or os.environ.get("PUSHOVER_APP_TOKEN", "")
    user = user_key or os.environ.get("PUSHOVER_USER_KEY", "")
    if not token or not user:
        raise ValueError("Pushover token/user key are required. Set PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY.")

    payload = {
        "token": token,
        "user": user,
        "title": title,
        "message": _truncate(message),
        "priority": priority,
    }
    if priority == 2:
        payload["retry"] = retry if retry is not None else 60
        payload["expire"] = expire if expire is not None else 600
        payload["sound"] = sound or "siren"
    elif sound:
        payload["sound"] = sound
    http = session or requests
    response = http.post(PUSHOVER_MESSAGES_URL, data=payload, timeout=timeout)
    result = {
        "status_code": getattr(response, "status_code", None),
        "text": getattr(response, "text", ""),
        "payload": safe_pushover_payload(payload),
    }
    if raise_on_error and getattr(response, "status_code", 200) >= 400:
        text = getattr(response, "text", "")
        raise RuntimeError(f"Pushover notification failed: {response.status_code} {text}")
    return result


def send_pushover_emergency(
    message: str,
    title: str = "A\u7d1a Breakout Alert",
    app_token: str | None = None,
    user_key: str | None = None,
    timeout: int = 20,
    session: HTTPSession | None = None,
) -> dict[str, Any]:
    return send_pushover_message(
        message,
        title=title,
        priority=2,
        app_token=app_token,
        user_key=user_key,
        retry=60,
        expire=600,
        sound="siren",
        timeout=timeout,
        session=session,
    )


def safe_pushover_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe = dict(payload)
    if "token" in safe:
        safe["token"] = bool(safe["token"])
    if "user" in safe:
        safe["user"] = bool(safe["user"])
    return safe


def _truncate(message: str, max_len: int = 1024) -> str:
    if len(message) <= max_len:
        return message
    suffix = "\n... truncated. See Discord/CSV for full scanner details."
    return message[: max_len - len(suffix)] + suffix
