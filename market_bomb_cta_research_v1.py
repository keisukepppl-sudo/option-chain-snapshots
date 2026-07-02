#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pandas as pd


MODULE_NAME = "cta_transparent_trend_replication_v1"
ARTIFACT_VERSION = "cta_transparent_trend_replication_v1_0_0"
HISTORICAL_MODE = "historical_descriptive_cta_trend_replication"
COT_VALIDATION_MODE = "weekly_cot_external_validation"
HISTORICAL_CONFIDENCE = "historical_descriptive_only"
ACTIONIZATION_ALLOWED = False
INCREASE_LABEL = "increase_risk"
REDUCE_LABEL = "reduce_risk"
UNCHANGED_LABEL = "unchanged"
UNAVAILABLE_LABEL = "input_unavailable"
ALLOWED_PRICE_TO_COT_RELATIONS = {"direct_futures_match", "cash_index_proxy_for_futures_cot", "etf_proxy_for_futures_cot"}
PLACEHOLDER_COT_IDENTIFIERS = {
    "",
    "blank",
    "empty",
    "none",
    "null",
    "nan",
    "na",
    "n/a",
    "not_known",
    "not_available",
    "not_applicable",
    "pending",
    "pending_manual_cot_identification",
    "placeholder",
    "manual_identification_required",
    "tbd",
    "to_be_determined",
    "unknown",
    "unresolved",
}
PLACEHOLDER_COT_PREFIXES = ("pending_", "unknown_", "tbd_", "placeholder_", "unresolved_")
FORBIDDEN_STRICT_STATUSES = {
    "gold_point_in_time_eligible",
    "silver_documented_schedule_eligible",
    "ready_for_eod_next_session_research",
}

PRICE_COLUMNS = ["date", "market_id", "instrument", "raw_close", "raw_or_adjusted"]
MAPPING_COLUMNS = ["market_id", "price_instrument", "cot_market_name", "cftc_market_code", "price_to_cot_relation", "market_mapping_authority", "notes"]
SCHEDULE_COLUMNS = ["market_id", "observation_date", "effective_session", "decision_timestamp_utc", "session_source"]
COT_COLUMNS = [
    "market_id",
    "market_name",
    "cftc_market_code",
    "position_as_of_date",
    "publication_timestamp_utc",
    "available_timestamp_utc",
    "reporting_group",
    "long_contracts",
    "short_contracts",
    "spreading_contracts",
    "open_interest_contracts",
    "source_authority",
    "revision_status",
]
SOURCE_MANIFEST_FIELDS = [
    "input_id",
    "dataset_type",
    "instrument",
    "relative_path",
    "content_sha256",
    "row_identifier_field",
    "source_name",
    "source_authority_type",
    "source_qualification_status",
    "historical_vintage_available",
    "publication_timestamp_available",
    "revision_history_available",
    "is_synthetic_fixture",
    "manual_export_timestamp_utc",
    "manual_capture_timestamp_utc",
    "raw_or_adjusted",
    "corporate_action_treatment",
    "coverage_start",
    "coverage_end",
    "notes",
]
CANONICAL_FILES = {
    "daily_market_prices": {"relative_path": "sources/daily_market_prices.csv", "columns": PRICE_COLUMNS, "required": True},
    "market_mapping": {"relative_path": "sources/market_mapping.csv", "columns": MAPPING_COLUMNS, "required": True},
    "decision_schedule": {"relative_path": "sources/decision_schedule.csv", "columns": SCHEDULE_COLUMNS, "required": True},
    "cot_weekly": {"relative_path": "sources/cot_weekly.csv", "columns": COT_COLUMNS, "required": False},
}


def utc_now_compact() -> str:
    return pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def sign(value: float) -> float:
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0


def normalize_identifier(value: Any) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).strip().casefold().split())
    return text


def is_placeholder_cot_identifier(value: object) -> bool:
    normalized = normalize_identifier(value)
    underscore = normalized.replace(" ", "_")
    return underscore in PLACEHOLDER_COT_IDENTIFIERS or any(underscore.startswith(prefix) for prefix in PLACEHOLDER_COT_PREFIXES)


def mapping_identity_payload(mapping_row: pd.Series | dict[str, Any]) -> dict[str, str]:
    get = mapping_row.get
    return {
        "market_id": str(get("market_id", "")),
        "price_instrument": str(get("price_instrument", "")),
        "cot_market_name": str(get("cot_market_name", "")),
        "cftc_market_code": str(get("cftc_market_code", "")),
        "price_to_cot_relation": str(get("price_to_cot_relation", "")),
    }


def mapping_identity_hash(mapping_row: pd.Series | dict[str, Any]) -> str:
    return bytes_sha256(json_dumps(mapping_identity_payload(mapping_row)).encode("utf-8"))


