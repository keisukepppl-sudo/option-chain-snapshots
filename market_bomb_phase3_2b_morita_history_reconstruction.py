#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import uuid
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import market_bomb_phase3_2_cta_vol_proxy as p32
except Exception:  # pragma: no cover
    p32 = None


ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
JST = ZoneInfo("Asia/Tokyo")
PARSER_VERSION = "morita_history_reconstruction_parser_v2"
RECONSTRUCTION_VERSION = "market_bomb_phase3_2b_morita_history_reconstruction_v2_20260627"
TIMEZONE_RULES_VERSION = "morita_source_timezone_rules_v1"
PARSER_MATRIX_VERSION = "morita_source_parser_matrix_v1"
OUTCOME_RULES_VERSION = "morita_reconstruction_rules_v2"
MAX_FEATURE_AGE_HOURS = 96
SOURCE_TIMEZONE_RULES_PATH = Path("market_bomb_config/morita_source_timezone_rules_v1.json")
PARSER_MATRIX_PATH = Path("market_bomb_config/morita_source_parser_matrix_v1.json")
RECONSTRUCTION_RULES_PATH = Path("market_bomb_config/morita_reconstruction_rules_v2.json")

SIGNAL_COLUMNS = [
    "signal_event_id", "setup_id", "source_id", "source_hash", "source_row_number", "source_record_key",
    "ticker", "event_timestamp_utc", "event_timestamp_original", "event_timezone_original",
    "event_timestamp_quality", "event_effective_at_utc", "event_session_context",
    "original_rank", "strategy_bucket", "setup_type", "scanner_name", "scanner_version",
    "signal_reason_raw", "signal_reason_normalized", "breakout_reference", "pullback_reference",
    "relative_strength", "volume_multiple", "source_evidence_level", "reconstruction_status",
    "reconstruction_notes", "data_type", "analysis_mode", "is_reconstructed", "raw_payload_reference",
    "source_timezone_policy_version", "source_timezone_policy", "timezone_resolution_method",
    "timezone_confidence", "event_time_precision", "cta_vol_join_eligible", "parser_version",
    "parser_matrix_version", "timezone_rules_version", "outcome_rules_version", "analysis_base_commit_sha",
    "analysis_run_id", "reconstruction_version", "source_priority", "evidence_priority",
    "timestamp_quality_priority", "canonical_selection_rank", "canonical_selection_reason",
]

DECISION_COLUMNS = [
    "decision_id", "signal_event_id", "setup_id", "source_id", "source_hash", "source_row_number",
    "ticker", "decision_timestamp_utc", "decision_timestamp_original", "decision_timezone_original",
    "decision_timestamp_quality", "decision_session_context", "decision_action", "decision_status",
    "decision_reason_raw", "decision_reason_normalized", "intended_instrument_type",
    "intended_option_expiration", "intended_option_strike", "intended_option_delta", "intended_option_dte",
    "intended_position_size_pct", "source_evidence_level", "reconstruction_status", "reconstruction_notes",
    "analysis_mode", "is_reconstructed", "raw_payload_reference",
    "source_timezone_policy_version", "source_timezone_policy", "timezone_resolution_method",
    "timezone_confidence", "event_time_precision", "cta_vol_join_eligible", "parser_version",
    "parser_matrix_version", "timezone_rules_version", "outcome_rules_version", "analysis_base_commit_sha",
    "analysis_run_id", "reconstruction_version",
]

FILL_COLUMNS = [
    "trade_id", "decision_id", "signal_event_id", "setup_id", "broker", "account_type", "ticker",
    "instrument_type", "contract_symbol", "option_expiration", "option_strike", "option_type",
    "multiplier", "fill_timestamp_utc", "fill_timestamp_original", "fill_timezone_original",
    "fill_timestamp_quality", "side", "quantity", "fill_price", "fees", "currency", "source_id",
    "source_hash", "source_row_number", "source_evidence_level", "reconstruction_status",
    "reconstruction_notes", "data_type", "analysis_mode", "is_reconstructed", "raw_payload_reference",
    "source_timezone_policy_version", "source_timezone_policy", "timezone_resolution_method",
    "timezone_confidence", "event_time_precision", "cta_vol_join_eligible", "parser_version",
    "parser_matrix_version", "timezone_rules_version", "outcome_rules_version", "analysis_base_commit_sha",
    "analysis_run_id", "reconstruction_version",
]

EXIT_COLUMNS = [
    "trade_exit_id", "trade_id", "exit_timestamp_utc", "exit_timestamp_original", "exit_timezone_original",
    "exit_timestamp_quality", "exit_reason", "exit_price", "exit_quantity", "fees", "realized_pnl_currency",
    "realized_pnl_pct", "source_id", "source_hash", "source_row_number", "source_evidence_level",
    "reconstruction_status", "reconstruction_notes", "data_type", "analysis_mode", "is_reconstructed",
    "raw_payload_reference",
    "source_timezone_policy_version", "source_timezone_policy", "timezone_resolution_method",
    "timezone_confidence", "event_time_precision", "cta_vol_join_eligible", "parser_version",
    "parser_matrix_version", "timezone_rules_version", "outcome_rules_version", "analysis_base_commit_sha",
    "analysis_run_id", "reconstruction_version",
]

PARSER_EXECUTION_COLUMNS = [
    "source_id", "source_type", "parser_name", "parser_allowed", "parser_executed",
    "parser_skipped_reason", "rows_read", "rows_parsed", "rows_rejected",
]

TIMESTAMP_AUDIT_COLUMNS = [
    "source_id", "source_path", "source_type", "timestamp_field_name", "raw_timestamp",
    "declared_timezone", "source_timezone_policy", "timezone_resolution_method",
    "timezone_confidence", "timestamp_utc", "timestamp_quality", "parse_warning", "row_count",
]


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value) or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def input_source_hash_manifest(root: Path, include_repo_sources: bool = True) -> pd.DataFrame:
    rows = []
    paths = candidate_source_paths(root) if include_repo_sources else []
    for path in paths:
        rel = str(path.relative_to(root)).replace("\\", "/")
        rows.append({
            "source_path": rel,
            "source_hash": hash_file(path),
            "file_size_bytes": path.stat().st_size,
            "source_modified_at_utc": pd.Timestamp(path.stat().st_mtime, unit="s", tz=UTC).isoformat(),
        })
    return pd.DataFrame(rows, columns=["source_path", "source_hash", "file_size_bytes", "source_modified_at_utc"])


def write_input_source_hash_manifest(root: Path, path: Path, include_repo_sources: bool = True) -> Path:
    manifest = input_source_hash_manifest(root, include_repo_sources)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(path, index=False)
    return path


def compare_input_source_manifests(before: pd.DataFrame, after: pd.DataFrame) -> tuple[int, str]:
    if before.empty and after.empty:
        return 0, ""
    b = before.set_index("source_path") if not before.empty else pd.DataFrame(columns=["source_hash"]).set_index(pd.Index([], name="source_path"))
    a = after.set_index("source_path") if not after.empty else pd.DataFrame(columns=["source_hash"]).set_index(pd.Index([], name="source_path"))
    changed = []
    for path in sorted(set(b.index).union(set(a.index))):
        bh = b.loc[path, "source_hash"] if path in b.index else ""
        ah = a.loc[path, "source_hash"] if path in a.index else ""
        if str(bh) != str(ah):
            changed.append(f"{path}: before={bh} after={ah}")
    return len(changed), "\n".join(changed)


def deterministic_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, raw).hex[:20]}"


def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass


def markdown_table(df: pd.DataFrame, max_rows: int = 60) -> str:
    if df.empty:
        return "_No rows._"
    clean = df.head(max_rows).fillna("").astype(str)
    cols = list(clean.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in clean.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("|", "\\|").replace("\n", " ") for c in cols) + " |")
    if len(df) > max_rows:
        lines.append(f"\n_Only first {max_rows} of {len(df)} rows shown._")
    return "\n".join(lines)


