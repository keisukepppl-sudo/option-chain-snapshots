from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, request

from morita_cloud.runner import TickRunner


app = Flask(__name__)


@app.get("/healthz")
def healthz() -> tuple[Any, int]:
    return jsonify({"status": "ok"}), 200


@app.post("/tick")
def tick() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    force_action = payload.get("force_action")
    mock_time_et = payload.get("mock_time_et")

    overrides_enabled = os.environ.get("ALLOW_TEST_OVERRIDES", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if (force_action or mock_time_et) and not overrides_enabled:
        return jsonify({"status": "forbidden", "reason": "test overrides are disabled"}), 403

    try:
        result = TickRunner.from_env().run(
            timestamp_et=mock_time_et,
            force_action=force_action,
        )
        return jsonify(result.as_dict()), 200
    except Exception as exc:
        app.logger.exception("Morita Cloud Run tick failed")
        return jsonify({"status": "error", "error": str(exc)}), 500
