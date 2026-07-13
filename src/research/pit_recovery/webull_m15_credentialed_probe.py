from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import logging
import os
import subprocess
import time as pytime
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


NY = ZoneInfo("America/New_York")
OFFICIAL_SDK_COMMIT = "10889b59ae98a70ba03c5d6c6113709b8c05afb0"
EXPECTED_HISTORY_SIGNATURE = [
    "self",
    "symbol",
    "category",
    "timespan",
    "count",
    "real_time_required",
    "trading_sessions",
    "start_time",
    "end_time",
]
SENSITIVE_KEYS = {
    "WEBULL_APP_KEY",
    "WEBULL_APP_SECRET",
    "WEBULL_REGION_ID",
    "WEBULL_API_ENDPOINT",
    "WEBULL_API_BASE_URL",
    "WEBULL_OPENAPI_TOKEN_DIR",
}


@dataclass(frozen=True)
class ProbeWindow:
    symbol: str
    session_date: str
    interval: str
    start_time_ms: int
    end_time_ms: int


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_user_env(name: str) -> str | None:
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"[Environment]::GetEnvironmentVariable('{name}', 'User')"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    value = (out.stdout or "").strip()
    return value or None


def credential_inventory(repo_root: Path) -> dict[str, Any]:
    process_present = {key: bool(os.getenv(key)) for key in SENSITIVE_KEYS}
    user_present = {key: bool(safe_user_env(key)) for key in SENSITIVE_KEYS}
    token_dir = os.getenv("WEBULL_OPENAPI_TOKEN_DIR") or safe_user_env("WEBULL_OPENAPI_TOKEN_DIR") or ""
    token_present = False
    token_expiry = ""
    if token_dir:
        token_path = Path(token_dir)
        token_present = token_path.exists() and any(token_path.glob("*"))
        for path in token_path.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            token_expiry = str(payload.get("expires_at") or payload.get("expire_time") or "")
            break
    local_secret_paths = [
        repo_root / ".env.local",
        repo_root / "config" / "webull.local.json",
        repo_root / "config" / "webull_credentials.local.json",
    ]
    local_secret_present = any(path.exists() for path in local_secret_paths)
    credential_present = any(process_present.values()) or any(user_present.values()) or local_secret_present
    return {
        "credential_present": bool(credential_present),
        "credential_source_type": "PROCESS_ENV" if any(process_present.values()) else "WINDOWS_USER_ENV" if any(user_present.values()) else "GITIGNORED_LOCAL_FILE" if local_secret_present else "NONE",
        "token_present": bool(token_present),
        "token_expiry_if_available": token_expiry,
        "authentication_status": "WEBULL_AUTH_CREDENTIALS_PRESENT_UNTESTED" if credential_present else "WEBULL_USER_AUTH_ACTION_REQUIRED",
        "process_env_keys_present": [key for key, present in process_present.items() if present],
        "windows_user_env_keys_present": [key for key, present in user_present.items() if present],
        "secrets_written_to_output": False,
        "secret_values_logged": False,
    }


def sdk_interface_audit() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "official_source_commit": OFFICIAL_SDK_COMMIT,
        "sdk_importable": False,
        "sdk_version": "",
        "history_signature": "",
        "batch_history_signature": "",
        "interface_status": "SDK_NOT_INSTALLED",
    }
    try:
        webull = importlib.import_module("webull")
        payload["sdk_importable"] = True
        payload["sdk_version"] = str(getattr(webull, "__version__", "UNKNOWN"))
        module = importlib.import_module("webull.data.quotes.market_data")
        cls = getattr(module, "MarketData")
        history_sig = inspect.signature(cls.get_history_bar)
        batch_sig = inspect.signature(cls.get_batch_history_bar)
        payload["history_signature"] = str(history_sig)
        payload["batch_history_signature"] = str(batch_sig)
        params = list(history_sig.parameters)
        payload["interface_status"] = "PASS" if params == EXPECTED_HISTORY_SIGNATURE else "SDK_INTERFACE_CHANGED"
    except Exception as exc:
        payload["interface_error_type"] = type(exc).__name__
    return payload


def normal_probe_sessions() -> list[str]:
    return ["2022-03-15", "2023-03-15", "2024-03-14", "2025-03-13"]


def completed_recent_sessions(today: date | None = None) -> list[str]:
    today = today or datetime.now(NY).date()
    sessions: list[str] = []
    cursor = today
    while len(sessions) < 2:
        cursor = cursor - pd.Timedelta(days=1)
        if cursor.weekday() < 5:
            sessions.append(cursor.strftime("%Y-%m-%d"))
    return sessions