def load_json_config(root: Path, rel_path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    path = root / rel_path
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def timezone_rules(root: Path) -> dict[str, Any]:
    return load_json_config(root, SOURCE_TIMEZONE_RULES_PATH, {
        "version": TIMEZONE_RULES_VERSION,
        "default_policy": "unknown_blocks_strict_join",
        "source_type_defaults": {
            "scanner_alert_csv": "America/New_York",
            "notified_candidates_csv": "Asia/Tokyo",
            "daily_scan_log_csv": "Asia/Tokyo",
            "notification_export_csv": "Asia/Tokyo",
            "broker_execution_csv": "source_declared_or_unknown",
            "broker_order_csv": "source_declared_or_unknown",
            "manual_reconstruction_csv": "explicit_column_required",
            "unknown": "unknown_blocks_strict_join",
        },
        "filename_overrides": {},
        "column_overrides": {"timezone_columns": ["timezone", "time_zone", "event_timezone", "timestamp_timezone"]},
    })


def parser_matrix(root: Path) -> dict[str, Any]:
    return load_json_config(root, PARSER_MATRIX_PATH, {
        "version": PARSER_MATRIX_VERSION,
        "scanner_alert_csv": {"allow": ["signal"], "evidence_level": "raw_scanner_output"},
        "notified_candidates_csv": {"allow": ["signal"], "evidence_level": "raw_scanner_output"},
        "daily_scan_log_csv": {"allow": ["signal"], "evidence_level": "raw_scanner_output"},
        "notification_export_csv": {"allow": ["signal", "decision"], "evidence_level": "raw_notification_export"},
        "broker_order_csv": {"allow": ["decision"], "evidence_level": "raw_broker_order"},
        "broker_execution_csv": {"allow": ["fill", "exit"], "evidence_level": "raw_broker_execution"},
        "manual_reconstruction_csv": {"allow": ["signal", "decision", "fill", "exit"], "evidence_level": "structured_manual_entry"},
        "unknown": {"allow": [], "evidence_level": "unknown"},
    })


def reconstruction_rules(root: Path) -> dict[str, Any]:
    return load_json_config(root, RECONSTRUCTION_RULES_PATH, {
        "version": OUTCOME_RULES_VERSION,
        "date_only_policy": {
            "default": "exclude_from_event_time_analysis",
            "allow_daily_research_proxy": False,
            "daily_proxy_entry_method": "next_trading_close_proxy",
        },
        "pre_open_signal_policy": {"allow_next_regular_open_proxy": True},
    })


def analysis_metadata() -> dict[str, str]:
    return {
        "analysis_base_commit_sha": os.environ.get("GITHUB_SHA", ""),
        "analysis_base_branch": os.environ.get("GITHUB_REF_NAME", ""),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "analysis_run_id": os.environ.get("GITHUB_RUN_ID", deterministic_id("run", os.getcwd(), pd.Timestamp.now(tz=UTC).isoformat())),
        "reconstruction_version": RECONSTRUCTION_VERSION,
        "parser_matrix_version": PARSER_MATRIX_VERSION,
        "timezone_rules_version": TIMEZONE_RULES_VERSION,
        "outcome_rules_version": OUTCOME_RULES_VERSION,
    }


def resolve_source_timezone_policy(source_type: str, source_path: str, rules: dict[str, Any]) -> str:
    overrides = rules.get("filename_overrides", {}) or {}
    name = Path(source_path).name
    if name in overrides:
        return str(overrides[name])
    return str((rules.get("source_type_defaults", {}) or {}).get(source_type, rules.get("default_policy", "unknown_blocks_strict_join")))


def declared_timezone_from_row(row: pd.Series, rules: dict[str, Any]) -> str:
    cols = ((rules.get("column_overrides", {}) or {}).get("timezone_columns") or [])
    return str(first_present(row, list(cols), "")).strip()


def timezone_object(name: str) -> ZoneInfo | None:
    aliases = {"UTC": "UTC", "Z": "UTC", "ET": "America/New_York", "EST": "America/New_York", "EDT": "America/New_York", "JST": "Asia/Tokyo"}
    value = aliases.get(name.strip(), name.strip())
    if not value:
        return None
    try:
        return ZoneInfo(value)
    except Exception:
        return None


def parse_timestamp_resolution(
    value: Any,
    declared_timezone: str = "",
    source_timezone_policy: str = "unknown_blocks_strict_join",
    timestamp_field_name: str = "",
) -> dict[str, Any]:
    if value in [None, ""] or (isinstance(value, float) and pd.isna(value)):
        return {
            "timestamp_utc": None,
            "timestamp_quality": "parse_failed",
            "timezone_original": declared_timezone,
            "timezone_resolution_method": "missing_value",
            "timezone_confidence": "none",
            "timestamp_parse_warning": "missing_timestamp",
            "timestamp_field_name": timestamp_field_name,
        }
    raw = str(value).strip()
    ts = pd.to_datetime(raw, utc=False, errors="coerce")
    if pd.isna(ts):
        return {
            "timestamp_utc": None,
            "timestamp_quality": "parse_failed",
            "timezone_original": declared_timezone,
            "timezone_resolution_method": "parse_failed",
            "timezone_confidence": "none",
            "timestamp_parse_warning": "timestamp_parse_failed",
            "timestamp_field_name": timestamp_field_name,
        }
    date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) or re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", raw))
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is not None:
        return {
            "timestamp_utc": stamp.tz_convert(UTC),
            "timestamp_quality": "exact_utc" if str(stamp.tzinfo).upper() in {"UTC", "UTC+00:00"} or raw.endswith("Z") else "exact_with_timezone",
            "timezone_original": str(stamp.tzinfo),
            "timezone_resolution_method": "timestamp_embedded_timezone",
            "timezone_confidence": "high",
            "timestamp_parse_warning": "",
            "timestamp_field_name": timestamp_field_name,
        }

    local_tz = timezone_object(declared_timezone)
    method = "declared_timezone_column" if local_tz is not None else ""
    confidence = "high" if local_tz is not None else ""
    if local_tz is None:
        if source_timezone_policy in {"source_declared_or_unknown", "explicit_column_required", "unknown_blocks_strict_join"}:
            return {
                "timestamp_utc": None,
                "timestamp_quality": "timezone_unknown",
                "timezone_original": declared_timezone,
                "timezone_resolution_method": "timezone_unresolved",
                "timezone_confidence": "none",
                "timestamp_parse_warning": f"timezone_required_for_naive_timestamp:{source_timezone_policy}",
                "timestamp_field_name": timestamp_field_name,
            }
        local_tz = timezone_object(source_timezone_policy)
        method = "source_timezone_rule"
        confidence = "medium"
    if local_tz is None:
        return {
            "timestamp_utc": None,
            "timestamp_quality": "timezone_unknown",
            "timezone_original": declared_timezone,
            "timezone_resolution_method": "timezone_unresolved",
            "timezone_confidence": "none",
            "timestamp_parse_warning": f"invalid_timezone_policy:{source_timezone_policy}",
            "timestamp_field_name": timestamp_field_name,
        }
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) or re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", raw):
        stamp = pd.Timestamp(ts).replace(hour=0, minute=0, second=0)
        local = stamp.tz_localize(local_tz)
        quality = "date_only"
    else:
        local = stamp.tz_localize(local_tz)
        quality = "exact_local_timezone_declared" if method == "declared_timezone_column" else "exact_local_timezone_inferred_from_source_rule"
    return {
        "timestamp_utc": local.tz_convert(UTC),
        "timestamp_quality": quality,
        "timezone_original": declared_timezone or str(local_tz),
        "timezone_resolution_method": method,
        "timezone_confidence": confidence,
        "timestamp_parse_warning": "",
        "timestamp_field_name": timestamp_field_name,
    }


def parse_timestamp(
    value: Any,
    declared_timezone: str = "",
    source_timezone_policy: str = "America/New_York",
    timestamp_field_name: str = "",
) -> tuple[pd.Timestamp | None, str, str]:
    parsed = parse_timestamp_resolution(value, declared_timezone, source_timezone_policy, timestamp_field_name)
    return parsed["timestamp_utc"], parsed["timestamp_quality"], parsed["timezone_original"]


def session_context(ts: pd.Timestamp | None, quality: str = "") -> str:
    if quality == "date_only":
        return "date_only"
    if ts is None:
        return "unknown"
    t = ts.tz_convert(ET).time()
    if time(4, 0) <= t < time(9, 30):
        return "pre_open"
    if time(9, 30) <= t < time(16, 0):
        return "regular_hours"
    if time(16, 0) <= t < time(20, 0):
        return "after_close"
    return "overnight"


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def observed_fixed_holiday(year: int, month: int, day: int) -> date:
    d = date(year, month, day)
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nyse_holidays(year: int) -> set[date]:
    holidays = {
        observed_fixed_holiday(year, 1, 1),
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        easter_date(year) - timedelta(days=2),
        last_weekday(year, 5, 0),
        observed_fixed_holiday(year, 6, 19),
        observed_fixed_holiday(year, 7, 4),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4),
        observed_fixed_holiday(year, 12, 25),
    }
    return holidays


def is_regular_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


def next_regular_open(ts: pd.Timestamp | None) -> pd.Timestamp | None:
    if ts is None:
        return None
    et = ts.tz_convert(ET)
    candidate = et.replace(hour=9, minute=30, second=0, microsecond=0)
    if et.time() >= time(9, 30):
        candidate += timedelta(days=1)
    while not is_regular_trading_day(candidate.date()):
        candidate += timedelta(days=1)
    return candidate.tz_convert(UTC)


def strategy_bucket(rank: Any) -> str:
    rank = str(rank or "").upper().strip()
    if rank == "S":
        return "S_breakout_momentum"
    if rank in {"A", "B"}:
        return "AB_institutional_pullback"
    return "unclassified"


def analysis_mode(evidence: str, timestamp_quality: str, unit: str) -> str:
    strict_qualities = {"exact_utc", "exact_with_timezone", "exact_local_timezone_declared", "exact_local_timezone_inferred_from_source_rule"}
    if evidence == "raw_broker_execution" and timestamp_quality in strict_qualities:
        return "strict_live_replay"
    if unit == "decision" and timestamp_quality in strict_qualities and evidence in {"raw_broker_order", "raw_notification_export", "raw_scanner_output"}:
        return "strict_live_replay"
    if timestamp_quality in {"timezone_unknown", "parse_failed"}:
        return "unavailable"
    if evidence in {"raw_scanner_output", "raw_notification_export", "raw_action_artifact"}:
        return "historical_reconstructed"
    if evidence == "structured_manual_entry":
        return "mixed_exploratory"
    return "unavailable"


