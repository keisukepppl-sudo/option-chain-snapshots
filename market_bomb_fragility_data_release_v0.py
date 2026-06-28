#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import pandas as pd

import market_bomb_fragility_score_v0 as scorer


ARTIFACT_VERSION = "fragility_data_release_v0_2_2"
RELEASE_CONTENT_MANIFEST_VERSION = "fragility_release_content_manifest_v0_2_2"
RELEASE_CORE_METADATA_VERSION = "fragility_release_core_metadata_v0_2_2"
EXECUTION_CONTENT_MANIFEST_VERSION = "fragility_execution_content_manifest_v0_2_2"
ACTIONIZATION_ALLOWED = False
REQUIRED_TICKERS = ["SPY", "QQQ", "VIX", "VIX3M"]
OPTIONAL_TICKERS = ["SOXX", "VIX9D"]
PRICE_TICKERS = ["SPY", "QQQ", "SOXX"]
VOL_TICKERS = ["VIX", "VIX3M", "VIX9D"]
SECRET_KEYS = ["apikey", "api_key", "token", "bearer", "password", "cookie", "secret", "authorization"]

ATTESTATION_COLUMNS = [
    "release_id",
    "source_id",
    "ticker",
    "asset_family",
    "provider_name",
    "provider_dataset_name",
    "source_url_or_local_export_reference",
    "terms_url_or_reference",
    "terms_review_status",
    "allowed_usage_assertion",
    "operator_personal_research_only",
    "retrieved_at_utc",
    "price_basis",
    "historical_effective_availability_policy",
    "row_effective_timestamp_field",
    "source_timezone",
    "expected_schema_profile",
    "source_file_sha256",
    "source_file_bytes",
    "source_file_row_count",
    "attestation_status",
    "attestation_reason",
]

INVENTORY_COLUMNS = [
    "release_id",
    "source_id",
    "ticker",
    "staged_relative_path",
    "source_file_exists",
    "source_file_sha256",
    "source_file_bytes",
    "raw_row_count",
    "canonical_valid_row_count",
    "selected_invalid_row_count",
    "first_raw_date",
    "last_raw_date",
    "first_canonical_date",
    "last_canonical_date",
]

SCHEMA_COLUMNS = ["release_id", "source_id", "ticker", "required_column", "column_present", "schema_status", "schema_reason"]
TERMS_COLUMNS = [
    "release_id",
    "source_id",
    "ticker",
    "terms_review_status",
    "allowed_usage_assertion",
    "raw_data_git_ignored",
    "credentials_present_in_manifest",
    "terms_gate_status",
    "terms_gate_reason",
]
AVAILABILITY_COLUMNS = [
    "release_id",
    "source_id",
    "ticker",
    "availability_policy",
    "row_effective_timestamp_field",
    "policy_effective_timestamp_rows",
    "explicit_effective_timestamp_rows",
    "assumed_effective_timestamp_rows",
    "invalid_effective_timestamp_rows",
    "availability_confidence_summary",
    "availability_policy_status",
    "availability_policy_reason",
]
COVERAGE_COLUMNS = [
    "release_id",
    "source_id",
    "ticker",
    "required_for_official_market_score",
    "optional_source",
    "minimum_required_start_date",
    "actual_first_valid_session_date",
    "actual_last_valid_session_date",
    "calendar_session_count_in_range",
    "valid_source_session_count",
    "missing_source_session_count",
    "missing_source_session_dates_hash",
    "recent_126_session_complete",
    "recent_252_session_complete",
    "latest_completed_session_timely_source_present",
    "recent_126_session_timely_complete",
    "recent_252_session_timely_complete",
    "late_effective_timestamp_row_count",
    "timeliness_coverage_status",
    "timeliness_coverage_reason",
    "latest_completed_nyse_session",
    "latest_completed_session_source_present",
    "staleness_session_count",
    "coverage_status",
    "coverage_reason",
]
TIMELINESS_COLUMNS = [
    "release_id",
    "source_id",
    "ticker",
    "raw_row_ordinal",
    "session_date",
    "decision_timestamp_utc",
    "effective_available_at_utc",
    "availability_basis",
    "availability_confidence",
    "source_row_timeliness_status",
    "source_row_timeliness_reason",
    "accepted_into_canonical_input",
]
CROSS_COLUMNS = ["release_id", "audit_name", "scope", "status", "reason", "count", "details"]
GATE_COLUMNS = [
    "release_id",
    "gate_scope",
    "ticker",
    "required_for_official_market_score",
    "quality_gate_status",
    "quality_gate_reason",
    "terms_gate_status",
    "schema_gate_status",
    "coverage_gate_status",
    "calendar_policy_gate_status",
    "timeliness_gate_status",
    "availability_gate_status",
    "duplicate_gate_status",
    "scorer_preflight_status",
    "hard_gate_valid",
    "freshness_valid",
    "stale_only",
    "promotion_eligible_default",
    "promotion_eligible_with_stale_override",
    "promotion_eligible",
]


def utc_now() -> pd.Timestamp:
    fixed = os.environ.get("FRAGILITY_RELEASE_NOW_UTC")
    if fixed:
        return pd.Timestamp(fixed).tz_convert("UTC")
    return pd.Timestamp.now(tz="UTC")


