from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "config" / "morita_notification_v2" / "ab_pullback_and_time_stop_spec.json"
OUTCOME_SPEC_PATH = REPO_ROOT / "config" / "morita_bot_historical_baseline_v1" / "underlying_outcome_spec_v1.json"

NON_ENTRY_TERMINAL_STATES = {"PULLBACK_INVALIDATED", "PULLBACK_EXPIRED", "BUY_ALERT_EXPIRED_NO_CHASE", "A_B_PULLBACK_RULE_UNRESOLVED"}
ACTIVE_STATES = {"ENTRY_CONFIRMED", "ACTIVE", "TIME_STOP_DUE"}
ALLOWED_ACK_REASONS = {"time_stop", "manual_close", "partial_reduce", "broker_sync_unavailable", "other_documented"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    return load_json(path)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_baseline_timeout_convention(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec or load_spec()
    source = REPO_ROOT / spec["baseline_timeout_convention_source"]
    outcome = load_json(source)
    required = spec["baseline_required"]
    for key, expected in required.items():
        if outcome.get(key) != expected:
            raise SystemExit(f"baseline_timeout_convention_mismatch:{key}")
    return {
        "status": "formal_baseline_timeout_convention_verified",
        "source": str(source.relative_to(REPO_ROOT)),
        "sha256": file_sha256(source),
        "entry_convention": outcome["entry_convention"],
        "target_return": outcome["target_return"],
        "outcome_window_sessions": outcome["outcome_window_sessions"],
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is None:
        columns = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def stable_id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def state_paths(spec: dict[str, Any] | None = None) -> dict[str, Path]:
    spec = spec or load_spec()
    local = spec["local_state"]
    return {
        "setup_registry": REPO_ROOT / local["setup_registry"],
        "ab_candidate_registry": REPO_ROOT / local["ab_candidate_registry"],
        "alert_events": REPO_ROOT / local["alert_events"],
        "manual_acknowledgements": REPO_ROOT / local["manual_acknowledgements"],
        "audit_output_dir": REPO_ROOT / local["audit_output_dir"],
    }


def alert_id(setup_id: str, alert_type: str, exchange_session_date: str, version: str = "v2") -> str:
    return stable_id(setup_id, alert_type, exchange_session_date, version)


def dedupe_alert(existing_events: list[dict[str, Any]], event: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    seen = {row.get("alert_id") for row in existing_events}
    if event["alert_id"] in seen:
        duplicate = dict(event)
        duplicate["delivery_status"] = "duplicate_suppressed"
        return False, duplicate
    event = dict(event)
    event.setdefault("delivery_status", "pending_delivery")
    return True, event


def latest_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get(key):
            out[str(row[key])] = row
    return out


def record_alert(path: Path, existing_events: list[dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
    should_write, payload = dedupe_alert(existing_events, event)
    if should_write:
        append_jsonl(path, payload)
    return payload
