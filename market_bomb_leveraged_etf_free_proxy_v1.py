#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pandas as pd


MODULE_NAME = "leveraged_etf_free_directional_proxy_v1"
ARTIFACT_VERSION = "leveraged_etf_free_directional_proxy_v1_0_0"
MODEL_ASSUMPTION_SET = "static_daily_reset_notional_proxy_v1"
MIN_ABS_BENCHMARK_RETURN = 0.001
ACTIONIZATION_ALLOWED = False
HISTORICAL_MODE = "historical_free_descriptive_proxy"
FORWARD_MODE = "forward_pit_lite_observation"
HISTORICAL_CONFIDENCE = "historical_descriptive_only"
FORWARD_CONFIDENCE = "forward_pit_lite"
PROXY_CONFIDENCE = "benchmark_proxy_only"
INPUT_UNAVAILABLE = "input_unavailable"
REQUIRED_HISTORY_STATUSES = {"historical_descriptive_only"}
FORBIDDEN_STRICT_STATUSES = {
    "gold_point_in_time_eligible",
    "silver_documented_schedule_eligible",
    "ready_for_eod_next_session_research",
}

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

MAPPING_FIELDS = [
    "leveraged_etf",
    "target_benchmark_instrument",
    "market_proxy_instrument",
    "target_leverage",
    "directionality",
    "benchmark_exact_or_proxy",
    "is_proxy_underlying",
    "mapping_source_authority",
]