def source_type_for(path: Path) -> str:
    p = str(path).lower().replace("\\", "/")
    name = path.name.lower()
    if "raw_sources" in p and "manual" in name:
        return "manual_reconstruction_csv"
    if "order" in name:
        return "broker_order_csv"
    if "/broker" in p or "broker_" in name or "execution" in name or "fill" in name:
        return "broker_execution_csv"
    if "notification" in p or "pushover" in p or "discord" in p:
        return "notification_export_csv"
    if "notified_candidates" in p:
        return "notified_candidates_csv"
    if "daily_scan" in p or "scan_log" in p:
        return "daily_scan_log_csv"
    if "scanner_alert" in p or "scanner" in p or "candidate" in name:
        return "scanner_alert_csv"
    return "unknown"


def source_priority(source_type: str) -> int:
    return {
        "broker_execution_csv": 1,
        "broker_order_csv": 2,
        "scanner_alert_csv": 3,
        "notified_candidates_csv": 3,
        "daily_scan_log_csv": 3,
        "notification_export_csv": 4,
        "manual_reconstruction_csv": 5,
        "scanner_markdown_report": 4,
        "unknown": 99,
    }.get(source_type, 99)


def evidence_priority(evidence: str) -> int:
    return {
        "raw_broker_execution": 1,
        "raw_broker_order": 2,
        "raw_scanner_output": 3,
        "raw_notification_export": 4,
        "structured_manual_entry": 5,
        "reconstructed_from_text": 6,
        "unknown": 99,
    }.get(evidence, 99)


def timestamp_quality_priority(quality: str) -> int:
    return {
        "exact_utc": 1,
        "exact_with_timezone": 2,
        "exact_local_timezone_declared": 3,
        "exact_local_timezone_inferred_from_source_rule": 4,
        "date_only": 20,
        "timezone_unknown": 90,
        "parse_failed": 99,
    }.get(quality, 99)


def evidence_level(source_type: str) -> str:
    if source_type == "broker_execution_csv":
        return "raw_broker_execution"
    if source_type == "broker_order_csv":
        return "raw_broker_order"
    if source_type in {"scanner_alert_csv", "notified_candidates_csv", "daily_scan_log_csv"}:
        return "raw_scanner_output"
    if source_type == "notification_export_csv":
        return "raw_notification_export"
    if source_type == "manual_reconstruction_csv":
        return "structured_manual_entry"
    return "unknown"


def candidate_source_paths(root: Path) -> list[Path]:
    globs = [
        "scanner_alerts/**/*.csv",
        "scanner/**/*.csv",
        "notified_candidates/**/*.csv",
        "daily_scan_log/**/*.csv",
        "morita_signal_history/**/*.csv",
        "morita_decision_history/**/*.csv",
        "morita_trade_log/**/*.csv",
        "market_bomb_reconstruction/raw_sources/**/*.csv",
    ]
    paths: list[Path] = []
    for pattern in globs:
        paths.extend(root.glob(pattern))
    return sorted({p for p in paths if p.is_file() and "market_bomb_reconstruction/normalized" not in str(p).replace("\\", "/")})


def first_present(row: pd.Series, names: list[str], default: Any = "") -> Any:
    for name in names:
        if name in row and pd.notna(row[name]) and str(row[name]) != "":
            return row[name]
    return default


def first_present_with_name(row: pd.Series, names: list[str], default: Any = "") -> tuple[Any, str]:
    for name in names:
        if name in row and pd.notna(row[name]) and str(row[name]) != "":
            return row[name], name
    return default, ""


def parsed_timestamp_for_row(row: pd.Series, source: pd.Series, names: list[str], rules: dict[str, Any]) -> dict[str, Any]:
    raw, field = first_present_with_name(row, names, "")
    declared = declared_timezone_from_row(row, rules)
    policy = str(source.get("source_timezone_policy", resolve_source_timezone_policy(str(source.get("source_type", "unknown")), str(source.get("source_path", "")), rules)))
    parsed = parse_timestamp_resolution(raw, declared, policy, field)
    parsed["raw_timestamp"] = raw
    parsed["declared_timezone"] = declared
    parsed["source_timezone_policy"] = policy
    return parsed


def event_time_precision(timestamp_quality: str) -> str:
    if timestamp_quality == "date_only":
        return "date_only"
    if timestamp_quality in {"exact_utc", "exact_with_timezone", "exact_local_timezone_declared", "exact_local_timezone_inferred_from_source_rule"}:
        return "exact"
    return "unavailable"


def cta_vol_join_eligible(timestamp_quality: str, mode: str) -> bool:
    return timestamp_quality in {"exact_utc", "exact_with_timezone", "exact_local_timezone_declared", "exact_local_timezone_inferred_from_source_rule"} and mode != "unavailable"


def provenance_metadata(source: pd.Series, parsed: dict[str, Any], mode: str) -> dict[str, Any]:
    meta = analysis_metadata()
    return {
        "source_timezone_policy_version": source.get("source_timezone_policy_version", TIMEZONE_RULES_VERSION),
        "source_timezone_policy": parsed.get("source_timezone_policy", source.get("source_timezone_policy", "")),
        "timezone_resolution_method": parsed.get("timezone_resolution_method", ""),
        "timezone_confidence": parsed.get("timezone_confidence", ""),
        "event_time_precision": event_time_precision(str(parsed.get("timestamp_quality", ""))),
        "cta_vol_join_eligible": cta_vol_join_eligible(str(parsed.get("timestamp_quality", "")), mode),
        "parser_version": PARSER_VERSION,
        "parser_matrix_version": PARSER_MATRIX_VERSION,
        "timezone_rules_version": TIMEZONE_RULES_VERSION,
        "outcome_rules_version": OUTCOME_RULES_VERSION,
        "analysis_base_commit_sha": meta["analysis_base_commit_sha"],
        "analysis_run_id": meta["analysis_run_id"],
        "reconstruction_version": RECONSTRUCTION_VERSION,
    }


