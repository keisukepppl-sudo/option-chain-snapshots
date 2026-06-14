from __future__ import annotations

import os
from typing import Any, Protocol

import requests


class HTTPSession(Protocol):
    def post(self, url: str, json: dict[str, Any], timeout: int) -> Any:
        ...


def send_discord_alert(
    message: str,
    webhook_url: str | None = None,
    env_var: str = "STOCK",
    username: str = "Russell1000 Minervini Scanner",
    timeout: int = 20,
    session: HTTPSession | None = None,
) -> None:
    url = webhook_url or os.environ.get(env_var, "")
    if not url:
        raise ValueError(f"Discord webhook URL is required. Set GitHub Secret/env var {env_var}.")

    payload = {
        "username": username,
        "content": _truncate(message),
    }
    http = session or requests
    response = http.post(url, json=payload, timeout=timeout)
    if getattr(response, "status_code", 204) >= 400:
        text = getattr(response, "text", "")
        raise RuntimeError(f"Discord webhook failed: {response.status_code} {text}")


def _truncate(message: str, max_len: int = 1900) -> str:
    if len(message) <= max_len:
        return message
    suffix = "\n... truncated. See CSV artifact for the full candidate list."
    return message[: max_len - len(suffix)] + suffix