def parse_now_utc(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise SystemExit("--now-utc must be timezone-aware")
    return ts.tz_convert("UTC")


def iso_utc(ts: Any) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(df: pd.DataFrame, path: Path, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        df = pd.DataFrame(df, columns=columns)
    df.to_csv(path, index=False)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def platform_write_path(path: Path) -> Path:
    resolved = path.resolve()
    if os.name == "nt":
        text = str(resolved)
        if not text.startswith("\\\\?\\"):
            return Path("\\\\?\\" + text)
    return resolved


def history_root(root: Path) -> Path:
    return root / "market_bomb_history" / "fragility_score_v0"


def staging_dir(root: Path, staging_id: str) -> Path:
    return history_root(root) / "staging" / staging_id


def releases_dir(root: Path) -> Path:
    return history_root(root) / "releases"


def release_dir(root: Path, release_id: str) -> Path:
    return releases_dir(root) / release_id


def active_pointer_path(root: Path) -> Path:
    return history_root(root) / "active_release.json"


def staging_path_has_symlink(path: Path, stop_at: Path) -> bool:
    current = path.resolve()
    stop = stop_at.resolve()
    parts = []
    while True:
        parts.append(current)
        if current == stop:
            break
        if current.parent == current:
            break
        current = current.parent
    for item in parts:
        if item.exists() and item.is_symlink():
            return True
    return False


def validate_source_relative_path(relative_path: Any) -> str:
    rel_text = str(relative_path or "").replace("\\", "/").strip()
    if not rel_text:
        raise SystemExit("empty source relative_path is not allowed")
    posix = PurePosixPath(rel_text)
    windows = PureWindowsPath(str(relative_path or ""))
    if posix.is_absolute() or windows.is_absolute() or windows.drive or str(relative_path or "").startswith("\\\\"):
        raise SystemExit(f"absolute source relative_path is not allowed: {relative_path}")
    if ".." in posix.parts or ".." in windows.parts:
        raise SystemExit(f"path traversal source relative_path is not allowed: {relative_path}")
    return posix.as_posix()


def validate_staging_source_paths(root: Path, staging_id: str, sources: list[dict[str, Any]]) -> dict[str, Path]:
    base = staging_dir(root, staging_id).resolve()
    if base.is_symlink() or not base.exists():
        raise SystemExit(f"missing or unsafe staging directory: {base}")
    resolved: dict[str, Path] = {}
    used_paths: set[str] = set()
    for source in sources:
        source_id = str(source.get("source_id", ""))
        rel_text = validate_source_relative_path(source.get("relative_path", ""))
        path = (base / rel_text).resolve()
        try:
            path.relative_to(base)
        except Exception as exc:
            raise SystemExit(f"source relative_path escapes staging root: {rel_text}") from exc
        normalized = path.as_posix().lower() if os.name == "nt" else path.as_posix()
        if normalized in used_paths:
            raise SystemExit(f"duplicate staged source path is not allowed: {rel_text}")
        used_paths.add(normalized)
        if staging_path_has_symlink(path, base):
            raise SystemExit(f"symlinked staging source path is not allowed: {rel_text}")
        if not path.is_file():
            raise SystemExit(f"staged source is not a regular file: {rel_text}")
        resolved[source_id] = path
    return resolved


def content_manifest_path(rel: Path) -> Path:
    return rel / "release_content_manifest.json"


def receipt_path(rel: Path) -> Path:
    return rel / "release_receipt.json"


def safe_relative_path(base: Path, path: Path) -> str:
    resolved_text = str(path.resolve())
    base_text = str(base.resolve())
    if resolved_text.startswith("\\\\?\\"):
        resolved_text = resolved_text[4:]
    if base_text.startswith("\\\\?\\"):
        base_text = base_text[4:]
    rel = Path(resolved_text).relative_to(Path(base_text))
    text = rel.as_posix()
    if text.startswith("../") or text == ".." or Path(text).is_absolute():
        raise SystemExit(f"unsafe release manifest path: {text}")
    return text


def release_core_candidate_files(rel: Path) -> list[Path]:
    files: list[Path] = []
    for base in [
        rel / "canonical_input",
        rel / "preflight_fragility_outputs",
    ]:
        platform_base = platform_write_path(base)
        if platform_base.exists():
            files.extend([p for p in platform_base.rglob("*") if p.is_file()])
    for name in [
        "source_attestations.csv",
        "source_file_inventory.csv",
        "source_schema_audit.csv",
        "source_coverage_audit.csv",
        "source_availability_policy_audit.csv",
        "source_timeliness_audit.csv",
        "source_terms_audit.csv",
        "source_cross_source_audit.csv",
        "release_quality_gate.csv",
        "release_core_metadata.json",
    ]:
        path = platform_write_path(rel / name)
        if path.exists():
            files.append(path)
    return sorted(files, key=lambda p: safe_relative_path(rel, p))


def required_release_core_files() -> set[str]:
    return {
        "source_attestations.csv",
        "source_file_inventory.csv",
        "source_schema_audit.csv",
        "source_coverage_audit.csv",
        "source_availability_policy_audit.csv",
        "source_timeliness_audit.csv",
        "source_terms_audit.csv",
        "source_cross_source_audit.csv",
        "release_quality_gate.csv",
        "release_core_metadata.json",
    }


def core_entry_category(relative_path: str) -> str:
    if relative_path.startswith("canonical_input/"):
        return "canonical_input"
    if relative_path.startswith("preflight_fragility_outputs/"):
        return "preflight_fragility_outputs"
    return "release_audit"


def content_set_hash(entries: list[dict[str, Any]]) -> str:
    parts = []
    for entry in sorted(entries, key=lambda e: str(e["relative_path"])):
        parts.append(f"{entry['relative_path']}\0{entry['sha256']}\0{entry['bytes']}\n")
    return bytes_sha256("".join(parts).encode("utf-8"))


def build_content_manifest(rel: Path, release_id: str) -> dict[str, Any]:
    entries = []
    seen: set[str] = set()
    for path in release_core_candidate_files(rel):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"unsafe release core path: {path}")
        relative_path = safe_relative_path(rel, path)
        if relative_path in seen:
            raise SystemExit(f"duplicate release core manifest path: {relative_path}")
        seen.add(relative_path)
        entries.append(
            {
                "relative_path": relative_path,
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
                "category": core_entry_category(relative_path),
                "required": True,
            }
        )
    return {
        "artifact_version": RELEASE_CONTENT_MANIFEST_VERSION,
        "release_id": release_id,
        "created_at_utc": iso_utc(utc_now()),
        "content_set_kind": "immutable_release_core",
        "entries": sorted(entries, key=lambda e: str(e["relative_path"])),
        "core_content_set_sha256": content_set_hash(entries),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def write_content_manifest(rel: Path, release_id: str) -> dict[str, Any]:
    manifest = build_content_manifest(rel, release_id)
    content_manifest_path(rel).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def validate_content_manifest(rel: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("artifact_version") != RELEASE_CONTENT_MANIFEST_VERSION:
        raise SystemExit("unsupported release content manifest version")
    entries = manifest.get("entries", [])
    if not isinstance(entries, list) or not entries:
        raise SystemExit("release content manifest has no entries")
    seen: set[str] = set()
    recomputed_entries = []
    for entry in entries:
        relative_path = str(entry.get("relative_path", ""))
        if not relative_path or relative_path.startswith("/") or relative_path.startswith("\\") or ".." in Path(relative_path).parts:
            raise SystemExit(f"unsafe release content manifest path: {relative_path}")
        if relative_path in seen:
            raise SystemExit(f"duplicate release content manifest path: {relative_path}")
        seen.add(relative_path)
        path = rel / relative_path
        try:
            safe_relative_path(rel, path)
        except Exception as exc:
            raise SystemExit(f"unsafe release content path: {relative_path}") from exc
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"missing or unsafe immutable release file: {relative_path}")
        size = path.stat().st_size
        sha = file_sha256(path)
        if int(entry.get("bytes", -1)) != size:
            raise SystemExit(f"immutable release file size mismatch: {relative_path}")
        if str(entry.get("sha256", "")) != sha:
            raise SystemExit(f"immutable release file sha mismatch: {relative_path}")
        recomputed_entries.append(
            {
                "relative_path": relative_path,
                "sha256": sha,
                "bytes": size,
                "category": entry.get("category", ""),
                "required": entry.get("required", True),
            }
        )
    actual_core_files = {safe_relative_path(rel, p) for p in release_core_candidate_files(rel)}
    if actual_core_files != seen:
        raise SystemExit("immutable release core file set does not match content manifest")
    missing_required = sorted(required_release_core_files() - seen)
    if missing_required:
        raise SystemExit(f"missing required immutable release core file(s): {','.join(missing_required)}")
    if not any(p.startswith("canonical_input/") for p in seen):
        raise SystemExit("missing canonical input from immutable release core")
    if not any(p.startswith("preflight_fragility_outputs/") for p in seen):
        raise SystemExit("missing preflight output from immutable release core")
    actual_set_hash = content_set_hash(recomputed_entries)
    if manifest.get("core_content_set_sha256") != actual_set_hash:
        raise SystemExit("release core content set hash mismatch")


def build_execution_content_manifest(execution_dir: Path, release_id: str, execution_id: str) -> dict[str, Any]:
    entries = []
    for path in sorted([p for p in platform_write_path(execution_dir).rglob("*") if p.is_file()], key=lambda p: str(p)):
        rel = safe_relative_path(execution_dir, path)
        if rel in {"execution_content_manifest.json", "fragility_score_execution_receipt_v0.json"}:
            continue
        entries.append({"relative_path": rel, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {
        "artifact_version": EXECUTION_CONTENT_MANIFEST_VERSION,
        "release_id": release_id,
        "execution_id": execution_id,
        "created_at_utc": iso_utc(utc_now()),
        "entries": entries,
        "execution_content_set_sha256": content_set_hash(
            [{**e, "category": "execution", "required": True} for e in entries]
        ),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {"date": "session_date", "adj_close": "adjusted_close", "adjusted_close": "adjusted_close"}
    renamed = {col: aliases.get(str(col).strip().lower(), str(col).strip().lower()) for col in df.columns}
    return df.rename(columns=renamed)


def has_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for k, v in value.items():
            lk = str(k).lower()
            if any(key in lk for key in SECRET_KEYS):
                return True
            if has_secret_key(v):
                return True
    elif isinstance(value, list):
        return any(has_secret_key(v) for v in value)
    return False


def latest_completed_session(root: Path, now_utc: pd.Timestamp | None = None) -> str:
    now = now_utc or utc_now()
    cal = scorer.load_calendar(root)
    eligible = cal[pd.to_datetime(cal["decision_timestamp_utc"], utc=True) <= now]
    if eligible.empty:
        return ""
    return str(eligible.iloc[-1]["session_date"])


def decision_map(root: Path) -> dict[str, str]:
    cal = scorer.load_calendar(root)
    return cal.set_index("session_date")["decision_timestamp_utc"].to_dict()


def source_output_path(canonical_root: Path, ticker: str) -> Path:
    if ticker in PRICE_TICKERS:
        return canonical_root / "daily_prices" / f"{ticker}.csv"
    return canonical_root / "volatility_indices" / f"{ticker}.csv"


def manifest_path_for_staging(root: Path, staging_id: str) -> Path:
    return staging_dir(root, staging_id) / "source_bundle_manifest.json"


def load_staging_manifest(root: Path, staging_id: str) -> dict[str, Any]:
    path = manifest_path_for_staging(root, staging_id)
    if not path.exists():
        raise SystemExit(f"missing staged source bundle manifest: {path}")
    manifest = load_json(path)
    if has_secret_key(manifest):
        raise SystemExit("staged manifest contains credential-like key; refusing to continue")
    return manifest


def source_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("sources", []))


def source_terms_ok(manifest: dict[str, Any], source: dict[str, Any], required: bool) -> tuple[str, str]:
    op = manifest.get("operator_attestation", {})
    if required and source.get("price_basis") != "as_traded_close":
        return "data_quality_blocked", "price_basis_not_as_traded_close"
    ok = (
        source.get("terms_review_status") == "operator_acknowledged"
        and source.get("allowed_usage_assertion") == "personal_research_only"
        and op.get("personal_research_only") is True
        and op.get("terms_reviewed_by_operator") is True
        and op.get("do_not_commit_raw_data") is True
    )
    if ok or not required:
        return "valid", "valid" if ok else "optional_source_terms_unavailable"
    return "data_quality_blocked", "terms_or_usage_not_operator_acknowledged"


def staged_source_path(root: Path, staging_id: str, source: dict[str, Any]) -> Path:
    rel_text = validate_source_relative_path(source.get("relative_path", ""))
    base = staging_dir(root, staging_id).resolve()
    path = (base / rel_text).resolve()
    try:
        path.relative_to(base)
    except Exception as exc:
        raise SystemExit(f"source relative_path escapes staging root: {rel_text}") from exc
    return path


def validate_source_set(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    sources = source_records(manifest)
    tickers = [str(s.get("ticker", "")).upper() for s in sources]
    if len([t for t in tickers if t]) != len(set([t for t in tickers if t])):
        raise SystemExit("duplicate ticker source records are not allowed")
    source_ids = [str(s.get("source_id", "")) for s in sources]
    if len(source_ids) != len(set(source_ids)):
        raise SystemExit("duplicate source_id records are not allowed")
    missing = [t for t in REQUIRED_TICKERS if t not in tickers]
    if missing:
        raise SystemExit(f"missing required source ticker(s): {','.join(missing)}")
    return sources


def compute_bundle_hash(root: Path, staging_id: str, manifest: dict[str, Any]) -> str:
    h = hashlib.sha256()
    manifest_bytes = manifest_path_for_staging(root, staging_id).read_bytes()
    h.update(manifest_bytes)
    validate_staging_source_paths(root, staging_id, source_records(manifest))
    for source in sorted(source_records(manifest), key=lambda s: str(s.get("source_id", ""))):
        path = staged_source_path(root, staging_id, source)
        h.update(str(source.get("source_id", "")).encode())
        if path.exists():
            h.update(file_sha256(path).encode())
    return h.hexdigest()


def make_release_id(root: Path, staging_id: str, manifest: dict[str, Any]) -> str:
    digest = compute_bundle_hash(root, staging_id, manifest)
    return f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{digest[:12]}"


def parse_source_rows(root: Path, staging_id: str, release_id: str, source: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    path = staged_source_path(root, staging_id, source)
    ticker = str(source.get("ticker", "")).upper()
    info = {
        "exists": path.exists(),
        "sha": file_sha256(path) if path.exists() else "",
        "bytes": path.stat().st_size if path.exists() else 0,
        "raw_row_count": 0,
        "canonical_valid_row_count": 0,
        "selected_invalid_row_count": 0,
        "first_raw_date": "",
        "last_raw_date": "",
        "first_canonical_date": "",
        "last_canonical_date": "",
        "schema_valid": False,
        "availability_status": "valid",
        "availability_reason": "valid",
        "late_effective_timestamp_row_count": 0,
    }
    timeliness_rows: list[dict[str, Any]] = []
    if not path.exists():
        return pd.DataFrame(), info, timeliness_rows
    raw = normalize_headers(pd.read_csv(path))
    if has_secret_key(list(raw.columns)):
        raise SystemExit(f"staged source appears to contain credential-like column names: {source.get('source_id', '')}")
    info["raw_row_count"] = len(raw)
    if "session_date" not in raw.columns or "close" not in raw.columns:
        return pd.DataFrame(), info, timeliness_rows
    cal = decision_map(root)
    rows: list[dict[str, Any]] = []
    invalid = 0
    for ordinal, row in enumerate(raw.to_dict("records"), start=1):
        session_date = scorer.as_date(row.get("session_date", ""))
        close = pd.to_numeric(pd.Series([row.get("close", None)]), errors="coerce").iloc[0]
        decision_ts = cal.get(session_date, "")
        audit_row = {
            "release_id": release_id,
            "source_id": source.get("source_id", ""),
            "ticker": ticker,
            "raw_row_ordinal": ordinal,
            "session_date": session_date,
            "decision_timestamp_utc": decision_ts,
            "effective_available_at_utc": "",
            "availability_basis": "",
            "availability_confidence": "",
            "source_row_timeliness_status": "",
            "source_row_timeliness_reason": "",
            "accepted_into_canonical_input": False,
        }
        if session_date:
            info["first_raw_date"] = min([d for d in [info["first_raw_date"], session_date] if d], default=session_date)
            info["last_raw_date"] = max([d for d in [info["last_raw_date"], session_date] if d], default=session_date)
        if not session_date or session_date not in cal:
            invalid += 1
            audit_row["source_row_timeliness_status"] = "selected_invalid_non_nyse_session"
            audit_row["source_row_timeliness_reason"] = "non_nyse_session_or_missing_session_date"
            timeliness_rows.append(audit_row)
            continue
        if pd.isna(close) or float(close) <= 0:
            invalid += 1
            audit_row["source_row_timeliness_status"] = "selected_invalid_nonpositive_close"
            audit_row["source_row_timeliness_reason"] = "missing_or_nonpositive_close"
            timeliness_rows.append(audit_row)
            continue
        eff_field = str(source.get("row_effective_timestamp_field", "") or "")
        raw_eff = row.get(eff_field, "") if eff_field else row.get("effective_available_at_utc", "")
        if not scorer.is_blank_value(raw_eff):
            if not scorer.is_tz_aware(raw_eff):
                invalid += 1
                audit_row["effective_available_at_utc"] = str(raw_eff)
                audit_row["availability_basis"] = "explicit_row_effective_timestamp"
                audit_row["availability_confidence"] = "unavailable"
                audit_row["source_row_timeliness_status"] = "selected_invalid_timezone_naive_effective_timestamp"
                audit_row["source_row_timeliness_reason"] = "timezone_naive_effective_timestamp"
                timeliness_rows.append(audit_row)
                continue
            effective = scorer.iso_utc(scorer.parse_ts(raw_eff))
            confidence = "high"
            basis = "explicit_row_effective_timestamp"
            if pd.Timestamp(effective) > pd.Timestamp(decision_ts):
                invalid += 1
                info["late_effective_timestamp_row_count"] += 1
                audit_row["effective_available_at_utc"] = effective
                audit_row["availability_basis"] = basis
                audit_row["availability_confidence"] = confidence
                audit_row["source_row_timeliness_status"] = "unavailable_coverage_late_effective_timestamp"
                audit_row["source_row_timeliness_reason"] = "effective_available_after_decision_timestamp"
                timeliness_rows.append(audit_row)
                continue
        else:
            effective = cal[session_date]
            confidence = "medium"
            basis = "assumed_nyse_close_plus_15_minutes_v0_2"
        audit_row["effective_available_at_utc"] = effective
        audit_row["availability_basis"] = basis
        audit_row["availability_confidence"] = confidence
        audit_row["source_row_timeliness_status"] = "valid_timely"
        audit_row["source_row_timeliness_reason"] = "valid"
        audit_row["accepted_into_canonical_input"] = True
        timeliness_rows.append(audit_row)
        rows.append(
            {
                "raw_row_ordinal": ordinal,
                "session_date": session_date,
                "close": float(close),
                "high": row.get("high", ""),
                "low": row.get("low", ""),
                "volume": row.get("volume", ""),
                "source_row_identifier": f"{release_id}:{source.get('source_id')}:{ordinal}",
                "source_as_of_timestamp_utc": row.get("source_as_of_timestamp_utc", source.get("retrieved_at_utc", "")),
                "effective_available_at_utc": effective,
                "source_url_or_path": source.get("source_url_or_local_export_reference", ""),
                "source_content_hash": info["sha"],
                "availability_confidence": confidence,
                "release_id": release_id,
                "source_id": source.get("source_id", ""),
                "provider_name": source.get("provider_name", ""),
                "price_basis": source.get("price_basis", ""),
                "availability_basis": basis,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        dup_mask = out.duplicated(["session_date"], keep=False)
        invalid += int(dup_mask.sum())
        duplicate_ordinals = set(out.loc[dup_mask, "raw_row_ordinal"].astype(int).tolist())
        for audit_row in timeliness_rows:
            if int(audit_row["raw_row_ordinal"]) in duplicate_ordinals:
                audit_row["source_row_timeliness_status"] = "selected_invalid_duplicate_ticker_session"
                audit_row["source_row_timeliness_reason"] = "duplicate_source_session_date"
                audit_row["accepted_into_canonical_input"] = False
        out = out[~dup_mask].copy()
    if not out.empty and "raw_row_ordinal" in out.columns:
        out = out.drop(columns=["raw_row_ordinal"])
    info["canonical_valid_row_count"] = len(out)
    info["selected_invalid_row_count"] = invalid
    if not out.empty:
        info["first_canonical_date"] = str(out["session_date"].min())
        info["last_canonical_date"] = str(out["session_date"].max())
    info["schema_valid"] = True
    if len(raw) and "effective_available_at_utc" not in raw.columns and not source.get("row_effective_timestamp_field"):
        info["availability_status"] = "valid"
        info["availability_reason"] = "policy_assumed_historical_daily_rows"
    return out, info, timeliness_rows


def recent_window_complete(valid_dates: set[str], calendar_dates: list[str], latest_session: str, length: int) -> bool:
    if not latest_session or latest_session not in calendar_dates:
        return False
    idx = calendar_dates.index(latest_session)
    if idx - length + 1 < 0:
        return False
    window = calendar_dates[idx - length + 1 : idx + 1]
    return all(d in valid_dates for d in window)


def build_release(root: Path, staging_id: str, allow_stale: bool = False, now_utc: str | None = None) -> str:
    manifest = load_staging_manifest(root, staging_id)
    sources = validate_source_set(manifest)
    validate_staging_source_paths(root, staging_id, sources)
    release_id = make_release_id(root, staging_id, manifest)
    final_rel = release_dir(root, release_id)
    if final_rel.exists():
        raise SystemExit(f"release already exists and cannot be overwritten: {release_id}")
    releases_dir(root).mkdir(parents=True, exist_ok=True)
    rel = releases_dir(root) / f".building_{release_id}_{uuid.uuid4().hex[:8]}"
    if rel.exists():
        raise SystemExit(f"temporary release build directory collision: {rel.name}")
    rel.mkdir(parents=True)
    canonical_root = rel / "canonical_input"
    latest_session = latest_completed_session(root, parse_now_utc(now_utc) if now_utc else None)
    cal_df = scorer.load_calendar(root)
    cal_dates = list(cal_df["session_date"].astype(str))
    calendar_min = cal_dates[0] if cal_dates else ""
    policy = load_json(root / "market_bomb_config" / "fragility_data_release_v0_policy.json")
    minimum_start = str(policy.get("minimum_required_start_date", "2016-01-01"))
    calendar_policy_valid = bool(calendar_min and calendar_min <= minimum_start)
    calendar_policy_status = "valid" if calendar_policy_valid else "data_quality_blocked"
    calendar_policy_reason = "valid" if calendar_policy_valid else "calendar_contract_insufficient_for_policy"

    attestations = []
    inventory_rows = []
    schema_rows = []
    terms_rows = []
    availability_rows = []
    timeliness_rows = []
    coverage_rows = []
    canonical_by_ticker: dict[str, pd.DataFrame] = {}
    source_infos: dict[str, dict[str, Any]] = {}

    for source in sources:
        ticker = str(source.get("ticker", "")).upper()
        required = ticker in REQUIRED_TICKERS
        path = staged_source_path(root, staging_id, source)
        df, info, source_timeliness_rows = parse_source_rows(root, staging_id, release_id, source)
        timeliness_rows.extend(source_timeliness_rows)
        source_infos[ticker] = info
        canonical_by_ticker[ticker] = df
        if not df.empty:
            out_path = source_output_path(canonical_root, ticker)
            write_csv(df, out_path)
        terms_status, terms_reason = source_terms_ok(manifest, source, required)
        file_hash = info["sha"]
        file_bytes = info["bytes"]
        attestations.append(
            {
                "release_id": release_id,
                "source_id": source.get("source_id", ""),
                "ticker": ticker,
                "asset_family": source.get("asset_family", ""),
                "provider_name": source.get("provider_name", ""),
                "provider_dataset_name": source.get("provider_dataset_name", ""),
                "source_url_or_local_export_reference": source.get("source_url_or_local_export_reference", ""),
                "terms_url_or_reference": source.get("terms_url_or_reference", ""),
                "terms_review_status": source.get("terms_review_status", ""),
                "allowed_usage_assertion": source.get("allowed_usage_assertion", ""),
                "operator_personal_research_only": manifest.get("operator_attestation", {}).get("personal_research_only", False),
                "retrieved_at_utc": source.get("retrieved_at_utc", ""),
                "price_basis": source.get("price_basis", ""),
                "historical_effective_availability_policy": source.get("historical_effective_availability_policy", ""),
                "row_effective_timestamp_field": source.get("row_effective_timestamp_field", ""),
                "source_timezone": source.get("source_timezone", ""),
                "expected_schema_profile": source.get("expected_schema_profile", ""),
                "source_file_sha256": file_hash,
                "source_file_bytes": file_bytes,
                "source_file_row_count": info["raw_row_count"],
                "attestation_status": terms_status,
                "attestation_reason": terms_reason,
            }
        )
        inventory_rows.append(
            {
                "release_id": release_id,
                "source_id": source.get("source_id", ""),
                "ticker": ticker,
                "staged_relative_path": source.get("relative_path", ""),
                "source_file_exists": info["exists"],
                "source_file_sha256": file_hash,
                "source_file_bytes": file_bytes,
                "raw_row_count": info["raw_row_count"],
                "canonical_valid_row_count": info["canonical_valid_row_count"],
                "selected_invalid_row_count": info["selected_invalid_row_count"],
                "first_raw_date": info["first_raw_date"],
                "last_raw_date": info["last_raw_date"],
                "first_canonical_date": info["first_canonical_date"],
                "last_canonical_date": info["last_canonical_date"],
            }
        )
        raw_cols = []
        if path.exists():
            raw_cols = list(normalize_headers(pd.read_csv(path, nrows=1)).columns)
        for col in ["session_date", "close"]:
            present = col in raw_cols
            schema_rows.append({"release_id": release_id, "source_id": source.get("source_id", ""), "ticker": ticker, "required_column": col, "column_present": present, "schema_status": "valid" if present else "data_quality_blocked", "schema_reason": "valid" if present else "missing_required_column"})
        if "adjusted_close" in raw_cols:
            schema_rows.append({"release_id": release_id, "source_id": source.get("source_id", ""), "ticker": ticker, "required_column": "adjusted_close", "column_present": True, "schema_status": "valid", "schema_reason": "retained_provenance_not_used_as_close"})
        credentials = has_secret_key(manifest)
        terms_rows.append({"release_id": release_id, "source_id": source.get("source_id", ""), "ticker": ticker, "terms_review_status": source.get("terms_review_status", ""), "allowed_usage_assertion": source.get("allowed_usage_assertion", ""), "raw_data_git_ignored": True, "credentials_present_in_manifest": credentials, "terms_gate_status": terms_status if not credentials else "data_quality_blocked", "terms_gate_reason": terms_reason if not credentials else "credentials_present_in_manifest"})
        assumed = int((df.get("availability_confidence", pd.Series(dtype=str)) == "medium").sum()) if not df.empty else 0
        explicit = int((df.get("availability_confidence", pd.Series(dtype=str)) == "high").sum()) if not df.empty else 0
        availability_rows.append({"release_id": release_id, "source_id": source.get("source_id", ""), "ticker": ticker, "availability_policy": source.get("historical_effective_availability_policy", ""), "row_effective_timestamp_field": source.get("row_effective_timestamp_field", ""), "policy_effective_timestamp_rows": assumed, "explicit_effective_timestamp_rows": explicit, "assumed_effective_timestamp_rows": assumed, "invalid_effective_timestamp_rows": info["selected_invalid_row_count"], "availability_confidence_summary": "high,medium" if assumed and explicit else "medium" if assumed else "high" if explicit else "", "availability_policy_status": "valid" if info["canonical_valid_row_count"] else "unavailable_coverage", "availability_policy_reason": info["availability_reason"]})
        valid_dates = set(df["session_date"].astype(str)) if not df.empty else set()
        timely_dates = {
            str(row["session_date"])
            for row in source_timeliness_rows
            if row.get("accepted_into_canonical_input") is True and row.get("source_row_timeliness_status") == "valid_timely"
        }
        range_dates = [d for d in cal_dates if info["first_canonical_date"] and info["first_canonical_date"] <= d <= (info["last_canonical_date"] or "9999-12-31")]
        missing = [d for d in range_dates if d not in valid_dates]
        latest_present = latest_session in valid_dates
        latest_timely_present = latest_session in timely_dates
        stale_count = 0 if latest_present else len([d for d in cal_dates if info["last_canonical_date"] and info["last_canonical_date"] < d <= latest_session])
        recent126 = recent_window_complete(valid_dates, cal_dates, latest_session, 126)
        recent252 = recent_window_complete(valid_dates, cal_dates, latest_session, 252)
        recent126_timely = recent_window_complete(timely_dates, cal_dates, latest_session, 126)
        recent252_timely = recent_window_complete(timely_dates, cal_dates, latest_session, 252)
        last_date = info["last_canonical_date"]
        source_recent252_timely = recent_window_complete(timely_dates, cal_dates, last_date, 252) if last_date else False
        late_count = int(info.get("late_effective_timestamp_row_count", 0))
        if not required and ticker in OPTIONAL_TICKERS and not info["canonical_valid_row_count"]:
            cov_status, cov_reason = "unavailable_coverage", "optional_source_unavailable"
        elif not info["canonical_valid_row_count"]:
            cov_status, cov_reason = "source_unavailable", "source_unavailable"
        elif info["first_canonical_date"] > minimum_start:
            cov_status, cov_reason = "insufficient_start_history", "insufficient_start_history"
        elif required and late_count:
            cov_status, cov_reason = "data_quality_blocked", "late_effective_timestamp_in_required_source"
        elif not latest_present and source_recent252_timely:
            cov_status, cov_reason = "valid_historical_but_stale", "stale_required_source_coverage"
        elif not recent252_timely:
            cov_status, cov_reason = "missing_recent_252_session_window", "missing_recent_252_session_window"
        elif not latest_present:
            cov_status, cov_reason = "valid_historical_but_stale", "stale_required_source_coverage"
        else:
            cov_status, cov_reason = "valid_current", "valid"
        timeliness_status = "valid" if cov_status in {"valid_current", "valid_historical_but_stale"} and not late_count else cov_status
        timeliness_reason = "valid" if timeliness_status == "valid" else cov_reason
        coverage_rows.append({"release_id": release_id, "source_id": source.get("source_id", ""), "ticker": ticker, "required_for_official_market_score": required, "optional_source": ticker in OPTIONAL_TICKERS, "minimum_required_start_date": minimum_start, "actual_first_valid_session_date": info["first_canonical_date"], "actual_last_valid_session_date": info["last_canonical_date"], "calendar_session_count_in_range": len(range_dates), "valid_source_session_count": len(valid_dates), "missing_source_session_count": len(missing), "missing_source_session_dates_hash": hashlib.sha256("\n".join(missing).encode()).hexdigest(), "recent_126_session_complete": recent126, "recent_252_session_complete": recent252, "latest_completed_session_timely_source_present": latest_timely_present, "recent_126_session_timely_complete": recent126_timely, "recent_252_session_timely_complete": recent252_timely, "late_effective_timestamp_row_count": late_count, "timeliness_coverage_status": timeliness_status, "timeliness_coverage_reason": timeliness_reason, "latest_completed_nyse_session": latest_session, "latest_completed_session_source_present": latest_present, "staleness_session_count": stale_count, "coverage_status": cov_status, "coverage_reason": cov_reason})

    cross_rows = cross_source_rows(root, release_id, sources, coverage_rows)
    cross_rows.append({"release_id": release_id, "audit_name": "calendar_policy_coverage", "scope": "release", "status": calendar_policy_status, "reason": calendar_policy_reason, "count": 0 if calendar_policy_valid else 1, "details": json.dumps({"calendar_first_session_date": calendar_min, "minimum_required_start_date": minimum_start})})
    write_csv(pd.DataFrame(attestations), rel / "source_attestations.csv", ATTESTATION_COLUMNS)
    write_csv(pd.DataFrame(inventory_rows), rel / "source_file_inventory.csv", INVENTORY_COLUMNS)
    write_csv(pd.DataFrame(schema_rows), rel / "source_schema_audit.csv", SCHEMA_COLUMNS)
    write_csv(pd.DataFrame(coverage_rows), rel / "source_coverage_audit.csv", COVERAGE_COLUMNS)
    write_csv(pd.DataFrame(availability_rows), rel / "source_availability_policy_audit.csv", AVAILABILITY_COLUMNS)
    write_csv(pd.DataFrame(timeliness_rows), rel / "source_timeliness_audit.csv", TIMELINESS_COLUMNS)
    write_csv(pd.DataFrame(terms_rows), rel / "source_terms_audit.csv", TERMS_COLUMNS)
    write_csv(pd.DataFrame(cross_rows), rel / "source_cross_source_audit.csv", CROSS_COLUMNS)

    required_last_dates = [str(r.get("actual_last_valid_session_date", "")) for r in coverage_rows if r.get("required_for_official_market_score") and r.get("actual_last_valid_session_date")]
    preflight_session = latest_session if required_last_dates and all(d >= latest_session for d in required_last_dates) else min(required_last_dates) if required_last_dates else latest_session
    scorer_out = rel / "preflight_fragility_outputs"
    if preflight_session:
        scorer.run(root, canonical_root, platform_write_path(scorer_out), as_of_date=preflight_session, strict=False)
    gate = build_quality_gate(release_id, pd.DataFrame(attestations), pd.DataFrame(schema_rows), pd.DataFrame(coverage_rows), pd.DataFrame(availability_rows), scorer_out, allow_stale, calendar_policy_status, calendar_policy_reason, preflight_session)
    write_csv(gate, rel / "release_quality_gate.csv", GATE_COLUMNS)
    metadata = release_core_metadata(root, staging_id, release_id, manifest, sources, gate, scorer_out, preflight_session)
    (rel / "release_core_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    content_manifest = write_content_manifest(rel, release_id)
    receipt = release_receipt(rel, release_id, content_manifest)
    receipt_path(rel).write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    rel.replace(final_rel)
    verify_release(root, release_id)
    return release_id


def cross_source_rows(root: Path, release_id: str, sources: list[dict[str, Any]], coverage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tickers = [str(s.get("ticker", "")).upper() for s in sources]
    source_ids = [str(s.get("source_id", "")) for s in sources]
    rows = []
    checks = [
        ("one_source_per_ticker", len(tickers) == len(set(tickers)), tickers),
        ("required_source_set_complete", all(t in tickers for t in REQUIRED_TICKERS), REQUIRED_TICKERS),
        ("no_duplicate_source_id", len(source_ids) == len(set(source_ids)), source_ids),
        ("no_duplicate_ticker_source", len(tickers) == len(set(tickers)), tickers),
        ("no_source_coalescing", len(tickers) == len(set(tickers)), tickers),
        ("cross_source_same_calendar_policy", True, "nyse_regular_sessions_v1"),
        ("VIX3M_required_for_official_score", "VIX3M" in tickers, "VIX3M"),
        ("VIX9D_optional", True, "optional"),
    ]
    for name, ok, details in checks:
        rows.append({"release_id": release_id, "audit_name": name, "scope": "release", "status": "valid" if ok else "data_quality_blocked", "reason": "valid" if ok else f"{name}_failed", "count": 0 if ok else 1, "details": json.dumps(details)})
    ignored = git_ignored(root, history_root(root) / "staging") and git_ignored(root, history_root(root) / "releases")
    rows.append({"release_id": release_id, "audit_name": "no_raw_data_git_tracking", "scope": "release", "status": "valid" if ignored else "unavailable_coverage", "reason": "git_ignore_verified" if ignored else "git_ignore_unavailable_or_not_ignored", "count": 0 if ignored else 1, "details": "staging/releases ignored"})
    return rows


def git_ignored(root: Path, path: Path) -> bool:
    candidates = [
        Path(r"C:\Users\keisu\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"),
        Path("git"),
    ]
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        rel = path
    for git_bin in candidates:
        try:
            cmd = [str(git_bin), "check-ignore", str(rel)]
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                return True
        except Exception:
            continue
    return False


def build_quality_gate(
    release_id: str,
    attest: pd.DataFrame,
    schema: pd.DataFrame,
    coverage: pd.DataFrame,
    availability: pd.DataFrame,
    scorer_out: Path,
    allow_stale: bool,
    calendar_policy_status: str,
    calendar_policy_reason: str,
    preflight_as_of_session: str,
) -> pd.DataFrame:
    rows = []
    latest_path = scorer_out / "fragility_score_latest_v0.csv"
    scorer_ok = False
    scorer_market_exact = False
    market_score_date = ""
    market_coverage = 0.0
    latest_completed = ""
    if not coverage.empty and "latest_completed_nyse_session" in coverage.columns:
        latest_values = coverage[coverage["ticker"].isin(REQUIRED_TICKERS)]["latest_completed_nyse_session"].dropna().astype(str)
        latest_completed = latest_values.iloc[0] if not latest_values.empty else ""
    if latest_path.exists():
        latest = pd.read_csv(latest_path)
        market = latest[latest["score_target"] == "MARKET"]
        if not market.empty:
            row = market.iloc[0]
            market_score_date = str(row.get("session_date", ""))
            market_coverage = float(row.get("data_coverage_pct", 0) or 0)
            scorer_ok = str(row.get("score_status")) == "valid"
            scorer_market_exact = scorer_ok and market_score_date == preflight_as_of_session and market_coverage == 100.0
    for ticker in sorted(set(attest["ticker"])):
        required = ticker in REQUIRED_TICKERS
        terms_status = "valid" if (attest[(attest["ticker"] == ticker)]["attestation_status"] == "valid").all() else "data_quality_blocked"
        schema_status = "valid" if (schema[(schema["ticker"] == ticker)]["schema_status"] == "valid").all() else "data_quality_blocked"
        cov = coverage[coverage["ticker"] == ticker]
        cov_status = str(cov.iloc[0]["coverage_status"]) if not cov.empty else "source_unavailable"
        timeliness_status = str(cov.iloc[0].get("timeliness_coverage_status", cov_status)) if not cov.empty else "source_unavailable"
        latest_timely = bool(cov.iloc[0].get("latest_completed_session_timely_source_present", False)) if not cov.empty else False
        recent252_timely = bool(cov.iloc[0].get("recent_252_session_timely_complete", False)) if not cov.empty else False
        availability_status = "valid" if not availability[availability["ticker"] == ticker].empty else "unavailable_coverage"
        hard_gate_valid = (
            (not required)
            or (
                terms_status == "valid"
                and schema_status == "valid"
                and calendar_policy_status == "valid"
                and availability_status == "valid"
                and timeliness_status == "valid"
                and scorer_market_exact
                and cov_status in {"valid_current", "valid_historical_but_stale"}
            )
        )
        freshness_valid = required and cov_status == "valid_current" and latest_timely and recent252_timely
        stale_only = bool(required and hard_gate_valid and not freshness_valid and cov_status == "valid_historical_but_stale")
        if not required:
            quality_status = "optional_reported"
            quality_reason = cov_status
        elif hard_gate_valid and freshness_valid:
            quality_status = "valid_current"
            quality_reason = "valid"
        elif stale_only:
            quality_status = "valid_historical_but_stale"
            quality_reason = "stale_required_source_coverage"
        else:
            quality_status = "data_quality_blocked"
            quality_reason = calendar_policy_reason if calendar_policy_status != "valid" else cov_status
        default_eligible = required and quality_status == "valid_current"
        stale_eligible = required and quality_status in {"valid_current", "valid_historical_but_stale"}
        rows.append({"release_id": release_id, "gate_scope": "source", "ticker": ticker, "required_for_official_market_score": required, "quality_gate_status": quality_status, "quality_gate_reason": quality_reason, "terms_gate_status": terms_status, "schema_gate_status": schema_status, "coverage_gate_status": cov_status, "calendar_policy_gate_status": calendar_policy_status, "timeliness_gate_status": timeliness_status if required else "optional_reported", "availability_gate_status": availability_status, "duplicate_gate_status": "valid", "scorer_preflight_status": "valid" if scorer_market_exact else "data_quality_blocked", "hard_gate_valid": hard_gate_valid, "freshness_valid": freshness_valid, "stale_only": stale_only, "promotion_eligible_default": default_eligible, "promotion_eligible_with_stale_override": stale_eligible, "promotion_eligible": default_eligible})
    required_rows = [r for r in rows if r["required_for_official_market_score"]]
    release_hard = bool(required_rows) and all(bool(r["hard_gate_valid"]) for r in required_rows)
    release_fresh = bool(required_rows) and all(bool(r["freshness_valid"]) for r in required_rows)
    release_stale_only = release_hard and not release_fresh and all(r["quality_gate_status"] in {"valid_current", "valid_historical_but_stale"} for r in required_rows)
    if release_hard and release_fresh:
        release_status = "valid_current"
        release_reason = "valid"
    elif release_stale_only:
        release_status = "valid_historical_but_stale"
        release_reason = "stale_required_source_coverage"
    else:
        release_status = "data_quality_blocked"
        release_reason = calendar_policy_reason if calendar_policy_status != "valid" else "one_or_more_required_gates_blocked"
    default_eligible = release_status == "valid_current"
    stale_eligible = release_status in {"valid_current", "valid_historical_but_stale"}
    rows.append({"release_id": release_id, "gate_scope": "release", "ticker": "MARKET", "required_for_official_market_score": True, "quality_gate_status": release_status, "quality_gate_reason": release_reason, "terms_gate_status": "valid" if all(r["terms_gate_status"] == "valid" for r in required_rows) else "data_quality_blocked", "schema_gate_status": "valid" if all(r["schema_gate_status"] == "valid" for r in required_rows) else "data_quality_blocked", "coverage_gate_status": "valid" if all(r["coverage_gate_status"] == "valid_current" for r in required_rows) else "valid_historical_but_stale" if release_stale_only else "data_quality_blocked", "calendar_policy_gate_status": calendar_policy_status, "timeliness_gate_status": "valid" if all(r["timeliness_gate_status"] == "valid" for r in required_rows) else "data_quality_blocked", "availability_gate_status": "valid" if all(r["availability_gate_status"] == "valid" for r in required_rows) else "data_quality_blocked", "duplicate_gate_status": "valid", "scorer_preflight_status": "valid" if scorer_market_exact else "data_quality_blocked", "hard_gate_valid": release_hard, "freshness_valid": release_fresh, "stale_only": release_stale_only, "promotion_eligible_default": default_eligible, "promotion_eligible_with_stale_override": stale_eligible, "promotion_eligible": default_eligible})
    return pd.DataFrame(rows, columns=GATE_COLUMNS)


def release_core_metadata(root: Path, staging_id: str, release_id: str, manifest: dict[str, Any], sources: list[dict[str, Any]], gate: pd.DataFrame, scorer_out: Path, latest_session: str) -> dict[str, Any]:
    score_manifest = scorer_out / "fragility_score_manifest_v0.json"
    release_row = gate[gate["gate_scope"] == "release"].iloc[0] if not gate.empty else {}
    return {
        "artifact_version": RELEASE_CORE_METADATA_VERSION,
        "release_id": release_id,
        "staging_id": staging_id,
        "built_at_utc": iso_utc(utc_now()),
        "source_bundle_sha256_at_build": compute_bundle_hash(root, staging_id, manifest),
        "source_file_hashes": {s.get("source_id", ""): file_sha256(staged_source_path(root, staging_id, s)) for s in sources if staged_source_path(root, staging_id, s).exists()},
        "release_quality_status": str(release_row.get("quality_gate_status", "data_quality_blocked")) if hasattr(release_row, "get") else "data_quality_blocked",
        "promotion_eligible_default": bool(release_row.get("promotion_eligible_default", False)) if hasattr(release_row, "get") else False,
        "promotion_eligible_with_stale_override": bool(release_row.get("promotion_eligible_with_stale_override", False)) if hasattr(release_row, "get") else False,
        "promotion_eligible": bool(release_row.get("promotion_eligible", False)) if hasattr(release_row, "get") else False,
        "preflight_as_of_session_date": latest_session,
        "score_manifest_sha256": file_sha256(score_manifest) if score_manifest.exists() else "",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def release_receipt(rel: Path, release_id: str, content_manifest: dict[str, Any]) -> dict[str, Any]:
    metadata_path = rel / "release_core_metadata.json"
    return {
        "artifact_version": ARTIFACT_VERSION,
        "release_id": release_id,
        "release_content_manifest_sha256": file_sha256(content_manifest_path(rel)),
        "release_core_content_set_sha256": content_manifest.get("core_content_set_sha256", ""),
        "release_core_metadata_sha256": file_sha256(metadata_path) if metadata_path.exists() else "",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def write_oos_summary(rel: Path, release_id: str) -> None:
    out = rel / "fragility_outputs"
    summary_path = out / "fragility_score_oos_summary_v0.csv"
    inv_path = rel / "source_file_inventory.csv"
    lines = [f"# Fragility Real-History OOS Release Summary", "", f"- Release ID: {release_id}", "- OOS mode: descriptive only", "- No fitted weights or actionization."]
    if inv_path.exists():
        inv = pd.read_csv(inv_path)
        lines += ["", "## Source Date Range"]
        for row in inv.to_dict("records"):
            lines.append(f"- {row['ticker']}: {row.get('first_canonical_date','')} to {row.get('last_canonical_date','')}")
    if summary_path.exists():
        summ = pd.read_csv(summary_path)
        lines += ["", "## OOS Evidence Status"]
        for row in summ.to_dict("records"):
            lines.append(f"- {row['score_target']}: {row['valid_oos_observation_count']} rows, {row['non_empty_fold_count']} folds, {row['evidence_status']}")
    lines += ["", "Caveat: descriptive OOS association only; results do not authorize actionization."]
    (rel / "fragility_real_history_oos_release_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_release(root: Path, release_id: str) -> dict[str, Any]:
    rel = release_dir(root, release_id)
    if rel.name != release_id:
        raise SystemExit("release directory id mismatch")
    r_path = receipt_path(rel)
    if not r_path.exists():
        raise SystemExit(f"missing release receipt: {release_id}")
    receipt = load_json(r_path)
    cm_path = content_manifest_path(rel)
    if not cm_path.exists():
        raise SystemExit("missing release content manifest")
    manifest_sha = file_sha256(cm_path)
    if receipt.get("release_content_manifest_sha256") != manifest_sha:
        raise SystemExit("release content manifest hash mismatch")
    manifest = load_json(cm_path)
    if manifest.get("release_id") != release_id or receipt.get("release_id") != release_id:
        raise SystemExit("release id mismatch in release wrapper or content manifest")
    validate_content_manifest(rel, manifest)
    if receipt.get("release_core_content_set_sha256") != manifest.get("core_content_set_sha256"):
        raise SystemExit("release receipt core content set hash mismatch")
    metadata_path = rel / "release_core_metadata.json"
    if not metadata_path.exists():
        raise SystemExit("missing release core metadata")
    metadata_sha = file_sha256(metadata_path)
    if receipt.get("release_core_metadata_sha256") != metadata_sha:
        raise SystemExit("release core metadata hash mismatch")
    metadata = load_json(metadata_path)
    if metadata.get("release_id") != release_id:
        raise SystemExit("release core metadata id mismatch")
    gate = pd.read_csv(rel / "release_quality_gate.csv")
    release_rows = gate[gate["gate_scope"] == "release"]
    if len(release_rows) != 1:
        raise SystemExit("release quality gate must have exactly one release row")
    release_row = release_rows.iloc[0]
    if str(release_row.get("quality_gate_status", "")) != str(metadata.get("release_quality_status", "")):
        raise SystemExit("release core metadata quality status mismatch")
    for col, key in [
        ("promotion_eligible_default", "promotion_eligible_default"),
        ("promotion_eligible_with_stale_override", "promotion_eligible_with_stale_override"),
        ("promotion_eligible", "promotion_eligible"),
    ]:
        if str(release_row.get(col, "")).lower() != str(metadata.get(key, "")).lower():
            raise SystemExit(f"release core metadata {key} mismatch")
    required_coverage = pd.read_csv(rel / "source_coverage_audit.csv")
    if required_coverage[required_coverage["ticker"].isin(REQUIRED_TICKERS)].groupby("ticker").size().to_dict().keys() != set(REQUIRED_TICKERS):
        raise SystemExit("required source coverage rows are not unique and complete")
    latest = pd.read_csv(rel / "preflight_fragility_outputs" / "fragility_score_latest_v0.csv")
    if len(latest[latest["score_target"] == "MARKET"]) != 1:
        raise SystemExit("preflight latest MARKET row is not unique")
    return {
        **metadata,
        "release_content_manifest_sha256": manifest_sha,
        "release_core_content_set_sha256": manifest.get("core_content_set_sha256", ""),
        "release_core_metadata_sha256": metadata_sha,
    }


def promote_release(root: Path, release_id: str, allow_stale: bool = False) -> None:
    rel = release_dir(root, release_id)
    receipt = verify_release(root, release_id)
    gate = pd.read_csv(rel / "release_quality_gate.csv")
    release_row = gate[gate["gate_scope"] == "release"].iloc[0]
    status = str(release_row["quality_gate_status"])
    default_ok = str(release_row.get("promotion_eligible_default", release_row.get("promotion_eligible", False))).lower() == "true"
    stale_ok = str(release_row.get("promotion_eligible_with_stale_override", default_ok)).lower() == "true"
    if allow_stale:
        if not stale_ok:
            raise SystemExit("release is not eligible even with stale override")
    elif not default_ok:
        raise SystemExit("release is not promotion eligible without --allow-stale")
    coverage = pd.read_csv(rel / "source_coverage_audit.csv")
    required = coverage[coverage["ticker"].isin(REQUIRED_TICKERS)]
    source_latest = str(required["actual_last_valid_session_date"].dropna().astype(str).min()) if not required.empty else ""
    staleness = int(pd.to_numeric(required["staleness_session_count"], errors="coerce").fillna(0).max()) if not required.empty else 0
    pointer = {
        "active_release_id": release_id,
        "promoted_at_utc": iso_utc(utc_now()),
        "promotion_command": "explicit_promote_release_v0_2_1",
        "release_quality_status": status,
        "stale_override_used": bool(allow_stale and status != "valid_current"),
        "promotion_as_of_latest_completed_nyse_session": str(required["latest_completed_nyse_session"].dropna().astype(str).iloc[0]) if not required.empty else "",
        "source_latest_session_date": source_latest,
        "staleness_session_count": staleness,
        "market_state_freshness_label": "current" if status == "valid_current" else "stale_historical_not_current",
        "release_content_manifest_sha256": receipt.get("release_content_manifest_sha256", ""),
        "release_receipt_sha256": file_sha256(rel / "release_receipt.json"),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    path = active_pointer_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pointer, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def release_preflight_session(rel: Path) -> str:
    metadata = load_json(rel / "release_core_metadata.json")
    return str(metadata.get("preflight_as_of_session_date", ""))


def release_source_latest_session(rel: Path) -> str:
    coverage = pd.read_csv(rel / "source_coverage_audit.csv")
    required = coverage[coverage["ticker"].isin(REQUIRED_TICKERS)].copy()
    if required.empty:
        return ""
    vals = required["actual_last_valid_session_date"].dropna().astype(str)
    return vals.min() if not vals.empty else ""


def resolve_verified_release_admission(root: Path, release_id: str, now_utc: str | None = None, allow_stale: bool = False, allow_blocked_inspection: bool = False) -> dict[str, Any]:
    metadata = verify_release(root, release_id)
    rel = release_dir(root, release_id)
    runtime_latest = latest_completed_session(root, parse_now_utc(now_utc) if now_utc else None)
    source_latest = release_source_latest_session(rel)
    quality = str(metadata.get("release_quality_status", "data_quality_blocked"))
    stale_at_runtime = bool(runtime_latest and source_latest and source_latest < runtime_latest)
    if quality == "data_quality_blocked":
        if not allow_blocked_inspection:
            raise SystemExit("release_data_quality_blocked")
        mode = "blocked_inspection_only"
        freshness = "blocked_inspection_not_current"
        warning = "DATA QUALITY BLOCKED - INSPECTION ONLY - NOT OFFICIAL MARKET STATE"
        official = False
    elif quality == "valid_current" and not stale_at_runtime:
        mode = "official_current"
        freshness = "current"
        warning = ""
        official = True
    else:
        if not allow_stale:
            raise SystemExit("release_stale_requires_allow_stale")
        mode = "stale_historical_override"
        freshness = "stale_historical_not_current"
        warning = "STALE HISTORICAL RELEASE - NOT CURRENT MARKET STATE"
        official = False
    return {
        "metadata": metadata,
        "execution_mode": mode,
        "official_market_state": official,
        "runtime_freshness_status": freshness,
        "admission_warning": warning,
        "admission_release_quality_status": quality,
        "admission_runtime_latest_completed_session": runtime_latest,
        "admission_source_latest_session": source_latest,
    }


def execution_id_for_release(receipt: dict[str, Any]) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    core = str(receipt.get("release_core_content_set_sha256", ""))[:12]
    nonce = bytes_sha256(os.urandom(16))[:8]
    return f"{stamp}_{core}_{nonce}"


def write_execution_summary(execution_dir: Path, release_id: str, freshness_label: str) -> None:
    out = execution_dir / "fragility_outputs"
    summary_path = out / "fragility_score_oos_summary_v0.csv"
    lines = []
    if freshness_label == "stale_historical_not_current":
        lines += ["# STALE HISTORICAL RELEASE - NOT CURRENT MARKET STATE", ""]
    elif freshness_label == "blocked_inspection_not_current":
        lines += ["# DATA QUALITY BLOCKED - INSPECTION ONLY - NOT OFFICIAL MARKET STATE", ""]
    else:
        lines += ["# Fragility Real-History OOS Execution Summary", ""]
    lines += [f"- Release ID: {release_id}", "- OOS mode: descriptive only", "- No fitted weights or actionization."]
    if platform_write_path(summary_path).exists():
        summ = pd.read_csv(platform_write_path(summary_path))
        lines += ["", "## OOS Evidence Status"]
        for row in summ.to_dict("records"):
            lines.append(f"- {row['score_target']}: {row['valid_oos_observation_count']} rows, {row['non_empty_fold_count']} folds, {row['evidence_status']}")
    lines += ["", "Caveat: descriptive OOS association only; results do not authorize actionization."]
    platform_write_path(execution_dir / "fragility_real_history_oos_release_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_execution(root: Path, release_id: str, execution_id: str) -> dict[str, Any]:
    release_meta = verify_release(root, release_id)
    rel = release_dir(root, release_id)
    execution_dir = rel / "executions" / execution_id
    try:
        execution_dir.resolve().relative_to(rel.resolve())
    except Exception as exc:
        raise SystemExit("execution directory escapes release") from exc
    manifest_path = execution_dir / "execution_content_manifest.json"
    receipt_file = execution_dir / "fragility_score_execution_receipt_v0.json"
    if not platform_write_path(manifest_path).exists() or not platform_write_path(receipt_file).exists():
        raise SystemExit("missing execution manifest or receipt")
    manifest = load_json(platform_write_path(manifest_path))
    receipt = load_json(platform_write_path(receipt_file))
    if manifest.get("artifact_version") != EXECUTION_CONTENT_MANIFEST_VERSION:
        raise SystemExit("unsupported execution manifest version")
    if manifest.get("release_id") != release_id or manifest.get("execution_id") != execution_id:
        raise SystemExit("execution manifest id mismatch")
    if receipt.get("release_id") != release_id or receipt.get("execution_id") != execution_id:
        raise SystemExit("execution receipt id mismatch")
    if receipt.get("release_content_manifest_sha256") != release_meta.get("release_content_manifest_sha256"):
        raise SystemExit("execution receipt release content manifest hash mismatch")
    if receipt.get("release_core_content_set_sha256") != release_meta.get("release_core_content_set_sha256"):
        raise SystemExit("execution receipt release core hash mismatch")
    if receipt.get("execution_content_manifest_sha256") != file_sha256(manifest_path):
        raise SystemExit("execution receipt manifest hash mismatch")
    seen: set[str] = set()
    recomputed = []
    for entry in manifest.get("entries", []):
        rel_path = str(entry.get("relative_path", ""))
        if not rel_path or rel_path.startswith("/") or rel_path.startswith("\\") or ".." in Path(rel_path).parts:
            raise SystemExit(f"unsafe execution manifest path: {rel_path}")
        if rel_path in seen:
            raise SystemExit(f"duplicate execution manifest path: {rel_path}")
        seen.add(rel_path)
        path = execution_dir / rel_path
        ppath = platform_write_path(path)
        if path.is_symlink() or not ppath.is_file():
            raise SystemExit(f"missing or unsafe execution file: {rel_path}")
        if int(entry.get("bytes", -1)) != ppath.stat().st_size:
            raise SystemExit(f"execution file size mismatch: {rel_path}")
        sha = file_sha256(ppath)
        if entry.get("sha256") != sha:
            raise SystemExit(f"execution file sha mismatch: {rel_path}")
        recomputed.append({"relative_path": rel_path, "sha256": sha, "bytes": ppath.stat().st_size, "category": "execution", "required": True})
    actual = {
        safe_relative_path(execution_dir, p)
        for p in platform_write_path(execution_dir).rglob("*")
        if p.is_file() and safe_relative_path(execution_dir, p) not in {"execution_content_manifest.json", "fragility_score_execution_receipt_v0.json"}
    }
    if actual != seen:
        raise SystemExit("execution file set does not match execution content manifest")
    if manifest.get("execution_content_set_sha256") != content_set_hash(recomputed):
        raise SystemExit("execution content set hash mismatch")
    mode = str(receipt.get("execution_mode", ""))
    official = bool(receipt.get("official_market_state", False))
    warning = str(receipt.get("admission_warning", ""))
    if mode == "official_current" and (not official or warning):
        raise SystemExit("official execution receipt admission fields are inconsistent")
    if mode in {"stale_historical_override", "blocked_inspection_only"} and (official or "NOT" not in warning):
        raise SystemExit("non-current execution receipt admission fields are inconsistent")
    return {"release_id": release_id, "execution_id": execution_id, "status": "valid", "execution_mode": mode, "official_market_state": official}


def run_score(root: Path, release_id: str, strict: bool = False, now_utc: str | None = None, allow_stale: bool = False, allow_blocked_inspection: bool = False, runtime_freshness_status: str | None = None) -> dict[str, Any]:
    rel = release_dir(root, release_id)
    admission = resolve_verified_release_admission(root, release_id, now_utc, allow_stale, allow_blocked_inspection)
    receipt = admission["metadata"]
    if runtime_freshness_status is None:
        runtime_freshness_status = admission["runtime_freshness_status"]
    latest = release_preflight_session(rel)
    execution_id = execution_id_for_release(receipt)
    execution_dir = rel / "executions" / execution_id
    execution_dir.mkdir(parents=True, exist_ok=False)
    output_dir = execution_dir / "fragility_outputs"
    output_dir.mkdir(parents=True, exist_ok=False)
    started = iso_utc(utc_now())
    scorer.run(root, rel / "canonical_input", platform_write_path(output_dir), as_of_date=latest, strict=strict)
    completed = iso_utc(utc_now())
    latest_df = pd.read_csv(platform_write_path(output_dir / "fragility_score_latest_v0.csv"))
    market = latest_df[latest_df["score_target"] == "MARKET"].iloc[0].to_dict() if not latest_df[latest_df["score_target"] == "MARKET"].empty else {}
    score_manifest = output_dir / "fragility_score_manifest_v0.json"
    write_execution_summary(execution_dir, release_id, runtime_freshness_status)
    execution_manifest = build_execution_content_manifest(execution_dir, release_id, execution_id)
    platform_write_path(execution_dir / "execution_content_manifest.json").write_text(json.dumps(execution_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    exec_receipt = {
        "release_id": release_id,
        "execution_id": execution_id,
        "release_content_manifest_sha256": receipt.get("release_content_manifest_sha256", ""),
        "release_core_content_set_sha256": receipt.get("release_core_content_set_sha256", ""),
        "run_started_at_utc": started,
        "run_completed_at_utc": completed,
        "requested_as_of_date": latest,
        "runtime_freshness_status": runtime_freshness_status,
        "execution_mode": admission["execution_mode"],
        "official_market_state": admission["official_market_state"],
        "admission_release_quality_status": admission["admission_release_quality_status"],
        "admission_runtime_latest_completed_session": admission["admission_runtime_latest_completed_session"],
        "admission_source_latest_session": admission["admission_source_latest_session"],
        "admission_warning": admission["admission_warning"],
        "release_quality_status": receipt.get("release_quality_status", ""),
        "scorer_artifact_version": scorer.ARTIFACT_VERSION,
        "score_manifest_sha256": file_sha256(platform_write_path(score_manifest)),
        "execution_content_manifest_sha256": file_sha256(platform_write_path(execution_dir / "execution_content_manifest.json")),
        "market_score_status": market.get("score_status", ""),
        "market_score_date": market.get("session_date", ""),
        "market_score_confidence": market.get("confidence", ""),
        "market_score_data_coverage_pct": market.get("data_coverage_pct", ""),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    platform_write_path(execution_dir / "fragility_score_execution_receipt_v0.json").write_text(json.dumps(exec_receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    verify_execution(root, release_id, execution_id)
    return exec_receipt


def run_active_score(root: Path, strict: bool = False, allow_stale: bool = False, now_utc: str | None = None, allow_blocked_inspection: bool = False) -> dict[str, Any]:
    path = active_pointer_path(root)
    if not path.exists():
        raise SystemExit("no active fragility release pointer")
    pointer = load_json(path)
    release_id = pointer.get("active_release_id", "")
    rel = release_dir(root, release_id)
    if not rel.exists():
        raise SystemExit("active release directory missing")
    expected = pointer.get("release_receipt_sha256", "")
    if expected and expected != file_sha256(rel / "release_receipt.json"):
        raise SystemExit("active release receipt hash mismatch")
    receipt = run_score(root, release_id, strict, now_utc=now_utc, allow_stale=allow_stale, allow_blocked_inspection=allow_blocked_inspection)
    freshness = receipt.get("runtime_freshness_status", "current")
    summary_dir = root / "market_bomb_fragility_v0"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary = {"warning": receipt.get("admission_warning", ""), "active_release": pointer, "last_run": receipt, "runtime_latest_completed_nyse_session": receipt.get("admission_runtime_latest_completed_session", "")}
    (summary_dir / "active_release_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return receipt


def verify_staging(root: Path, staging_id: str, now_utc: str | None = None) -> dict[str, Any]:
    manifest = load_staging_manifest(root, staging_id)
    sources = validate_source_set(manifest)
    validate_staging_source_paths(root, staging_id, sources)
    with tempfile.TemporaryDirectory(prefix="fragility_verify_staging_") as tmp:
        tmp_root = Path(tmp) / "repo"
        (tmp_root / "market_bomb_config").mkdir(parents=True)
        for name in [
            "nyse_regular_sessions_v1.csv",
            "fragility_score_v0_rules.json",
            "fragility_data_release_v0_policy.json",
            "fragility_data_release_v0_schema.json",
        ]:
            shutil.copyfile(root / "market_bomb_config" / name, tmp_root / "market_bomb_config" / name)
        (tmp_root / ".gitignore").write_text(
            "market_bomb_history/fragility_score_v0/staging/\n"
            "market_bomb_history/fragility_score_v0/releases/\n"
            "market_bomb_history/fragility_score_v0/active_release.json\n",
            encoding="utf-8",
        )
        target_stage = staging_dir(tmp_root, staging_id)
        target_stage.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging_dir(root, staging_id), target_stage, symlinks=True)
        now_text = now_utc or os.environ.get("FRAGILITY_RELEASE_NOW_UTC")
        release_id = build_release(tmp_root, staging_id, now_utc=now_text)
        rel = release_dir(tmp_root, release_id)
        gate = pd.read_csv(rel / "release_quality_gate.csv")
        row = gate[gate["gate_scope"] == "release"].iloc[0]
        metadata = load_json(rel / "release_core_metadata.json")
        status = str(row["quality_gate_status"])
        candidate_status = "valid_current_candidate" if status == "valid_current" else "valid_historical_but_stale_candidate" if status == "valid_historical_but_stale" else "data_quality_blocked"
        required = pd.read_csv(rel / "source_coverage_audit.csv")
        source_results = required[required["ticker"].isin(REQUIRED_TICKERS)][["ticker", "coverage_status", "timeliness_coverage_status", "actual_last_valid_session_date"]].to_dict("records")
        return {
            "staging_id": staging_id,
            "source_count": len(sources),
            "status": "valid" if status == "valid_current" else status,
            "as_of_now_utc": now_text or iso_utc(utc_now()),
            "latest_completed_nyse_session": source_results[0].get("actual_last_valid_session_date", "") if source_results else "",
            "candidate_preflight_as_of_session": metadata.get("preflight_as_of_session_date", ""),
            "candidate_quality_status": candidate_status,
            "candidate_quality_reason": str(row["quality_gate_reason"]),
            "hard_gate_valid": bool(row["hard_gate_valid"]),
            "freshness_valid": bool(row["freshness_valid"]),
            "stale_only": bool(row["stale_only"]),
            "promotion_eligible_default_preview": bool(row["promotion_eligible_default"]),
            "promotion_eligible_with_stale_override_preview": bool(row["promotion_eligible_with_stale_override"]),
            "required_source_results": source_results,
            "calendar_policy_status": str(row["calendar_policy_gate_status"]),
            "timeliness_status": str(row["timeliness_gate_status"]),
            "scorer_preflight_status": str(row["scorer_preflight_status"]),
        }


def verify_staging_against_release(root: Path, release_id: str, staging_id: str) -> dict[str, Any]:
    receipt = verify_release(root, release_id)
    manifest = load_staging_manifest(root, staging_id)
    current_hash = compute_bundle_hash(root, staging_id, manifest)
    expected_hash = receipt.get("source_bundle_sha256_at_build", "")
    return {
        "release_id": release_id,
        "staging_id": staging_id,
        "current_source_bundle_sha256": current_hash,
        "source_bundle_sha256_at_build": expected_hash,
        "matches_release_build_bundle": current_hash == expected_hash,
        "status": "valid" if current_hash == expected_hash else "source_bundle_differs_from_release_build",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["verify-staging", "build-release"]:
        p = sub.add_parser(name)
        p.add_argument("--staging-id", required=True)
        p.add_argument("--allow-stale", action="store_true")
        p.add_argument("--now-utc", default=None)
    p = sub.add_parser("verify-release")
    p.add_argument("--release-id", required=True)
    p = sub.add_parser("verify-staging-against-release")
    p.add_argument("--release-id", required=True)
    p.add_argument("--staging-id", required=True)
    p = sub.add_parser("promote-release")
    p.add_argument("--release-id", required=True)
    p.add_argument("--allow-stale", action="store_true")
    p = sub.add_parser("run-score")
    p.add_argument("--release-id", required=True)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--now-utc", default=None)
    p.add_argument("--allow-stale", action="store_true")
    p.add_argument("--allow-blocked-inspection", action="store_true")
    p = sub.add_parser("verify-execution")
    p.add_argument("--release-id", required=True)
    p.add_argument("--execution-id", required=True)
    p = sub.add_parser("run-active-score")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--allow-stale", action="store_true")
    p.add_argument("--allow-blocked-inspection", action="store_true")
    p.add_argument("--now-utc", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "verify-staging":
        print(json.dumps(verify_staging(root, args.staging_id, args.now_utc), indent=2))
    elif args.command == "build-release":
        release_id = build_release(root, args.staging_id, args.allow_stale, args.now_utc)
        print(release_id)
    elif args.command == "verify-release":
        print(json.dumps(verify_release(root, args.release_id), indent=2))
    elif args.command == "verify-staging-against-release":
        print(json.dumps(verify_staging_against_release(root, args.release_id, args.staging_id), indent=2))
    elif args.command == "promote-release":
        promote_release(root, args.release_id, args.allow_stale)
    elif args.command == "run-score":
        print(json.dumps(run_score(root, args.release_id, args.strict, args.now_utc, args.allow_stale, args.allow_blocked_inspection), indent=2, default=str))
    elif args.command == "verify-execution":
        print(json.dumps(verify_execution(root, args.release_id, args.execution_id), indent=2, default=str))
    elif args.command == "run-active-score":
        print(json.dumps(run_active_score(root, args.strict, args.allow_stale, args.now_utc, args.allow_blocked_inspection), indent=2, default=str))


if __name__ == "__main__":
    main()