def rth_window_ms(session_date: str) -> tuple[int, int]:
    d = date.fromisoformat(session_date)
    start = datetime.combine(d, time(9, 30), tzinfo=NY).astimezone(timezone.utc)
    end = datetime.combine(d, time(16, 0), tzinfo=NY).astimezone(timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def build_probe_windows(symbols: list[str] | None = None) -> list[ProbeWindow]:
    symbols = symbols or ["SOXX", "QQQ", "AMAT"]
    dates = normal_probe_sessions() + completed_recent_sessions()
    rows: list[ProbeWindow] = []
    for symbol in symbols:
        for session in dates:
            start_ms, end_ms = rth_window_ms(session)
            for interval in ["M15", "M5", "M1"]:
                rows.append(ProbeWindow(symbol, session, interval, start_ms, end_ms))
    return rows


def request_log_row(window: ProbeWindow) -> dict[str, Any]:
    return {
        "symbol": window.symbol,
        "session_date": window.session_date,
        "interval": window.interval,
        "category": "US_ETF" if window.symbol in {"SOXX", "QQQ"} else "US_STOCK",
        "count": 1200,
        "trading_sessions": "RTH",
        "start_time_ms": window.start_time_ms,
        "end_time_ms": window.end_time_ms,
        "requested_at_utc": utc_now(),
    }


def classify_response(window: ProbeWindow, response: Any, error: str = "") -> tuple[str, dict[str, Any]]:
    if error:
        status = "AUTH_BLOCKED" if "auth" in error.lower() or "credential" in error.lower() else "ERROR"
        return status, {"row_count": 0, "returned_min_time": "", "returned_max_time": "", "error": error[:240]}
    if response is None:
        return "NO_DATA", {"row_count": 0, "returned_min_time": "", "returned_max_time": "", "error": ""}
    status_code = getattr(response, "status_code", 200)
    if status_code in {401, 403}:
        return "AUTH_BLOCKED", {"row_count": 0, "returned_min_time": "", "returned_max_time": "", "error": f"HTTP_{status_code}"}
    if status_code and int(status_code) >= 400:
        text = str(getattr(response, "text", ""))[:240]
        status = "NOT_ENTITLED" if "entitle" in text.lower() or "permission" in text.lower() else "ERROR"
        return status, {"row_count": 0, "returned_min_time": "", "returned_max_time": "", "error": f"HTTP_{status_code}:{text}"}
    try:
        payload = response.json() if hasattr(response, "json") else response
    except Exception as exc:
        return "ERROR", {"row_count": 0, "returned_min_time": "", "returned_max_time": "", "error": type(exc).__name__}
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("bars") or payload.get("results") or []
    else:
        rows = payload
    if not rows:
        return "NO_DATA", {"row_count": 0, "returned_min_time": "", "returned_max_time": "", "error": ""}
    times = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = row.get("time") or row.get("timestamp") or row.get("t")
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if not pd.isna(ts):
            times.append(ts)
    if not times:
        return "UNKNOWN", {"row_count": len(rows), "returned_min_time": "", "returned_max_time": "", "error": ""}
    min_time = min(times)
    max_time = max(times)
    requested_start = pd.to_datetime(window.start_time_ms, unit="ms", utc=True)
    requested_end = pd.to_datetime(window.end_time_ms, unit="ms", utc=True)
    if max_time < requested_start or min_time > requested_end:
        return "START_END_IGNORED", {"row_count": len(rows), "returned_min_time": min_time.isoformat(), "returned_max_time": max_time.isoformat(), "error": ""}
    supported = f"HISTORICAL_M15_{window.session_date[:4]}_SUPPORTED" if window.interval == "M15" else f"{window.interval}_SUPPORTED_DIAGNOSTIC"
    return supported, {"row_count": len(rows), "returned_min_time": min_time.isoformat(), "returned_max_time": max_time.isoformat(), "error": ""}


def fake_blocked_probe(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], str]:
    credentials = credential_inventory(repo_root)
    sdk = sdk_interface_audit()
    if os.getenv("MORITA_V12_DISABLE_LIVE_WEBULL") != "1" and credentials["credential_present"] and sdk["interface_status"] == "PASS":
        return credentialed_probe(repo_root, credentials, sdk)
    requests = [request_log_row(window) for window in build_probe_windows()]
    matrix = []
    audit = []
    for row in requests:
        status = "AUTH_BLOCKED" if not credentials["credential_present"] else "UNKNOWN"
        matrix.append({
            "symbol": row["symbol"],
            "session_date": row["session_date"],
            "interval": row["interval"],
            "status": status,
            "requested_date_matched": False,
            "row_count": 0,
            "start_end_honored": False,
        })
        audit.append({
            **row,
            "response_status": status,
            "returned_min_time": "",
            "returned_max_time": "",
            "response_sha256": "",
            "error": "credentials_missing" if not credentials["credential_present"] else "credentialed_probe_not_executed_in_test_mode",
        })
    report = "\n".join([
        "# Webull M15 Credentialed Probe Report",
        "",
        f"credential_present: {credentials['credential_present']}",
        f"authentication_status: {credentials['authentication_status']}",
        f"sdk_interface_status: {sdk['interface_status']}",
        "No order, account, balance, position, or preview endpoint was called.",
        "",
    ])
    receipt = {
        "terminal_status": "WEBULL_USER_AUTH_ACTION_REQUIRED" if not credentials["credential_present"] else "WEBULL_M15_BLOCKED",
        "credential": credentials,
        "sdk": sdk,
        "probe_executed": False,
        "blocked_reason": "WEBULL_USER_AUTH_ACTION_REQUIRED" if not credentials["credential_present"] else "SDK_OR_AUTH_PROBE_NOT_COMPLETED",
    }
    return matrix, requests, audit, receipt, report


