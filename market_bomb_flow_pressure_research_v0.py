#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import numpy as np
import pandas as pd


ARTIFACT_VERSION = "flow_pressure_research_v0_0_1"
RELEASE_CONTENT_MANIFEST_VERSION = "flow_pressure_release_content_manifest_v0_0_1"
RELEASE_CORE_METADATA_VERSION = "flow_pressure_release_core_metadata_v0_0_1"
BACKTEST_CONTENT_MANIFEST_VERSION = "flow_pressure_backtest_content_manifest_v0_0_1"
METHODOLOGY_VERSION = "flow_pressure_methodology_v0_0_1"
SOURCE_CONTRACT_VERSION = "flow_provider_contract_v1"
BACKTEST_SPEC_VERSION = "flow_pressure_backtest_spec_v0_0_2"
ACTIONIZATION_ALLOWED = False
SUPPORTED_MODULES = {"leveraged_etf_rebalance", "vol_control_deleveraging", "cta_trend_flow", "dealer_gamma_regime"}
IMPLEMENTED_MODULES = {"leveraged_etf_rebalance", "vol_control_deleveraging"}
TIMING_CLASSES = {"eod_next_session", "eod_after_close", "intraday_close_window", "historical_descriptive_only"}
CONTRACT_DATASET_TYPES = {
    "prices_daily",
    "prices_intraday",
    "leveraged_etf_reference",
    "leveraged_etf_aum",
    "vol_control_returns",
}
REQUIRED_SOURCE_FIELDS = [
    "source_id",
    "source_name",
    "source_file",
    "dataset_type",
    "source_as_of_timestamp",
    "available_at_timestamp",
    "market_timestamp",
    "instrument",
    "asset_class",
    "relative_path",
    "coverage_start_date",
    "coverage_end_date",
    "dataset_version",
    "timezone",
    "row_identifier_field",
    "content_sha256",
    "is_synthetic_fixture",
]

DATASET_REQUIRED_COLUMNS = {
    "prices_daily": [
        "source_row_id",
        "instrument",
        "asset_class",
        "market",
        "market_timestamp",
        "available_at_timestamp",
        "source_as_of_timestamp",
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "currency",
        "source_name",
        "source_file",
        "dataset_version",
    ],
    "prices_intraday": [
        "source_row_id",
        "instrument",
        "asset_class",
        "market",
        "bar_start_timestamp",
        "bar_end_timestamp",
        "available_at_timestamp",
        "source_as_of_timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "bar_interval_seconds",
        "currency",
        "source_name",
        "source_file",
        "dataset_version",
    ],
    "leveraged_etf_reference": [
        "source_row_id",
        "etf_instrument",
        "underlying_instrument",
        "target_leverage",
        "directionality",
        "asset_class",
        "market",
        "effective_start_timestamp",
        "effective_end_timestamp",
        "available_at_timestamp",
        "source_as_of_timestamp",
        "source_name",
        "source_file",
        "dataset_version",
    ],
    "leveraged_etf_aum": [
        "source_row_id",
        "etf_instrument",
        "as_of_timestamp",
        "available_at_timestamp",
        "source_as_of_timestamp",
        "aum_usd",
        "shares_outstanding",
        "nav_per_share",
        "currency",
        "publication_status",
        "valid_until_timestamp",
        "source_name",
        "source_file",
        "dataset_version",
    ],
    "vol_control_returns": [
        "source_row_id",
        "instrument",
        "asset_class",
        "market",
        "return_start_timestamp",
        "return_end_timestamp",
        "available_at_timestamp",
        "source_as_of_timestamp",
        "simple_return",
        "log_return",
        "price_basis",
        "source_name",
        "source_file",
        "dataset_version",
    ],
}


def utc_now() -> pd.Timestamp:
    fixed = os.environ.get("FLOW_PRESSURE_NOW_UTC")
    if fixed:
        return parse_utc_ts(fixed, "FLOW_PRESSURE_NOW_UTC")
    return pd.Timestamp.now(tz="UTC")


def parse_utc_ts(value: Any, label: str) -> pd.Timestamp:
    if value in [None, ""]:
        raise SystemExit(f"{label} is required")
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise SystemExit(f"{label} must be timezone-aware")
    return ts.tz_convert("UTC")


def iso_utc(ts: Any) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")