def evaluate_cot_mapping_eligibility(mapping_row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    payload = mapping_identity_payload(mapping_row)
    blocking_codes: list[str] = []
    if is_placeholder_cot_identifier(payload["cot_market_name"]):
        blocking_codes.append("cot_market_name_placeholder")
    if is_placeholder_cot_identifier(payload["cftc_market_code"]):
        blocking_codes.append("cftc_market_code_placeholder")
    if payload["price_to_cot_relation"] not in ALLOWED_PRICE_TO_COT_RELATIONS:
        blocking_codes.append("invalid_price_to_cot_relation")
    status = "cot_validation_mapping_eligible" if not blocking_codes else "cot_mapping_unresolved"
    return {
        **payload,
        "cot_mapping_status": status,
        "cot_validation_eligible": not blocking_codes,
        "blocking_codes": blocking_codes,
        "mapping_identity_hash": mapping_identity_hash(mapping_row),
    }


def cta_root(root: Path) -> Path:
    return root / "market_bomb_history" / "cta_research_v1"


def input_dir(root: Path, input_id: str) -> Path:
    return cta_root(root) / "input" / input_id


def source_manifest_path(root: Path, input_id: str) -> Path:
    return input_dir(root, input_id) / "source_manifest.json"


def historical_run_dir(root: Path, run_id: str) -> Path:
    return cta_root(root) / "historical_runs" / run_id


def validation_run_dir(root: Path, run_id: str) -> Path:
    return cta_root(root) / "cot_validation_runs" / run_id


def config_path(root: Path) -> Path:
    return root / "config" / "cta_research_v1" / "model_specs.json"


def safe_rel(base: Path, rel: str) -> Path:
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise SystemExit(f"unsafe relative path: {rel}")
    resolved_base = base.resolve()
    path = (base / rel_path).resolve()
    if not str(path).startswith(str(resolved_base)):
        raise SystemExit(f"path escapes base: {rel}")
    return path


def tracked_cta_history(root: Path) -> list[str]:
    try:
        out = subprocess.check_output(["git", "ls-files", "market_bomb_history/cta_research_v1"], cwd=root, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    return [line for line in out.splitlines() if line.strip()]


def source_by_dataset(sources: list[dict[str, Any]], dataset_type: str) -> dict[str, Any] | None:
    for source in sources:
        if str(source.get("dataset_type")) == dataset_type:
            return source
    return None


def manifest_sources(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    sources = manifest.get("sources", [])
    if not isinstance(sources, list):
        raise SystemExit("source_manifest.json sources must be a list")
    return sources


def load_source_manifest(root: Path, input_id: str) -> dict[str, Any]:
    path = source_manifest_path(root, input_id)
    if not path.exists():
        raise SystemExit(f"missing source manifest: {path}")
    return load_json(path)


def read_source_csv(root: Path, input_id: str, source: dict[str, Any]) -> pd.DataFrame:
    path = safe_rel(input_dir(root, input_id), str(source.get("relative_path", "")))
    if not path.exists():
        raise SystemExit(f"missing source file: {source.get('relative_path')}")
    return pd.read_csv(path)


def safety_flags() -> dict[str, bool]:
    return {
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "not_actual_cta_position_estimate": True,
        "not_actual_cta_flow_estimate": True,
        "not_market_impact_estimate": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "cot_is_not_cta_ground_truth": True,
        "cot_is_not_parameter_tuning_target": True,
    }


def build_template(root: Path, input_id: str) -> dict[str, Any]:
    base = input_dir(root, input_id)
    base.mkdir(parents=True, exist_ok=True)
    for spec in CANONICAL_FILES.values():
        path = base / str(spec["relative_path"])
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(",".join(spec["columns"]) + "\n", encoding="utf-8")
    manifest_path = base / "source_manifest.json"
    if not manifest_path.exists():
        write_json(
            manifest_path,
            {
                "artifact_version": ARTIFACT_VERSION,
                "module_name": MODULE_NAME,
                "input_id": input_id,
                **safety_flags(),
                "sources": [],
                "template_note": "Populate sources manually. Do not commit raw provider files.",
            },
        )
    return {"template_status": "created_or_existing", "input_id": input_id, "template_root": str(base)}


def build_cot_validation_template(root: Path, input_id: str) -> dict[str, Any]:
    build_template(root, input_id)
    path = input_dir(root, input_id) / "sources" / "cot_weekly.csv"
    if not path.exists():
        path.write_text(",".join(COT_COLUMNS) + "\n", encoding="utf-8")
    return {"template_status": "created_or_existing", "input_id": input_id, "cot_weekly_path": str(path)}


def csv_status(path: Path, expected_columns: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "read_status": "missing", "columns": [], "row_count": 0, "missing_required_headers": expected_columns, "extra_headers": []}
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return {"present": True, "read_status": "blocked", "columns": [], "row_count": 0, "missing_required_headers": expected_columns, "extra_headers": [], "read_error": str(exc)}
    columns = [str(col) for col in df.columns]
    return {
        "present": True,
        "read_status": "readable",
        "columns": columns,
        "row_count": int(len(df)),
        "missing_required_headers": sorted(set(expected_columns) - set(columns)),
        "extra_headers": sorted(set(columns) - set(expected_columns)),
    }


def manifest_entry_status(root: Path, input_id: str, source: dict[str, Any]) -> dict[str, Any]:
    rel = str(source.get("relative_path", ""))
    row: dict[str, Any] = {
        "dataset_type": source.get("dataset_type", ""),
        "instrument": source.get("instrument", ""),
        "relative_path": rel,
        "declared_sha256": source.get("content_sha256", ""),
        "actual_sha256": "",
        "hash_status": "missing_source_file",
        "source_qualification_status": source.get("source_qualification_status", ""),
        "historical_vintage_available": truthy(source.get("historical_vintage_available")),
        "publication_timestamp_available": truthy(source.get("publication_timestamp_available")),
        "revision_history_available": truthy(source.get("revision_history_available")),
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }
    try:
        path = safe_rel(input_dir(root, input_id), rel)
        if path.exists():
            actual = file_sha256(path)
            row["actual_sha256"] = actual
            row["hash_status"] = "match" if str(source.get("content_sha256")) == actual else "mismatch"
    except SystemExit:
        row["hash_status"] = "unsafe_relative_path"
    row["missing_manifest_fields"] = ",".join([field for field in SOURCE_MANIFEST_FIELDS if field not in source])
    return row


def inspect_input_contract(root: Path, input_id: str) -> dict[str, Any]:
    base = input_dir(root, input_id)
    files = []
    for dataset, spec in CANONICAL_FILES.items():
        files.append({"dataset_type": dataset, "relative_path": spec["relative_path"], "required": spec["required"], **csv_status(base / str(spec["relative_path"]), list(spec["columns"]))})
    manifest_path = source_manifest_path(root, input_id)
    entries: list[dict[str, Any]] = []
    manifest_status = "missing"
    if manifest_path.exists():
        try:
            manifest = load_json(manifest_path)
            manifest_status = "readable"
            entries = [manifest_entry_status(root, input_id, source) for source in manifest_sources(manifest)]
        except Exception as exc:
            manifest_status = f"blocked:{exc}"
    validation = validate_input(root, input_id, raise_on_missing=False)
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "inspection_status": "completed",
        "creates_run_artifact": False,
        **safety_flags(),
        "files": files,
        "manifest": {"present": manifest_path.exists(), "read_status": manifest_status, "entries": entries},
        "validation_status": validation["validation_status"],
        "validation_diagnostics": validation["diagnostics"],
    }


def inspect_cot_validation_input(root: Path, input_id: str) -> dict[str, Any]:
    path = input_dir(root, input_id) / "sources" / "cot_weekly.csv"
    status = csv_status(path, COT_COLUMNS)
    mapping_path = input_dir(root, input_id) / "sources" / "market_mapping.csv"
    mapping_rows: list[dict[str, Any]] = []
    if mapping_path.exists():
        try:
            mapping_df = pd.read_csv(mapping_path)
            if set(MAPPING_COLUMNS) <= set(mapping_df.columns):
                for _, mapping_row in mapping_df.iterrows():
                    mapping_rows.append(evaluate_cot_mapping_eligibility(mapping_row))
        except Exception:
            mapping_rows = []
    rows = []
    cot_summary: list[dict[str, Any]] = []
    if status["present"] and status["read_status"] == "readable":
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            pos = pd.to_datetime(row.get("position_as_of_date"), utc=True, errors="coerce")
            pub = pd.to_datetime(row.get("publication_timestamp_utc"), utc=True, errors="coerce")
            avail = pd.to_datetime(row.get("available_timestamp_utc"), utc=True, errors="coerce")
            rows.append(
                {
                    "market_id": row.get("market_id", ""),
                    "reporting_group": row.get("reporting_group", ""),
                    "timing_fields_present": bool(pd.notna(pos) and pd.notna(pub) and pd.notna(avail)),
                    "position_as_of_is_publication_time": bool(pd.notna(pos) and pd.notna(pub) and pos == pub),
                    "daily_interpolation_allowed": False,
                    "cot_is_not_cta_ground_truth": True,
                }
            )
        for mapping in mapping_rows:
            if df.empty:
                cot_summary.append({**mapping, "cot_source_status": "absent_or_header_only", "cot_rows_total": 0, "cot_rows_market_name_match": 0, "cot_rows_cftc_code_match": 0, "cot_rows_full_mapping_match": 0, "cot_rows_mismatch_count": 0, "reporting_groups_observed": []})
                continue
            selected = df[df["market_id"].astype(str).eq(str(mapping["market_id"]))].copy()
            market_match = selected["market_name"].map(normalize_identifier).eq(normalize_identifier(mapping["cot_market_name"])) if "market_name" in selected else pd.Series(dtype=bool)
            code_match = selected["cftc_market_code"].map(normalize_identifier).eq(normalize_identifier(mapping["cftc_market_code"])) if "cftc_market_code" in selected else pd.Series(dtype=bool)
            full_match = market_match & code_match
            cot_summary.append(
                {
                    **mapping,
                    "cot_source_status": "present",
                    "cot_rows_total": int(len(selected)),
                    "cot_rows_market_name_match": int(market_match.sum()) if len(selected) else 0,
                    "cot_rows_cftc_code_match": int(code_match.sum()) if len(selected) else 0,
                    "cot_rows_full_mapping_match": int(full_match.sum()) if len(selected) else 0,
                    "cot_rows_mismatch_count": int(len(selected) - full_match.sum()) if len(selected) else 0,
                    "reporting_groups_observed": sorted(selected["reporting_group"].dropna().astype(str).unique().tolist()) if "reporting_group" in selected else [],
                }
            )
    elif mapping_rows:
        cot_summary = [{**mapping, "cot_source_status": "absent_or_header_only", "cot_rows_total": 0, "cot_rows_market_name_match": 0, "cot_rows_cftc_code_match": 0, "cot_rows_full_mapping_match": 0, "cot_rows_mismatch_count": 0, "reporting_groups_observed": []} for mapping in mapping_rows]
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "inspection_status": "completed",
        "creates_run_artifact": False,
        "ex_post_external_validation_only": True,
        **safety_flags(),
        "file": status,
        "mapping_rows": mapping_rows,
        "cot_mapping_summary": cot_summary,
        "rows": rows,
    }


def base_validation(input_id: str, diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "validation_status": "valid" if not diagnostics else "blocked",
        "diagnostics": diagnostics,
        **safety_flags(),
    }


def validate_input(root: Path, input_id: str, raise_on_missing: bool = True, require_cot: bool = False) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    try:
        manifest = load_source_manifest(root, input_id)
        sources = manifest_sources(manifest)
    except SystemExit as exc:
        if raise_on_missing:
            raise
        return base_validation(input_id, [{"status": "blocked", "code": str(exc)}])
    seen_paths: set[str] = set()
    source_frames: dict[str, pd.DataFrame] = {}
    for source in sources:
        missing = [field for field in SOURCE_MANIFEST_FIELDS if field not in source]
        if missing:
            diagnostics.append({"status": "blocked", "code": "missing_source_manifest_fields", "source": source.get("relative_path", ""), "details": ",".join(missing)})
            continue
        rel = str(source.get("relative_path"))
        if rel in seen_paths:
            diagnostics.append({"status": "blocked", "code": "duplicate_source_path", "source": rel})
        seen_paths.add(rel)
        try:
            path = safe_rel(input_dir(root, input_id), rel)
        except SystemExit:
            diagnostics.append({"status": "blocked", "code": "unsafe_relative_path", "source": rel})
            continue
        if not path.exists():
            diagnostics.append({"status": "blocked", "code": "missing_source_file", "source": rel})
            continue
        if str(source.get("content_sha256")) != file_sha256(path):
            diagnostics.append({"status": "blocked", "code": "content_sha256_mismatch", "source": rel})
        if str(source.get("source_qualification_status")) != HISTORICAL_CONFIDENCE:
            diagnostics.append({"status": "blocked", "code": "cta_requires_descriptive_status", "source": rel})
        if str(source.get("source_qualification_status")) in FORBIDDEN_STRICT_STATUSES:
            diagnostics.append({"status": "blocked", "code": "cta_cannot_emit_strict_status", "source": rel})
        if truthy(source.get("historical_vintage_available")) or truthy(source.get("publication_timestamp_available")) or truthy(source.get("revision_history_available")):
            diagnostics.append({"status": "blocked", "code": "manual_history_cannot_claim_pit_gold", "source": rel})
        try:
            source_frames[str(source.get("dataset_type"))] = pd.read_csv(path)
        except Exception as exc:
            diagnostics.append({"status": "blocked", "code": "source_csv_unreadable", "source": rel, "details": str(exc)})
    present = {str(s.get("dataset_type")) for s in sources}
    for required in ["daily_market_prices", "market_mapping", "decision_schedule"]:
        if required not in present:
            diagnostics.append({"status": "blocked", "code": "missing_required_dataset", "dataset_type": required})
    if require_cot and "cot_weekly" not in present:
        diagnostics.append({"status": "blocked", "code": "missing_required_dataset", "dataset_type": "cot_weekly"})
    if "daily_market_prices" in source_frames:
        diagnostics.extend(validate_prices(source_frames["daily_market_prices"]))
    if "market_mapping" in source_frames:
        diagnostics.extend(validate_mapping(source_frames["market_mapping"]))
    if "decision_schedule" in source_frames:
        diagnostics.extend(validate_schedule(source_frames["decision_schedule"]))
    if {"daily_market_prices", "market_mapping", "decision_schedule"} <= set(source_frames):
        diagnostics.extend(validate_join(source_frames["daily_market_prices"], source_frames["market_mapping"], source_frames["decision_schedule"]))
    if "cot_weekly" in source_frames:
        diagnostics.extend(validate_cot(source_frames["cot_weekly"]))
    tracked = tracked_cta_history(root)
    if tracked:
        diagnostics.append({"status": "blocked", "code": "raw_provider_files_tracked", "details": ";".join(tracked)})
    return base_validation(input_id, diagnostics)


def validate_prices(df: pd.DataFrame) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    missing = set(PRICE_COLUMNS) - set(df.columns)
    if missing:
        return [{"status": "blocked", "code": "daily_market_prices_missing_columns", "details": ",".join(sorted(missing))}]
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work["raw_close"] = pd.to_numeric(work["raw_close"], errors="coerce")
    if work["date"].isna().any() or work["raw_close"].isna().any() or work["raw_close"].le(0).any():
        diagnostics.append({"status": "blocked", "code": "invalid_market_price_row"})
    if work.duplicated(["date", "market_id", "instrument"]).any():
        diagnostics.append({"status": "blocked", "code": "duplicate_market_price_key"})
    for keys, group in work.groupby(["market_id", "instrument"], dropna=False):
        if group["raw_or_adjusted"].astype(str).nunique() > 1:
            diagnostics.append({"status": "blocked", "code": "mixed_raw_adjusted_basis", "market_id": str(keys[0]), "instrument": str(keys[1])})
        dates = pd.to_datetime(group["date"], errors="coerce")
        if list(dates) != list(dates.sort_values()):
            diagnostics.append({"status": "blocked", "code": "market_dates_not_strictly_increasing", "market_id": str(keys[0]), "instrument": str(keys[1])})
    return diagnostics


def validate_mapping(df: pd.DataFrame) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    missing = set(MAPPING_COLUMNS) - set(df.columns)
    if missing:
        return [{"status": "blocked", "code": "market_mapping_missing_columns", "details": ",".join(sorted(missing))}]
    if df["market_id"].astype(str).duplicated().any():
        diagnostics.append({"status": "blocked", "code": "duplicate_market_mapping_key"})
    invalid = sorted(set(df["price_to_cot_relation"].astype(str)) - ALLOWED_PRICE_TO_COT_RELATIONS)
    if invalid:
        diagnostics.append({"status": "blocked", "code": "invalid_price_to_cot_relation", "details": ",".join(invalid)})
    return diagnostics


def validate_schedule(df: pd.DataFrame) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    missing = set(SCHEDULE_COLUMNS) - set(df.columns)
    if missing:
        return [{"status": "blocked", "code": "decision_schedule_missing_columns", "details": ",".join(sorted(missing))}]
    obs = pd.to_datetime(df["observation_date"], errors="coerce")
    eff = pd.to_datetime(df["effective_session"], errors="coerce")
    dec = pd.to_datetime(df["decision_timestamp_utc"], utc=True, errors="coerce")
    if obs.isna().any() or eff.isna().any() or dec.isna().any():
        diagnostics.append({"status": "blocked", "code": "decision_schedule_bad_datetime"})
    if (eff <= obs).any():
        diagnostics.append({"status": "blocked", "code": "same_day_or_prior_effective_session"})
    if df.duplicated(["market_id", "observation_date"]).any():
        diagnostics.append({"status": "blocked", "code": "duplicate_decision_schedule_observation"})
    return diagnostics


def validate_join(prices: pd.DataFrame, mapping: pd.DataFrame, schedule: pd.DataFrame) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    declared = {(str(r.market_id), str(r.price_instrument)) for r in mapping.itertuples()}
    observed = {(str(r.market_id), str(r.instrument)) for r in prices.itertuples()}
    undeclared = sorted(observed - declared)
    if undeclared:
        diagnostics.append({"status": "blocked", "code": "price_instrument_not_declared_in_mapping", "details": str(undeclared[:5])})
    for market_id, group in prices.groupby("market_id"):
        if group["instrument"].astype(str).nunique() != 1:
            diagnostics.append({"status": "blocked", "code": "multiple_price_instruments_for_market", "market_id": str(market_id)})
    price_keys = set(zip(prices["market_id"].astype(str), pd.to_datetime(prices["date"], errors="coerce").dt.strftime("%Y-%m-%d")))
    sched_keys = set(zip(schedule["market_id"].astype(str), pd.to_datetime(schedule["observation_date"], errors="coerce").dt.strftime("%Y-%m-%d")))
    missing = sorted(sched_keys - price_keys)
    if missing:
        diagnostics.append({"status": "blocked", "code": "schedule_observation_missing_price", "details": str(missing[:5])})
    return diagnostics


def validate_cot(df: pd.DataFrame) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    missing = set(COT_COLUMNS) - set(df.columns)
    if missing:
        return [{"status": "blocked", "code": "cot_weekly_missing_columns", "details": ",".join(sorted(missing))}]
    if df.empty:
        return diagnostics
    pos = pd.to_datetime(df["position_as_of_date"], errors="coerce")
    pub = pd.to_datetime(df["publication_timestamp_utc"], utc=True, errors="coerce")
    avail = pd.to_datetime(df["available_timestamp_utc"], utc=True, errors="coerce")
    numeric_cols = ["long_contracts", "short_contracts", "spreading_contracts", "open_interest_contracts"]
    numeric = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    if pos.isna().any() or pub.isna().any() or avail.isna().any():
        diagnostics.append({"status": "blocked", "code": "cot_timing_fields_invalid"})
    if (avail < pub).any():
        diagnostics.append({"status": "blocked", "code": "cot_available_before_publication"})
    if numeric.isna().any().any() or numeric["open_interest_contracts"].le(0).any():
        diagnostics.append({"status": "blocked", "code": "cot_numeric_fields_invalid"})
    return diagnostics


def validate_cta_cot_intake(root: Path, input_id: str, market_id: str, cot_reporting_group: str) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    base = validate_input(root, input_id, raise_on_missing=False, require_cot=True)
    diagnostics.extend(base.get("diagnostics", []))
    coverage: dict[str, Any] = {
        "cot_source_row_count": 0,
        "selected_cot_row_count": 0,
        "cot_coverage_start": "",
        "cot_coverage_end": "",
        "missing_calendar_week_count": None,
        "missing_calendar_weeks": [],
    }
    mapping_eligibility: dict[str, Any] | None = None

    try:
        manifest = load_source_manifest(root, input_id)
        sources = manifest_sources(manifest)
        mapping_source = source_by_dataset(sources, "market_mapping")
        cot_source = source_by_dataset(sources, "cot_weekly")
        if mapping_source is None:
            diagnostics.append({"status": "blocked", "code": "missing_required_dataset", "dataset_type": "market_mapping"})
            mapping = pd.DataFrame(columns=MAPPING_COLUMNS)
        else:
            mapping = read_source_csv(root, input_id, mapping_source)
        if cot_source is None:
            diagnostics.append({"status": "blocked", "code": "missing_required_dataset", "dataset_type": "cot_weekly"})
            cot = pd.DataFrame(columns=COT_COLUMNS)
        else:
            cot = read_source_csv(root, input_id, cot_source)
    except SystemExit as exc:
        diagnostics.append({"status": "blocked", "code": str(exc)})
        mapping = pd.DataFrame(columns=MAPPING_COLUMNS)
        cot = pd.DataFrame(columns=COT_COLUMNS)

    if set(MAPPING_COLUMNS) <= set(mapping.columns):
        mapping_rows = mapping[mapping["market_id"].astype(str).eq(market_id)]
        if len(mapping_rows) != 1:
            diagnostics.append({"status": "blocked", "code": "missing_or_duplicate_market_mapping", "market_id": market_id})
        else:
            map_row = mapping_rows.iloc[0]
            mapping_eligibility = evaluate_cot_mapping_eligibility(map_row)
            if not mapping_eligibility["cot_validation_eligible"]:
                diagnostics.append({"status": "blocked", "code": "cot_mapping_placeholder_blocked", "blocking_codes": ",".join(mapping_eligibility["blocking_codes"])})
    else:
        diagnostics.append({"status": "blocked", "code": "market_mapping_missing_columns"})

    if not (set(COT_COLUMNS) <= set(cot.columns)):
        diagnostics.append({"status": "blocked", "code": "cot_weekly_missing_columns"})
    elif cot.empty:
        diagnostics.append({"status": "blocked", "code": "cot_weekly_header_only"})
    else:
        coverage["cot_source_row_count"] = int(len(cot))
        selected_market = cot[cot["market_id"].astype(str).eq(market_id)].copy()
        selected = selected_market[selected_market["reporting_group"].astype(str).eq(cot_reporting_group)].copy()
        if selected.empty:
            diagnostics.append({"status": "blocked", "code": "cot_reporting_group_not_found_for_confirmed_mapping", "market_id": market_id, "cot_reporting_group": cot_reporting_group})
        else:
            coverage["selected_cot_row_count"] = int(len(selected))
            if selected.duplicated(["market_id", "position_as_of_date", "reporting_group"]).any():
                diagnostics.append({"status": "blocked", "code": "duplicate_cot_weekly_key"})
            if mapping_eligibility is not None:
                market_match = selected["market_name"].map(normalize_identifier).eq(normalize_identifier(mapping_eligibility["cot_market_name"]))
                code_match = selected["cftc_market_code"].map(normalize_identifier).eq(normalize_identifier(mapping_eligibility["cftc_market_code"]))
                if not bool((market_match & code_match).all()):
                    diagnostics.append({"status": "blocked", "code": "cot_row_market_mapping_mismatch"})
            pos = pd.to_datetime(selected["position_as_of_date"], errors="coerce")
            if pos.isna().any():
                diagnostics.append({"status": "blocked", "code": "cot_timing_fields_invalid"})
            else:
                dates = sorted(pos.dt.strftime("%Y-%m-%d").tolist())
                coverage["cot_coverage_start"] = dates[0]
                coverage["cot_coverage_end"] = dates[-1]
                observed_weeks = {(int(row.year), int(row.week)) for row in pos.dt.isocalendar().itertuples(index=False)}
                expected_weeks = {
                    (int(row.year), int(row.week))
                    for row in pd.date_range(pd.Timestamp(dates[0]), pd.Timestamp(dates[-1]), freq="W-TUE").to_series().dt.isocalendar().itertuples(index=False)
                }
                missing = [f"{year}-W{week:02d}" for year, week in sorted(expected_weeks - observed_weeks)]
                coverage["missing_calendar_week_count"] = int(len(missing))
                coverage["missing_calendar_weeks"] = missing[:20]
            pub = pd.to_datetime(selected["publication_timestamp_utc"], utc=True, errors="coerce")
            avail = pd.to_datetime(selected["available_timestamp_utc"], utc=True, errors="coerce")
            if pub.isna().any() or avail.isna().any():
                diagnostics.append({"status": "blocked", "code": "cot_timing_fields_invalid"})
            elif (avail < pub).any():
                diagnostics.append({"status": "blocked", "code": "cot_available_before_publication"})
            numeric_cols = ["long_contracts", "short_contracts", "spreading_contracts", "open_interest_contracts"]
            numeric = selected[numeric_cols].apply(pd.to_numeric, errors="coerce")
            if numeric.isna().any().any() or numeric["open_interest_contracts"].le(0).any():
                diagnostics.append({"status": "blocked", "code": "cot_numeric_fields_invalid"})

    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "market_id": market_id,
        "cot_reporting_group": cot_reporting_group,
        "cot_intake_validation_status": "blocked" if diagnostics else "valid",
        "diagnostics": diagnostics,
        "mapping_eligibility": mapping_eligibility,
        "coverage": coverage,
        "creates_run_artifact": False,
        "reads_cta_historical_artifact": False,
        "calculates_correlation": False,
        "calculates_sign_agreement": False,
        "calculates_lag": False,
        **safety_flags(),
    }


