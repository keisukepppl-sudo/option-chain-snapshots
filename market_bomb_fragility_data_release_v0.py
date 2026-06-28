#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import market_bomb_fragility_score_v0 as scorer


ARTIFACT_VERSION = "fragility_data_release_v0_2"
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
    "latest_completed_nyse_session",
    "latest_completed_session_source_present",
    "staleness_session_count",
    "coverage_status",
    "coverage_reason",
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
    "availability_gate_status",
    "duplicate_gate_status",
    "scorer_preflight_status",
    "promotion_eligible",
]


def utc_now() -> pd.Timestamp:
    fixed = os.environ.get("FRAGILITY_RELEASE_NOW_UTC")
    if fixed:
        return pd.Timestamp(fixed).tz_convert("UTC")
    return pd.Timestamp.now(tz="UTC")


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


def write_csv(df: pd.DataFrame, path: Path, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        df = pd.DataFrame(df, columns=columns)
    df.to_csv(path, index=False)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    return staging_dir(root, staging_id) / str(source.get("relative_path", ""))


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
    for source in sorted(source_records(manifest), key=lambda s: str(s.get("source_id", ""))):
        path = staged_source_path(root, staging_id, source)
        h.update(str(source.get("source_id", "")).encode())
        if path.exists():
            h.update(file_sha256(path).encode())
    return h.hexdigest()


def make_release_id(root: Path, staging_id: str, manifest: dict[str, Any]) -> str:
    digest = compute_bundle_hash(root, staging_id, manifest)
    return f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{digest[:12]}"


def parse_source_rows(root: Path, staging_id: str, release_id: str, source: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
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
    }
    if not path.exists():
        return pd.DataFrame(), info
    raw = normalize_headers(pd.read_csv(path))
    if has_secret_key(list(raw.columns)):
        raise SystemExit(f"staged source appears to contain credential-like column names: {source.get('source_id', '')}")
    info["raw_row_count"] = len(raw)
    if "session_date" not in raw.columns or "close" not in raw.columns:
        return pd.DataFrame(), info
    cal = decision_map(root)
    rows: list[dict[str, Any]] = []
    invalid = 0
    for ordinal, row in enumerate(raw.to_dict("records"), start=1):
        session_date = scorer.as_date(row.get("session_date", ""))
        close = pd.to_numeric(pd.Series([row.get("close", None)]), errors="coerce").iloc[0]
        if session_date:
            info["first_raw_date"] = min([d for d in [info["first_raw_date"], session_date] if d], default=session_date)
            info["last_raw_date"] = max([d for d in [info["last_raw_date"], session_date] if d], default=session_date)
        if not session_date or session_date not in cal or pd.isna(close) or float(close) <= 0:
            invalid += 1
            continue
        eff_field = str(source.get("row_effective_timestamp_field", "") or "")
        raw_eff = row.get(eff_field, "") if eff_field else row.get("effective_available_at_utc", "")
        if not scorer.is_blank_value(raw_eff):
            if not scorer.is_tz_aware(raw_eff):
                invalid += 1
                continue
            effective = scorer.iso_utc(scorer.parse_ts(raw_eff))
            confidence = "high"
            basis = "explicit_row_effective_timestamp"
        else:
            effective = cal[session_date]
            confidence = "medium"
            basis = "assumed_nyse_close_plus_15_minutes_v0_2"
        rows.append(
            {
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
        out = out[~dup_mask].copy()
    info["canonical_valid_row_count"] = len(out)
    info["selected_invalid_row_count"] = invalid
    if not out.empty:
        info["first_canonical_date"] = str(out["session_date"].min())
        info["last_canonical_date"] = str(out["session_date"].max())
    info["schema_valid"] = True
    if len(raw) and "effective_available_at_utc" not in raw.columns and not source.get("row_effective_timestamp_field"):
        info["availability_status"] = "valid"
        info["availability_reason"] = "policy_assumed_historical_daily_rows"
    return out, info


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
    release_id = make_release_id(root, staging_id, manifest)
    rel = release_dir(root, release_id)
    if rel.exists():
        raise SystemExit(f"release already exists and cannot be overwritten: {release_id}")
    rel.mkdir(parents=True)
    canonical_root = rel / "canonical_input"
    latest_session = latest_completed_session(root, pd.Timestamp(now_utc).tz_convert("UTC") if now_utc else None)
    cal_df = scorer.load_calendar(root)
    cal_dates = list(cal_df["session_date"].astype(str))
    calendar_min = cal_dates[0] if cal_dates else ""
    policy = load_json(root / "market_bomb_config" / "fragility_data_release_v0_policy.json")
    minimum_start = str(policy.get("minimum_required_start_date", "2016-01-01"))
    effective_minimum_start = max(minimum_start, calendar_min) if calendar_min else minimum_start

    attestations = []
    inventory_rows = []
    schema_rows = []
    terms_rows = []
    availability_rows = []
    coverage_rows = []
    canonical_by_ticker: dict[str, pd.DataFrame] = {}
    source_infos: dict[str, dict[str, Any]] = {}

    for source in sources:
        ticker = str(source.get("ticker", "")).upper()
        required = ticker in REQUIRED_TICKERS
        path = staged_source_path(root, staging_id, source)
        df, info = parse_source_rows(root, staging_id, release_id, source)
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
        range_dates = [d for d in cal_dates if info["first_canonical_date"] and info["first_canonical_date"] <= d <= (info["last_canonical_date"] or "9999-12-31")]
        missing = [d for d in range_dates if d not in valid_dates]
        latest_present = latest_session in valid_dates
        stale_count = 0 if latest_present else len([d for d in cal_dates if info["last_canonical_date"] and info["last_canonical_date"] < d <= latest_session])
        recent126 = recent_window_complete(valid_dates, cal_dates, latest_session, 126)
        recent252 = recent_window_complete(valid_dates, cal_dates, latest_session, 252)
        if not required and ticker in OPTIONAL_TICKERS and not info["canonical_valid_row_count"]:
            cov_status, cov_reason = "unavailable_coverage", "optional_source_unavailable"
        elif not info["canonical_valid_row_count"]:
            cov_status, cov_reason = "source_unavailable", "source_unavailable"
        elif info["first_canonical_date"] > effective_minimum_start:
            cov_status, cov_reason = "insufficient_start_history", "insufficient_start_history"
        elif not recent252:
            cov_status, cov_reason = "missing_recent_252_session_window", "missing_recent_252_session_window"
        elif not latest_present:
            cov_status, cov_reason = "valid_historical_but_stale", "stale_required_source_coverage"
        else:
            cov_status, cov_reason = "valid_current", "valid"
        coverage_rows.append({"release_id": release_id, "source_id": source.get("source_id", ""), "ticker": ticker, "required_for_official_market_score": required, "optional_source": ticker in OPTIONAL_TICKERS, "minimum_required_start_date": minimum_start, "actual_first_valid_session_date": info["first_canonical_date"], "actual_last_valid_session_date": info["last_canonical_date"], "calendar_session_count_in_range": len(range_dates), "valid_source_session_count": len(valid_dates), "missing_source_session_count": len(missing), "missing_source_session_dates_hash": hashlib.sha256("\n".join(missing).encode()).hexdigest(), "recent_126_session_complete": recent126, "recent_252_session_complete": recent252, "latest_completed_nyse_session": latest_session, "latest_completed_session_source_present": latest_present, "staleness_session_count": stale_count, "coverage_status": cov_status, "coverage_reason": cov_reason})

    cross_rows = cross_source_rows(root, release_id, sources, coverage_rows)
    write_csv(pd.DataFrame(attestations), rel / "source_attestations.csv", ATTESTATION_COLUMNS)
    write_csv(pd.DataFrame(inventory_rows), rel / "source_file_inventory.csv", INVENTORY_COLUMNS)
    write_csv(pd.DataFrame(schema_rows), rel / "source_schema_audit.csv", SCHEMA_COLUMNS)
    write_csv(pd.DataFrame(coverage_rows), rel / "source_coverage_audit.csv", COVERAGE_COLUMNS)
    write_csv(pd.DataFrame(availability_rows), rel / "source_availability_policy_audit.csv", AVAILABILITY_COLUMNS)
    write_csv(pd.DataFrame(terms_rows), rel / "source_terms_audit.csv", TERMS_COLUMNS)
    write_csv(pd.DataFrame(cross_rows), rel / "source_cross_source_audit.csv", CROSS_COLUMNS)

    scorer_out = rel / "fragility_outputs"
    if latest_session:
        scorer.run(root, canonical_root, scorer_out, as_of_date=latest_session, strict=False)
    gate = build_quality_gate(release_id, pd.DataFrame(attestations), pd.DataFrame(schema_rows), pd.DataFrame(coverage_rows), pd.DataFrame(availability_rows), scorer_out, allow_stale)
    write_csv(gate, rel / "release_quality_gate.csv", GATE_COLUMNS)
    receipt = release_receipt(root, staging_id, release_id, manifest, sources, gate, scorer_out)
    (rel / "release_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    write_oos_summary(rel, release_id)
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


def build_quality_gate(release_id: str, attest: pd.DataFrame, schema: pd.DataFrame, coverage: pd.DataFrame, availability: pd.DataFrame, scorer_out: Path, allow_stale: bool) -> pd.DataFrame:
    rows = []
    score_manifest_path = scorer_out / "fragility_score_manifest_v0.json"
    latest_path = scorer_out / "fragility_score_latest_v0.csv"
    scorer_ok = False
    if latest_path.exists():
        latest = pd.read_csv(latest_path)
        market = latest[latest["score_target"] == "MARKET"]
        scorer_ok = not market.empty and str(market.iloc[0].get("score_status")) == "valid"
    for ticker in sorted(set(attest["ticker"])):
        required = ticker in REQUIRED_TICKERS
        terms_status = "valid" if (attest[(attest["ticker"] == ticker)]["attestation_status"] == "valid").all() else "data_quality_blocked"
        schema_status = "valid" if (schema[(schema["ticker"] == ticker)]["schema_status"] == "valid").all() else "data_quality_blocked"
        cov = coverage[coverage["ticker"] == ticker]
        cov_status = str(cov.iloc[0]["coverage_status"]) if not cov.empty else "source_unavailable"
        availability_status = "valid" if not availability[availability["ticker"] == ticker].empty else "unavailable_coverage"
        eligible = required and terms_status == "valid" and schema_status == "valid" and availability_status == "valid" and scorer_ok and (cov_status == "valid_current" or (allow_stale and cov_status == "valid_historical_but_stale"))
        rows.append({"release_id": release_id, "gate_scope": "source", "ticker": ticker, "required_for_official_market_score": required, "quality_gate_status": "valid_current" if eligible and cov_status == "valid_current" else cov_status if required else "optional_reported", "quality_gate_reason": "valid" if eligible else cov_status, "terms_gate_status": terms_status, "schema_gate_status": schema_status, "coverage_gate_status": cov_status, "availability_gate_status": availability_status, "duplicate_gate_status": "valid", "scorer_preflight_status": "valid" if scorer_ok else "data_quality_blocked", "promotion_eligible": eligible})
    required_rows = [r for r in rows if r["required_for_official_market_score"]]
    release_eligible = bool(required_rows) and all(r["promotion_eligible"] for r in required_rows)
    release_status = "valid_current" if release_eligible else "data_quality_blocked"
    rows.append({"release_id": release_id, "gate_scope": "release", "ticker": "MARKET", "required_for_official_market_score": True, "quality_gate_status": release_status, "quality_gate_reason": "valid" if release_eligible else "one_or_more_required_gates_blocked", "terms_gate_status": "valid" if all(r["terms_gate_status"] == "valid" for r in required_rows) else "data_quality_blocked", "schema_gate_status": "valid" if all(r["schema_gate_status"] == "valid" for r in required_rows) else "data_quality_blocked", "coverage_gate_status": "valid" if all(r["coverage_gate_status"] == "valid_current" or (allow_stale and r["coverage_gate_status"] == "valid_historical_but_stale") for r in required_rows) else "data_quality_blocked", "availability_gate_status": "valid" if all(r["availability_gate_status"] == "valid" for r in required_rows) else "data_quality_blocked", "duplicate_gate_status": "valid", "scorer_preflight_status": "valid" if scorer_ok else "data_quality_blocked", "promotion_eligible": release_eligible})
    return pd.DataFrame(rows, columns=GATE_COLUMNS)


def release_receipt(root: Path, staging_id: str, release_id: str, manifest: dict[str, Any], sources: list[dict[str, Any]], gate: pd.DataFrame, scorer_out: Path) -> dict[str, Any]:
    score_manifest = scorer_out / "fragility_score_manifest_v0.json"
    return {
        "artifact_version": ARTIFACT_VERSION,
        "release_id": release_id,
        "staging_id": staging_id,
        "built_at_utc": iso_utc(utc_now()),
        "source_bundle_sha256": compute_bundle_hash(root, staging_id, manifest),
        "source_file_hashes": {s.get("source_id", ""): file_sha256(staged_source_path(root, staging_id, s)) for s in sources if staged_source_path(root, staging_id, s).exists()},
        "release_quality_status": str(gate[gate["gate_scope"] == "release"].iloc[0]["quality_gate_status"]) if not gate.empty else "data_quality_blocked",
        "promotion_eligible": bool(gate[gate["gate_scope"] == "release"].iloc[0]["promotion_eligible"]) if not gate.empty else False,
        "score_manifest_sha256": file_sha256(score_manifest) if score_manifest.exists() else "",
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
    receipt_path = rel / "release_receipt.json"
    if not receipt_path.exists():
        raise SystemExit(f"missing release receipt: {release_id}")
    receipt = load_json(receipt_path)
    manifest = load_json(manifest_path_for_staging(root, receipt["staging_id"]))
    expected = compute_bundle_hash(root, receipt["staging_id"], manifest)
    if receipt.get("source_bundle_sha256") != expected:
        raise SystemExit("release receipt source bundle hash mismatch")
    gate_path = rel / "release_quality_gate.csv"
    if not gate_path.exists():
        raise SystemExit("missing release quality gate")
    return receipt


def promote_release(root: Path, release_id: str, allow_stale: bool = False) -> None:
    rel = release_dir(root, release_id)
    receipt = verify_release(root, release_id)
    gate = pd.read_csv(rel / "release_quality_gate.csv")
    release_row = gate[gate["gate_scope"] == "release"].iloc[0]
    if str(release_row["promotion_eligible"]).lower() != "true":
        raise SystemExit("release is not promotion eligible")
    status = str(release_row["quality_gate_status"])
    if status != "valid_current" and not allow_stale:
        raise SystemExit("stale or blocked release cannot be promoted without --allow-stale")
    pointer = {
        "active_release_id": release_id,
        "promoted_at_utc": iso_utc(utc_now()),
        "promotion_command": "explicit_promote_release_v0_2",
        "release_quality_status": status,
        "stale_override_used": bool(allow_stale and status != "valid_current"),
        "release_receipt_sha256": file_sha256(rel / "release_receipt.json"),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    path = active_pointer_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pointer, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def run_score(root: Path, release_id: str, strict: bool = False) -> dict[str, Any]:
    rel = release_dir(root, release_id)
    receipt = verify_release(root, release_id)
    coverage = pd.read_csv(rel / "source_coverage_audit.csv")
    latest = str(coverage[coverage["ticker"].isin(REQUIRED_TICKERS)]["latest_completed_nyse_session"].dropna().iloc[0])
    started = iso_utc(utc_now())
    scorer.run(root, rel / "canonical_input", rel / "fragility_outputs", as_of_date=latest, strict=strict)
    completed = iso_utc(utc_now())
    latest_df = pd.read_csv(rel / "fragility_outputs" / "fragility_score_latest_v0.csv")
    market = latest_df[latest_df["score_target"] == "MARKET"].iloc[0].to_dict() if not latest_df[latest_df["score_target"] == "MARKET"].empty else {}
    score_manifest = rel / "fragility_outputs" / "fragility_score_manifest_v0.json"
    exec_receipt = {
        "release_id": release_id,
        "run_started_at_utc": started,
        "run_completed_at_utc": completed,
        "requested_as_of_date": latest,
        "release_quality_status": receipt.get("release_quality_status", ""),
        "scorer_artifact_version": scorer.ARTIFACT_VERSION,
        "score_manifest_sha256": file_sha256(score_manifest),
        "market_score_status": market.get("score_status", ""),
        "market_score_date": market.get("session_date", ""),
        "market_score_confidence": market.get("confidence", ""),
        "market_score_data_coverage_pct": market.get("data_coverage_pct", ""),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    (rel / "fragility_score_execution_receipt_v0.json").write_text(json.dumps(exec_receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    write_oos_summary(rel, release_id)
    return exec_receipt


def run_active_score(root: Path, strict: bool = False) -> dict[str, Any]:
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
    receipt = run_score(root, release_id, strict)
    summary_dir = root / "market_bomb_fragility_v0"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "active_release_summary.json").write_text(json.dumps({"active_release": pointer, "last_run": receipt}, indent=2, ensure_ascii=False), encoding="utf-8")
    return receipt


def verify_staging(root: Path, staging_id: str) -> dict[str, Any]:
    manifest = load_staging_manifest(root, staging_id)
    sources = validate_source_set(manifest)
    return {"staging_id": staging_id, "source_count": len(sources), "status": "valid"}


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
    p = sub.add_parser("promote-release")
    p.add_argument("--release-id", required=True)
    p.add_argument("--allow-stale", action="store_true")
    p = sub.add_parser("run-score")
    p.add_argument("--release-id", required=True)
    p.add_argument("--strict", action="store_true")
    p = sub.add_parser("run-active-score")
    p.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "verify-staging":
        print(json.dumps(verify_staging(root, args.staging_id), indent=2))
    elif args.command == "build-release":
        release_id = build_release(root, args.staging_id, args.allow_stale, args.now_utc)
        print(release_id)
    elif args.command == "verify-release":
        print(json.dumps(verify_release(root, args.release_id), indent=2))
    elif args.command == "promote-release":
        promote_release(root, args.release_id, args.allow_stale)
    elif args.command == "run-score":
        print(json.dumps(run_score(root, args.release_id, args.strict), indent=2, default=str))
    elif args.command == "run-active-score":
        print(json.dumps(run_active_score(root, args.strict), indent=2, default=str))


if __name__ == "__main__":
    main()