def parse_now_utc(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return parse_utc_ts(value, "--now-utc")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(df: pd.DataFrame, path: Path, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        df = pd.DataFrame(df, columns=columns)
    df.to_csv(path, index=False)


def platform_path(path: Path) -> Path:
    resolved = path.resolve()
    if os.name == "nt":
        text = str(resolved)
        if not text.startswith("\\\\?\\"):
            return Path("\\\\?\\" + text)
    return resolved


def history_root(root: Path) -> Path:
    return root / "market_bomb_history" / "flow_pressure_research_v0"


def staging_dir(root: Path, staging_id: str) -> Path:
    return history_root(root) / "staging" / staging_id


def releases_dir(root: Path) -> Path:
    return history_root(root) / "releases"


def release_dir(root: Path, release_id: str) -> Path:
    return releases_dir(root) / release_id


def receipt_path(rel: Path) -> Path:
    return rel / "release_receipt.json"


def content_manifest_path(rel: Path) -> Path:
    return rel / "release_content_manifest.json"


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
        raise SystemExit(f"unsafe manifest path: {text}")
    return text


def validate_source_relative_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        raise SystemExit("empty staged source relative_path")
    if text.startswith("/") or text.startswith("\\"):
        raise SystemExit(f"absolute staged source path is not allowed: {text}")
    if PureWindowsPath(str(value)).drive or str(value).startswith("\\\\"):
        raise SystemExit(f"windows drive or UNC staged source path is not allowed: {value}")
    parts = PurePosixPath(text).parts
    if ".." in parts:
        raise SystemExit(f"path traversal staged source path is not allowed: {text}")
    return text


def staged_source_path(root: Path, staging_id: str, source: dict[str, Any]) -> Path:
    rel = validate_source_relative_path(source.get("relative_path"))
    base = staging_dir(root, staging_id)
    path = base / rel
    try:
        path.resolve().relative_to(base.resolve())
    except Exception as exc:
        raise SystemExit(f"staged source path escapes staging root: {rel}") from exc
    return path


def load_staging_manifest(root: Path, staging_id: str) -> dict[str, Any]:
    path = staging_dir(root, staging_id) / "source_bundle_manifest.json"
    if not path.exists():
        raise SystemExit(f"missing source bundle manifest: {staging_id}")
    manifest = load_json(path)
    if str(manifest.get("staging_id", staging_id)) != staging_id:
        raise SystemExit("staging manifest id mismatch")
    return manifest


def policy(root: Path) -> dict[str, Any]:
    path = root / "market_bomb_config" / "flow_pressure_research_v0_policy.json"
    if path.exists():
        return load_json(path)
    return {
        "artifact_version": ARTIFACT_VERSION,
        "implemented_modules": sorted(IMPLEMENTED_MODULES),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "min_rows_per_implemented_module": 5,
        "max_source_staleness_days": 7,
        "vol_control_windows": [5, 10, 20],
        "vol_control_target_vols": [0.10, 0.12],
        "vol_control_max_exposure": 1.0,
        "vol_control_exposure_floor": 0.0,
        "backtest_forward_days": [1, 3, 5],
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "default_research_timing_class": "eod_next_session",
        "max_aum_observation_age_days": 3,
        "return_consistency_tolerance": 0.0005,
    }


def manifest_path(root: Path, staging_id: str) -> Path:
    return staging_dir(root, staging_id) / "source_bundle_manifest.json"


def source_bundle_manifest_sha256(root: Path, staging_id: str) -> str:
    return file_sha256(manifest_path(root, staging_id))


def parse_decision_time(value: str | None, now_utc: pd.Timestamp | None = None) -> pd.Timestamp:
    return parse_now_utc(value) or now_utc or utc_now()


def validate_timing_class(value: str | None, root: Path) -> str:
    timing = value or str(policy(root).get("default_research_timing_class", "eod_next_session"))
    if timing not in TIMING_CLASSES:
        raise SystemExit(f"unsupported research_timing_class: {timing}")
    return timing


def required_columns(dataset_type: str) -> list[str]:
    if dataset_type not in DATASET_REQUIRED_COLUMNS:
        raise SystemExit(f"unrecognized dataset_type: {dataset_type}")
    return DATASET_REQUIRED_COLUMNS[dataset_type]


def template_row_for(dataset_type: str, source_name: str, source_file: str) -> dict[str, Any]:
    base = {col: "" for col in required_columns(dataset_type)}
    base.update({"source_name": source_name, "source_file": source_file, "dataset_version": "synthetic_template_v1"})
    if "currency" in base:
        base["currency"] = "USD"
    if "market" in base:
        base["market"] = "US"
    if dataset_type == "leveraged_etf_reference":
        base.update({"directionality": "long", "target_leverage": "3.0"})
    if dataset_type == "prices_intraday":
        base["bar_interval_seconds"] = "60"
    return base


def build_flow_staging_template(root: Path, staging_id: str) -> dict[str, Any]:
    stage = staging_dir(root, staging_id)
    if stage.exists() and any(stage.iterdir()):
        raise SystemExit(f"staging directory is not empty: {stage}")
    (stage / "sources").mkdir(parents=True, exist_ok=True)
    dataset_files = {
        "prices_daily": "sources/prices_daily.csv",
        "prices_intraday": "sources/prices_intraday.csv",
        "leveraged_etf_reference": "sources/leveraged_etf_reference.csv",
        "leveraged_etf_aum": "sources/leveraged_etf_aum.csv",
        "vol_control_returns": "sources/vol_control_returns.csv",
    }
    sources = []
    for dataset_type, rel in dataset_files.items():
        source_name = "synthetic_template"
        df = pd.DataFrame([template_row_for(dataset_type, source_name, Path(rel).name)], columns=required_columns(dataset_type))
        # Header-only template with a documented contract; no provider values are included.
        df.iloc[0:0].to_csv(stage / rel, index=False)
        sources.append(
            {
                "source_id": dataset_type,
                "source_name": source_name,
                "source_file": rel,
                "relative_path": rel,
                "dataset_type": dataset_type,
                "dataset_version": "synthetic_template_v1",
                "coverage_start_date": "2000-01-01",
                "coverage_end_date": "2000-01-01",
                "timezone": "UTC",
                "row_identifier_field": "source_row_id",
                "content_sha256": file_sha256(stage / rel),
                "is_synthetic_fixture": True,
                "source_as_of_timestamp": "2000-01-01T00:00:00Z",
                "available_at_timestamp": "2000-01-01T00:00:00Z",
                "market_timestamp": "2000-01-01T00:00:00Z",
                "instrument": "",
                "asset_class": "template",
                "module": "leveraged_etf_rebalance" if dataset_type.startswith("leveraged") or dataset_type.startswith("prices") else "vol_control_deleveraging",
            }
        )
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "staging_id": staging_id,
        "research_timing_class": "eod_next_session",
        "decision_time_specification": {"type": "explicit_utc_timestamp", "example": "YYYY-MM-DDTHH:MM:SSZ"},
        "operator_attestation": {"personal_research_only": True},
        "sources": sources,
    }
    write_json(stage / "source_bundle_manifest.json", manifest)
    return {"staging_id": staging_id, "staging_path": str(stage), "source_contract_version": SOURCE_CONTRACT_VERSION, "template_files": list(dataset_files.values()), "actionization_allowed": ACTIONIZATION_ALLOWED}


def report_row(status: str, code: str, message: str, source_id: str = "", dataset_type: str = "", source_row_id: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "message": message,
        "source_id": source_id,
        "dataset_type": dataset_type,
        "source_row_id": source_row_id,
    }


def read_source_csv(path: Path, source: dict[str, Any]) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise SystemExit(f"cannot read source csv {source.get('relative_path')}: {exc}") from exc


def parse_row_timestamp(value: Any, label: str, rows: list[dict[str, Any]], source: dict[str, Any], source_row_id: str) -> pd.Timestamp | None:
    if value in [None, ""] or pd.isna(value):
        rows.append(report_row("blocked", f"missing_{label}", f"{label} is required", str(source.get("source_id", "")), str(source.get("dataset_type", "")), source_row_id))
        return None
    try:
        return parse_utc_ts(value, label)
    except SystemExit:
        rows.append(report_row("blocked", "unknown_timezone", f"{label} must be timezone-aware", str(source.get("source_id", "")), str(source.get("dataset_type", "")), source_row_id))
        return None


def finite_number(value: Any) -> float:
    try:
        if value in [None, ""] or pd.isna(value):
            return math.nan
        return float(value)
    except Exception:
        return math.nan


def validate_contract_rows(root: Path, staging_id: str, source: dict[str, Any], decision_time: pd.Timestamp, research_timing_class: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    dataset_type = str(source.get("dataset_type", ""))
    source_id = str(source.get("source_id", ""))
    diagnostics: list[dict[str, Any]] = []
    if dataset_type not in CONTRACT_DATASET_TYPES:
        diagnostics.append(report_row("blocked", "unrecognized_dataset_type", f"unrecognized dataset_type: {dataset_type}", source_id, dataset_type))
        return pd.DataFrame(), diagnostics
    if dataset_type in {"cta_trend_flow", "dealer_gamma_regime"} or str(source.get("module", "")) in {"cta_trend_flow", "dealer_gamma_regime"}:
        diagnostics.append(report_row("blocked", "methodology_incomplete", "CTA and Dealer inputs are out of scope in this phase", source_id, dataset_type))
        return pd.DataFrame(), diagnostics
    path = staged_source_path(root, staging_id, source)
    actual_hash = file_sha256(path)
    if str(source.get("content_sha256", "")).lower() != actual_hash.lower():
        diagnostics.append(report_row("blocked", "source_hash_mismatch", "manifest content_sha256 does not match staged file", source_id, dataset_type))
    df = read_source_csv(path, source)
    required = required_columns(dataset_type)
    missing = [c for c in required if c not in df.columns]
    if missing:
        diagnostics.append(report_row("blocked", "missing_required_columns", ",".join(missing), source_id, dataset_type))
        return pd.DataFrame(), diagnostics
    row_id_field = str(source.get("row_identifier_field", "source_row_id"))
    if row_id_field not in df.columns:
        diagnostics.append(report_row("blocked", "missing_row_identifier_field", f"missing {row_id_field}", source_id, dataset_type))
        return pd.DataFrame(), diagnostics
    if df[row_id_field].astype(str).duplicated().any():
        diagnostics.append(report_row("blocked", "duplicate_source_row_id", "duplicate row identifier in source file", source_id, dataset_type))
    if research_timing_class == "intraday_close_window" and dataset_type == "prices_daily":
        diagnostics.append(report_row("blocked", "daily_data_not_close_window_eligible", "daily rows cannot support intraday_close_window", source_id, dataset_type))
    out_rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        source_row_id = str(row.get(row_id_field, ""))
        available_at = parse_row_timestamp(row.get("available_at_timestamp"), "available_at_timestamp", diagnostics, source, source_row_id)
        source_as_of = parse_row_timestamp(row.get("source_as_of_timestamp"), "source_as_of_timestamp", diagnostics, source, source_row_id)
        if dataset_type == "prices_intraday":
            market_ts = parse_row_timestamp(row.get("bar_end_timestamp"), "bar_end_timestamp", diagnostics, source, source_row_id)
        elif dataset_type == "leveraged_etf_aum":
            market_ts = parse_row_timestamp(row.get("as_of_timestamp"), "as_of_timestamp", diagnostics, source, source_row_id)
        elif dataset_type == "leveraged_etf_reference":
            market_ts = parse_row_timestamp(row.get("effective_start_timestamp"), "effective_start_timestamp", diagnostics, source, source_row_id)
        elif dataset_type == "vol_control_returns":
            market_ts = parse_row_timestamp(row.get("return_end_timestamp"), "return_end_timestamp", diagnostics, source, source_row_id)
        else:
            market_ts = parse_row_timestamp(row.get("market_timestamp"), "market_timestamp", diagnostics, source, source_row_id)
        timing_status = "timing_eligible"
        timing_reason = "valid"
        if available_at is None or source_as_of is None or market_ts is None:
            timing_status = "blocked"
            timing_reason = "missing_or_invalid_timestamp"
        elif market_ts > available_at or source_as_of > available_at:
            timing_status = "blocked"
            timing_reason = "as_of_after_available_at"
            diagnostics.append(report_row("blocked", "as_of_after_available_at", "market/as-of timestamp is after availability timestamp", source_id, dataset_type, source_row_id))
        elif available_at > decision_time:
            timing_status = "timing_ineligible"
            timing_reason = "available_after_decision_time"
        if dataset_type == "leveraged_etf_aum":
            valid_until = parse_row_timestamp(row.get("valid_until_timestamp"), "valid_until_timestamp", diagnostics, source, source_row_id)
            if valid_until is None:
                timing_status = "timing_ineligible"
                timing_reason = "missing_validity_window"
            elif valid_until < decision_time:
                timing_status = "timing_ineligible"
                timing_reason = "stale_observation"
            aum = finite_number(row.get("aum_usd"))
            shares = finite_number(row.get("shares_outstanding"))
            nav = finite_number(row.get("nav_per_share"))
            if not np.isfinite(aum) and not (np.isfinite(shares) and np.isfinite(nav)):
                diagnostics.append(report_row("blocked", "missing_aum_or_shares_nav", "AUM row needs aum_usd or shares_outstanding and nav_per_share", source_id, dataset_type, source_row_id))
        if dataset_type == "leveraged_etf_reference":
            lev = finite_number(row.get("target_leverage"))
            if not np.isfinite(lev) or lev == 0:
                diagnostics.append(report_row("blocked", "invalid_target_leverage", "target_leverage must be finite and non-zero", source_id, dataset_type, source_row_id))
            if str(row.get("directionality", "")).lower() not in {"long", "inverse"}:
                diagnostics.append(report_row("blocked", "invalid_directionality", "directionality must be long or inverse", source_id, dataset_type, source_row_id))
        if dataset_type == "vol_control_returns":
            simple_return = finite_number(row.get("simple_return"))
            log_return = finite_number(row.get("log_return"))
            if not np.isfinite(simple_return) and not np.isfinite(log_return):
                diagnostics.append(report_row("blocked", "missing_return", "simple_return or log_return must be finite", source_id, dataset_type, source_row_id))
        if dataset_type == "prices_intraday":
            interval = finite_number(row.get("bar_interval_seconds"))
            if not np.isfinite(interval) or interval <= 0:
                diagnostics.append(report_row("blocked", "invalid_bar_interval", "bar_interval_seconds must be positive", source_id, dataset_type, source_row_id))
        out_rows.append(canonical_row_from_contract_row(source, row, decision_time, research_timing_class, timing_status, timing_reason, market_ts, available_at, source_as_of, actual_hash))
    canonical = pd.DataFrame(out_rows)
    duplicate_keys = {
        "prices_daily": ["dataset_type", "instrument", "market_timestamp", "source_name", "dataset_version"],
        "prices_intraday": ["dataset_type", "instrument", "bar_end_timestamp", "source_name", "dataset_version"],
        "leveraged_etf_reference": ["dataset_type", "etf_instrument", "effective_start_timestamp", "source_name", "dataset_version"],
        "leveraged_etf_aum": ["dataset_type", "etf_instrument", "as_of_timestamp", "source_name", "dataset_version"],
        "vol_control_returns": ["dataset_type", "instrument", "return_end_timestamp", "source_name", "dataset_version"],
    }[dataset_type]
    if not canonical.empty and canonical[duplicate_keys].astype(str).duplicated().any():
        diagnostics.append(report_row("blocked", "duplicate_canonical_key", "duplicate canonical key in source export", source_id, dataset_type))
    return canonical, diagnostics


def canonical_row_from_contract_row(source: dict[str, Any], row: pd.Series, decision_time: pd.Timestamp, research_timing_class: str, timing_status: str, timing_reason: str, market_ts: pd.Timestamp | None, available_at: pd.Timestamp | None, source_as_of: pd.Timestamp | None, source_hash: str) -> dict[str, Any]:
    dataset_type = str(source.get("dataset_type", ""))
    source_row_id = str(row.get(str(source.get("row_identifier_field", "source_row_id")), row.get("source_row_id", "")))
    record = {
        "observed_input": True,
        "canonical_input": True,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "source_id": source.get("source_id", ""),
        "source_row_id": source_row_id,
        "dataset_type": dataset_type,
        "source_name": row.get("source_name", source.get("source_name", "")),
        "source_file": row.get("source_file", source.get("source_file", "")),
        "relative_path": source.get("relative_path", ""),
        "dataset_version": row.get("dataset_version", source.get("dataset_version", "")),
        "decision_time": iso_utc(decision_time),
        "research_timing_class": research_timing_class,
        "timing_status": timing_status,
        "timing_reason": timing_reason,
        "market_timestamp": iso_utc(market_ts),
        "available_at": iso_utc(available_at),
        "source_as_of": iso_utc(source_as_of),
        "source_file_sha256": source_hash,
        "instrument": str(row.get("instrument", source.get("instrument", ""))).upper(),
        "asset_class": row.get("asset_class", source.get("asset_class", "")),
        "market": row.get("market", ""),
        "session_date": row.get("session_date", ""),
        "open": finite_number(row.get("open")),
        "high": finite_number(row.get("high")),
        "low": finite_number(row.get("low")),
        "close": finite_number(row.get("adjusted_close")) if np.isfinite(finite_number(row.get("adjusted_close"))) else finite_number(row.get("close")),
        "volume": finite_number(row.get("volume")),
        "bar_start_timestamp": iso_utc(pd.Timestamp(row.get("bar_start_timestamp")).tz_convert("UTC")) if dataset_type == "prices_intraday" and pd.notna(row.get("bar_start_timestamp")) else "",
        "bar_end_timestamp": iso_utc(market_ts) if dataset_type == "prices_intraday" else "",
        "bar_interval_seconds": finite_number(row.get("bar_interval_seconds")),
        "etf_instrument": str(row.get("etf_instrument", "")).upper(),
        "underlying_instrument": str(row.get("underlying_instrument", "")).upper(),
        "target_leverage": finite_number(row.get("target_leverage")),
        "directionality": str(row.get("directionality", "")).lower(),
        "effective_start_timestamp": iso_utc(market_ts) if dataset_type == "leveraged_etf_reference" else "",
        "effective_end_timestamp": row.get("effective_end_timestamp", ""),
        "as_of_timestamp": iso_utc(market_ts) if dataset_type == "leveraged_etf_aum" else "",
        "valid_until_timestamp": row.get("valid_until_timestamp", ""),
        "aum_usd": finite_number(row.get("aum_usd")),
        "shares_outstanding": finite_number(row.get("shares_outstanding")),
        "nav_per_share": finite_number(row.get("nav_per_share")),
        "return_start_timestamp": row.get("return_start_timestamp", ""),
        "return_end_timestamp": iso_utc(market_ts) if dataset_type == "vol_control_returns" else "",
        "simple_return": finite_number(row.get("simple_return")),
        "log_return": finite_number(row.get("log_return")),
        "price_basis": row.get("price_basis", ""),
    }
    if not np.isfinite(record["aum_usd"]) and np.isfinite(record["shares_outstanding"]) and np.isfinite(record["nav_per_share"]):
        record["aum_usd"] = record["shares_outstanding"] * record["nav_per_share"]
    record["row_hash"] = bytes_sha256(json.dumps(record, sort_keys=True, default=str).encode("utf-8"))
    return record


def validate_flow_provider_contract(root: Path, staging_id: str, decision_time_utc: str | None = None, research_timing_class: str | None = None) -> dict[str, Any]:
    decision_time = parse_decision_time(decision_time_utc)
    timing_class = validate_timing_class(research_timing_class, root)
    manifest = load_staging_manifest(root, staging_id)
    diagnostics: list[dict[str, Any]] = []
    sources = manifest.get("sources", [])
    if manifest.get("source_contract_version") != SOURCE_CONTRACT_VERSION:
        diagnostics.append(report_row("blocked", "source_contract_version_mismatch", f"expected {SOURCE_CONTRACT_VERSION}"))
    if not isinstance(sources, list) or not sources:
        diagnostics.append(report_row("blocked", "missing_sources", "manifest sources must be non-empty"))
    declared_paths = set()
    canonical_frames = []
    seen_source_ids = set()
    for source in sources if isinstance(sources, list) else []:
        for field in REQUIRED_SOURCE_FIELDS:
            if source.get(field) in [None, ""]:
                diagnostics.append(report_row("blocked", f"missing_{field}", f"missing required source field: {field}", str(source.get("source_id", "")), str(source.get("dataset_type", ""))))
        source_id = str(source.get("source_id", ""))
        source_available = parse_row_timestamp(source.get("available_at_timestamp"), "available_at_timestamp", diagnostics, source, "")
        source_as_of = parse_row_timestamp(source.get("source_as_of_timestamp"), "source_as_of_timestamp", diagnostics, source, "")
        source_market = parse_row_timestamp(source.get("market_timestamp"), "market_timestamp", diagnostics, source, "")
        if source_available is not None and source_available > decision_time:
            diagnostics.append(report_row("blocked", "available_after_decision_time", "manifest available_at_timestamp is after decision_time", source_id, str(source.get("dataset_type", ""))))
        if source_available is not None and source_as_of is not None and source_as_of > source_available:
            diagnostics.append(report_row("blocked", "as_of_after_available_at", "manifest source_as_of_timestamp is after available_at_timestamp", source_id, str(source.get("dataset_type", ""))))
        if source_available is not None and source_market is not None and source_market > source_available:
            diagnostics.append(report_row("blocked", "as_of_after_available_at", "manifest market_timestamp is after available_at_timestamp", source_id, str(source.get("dataset_type", ""))))
        if source_id in seen_source_ids:
            diagnostics.append(report_row("blocked", "duplicate_source_id", f"duplicate source_id: {source_id}", source_id, str(source.get("dataset_type", ""))))
        seen_source_ids.add(source_id)
        try:
            rel = validate_source_relative_path(source.get("relative_path"))
            if rel in declared_paths:
                diagnostics.append(report_row("blocked", "duplicate_relative_path", f"duplicate relative_path: {rel}", source_id, str(source.get("dataset_type", ""))))
            declared_paths.add(rel)
            source_path = staged_source_path(root, staging_id, source)
            if source_path.is_symlink():
                diagnostics.append(report_row("blocked", "symlink_source", "symlink staged source is not allowed", source_id, str(source.get("dataset_type", ""))))
                continue
            if not source_path.exists():
                diagnostics.append(report_row("blocked", "missing_declared_file", f"declared file is absent: {rel}", source_id, str(source.get("dataset_type", ""))))
                continue
            canonical, row_diags = validate_contract_rows(root, staging_id, source, decision_time, timing_class)
            canonical_frames.append(canonical)
            diagnostics.extend(row_diags)
        except SystemExit as exc:
            diagnostics.append(report_row("blocked", "path_or_source_validation_failed", str(exc), source_id, str(source.get("dataset_type", ""))))
    source_dir = staging_dir(root, staging_id) / "sources"
    if source_dir.exists():
        for file in source_dir.rglob("*"):
            if file.is_file():
                rel = safe_relative_path(staging_dir(root, staging_id), file)
                if rel not in declared_paths:
                    diagnostics.append(report_row("blocked", "undeclared_source_file", f"source file is not declared in manifest: {rel}"))
    non_empty_frames = [f for f in canonical_frames if f is not None and not f.empty]
    canonical_all = pd.concat(non_empty_frames, ignore_index=True) if non_empty_frames else pd.DataFrame()
    if not canonical_all.empty:
        diagnostics.extend(cross_file_contract_diagnostics(canonical_all, timing_class, decision_time, root))
    blocked_count = sum(1 for row in diagnostics if row["status"] == "blocked")
    timing_ineligible_count = int((canonical_all.get("timing_status", pd.Series(dtype=str)) == "timing_ineligible").sum()) if not canonical_all.empty else 0
    status = "valid" if blocked_count == 0 else "blocked"
    return {
        "artifact_version": ARTIFACT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "staging_id": staging_id,
        "research_timing_class": timing_class,
        "decision_time": iso_utc(decision_time),
        "validation_status": status,
        "blocked_count": blocked_count,
        "timing_ineligible_count": timing_ineligible_count,
        "canonical_row_count": len(canonical_all),
        "source_bundle_manifest_sha256": source_bundle_manifest_sha256(root, staging_id) if manifest_path(root, staging_id).exists() else "",
        "diagnostics": diagnostics,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def cross_file_contract_diagnostics(canonical: pd.DataFrame, timing_class: str, decision_time: pd.Timestamp, root: Path) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    refs = canonical[canonical["dataset_type"] == "leveraged_etf_reference"].copy()
    if not refs.empty:
        refs["start"] = pd.to_datetime(refs["effective_start_timestamp"], utc=True, errors="coerce")
        refs["end"] = pd.to_datetime(refs["effective_end_timestamp"], utc=True, errors="coerce")
        for etf, group in refs.groupby("etf_instrument"):
            ordered = group.sort_values("start")
            prev_end = None
            for _, row in ordered.iterrows():
                start = row["start"]
                end = row["end"]
                if prev_end is not None and pd.notna(start) and pd.notna(prev_end) and start <= prev_end:
                    diagnostics.append(report_row("blocked", "overlapping_reference_mapping", "overlapping ETF reference mappings", str(row.get("source_id", "")), "leveraged_etf_reference", str(row.get("source_row_id", ""))))
                prev_end = end
    returns = canonical[canonical["dataset_type"] == "vol_control_returns"].copy()
    if not returns.empty:
        basis = returns.groupby("instrument")["price_basis"].nunique(dropna=True)
        for instrument, count in basis.items():
            if count > 1:
                diagnostics.append(report_row("blocked", "mixed_price_basis", "only one explicit price_basis is permitted per return series", "", "vol_control_returns", str(instrument)))
    if timing_class == "intraday_close_window":
        intraday = canonical[(canonical["dataset_type"] == "prices_intraday") & (canonical["timing_status"] == "timing_eligible")]
        if intraday.empty:
            diagnostics.append(report_row("blocked", "missing_intraday_close_window_data", "intraday_close_window requires timing-eligible intraday rows"))
    return diagnostics


def canonical_contract_input(root: Path, staging_id: str, decision_time_utc: str | None, research_timing_class: str | None) -> tuple[dict[str, Any], list[dict[str, Any]], pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    decision_time = parse_decision_time(decision_time_utc)
    timing_class = validate_timing_class(research_timing_class, root)
    validation = validate_flow_provider_contract(root, staging_id, iso_utc(decision_time), timing_class)
    if validation["validation_status"] != "valid":
        raise SystemExit(f"flow provider contract blocked: {validation['blocked_count']} blocking diagnostics")
    manifest = load_staging_manifest(root, staging_id)
    sources = manifest.get("sources", [])
    frames = []
    diagnostics = []
    for source in sources:
        canonical, row_diags = validate_contract_rows(root, staging_id, source, decision_time, timing_class)
        frames.append(canonical)
        diagnostics.extend(row_diags)
    canonical = pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True) if frames else pd.DataFrame()
    timing_audit = timing_audit_frame(canonical, decision_time, timing_class, root)
    return manifest, sources, canonical, timing_audit, validation


def timing_audit_frame(canonical: pd.DataFrame, decision_time: pd.Timestamp, research_timing_class: str, root: Path) -> pd.DataFrame:
    rows = []
    if canonical.empty:
        return pd.DataFrame(columns=["source_id", "source_row_id", "dataset_type", "instrument", "decision_time", "research_timing_class", "timing_status", "timing_reason"])
    for _, row in canonical.iterrows():
        reason = row.get("timing_reason", "valid")
        status = row.get("timing_status", "timing_eligible")
        if row.get("dataset_type") == "leveraged_etf_aum" and status == "timing_eligible":
            valid_until = pd.to_datetime(row.get("valid_until_timestamp"), utc=True, errors="coerce")
            available_at = pd.to_datetime(row.get("available_at"), utc=True, errors="coerce")
            if pd.isna(valid_until):
                status, reason = "timing_ineligible", "missing_validity_window"
            elif valid_until < decision_time:
                status, reason = "timing_ineligible", "stale_observation"
            max_age = float(policy(root).get("max_aum_observation_age_days", 3))
            if pd.notna(available_at) and (decision_time - available_at).total_seconds() / 86400 > max_age:
                status, reason = "timing_ineligible", "stale_observation"
        rows.append(
            {
                "source_id": row.get("source_id", ""),
                "source_row_id": row.get("source_row_id", ""),
                "dataset_type": row.get("dataset_type", ""),
                "instrument": row.get("instrument") or row.get("etf_instrument", ""),
                "decision_time": iso_utc(decision_time),
                "research_timing_class": research_timing_class,
                "timing_status": status,
                "timing_reason": reason,
                "available_at": row.get("available_at", ""),
                "market_timestamp": row.get("market_timestamp", ""),
                "source_as_of": row.get("source_as_of", ""),
            }
        )
    return pd.DataFrame(rows)


def audit_flow_timing(root: Path, staging_id: str, decision_time_utc: str | None, research_timing_class: str | None) -> dict[str, Any]:
    decision_time = parse_decision_time(decision_time_utc)
    timing_class = validate_timing_class(research_timing_class, root)
    manifest = load_staging_manifest(root, staging_id)
    frames = []
    diagnostics = []
    for source in manifest.get("sources", []):
        try:
            canonical, row_diags = validate_contract_rows(root, staging_id, source, decision_time, timing_class)
            frames.append(canonical)
            diagnostics.extend(row_diags)
        except SystemExit as exc:
            diagnostics.append(report_row("blocked", "timing_audit_source_blocked", str(exc), str(source.get("source_id", "")), str(source.get("dataset_type", ""))))
    canonical = pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True) if frames else pd.DataFrame()
    audit = timing_audit_frame(canonical, decision_time, timing_class, root)
    return {
        "artifact_version": ARTIFACT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "staging_id": staging_id,
        "decision_time": iso_utc(decision_time),
        "research_timing_class": timing_class,
        "row_count": len(audit),
        "timing_eligible_count": int((audit.get("timing_status", pd.Series(dtype=str)) == "timing_eligible").sum()) if not audit.empty else 0,
        "timing_ineligible_count": int((audit.get("timing_status", pd.Series(dtype=str)) == "timing_ineligible").sum()) if not audit.empty else 0,
        "blocked_count": int((audit.get("timing_status", pd.Series(dtype=str)) == "blocked").sum()) if not audit.empty else 0,
        "diagnostics": diagnostics,
        "timing_audit": audit.to_dict("records"),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def inspect_flow_source_coverage(root: Path, staging_id: str, decision_time_utc: str | None = None, research_timing_class: str | None = None) -> dict[str, Any]:
    decision_time = parse_decision_time(decision_time_utc)
    timing_class = validate_timing_class(research_timing_class, root)
    manifest = load_staging_manifest(root, staging_id)
    frames = []
    for source in manifest.get("sources", []):
        try:
            canonical, _ = validate_contract_rows(root, staging_id, source, decision_time, timing_class)
            frames.append(canonical)
        except SystemExit:
            continue
    canonical = pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True) if frames else pd.DataFrame()
    if canonical.empty:
        coverage = pd.DataFrame(columns=["dataset_type", "instrument", "observed_rows", "timing_eligible_rows", "excluded_rows", "first_market_timestamp", "last_market_timestamp"])
    else:
        work = canonical.copy()
        work["coverage_instrument"] = work["instrument"].where(work["instrument"].astype(str) != "", work["etf_instrument"])
        coverage = (
            work.groupby(["dataset_type", "coverage_instrument"], dropna=False)
            .agg(
                observed_rows=("source_row_id", "count"),
                timing_eligible_rows=("timing_status", lambda s: int((s == "timing_eligible").sum())),
                excluded_rows=("timing_status", lambda s: int((s != "timing_eligible").sum())),
                first_market_timestamp=("market_timestamp", "min"),
                last_market_timestamp=("market_timestamp", "max"),
            )
            .reset_index()
            .rename(columns={"coverage_instrument": "instrument"})
        )
    return {
        "artifact_version": ARTIFACT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "staging_id": staging_id,
        "decision_time": iso_utc(decision_time),
        "research_timing_class": timing_class,
        "coverage": coverage.to_dict("records"),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def validate_manifest_and_sources(root: Path, staging_id: str, now_utc: pd.Timestamp | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = load_staging_manifest(root, staging_id)
    sources = manifest.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise SystemExit("staging manifest must include non-empty sources")
    now = now_utc or utc_now()
    seen_paths: set[str] = set()
    seen_source_ids: set[str] = set()
    audit_rows: list[dict[str, Any]] = []
    for source in sources:
        for field in REQUIRED_SOURCE_FIELDS:
            if source.get(field) in [None, ""]:
                raise SystemExit(f"missing required source field: {field}")
        module = str(source.get("module", "") or source.get("feature_module", ""))
        if module and module not in SUPPORTED_MODULES:
            raise SystemExit(f"unsupported source module: {module}")
        source_id = str(source.get("source_id"))
        if source_id in seen_source_ids:
            raise SystemExit(f"duplicate source_id: {source_id}")
        seen_source_ids.add(source_id)
        rel = validate_source_relative_path(source.get("relative_path"))
        if rel in seen_paths:
            raise SystemExit(f"duplicate staged source path: {rel}")
        seen_paths.add(rel)
        source_path = staged_source_path(root, staging_id, source)
        if source_path.is_symlink():
            raise SystemExit(f"symlink staged source is not allowed: {rel}")
        exists = source_path.exists() and source_path.is_file()
        if not exists:
            raise SystemExit(f"missing staged source file: {rel}")
        source_as_of = parse_utc_ts(source.get("source_as_of_timestamp"), "source_as_of_timestamp")
        available_at = parse_utc_ts(source.get("available_at_timestamp"), "available_at_timestamp")
        market_ts = parse_utc_ts(source.get("market_timestamp"), "market_timestamp")
        if market_ts > available_at:
            raise SystemExit("market_timestamp cannot be after available_at_timestamp")
        if source_as_of > available_at:
            raise SystemExit("source_as_of_timestamp cannot be after available_at_timestamp")
        if available_at > now:
            raise SystemExit("available_at_timestamp cannot be in the future relative to decision time")
        audit_rows.append(
            {
                "source_id": source_id,
                "source_name": source.get("source_name", ""),
                "source_file": source.get("source_file", ""),
                "relative_path": rel,
                "instrument": str(source.get("instrument", "")).upper(),
                "asset_class": source.get("asset_class", ""),
                "module": module,
                "source_as_of": iso_utc(source_as_of),
                "available_at": iso_utc(available_at),
                "market_timestamp": iso_utc(market_ts),
                "dataset_version": source.get("dataset_version", ""),
                "source_file_sha256": file_sha256(source_path),
                "source_file_bytes": source_path.stat().st_size,
                "source_path_valid": True,
            }
        )
    return manifest, sources, audit_rows


def normalize_source_frame(path: Path, source: dict[str, Any]) -> pd.DataFrame:
    df = pd.read_csv(path)
    lower = {str(c).lower(): c for c in df.columns}
    date_col = lower.get("date") or lower.get("session_date") or lower.get("coverage_date")
    close_col = lower.get("close") or lower.get("adjusted_close") or lower.get("nav")
    aum_col = lower.get("aum") or lower.get("assets") or lower.get("net_assets")
    shares_col = lower.get("shares_outstanding")
    nav_col = lower.get("nav")
    if date_col is None:
        raise SystemExit(f"source missing date/session_date column: {source.get('source_id')}")
    out = pd.DataFrame()
    out["session_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    out["instrument"] = str(source.get("instrument", "")).upper()
    out["source_id"] = source.get("source_id", "")
    out["module"] = source.get("module", source.get("feature_module", ""))
    out["close"] = pd.to_numeric(df[close_col], errors="coerce") if close_col else np.nan
    out["aum"] = pd.to_numeric(df[aum_col], errors="coerce") if aum_col else np.nan
    out["shares_outstanding"] = pd.to_numeric(df[shares_col], errors="coerce") if shares_col else np.nan
    out["nav"] = pd.to_numeric(df[nav_col], errors="coerce") if nav_col else out["close"]
    if out["aum"].isna().all() and not out["shares_outstanding"].isna().all():
        out["aum"] = out["shares_outstanding"] * out["nav"]
    out["source_as_of"] = iso_utc(parse_utc_ts(source.get("source_as_of_timestamp"), "source_as_of_timestamp"))
    out["available_at"] = iso_utc(parse_utc_ts(source.get("available_at_timestamp"), "available_at_timestamp"))
    out["market_timestamp"] = iso_utc(parse_utc_ts(source.get("market_timestamp"), "market_timestamp"))
    out["dataset_version"] = source.get("dataset_version", "")
    out["row_hash"] = [
        bytes_sha256("|".join(str(v) for v in row).encode("utf-8"))
        for row in out[["session_date", "instrument", "close", "aum", "available_at"]].fillna("").to_numpy()
    ]
    return out.dropna(subset=["session_date"]).sort_values(["instrument", "session_date"]).reset_index(drop=True)


def source_inventory(root: Path, staging_id: str, sources: list[dict[str, Any]]) -> pd.DataFrame:
    frames = []
    for source in sources:
        path = staged_source_path(root, staging_id, source)
        df = normalize_source_frame(path, source)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_leveraged_universe(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("leveraged_etf_universe"):
        return list(manifest["leveraged_etf_universe"])
    cfg = root / "market_bomb_config" / "flow_pressure_research_v0_policy.json"
    p = policy(root)
    if p.get("leveraged_etf_universe"):
        return list(p["leveraged_etf_universe"])
    existing = root / "market_bomb_config" / "leveraged_etf_universe_v1.json"
    rows: list[dict[str, Any]] = []
    if existing.exists():
        data = load_json(existing)
        for items in data.values():
            if isinstance(items, list):
                rows.extend(items)
    return rows


def build_leveraged_etf_features(root: Path, manifest: dict[str, Any], canonical: pd.DataFrame) -> pd.DataFrame:
    rows = []
    universe = load_leveraged_universe(root, manifest)
    by_ticker = {ticker: g.sort_values("session_date").copy() for ticker, g in canonical.groupby("instrument")}
    for item in universe:
        etf = str(item.get("ticker", "")).upper()
        target = str(item.get("target") or item.get("underlying", "")).upper()
        leverage = float(item.get("leverage", np.nan))
        if etf not in by_ticker or target not in by_ticker or not np.isfinite(leverage):
            continue
        e = by_ticker[etf].copy()
        u = by_ticker[target].copy()
        e["etf_return_1d"] = pd.to_numeric(e["close"], errors="coerce").pct_change()
        e["prior_aum"] = pd.to_numeric(e["aum"], errors="coerce").shift(1)
        u["underlying_return_1d"] = pd.to_numeric(u["close"], errors="coerce").pct_change()
        merged = e.merge(u[["session_date", "close", "underlying_return_1d"]], on="session_date", how="left", suffixes=("", "_underlying"))
        for _, row in merged.iterrows():
            prior_aum = float(row.get("prior_aum", np.nan))
            uret = float(row.get("underlying_return_1d", np.nan))
            pressure = prior_aum * leverage * (leverage - 1.0) * uret if np.isfinite(prior_aum) and np.isfinite(uret) else np.nan
            exposure = prior_aum * leverage if np.isfinite(prior_aum) else np.nan
            normalized = pressure / abs(exposure) if np.isfinite(pressure) and np.isfinite(exposure) and exposure else np.nan
            rows.append(
                {
                    "module": "leveraged_etf_rebalance",
                    "feature_name": "theoretical_rebalance_pressure",
                    "instrument": etf,
                    "underlying": target,
                    "as_of_date": row["session_date"],
                    "source_as_of": row["source_as_of"],
                    "available_at": row["available_at"],
                    "feature_state": "available" if np.isfinite(pressure) else "insufficient_coverage",
                    "data_quality_state": "valid" if np.isfinite(pressure) else "insufficient_coverage",
                    "methodology_version": METHODOLOGY_VERSION,
                    "source_coverage": "prior_aum_and_underlying_return" if np.isfinite(pressure) else "missing_prior_aum_or_return",
                    "confidence": "medium" if np.isfinite(pressure) else "low",
                    "coverage_tier": "sufficient" if np.isfinite(pressure) else "insufficient",
                    "pressure_direction": "buy" if pressure > 0 else "sell" if pressure < 0 else "neutral",
                    "pressure_value": pressure,
                    "pressure_normalized": normalized,
                    "is_observed_flow": False,
                    "is_model_estimate": True,
                    "explicit_limitations": "theoretical rebalance pressure only; not observed ETF flow",
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
    return pd.DataFrame(rows)


def build_vol_control_features(root: Path, canonical: pd.DataFrame) -> pd.DataFrame:
    p = policy(root)
    windows = [int(x) for x in p.get("vol_control_windows", [5, 10, 20])]
    targets = [float(x) for x in p.get("vol_control_target_vols", [0.10, 0.12])]
    max_exp = float(p.get("vol_control_max_exposure", 1.0))
    rows = []
    for ticker, g in canonical.groupby("instrument"):
        df = g.sort_values("session_date").copy()
        if df["close"].isna().all():
            continue
        px = pd.to_numeric(df["close"], errors="coerce")
        df["return_1d"] = px.pct_change()
        for window in windows:
            vol = df["return_1d"].rolling(window, min_periods=window).std() * math.sqrt(252)
            for target in targets:
                exposure = (target / vol).clip(upper=max_exp)
                exposure = exposure.where(vol > 0)
                change = exposure.diff()
                for idx, row in df.iterrows():
                    exp_value = float(exposure.loc[idx]) if pd.notna(exposure.loc[idx]) else np.nan
                    change_value = float(change.loc[idx]) if pd.notna(change.loc[idx]) else np.nan
                    pressure = change_value
                    rows.append(
                        {
                            "module": "vol_control_deleveraging",
                            "feature_name": f"target_vol_{target:g}_window_{window}",
                            "instrument": ticker,
                            "underlying": ticker,
                            "as_of_date": row["session_date"],
                            "source_as_of": row["source_as_of"],
                            "available_at": row["available_at"],
                            "feature_state": "available" if np.isfinite(pressure) else "insufficient_coverage",
                            "data_quality_state": "valid" if np.isfinite(pressure) else "insufficient_coverage",
                            "methodology_version": METHODOLOGY_VERSION,
                            "source_coverage": f"{window}d_realized_vol" if np.isfinite(pressure) else "missing_return_window",
                            "confidence": "medium" if np.isfinite(pressure) else "low",
                            "coverage_tier": "sufficient" if np.isfinite(pressure) else "insufficient",
                            "pressure_direction": "buy" if pressure > 0 else "sell" if pressure < 0 else "neutral",
                            "pressure_value": pressure,
                            "pressure_normalized": pressure,
                            "vol_control_exposure": exp_value,
                            "is_observed_flow": False,
                            "is_model_estimate": True,
                            "explicit_limitations": "normalized target-vol pressure proxy; AUM not assumed",
                            "actionization_allowed": ACTIONIZATION_ALLOWED,
                        }
                    )
    return pd.DataFrame(rows)


def placeholder_module_rows() -> pd.DataFrame:
    rows = []
    for module in sorted(SUPPORTED_MODULES - IMPLEMENTED_MODULES):
        rows.append(
            {
                "module": module,
                "feature_name": "placeholder",
                "instrument": "",
                "underlying": "",
                "as_of_date": "",
                "source_as_of": "",
                "available_at": "",
                "feature_state": "methodology_incomplete",
                "data_quality_state": "methodology_incomplete",
                "methodology_version": METHODOLOGY_VERSION,
                "source_coverage": "not_implemented_in_phase_1_2",
                "confidence": "none",
                "coverage_tier": "unavailable",
                "pressure_direction": "unknown",
                "pressure_value": np.nan,
                "pressure_normalized": np.nan,
                "is_observed_flow": False,
                "is_model_estimate": True,
                "explicit_limitations": "placeholder only; no inference or actionization",
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
        )
    return pd.DataFrame(rows)


def build_features(root: Path, manifest: dict[str, Any], canonical: pd.DataFrame) -> pd.DataFrame:
    if "dataset_type" in canonical.columns and set(canonical["dataset_type"].dropna()).intersection(CONTRACT_DATASET_TYPES):
        return build_features_from_provider_contract(root, manifest, canonical)
    frames = [
        build_leveraged_etf_features(root, manifest, canonical),
        build_vol_control_features(root, canonical),
        placeholder_module_rows(),
    ]
    return pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True)


def build_features_from_provider_contract(root: Path, manifest: dict[str, Any], canonical: pd.DataFrame) -> pd.DataFrame:
    frames = [
        build_leveraged_etf_features_contract(root, canonical),
        build_vol_control_features_contract(root, canonical),
        placeholder_module_rows(),
    ]
    out = pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True)
    decision_time = canonical["decision_time"].dropna().astype(str).iloc[0] if "decision_time" in canonical.columns and not canonical.empty else ""
    timing_class = canonical["research_timing_class"].dropna().astype(str).iloc[0] if "research_timing_class" in canonical.columns and not canonical.empty else ""
    for col, value in [("decision_time", decision_time), ("research_timing_class", timing_class), ("source_as_of", ""), ("available_at", ""), ("as_of_date", "")]:
        if col not in out.columns:
            out[col] = value
        else:
            out[col] = out[col].fillna(value)
    return out


def timing_eligible(canonical: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    if canonical.empty:
        return canonical.copy()
    return canonical[(canonical["dataset_type"] == dataset_type) & (canonical["timing_status"] == "timing_eligible")].copy()


def select_latest_aum(root: Path, aum_rows: pd.DataFrame, etf: str, decision_time: pd.Timestamp) -> pd.Series | None:
    max_age = float(policy(root).get("max_aum_observation_age_days", 3))
    rows = aum_rows[aum_rows["etf_instrument"] == etf].copy()
    if rows.empty:
        return None
    rows["available_ts"] = pd.to_datetime(rows["available_at"], utc=True, errors="coerce")
    rows["valid_until_ts"] = pd.to_datetime(rows["valid_until_timestamp"], utc=True, errors="coerce")
    rows = rows[(rows["available_ts"] <= decision_time) & (rows["valid_until_ts"] >= decision_time)]
    if rows.empty:
        return None
    rows["age_days"] = (decision_time - rows["available_ts"]).dt.total_seconds() / 86400
    rows = rows[rows["age_days"] <= max_age]
    if rows.empty:
        return None
    return rows.sort_values(["available_ts", "as_of_timestamp", "source_row_id"]).iloc[-1]


def active_reference(refs: pd.DataFrame, etf: str, decision_time: pd.Timestamp) -> pd.Series | None:
    rows = refs[refs["etf_instrument"] == etf].copy()
    if rows.empty:
        return None
    rows["start"] = pd.to_datetime(rows["effective_start_timestamp"], utc=True, errors="coerce")
    rows["end"] = pd.to_datetime(rows["effective_end_timestamp"], utc=True, errors="coerce")
    rows = rows[(rows["start"] <= decision_time) & (rows["end"].isna() | (rows["end"] >= decision_time))]
    if rows.empty:
        return None
    return rows.sort_values(["start", "source_row_id"]).iloc[-1]


def build_leveraged_etf_features_contract(root: Path, canonical: pd.DataFrame) -> pd.DataFrame:
    refs = timing_eligible(canonical, "leveraged_etf_reference")
    aum = timing_eligible(canonical, "leveraged_etf_aum")
    prices = timing_eligible(canonical, "prices_daily")
    if prices.empty:
        prices = timing_eligible(canonical, "prices_intraday")
    rows = []
    decision_time = pd.to_datetime(canonical["decision_time"].dropna().astype(str).iloc[0], utc=True) if not canonical.empty else utc_now()
    for etf in sorted(set(aum["etf_instrument"].dropna().astype(str)) if not aum.empty else []):
        ref = active_reference(refs, etf, decision_time)
        selected_aum = select_latest_aum(root, aum, etf, decision_time)
        if ref is None or selected_aum is None:
            rows.append(
                {
                    "module": "leveraged_etf_rebalance",
                    "feature_name": "theoretical_rebalance_pressure",
                    "etf_instrument": etf,
                    "instrument": etf,
                    "underlying_instrument": "" if ref is None else ref.get("underlying_instrument", ""),
                    "underlying": "" if ref is None else ref.get("underlying_instrument", ""),
                    "decision_time": iso_utc(decision_time),
                    "research_timing_class": canonical["research_timing_class"].iloc[0] if not canonical.empty else "",
                    "feature_state": "insufficient_coverage",
                    "data_quality_state": "insufficient_coverage",
                    "source_coverage": "missing_reference_mapping" if ref is None else "missing_eligible_aum",
                    "methodology_version": METHODOLOGY_VERSION,
                    "is_observed_flow": False,
                    "is_model_estimate": True,
                    "explicit_limitations": "model_implied_pressure only; not observed ETF flow",
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
            continue
        underlying = str(ref["underlying_instrument"])
        upx = prices[prices["instrument"] == underlying].sort_values("market_timestamp").copy()
        upx["underlying_return_used"] = pd.to_numeric(upx["close"], errors="coerce").pct_change()
        for _, price_row in upx.iterrows():
            underlying_return = finite_number(price_row.get("underlying_return_used"))
            aum_value = finite_number(selected_aum.get("aum_usd"))
            lev = finite_number(ref.get("target_leverage"))
            pressure = aum_value * lev * (lev - 1.0) * underlying_return if np.isfinite(aum_value) and np.isfinite(lev) and np.isfinite(underlying_return) else np.nan
            normalized = pressure / abs(aum_value * lev) if np.isfinite(pressure) and aum_value and lev else np.nan
            rows.append(
                {
                    "module": "leveraged_etf_rebalance",
                    "feature_name": "theoretical_rebalance_pressure",
                    "instrument": etf,
                    "etf_instrument": etf,
                    "underlying": underlying,
                    "underlying_instrument": underlying,
                    "as_of_date": str(price_row.get("session_date", "")),
                    "decision_time": iso_utc(decision_time),
                    "research_timing_class": price_row.get("research_timing_class", ""),
                    "selected_aum_source_row_id": selected_aum.get("source_row_id", ""),
                    "aum_as_of_timestamp": selected_aum.get("as_of_timestamp", ""),
                    "aum_available_at_timestamp": selected_aum.get("available_at", ""),
                    "aum_observation_age": float((decision_time - pd.to_datetime(selected_aum.get("available_at"), utc=True)).total_seconds() / 86400),
                    "aum_selection_rule": "latest_timing_eligible_valid_until_within_max_age",
                    "target_leverage": lev,
                    "underlying_return_used": underlying_return,
                    "underlying_return_available_at": price_row.get("available_at", ""),
                    "theoretical_rebalance_pressure": pressure,
                    "normalized_rebalance_pressure": normalized,
                    "source_as_of": price_row.get("source_as_of", ""),
                    "available_at": price_row.get("available_at", ""),
                    "source_coverage": "eligible_aum_reference_underlying_return" if np.isfinite(pressure) else "missing_underlying_return",
                    "feature_state": "available" if np.isfinite(pressure) else "insufficient_coverage",
                    "data_quality_state": "valid" if np.isfinite(pressure) else "insufficient_coverage",
                    "methodology_version": METHODOLOGY_VERSION,
                    "confidence": "medium" if np.isfinite(pressure) else "low",
                    "coverage_tier": "sufficient" if np.isfinite(pressure) else "insufficient",
                    "pressure_direction": "buy" if pressure > 0 else "sell" if pressure < 0 else "neutral",
                    "pressure_value": pressure,
                    "pressure_normalized": normalized,
                    "is_observed_flow": False,
                    "is_model_estimate": True,
                    "explicit_limitations": "model_implied_pressure only; not observed ETF flow or institutional orders",
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
    return pd.DataFrame(rows)


def build_vol_control_features_contract(root: Path, canonical: pd.DataFrame) -> pd.DataFrame:
    returns = timing_eligible(canonical, "vol_control_returns")
    if returns.empty:
        return pd.DataFrame()
    p = policy(root)
    windows = [int(x) for x in p.get("vol_control_windows", [5, 10, 20])]
    targets = [float(x) for x in p.get("vol_control_target_vols", [0.10, 0.12])]
    cap = float(p.get("vol_control_max_exposure", 1.0))
    floor = float(p.get("vol_control_exposure_floor", 0.0))
    rows = []
    decision_time = pd.to_datetime(returns["decision_time"].dropna().astype(str).iloc[0], utc=True)
    for instrument, g in returns.groupby("instrument"):
        df = g.sort_values("return_end_timestamp").copy().reset_index(drop=True)
        df["return_value"] = pd.to_numeric(df["simple_return"], errors="coerce")
        missing_basis = df["price_basis"].nunique(dropna=True) != 1
        for window in windows:
            for target in targets:
                for idx, row in df.iterrows():
                    window_df = df.iloc[max(0, idx - window + 1) : idx + 1]
                    returns_used = window_df["return_value"].dropna()
                    missing = window - len(returns_used)
                    if len(returns_used) < window or missing_basis:
                        state = "insufficient_coverage"
                        reason = "incomplete_return_window" if len(returns_used) < window else "mixed_price_basis"
                        prior_exp = new_exp = change = pressure = np.nan
                    else:
                        vol = float(returns_used.std() * math.sqrt(252))
                        new_exp = min(cap, max(floor, target / vol)) if vol > 0 else np.nan
                        prev_returns = df.iloc[max(0, idx - window) : idx]["return_value"].dropna()
                        prev_vol = float(prev_returns.std() * math.sqrt(252)) if len(prev_returns) == window else np.nan
                        prior_exp = min(cap, max(floor, target / prev_vol)) if np.isfinite(prev_vol) and prev_vol > 0 else np.nan
                        change = new_exp - prior_exp if np.isfinite(new_exp) and np.isfinite(prior_exp) else np.nan
                        pressure = change
                        state = "available" if np.isfinite(pressure) else "insufficient_coverage"
                        reason = "valid" if state == "available" else "missing_prior_exposure"
                    rows.append(
                        {
                            "module": "vol_control_deleveraging",
                            "feature_name": f"target_vol_{target:g}_window_{window}",
                            "instrument": instrument,
                            "underlying": instrument,
                            "decision_time": iso_utc(decision_time),
                            "research_timing_class": row.get("research_timing_class", ""),
                            "vol_window_name": f"{window}d",
                            "vol_estimator_name": "simple_return_realized_vol",
                            "target_volatility": target,
                            "exposure_floor": floor,
                            "exposure_cap": cap,
                            "prior_exposure": prior_exp,
                            "new_exposure": new_exp,
                            "exposure_change": change,
                            "normalized_deleveraging_pressure": pressure,
                            "returns_used_count": len(returns_used),
                            "missing_returns_count": max(0, missing),
                            "latest_return_end_timestamp": row.get("return_end_timestamp", ""),
                            "latest_return_available_at_timestamp": row.get("available_at", ""),
                            "source_row_id": row.get("source_row_id", ""),
                            "as_of_date": str(pd.to_datetime(row.get("return_end_timestamp"), utc=True, errors="coerce").date()) if row.get("return_end_timestamp") else "",
                            "source_as_of": row.get("source_as_of", ""),
                            "available_at": row.get("available_at", ""),
                            "feature_state": state,
                            "data_quality_state": "valid" if state == "available" else "insufficient_coverage",
                            "source_coverage": reason,
                            "methodology_version": METHODOLOGY_VERSION,
                            "confidence": "medium" if state == "available" else "low",
                            "coverage_tier": "sufficient" if state == "available" else "insufficient",
                            "pressure_direction": "buy" if np.isfinite(pressure) and pressure > 0 else "sell" if np.isfinite(pressure) and pressure < 0 else "neutral",
                            "pressure_value": pressure,
                            "pressure_normalized": pressure,
                            "is_observed_flow": False,
                            "is_model_estimate": True,
                            "explicit_limitations": "model_implied_pressure only; no observed vol-control order flow",
                            "actionization_allowed": ACTIONIZATION_ALLOWED,
                        }
                    )
    return pd.DataFrame(rows)


def build_backtest_results(root: Path, features: pd.DataFrame, canonical: pd.DataFrame) -> pd.DataFrame:
    p = policy(root)
    forward_days = [int(x) for x in p.get("backtest_forward_days", [1, 3, 5])]
    prices = canonical[["instrument", "session_date", "close"]].dropna().copy()
    prices = prices.sort_values(["instrument", "session_date"])
    result_rows = []
    available = features[features["feature_state"] == "available"].copy()
    if available.empty:
        return pd.DataFrame(columns=["module", "feature_name", "forward_days", "sample_count", "hit_rate", "median_forward_return", "downside_p10", "effect_size", "interpretation"])
    for (module, feature_name), g in available.groupby(["module", "feature_name"]):
        for horizon in forward_days:
            sample_rows = []
            for _, feat in g.iterrows():
                target = str(feat.get("underlying") or feat.get("instrument"))
                px = prices[prices["instrument"] == target].reset_index(drop=True)
                idx = px.index[px["session_date"] == feat["as_of_date"]]
                if len(idx) == 0:
                    continue
                i = int(idx[0])
                if i + horizon >= len(px):
                    continue
                ret = float(px.loc[i + horizon, "close"] / px.loc[i, "close"] - 1.0)
                pressure = float(feat.get("pressure_normalized", np.nan))
                sample_rows.append({"forward_return": ret, "pressure": pressure})
            sample = pd.DataFrame(sample_rows).replace([np.inf, -np.inf], np.nan).dropna()
            if sample.empty:
                continue
            signed = sample["forward_return"] * np.sign(sample["pressure"])
            high = sample[sample["pressure"].abs() >= sample["pressure"].abs().median()]
            low = sample[sample["pressure"].abs() < sample["pressure"].abs().median()]
            effect = float(high["forward_return"].median() - low["forward_return"].median()) if not high.empty and not low.empty else np.nan
            result_rows.append(
                {
                    "module": module,
                    "feature_name": feature_name,
                    "forward_days": horizon,
                    "sample_count": len(sample),
                    "hit_rate": float((signed > 0).mean()),
                    "median_forward_return": float(sample["forward_return"].median()),
                    "downside_p10": float(sample["forward_return"].quantile(0.10)),
                    "effect_size": effect,
                    "interpretation": "exploratory_descriptive_only",
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
    return pd.DataFrame(result_rows)


def source_coverage_audit(sources: list[dict[str, Any]], canonical: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for source in sources:
        instrument = str(source.get("instrument", "")).upper()
        df = canonical[canonical["instrument"] == instrument]
        rows.append(
            {
                "source_id": source.get("source_id", ""),
                "instrument": instrument,
                "module": source.get("module", source.get("feature_module", "")),
                "coverage_start_date": source.get("coverage_start_date", ""),
                "coverage_end_date": source.get("coverage_end_date", ""),
                "canonical_row_count": len(df),
                "coverage_status": "valid" if len(df) else "insufficient_coverage",
                "coverage_reason": "valid" if len(df) else "no_canonical_rows",
            }
        )
    return pd.DataFrame(rows)


def provider_source_file_inventory(root: Path, staging_id: str, sources: list[dict[str, Any]], canonical: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for source in sources:
        path = staged_source_path(root, staging_id, source)
        source_id = str(source.get("source_id", ""))
        dataset_type = str(source.get("dataset_type", ""))
        rows.append(
            {
                "source_id": source_id,
                "dataset_type": dataset_type,
                "source_name": source.get("source_name", ""),
                "source_file": source.get("source_file", ""),
                "relative_path": source.get("relative_path", ""),
                "instrument": source.get("instrument", ""),
                "asset_class": source.get("asset_class", ""),
                "dataset_version": source.get("dataset_version", ""),
                "declared_content_sha256": source.get("content_sha256", ""),
                "actual_content_sha256": file_sha256(path) if path.exists() else "",
                "source_file_bytes": path.stat().st_size if path.exists() else 0,
                "canonical_row_count": int((canonical["source_id"].astype(str) == source_id).sum()) if "source_id" in canonical.columns and not canonical.empty else 0,
                "source_contract_version": SOURCE_CONTRACT_VERSION,
                "is_synthetic_fixture": bool(source.get("is_synthetic_fixture", False)),
                "raw_provider_data_committed": False,
            }
        )
    return pd.DataFrame(rows)


def source_timeliness_audit(sources: list[dict[str, Any]], now_utc: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for source in sources:
        available_at = parse_utc_ts(source.get("available_at_timestamp"), "available_at_timestamp")
        rows.append(
            {
                "source_id": source.get("source_id", ""),
                "instrument": str(source.get("instrument", "")).upper(),
                "available_at": iso_utc(available_at),
                "decision_time_utc": iso_utc(now_utc),
                "age_hours": round((now_utc - available_at).total_seconds() / 3600, 6),
                "timeliness_status": "valid" if available_at <= now_utc else "data_quality_blocked",
                "timeliness_reason": "valid" if available_at <= now_utc else "available_at_after_decision_time",
            }
        )
    return pd.DataFrame(rows)


def feature_quality_gate(root: Path, features: pd.DataFrame, coverage: pd.DataFrame, timeliness: pd.DataFrame) -> pd.DataFrame:
    p = policy(root)
    min_rows = int(p.get("min_rows_per_implemented_module", 5))
    rows = []
    hard_block = False
    for module in sorted(SUPPORTED_MODULES):
        module_features = features[features["module"] == module]
        available_count = int((module_features["feature_state"] == "available").sum()) if not module_features.empty else 0
        if module in IMPLEMENTED_MODULES:
            ok = available_count >= min_rows
            status = "valid_research_candidate" if ok else "insufficient_coverage"
            reason = "valid" if ok else "implemented_module_insufficient_feature_rows"
            hard_block = hard_block or not ok
        else:
            status = "methodology_incomplete"
            reason = "placeholder_not_actionable"
        rows.append({"gate_scope": "module", "module": module, "quality_gate_status": status, "quality_gate_reason": reason, "available_feature_count": available_count, "actionization_allowed": ACTIONIZATION_ALLOWED})
    if (timeliness["timeliness_status"] == "data_quality_blocked").any():
        release_status = "data_quality_blocked"
        release_reason = "timeliness_blocked"
    elif hard_block:
        release_status = "insufficient_coverage"
        release_reason = "one_or_more_implemented_modules_insufficient"
    else:
        release_status = "valid_research_candidate"
        release_reason = "valid_for_research_only"
    rows.append({"gate_scope": "release", "module": "ALL", "quality_gate_status": release_status, "quality_gate_reason": release_reason, "available_feature_count": int((features["feature_state"] == "available").sum()), "actionization_allowed": ACTIONIZATION_ALLOWED})
    return pd.DataFrame(rows)


def release_core_files(rel: Path) -> list[Path]:
    files: list[Path] = []
    for base in [rel / "canonical_input", rel / "features"]:
        pbase = platform_path(base)
        if pbase.exists():
            files.extend([p for p in pbase.rglob("*") if p.is_file()])
    for name in [
        "release_core_metadata.json",
        "source_coverage_audit.csv",
        "source_timeliness_audit.csv",
        "source_file_inventory.csv",
        "provider_contract_validation_report.json",
        "timing_audit.csv",
        "feature_quality_gate.csv",
        "module_methodology.json",
        "parameter_registry.json",
        "backtest_spec.json",
        "backtest_results.csv",
        "backtest_summary.md",
        "explicit_limitations.md",
    ]:
        path = platform_path(rel / name)
        if path.exists():
            files.append(path)
    return sorted(files, key=lambda p: safe_relative_path(rel, p))


def content_set_hash(entries: list[dict[str, Any]]) -> str:
    parts = [f"{e['relative_path']}\0{e['sha256']}\0{e['bytes']}\n" for e in sorted(entries, key=lambda x: x["relative_path"])]
    return bytes_sha256("".join(parts).encode("utf-8"))


def write_content_manifest(rel: Path, release_id: str) -> dict[str, Any]:
    entries = []
    seen: set[str] = set()
    for path in release_core_files(rel):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"unsafe release core path: {path}")
        relative = safe_relative_path(rel, path)
        if relative in seen:
            raise SystemExit(f"duplicate release core path: {relative}")
        seen.add(relative)
        entries.append({"relative_path": relative, "sha256": file_sha256(path), "bytes": path.stat().st_size, "required": True})
    manifest = {
        "artifact_version": RELEASE_CONTENT_MANIFEST_VERSION,
        "release_id": release_id,
        "created_at_utc": iso_utc(utc_now()),
        "content_set_kind": "immutable_flow_pressure_research_release_core",
        "core_content_set_sha256": content_set_hash(entries),
        "entries": entries,
    }
    write_json(content_manifest_path(rel), manifest)
    return manifest


def release_core_metadata(root: Path, staging_id: str, release_id: str, manifest: dict[str, Any], gate: pd.DataFrame, research_timing_class: str, decision_time: pd.Timestamp, timing_audit_path: Path, validation_report_path: Path) -> dict[str, Any]:
    release_row = gate[gate["gate_scope"] == "release"].iloc[0].to_dict()
    return {
        "artifact_version": RELEASE_CORE_METADATA_VERSION,
        "release_id": release_id,
        "staging_id": staging_id,
        "built_at_utc": iso_utc(utc_now()),
        "source_bundle_sha256_at_build": compute_bundle_hash(root, staging_id, manifest),
        "source_bundle_manifest_sha256": source_bundle_manifest_sha256(root, staging_id),
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "canonical_schema_version": SOURCE_CONTRACT_VERSION,
        "research_timing_class": research_timing_class,
        "decision_time_specification": {"type": "explicit_utc_timestamp", "decision_time": iso_utc(decision_time)},
        "timing_audit_sha256": file_sha256(timing_audit_path),
        "provider_contract_validation_report_sha256": file_sha256(validation_report_path),
        "raw_provider_data_committed": False,
        "release_quality_status": release_row.get("quality_gate_status", "data_quality_blocked"),
        "release_quality_reason": release_row.get("quality_gate_reason", ""),
        "implemented_modules": sorted(IMPLEMENTED_MODULES),
        "placeholder_modules": sorted(SUPPORTED_MODULES - IMPLEMENTED_MODULES),
        "methodology_version": METHODOLOGY_VERSION,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def release_receipt(rel: Path, release_id: str, content_manifest: dict[str, Any]) -> dict[str, Any]:
    metadata_path = rel / "release_core_metadata.json"
    return {
        "artifact_version": ARTIFACT_VERSION,
        "release_id": release_id,
        "release_content_manifest_sha256": file_sha256(content_manifest_path(rel)),
        "release_core_content_set_sha256": content_manifest.get("core_content_set_sha256", ""),
        "release_core_metadata_sha256": file_sha256(metadata_path),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def compute_bundle_hash(root: Path, staging_id: str, manifest: dict[str, Any]) -> str:
    sources = manifest.get("sources", [])
    pieces = [json.dumps({k: v for k, v in manifest.items() if k != "sources"}, sort_keys=True)]
    for source in sorted(sources, key=lambda s: str(s.get("source_id", ""))):
        path = staged_source_path(root, staging_id, source)
        pieces.append(json.dumps(source, sort_keys=True))
        pieces.append(file_sha256(path))
    return bytes_sha256("\n".join(pieces).encode("utf-8"))


def make_release_id(root: Path, staging_id: str, manifest: dict[str, Any]) -> str:
    digest = compute_bundle_hash(root, staging_id, manifest)[:12]
    return f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{digest}"


def backtest_summary_md(results: pd.DataFrame, gate: pd.DataFrame) -> str:
    def md_table(df: pd.DataFrame) -> str:
        if df.empty:
            return "_No rows._"
        clean = df.fillna("").astype(str)
        cols = list(clean.columns)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, row in clean.iterrows():
            lines.append("| " + " | ".join(str(row[c]).replace("|", "\\|").replace("\n", " ") for c in cols) + " |")
        return "\n".join(lines)

    lines = [
        "# Flow Pressure Research v0 Backtest Summary",
        "",
        "This release is exploratory research only. It does not authorize trading, notification, or automated execution.",
        "",
        "## Quality Gate",
        md_table(gate),
        "",
        "## Results",
        md_table(results),
        "",
        "## Interpretation",
        "Reported relationships are descriptive and exploratory. No fitted calibration, optimized thresholds, or actionization are included.",
    ]
    return "\n".join(lines) + "\n"


def build_release(root: Path, staging_id: str, now_utc: str | None = None, research_timing_class: str | None = None) -> str:
    now = parse_now_utc(now_utc) or utc_now()
    timing_class = validate_timing_class(research_timing_class, root)
    manifest, sources, canonical_contract, timing_audit, validation = canonical_contract_input(root, staging_id, iso_utc(now), timing_class)
    release_id = make_release_id(root, staging_id, manifest)
    final_rel = release_dir(root, release_id)
    if final_rel.exists():
        raise SystemExit(f"release already exists: {release_id}")
    releases_dir(root).mkdir(parents=True, exist_ok=True)
    rel = releases_dir(root) / f".building_{release_id}_{uuid.uuid4().hex[:8]}"
    rel.mkdir(parents=True, exist_ok=False)
    try:
        canonical = canonical_contract
        features = build_features(root, manifest, canonical)
        coverage = source_coverage_audit(sources, canonical)
        timeliness = source_timeliness_audit(sources, now)
        inventory = provider_source_file_inventory(root, staging_id, sources, canonical)
        gate = feature_quality_gate(root, features, coverage, timeliness)
        backtest = build_backtest_results(root, features, canonical)
        write_csv(canonical, rel / "canonical_input" / "flow_pressure_canonical_source_rows.csv")
        write_csv(features, rel / "features" / "flow_pressure_features.csv")
        write_csv(inventory, rel / "source_file_inventory.csv")
        write_csv(coverage, rel / "source_coverage_audit.csv")
        write_csv(timeliness, rel / "source_timeliness_audit.csv")
        write_csv(timing_audit, rel / "timing_audit.csv")
        write_json(rel / "provider_contract_validation_report.json", validation)
        write_csv(gate, rel / "feature_quality_gate.csv")
        write_csv(backtest, rel / "backtest_results.csv")
        write_json(rel / "module_methodology.json", module_methodology())
        write_json(rel / "parameter_registry.json", parameter_registry(root, timing_class))
        write_json(rel / "backtest_spec.json", backtest_spec(root, timing_class, iso_utc(now), len(timing_audit), int((timing_audit.get("timing_status", pd.Series(dtype=str)) == "timing_eligible").sum()) if not timing_audit.empty else 0))
        (rel / "backtest_summary.md").write_text(backtest_summary_md(backtest, gate), encoding="utf-8")
        (rel / "explicit_limitations.md").write_text(explicit_limitations_text(), encoding="utf-8")
        write_json(rel / "release_core_metadata.json", release_core_metadata(root, staging_id, release_id, manifest, gate, timing_class, now, rel / "timing_audit.csv", rel / "provider_contract_validation_report.json"))
        content_manifest = write_content_manifest(rel, release_id)
        write_json(receipt_path(rel), release_receipt(rel, release_id, content_manifest))
        rel.replace(final_rel)
        verify_release(root, release_id)
        return release_id
    except Exception:
        if rel.exists():
            shutil.rmtree(platform_path(rel), ignore_errors=True)
        raise


def module_methodology() -> dict[str, Any]:
    return {
        "artifact_version": METHODOLOGY_VERSION,
        "modules": {
            "leveraged_etf_rebalance": "Theoretical rebalance pressure from prior available AUM, target leverage, and underlying return.",
            "vol_control_deleveraging": "Normalized target-vol exposure change from realized volatility windows.",
            "cta_trend_flow": "Placeholder only in this release.",
            "dealer_gamma_regime": "Placeholder only in this release.",
        },
        "all_pressure_fields_are": "model-implied pressure proxies; not observed institutional flow",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def parameter_registry(root: Path, research_timing_class: str | None = None) -> dict[str, Any]:
    p = policy(root)
    return {
        "artifact_version": ARTIFACT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "research_timing_class": research_timing_class or p.get("default_research_timing_class", "eod_next_session"),
        "methodology_version": METHODOLOGY_VERSION,
        "vol_control_windows": p.get("vol_control_windows", [5, 10, 20]),
        "vol_control_target_vols": p.get("vol_control_target_vols", [0.10, 0.12]),
        "vol_control_max_exposure": p.get("vol_control_max_exposure", 1.0),
        "vol_control_exposure_floor": p.get("vol_control_exposure_floor", 0.0),
        "max_aum_observation_age_days": p.get("max_aum_observation_age_days", 3),
        "backtest_forward_days": p.get("backtest_forward_days", [1, 3, 5]),
        "leveraged_etf_universe": p.get("leveraged_etf_universe", []),
    }


def backtest_spec(root: Path, research_timing_class: str | None = None, decision_time: str = "", timing_row_count: int = 0, timing_eligible_count: int = 0) -> dict[str, Any]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "backtest_spec_version": BACKTEST_SPEC_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "research_timing_class": research_timing_class or policy(root).get("default_research_timing_class", "eod_next_session"),
        "decision_time_specification": {"type": "explicit_utc_timestamp", "decision_time": decision_time},
        "timing_eligible_observations": timing_eligible_count,
        "timing_excluded_observations": max(0, timing_row_count - timing_eligible_count),
        "timing_excluded_share": (max(0, timing_row_count - timing_eligible_count) / timing_row_count) if timing_row_count else 0,
        "targets": ["forward close-to-close returns"],
        "forward_days": policy(root).get("backtest_forward_days", [1, 3, 5]),
        "metrics": ["hit_rate", "median_forward_return", "downside_p10", "effect_size", "sample_count"],
        "overfitting_guard": "descriptive only; no best-parameter adoption",
        "observed_flow_statement": "No observed flow data; all flow measures are model-implied pressure proxies.",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def explicit_limitations_text() -> str:
    return (
        "# Explicit Limitations\n\n"
        "- All outputs are research-only model-implied pressure proxies.\n"
        "- No output is observed institutional flow, dealer positioning, or actual CTA/vol-control order flow.\n"
        "- `actionization_allowed=false`; do not connect this release to notifications, execution, or trading gates.\n"
        "- No network fetch, scraping, forward fill, fitted calibration, source coalescing, or calendar fallback is performed.\n"
        "- CTA and Dealer modules are placeholders until source contracts and methodology are complete.\n"
    )


def validate_content_manifest(rel: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("artifact_version") != RELEASE_CONTENT_MANIFEST_VERSION:
        raise SystemExit("unsupported flow release content manifest version")
    entries = manifest.get("entries", [])
    if not isinstance(entries, list) or not entries:
        raise SystemExit("empty flow release content manifest")
    seen: set[str] = set()
    recomputed = []
    for entry in entries:
        relative = str(entry.get("relative_path", ""))
        if not relative or relative.startswith("/") or relative.startswith("\\") or ".." in PurePosixPath(relative).parts:
            raise SystemExit(f"unsafe release content path: {relative}")
        if relative in seen:
            raise SystemExit(f"duplicate release content path: {relative}")
        seen.add(relative)
        path = rel / relative
        safe_relative_path(rel, path)
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"missing or unsafe release core file: {relative}")
        sha = file_sha256(path)
        size = path.stat().st_size
        if str(entry.get("sha256", "")) != sha:
            raise SystemExit(f"release core sha mismatch: {relative}")
        if int(entry.get("bytes", -1)) != size:
            raise SystemExit(f"release core size mismatch: {relative}")
        recomputed.append({"relative_path": relative, "sha256": sha, "bytes": size})
    actual = {safe_relative_path(rel, p) for p in release_core_files(rel)}
    if actual != seen:
        raise SystemExit("release core file set does not match content manifest")
    if manifest.get("core_content_set_sha256") != content_set_hash(recomputed):
        raise SystemExit("release core content set hash mismatch")


def verify_release(root: Path, release_id: str) -> dict[str, Any]:
    rel = release_dir(root, release_id)
    if not rel.exists() or rel.name != release_id:
        raise SystemExit(f"missing release: {release_id}")
    receipt = load_json(receipt_path(rel))
    manifest = load_json(content_manifest_path(rel))
    if receipt.get("release_id") != release_id or manifest.get("release_id") != release_id:
        raise SystemExit("flow release id mismatch")
    if receipt.get("release_content_manifest_sha256") != file_sha256(content_manifest_path(rel)):
        raise SystemExit("flow release manifest hash mismatch")
    validate_content_manifest(rel, manifest)
    metadata_path = rel / "release_core_metadata.json"
    metadata_sha = file_sha256(metadata_path)
    if receipt.get("release_core_metadata_sha256") != metadata_sha:
        raise SystemExit("flow release core metadata hash mismatch")
    metadata = load_json(metadata_path)
    if metadata.get("source_contract_version") != SOURCE_CONTRACT_VERSION:
        raise SystemExit("flow release source contract version mismatch")
    if metadata.get("timing_audit_sha256") != file_sha256(rel / "timing_audit.csv"):
        raise SystemExit("flow release timing audit hash mismatch")
    if metadata.get("provider_contract_validation_report_sha256") != file_sha256(rel / "provider_contract_validation_report.json"):
        raise SystemExit("flow provider validation report hash mismatch")
    if metadata.get("raw_provider_data_committed") is not False:
        raise SystemExit("flow release raw_provider_data_committed must be false")
    gate = pd.read_csv(rel / "feature_quality_gate.csv")
    release_rows = gate[gate["gate_scope"] == "release"]
    if len(release_rows) != 1:
        raise SystemExit("flow release gate must have exactly one release row")
    release_status = str(release_rows.iloc[0]["quality_gate_status"])
    if release_status != str(metadata.get("release_quality_status")):
        raise SystemExit("flow release metadata status mismatch")
    features = pd.read_csv(rel / "features" / "flow_pressure_features.csv")
    required_cols = {"feature_state", "data_quality_state", "methodology_version", "source_coverage", "source_as_of", "available_at", "as_of_date", "is_observed_flow", "is_model_estimate", "research_timing_class", "decision_time"}
    if not required_cols.issubset(features.columns):
        raise SystemExit("flow feature output missing required fields")
    if bool(features["is_observed_flow"].fillna(False).astype(bool).any()):
        raise SystemExit("flow release cannot mark model proxies as observed flow")
    if bool(pd.Series(features["actionization_allowed"]).fillna(False).astype(bool).any()):
        raise SystemExit("flow release cannot allow actionization")
    return {
        **metadata,
        "release_content_manifest_sha256": file_sha256(content_manifest_path(rel)),
        "release_core_content_set_sha256": manifest.get("core_content_set_sha256", ""),
        "release_core_metadata_sha256": metadata_sha,
    }


def verify_staging(root: Path, staging_id: str, now_utc: str | None = None, research_timing_class: str | None = None) -> dict[str, Any]:
    now = parse_now_utc(now_utc) or utc_now()
    timing_class = validate_timing_class(research_timing_class, root)
    validation = validate_flow_provider_contract(root, staging_id, iso_utc(now), timing_class)
    if validation["validation_status"] != "valid":
        raise SystemExit(f"flow staging provider contract blocked: {validation['blocked_count']} blocking diagnostics")
    manifest = load_staging_manifest(root, staging_id)
    sources = manifest.get("sources", [])
    before_releases = releases_dir(root).exists()
    with tempfile.TemporaryDirectory(prefix="flow_pressure_preflight_") as tmp:
        temp_root = Path(tmp) / "repo"
        temp_stage = staging_dir(temp_root, staging_id)
        temp_stage.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging_dir(root, staging_id), temp_stage)
        cfg_src = root / "market_bomb_config"
        cfg_dst = temp_root / "market_bomb_config"
        if cfg_src.exists():
            shutil.copytree(cfg_src, cfg_dst)
        release_id = build_release(temp_root, staging_id, now_utc=iso_utc(now), research_timing_class=timing_class)
        verified = verify_release(temp_root, release_id)
    if releases_dir(root).exists() != before_releases:
        raise SystemExit("verify-flow-staging attempted to mutate source release directory")
    return {
        "artifact_version": ARTIFACT_VERSION,
        "staging_id": staging_id,
        "candidate_quality_status": verified.get("release_quality_status", ""),
        "candidate_quality_reason": verified.get("release_quality_reason", ""),
        "source_count": len(sources),
        "source_bundle_sha256": compute_bundle_hash(root, staging_id, manifest),
        "source_bundle_manifest_sha256": source_bundle_manifest_sha256(root, staging_id),
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "research_timing_class": timing_class,
        "validated_sources": validation.get("diagnostics", []),
        "preflight_release_id_preview": release_id,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def run_flow_backtest(root: Path, release_id: str) -> str:
    release_meta = verify_release(root, release_id)
    rel = release_dir(root, release_id)
    run_id = f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    out = rel / "backtest_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    for name in ["backtest_results.csv", "backtest_summary.md", "backtest_spec.json"]:
        shutil.copyfile(rel / name, out / name)
    manifest = build_backtest_content_manifest(out, release_id, run_id)
    write_json(out / "backtest_content_manifest.json", manifest)
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "release_id": release_id,
        "backtest_run_id": run_id,
        "backtest_spec_version": BACKTEST_SPEC_VERSION,
        "source_contract_version": release_meta.get("source_contract_version", SOURCE_CONTRACT_VERSION),
        "research_timing_class": release_meta.get("research_timing_class", ""),
        "decision_time_specification": release_meta.get("decision_time_specification", {}),
        "timing_audit_sha256": release_meta.get("timing_audit_sha256", ""),
        "run_at_utc": iso_utc(utc_now()),
        "backtest_content_manifest_sha256": file_sha256(out / "backtest_content_manifest.json"),
        "release_content_manifest_sha256": file_sha256(content_manifest_path(rel)),
        "observed_flow_statement": "No observed flow data; all flow measures are model-implied pressure proxies.",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    write_json(out / "backtest_receipt.json", receipt)
    verify_backtest(root, release_id, run_id)
    return run_id


def build_backtest_content_manifest(run_dir: Path, release_id: str, run_id: str) -> dict[str, Any]:
    entries = []
    for path in sorted([p for p in platform_path(run_dir).rglob("*") if p.is_file()], key=lambda p: str(p)):
        relative = safe_relative_path(run_dir, path)
        if relative in {"backtest_content_manifest.json", "backtest_receipt.json"}:
            continue
        entries.append({"relative_path": relative, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {
        "artifact_version": BACKTEST_CONTENT_MANIFEST_VERSION,
        "release_id": release_id,
        "backtest_run_id": run_id,
        "entries": entries,
        "content_set_sha256": content_set_hash(entries),
    }


def verify_backtest(root: Path, release_id: str, run_id: str) -> dict[str, Any]:
    verify_release(root, release_id)
    run_dir = release_dir(root, release_id) / "backtest_runs" / run_id
    manifest = load_json(run_dir / "backtest_content_manifest.json")
    receipt = load_json(run_dir / "backtest_receipt.json")
    if manifest.get("artifact_version") != BACKTEST_CONTENT_MANIFEST_VERSION:
        raise SystemExit("unsupported flow backtest manifest version")
    if manifest.get("release_id") != release_id or receipt.get("release_id") != release_id:
        raise SystemExit("flow backtest release id mismatch")
    if receipt.get("source_contract_version") != SOURCE_CONTRACT_VERSION:
        raise SystemExit("flow backtest source contract version mismatch")
    if receipt.get("backtest_spec_version") != BACKTEST_SPEC_VERSION:
        raise SystemExit("flow backtest spec version mismatch")
    if receipt.get("actionization_allowed") is not False:
        raise SystemExit("flow backtest actionization_allowed must be false")
    if receipt.get("backtest_content_manifest_sha256") != file_sha256(run_dir / "backtest_content_manifest.json"):
        raise SystemExit("flow backtest manifest hash mismatch")
    seen = set()
    recomputed = []
    for entry in manifest.get("entries", []):
        relative = str(entry.get("relative_path", ""))
        if not relative or ".." in PurePosixPath(relative).parts:
            raise SystemExit(f"unsafe flow backtest path: {relative}")
        seen.add(relative)
        path = run_dir / relative
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"missing flow backtest file: {relative}")
        sha = file_sha256(path)
        if sha != entry.get("sha256"):
            raise SystemExit(f"flow backtest sha mismatch: {relative}")
        recomputed.append({"relative_path": relative, "sha256": sha, "bytes": path.stat().st_size})
    actual = {safe_relative_path(run_dir, p) for p in platform_path(run_dir).rglob("*") if p.is_file() and safe_relative_path(run_dir, p) not in {"backtest_content_manifest.json", "backtest_receipt.json"}}
    if actual != seen:
        raise SystemExit("flow backtest file set mismatch")
    if manifest.get("content_set_sha256") != content_set_hash(recomputed):
        raise SystemExit("flow backtest content set hash mismatch")
    return {"release_id": release_id, "backtest_run_id": run_id, "status": "valid"}


def inspect_release(root: Path, release_id: str) -> dict[str, Any]:
    meta = verify_release(root, release_id)
    rel = release_dir(root, release_id)
    gate = pd.read_csv(rel / "feature_quality_gate.csv")
    features = pd.read_csv(rel / "features" / "flow_pressure_features.csv")
    return {
        "release_id": release_id,
        "release_quality_status": meta.get("release_quality_status"),
        "module_gate": gate.to_dict("records"),
        "feature_count": len(features),
        "available_feature_count": int((features["feature_state"] == "available").sum()),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Flow Pressure Research v0 release/backtest CLI")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build-flow-staging-template")
    p.add_argument("--staging-id", required=True)
    p = sub.add_parser("verify-flow-staging")
    p.add_argument("--staging-id", required=True)
    p.add_argument("--now-utc")
    p.add_argument("--research-timing-class", choices=sorted(TIMING_CLASSES))
    p = sub.add_parser("validate-flow-provider-contract")
    p.add_argument("--staging-id", required=True)
    p.add_argument("--decision-time-utc", required=True)
    p.add_argument("--research-timing-class", required=True, choices=sorted(TIMING_CLASSES))
    p.add_argument("--output")
    p = sub.add_parser("audit-flow-timing")
    p.add_argument("--staging-id", required=True)
    p.add_argument("--decision-time-utc", required=True)
    p.add_argument("--research-timing-class", required=True, choices=sorted(TIMING_CLASSES))
    p.add_argument("--output")
    p = sub.add_parser("inspect-flow-source-coverage")
    p.add_argument("--staging-id", required=True)
    p.add_argument("--decision-time-utc", required=True)
    p.add_argument("--research-timing-class", required=True, choices=sorted(TIMING_CLASSES))
    p.add_argument("--output")
    p = sub.add_parser("build-flow-release")
    p.add_argument("--staging-id", required=True)
    p.add_argument("--now-utc")
    p.add_argument("--research-timing-class", choices=sorted(TIMING_CLASSES))
    p = sub.add_parser("verify-flow-release")
    p.add_argument("--release-id", required=True)
    p = sub.add_parser("run-flow-backtest")
    p.add_argument("--release-id", required=True)
    p = sub.add_parser("verify-flow-backtest")
    p.add_argument("--release-id", required=True)
    p.add_argument("--backtest-run-id", required=True)
    p = sub.add_parser("inspect-flow-release")
    p.add_argument("--release-id", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    if args.command == "build-flow-staging-template":
        result = build_flow_staging_template(root, args.staging_id)
    elif args.command == "verify-flow-staging":
        result = verify_staging(root, args.staging_id, args.now_utc, args.research_timing_class)
    elif args.command == "validate-flow-provider-contract":
        result = validate_flow_provider_contract(root, args.staging_id, args.decision_time_utc, args.research_timing_class)
    elif args.command == "audit-flow-timing":
        result = audit_flow_timing(root, args.staging_id, args.decision_time_utc, args.research_timing_class)
    elif args.command == "inspect-flow-source-coverage":
        result = inspect_flow_source_coverage(root, args.staging_id, args.decision_time_utc, args.research_timing_class)
    elif args.command == "build-flow-release":
        result = {"release_id": build_release(root, args.staging_id, args.now_utc, args.research_timing_class)}
    elif args.command == "verify-flow-release":
        result = verify_release(root, args.release_id)
    elif args.command == "run-flow-backtest":
        result = {"backtest_run_id": run_flow_backtest(root, args.release_id)}
    elif args.command == "verify-flow-backtest":
        result = verify_backtest(root, args.release_id, args.backtest_run_id)
    elif args.command == "inspect-flow-release":
        result = inspect_release(root, args.release_id)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    if getattr(args, "output", None):
        write_json(Path(args.output), result)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