def load_model_specs(root: Path) -> tuple[dict[str, Any], str]:
    path = config_path(root)
    if not path.exists():
        raise SystemExit(f"missing model spec registry: {path}")
    payload = load_json(path)
    return payload, file_sha256(path)


def get_model_spec(root: Path, model_spec_id: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    registry, registry_hash = load_model_specs(root)
    for spec in registry.get("model_specs", []):
        if str(spec.get("model_spec_id")) == model_spec_id:
            return registry, spec, registry_hash
    raise SystemExit(f"unknown model_spec_id: {model_spec_id}")


def model_spec_hash(spec: dict[str, Any]) -> str:
    return bytes_sha256(json_dumps(spec).encode("utf-8"))


def selected_market_frames(root: Path, input_id: str, market_id: str) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    manifest = load_source_manifest(root, input_id)
    sources = manifest_sources(manifest)
    price_source = source_by_dataset(sources, "daily_market_prices")
    mapping_source = source_by_dataset(sources, "market_mapping")
    schedule_source = source_by_dataset(sources, "decision_schedule")
    if price_source is None or mapping_source is None or schedule_source is None:
        raise SystemExit("missing_required_cta_source")
    prices = read_source_csv(root, input_id, price_source)
    mapping = read_source_csv(root, input_id, mapping_source)
    schedule = read_source_csv(root, input_id, schedule_source)
    mapping_rows = mapping[mapping["market_id"].astype(str).eq(market_id)]
    if len(mapping_rows) != 1:
        raise SystemExit(f"missing_or_duplicate_market_mapping:{market_id}")
    map_row = mapping_rows.iloc[0]
    instrument = str(map_row["price_instrument"])
    prices = prices[prices["market_id"].astype(str).eq(market_id) & prices["instrument"].astype(str).eq(instrument)].copy()
    if prices.empty:
        raise SystemExit(f"missing_market_price_instrument:{market_id}:{instrument}")
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    prices["raw_close"] = pd.to_numeric(prices["raw_close"], errors="coerce")
    prices = prices.sort_values("date")
    schedule = schedule[schedule["market_id"].astype(str).eq(market_id)].copy()
    schedule["observation_date"] = pd.to_datetime(schedule["observation_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    schedule["effective_session"] = pd.to_datetime(schedule["effective_session"], errors="coerce").dt.strftime("%Y-%m-%d")
    return prices, map_row, schedule


def exposure_label(change: float | None) -> str:
    if change is None or pd.isna(change):
        return UNAVAILABLE_LABEL
    if change > 0:
        return INCREASE_LABEL
    if change < 0:
        return REDUCE_LABEL
    return UNCHANGED_LABEL


def compute_target_exposures(prices: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    work = prices.copy()
    closes = work["raw_close"].astype(float)
    component_cols: list[str] = []
    for h in [int(x) for x in spec.get("horizons", [])]:
        trend = closes / closes.shift(h) - 1.0
        signal = trend.map(lambda x: None if pd.isna(x) else sign(float(x)))
        col = f"component_signal_{h}"
        work[f"trend_return_{h}"] = trend
        work[col] = signal
        component_cols.append(col)
    if str(spec.get("combination_method")) == "single_horizon_binary":
        work["target_exposure"] = work[component_cols[0]]
    elif str(spec.get("combination_method")) == "equal_weight_binary_components":
        work["target_exposure"] = work[component_cols].apply(lambda row: None if row.isna().any() else sign(float(row.sum()) / len(component_cols)), axis=1)
    else:
        raise SystemExit(f"unsupported_combination_method:{spec.get('combination_method')}")
    priors: list[float | None] = []
    changes: list[float | None] = []
    labels: list[str] = []
    prior: float | None = None
    for target in work["target_exposure"]:
        if pd.isna(target):
            priors.append(prior)
            changes.append(None)
            labels.append(UNAVAILABLE_LABEL)
            continue
        target_f = float(target)
        change = None if prior is None else target_f - prior
        priors.append(prior)
        changes.append(change)
        labels.append(exposure_label(change))
        prior = target_f
    work["prior_target_exposure"] = priors
    work["exposure_change"] = changes
    work["exposure_change_label"] = labels
    return work


def compute_daily_exposure(prices: pd.DataFrame, map_row: pd.Series, schedule: pd.DataFrame, spec: dict[str, Any], input_id: str, run_id: str, manifest_hash: str, registry_hash: str) -> pd.DataFrame:
    priced = compute_target_exposures(prices, spec)
    work = priced.merge(schedule, left_on=["market_id", "date"], right_on=["market_id", "observation_date"], how="inner", validate="one_to_one")
    rows = []
    spec_hash = model_spec_hash(spec)
    for _, row in work.iterrows():
        rows.append(
            {
                "market_id": row["market_id"],
                "observation_date": row["observation_date"],
                "effective_session": row["effective_session"],
                "decision_timestamp_utc": row["decision_timestamp_utc"],
                "feature_cutoff_date": row["observation_date"],
                "price_instrument": row["instrument"],
                "price_to_cot_relation": map_row["price_to_cot_relation"],
                "model_spec_id": spec["model_spec_id"],
                "target_exposure": "" if pd.isna(row["target_exposure"]) else row["target_exposure"],
                "prior_target_exposure": "" if pd.isna(row["prior_target_exposure"]) else row["prior_target_exposure"],
                "exposure_change": "" if pd.isna(row["exposure_change"]) else row["exposure_change"],
                "exposure_change_label": row["exposure_change_label"],
                "decision_timing_status": "valid_next_session_eod_decision",
                "source_manifest_hash": manifest_hash,
                "model_spec_registry_hash": registry_hash,
                "model_spec_content_hash": spec_hash,
                "run_id": run_id,
                **safety_flags(),
            }
        )
    return pd.DataFrame(rows)


def build_content_manifest(out_dir: Path, manifest_name: str, run_id: str) -> dict[str, Any]:
    files = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != manifest_name:
            files.append({"relative_path": path.relative_to(out_dir).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {"artifact_version": ARTIFACT_VERSION, "module_name": MODULE_NAME, "run_id": run_id, "content_set_hash": bytes_sha256(json_dumps(files).encode("utf-8")), "files": files}


def cta_summary_md(run_id: str, input_id: str, market_id: str, model_spec_id: str, daily: pd.DataFrame) -> str:
    counts = daily["exposure_change_label"].value_counts(dropna=False).to_dict() if not daily.empty else {}
    return "\n".join(
        [
            "# CTA Transparent Trend Replication Summary",
            "",
            f"- module_name: `{MODULE_NAME}`",
            f"- run_id: `{run_id}`",
            f"- input_id: `{input_id}`",
            f"- market_id: `{market_id}`",
            f"- model_spec_id: `{model_spec_id}`",
            "- mode: `historical_descriptive_cta_trend_replication`",
            "- actionization_allowed: `false`",
            "- predictive_pit_eligible: `false`",
            "- phase2_eligible: `false`",
            "",
            "This is a transparent normalized trend-state model, not actual CTA position, flow, market impact, or a trading signal.",
            "",
            f"Exposure change label counts: `{counts}`",
        ]
    ) + "\n"


def limitations_md() -> str:
    return """# CTA Research Limitations

This artifact is historical descriptive research only.

The output is a transparent fixed-specification trend-state path. It is not actual CTA manager positioning, not CTA dollar flow, not market impact, not a prediction ledger, and not a trading instruction.

COT validation, when run separately, is an external weekly consistency comparison only. COT is not CTA ground truth and cannot be used for parameter tuning, automatic acceptance, promotion, alerts, sizing, execution, or Phase 2 admission.
"""


def run_historical(root: Path, input_id: str, market_id: str, model_spec_id: str) -> dict[str, Any]:
    validation = validate_input(root, input_id)
    if validation["validation_status"] != "valid":
        raise SystemExit("cta_input_validation_blocked")
    registry, spec, registry_hash = get_model_spec(root, model_spec_id)
    if str(spec.get("parameter_selection_status")) != "predeclared_not_fitted":
        raise SystemExit("cta_model_spec_must_be_predeclared")
    prices, map_row, schedule = selected_market_frames(root, input_id, market_id)
    mapping_eligibility = evaluate_cot_mapping_eligibility(map_row)
    run_id = f"{utc_now_compact()}_{bytes_sha256((input_id + market_id + model_spec_id + str(uuid.uuid4())).encode())[:12]}"
    out = historical_run_dir(root, run_id)
    if out.exists():
        raise SystemExit("cta_run_artifact_not_immutable")
    out.mkdir(parents=True, exist_ok=False)
    manifest_hash = file_sha256(source_manifest_path(root, input_id))
    daily = compute_daily_exposure(prices, map_row, schedule, spec, input_id, run_id, manifest_hash, registry_hash)
    timing = daily[["market_id", "observation_date", "decision_timestamp_utc", "effective_session", "feature_cutoff_date", "decision_timing_status"]].copy()
    write_json(out / "cta_input_validation_report.json", validation)
    write_json(out / "cta_model_spec_snapshot.json", {"registry": registry, "registry_content_sha256": registry_hash, "selected_model_spec": spec, "selected_model_spec_content_sha256": model_spec_hash(spec)})
    write_json(
        out / "cta_market_mapping_snapshot.json",
        {
            "market_id": market_id,
            "mapping": map_row.to_dict(),
            "price_to_cot_relation": map_row["price_to_cot_relation"],
            **mapping_eligibility,
        },
    )
    write_csv(out / "cta_decision_timing_audit.csv", timing.to_dict("records"))
    write_csv(out / "cta_daily_exposure.csv", daily.to_dict("records"))
    (out / "cta_summary.md").write_text(cta_summary_md(run_id, input_id, market_id, model_spec_id, daily), encoding="utf-8")
    (out / "cta_limitations.md").write_text(limitations_md(), encoding="utf-8")
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "run_id": run_id,
        "input_id": input_id,
        "market_id": market_id,
        "mode": HISTORICAL_MODE,
        "model_spec_id": model_spec_id,
        "model_spec_registry_hash": registry_hash,
        "release_created": False,
        "backtest_run": False,
        "phase1_3_readiness_run": False,
        "phase2_run": False,
        "cot_mapping_status": mapping_eligibility["cot_mapping_status"],
        "cot_validation_eligible": mapping_eligibility["cot_validation_eligible"],
        "cot_mapping_blocking_codes": mapping_eligibility["blocking_codes"],
        "mapping_identity_hash": mapping_eligibility["mapping_identity_hash"],
        **safety_flags(),
    }
    write_json(out / "cta_run_receipt.json", receipt)
    write_json(out / "cta_content_manifest.json", build_content_manifest(out, "cta_content_manifest.json", run_id))
    return {"run_status": "completed", "run_artifact": str(out), **receipt}


def verify_manifested_dir(run_artifact: Path, manifest_name: str) -> dict[str, Any]:
    manifest_path = run_artifact / manifest_name
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_name}")
    manifest = load_json(manifest_path)
    failures = []
    expected = {entry["relative_path"]: entry for entry in manifest.get("files", [])}
    actual = {p.relative_to(run_artifact).as_posix(): p for p in run_artifact.rglob("*") if p.is_file() and p.name != manifest_name}
    for rel, entry in expected.items():
        path = run_artifact / rel
        if not path.exists():
            failures.append({"relative_path": rel, "reason": "missing"})
        elif file_sha256(path) != entry.get("sha256"):
            failures.append({"relative_path": rel, "reason": "sha256_mismatch"})
    for rel in sorted(set(actual) - set(expected)):
        failures.append({"relative_path": rel, "reason": "extra_file"})
    return {"verification_status": "valid" if not failures else "tampered", "failures": failures, "artifact": str(run_artifact)}


def verify_cta_run(run_artifact: str) -> dict[str, Any]:
    path = Path(run_artifact).resolve()
    result = verify_manifested_dir(path, "cta_content_manifest.json")
    receipt = load_json(path / "cta_run_receipt.json")
    for field in ["actionization_allowed", "predictive_pit_eligible", "phase2_eligible", "phase1_3_readiness_run", "phase2_run", "release_created", "backtest_run"]:
        if receipt.get(field) is not False:
            result["verification_status"] = "tampered"
            result.setdefault("failures", []).append({"relative_path": "cta_run_receipt.json", "reason": f"{field}_must_be_false"})
    if (path / "cta_market_mapping_snapshot.json").exists():
        snapshot = load_json(path / "cta_market_mapping_snapshot.json")
        if "mapping_identity_hash" in snapshot:
            expected = mapping_identity_hash(snapshot.get("mapping", snapshot))
            if snapshot.get("mapping_identity_hash") != expected:
                result["verification_status"] = "tampered"
                result.setdefault("failures", []).append({"relative_path": "cta_market_mapping_snapshot.json", "reason": "mapping_identity_hash_mismatch"})
            for field in ["cot_mapping_status", "cot_validation_eligible", "mapping_identity_hash"]:
                if field not in receipt:
                    result["verification_status"] = "tampered"
                    result.setdefault("failures", []).append({"relative_path": "cta_run_receipt.json", "reason": f"{field}_missing"})
    return result


def nearest_daily_on_or_before(daily: pd.DataFrame, date_value: Any) -> pd.Series | None:
    date = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(date):
        return None
    work = daily.copy()
    work["_date"] = pd.to_datetime(work["observation_date"], errors="coerce")
    candidates = work[work["_date"].le(date)]
    if candidates.empty:
        return None
    return candidates.sort_values("_date").iloc[-1]


def cot_pairs_for_mode(daily: pd.DataFrame, cot: pd.DataFrame, mapping: pd.Series, reporting_group: str, alignment_mode: str) -> pd.DataFrame:
    selected = cot[cot["reporting_group"].astype(str).eq(reporting_group) & cot["market_id"].astype(str).eq(str(mapping["market_id"]))].copy()
    if selected.empty:
        return pd.DataFrame()
    selected["position_as_of_date"] = pd.to_datetime(selected["position_as_of_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    selected["publication_timestamp_utc"] = pd.to_datetime(selected["publication_timestamp_utc"], utc=True, errors="coerce")
    selected["available_timestamp_utc"] = pd.to_datetime(selected["available_timestamp_utc"], utc=True, errors="coerce")
    selected["long_contracts"] = pd.to_numeric(selected["long_contracts"], errors="coerce")
    selected["short_contracts"] = pd.to_numeric(selected["short_contracts"], errors="coerce")
    selected["spreading_contracts"] = pd.to_numeric(selected["spreading_contracts"], errors="coerce")
    selected["open_interest_contracts"] = pd.to_numeric(selected["open_interest_contracts"], errors="coerce")
    selected = selected.dropna(subset=["position_as_of_date", "publication_timestamp_utc", "available_timestamp_utc", "long_contracts", "short_contracts", "open_interest_contracts"])
    selected = selected[selected["open_interest_contracts"].gt(0)].sort_values("position_as_of_date")
    if alignment_mode == "availability_monitoring_only":
        latest_decision = pd.to_datetime(daily["decision_timestamp_utc"], utc=True, errors="coerce").max()
        selected = selected[selected["available_timestamp_utc"].le(latest_decision)]
    rows = []
    prev_model: float | None = None
    prev_net: float | None = None
    prev_ratio: float | None = None
    for _, cot_row in selected.iterrows():
        if alignment_mode == "as_of_ex_post_only":
            model_row = nearest_daily_on_or_before(daily, cot_row["position_as_of_date"])
            timing_eligible = model_row is not None
        else:
            comparison_date = cot_row["available_timestamp_utc"].date().isoformat()
            model_row = nearest_daily_on_or_before(daily, comparison_date)
            timing_eligible = model_row is not None and pd.notna(cot_row["available_timestamp_utc"])
        if model_row is None:
            continue
        model_exp = pd.to_numeric(pd.Series([model_row.get("target_exposure")]), errors="coerce").iloc[0]
        if pd.isna(model_exp):
            continue
        net = float(cot_row["long_contracts"] - cot_row["short_contracts"])
        ratio = net / float(cot_row["open_interest_contracts"])
        model_change = None if prev_model is None else float(model_exp) - prev_model
        net_change = None if prev_net is None else net - prev_net
        ratio_change = None if prev_ratio is None else ratio - prev_ratio
        level_agree = "" if model_exp == 0 or ratio == 0 else bool(sign(float(model_exp)) == sign(float(ratio)))
        change_agree = "" if model_change is None or ratio_change is None or model_change == 0 or ratio_change == 0 else bool(sign(float(model_change)) == sign(float(ratio_change)))
        rows.append(
            {
                "market_id": cot_row["market_id"],
                "market_name": cot_row["market_name"],
                "cftc_market_code": cot_row["cftc_market_code"],
                "price_to_cot_relation": mapping["price_to_cot_relation"],
                "reporting_group": cot_row["reporting_group"],
                "position_as_of_date": cot_row["position_as_of_date"],
                "publication_timestamp_utc": cot_row["publication_timestamp_utc"].isoformat(),
                "available_timestamp_utc": cot_row["available_timestamp_utc"].isoformat(),
                "alignment_mode": alignment_mode,
                "model_exposure_level": float(model_exp),
                "model_weekly_exposure_change": "" if model_change is None else model_change,
                "cot_long_contracts": float(cot_row["long_contracts"]),
                "cot_short_contracts": float(cot_row["short_contracts"]),
                "cot_spreading_contracts": float(cot_row["spreading_contracts"]),
                "cot_open_interest_contracts": float(cot_row["open_interest_contracts"]),
                "cot_net_contracts": net,
                "cot_net_open_interest_ratio": ratio,
                "cot_weekly_net_contract_change": "" if net_change is None else net_change,
                "cot_weekly_net_oi_ratio_change": "" if ratio_change is None else ratio_change,
                "level_sign_agreement": level_agree,
                "change_sign_agreement": change_agree,
                "timing_eligible": bool(timing_eligible),
                "not_decision_available_at_position_as_of": alignment_mode == "as_of_ex_post_only",
                "cot_available_at_comparison": alignment_mode == "availability_monitoring_only",
                "ex_post_external_validation_only": True,
                "cot_is_not_cta_ground_truth": True,
            }
        )
        prev_model = float(model_exp)
        prev_net = net
        prev_ratio = ratio
    return pd.DataFrame(rows)


def corr(a: pd.Series, b: pd.Series, method: str) -> float | None:
    work = pd.DataFrame({"a": pd.to_numeric(a, errors="coerce"), "b": pd.to_numeric(b, errors="coerce")}).dropna()
    if len(work) < 2 or work["a"].nunique() < 2 or work["b"].nunique() < 2:
        return None
    return float(work["a"].corr(work["b"], method=method))


def sign_agreement_rate(a: pd.Series) -> float | None:
    vals = [x for x in a if isinstance(x, bool)]
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def turning_point_metrics(pairs: pd.DataFrame, window: int) -> tuple[float | None, float | None]:
    model = pd.to_numeric(pairs["model_weekly_exposure_change"], errors="coerce")
    cot = pd.to_numeric(pairs["cot_weekly_net_oi_ratio_change"], errors="coerce")
    model_flips = [i for i in range(1, len(model)) if pd.notna(model.iloc[i]) and pd.notna(model.iloc[i - 1]) and sign(float(model.iloc[i])) != sign(float(model.iloc[i - 1]))]
    cot_flips = [i for i in range(1, len(cot)) if pd.notna(cot.iloc[i]) and pd.notna(cot.iloc[i - 1]) and sign(float(cot.iloc[i])) != sign(float(cot.iloc[i - 1]))]
    if not model_flips or not cot_flips:
        return None, None
    lags = []
    for idx in model_flips:
        candidates = [c - idx for c in cot_flips if abs(c - idx) <= window]
        if candidates:
            lags.append(min(candidates, key=lambda x: abs(x)))
    if not lags:
        return 0.0, None
    return float(len(lags) / len(model_flips)), float(pd.Series(lags).median())


def validation_summary_rows(pairs: pd.DataFrame, minimum_pairs: int, window: int) -> list[dict[str, Any]]:
    rows = []
    if pairs.empty:
        return rows
    for (alignment_mode, reporting_group, relation), group in pairs.groupby(["alignment_mode", "reporting_group", "price_to_cot_relation"], dropna=False):
        enough = len(group) >= minimum_pairs
        turn_rate, turn_lag = turning_point_metrics(group, window) if enough else (None, None)
        rows.append(
            {
                "weekly_pair_count": len(group),
                "metrics_available": bool(enough),
                "metrics_unavailable_reason": "" if enough else f"weekly_pair_count_below_{minimum_pairs}",
                "level_pearson_correlation": "" if not enough else corr(group["model_exposure_level"], group["cot_net_open_interest_ratio"], "pearson"),
                "level_spearman_correlation": "" if not enough else corr(group["model_exposure_level"], group["cot_net_open_interest_ratio"], "spearman"),
                "change_pearson_correlation": "" if not enough else corr(group["model_weekly_exposure_change"], group["cot_weekly_net_oi_ratio_change"], "pearson"),
                "change_spearman_correlation": "" if not enough else corr(group["model_weekly_exposure_change"], group["cot_weekly_net_oi_ratio_change"], "spearman"),
                "level_sign_agreement_rate": "" if not enough else sign_agreement_rate(group["level_sign_agreement"]),
                "change_sign_agreement_rate": "" if not enough else sign_agreement_rate(group["change_sign_agreement"]),
                "gross_turning_point_agreement_rate": "" if turn_rate is None else turn_rate,
                "median_turning_point_lag_weeks": "" if turn_lag is None else turn_lag,
                "price_to_cot_relation": relation,
                "alignment_mode": alignment_mode,
                "reporting_group": reporting_group,
                "coverage_start": group["position_as_of_date"].min(),
                "coverage_end": group["position_as_of_date"].max(),
                "automatic_acceptance_threshold_applied": False,
                "non_acceptance_policy": "No automatic acceptance threshold is applied. High in-sample correlation can be affected by mixed COT participants, proxy mismatch, common trend exposure, release lag, and overfitting risk. Cross-period and cross-market stability must be evaluated separately later.",
            }
        )
    return rows


def assert_cta_cot_mapping_preflight(root: Path, input_id: str, market_id: str, cot_reporting_group: str, cta_artifact: Path) -> tuple[pd.Series, dict[str, Any], pd.DataFrame, dict[str, Any]]:
    _, map_row, _ = selected_market_frames(root, input_id, market_id)
    current = evaluate_cot_mapping_eligibility(map_row)
    if not current["cot_validation_eligible"]:
        raise SystemExit("cta_cot_mapping_placeholder_blocked")

    snapshot_path = cta_artifact / "cta_market_mapping_snapshot.json"
    receipt_path = cta_artifact / "cta_run_receipt.json"
    if not snapshot_path.exists() or not receipt_path.exists():
        raise SystemExit("cta_run_mapping_snapshot_mismatch")
    snapshot = load_json(snapshot_path)
    receipt = load_json(receipt_path)
    legacy_required = ["cot_validation_eligible", "mapping_identity_hash", "cot_mapping_status"]
    if any(field not in snapshot for field in legacy_required) or any(field not in receipt for field in legacy_required):
        raise SystemExit("cta_run_mapping_snapshot_mismatch")
    if str(receipt.get("market_id")) != market_id or str(snapshot.get("market_id")) != market_id:
        raise SystemExit("cta_run_mapping_snapshot_mismatch")
    if snapshot.get("cot_validation_eligible") is not True or receipt.get("cot_validation_eligible") is not True:
        raise SystemExit("cta_run_mapping_snapshot_mismatch")
    if snapshot.get("mapping_identity_hash") != current["mapping_identity_hash"] or receipt.get("mapping_identity_hash") != current["mapping_identity_hash"]:
        raise SystemExit("cta_run_mapping_snapshot_mismatch")
    snap_payload = mapping_identity_payload(snapshot.get("mapping", snapshot))
    for key in ["market_id", "price_instrument", "cot_market_name", "cftc_market_code", "price_to_cot_relation"]:
        if normalize_identifier(snap_payload.get(key)) != normalize_identifier(current.get(key)):
            raise SystemExit("cta_run_mapping_snapshot_mismatch")

    manifest = load_source_manifest(root, input_id)
    cot_source = source_by_dataset(manifest_sources(manifest), "cot_weekly")
    if cot_source is None:
        raise SystemExit("missing_cot_weekly")
    cot = read_source_csv(root, input_id, cot_source)
    selected = cot[cot["market_id"].astype(str).eq(market_id) & cot["reporting_group"].astype(str).eq(cot_reporting_group)].copy()
    if selected.empty:
        raise SystemExit("cot_reporting_group_not_found_for_confirmed_mapping")
    market_match = selected["market_name"].map(normalize_identifier).eq(normalize_identifier(current["cot_market_name"]))
    code_match = selected["cftc_market_code"].map(normalize_identifier).eq(normalize_identifier(current["cftc_market_code"]))
    full_match = market_match & code_match
    if not bool(full_match.all()):
        raise SystemExit("cot_row_market_mapping_mismatch")
    eligibility_snapshot = {
        "current_mapping_identity_hash": current["mapping_identity_hash"],
        "cta_run_mapping_identity_hash": snapshot["mapping_identity_hash"],
        "mapping_snapshot_match": True,
        "cot_row_mapping_match_required": True,
        "cot_rows_checked": int(len(selected)),
        "cot_rows_full_mapping_match": int(full_match.sum()),
        "cot_validation_eligible": True,
        "cot_mapping_status": current["cot_mapping_status"],
        "price_to_cot_relation": current["price_to_cot_relation"],
        "ex_post_external_validation_only": True,
        "cot_is_not_cta_ground_truth": True,
        "cot_is_not_parameter_tuning_target": True,
    }
    return map_row, current, cot, eligibility_snapshot


def run_cot_validation(root: Path, cta_run_artifact: str, input_id: str, market_id: str, cot_reporting_group: str) -> dict[str, Any]:
    validation = validate_input(root, input_id, require_cot=True)
    if validation["validation_status"] != "valid":
        raise SystemExit("cta_cot_input_validation_blocked")
    cta_artifact = Path(cta_run_artifact).resolve()
    cta_verify = verify_cta_run(str(cta_artifact))
    if cta_verify["verification_status"] != "valid":
        raise SystemExit("cta_run_artifact_invalid")
    map_row, current_mapping, cot, eligibility_snapshot = assert_cta_cot_mapping_preflight(root, input_id, market_id, cot_reporting_group, cta_artifact)
    daily = pd.read_csv(cta_artifact / "cta_daily_exposure.csv")
    asof = cot_pairs_for_mode(daily, cot, map_row, cot_reporting_group, "as_of_ex_post_only")
    avail = cot_pairs_for_mode(daily, cot, map_row, cot_reporting_group, "availability_monitoring_only")
    pairs = pd.concat([asof, avail], ignore_index=True) if not asof.empty or not avail.empty else pd.DataFrame()
    registry, _, registry_hash = get_model_spec(root, str(load_json(cta_artifact / "cta_run_receipt.json")["model_spec_id"]))
    minimum = int(registry.get("minimum_weekly_pairs_for_summary", 26))
    window = int(registry.get("turning_point_lag_window_weeks", 4))
    run_id = f"{utc_now_compact()}_{bytes_sha256((input_id + market_id + cot_reporting_group + str(uuid.uuid4())).encode())[:12]}"
    out = validation_run_dir(root, run_id)
    if out.exists():
        raise SystemExit("cta_cot_validation_artifact_not_immutable")
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "cta_cot_input_validation_report.json", validation)
    write_json(out / "cta_cot_model_run_reference.json", {"cta_run_artifact": str(cta_artifact), "cta_run_verification": cta_verify})
    write_json(out / "cta_cot_mapping_eligibility_snapshot.json", eligibility_snapshot)
    write_csv(out / "cta_cot_weekly_pairs.csv", pairs.to_dict("records") if not pairs.empty else [], list(pairs.columns) if not pairs.empty else [])
    summary = validation_summary_rows(pairs, minimum, window)
    write_csv(out / "cta_cot_validation_summary.csv", summary)
    (out / "cta_cot_validation_summary.md").write_text(cot_validation_md(run_id, input_id, market_id, cot_reporting_group, len(pairs), summary), encoding="utf-8")
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "validation_run_id": run_id,
        "run_id": run_id,
        "input_id": input_id,
        "market_id": market_id,
        "mode": COT_VALIDATION_MODE,
        "cta_run_artifact": str(cta_artifact),
        "cot_reporting_group": cot_reporting_group,
        "model_spec_registry_hash": registry_hash,
        "minimum_weekly_pairs_for_summary": minimum,
        "mapping_identity_hash": current_mapping["mapping_identity_hash"],
        "cot_mapping_status": current_mapping["cot_mapping_status"],
        "cot_validation_eligible": True,
        "mapping_snapshot_match": True,
        "cot_row_mapping_match_required": True,
        "release_created": False,
        "backtest_run": False,
        "phase1_3_readiness_run": False,
        "phase2_run": False,
        "ex_post_external_validation_only": True,
        **safety_flags(),
    }
    write_json(out / "cta_cot_validation_receipt.json", receipt)
    write_json(out / "cta_cot_validation_content_manifest.json", build_content_manifest(out, "cta_cot_validation_content_manifest.json", run_id))
    return {"validation_status": "completed", "validation_artifact": str(out), **receipt}


def cot_validation_md(run_id: str, input_id: str, market_id: str, group: str, pair_count: int, summary: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "# CTA COT Weekly External Validation Summary",
            "",
            f"- validation_run_id: `{run_id}`",
            f"- input_id: `{input_id}`",
            f"- market_id: `{market_id}`",
            f"- reporting_group: `{group}`",
            f"- weekly_pair_rows: `{pair_count}`",
            "- ex_post_external_validation_only: `true`",
            "- cot_is_not_cta_ground_truth: `true`",
            "- cot_is_not_parameter_tuning_target: `true`",
            "",
            "No automatic acceptance threshold is applied. High in-sample correlation can be affected by mixed COT participants, proxy mismatch, common trend exposure, release lag, and overfitting risk. Cross-period and cross-market stability must be evaluated separately later.",
            "",
            f"Summary rows: `{len(summary)}`",
        ]
    ) + "\n"


def verify_cot_validation(validation_artifact: str) -> dict[str, Any]:
    path = Path(validation_artifact).resolve()
    result = verify_manifested_dir(path, "cta_cot_validation_content_manifest.json")
    receipt = load_json(path / "cta_cot_validation_receipt.json")
    snapshot_path = path / "cta_cot_mapping_eligibility_snapshot.json"
    if not snapshot_path.exists():
        result["verification_status"] = "tampered"
        result.setdefault("failures", []).append({"relative_path": "cta_cot_mapping_eligibility_snapshot.json", "reason": "missing"})
    else:
        snapshot = load_json(snapshot_path)
        for field in ["mapping_snapshot_match", "cot_row_mapping_match_required", "cot_validation_eligible"]:
            if snapshot.get(field) is not True:
                result["verification_status"] = "tampered"
                result.setdefault("failures", []).append({"relative_path": "cta_cot_mapping_eligibility_snapshot.json", "reason": f"{field}_must_be_true"})
    for field in ["actionization_allowed", "predictive_pit_eligible", "phase2_eligible", "phase1_3_readiness_run", "phase2_run", "release_created", "backtest_run"]:
        if receipt.get(field) is not False:
            result["verification_status"] = "tampered"
            result.setdefault("failures", []).append({"relative_path": "cta_cot_validation_receipt.json", "reason": f"{field}_must_be_false"})
    for field in ["mapping_snapshot_match", "cot_row_mapping_match_required", "cot_validation_eligible"]:
        if receipt.get(field) is not True:
            result["verification_status"] = "tampered"
            result.setdefault("failures", []).append({"relative_path": "cta_cot_validation_receipt.json", "reason": f"{field}_must_be_true"})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=MODULE_NAME)
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build-cta-template")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("inspect-cta-input-contract")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("validate-cta-input")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("run-cta-historical-descriptive")
    p.add_argument("--input-id", required=True)
    p.add_argument("--market-id", required=True)
    p.add_argument("--model-spec-id", required=True)
    p = sub.add_parser("verify-cta-run")
    p.add_argument("--run-artifact", required=True)
    p = sub.add_parser("build-cta-cot-validation-template")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("inspect-cta-cot-validation-input")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("validate-cta-cot-intake")
    p.add_argument("--input-id", required=True)
    p.add_argument("--market-id", required=True)
    p.add_argument("--cot-reporting-group", required=True)
    p = sub.add_parser("run-cta-cot-weekly-external-validation")
    p.add_argument("--cta-run-artifact", required=True)
    p.add_argument("--input-id", required=True)
    p.add_argument("--market-id", required=True)
    p.add_argument("--cot-reporting-group", required=True)
    p = sub.add_parser("verify-cta-cot-validation")
    p.add_argument("--validation-artifact", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.command == "build-cta-template":
        result = build_template(root, args.input_id)
    elif args.command == "inspect-cta-input-contract":
        result = inspect_input_contract(root, args.input_id)
    elif args.command == "validate-cta-input":
        result = validate_input(root, args.input_id)
    elif args.command == "run-cta-historical-descriptive":
        result = run_historical(root, args.input_id, args.market_id, args.model_spec_id)
    elif args.command == "verify-cta-run":
        result = verify_cta_run(args.run_artifact)
    elif args.command == "build-cta-cot-validation-template":
        result = build_cot_validation_template(root, args.input_id)
    elif args.command == "inspect-cta-cot-validation-input":
        result = inspect_cot_validation_input(root, args.input_id)
    elif args.command == "validate-cta-cot-intake":
        result = validate_cta_cot_intake(root, args.input_id, args.market_id, args.cot_reporting_group)
    elif args.command == "run-cta-cot-weekly-external-validation":
        result = run_cot_validation(root, args.cta_run_artifact, args.input_id, args.market_id, args.cot_reporting_group)
    elif args.command == "verify-cta-cot-validation":
        result = verify_cot_validation(args.validation_artifact)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    print(json_dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