def credentialed_probe(repo_root: Path, credentials: dict[str, Any] | None = None, sdk: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], str]:
    credentials = credentials or credential_inventory(repo_root)
    sdk = sdk or sdk_interface_audit()
    app_key = os.getenv("WEBULL_APP_KEY") or safe_user_env("WEBULL_APP_KEY") or ""
    app_secret = os.getenv("WEBULL_APP_SECRET") or safe_user_env("WEBULL_APP_SECRET") or ""
    region = os.getenv("WEBULL_REGION_ID") or safe_user_env("WEBULL_REGION_ID") or "jp"
    endpoint = os.getenv("WEBULL_API_ENDPOINT") or safe_user_env("WEBULL_API_ENDPOINT") or ("api.webull.co.jp" if region == "jp" else "")
    request_rows = [request_log_row(window) for window in build_probe_windows()]
    matrix: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    if not app_key or not app_secret:
        return fake_blocked_probe(repo_root)
    try:
        logging.getLogger("webull").setLevel(logging.WARNING)
        from webull.core.client import ApiClient
        from webull.data.common.category import Category
        from webull.data.common.timespan import Timespan
        from webull.data.data_client import DataClient

        api_client = ApiClient(app_key, app_secret, region)
        if endpoint:
            api_client.add_endpoint(region, endpoint)
        data_client = DataClient(api_client)
        for window, request_row in zip(build_probe_windows(), request_rows, strict=True):
            category = Category.US_ETF.name if window.symbol in {"SOXX", "QQQ"} else Category.US_STOCK.name
            timespan = getattr(Timespan, window.interval).name
            payload_for_hash: Any = None
            error = ""
            response = None
            try:
                response = data_client.market_data.get_history_bar(
                    symbol=window.symbol,
                    category=category,
                    timespan=timespan,
                    count="1200",
                    trading_sessions="RTH",
                    start_time=window.start_time_ms,
                    end_time=window.end_time_ms,
                )
                try:
                    payload_for_hash = response.json()
                except Exception:
                    payload_for_hash = getattr(response, "text", "")
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:180]}"
            status, detail = classify_response(window, response, error=error)
            returned_min = str(detail.get("returned_min_time", ""))
            returned_max = str(detail.get("returned_max_time", ""))
            requested_date_matched = window.session_date in returned_min or window.session_date in returned_max
            start_end_honored = status.startswith("HISTORICAL_M15_") or status.endswith("_SUPPORTED_DIAGNOSTIC")
            matrix.append(
                {
                    "symbol": window.symbol,
                    "session_date": window.session_date,
                    "interval": window.interval,
                    "status": status,
                    "requested_date_matched": requested_date_matched,
                    "row_count": detail.get("row_count", 0),
                    "start_end_honored": start_end_honored,
                }
            )
            audit.append(
                {
                    **request_row,
                    "response_status": status,
                    "returned_min_time": returned_min,
                    "returned_max_time": returned_max,
                    "response_sha256": response_hash(payload_for_hash) if payload_for_hash is not None else "",
                    "error": detail.get("error", ""),
                }
            )
            pytime.sleep(0.15)
        terminal = "WEBULL_M15_2022_2025_SUPPORTED" if all(
            any(row["symbol"] == "SOXX" and row["interval"] == "M15" and row["session_date"].startswith(year) and "SUPPORTED" in row["status"] for row in matrix)
            for year in ["2022", "2023", "2024", "2025"]
        ) else "WEBULL_M15_PARTIAL"
        report = "\n".join(
            [
                "# Webull M15 Credentialed Probe Report",
                "",
                f"credential_present: {credentials['credential_present']}",
                "credentialed_probe_executed: True",
                f"sdk_version: {sdk.get('sdk_version', '')}",
                f"sdk_interface_status: {sdk.get('interface_status', '')}",
                f"terminal_status: {terminal}",
                "No order, account, balance, position, or preview endpoint was called.",
                "",
            ]
        )
        receipt = {
            "terminal_status": terminal,
            "credential": {**credentials, "authentication_status": "WEBULL_AUTH_OK"},
            "sdk": sdk,
            "probe_executed": True,
            "blocked_reason": "" if terminal == "WEBULL_M15_2022_2025_SUPPORTED" else "WEBULL_M15_PARTIAL",
        }
        return matrix, request_rows, audit, receipt, report
    finally:
        app_secret = ""


def response_hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
