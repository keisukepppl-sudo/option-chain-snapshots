from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "aws" / "pushover_healthcheck" / "lambda_function.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aws_pushover_healthcheck_lambda", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_payload_masks_credentials(monkeypatch):
    module = load_module()
    monkeypatch.setenv("PUSHOVER_ENABLED", "true")
    monkeypatch.setenv("PUSHOVER_APP_TOKEN", "app-token")
    monkeypatch.setenv("PUSHOVER_USER_KEY", "user-key")
    monkeypatch.setenv("PUSHOVER_PRIORITY", "2")
    monkeypatch.setenv("PUSHOVER_RETRY", "60")
    monkeypatch.setenv("PUSHOVER_EXPIRE", "600")
    monkeypatch.setenv("PUSHOVER_SOUND", "climb")

    payload = module._pushover_payload({"message": "test"})
    safe = module._safe_payload_for_log(payload)

    assert payload["token"] == "app-token"
    assert payload["user"] == "user-key"
    assert payload["priority"] == 2
    assert payload["retry"] == 60
    assert payload["expire"] == 600
    assert payload["sound"] == "climb"
    assert "token" not in safe
    assert "user" not in safe
    assert safe["token_exists"] is True
    assert safe["user_key_exists"] is True


def test_disabled_handler_does_not_send(monkeypatch):
    module = load_module()
    monkeypatch.setenv("PUSHOVER_ENABLED", "false")
    monkeypatch.setenv("PUSHOVER_APP_TOKEN", "app-token")
    monkeypatch.setenv("PUSHOVER_USER_KEY", "user-key")

    def fail_send(payload):
        raise AssertionError("send_pushover should not be called when disabled")

    monkeypatch.setattr(module, "send_pushover", fail_send)
    result = module.lambda_handler({"message": "test"}, None)

    assert result["sent"] is False
    assert result["reason"] == "PUSHOVER_ENABLED is false"