def build_source_inventory(root: Path, include_repo_sources: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    paths = candidate_source_paths(root) if include_repo_sources else []
    tz_rules = timezone_rules(root)
    matrix = parser_matrix(root)
    rows = []
    manifest = []
    for i, path in enumerate(paths, start=1):
        rel = str(path.relative_to(root)).replace("\\", "/")
        stype = source_type_for(path)
        tz_policy = resolve_source_timezone_policy(stype, rel, tz_rules)
        matrix_entry = matrix.get(stype, matrix.get("unknown", {"allow": [], "evidence_level": "unknown"}))
        sha = hash_file(path)
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame()
        source_id = deterministic_id("src", rel, sha)
        rows.append(
            {
                "source_id": source_id,
                "source_path": rel,
                "source_filename": path.name,
                "source_type": stype,
                "source_priority": source_priority(stype),
                "source_timezone_policy": tz_policy,
                "source_timezone_policy_version": str(tz_rules.get("version", TIMEZONE_RULES_VERSION)),
                "parser_allowed_units": ",".join(matrix_entry.get("allow", [])),
                "source_evidence_level": matrix_entry.get("evidence_level", evidence_level(stype)),
                "source_hash": sha,
                "file_size_bytes": path.stat().st_size,
                "source_created_at_utc": pd.Timestamp(path.stat().st_ctime, unit="s", tz=UTC).isoformat(),
                "source_modified_at_utc": pd.Timestamp(path.stat().st_mtime, unit="s", tz=UTC).isoformat(),
                "discovered_on_main": True,
                "source_access_method": "repository_checkout",
                "parser_name": parser_for_type(stype),
                "parser_version": PARSER_VERSION,
                "row_count_raw": len(df),
                "row_count_parsed": 0,
                "timezone_found": "",
                "timestamp_quality": "unknown",
                "rank_availability": any(c in df.columns for c in ["alert_rank", "rank", "original_rank", "production_rank"]),
                "ticker_availability": any(c in df.columns for c in ["ticker", "symbol", "underlying"]),
                "trade_data_availability": any(c in df.columns for c in ["fill_price", "exit_price", "contract_symbol"]),
                "recommended_use": recommended_use(stype),
                "notes": "" if not df.empty else "empty_or_unreadable",
            }
        )
        manifest.append({"source_id": source_id, "source_path": rel, "source_hash": sha, "source_type": stype, "row_count_raw": len(df)})
    return pd.DataFrame(rows), pd.DataFrame(manifest)


def parser_for_type(source_type: str) -> str:
    if source_type == "broker_execution_csv":
        return "broker_execution_csv_parser"
    if source_type == "broker_order_csv":
        return "broker_order_csv_parser"
    if source_type in {"scanner_alert_csv", "notified_candidates_csv", "daily_scan_log_csv"}:
        return "scanner_signal_csv_parser"
    if source_type == "manual_reconstruction_csv":
        return "manual_reconstruction_csv_parser"
    if source_type == "notification_export_csv":
        return "notification_export_csv_parser"
    return "generic_csv_parser"


def recommended_use(source_type: str) -> str:
    if source_type in {"broker_execution_csv", "broker_order_csv"}:
        return "trade_fill_exit_reconstruction"
    if source_type in {"scanner_alert_csv", "notified_candidates_csv", "daily_scan_log_csv"}:
        return "signal_reconstruction"
    if source_type == "manual_reconstruction_csv":
        return "manual_research_reconstruction_only"
    return "audit_only"


def normalize_signal_row(row: pd.Series, source: pd.Series, row_num: int, rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rules = rules or timezone_rules(Path("."))
    ticker = str(first_present(row, ["ticker", "symbol", "underlying"], "")).upper().strip()
    if not ticker:
        return None
    raw_rank = str(first_present(row, ["alert_rank", "rank", "original_rank", "production_rank"], "")).upper().strip()
    parsed = parsed_timestamp_for_row(row, source, ["event_timestamp_utc", "timestamp_utc", "alert_timestamp_utc", "scan_time_utc", "date", "breakout_date"], rules)
    ts, tq, tz = parsed["timestamp_utc"], parsed["timestamp_quality"], parsed["timezone_original"]
    ts_raw = parsed["raw_timestamp"]
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    mode = analysis_mode(evidence, tq, "signal")
    setup_type = str(first_present(row, ["setup_type", "entry_rule"], "unknown")).lower()
    if setup_type not in {"breakout", "first_pullback", "institutional_pullback"}:
        setup_type = "unknown"
    sid = deterministic_id("sig", source["source_hash"], row_num, ticker, ts.isoformat())
    setup_id = deterministic_id("setup", source["source_hash"], ticker, raw_rank, setup_type, ts.date())
    return {
        "signal_event_id": sid,
        "setup_id": setup_id,
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "source_record_key": f"{source['source_id']}:{row_num}",
        "ticker": ticker,
        "event_timestamp_utc": ts.isoformat(),
        "event_timestamp_original": ts_raw,
        "event_timezone_original": tz,
        "event_timestamp_quality": tq,
        "event_effective_at_utc": ts.isoformat(),
        "event_session_context": session_context(ts, tq),
        "original_rank": raw_rank,
        "strategy_bucket": strategy_bucket(raw_rank),
        "setup_type": setup_type,
        "scanner_name": str(first_present(row, ["scanner_name"], "morita_scanner")),
        "scanner_version": str(first_present(row, ["scanner_version"], "")),
        "signal_reason_raw": str(first_present(row, ["signal_reason", "reason", "exclusion_reason"], "")),
        "signal_reason_normalized": "",
        "breakout_reference": first_present(row, ["prior_20d_high", "breakout_price"], ""),
        "pullback_reference": first_present(row, ["pullback_reference", "pullback_price"], ""),
        "relative_strength": first_present(row, ["RS", "rs", "relative_strength"], ""),
        "volume_multiple": first_present(row, ["volume_multiple"], ""),
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "" if raw_rank in {"S", "A", "B"} else "rank_missing_or_unclassified",
        "data_type": "reconstructed",
        "analysis_mode": mode,
        "is_reconstructed": True,
        "raw_payload_reference": source["source_path"],
        "source_priority": source_priority(str(source["source_type"])),
        "evidence_priority": evidence_priority(evidence),
        "timestamp_quality_priority": timestamp_quality_priority(tq),
        "canonical_selection_rank": "",
        "canonical_selection_reason": "",
        **provenance_metadata(source, parsed, mode),
    }


def normalize_decision_row(row: pd.Series, source: pd.Series, row_num: int, signal_id: str = "", setup_id: str = "", rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rules = rules or timezone_rules(Path("."))
    ticker = str(first_present(row, ["ticker", "symbol", "underlying"], "")).upper().strip()
    action = str(first_present(row, ["decision_action", "action"], "")).lower().strip()
    if action not in {"enter", "skip", "watch", "exit_plan_only", "unknown"}:
        if action:
            action = "unknown"
    if not ticker or not action:
        return None
    parsed = parsed_timestamp_for_row(row, source, ["decision_timestamp_utc", "timestamp_utc", "decision_time", "date"], rules)
    ts, tq, tz = parsed["timestamp_utc"], parsed["timestamp_quality"], parsed["timezone_original"]
    ts_raw = parsed["raw_timestamp"]
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    mode = analysis_mode(evidence, tq, "decision")
    did = deterministic_id("dec", source["source_hash"], row_num, ticker, ts.isoformat(), action)
    return {
        "decision_id": did,
        "signal_event_id": signal_id,
        "setup_id": setup_id,
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "ticker": ticker,
        "decision_timestamp_utc": ts.isoformat(),
        "decision_timestamp_original": ts_raw,
        "decision_timezone_original": tz,
        "decision_timestamp_quality": tq,
        "decision_session_context": session_context(ts, tq),
        "decision_action": action,
        "decision_status": str(first_present(row, ["decision_status", "status"], "")),
        "decision_reason_raw": str(first_present(row, ["decision_reason", "reason"], "")),
        "decision_reason_normalized": "",
        "intended_instrument_type": first_present(row, ["intended_instrument_type", "instrument_type"], ""),
        "intended_option_expiration": first_present(row, ["intended_option_expiration", "option_expiration"], ""),
        "intended_option_strike": first_present(row, ["intended_option_strike", "option_strike"], ""),
        "intended_option_delta": first_present(row, ["intended_option_delta", "option_delta"], ""),
        "intended_option_dte": first_present(row, ["intended_option_dte", "option_dte"], ""),
        "intended_position_size_pct": first_present(row, ["intended_position_size_pct", "position_size_pct"], ""),
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "",
        "analysis_mode": mode,
        "is_reconstructed": True,
        "raw_payload_reference": source["source_path"],
        **provenance_metadata(source, parsed, mode),
    }


def normalize_fill_row(row: pd.Series, source: pd.Series, row_num: int, rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rules = rules or timezone_rules(Path("."))
    ticker = str(first_present(row, ["ticker", "symbol", "underlying"], "")).upper().strip()
    price = safe_float(first_present(row, ["fill_price", "price"], math.nan))
    qty = safe_float(first_present(row, ["quantity", "qty"], math.nan))
    side = str(first_present(row, ["side", "action"], "")).lower()
    if not ticker or pd.isna(price) or pd.isna(qty):
        return None
    parsed = parsed_timestamp_for_row(row, source, ["fill_timestamp_utc", "timestamp_utc", "fill_time", "date"], rules)
    ts, tq, tz = parsed["timestamp_utc"], parsed["timestamp_quality"], parsed["timezone_original"]
    ts_raw = parsed["raw_timestamp"]
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    mode = analysis_mode(evidence, tq, "fill")
    contract = str(first_present(row, ["contract_symbol"], ""))
    trade_id = deterministic_id("trd", source["source_hash"], row_num, ticker, contract, ts.isoformat(), side, qty, price)
    return {
        "trade_id": trade_id,
        "decision_id": str(first_present(row, ["decision_id"], "")),
        "signal_event_id": str(first_present(row, ["signal_event_id"], "")),
        "setup_id": str(first_present(row, ["setup_id"], "")),
        "broker": first_present(row, ["broker"], ""),
        "account_type": first_present(row, ["account_type"], ""),
        "ticker": ticker,
        "instrument_type": first_present(row, ["instrument_type"], "option" if contract else ""),
        "contract_symbol": contract,
        "option_expiration": first_present(row, ["option_expiration"], ""),
        "option_strike": first_present(row, ["option_strike"], ""),
        "option_type": first_present(row, ["option_type"], ""),
        "multiplier": first_present(row, ["multiplier"], 100 if contract else ""),
        "fill_timestamp_utc": ts.isoformat(),
        "fill_timestamp_original": ts_raw,
        "fill_timezone_original": tz,
        "fill_timestamp_quality": tq,
        "side": side,
        "quantity": qty,
        "fill_price": price,
        "fees": first_present(row, ["fees"], ""),
        "currency": first_present(row, ["currency"], "USD"),
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "",
        "data_type": "observed" if evidence == "raw_broker_execution" else "reconstructed",
        "analysis_mode": mode,
        "is_reconstructed": evidence != "raw_broker_execution",
        "raw_payload_reference": source["source_path"],
        **provenance_metadata(source, parsed, mode),
    }


def normalize_exit_row(row: pd.Series, source: pd.Series, row_num: int, rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rules = rules or timezone_rules(Path("."))
    trade_id = str(first_present(row, ["trade_id"], ""))
    price = safe_float(first_present(row, ["exit_price"], math.nan))
    if not trade_id or pd.isna(price):
        return None
    parsed = parsed_timestamp_for_row(row, source, ["exit_timestamp_utc", "timestamp_utc", "exit_time", "date"], rules)
    ts, tq, tz = parsed["timestamp_utc"], parsed["timestamp_quality"], parsed["timezone_original"]
    ts_raw = parsed["raw_timestamp"]
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    mode = analysis_mode(evidence, tq, "exit")
    return {
        "trade_exit_id": deterministic_id("exit", source["source_hash"], row_num, trade_id, ts.isoformat(), price),
        "trade_id": trade_id,
        "exit_timestamp_utc": ts.isoformat(),
        "exit_timestamp_original": ts_raw,
        "exit_timezone_original": tz,
        "exit_timestamp_quality": tq,
        "exit_reason": first_present(row, ["exit_reason"], ""),
        "exit_price": price,
        "exit_quantity": first_present(row, ["exit_quantity", "quantity"], ""),
        "fees": first_present(row, ["fees"], ""),
        "realized_pnl_currency": first_present(row, ["realized_pnl_currency"], ""),
        "realized_pnl_pct": first_present(row, ["realized_pnl_pct", "pnl_pct"], ""),
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "",
        "data_type": "observed" if evidence == "raw_broker_execution" else "reconstructed",
        "analysis_mode": mode,
        "is_reconstructed": evidence != "raw_broker_execution",
        "raw_payload_reference": source["source_path"],
        **provenance_metadata(source, parsed, mode),
    }


def timestamp_audit_row(source: pd.Series, row_count: int, parsed: dict[str, Any]) -> dict[str, Any]:
    ts = parsed.get("timestamp_utc")
    return {
        "source_id": source.get("source_id", ""),
        "source_path": source.get("source_path", ""),
        "source_type": source.get("source_type", ""),
        "timestamp_field_name": parsed.get("timestamp_field_name", ""),
        "raw_timestamp": parsed.get("raw_timestamp", ""),
        "declared_timezone": parsed.get("declared_timezone", ""),
        "source_timezone_policy": parsed.get("source_timezone_policy", source.get("source_timezone_policy", "")),
        "timezone_resolution_method": parsed.get("timezone_resolution_method", ""),
        "timezone_confidence": parsed.get("timezone_confidence", ""),
        "timestamp_utc": ts.isoformat() if ts is not None else "",
        "timestamp_quality": parsed.get("timestamp_quality", ""),
        "parse_warning": parsed.get("timestamp_parse_warning", ""),
        "row_count": row_count,
    }


def parse_sources_with_audits(root: Path, inventory: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signals: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    parser_audit: list[dict[str, Any]] = []
    timestamp_audit: list[dict[str, Any]] = []
    rules = timezone_rules(root)
    matrix = parser_matrix(root)
    for _, source in inventory.iterrows():
        path = root / str(source["source_path"])
        try:
            df = pd.read_csv(path)
        except Exception:
            parser_audit.append({
                "source_id": source.get("source_id", ""),
                "source_type": source.get("source_type", ""),
                "parser_name": source.get("parser_name", ""),
                "parser_allowed": False,
                "parser_executed": False,
                "parser_skipped_reason": "source_unreadable",
                "rows_read": 0,
                "rows_parsed": 0,
                "rows_rejected": 0,
            })
            continue
        stype = str(source.get("source_type", "unknown"))
        allowed = set((matrix.get(stype, matrix.get("unknown", {})).get("allow", [])))
        before_counts = {"signal": len(signals), "decision": len(decisions), "fill": len(fills), "exit": len(exits)}
        for parser_name, unit in [
            ("signal_normalizer", "signal"),
            ("decision_normalizer", "decision"),
            ("fill_normalizer", "fill"),
            ("exit_normalizer", "exit"),
        ]:
            parser_audit.append({
                "source_id": source.get("source_id", ""),
                "source_type": stype,
                "parser_name": parser_name,
                "parser_allowed": unit in allowed,
                "parser_executed": unit in allowed,
                "parser_skipped_reason": "" if unit in allowed else "not_allowed_by_source_parser_matrix",
                "rows_read": len(df),
                "rows_parsed": 0,
                "rows_rejected": len(df) if unit in allowed else 0,
            })
        if not allowed:
            continue
        for idx, row in df.iterrows():
            row_num = int(idx) + 2
            sig = None
            if "signal" in allowed:
                parsed = parsed_timestamp_for_row(row, source, ["event_timestamp_utc", "timestamp_utc", "alert_timestamp_utc", "scan_time_utc", "date", "breakout_date"], rules)
                timestamp_audit.append(timestamp_audit_row(source, 1, parsed))
                sig = normalize_signal_row(row, source, row_num, rules)
                if sig is not None:
                    signals.append(sig)
            if "decision" in allowed:
                parsed = parsed_timestamp_for_row(row, source, ["decision_timestamp_utc", "timestamp_utc", "decision_time", "date"], rules)
                timestamp_audit.append(timestamp_audit_row(source, 1, parsed))
                dec = normalize_decision_row(row, source, row_num, sig["signal_event_id"] if sig else "", sig["setup_id"] if sig else "", rules)
                if dec is not None:
                    decisions.append(dec)
            if "fill" in allowed:
                parsed = parsed_timestamp_for_row(row, source, ["fill_timestamp_utc", "timestamp_utc", "fill_time", "date"], rules)
                timestamp_audit.append(timestamp_audit_row(source, 1, parsed))
                fill = normalize_fill_row(row, source, row_num, rules)
                if fill is not None:
                    fills.append(fill)
            if "exit" in allowed:
                parsed = parsed_timestamp_for_row(row, source, ["exit_timestamp_utc", "timestamp_utc", "exit_time", "date"], rules)
                timestamp_audit.append(timestamp_audit_row(source, 1, parsed))
                ex = normalize_exit_row(row, source, row_num, rules)
                if ex is not None:
                    exits.append(ex)
        after_counts = {"signal": len(signals), "decision": len(decisions), "fill": len(fills), "exit": len(exits)}
        for audit in parser_audit:
            if audit["source_id"] != source.get("source_id", "") or not audit["parser_executed"]:
                continue
            unit = audit["parser_name"].split("_")[0]
            parsed_count = after_counts[unit] - before_counts[unit]
            audit["rows_parsed"] = parsed_count
            audit["rows_rejected"] = max(0, len(df) - parsed_count)
    return (
        pd.DataFrame(signals, columns=SIGNAL_COLUMNS),
        pd.DataFrame(decisions, columns=DECISION_COLUMNS),
        pd.DataFrame(fills, columns=FILL_COLUMNS),
        pd.DataFrame(exits, columns=EXIT_COLUMNS),
        pd.DataFrame(parser_audit, columns=PARSER_EXECUTION_COLUMNS),
        pd.DataFrame(timestamp_audit, columns=TIMESTAMP_AUDIT_COLUMNS),
    )


def parse_sources(root: Path, inventory: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signals, decisions, fills, exits, _, _ = parse_sources_with_audits(root, inventory)
    return (
        signals,
        decisions,
        fills,
        exits,
    )


def duplicate_audit(signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if signals.empty:
        return pd.DataFrame(), pd.DataFrame(), signals
    df = signals.copy()
    df["event_date"] = pd.to_datetime(df["event_timestamp_utc"], utc=True, errors="coerce").dt.date.astype(str)
    keys = ["ticker", "event_date", "original_rank", "scanner_name", "setup_type", "event_session_context"]
    df["duplicate_key"] = df[keys].astype(str).agg("|".join, axis=1)
    df["source_priority"] = df.get("source_priority", df["source_evidence_level"].map(lambda x: source_priority("unknown")))
    if "source_priority" not in signals.columns:
        df["source_priority"] = df["source_evidence_level"].map(lambda x: 1 if x == "raw_broker_execution" else 2 if x == "raw_broker_order" else 3 if x == "raw_scanner_output" else 4 if x == "raw_notification_export" else 5 if x == "structured_manual_entry" else 99)
    df["evidence_priority"] = df["source_evidence_level"].map(evidence_priority)
    df["timestamp_quality_priority"] = df["event_timestamp_quality"].map(timestamp_quality_priority)
    df["has_exact_timestamp"] = df["timestamp_quality_priority"] <= 4
    df["has_source_row_number"] = pd.to_numeric(df["source_row_number"], errors="coerce").notna()
    dupes = df[df.duplicated("duplicate_key", keep=False)].copy()
    canonical_sorted = df.sort_values(
        [
            "duplicate_key",
            "source_priority",
            "evidence_priority",
            "timestamp_quality_priority",
            "has_exact_timestamp",
            "has_source_row_number",
            "source_id",
            "source_row_number",
        ],
        ascending=[True, True, True, True, False, False, True, True],
    ).copy()
    canonical_sorted["canonical_selection_rank"] = canonical_sorted.groupby("duplicate_key").cumcount() + 1
    canonical_sorted["canonical_selection_reason"] = "source_priority_then_evidence_then_timestamp_quality"
    canonical = canonical_sorted.drop_duplicates("duplicate_key", keep="first")
    linkage_rows = []
    if not dupes.empty:
        for key, group in dupes.groupby("duplicate_key"):
            winner = canonical[canonical["duplicate_key"].eq(key)].iloc[0]
            for _, row in group.iterrows():
                if row["signal_event_id"] == winner["signal_event_id"]:
                    continue
                linkage_rows.append(
                    {
                        "canonical_signal_event_id": winner["signal_event_id"],
                        "duplicate_signal_event_id": row["signal_event_id"],
                        "duplicate_type": "probable_duplicate",
                        "duplicate_key": key,
                        "duplicate_source_id": row["source_id"],
                        "canonical_source_id": winner["source_id"],
                        "canonical_selection_reason": winner["canonical_selection_reason"],
                        "canonical_source_priority": winner["source_priority"],
                        "duplicate_source_priority": row["source_priority"],
                    }
                )
    canonical = canonical.drop(columns=["event_date", "duplicate_key", "has_exact_timestamp", "has_source_row_number"], errors="ignore")
    dupes = dupes.drop(columns=["event_date"], errors="ignore")
    return dupes, pd.DataFrame(linkage_rows), canonical


def load_price_history(root: Path) -> dict[str, pd.DataFrame]:
    if p32 is None:
        return {}
    return p32.load_price_history(root, refresh_price_history=False)


def build_outcome_panel(root: Path, signals: pd.DataFrame, decisions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame, build_underlying: bool) -> pd.DataFrame:
    rows = []
    prices = load_price_history(root) if build_underlying else {}
    used_signals: set[str] = set()
    used_decisions: set[str] = set()

    exit_by_trade = {str(row["trade_id"]): row for _, row in exits.iterrows()} if not exits.empty and "trade_id" in exits.columns else {}
    if not fills.empty:
        for _, fill in fills.iterrows():
            trade_id = str(fill.get("trade_id", ""))
            exit_row = exit_by_trade.get(trade_id)
            observed_available = bool(exit_row is not None and fill.get("source_evidence_level") == "raw_broker_execution" and exit_row.get("source_evidence_level") == "raw_broker_execution")
            observed_pct = np.nan
            observed_currency = np.nan
            method = ""
            if observed_available:
                entry_price = safe_float(fill.get("fill_price"))
                exit_price = safe_float(exit_row.get("exit_price"))
                qty = abs(safe_float(exit_row.get("exit_quantity", fill.get("quantity", math.nan))))
                multiplier = safe_float(fill.get("multiplier", 100), 100)
                if not pd.isna(entry_price) and not pd.isna(exit_price) and entry_price > 0:
                    observed_pct = exit_price / entry_price - 1
                    observed_currency = (exit_price - entry_price) * qty * multiplier
                    method = "actual_entry_exit_fill"
            sig_id = str(fill.get("signal_event_id", ""))
            dec_id = str(fill.get("decision_id", ""))
            if sig_id:
                used_signals.add(sig_id)
            if dec_id:
                used_decisions.add(dec_id)
            row = {
                "analysis_unit": "trade",
                "outcome_unit_priority": 1,
                "signal_event_id": sig_id,
                "decision_id": dec_id,
                "trade_id": trade_id,
                "ticker": fill.get("ticker", ""),
                "strategy_bucket": "unclassified",
                "original_rank": "",
                "setup_type": "",
                "event_timestamp_utc": fill.get("fill_timestamp_utc", ""),
                "entry_timestamp_utc": fill.get("fill_timestamp_utc", ""),
                "entry_timestamp_source": "trade_fill",
                "entry_price_method": "actual_fill",
                "entry_price_quality": "observed_fill",
                "analysis_mode": fill.get("analysis_mode", "strict_live_replay"),
                "cta_vol_join_eligible": bool(fill.get("cta_vol_join_eligible", True)),
                "observed_option_pnl_pct": observed_pct,
                "observed_option_pnl_currency": observed_currency,
                "observed_option_pnl_available": observed_available,
                "observed_pnl_link_confidence": "high" if observed_available else "none",
                "observed_pnl_calculation_method": method,
                "modelled_option_pnl_pct": np.nan,
                "modelled_option_pnl_available": False,
                "underlying_entry_timestamp_utc": fill.get("fill_timestamp_utc", ""),
                "underlying_entry_price": np.nan,
                "outcome_price_source": "",
                "outcome_calculation_version": RECONSTRUCTION_VERSION,
                "reconstruction_version": RECONSTRUCTION_VERSION,
                "outcome_rules_version": OUTCOME_RULES_VERSION,
            }
            rows.append(add_underlying_outcomes(row, prices))

    if not decisions.empty:
        for _, dec in decisions.iterrows():
            dec_id = str(dec.get("decision_id", ""))
            if dec_id and dec_id in used_decisions:
                continue
            sig_id = str(dec.get("signal_event_id", ""))
            if sig_id:
                used_signals.add(sig_id)
            entry_ts = dec.get("decision_timestamp_utc", "")
            price_method = "exact_decision_price" if first_present(dec, ["underlying_entry_price", "entry_price"], "") != "" else "unavailable_no_fill_or_price"
            row = {
                "analysis_unit": "decision",
                "outcome_unit_priority": 2,
                "signal_event_id": sig_id,
                "decision_id": dec_id,
                "trade_id": "",
                "ticker": dec.get("ticker", ""),
                "strategy_bucket": "unclassified",
                "original_rank": "",
                "setup_type": "",
                "event_timestamp_utc": entry_ts,
                "entry_timestamp_utc": entry_ts,
                "entry_timestamp_source": "decision_timestamp",
                "entry_price_method": price_method,
                "entry_price_quality": "raw_decision_price" if price_method == "exact_decision_price" else "unavailable",
                "analysis_mode": dec.get("analysis_mode", "strict_live_replay"),
                "cta_vol_join_eligible": bool(dec.get("cta_vol_join_eligible", True)) and price_method == "exact_decision_price",
                "observed_option_pnl_pct": np.nan,
                "observed_option_pnl_currency": np.nan,
                "observed_option_pnl_available": False,
                "observed_pnl_link_confidence": "none",
                "observed_pnl_calculation_method": "",
                "modelled_option_pnl_pct": np.nan,
                "modelled_option_pnl_available": False,
                "underlying_entry_timestamp_utc": entry_ts if price_method == "exact_decision_price" else "",
                "underlying_entry_price": np.nan,
                "outcome_price_source": "",
                "outcome_calculation_version": RECONSTRUCTION_VERSION,
                "reconstruction_version": RECONSTRUCTION_VERSION,
                "outcome_rules_version": OUTCOME_RULES_VERSION,
            }
            rows.append(add_underlying_outcomes(row, prices))

    rules = reconstruction_rules(root)
    allow_daily_proxy = bool(((rules.get("date_only_policy", {}) or {}).get("allow_daily_research_proxy", False)))
    for _, sig in signals.iterrows():
        if str(sig.get("signal_event_id", "")) in used_signals:
            continue
        event_ts = parse_timestamp(sig["event_timestamp_utc"])[0]
        if sig["event_session_context"] in {"after_close", "overnight"}:
            entry_ts = next_regular_open(event_ts)
            method = "next_regular_open_proxy"
            entry_source = "signal_after_close_proxy"
            cta_eligible = bool(sig.get("cta_vol_join_eligible", False))
        elif sig["event_session_context"] == "pre_open" and bool((rules.get("pre_open_signal_policy", {}) or {}).get("allow_next_regular_open_proxy", True)):
            entry_ts = next_regular_open(event_ts)
            method = "next_regular_open_proxy"
            entry_source = "signal_pre_open_proxy"
            cta_eligible = bool(sig.get("cta_vol_join_eligible", False))
        elif sig["event_session_context"] == "date_only" and allow_daily_proxy:
            entry_ts = next_regular_open(event_ts)
            method = "next_trading_close_proxy"
            entry_source = "daily_proxy_research_only"
            cta_eligible = False
        elif sig["event_session_context"] == "date_only":
            entry_ts = None
            method = "unavailable_date_only"
            entry_source = "date_only_unavailable"
            cta_eligible = False
        else:
            entry_ts = None
            method = "unavailable"
            entry_source = "signal_only_no_fill_or_decision"
            cta_eligible = False
        row = {
            "analysis_unit": "signal_event",
            "outcome_unit_priority": 3,
            "signal_event_id": sig["signal_event_id"],
            "decision_id": "",
            "trade_id": "",
            "ticker": sig["ticker"],
            "strategy_bucket": sig["strategy_bucket"],
            "original_rank": sig["original_rank"],
            "setup_type": sig["setup_type"],
            "event_timestamp_utc": sig["event_timestamp_utc"],
            "entry_timestamp_utc": entry_ts.isoformat() if entry_ts is not None else "",
            "entry_timestamp_source": entry_source,
            "entry_price_method": method,
            "entry_price_quality": "proxy" if "proxy" in method else "unavailable",
            "analysis_mode": sig["analysis_mode"],
            "cta_vol_join_eligible": cta_eligible,
            "observed_option_pnl_pct": np.nan,
            "observed_option_pnl_currency": np.nan,
            "modelled_option_pnl_pct": np.nan,
            "observed_option_pnl_available": False,
            "observed_pnl_link_confidence": "none",
            "observed_pnl_calculation_method": "",
            "modelled_option_pnl_available": False,
            "underlying_entry_timestamp_utc": entry_ts.isoformat() if entry_ts is not None else "",
            "underlying_entry_price": np.nan,
            "outcome_price_source": "",
            "outcome_calculation_version": RECONSTRUCTION_VERSION,
            "reconstruction_version": RECONSTRUCTION_VERSION,
            "outcome_rules_version": OUTCOME_RULES_VERSION,
        }
        rows.append(add_underlying_outcomes(row, prices))
    return pd.DataFrame(rows)


def add_underlying_outcomes(row: dict[str, Any], prices: dict[str, pd.DataFrame]) -> dict[str, Any]:
    for col in ["underlying_return_1d", "underlying_return_5d", "underlying_return_10d", "underlying_max_adverse_excursion", "underlying_max_favorable_excursion"]:
        row[col] = np.nan
    if not prices:
        return row
    ticker = row["ticker"] if row["ticker"] in prices and not prices[row["ticker"]].empty else "QQQ"
    df = prices.get(ticker, pd.DataFrame())
    ts = parse_timestamp(row.get("entry_timestamp_utc"))[0]
    if df.empty or ts is None:
        return row
    if "date" not in df.columns:
        return row
    work = df.copy()
    work["date_norm"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    date = ts.tz_convert(ET).tz_localize(None).normalize()
    future = work[work["date_norm"] >= date].head(11).reset_index(drop=True)
    if len(future) < 2:
        return row
    entry = safe_float(future.loc[0, "adjusted_close"])
    if pd.isna(entry) or entry <= 0:
        return row
    row["underlying_entry_price"] = entry
    row["outcome_price_source"] = f"price_history:{ticker}"
    returns = future["adjusted_close"] / entry - 1
    for horizon in [1, 5, 10]:
        row[f"underlying_return_{horizon}d"] = returns.iloc[horizon] if len(returns) > horizon else np.nan
    row["underlying_max_adverse_excursion"] = returns.min()
    row["underlying_max_favorable_excursion"] = returns.max()
    return row


def latest_feature(df: pd.DataFrame, asset: str, ts: pd.Timestamp, target_vol: float | None = None) -> tuple[pd.Series | None, str, str]:
    if df.empty:
        return None, "failed", "feature_history_missing"
    work = df[df["asset"].astype(str).eq(asset)].copy()
    if target_vol is not None and "target_vol" in work.columns:
        work = work[np.isclose(pd.to_numeric(work["target_vol"], errors="coerce"), target_vol)]
    if work.empty:
        return None, "failed", f"feature_asset_missing:{asset}"
    work["effective_ts"] = pd.to_datetime(work["effective_available_at_utc"], utc=True, errors="coerce")
    work["asof_ts"] = pd.to_datetime(work["feature_as_of_timestamp_utc"], utc=True, errors="coerce")
    work = work[(work["effective_ts"] <= ts) & (work["asof_ts"] <= ts)]
    if work.empty:
        return None, "failed", "no_temporally_available_feature"
    work["feature_age_hours"] = (ts - work["effective_ts"]).dt.total_seconds() / 3600
    work = work[work["feature_age_hours"] <= MAX_FEATURE_AGE_HOURS]
    if work.empty:
        return None, "failed", "feature_too_old"
    return work.sort_values("effective_ts").iloc[-1], "joined", ""


def feature_asset(ticker: str) -> str:
    if p32 is not None:
        return p32.market_proxy_asset_for_ticker(ticker)
    return "SOXX" if ticker in {"NVDA", "AMD", "AVGO", "MU", "SMH"} else "QQQ"


def build_cta_vol_join(root: Path, panel: pd.DataFrame) -> pd.DataFrame:
    cta_path = root / "market_bomb_history" / "cta_proxy_history.csv"
    vol_path = root / "market_bomb_history" / "vol_control_proxy_history.csv"
    cta = pd.read_csv(cta_path) if cta_path.exists() else pd.DataFrame()
    vol = pd.read_csv(vol_path) if vol_path.exists() else pd.DataFrame()
    rows = []
    for _, event in panel.iterrows():
        if not bool(event.get("cta_vol_join_eligible", True)):
            rows.append(
                {
                    "analysis_unit": event.get("analysis_unit", ""),
                    "signal_event_id": event.get("signal_event_id", ""),
                    "decision_id": event.get("decision_id", ""),
                    "trade_id": event.get("trade_id", ""),
                    "ticker": event.get("ticker", ""),
                    "strategy_bucket": event.get("strategy_bucket", ""),
                    "original_rank": event.get("original_rank", ""),
                    "event_timestamp_utc": event.get("event_timestamp_utc", ""),
                    "feature_id": "",
                    "feature_as_of_timestamp_utc": "",
                    "effective_available_at_utc": "",
                    "feature_age_hours": np.nan,
                    "join_status": "skipped",
                    "join_failure_reason": "cta_vol_join_ineligible",
                    "cta_trend_state": "unavailable",
                    "cta_deleveraging_proxy": "",
                    "vol_control_state": "unavailable",
                    "vol_control_pressure_proxy": "unavailable",
                    "analysis_mode": event.get("analysis_mode", ""),
                }
            )
            continue
        ts = parse_timestamp(event.get("event_timestamp_utc"))[0]
        if ts is None:
            continue
        asset = feature_asset(event["ticker"])
        vol_asset = asset if asset in {"QQQ", "SPY", "SOXX"} else "QQQ"
        cta_row, cta_status, cta_reason = latest_feature(cta, asset, ts)
        vol_row, vol_status, vol_reason = latest_feature(vol, vol_asset, ts, target_vol=0.12)
        status = "joined" if cta_status == "joined" and vol_status == "joined" else "partial" if cta_status == "joined" or vol_status == "joined" else "failed"
        eff = cta_row.get("effective_available_at_utc") if cta_row is not None else ""
        eff_ts = parse_timestamp(eff)[0] if eff else None
        rows.append(
            {
                "analysis_unit": event["analysis_unit"],
                "signal_event_id": event["signal_event_id"],
                "decision_id": event.get("decision_id", ""),
                "trade_id": event.get("trade_id", ""),
                "ticker": event["ticker"],
                "strategy_bucket": event["strategy_bucket"],
                "original_rank": event["original_rank"],
                "event_timestamp_utc": event["event_timestamp_utc"],
                "feature_id": f"{asset}_{cta_row.get('feature_as_of_timestamp_utc') if cta_row is not None else ''}",
                "feature_as_of_timestamp_utc": cta_row.get("feature_as_of_timestamp_utc") if cta_row is not None else "",
                "effective_available_at_utc": eff,
                "feature_age_hours": round((ts - eff_ts).total_seconds() / 3600, 2) if eff_ts is not None else np.nan,
                "join_status": status,
                "join_failure_reason": "; ".join([x for x in [cta_reason, vol_reason] if x]),
                "cta_trend_state": cta_row.get("cta_trend_state") if cta_row is not None else "unavailable",
                "cta_deleveraging_proxy": cta_row.get("cta_deleveraging_proxy") if cta_row is not None else "",
                "vol_control_state": vol_row.get("vol_control_state") if vol_row is not None else "unavailable",
                "vol_control_pressure_proxy": vol_row.get("vol_control_pressure_proxy") if vol_row is not None else "unavailable",
                "analysis_mode": event["analysis_mode"],
            }
        )
    return pd.DataFrame(rows)


def write_templates(root: Path) -> None:
    tdir = root / "market_bomb_reconstruction" / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=["ticker", "event_timestamp_utc", "original_rank", "setup_type", "signal_reason_raw"]).to_csv(tdir / "manual_signal_events_template.csv", index=False)
    pd.DataFrame(columns=["ticker", "decision_timestamp_utc", "decision_action", "decision_reason_raw", "intended_option_delta", "intended_option_dte"]).to_csv(tdir / "manual_entry_decisions_template.csv", index=False)
    pd.DataFrame(columns=["broker", "ticker", "contract_symbol", "fill_timestamp_utc", "side", "quantity", "fill_price", "fees"]).to_csv(tdir / "manual_trade_fills_template.csv", index=False)
    pd.DataFrame(columns=["trade_id", "exit_timestamp_utc", "exit_reason", "exit_price", "exit_quantity", "realized_pnl_pct"]).to_csv(tdir / "manual_trade_exits_template.csv", index=False)
    (tdir / "manual_reconstruction_instructions.md").write_text(
        "# Manual Reconstruction Instructions\n\n"
        "Place completed manual CSV files under `market_bomb_reconstruction/raw_sources/`.\n\n"
        "- Manual rows are `structured_manual_entry`.\n"
        "- Manual rows are `mixed_exploratory`, not `strict_live_replay`.\n"
        "- Do not enter guessed ranks, guessed timestamps, or guessed option PnL.\n",
        encoding="utf-8",
    )


def gate_audit(root: Path, inventory: pd.DataFrame, signals: pd.DataFrame, decisions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame, join: pd.DataFrame, mutation_count: int = 0, artifact_status: str = "not_requested") -> Path:
    path = root / "morita_history_reconstruction_gate_audit.md"
    normalized_count = len(signals) + len(decisions) + len(fills) + len(exits)
    has_inventory = (root / "market_bomb_reconstruction" / "source_inventory.csv").exists()
    has_manifest = (root / "market_bomb_reconstruction" / "source_file_manifest.csv").exists()
    has_templates = (root / "market_bomb_reconstruction" / "templates" / "manual_signal_events_template.csv").exists()
    audit_dir = root / "market_bomb_reconstruction" / "audit"
    pipeline_passed = all([
        has_inventory,
        has_manifest,
        mutation_count == 0,
        (audit_dir / "duplicate_candidates.csv").exists(),
        (audit_dir / "timestamp_resolution_audit.csv").exists(),
        (audit_dir / "parser_execution_audit.csv").exists(),
        (audit_dir / "trade_decision_signal_linkage_audit.csv").exists(),
        (audit_dir / "analysis_run_metadata.json").exists(),
        (root / "market_bomb_reconstruction" / "analysis" / "cta_vol_event_join_audit.csv").exists(),
        has_templates,
    ])
    ready_32c = bool(len(join[join.get("join_status", pd.Series(dtype=str)).isin(["joined", "partial"])]) > 0 and (signals["strategy_bucket"].isin(["S_breakout_momentum", "AB_institutional_pullback"]).any() if not signals.empty else False))
    reasons = []
    if not pipeline_passed:
        reasons.append("reconstruction_pipeline_gate requirements not fully met")
    if inventory.empty:
        reasons.append("blocked_by_missing_sources")
    if normalized_count == 0:
        reasons.append("no normalized signal decision trade or exit rows")
    if not ready_32c:
        reasons.append("phase3_2c_research_ready false due to insufficient joined events or strategy samples")
    text = (
        "# Morita History Reconstruction Gate Audit\n\n"
        f"reconstruction_pipeline_gate: `{'passed' if pipeline_passed else 'blocked'}`\n\n"
        f"phase3_2c_research_ready: `{str(ready_32c).lower()}`\n\n"
        f"source_count: `{len(inventory)}`\n\n"
        f"signal_events: `{len(signals)}`\n\n"
        f"entry_decisions: `{len(decisions)}`\n\n"
        f"trade_fills: `{len(fills)}`\n\n"
        f"trade_exits: `{len(exits)}`\n\n"
        f"cta_vol_join_rows: `{len(join)}`\n\n"
        f"input_source_mutation_count: `{mutation_count}`\n\n"
        f"raw_source_mutation_count: `{mutation_count}`\n\n"
        f"artifact_source_status: `{artifact_status}`\n\n"
        "Blocking reasons:\n\n"
        + ("\n".join(f"- {r}" for r in reasons) if reasons else "- none")
        + "\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def write_outputs(root: Path, inventory: pd.DataFrame, manifest: pd.DataFrame, signals: pd.DataFrame, decisions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame, dupes: pd.DataFrame, linkage: pd.DataFrame, panel: pd.DataFrame, join: pd.DataFrame, artifact_status: str, parser_audit: pd.DataFrame | None = None, timestamp_audit: pd.DataFrame | None = None, include_repo_sources: bool = True) -> dict[str, Path]:
    base = root / "market_bomb_reconstruction"
    norm = base / "normalized"
    audit = base / "audit"
    analysis = base / "analysis"
    for d in [base, norm, audit, analysis]:
        d.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(base / "source_inventory.csv", index=False)
    (base / "source_inventory.md").write_text("# Source Inventory\n\n" + markdown_table(inventory) + "\n", encoding="utf-8")
    manifest.to_csv(base / "source_file_manifest.csv", index=False)
    (base / "source_ingestion_audit.md").write_text(
        "# Source Ingestion Audit\n\n"
        f"artifact_source_status: `{artifact_status}`\n\n"
        f"sources_discovered: `{len(inventory)}`\n\n"
        f"signals_parsed: `{len(signals)}`\n\n"
        f"decisions_parsed: `{len(decisions)}`\n\n"
        f"fills_parsed: `{len(fills)}`\n\n"
        f"exits_parsed: `{len(exits)}`\n",
        encoding="utf-8",
    )
    write_table(signals, norm / "signal_events.csv", norm / "signal_events.parquet")
    write_table(decisions, norm / "entry_decisions.csv", norm / "entry_decisions.parquet")
    write_table(fills, norm / "trade_fills.csv", norm / "trade_fills.parquet")
    write_table(exits, norm / "trade_exits.csv", norm / "trade_exits.parquet")
    dupes.to_csv(audit / "duplicate_candidates.csv", index=False)
    linkage.to_csv(audit / "event_linkage_audit.csv", index=False)
    linkage.to_csv(audit / "trade_decision_signal_linkage_audit.csv", index=False)
    (audit / "trade_decision_signal_linkage_audit.md").write_text("# Trade Decision Signal Linkage Audit\n\n" + markdown_table(linkage) + "\n", encoding="utf-8")
    parser_audit = parser_audit if parser_audit is not None else pd.DataFrame(columns=PARSER_EXECUTION_COLUMNS)
    timestamp_audit = timestamp_audit if timestamp_audit is not None else pd.DataFrame(columns=TIMESTAMP_AUDIT_COLUMNS)
    parser_audit.to_csv(audit / "parser_execution_audit.csv", index=False)
    timestamp_audit.to_csv(audit / "timestamp_resolution_audit.csv", index=False)
    (audit / "timestamp_resolution_audit.md").write_text("# Timestamp Resolution Audit\n\n" + markdown_table(timestamp_audit) + "\n", encoding="utf-8")
    before_manifest_path = audit / "input_source_hash_manifest_before.csv"
    before = pd.read_csv(before_manifest_path) if before_manifest_path.exists() else input_source_hash_manifest(root, include_repo_sources)
    after = input_source_hash_manifest(root, include_repo_sources)
    after.to_csv(audit / "input_source_hash_manifest_after.csv", index=False)
    if not before_manifest_path.exists():
        before.to_csv(before_manifest_path, index=False)
    mutation_count, mutation_report = compare_input_source_manifests(before, after)
    (audit / "input_source_mutation_report.txt").write_text(mutation_report, encoding="utf-8")
    (root / "input_source_mutation_count.txt").write_text(f"input_source_mutation_count={mutation_count}\n", encoding="utf-8")
    meta = analysis_metadata()
    with (audit / "analysis_run_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    write_table(panel, analysis / "morita_event_outcome_panel.csv", analysis / "morita_event_outcome_panel.parquet")
    write_table(join, analysis / "cta_vol_event_join_audit.csv", analysis / "cta_vol_event_join_audit.parquet")
    write_templates(root)
    gate = gate_audit(root, inventory, signals, decisions, fills, exits, join, mutation_count=mutation_count, artifact_status=artifact_status)
    (root / "raw_source_mutation_count.txt").write_text(f"raw_source_mutation_count={mutation_count}\n", encoding="utf-8")
    (root / "raw_source_mutation_report.txt").write_text(mutation_report, encoding="utf-8")
    return {
        "source_inventory": base / "source_inventory.csv",
        "signal_events": norm / "signal_events.csv",
        "entry_decisions": norm / "entry_decisions.csv",
        "trade_fills": norm / "trade_fills.csv",
        "trade_exits": norm / "trade_exits.csv",
        "outcome_panel": analysis / "morita_event_outcome_panel.csv",
        "cta_vol_join": analysis / "cta_vol_event_join_audit.csv",
        "parser_execution_audit": audit / "parser_execution_audit.csv",
        "timestamp_resolution_audit": audit / "timestamp_resolution_audit.csv",
        "input_source_mutation_count": root / "input_source_mutation_count.txt",
        "gate": gate,
    }


def run(root: Path = Path("."), include_repo_sources: bool = True, include_github_action_artifacts: bool = False, build_underlying_outcomes: bool = True) -> dict[str, Path]:
    audit = root / "market_bomb_reconstruction" / "audit"
    write_input_source_hash_manifest(root, audit / "input_source_hash_manifest_before.csv", include_repo_sources)
    inventory, manifest = build_source_inventory(root, include_repo_sources)
    artifact_status = "unavailable" if include_github_action_artifacts else "not_requested"
    if include_github_action_artifacts:
        artifact_status = "unavailable_api_retrieval_not_implemented_in_research_runner"
    signals, decisions, fills, exits, parser_audit, timestamp_audit = parse_sources_with_audits(root, inventory)
    dupes, linkage, canonical_signals = duplicate_audit(signals)
    panel = build_outcome_panel(root, canonical_signals, decisions, fills, exits, build_underlying_outcomes)
    join = build_cta_vol_join(root, panel)
    return write_outputs(root, inventory, manifest, canonical_signals, decisions, fills, exits, dupes, linkage, panel, join, artifact_status, parser_audit, timestamp_audit, include_repo_sources)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--skip-repo-sources", action="store_true")
    parser.add_argument("--include-github-action-artifacts", action="store_true")
    parser.add_argument("--skip-underlying-outcomes", action="store_true")
    args = parser.parse_args()
    outputs = run(
        Path(args.root),
        include_repo_sources=not args.skip_repo_sources,
        include_github_action_artifacts=args.include_github_action_artifacts,
        build_underlying_outcomes=not args.skip_underlying_outcomes,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