PRICE_COLUMNS = ["date", "instrument", "raw_close", "raw_or_adjusted"]
AUM_COLUMNS = ["date", "instrument", "aum_usd", "shares_outstanding", "nav_per_share", "unit"]
SPLIT_COLUMNS = ["instrument", "effective_date", "split_ratio", "source_authority"]
MAPPING_COLUMNS = MAPPING_FIELDS
CANONICAL_SOURCE_FILES = {
    "benchmark_prices": {
        "relative_path": "sources/benchmark_prices.csv",
        "required": True,
        "columns": PRICE_COLUMNS,
        "purpose": "NDX exact or QQQ proxy benchmark prices",
    },
    "benchmark_mapping": {
        "relative_path": "sources/benchmark_mapping.csv",
        "required": True,
        "columns": MAPPING_COLUMNS,
        "purpose": "TQQQ/SQQQ target benchmark and QQQ proxy mapping",
    },
    "leveraged_etf_prices": {
        "relative_path": "sources/leveraged_etf_prices.csv",
        "required": False,
        "columns": PRICE_COLUMNS,
        "purpose": "TQQQ/SQQQ price reconciliation",
    },
    "aum_or_capital": {
        "relative_path": "sources/aum_or_capital.csv",
        "required": False,
        "columns": AUM_COLUMNS,
        "purpose": "AUM or shares times NAV rough scale",
    },
    "split_history": {
        "relative_path": "sources/split_history.csv",
        "required": False,
        "columns": SPLIT_COLUMNS,
        "purpose": "TQQQ/SQQQ split diagnostics",
    },
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def free_proxy_root(root: Path) -> Path:
    return root / "market_bomb_history" / "leveraged_etf_free_proxy_v1"


def input_dir(root: Path, input_id: str) -> Path:
    return free_proxy_root(root) / "input" / input_id


def historical_run_dir(root: Path, run_id: str) -> Path:
    return free_proxy_root(root) / "historical_runs" / run_id


def forward_ledger_root(root: Path) -> Path:
    return free_proxy_root(root) / "forward_ledger"


def safe_rel(base: Path, rel: str) -> Path:
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise SystemExit(f"unsafe relative path: {rel}")
    path = (base / rel_path).resolve()
    if not str(path).startswith(str(base.resolve())):
        raise SystemExit(f"path escapes base: {rel}")
    return path


def source_manifest_path(root: Path, input_id: str) -> Path:
    return input_dir(root, input_id) / "source_manifest.json"


def load_source_manifest(root: Path, input_id: str) -> dict[str, Any]:
    path = source_manifest_path(root, input_id)
    if not path.exists():
        raise SystemExit(f"missing source manifest: {path}")
    return load_json(path)


def manifest_sources(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    sources = manifest.get("sources", [])
    if not isinstance(sources, list):
        raise SystemExit("source_manifest.json sources must be a list")
    return sources


def source_by_dataset(sources: list[dict[str, Any]], dataset_type: str, instrument: str | None = None) -> dict[str, Any] | None:
    for source in sources:
        if str(source.get("dataset_type")) != dataset_type:
            continue
        if instrument is not None and str(source.get("instrument", "")).upper() != instrument.upper():
            continue
        return source
    return None


def read_source_csv(root: Path, input_id: str, source: dict[str, Any]) -> pd.DataFrame:
    path = safe_rel(input_dir(root, input_id), str(source.get("relative_path", "")))
    if not path.exists():
        raise SystemExit(f"missing source file: {source.get('relative_path')}")
    return pd.read_csv(path)


def mechanical_rebalance_notional(leverage: float, capital: float, benchmark_return: float) -> float:
    return leverage * (leverage - 1.0) * capital * benchmark_return


def equal_weight_direction(benchmark_return: float, minimum_abs_return: float = MIN_ABS_BENCHMARK_RETURN) -> int:
    if abs(benchmark_return) < minimum_abs_return:
        return 0
    return 1 if benchmark_return > 0 else -1


def amplifier_label(benchmark_return: float, minimum_abs_return: float = MIN_ABS_BENCHMARK_RETURN) -> str:
    direction = equal_weight_direction(benchmark_return, minimum_abs_return)
    if direction > 0:
        return "directional_amplifier_positive"
    if direction < 0:
        return "directional_amplifier_negative"
    return "directional_amplifier_neutral"


def validate_mapping_row(row: dict[str, Any], benchmark_mode: str = "ndx_exact") -> dict[str, Any]:
    missing = [field for field in MAPPING_FIELDS if field not in row or str(row.get(field, "")).strip() == ""]
    if missing:
        return {"mapping_status": "blocked_by_mapping", "blocking_reason": "missing_fields:" + ",".join(missing)}
    etf = str(row["leveraged_etf"]).upper()
    target = str(row["target_benchmark_instrument"]).upper()
    proxy = str(row["market_proxy_instrument"]).upper()
    exact_or_proxy = str(row["benchmark_exact_or_proxy"])
    if etf not in {"TQQQ", "SQQQ"}:
        return {"mapping_status": "blocked_by_mapping", "blocking_reason": "unsupported_leveraged_etf"}
    if proxy != "QQQ":
        return {"mapping_status": "blocked_by_mapping", "blocking_reason": "market_proxy_must_be_QQQ"}
    if truthy(row.get("is_proxy_underlying")):
        return {"mapping_status": "blocked_by_mapping", "blocking_reason": "qqq_cannot_be_silent_underlying"}
    if benchmark_mode == "ndx_exact":
        if target != "NDX":
            return {"mapping_status": "blocked_by_mapping", "blocking_reason": "target_benchmark_must_be_NDX"}
        if exact_or_proxy != "benchmark_exact":
            return {"mapping_status": "blocked_by_mapping", "blocking_reason": "ndx_mode_requires_benchmark_exact"}
    elif benchmark_mode == "qqq_proxy_only_descriptive":
        if target != "QQQ" and proxy != "QQQ":
            return {"mapping_status": "blocked_by_mapping", "blocking_reason": "qqq_proxy_mode_requires_QQQ"}
        if exact_or_proxy != "proxy_based":
            return {"mapping_status": "blocked_by_mapping", "blocking_reason": "qqq_proxy_mode_requires_proxy_based"}
    else:
        raise SystemExit(f"unsupported benchmark mode: {benchmark_mode}")
    return {"mapping_status": "valid", "blocking_reason": ""}


def validate_all_mappings(mapping: pd.DataFrame, benchmark_mode: str) -> pd.DataFrame:
    rows = []
    for _, row in mapping.iterrows():
        payload = row.to_dict()
        result = validate_mapping_row(payload, benchmark_mode)
        rows.append({**payload, **result})
    return pd.DataFrame(rows)


def build_template(root: Path, input_id: str) -> dict[str, Any]:
    base = input_dir(root, input_id)
    sources = base / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    templates = {
        "benchmark_prices.csv": PRICE_COLUMNS,
        "leveraged_etf_prices.csv": PRICE_COLUMNS,
        "aum_or_capital.csv": AUM_COLUMNS,
        "split_history.csv": SPLIT_COLUMNS,
        "benchmark_mapping.csv": MAPPING_COLUMNS,
    }
    for name, header in templates.items():
        path = sources / name
        if not path.exists():
            path.write_text(",".join(header) + "\n", encoding="utf-8")
    manifest_path = base / "source_manifest.json"
    if not manifest_path.exists():
        manifest = {
            "artifact_version": ARTIFACT_VERSION,
            "module_name": MODULE_NAME,
            "input_id": input_id,
            "research_only": True,
            "actionization_allowed": ACTIONIZATION_ALLOWED,
            "not_a_trading_signal": True,
            "sources": [],
            "template_note": "Populate sources manually. Do not commit raw provider files.",
        }
        write_json(manifest_path, manifest)
    return {"template_status": "created_or_existing", "input_id": input_id, "template_root": str(base)}


def csv_contract_status(path: Path, expected_columns: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {
            "present": False,
            "columns": [],
            "missing_required_headers": expected_columns,
            "extra_headers": [],
            "row_count": 0,
            "read_status": "missing",
        }
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return {
            "present": True,
            "columns": [],
            "missing_required_headers": expected_columns,
            "extra_headers": [],
            "row_count": 0,
            "read_status": "blocked",
            "read_error": str(exc),
        }
    columns = [str(col) for col in df.columns]
    return {
        "present": True,
        "columns": columns,
        "missing_required_headers": sorted(set(expected_columns) - set(columns)),
        "extra_headers": sorted(set(columns) - set(expected_columns)),
        "row_count": int(len(df)),
        "read_status": "readable",
    }


def detected_instruments(path: Path, date_column: str = "date") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    if "instrument" not in df.columns:
        return []
    rows: list[dict[str, Any]] = []
    for instrument, group in df.groupby(df["instrument"].astype(str).str.upper(), dropna=False):
        rows.append({
            "instrument": instrument,
            "rows": int(len(group)),
            "coverage_start": "" if date_column not in group.columns or group.empty else str(group[date_column].min()),
            "coverage_end": "" if date_column not in group.columns or group.empty else str(group[date_column].max()),
        })
    return rows


def manifest_entry_status(root: Path, input_id: str, source: dict[str, Any]) -> dict[str, Any]:
    rel = str(source.get("relative_path", ""))
    row = {
        "dataset_type": source.get("dataset_type", ""),
        "instrument": source.get("instrument", ""),
        "relative_path": rel,
        "declared_sha256": source.get("content_sha256", ""),
        "actual_sha256": "",
        "hash_status": "missing_source_file",
        "source_qualification_status": source.get("source_qualification_status", ""),
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "historical_vintage_available": truthy(source.get("historical_vintage_available")),
        "publication_timestamp_available": truthy(source.get("publication_timestamp_available")),
        "revision_history_available": truthy(source.get("revision_history_available")),
        "requires_human_provenance_completion": False,
    }
    if rel:
        try:
            path = safe_rel(input_dir(root, input_id), rel)
            if path.exists():
                actual = file_sha256(path)
                row["actual_sha256"] = actual
                row["hash_status"] = "match" if str(source.get("content_sha256")) == actual else "mismatch"
        except SystemExit:
            row["hash_status"] = "unsafe_relative_path"
    missing = ensure_required_source_fields(source)
    if missing:
        row["requires_human_provenance_completion"] = True
        row["missing_manifest_fields"] = ",".join(missing)
    return row


def mapping_mode_possible(mapping_path: Path, benchmark_mode: str) -> bool:
    if not mapping_path.exists():
        return False
    try:
        mapping = pd.read_csv(mapping_path)
    except Exception:
        return False
    if set(MAPPING_COLUMNS) - set(mapping.columns):
        return False
    validations = validate_all_mappings(mapping, benchmark_mode)
    required_etfs = {"TQQQ", "SQQQ"}
    if validations.empty:
        return False
    valid = validations[validations["mapping_status"].astype(str).eq("valid")]
    return required_etfs.issubset(set(valid["leveraged_etf"].astype(str).str.upper()))


def has_price_instrument(price_path: Path, instrument: str) -> bool:
    if not price_path.exists():
        return False
    try:
        prices = pd.read_csv(price_path)
    except Exception:
        return False
    if set(PRICE_COLUMNS) - set(prices.columns):
        return False
    return prices["instrument"].astype(str).str.upper().eq(instrument.upper()).any()


def manifest_descriptive_only(manifest_entries: list[dict[str, Any]]) -> bool:
    if not manifest_entries:
        return False
    for entry in manifest_entries:
        if str(entry.get("source_qualification_status")) != HISTORICAL_CONFIDENCE:
            return False
        if entry.get("historical_vintage_available") or entry.get("publication_timestamp_available") or entry.get("revision_history_available"):
            return False
        if entry.get("hash_status") != "match":
            return False
    return True


def inspect_input_contract(root: Path, input_id: str) -> dict[str, Any]:
    base = input_dir(root, input_id)
    files: list[dict[str, Any]] = []
    instruments: dict[str, list[dict[str, Any]]] = {}
    for dataset_type, spec in CANONICAL_SOURCE_FILES.items():
        rel = str(spec["relative_path"])
        path = base / rel
        status = csv_contract_status(path, list(spec["columns"]))
        files.append({
            "dataset_type": dataset_type,
            "relative_path": rel,
            "required": spec["required"],
            "purpose": spec["purpose"],
            **status,
        })
        date_col = "effective_date" if dataset_type == "split_history" else "date"
        instruments[dataset_type] = detected_instruments(path, date_col)
    manifest_path = source_manifest_path(root, input_id)
    manifest_entries: list[dict[str, Any]] = []
    manifest_status = "missing"
    manifest_required_fields_missing: list[str] = []
    if manifest_path.exists():
        try:
            manifest = load_json(manifest_path)
            manifest_status = "readable"
            for source in manifest_sources(manifest):
                manifest_entries.append(manifest_entry_status(root, input_id, source))
            for field in ["artifact_version", "module_name", "input_id", "sources"]:
                if field not in manifest:
                    manifest_required_fields_missing.append(field)
        except Exception as exc:
            manifest_status = "blocked"
            manifest_required_fields_missing.append(str(exc))
    by_dataset = {row["dataset_type"]: row for row in files}
    price_path = base / "sources" / "benchmark_prices.csv"
    mapping_path = base / "sources" / "benchmark_mapping.csv"
    aum_path = base / "sources" / "aum_or_capital.csv"
    split_path = base / "sources" / "split_history.csv"
    descriptive_ok = manifest_descriptive_only(manifest_entries)
    try:
        validation = validate_input(root, input_id)
        validation_status = validation.get("validation_status", "blocked")
    except SystemExit as exc:
        validation_status = "blocked"
        validation = {"diagnostics": [{"status": "blocked", "code": str(exc)}]}
    capabilities = {
        "ndx_exact_direction_possible": bool(
            descriptive_ok
            and validation_status == "valid"
            and has_price_instrument(price_path, "NDX")
            and mapping_mode_possible(mapping_path, "ndx_exact")
        ),
        "qqq_proxy_only_direction_possible": bool(
            descriptive_ok
            and validation_status == "valid"
            and has_price_instrument(price_path, "QQQ")
            and mapping_mode_possible(mapping_path, "qqq_proxy_only_descriptive")
        ),
        "aum_scaled_possible": bool(
            descriptive_ok
            and by_dataset["aum_or_capital"]["present"]
            and not by_dataset["aum_or_capital"]["missing_required_headers"]
            and any(row["instrument"] == "TQQQ" for row in instruments["aum_or_capital"])
            and any(row["instrument"] == "SQQQ" for row in instruments["aum_or_capital"])
        ),
        "split_diagnostics_possible": bool(
            by_dataset["split_history"]["present"]
            and not by_dataset["split_history"]["missing_required_headers"]
            and by_dataset["split_history"]["row_count"] > 0
        ),
        "forward_snapshot_ingestion_possible": bool(descriptive_ok and validation_status == "valid"),
    }
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "inspection_status": "completed",
        "canonical_layout": "market_bomb_history/leveraged_etf_free_proxy_v1/input/<input_id>/{source_manifest.json,sources/*.csv}",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "creates_run_artifact": False,
        "legacy_per_ticker_filenames_supported": False,
        "files": files,
        "manifest": {
            "relative_path": "source_manifest.json",
            "present": manifest_path.exists(),
            "read_status": manifest_status,
            "missing_top_level_fields": manifest_required_fields_missing,
            "entries": manifest_entries,
            "descriptive_only_status": "valid" if descriptive_ok else "incomplete_or_blocked",
        },
        "detected_instruments": instruments,
        "validation_status": validation_status,
        "validation_diagnostics": validation.get("diagnostics", []),
        "capabilities": capabilities,
    }


def ensure_required_source_fields(source: dict[str, Any]) -> list[str]:
    return [field for field in SOURCE_MANIFEST_FIELDS if field not in source]


def validate_input(root: Path, input_id: str) -> dict[str, Any]:
    manifest = load_source_manifest(root, input_id)
    sources = manifest_sources(manifest)
    diagnostics: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for source in sources:
        missing = ensure_required_source_fields(source)
        if missing:
            diagnostics.append({"status": "blocked", "code": "missing_source_manifest_fields", "source": source.get("relative_path", ""), "details": ",".join(missing)})
            continue
        rel = str(source["relative_path"])
        if rel in seen_paths:
            diagnostics.append({"status": "blocked", "code": "duplicate_source_path", "source": rel})
        seen_paths.add(rel)
        path = safe_rel(input_dir(root, input_id), rel)
        if not path.exists():
            diagnostics.append({"status": "blocked", "code": "missing_source_file", "source": rel})
            continue
        actual_hash = file_sha256(path)
        if str(source.get("content_sha256")) != actual_hash:
            diagnostics.append({"status": "blocked", "code": "content_sha256_mismatch", "source": rel})
        if str(source.get("source_qualification_status")) not in REQUIRED_HISTORY_STATUSES:
            diagnostics.append({"status": "blocked", "code": "free_proxy_requires_descriptive_status", "source": rel})
        if str(source.get("source_qualification_status")) in FORBIDDEN_STRICT_STATUSES:
            diagnostics.append({"status": "blocked", "code": "free_proxy_cannot_emit_strict_status", "source": rel})
        if truthy(source.get("historical_vintage_available")) or truthy(source.get("publication_timestamp_available")) or truthy(source.get("revision_history_available")):
            diagnostics.append({"status": "blocked", "code": "free_historical_input_cannot_claim_pit_gold", "source": rel})
    required = {"benchmark_prices", "benchmark_mapping"}
    present = {str(s.get("dataset_type")) for s in sources}
    for dataset in sorted(required - present):
        diagnostics.append({"status": "blocked", "code": "missing_required_dataset", "dataset_type": dataset})
    mapping_source = source_by_dataset(sources, "benchmark_mapping")
    mapping_validation: list[dict[str, Any]] = []
    if mapping_source:
        mapping = read_source_csv(root, input_id, mapping_source)
        missing_cols = set(MAPPING_COLUMNS) - set(mapping.columns)
        if missing_cols:
            diagnostics.append({"status": "blocked", "code": "mapping_missing_columns", "details": ",".join(sorted(missing_cols))})
        else:
            mapping_validation = [{"leveraged_etf": row.get("leveraged_etf", ""), "mapping_status": "schema_valid"} for _, row in mapping.iterrows()]
    tracked = tracked_market_bomb_history(root)
    if tracked:
        diagnostics.append({"status": "blocked", "code": "raw_provider_files_tracked", "details": ";".join(tracked)})
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "validation_status": "valid" if not diagnostics else "blocked",
        "diagnostics": diagnostics,
        "mapping_validation": mapping_validation,
        "research_only": True,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }


def tracked_market_bomb_history(root: Path) -> list[str]:
    try:
        out = subprocess.check_output(["git", "ls-files", "market_bomb_history"], cwd=root, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    return [line for line in out.splitlines() if line.strip()]


def benchmark_price_frame(root: Path, input_id: str, source: dict[str, Any], benchmark_mode: str) -> tuple[pd.DataFrame, str, str]:
    df = read_source_csv(root, input_id, source)
    missing = set(PRICE_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit("benchmark_prices missing columns: " + ",".join(sorted(missing)))
    instrument = "NDX" if benchmark_mode == "ndx_exact" else "QQQ"
    exact_or_proxy = "benchmark_exact" if benchmark_mode == "ndx_exact" else "proxy_based"
    work = df[df["instrument"].astype(str).str.upper().eq(instrument)].copy()
    if work.empty:
        raise SystemExit(f"missing benchmark instrument {instrument}")
    if work["raw_or_adjusted"].astype(str).nunique() != 1:
        raise SystemExit("raw_adjusted_basis_mixed")
    work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    work["raw_close"] = pd.to_numeric(work["raw_close"], errors="coerce")
    work = work.sort_values("date")
    work["lagged_capital_date"] = work["date"].shift(1)
    work["benchmark_return"] = work["raw_close"].pct_change()
    return work.dropna(subset=["benchmark_return"]), instrument, exact_or_proxy


def aum_frame(root: Path, input_id: str, source: dict[str, Any] | None) -> pd.DataFrame:
    if source is None:
        return pd.DataFrame(columns=AUM_COLUMNS)
    df = read_source_csv(root, input_id, source)
    missing = set(AUM_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit("aum_or_capital missing columns: " + ",".join(sorted(missing)))
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    work["aum_usd"] = pd.to_numeric(work["aum_usd"], errors="coerce")
    work["shares_outstanding"] = pd.to_numeric(work["shares_outstanding"], errors="coerce")
    work["nav_per_share"] = pd.to_numeric(work["nav_per_share"], errors="coerce")
    return work


def capital_for_date(aum: pd.DataFrame, etf: str, date: str) -> tuple[float | None, str]:
    if aum.empty:
        return None, "aum_scale_unavailable"
    rows = aum[(aum["instrument"].astype(str).str.upper().eq(etf)) & (aum["date"].astype(str).eq(date))].copy()
    if rows.empty:
        return None, "aum_scale_unavailable"
    row = rows.iloc[-1]
    if str(row.get("unit", "")).upper() not in {"USD", ""}:
        return None, "unit_mismatch"
    aum_usd = row.get("aum_usd")
    if pd.notna(aum_usd):
        return float(aum_usd), "aum_usd"
    if pd.notna(row.get("shares_outstanding")) and pd.notna(row.get("nav_per_share")):
        return float(row["shares_outstanding"]) * float(row["nav_per_share"]), "shares_times_nav"
    return None, "aum_scale_unavailable"


def aum_coverage_rows(aum: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for etf in ["TQQQ", "SQQQ"]:
        group = aum[aum["instrument"].astype(str).str.upper().eq(etf)] if not aum.empty else pd.DataFrame()
        rows.append({
            "instrument": etf,
            "rows": int(len(group)),
            "coverage_start": "" if group.empty else str(group["date"].min()),
            "coverage_end": "" if group.empty else str(group["date"].max()),
            "aum_scale_status": "available" if not group.empty else "aum_scale_unavailable",
        })
    return rows


def price_basis_rows(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source in sources:
        if str(source.get("dataset_type")) in {"benchmark_prices", "leveraged_etf_prices"}:
            rows.append({
                "dataset_type": source.get("dataset_type", ""),
                "instrument": source.get("instrument", ""),
                "raw_or_adjusted": source.get("raw_or_adjusted", ""),
                "corporate_action_treatment": source.get("corporate_action_treatment", ""),
                "price_basis_status": "valid" if str(source.get("raw_or_adjusted")) in {"raw", "adjusted", "raw_and_adjusted_separate"} else "blocked",
            })
    return rows


def split_rows(root: Path, input_id: str, source: dict[str, Any] | None) -> list[dict[str, Any]]:
    if source is None:
        return [{"instrument": "TQQQ/SQQQ", "split_reconciliation_status": "split_reconciliation_incomplete", "details": "missing split_history source"}]
    df = read_source_csv(root, input_id, source)
    if set(SPLIT_COLUMNS) - set(df.columns):
        return [{"instrument": "TQQQ/SQQQ", "split_reconciliation_status": "split_reconciliation_incomplete", "details": "missing split columns"}]
    return [{"instrument": row.get("instrument", ""), "effective_date": row.get("effective_date", ""), "split_reconciliation_status": "documented", "details": ""} for _, row in df.iterrows()]


def source_manifest_hash(root: Path, input_id: str) -> str:
    return file_sha256(source_manifest_path(root, input_id))


def run_historical(root: Path, input_id: str, benchmark_mode: str) -> dict[str, Any]:
    validation = validate_input(root, input_id)
    if validation["validation_status"] != "valid":
        raise SystemExit("free_proxy_input_validation_blocked")
    manifest = load_source_manifest(root, input_id)
    sources = manifest_sources(manifest)
    if benchmark_mode not in {"ndx_exact", "qqq_proxy_only_descriptive"}:
        raise SystemExit("invalid_benchmark_mode")
    mapping_source = source_by_dataset(sources, "benchmark_mapping")
    if mapping_source is None:
        raise SystemExit("missing_benchmark_mapping")
    mapping = read_source_csv(root, input_id, mapping_source)
    mapping_validation = validate_all_mappings(mapping, benchmark_mode)
    if mapping_validation.empty or mapping_validation["mapping_status"].astype(str).ne("valid").any():
        raise SystemExit("benchmark_mapping_invalid")
    price_source = source_by_dataset(sources, "benchmark_prices")
    if price_source is None:
        raise SystemExit("missing_benchmark_prices")
    benchmark, benchmark_instrument, exact_or_proxy = benchmark_price_frame(root, input_id, price_source, benchmark_mode)
    aum = aum_frame(root, input_id, source_by_dataset(sources, "aum_or_capital"))
    run_id = f"{utc_now_compact()}_{bytes_sha256((input_id + benchmark_mode + str(uuid.uuid4())).encode())[:12]}"
    out = historical_run_dir(root, run_id)
    if out.exists():
        raise SystemExit("free_proxy_run_artifact_not_immutable")
    out.mkdir(parents=True, exist_ok=False)
    manifest_hash = source_manifest_hash(root, input_id)
    daily_rows: list[dict[str, Any]] = []
    for _, row in benchmark.iterrows():
        date = str(row["date"])
        lag_date = str(row.get("lagged_capital_date", ""))
        ret = float(row["benchmark_return"])
        direction = equal_weight_direction(ret)
        tqqq_cap, tqqq_source = capital_for_date(aum, "TQQQ", lag_date)
        sqqq_cap, sqqq_source = capital_for_date(aum, "SQQQ", lag_date)
        tqqq_notional = mechanical_rebalance_notional(3.0, tqqq_cap, ret) if tqqq_cap is not None else ""
        sqqq_notional = mechanical_rebalance_notional(-3.0, sqqq_cap, ret) if sqqq_cap is not None else ""
        combined = tqqq_notional + sqqq_notional if isinstance(tqqq_notional, float) and isinstance(sqqq_notional, float) else ""
        confidence = HISTORICAL_CONFIDENCE if exact_or_proxy == "benchmark_exact" else PROXY_CONFIDENCE
        daily_rows.append({
            "observation_date": date,
            "benchmark_instrument": benchmark_instrument,
            "benchmark_exact_or_proxy": exact_or_proxy,
            "benchmark_return": ret,
            "minimum_absolute_benchmark_return_for_direction": MIN_ABS_BENCHMARK_RETURN,
            "tqqq_aum_input_available": tqqq_cap is not None,
            "sqqq_aum_input_available": sqqq_cap is not None,
            "tqqq_lagged_aum_or_capital": "" if tqqq_cap is None else tqqq_cap,
            "sqqq_lagged_aum_or_capital": "" if sqqq_cap is None else sqqq_cap,
            "tqqq_capital_source": tqqq_source,
            "sqqq_capital_source": sqqq_source,
            "tqqq_rebalance_notional_proxy": tqqq_notional,
            "sqqq_rebalance_notional_proxy": sqqq_notional,
            "combined_aum_scaled_rebalance_notional_proxy": combined,
            "equal_weight_directional_proxy": direction,
            "directional_amplifier_label": amplifier_label(ret),
            "confidence_label": confidence,
            "mode": HISTORICAL_MODE,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
            "model_assumption_set": MODEL_ASSUMPTION_SET,
            "source_manifest_hash": manifest_hash,
            "run_id": run_id,
        })
    write_json(out / "free_proxy_input_validation_report.json", validation)
    write_csv(out / "benchmark_mapping_validation.csv", mapping_validation.to_dict("records"))
    write_json(out / "benchmark_mapping_validation.json", {"benchmark_mode": benchmark_mode, "rows": mapping_validation.to_dict("records")})
    write_csv(out / "price_basis_validation.csv", price_basis_rows(sources))
    write_csv(out / "split_reconciliation_report.csv", split_rows(root, input_id, source_by_dataset(sources, "split_history")))
    write_csv(out / "aum_input_coverage.csv", aum_coverage_rows(aum))
    write_csv(out / "leveraged_etf_free_proxy_daily.csv", daily_rows)
    summary = historical_summary(run_id, input_id, benchmark_mode, daily_rows)
    (out / "leveraged_etf_free_proxy_summary.md").write_text(summary, encoding="utf-8")
    (out / "historical_descriptive_limitations.md").write_text(historical_limitations_md(), encoding="utf-8")
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "run_id": run_id,
        "input_id": input_id,
        "mode": HISTORICAL_MODE,
        "benchmark_mode": benchmark_mode,
        "research_only": True,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "not_a_trading_signal": True,
        "not_market_impact_estimate": True,
        "not_dealer_inventory_estimate": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "phase1_3_readiness_run": False,
        "phase2_run": False,
        "release_created": False,
        "backtest_run": False,
    }
    write_json(out / "free_proxy_run_receipt.json", receipt)
    write_json(out / "free_proxy_content_manifest.json", build_content_manifest(out, run_id))
    return {"run_status": "completed", "run_id": run_id, "run_artifact": str(out), **receipt}


def historical_summary(run_id: str, input_id: str, benchmark_mode: str, daily_rows: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in daily_rows:
        counts[str(row["directional_amplifier_label"])] = counts.get(str(row["directional_amplifier_label"]), 0) + 1
    return "\n".join([
        "# Leveraged ETF Free Directional Proxy Summary",
        "",
        f"- module_name: `{MODULE_NAME}`",
        f"- run_id: `{run_id}`",
        f"- input_id: `{input_id}`",
        f"- mode: `{HISTORICAL_MODE}`",
        f"- benchmark_mode: `{benchmark_mode}`",
        "- predictive_pit_eligible: `false`",
        "- phase2_eligible: `false`",
        "- actionization_allowed: `false`",
        "- not_a_trading_signal: `true`",
        "",
        "This module is research context only. It must not be used as a standalone buy/sell signal.",
        "",
        f"Directional label counts: `{counts}`",
    ]) + "\n"


def historical_limitations_md() -> str:
    return """# Historical Descriptive Limitations

This free historical proxy is descriptive only.

It does not observe actual creation/redemption flow, intraday subscriptions or redemptions, AP activity, manager execution timing, cash balances, derivatives usage, tracking error, fees, corporate actions, or market-maker hedging.

Current downloaded history cannot prove when each historical row was first available. Today's download time, file modification time, current web-page timestamp, or assumed NAV calculation time must not become a historical `available_at_timestamp`.

The output cannot unlock strict Phase 1.3 readiness, Phase 2 admission, release builds, statistical backtests, notifications, trading, sizing, execution, or actionization.
"""


def build_content_manifest(out_dir: Path, run_id: str) -> dict[str, Any]:
    files = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name not in {"free_proxy_content_manifest.json", "forward_ledger_content_manifest.json"}:
            files.append({"relative_path": path.relative_to(out_dir).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "run_id": run_id,
        "content_set_hash": bytes_sha256(json_dumps(files).encode("utf-8")),
        "files": files,
    }


def verify_manifested_dir(run_artifact: Path, manifest_name: str) -> dict[str, Any]:
    manifest_path = run_artifact / manifest_name
    if not manifest_path.exists():
        raise SystemExit(f"missing manifest: {manifest_name}")
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
    extra = sorted(set(actual) - set(expected))
    for rel in extra:
        failures.append({"relative_path": rel, "reason": "extra_file"})
    return {"verification_status": "valid" if not failures else "tampered", "failures": failures, "run_artifact": str(run_artifact)}


def verify_run(run_artifact: str) -> dict[str, Any]:
    path = Path(run_artifact).resolve()
    result = verify_manifested_dir(path, "free_proxy_content_manifest.json")
    receipt = load_json(path / "free_proxy_run_receipt.json")
    required_false = ["actionization_allowed", "predictive_pit_eligible", "phase2_eligible", "phase1_3_readiness_run", "phase2_run", "release_created", "backtest_run"]
    for field in required_false:
        if receipt.get(field) is not False:
            result.setdefault("failures", []).append({"relative_path": "free_proxy_run_receipt.json", "reason": f"{field}_must_be_false"})
            result["verification_status"] = "tampered"
    return result


def ingest_forward_snapshot(root: Path, input_id: str, snapshot_date: str, capture_timestamp_utc: str) -> dict[str, Any]:
    manifest = load_source_manifest(root, input_id)
    sources = manifest_sources(manifest)
    if not capture_timestamp_utc.endswith("Z"):
        raise SystemExit("capture_timestamp_utc_must_be_utc_z")
    snapshot_id = f"{snapshot_date}_{input_id}"
    out = forward_ledger_root(root) / "snapshots" / snapshot_id
    source_entries = []
    for source in sources:
        path = safe_rel(input_dir(root, input_id), str(source.get("relative_path", "")))
        source_entries.append({
            "dataset_type": source.get("dataset_type", ""),
            "instrument": source.get("instrument", ""),
            "relative_path": source.get("relative_path", ""),
            "local_file_content_sha256": file_sha256(path) if path.exists() else "",
            "source_file_name": path.name,
        })
    payload = {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "snapshot_id": snapshot_id,
        "snapshot_date": snapshot_date,
        "capture_timestamp_utc": capture_timestamp_utc,
        "operator_capture_method": manifest.get("operator_capture_method", "manual_local_file"),
        "sources": source_entries,
        "mode": FORWARD_MODE,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    serialized = json_dumps(payload)
    if out.exists():
        existing = out / "forward_snapshot_receipt.json"
        if existing.exists() and existing.read_text(encoding="utf-8") != serialized:
            raise SystemExit("duplicate_snapshot_id_with_different_hash")
        return {"snapshot_status": "already_exists", "snapshot_id": snapshot_id, "snapshot_artifact": str(out)}
    out.mkdir(parents=True, exist_ok=False)
    (out / "forward_snapshot_receipt.json").write_text(serialized, encoding="utf-8")
    write_json(out / "forward_snapshot_manifest.json", build_content_manifest(out, snapshot_id))
    return {"snapshot_status": "ingested", "snapshot_id": snapshot_id, "snapshot_artifact": str(out)}


def latest_snapshot_before(root: Path, observation_date: str) -> dict[str, Any] | None:
    snap_root = forward_ledger_root(root) / "snapshots"
    if not snap_root.exists():
        return None
    eligible = []
    for receipt in snap_root.glob("*/forward_snapshot_receipt.json"):
        payload = load_json(receipt)
        if str(payload.get("snapshot_date", "")) < observation_date:
            eligible.append(payload)
    if not eligible:
        return None
    return sorted(eligible, key=lambda x: str(x.get("snapshot_date", "")))[-1]


def build_forward_observation(root: Path, observation_date: str) -> dict[str, Any]:
    snapshot = latest_snapshot_before(root, observation_date)
    obs_root = forward_ledger_root(root) / "observations"
    obs_root.mkdir(parents=True, exist_ok=True)
    observation_id = f"{observation_date}_{bytes_sha256((observation_date + str(uuid.uuid4())).encode())[:8]}"
    ledger_path = obs_root / "forward_observation_ledger.csv"
    if snapshot is None:
        row = unavailable_forward_row(observation_id, observation_date, "missing_prior_snapshot")
    else:
        input_id = str(snapshot.get("input_id", ""))
        try:
            result = run_forward_from_snapshot(root, input_id, observation_id, observation_date, snapshot)
            row = result
        except SystemExit:
            row = unavailable_forward_row(observation_id, observation_date, "lineage_unavailable")
    existing: list[dict[str, Any]] = []
    if ledger_path.exists():
        existing = pd.read_csv(ledger_path).to_dict("records")
    existing.append(row)
    write_csv(ledger_path, existing)
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "observation_id": observation_id,
        "observation_date": observation_date,
        "mode": FORWARD_MODE,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    write_json(obs_root / "forward_observation_receipt.json", receipt)
    write_json(forward_ledger_root(root) / "forward_ledger_content_manifest.json", build_content_manifest(forward_ledger_root(root), "forward_ledger"))
    return {"observation_status": "written", "observation_id": observation_id, "ledger_path": str(ledger_path)}


def unavailable_forward_row(observation_id: str, observation_date: str, reason: str) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "observation_date": observation_date,
        "decision_cutoff_timestamp_utc": "",
        "benchmark_instrument": "",
        "benchmark_exact_or_proxy": "",
        "benchmark_return": "",
        "lagged_capital_snapshot_date": "",
        "lagged_capital_capture_timestamp_utc": "",
        "lagged_capital_source_hash": "",
        "tqqq_capital_input": "",
        "sqqq_capital_input": "",
        "tqqq_proxy_notional": "",
        "sqqq_proxy_notional": "",
        "combined_proxy_notional": "",
        "equal_weight_direction": 0,
        "directional_amplifier_label": "directional_amplifier_unavailable",
        "confidence_label": INPUT_UNAVAILABLE,
        "mode": FORWARD_MODE,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "unavailable_reason": reason,
    }


def run_forward_from_snapshot(root: Path, input_id: str, observation_id: str, observation_date: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    manifest = load_source_manifest(root, input_id)
    sources = manifest_sources(manifest)
    price_source = source_by_dataset(sources, "benchmark_prices")
    if price_source is None:
        raise SystemExit("missing_benchmark_prices")
    benchmark, instrument, exact_or_proxy = benchmark_price_frame(root, input_id, price_source, "ndx_exact")
    row = benchmark[benchmark["date"].astype(str).eq(observation_date)]
    if row.empty:
        raise SystemExit("missing_observation_benchmark_return")
    aum = aum_frame(root, input_id, source_by_dataset(sources, "aum_or_capital"))
    lag_date = str(snapshot["snapshot_date"])
    ret = float(row.iloc[-1]["benchmark_return"])
    tqqq_cap, _ = capital_for_date(aum, "TQQQ", lag_date)
    sqqq_cap, _ = capital_for_date(aum, "SQQQ", lag_date)
    if tqqq_cap is None or sqqq_cap is None:
        return unavailable_forward_row(observation_id, observation_date, "missing_prior_capital_snapshot")
    tqqq = mechanical_rebalance_notional(3.0, tqqq_cap, ret)
    sqqq = mechanical_rebalance_notional(-3.0, sqqq_cap, ret)
    hash_value = bytes_sha256(json_dumps(snapshot.get("sources", [])).encode("utf-8"))
    return {
        "observation_id": observation_id,
        "observation_date": observation_date,
        "decision_cutoff_timestamp_utc": snapshot.get("capture_timestamp_utc", ""),
        "benchmark_instrument": instrument,
        "benchmark_exact_or_proxy": exact_or_proxy,
        "benchmark_return": ret,
        "lagged_capital_snapshot_date": lag_date,
        "lagged_capital_capture_timestamp_utc": snapshot.get("capture_timestamp_utc", ""),
        "lagged_capital_source_hash": hash_value,
        "tqqq_capital_input": tqqq_cap,
        "sqqq_capital_input": sqqq_cap,
        "tqqq_proxy_notional": tqqq,
        "sqqq_proxy_notional": sqqq,
        "combined_proxy_notional": tqqq + sqqq,
        "equal_weight_direction": equal_weight_direction(ret),
        "directional_amplifier_label": amplifier_label(ret),
        "confidence_label": FORWARD_CONFIDENCE,
        "mode": FORWARD_MODE,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "unavailable_reason": "",
    }


def verify_forward_ledger(ledger_root: str) -> dict[str, Any]:
    root = Path(ledger_root).resolve()
    manifest_path = root / "forward_ledger_content_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("missing forward ledger content manifest")
    result = verify_manifested_dir(root, "forward_ledger_content_manifest.json")
    obs = root / "observations" / "forward_observation_ledger.csv"
    if obs.exists():
        df = pd.read_csv(obs)
        for col in ["predictive_pit_eligible", "phase2_eligible", "actionization_allowed"]:
            if col in df.columns and df[col].astype(str).str.lower().ne("false").any():
                result["verification_status"] = "tampered"
                result.setdefault("failures", []).append({"relative_path": "observations/forward_observation_ledger.csv", "reason": f"{col}_must_be_false"})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=MODULE_NAME)
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build-leveraged-etf-free-proxy-template")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("validate-leveraged-etf-free-proxy-input")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("inspect-leveraged-etf-free-proxy-input-contract")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("run-leveraged-etf-free-proxy-historical")
    p.add_argument("--input-id", required=True)
    p.add_argument("--benchmark-mode", choices=["ndx_exact", "qqq_proxy_only_descriptive"], required=True)
    p = sub.add_parser("ingest-leveraged-etf-free-proxy-forward-snapshot")
    p.add_argument("--input-id", required=True)
    p.add_argument("--snapshot-date", required=True)
    p.add_argument("--capture-timestamp-utc", required=True)
    p = sub.add_parser("build-leveraged-etf-free-proxy-forward-observation")
    p.add_argument("--observation-date", required=True)
    p = sub.add_parser("verify-leveraged-etf-free-proxy-run")
    p.add_argument("--run-artifact", required=True)
    p = sub.add_parser("verify-leveraged-etf-free-proxy-forward-ledger")
    p.add_argument("--ledger-root", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.command == "build-leveraged-etf-free-proxy-template":
        result = build_template(root, args.input_id)
    elif args.command == "validate-leveraged-etf-free-proxy-input":
        result = validate_input(root, args.input_id)
    elif args.command == "inspect-leveraged-etf-free-proxy-input-contract":
        result = inspect_input_contract(root, args.input_id)
    elif args.command == "run-leveraged-etf-free-proxy-historical":
        result = run_historical(root, args.input_id, args.benchmark_mode)
    elif args.command == "ingest-leveraged-etf-free-proxy-forward-snapshot":
        result = ingest_forward_snapshot(root, args.input_id, args.snapshot_date, args.capture_timestamp_utc)
    elif args.command == "build-leveraged-etf-free-proxy-forward-observation":
        result = build_forward_observation(root, args.observation_date)
    elif args.command == "verify-leveraged-etf-free-proxy-run":
        result = verify_run(args.run_artifact)
    elif args.command == "verify-leveraged-etf-free-proxy-forward-ledger":
        result = verify_forward_ledger(args.ledger_root)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    print(json_dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
