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


MODULE_NAME = "vol_control_transparent_replication_v1"
ARTIFACT_VERSION = "vol_control_transparent_replication_v1_0_0"
HISTORICAL_MODE = "historical_descriptive_vol_control_replication"
HISTORICAL_CONFIDENCE = "historical_descriptive_only"
ACTIONIZATION_ALLOWED = False
UNCHANGED_LABEL = "unchanged"
INCREASE_LABEL = "increase_risk"
REDUCE_LABEL = "reduce_risk"
UNAVAILABLE_LABEL = "input_unavailable"
FORBIDDEN_STRICT_STATUSES = {
    "gold_point_in_time_eligible",
    "silver_documented_schedule_eligible",
    "ready_for_eod_next_session_research",
}

PRICE_COLUMNS = ["date", "instrument", "raw_close", "raw_or_adjusted"]
SCHEDULE_COLUMNS = ["observation_date", "effective_session", "decision_timestamp_utc", "session_source"]
REFERENCE_COLUMNS = [
    "date",
    "reference_id",
    "reference_exposure",
    "reference_source_authority",
    "reference_methodology_version",
    "available_timestamp_utc",
]
COT_COLUMNS = [
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
    "benchmark_prices": {"relative_path": "sources/benchmark_prices.csv", "columns": PRICE_COLUMNS, "required": True},
    "decision_schedule": {"relative_path": "sources/decision_schedule.csv", "columns": SCHEDULE_COLUMNS, "required": True},
    "reference_exposure": {"relative_path": "sources/reference_exposure.csv", "columns": REFERENCE_COLUMNS, "required": False},
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


def vc_root(root: Path) -> Path:
    return root / "market_bomb_history" / "vol_control_research_v1"


def input_dir(root: Path, input_id: str) -> Path:
    return vc_root(root) / "input" / input_id


def source_manifest_path(root: Path, input_id: str) -> Path:
    return input_dir(root, input_id) / "source_manifest.json"


def historical_run_dir(root: Path, run_id: str) -> Path:
    return vc_root(root) / "historical_runs" / run_id


def config_path(root: Path) -> Path:
    return root / "config" / "vol_control_research_v1" / "model_specs.json"


def safe_rel(base: Path, rel: str) -> Path:
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise SystemExit(f"unsafe relative path: {rel}")
    resolved_base = base.resolve()
    path = (base / rel_path).resolve()
    if not str(path).startswith(str(resolved_base)):
        raise SystemExit(f"path escapes base: {rel}")
    return path


def tracked_vol_control_history(root: Path) -> list[str]:
    try:
        out = subprocess.check_output(["git", "ls-files", "market_bomb_history/vol_control_research_v1"], cwd=root, text=True, stderr=subprocess.DEVNULL)
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


def build_template(root: Path, input_id: str) -> dict[str, Any]:
    base = input_dir(root, input_id)
    sources = base / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    for spec in CANONICAL_FILES.values():
        path = base / str(spec["relative_path"])
        if not path.exists():
            path.write_text(",".join(spec["columns"]) + "\n", encoding="utf-8")
    manifest_path = base / "source_manifest.json"
    if not manifest_path.exists():
        write_json(
            manifest_path,
            {
                "artifact_version": ARTIFACT_VERSION,
                "module_name": MODULE_NAME,
                "input_id": input_id,
                "research_only": True,
                "actionization_allowed": ACTIONIZATION_ALLOWED,
                "not_a_trading_signal": True,
                "sources": [],
                "template_note": "Populate sources manually. Do not commit raw provider files.",
            },
        )
    return {"template_status": "created_or_existing", "input_id": input_id, "template_root": str(base)}


def build_cot_template(root: Path, input_id: str) -> dict[str, Any]:
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
    missing = [field for field in SOURCE_MANIFEST_FIELDS if field not in source]
    row["missing_manifest_fields"] = ",".join(missing)
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
        "research_only": True,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "files": files,
        "manifest": {"present": manifest_path.exists(), "read_status": manifest_status, "entries": entries},
        "validation_status": validation["validation_status"],
        "validation_diagnostics": validation["diagnostics"],
    }


def inspect_cot_sanity_input(root: Path, input_id: str) -> dict[str, Any]:
    path = input_dir(root, input_id) / "sources" / "cot_weekly.csv"
    status = csv_status(path, COT_COLUMNS)
    rows = []
    if status["present"] and status["read_status"] == "readable":
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            pos = pd.to_datetime(row.get("position_as_of_date"), utc=True, errors="coerce")
            pub = pd.to_datetime(row.get("publication_timestamp_utc"), utc=True, errors="coerce")
            avail = pd.to_datetime(row.get("available_timestamp_utc"), utc=True, errors="coerce")
            rows.append(
                {
                    "market_name": row.get("market_name", ""),
                    "reporting_group": row.get("reporting_group", ""),
                    "cot_is_not_vol_control_ground_truth": True,
                    "daily_validation_allowed": False,
                    "position_as_of_is_publication_time": bool(pd.notna(pos) and pd.notna(pub) and pos == pub),
                    "timing_fields_present": bool(pd.notna(pos) and pd.notna(pub) and pd.notna(avail)),
                }
            )
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "inspection_status": "completed",
        "creates_run_artifact": False,
        "cot_is_not_vol_control_ground_truth": True,
        "weekly_sanity_check_only": True,
        "daily_validation_allowed": False,
        "file": status,
        "rows": rows,
    }


def validate_input(root: Path, input_id: str, raise_on_missing: bool = True) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    try:
        manifest = load_source_manifest(root, input_id)
        sources = manifest_sources(manifest)
    except SystemExit as exc:
        if raise_on_missing:
            raise
        return base_validation(input_id, [{"status": "blocked", "code": str(exc)}])
    seen_paths: set[str] = set()
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
            diagnostics.append({"status": "blocked", "code": "vol_control_requires_descriptive_status", "source": rel})
        if str(source.get("source_qualification_status")) in FORBIDDEN_STRICT_STATUSES:
            diagnostics.append({"status": "blocked", "code": "vol_control_cannot_emit_strict_status", "source": rel})
        if truthy(source.get("historical_vintage_available")) or truthy(source.get("publication_timestamp_available")) or truthy(source.get("revision_history_available")):
            diagnostics.append({"status": "blocked", "code": "manual_history_cannot_claim_pit_gold", "source": rel})
    present = {str(s.get("dataset_type")) for s in sources}
    for required in ["benchmark_prices", "decision_schedule"]:
        if required not in present:
            diagnostics.append({"status": "blocked", "code": "missing_required_dataset", "dataset_type": required})
    price_source = source_by_dataset(sources, "benchmark_prices")
    price_df: pd.DataFrame | None = None
    if price_source:
        price_path = safe_rel(input_dir(root, input_id), str(price_source.get("relative_path", "")))
        if price_path.exists():
            price_df = read_source_csv(root, input_id, price_source)
            diagnostics.extend(validate_prices(price_df))
    schedule_source = source_by_dataset(sources, "decision_schedule")
    if schedule_source:
        schedule_path = safe_rel(input_dir(root, input_id), str(schedule_source.get("relative_path", "")))
        if not schedule_path.exists():
            return base_validation(input_id, diagnostics)
        schedule = read_source_csv(root, input_id, schedule_source)
        diagnostics.extend(validate_schedule(schedule))
        if price_df is not None:
            diagnostics.extend(validate_schedule_price_join(price_df, schedule))
    tracked = tracked_vol_control_history(root)
    if tracked:
        diagnostics.append({"status": "blocked", "code": "raw_provider_files_tracked", "details": ";".join(tracked)})
    return base_validation(input_id, diagnostics)


def base_validation(input_id: str, diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "validation_status": "valid" if not diagnostics else "blocked",
        "diagnostics": diagnostics,
        "research_only": True,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "not_a_trading_signal": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }


def validate_prices(df: pd.DataFrame) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    missing = set(PRICE_COLUMNS) - set(df.columns)
    if missing:
        return [{"status": "blocked", "code": "benchmark_prices_missing_columns", "details": ",".join(sorted(missing))}]
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work["raw_close"] = pd.to_numeric(work["raw_close"], errors="coerce")
    if work["date"].isna().any() or work["raw_close"].isna().any() or work["raw_close"].le(0).any():
        diagnostics.append({"status": "blocked", "code": "invalid_benchmark_price_row"})
    if work.duplicated(["date", "instrument"]).any():
        diagnostics.append({"status": "blocked", "code": "duplicate_benchmark_price_key"})
    for instrument, group in work.groupby(work["instrument"].astype(str).str.upper(), dropna=False):
        if group["raw_or_adjusted"].astype(str).nunique() > 1:
            diagnostics.append({"status": "blocked", "code": "mixed_raw_adjusted_basis", "instrument": str(instrument)})
        dates = pd.to_datetime(group["date"], errors="coerce")
        if not dates.is_monotonic_increasing and list(dates) != list(dates.sort_values()):
            diagnostics.append({"status": "blocked", "code": "benchmark_dates_not_strictly_increasing", "instrument": str(instrument)})
    return diagnostics


def validate_schedule(df: pd.DataFrame) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    missing = set(SCHEDULE_COLUMNS) - set(df.columns)
    if missing:
        return [{"status": "blocked", "code": "decision_schedule_missing_columns", "details": ",".join(sorted(missing))}]
    work = df.copy()
    obs = pd.to_datetime(work["observation_date"], errors="coerce")
    eff = pd.to_datetime(work["effective_session"], errors="coerce")
    dec = pd.to_datetime(work["decision_timestamp_utc"], utc=True, errors="coerce")
    if obs.isna().any() or eff.isna().any() or dec.isna().any():
        diagnostics.append({"status": "blocked", "code": "decision_schedule_bad_datetime"})
    if (eff <= obs).any():
        diagnostics.append({"status": "blocked", "code": "same_day_or_prior_effective_session"})
    if work["observation_date"].duplicated().any():
        diagnostics.append({"status": "blocked", "code": "duplicate_decision_schedule_observation"})
    return diagnostics


def validate_schedule_price_join(prices: pd.DataFrame, schedule: pd.DataFrame) -> list[dict[str, Any]]:
    price_dates = set(pd.to_datetime(prices["date"], errors="coerce").dt.strftime("%Y-%m-%d"))
    schedule_dates = set(pd.to_datetime(schedule["observation_date"], errors="coerce").dt.strftime("%Y-%m-%d"))
    missing = sorted(schedule_dates - price_dates)
    if missing:
        return [{"status": "blocked", "code": "schedule_observation_missing_price", "details": ",".join(missing[:10])}]
    return []


def load_model_specs(root: Path) -> tuple[dict[str, Any], str]:
    path = config_path(root)
    if not path.exists():
        raise SystemExit(f"missing model spec registry: {path}")
    payload = load_json(path)
    return payload, file_sha256(path)


def get_model_spec(root: Path, model_spec_id: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    registry, registry_hash = load_model_specs(root)
    specs = registry.get("model_specs", [])
    for spec in specs:
        if str(spec.get("model_spec_id")) == model_spec_id:
            return registry, spec, registry_hash
    raise SystemExit(f"unknown model_spec_id: {model_spec_id}")


def selected_instrument(benchmark_mode: str) -> tuple[str, str]:
    if benchmark_mode == "ndx_exact_descriptive":
        return "NDX", "benchmark_exact"
    if benchmark_mode == "qqq_proxy_only_descriptive":
        return "QQQ", "proxy_only"
    raise SystemExit(f"unsupported benchmark mode: {benchmark_mode}")


def prepare_prices(root: Path, input_id: str, benchmark_mode: str) -> pd.DataFrame:
    manifest = load_source_manifest(root, input_id)
    source = source_by_dataset(manifest_sources(manifest), "benchmark_prices")
    if source is None:
        raise SystemExit("missing_benchmark_prices")
    instrument, _ = selected_instrument(benchmark_mode)
    df = read_source_csv(root, input_id, source)
    missing = set(PRICE_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit("benchmark_prices_missing_columns:" + ",".join(sorted(missing)))
    work = df.copy()
    work["instrument"] = work["instrument"].astype(str).str.upper()
    work = work[work["instrument"].eq(instrument)].copy()
    if work.empty:
        raise SystemExit(f"missing_benchmark_instrument:{instrument}")
    if work["raw_or_adjusted"].astype(str).nunique() != 1:
        raise SystemExit("mixed_raw_adjusted_basis")
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work["raw_close"] = pd.to_numeric(work["raw_close"], errors="coerce")
    work = work.sort_values("date")
    work["benchmark_return"] = work["raw_close"].pct_change()
    return work


def prepare_schedule(root: Path, input_id: str) -> pd.DataFrame:
    manifest = load_source_manifest(root, input_id)
    source = source_by_dataset(manifest_sources(manifest), "decision_schedule")
    if source is None:
        raise SystemExit("missing_decision_schedule")
    df = read_source_csv(root, input_id, source)
    missing = set(SCHEDULE_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit("decision_schedule_missing_columns:" + ",".join(sorted(missing)))
    work = df.copy()
    work["observation_date"] = pd.to_datetime(work["observation_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work["effective_session"] = pd.to_datetime(work["effective_session"], errors="coerce").dt.strftime("%Y-%m-%d")
    return work


def model_spec_hash(spec: dict[str, Any]) -> str:
    return bytes_sha256(json_dumps(spec).encode("utf-8"))


def exposure_label(change: float | None, tolerance: float) -> str:
    if change is None or pd.isna(change):
        return UNAVAILABLE_LABEL
    if abs(change) < tolerance:
        return UNCHANGED_LABEL
    return INCREASE_LABEL if change > 0 else REDUCE_LABEL


def compute_daily_exposure(prices: pd.DataFrame, schedule: pd.DataFrame, spec: dict[str, Any], benchmark_mode: str, input_id: str, run_id: str, manifest_hash: str) -> pd.DataFrame:
    instrument, exact_or_proxy = selected_instrument(benchmark_mode)
    window = int(spec["trailing_window_sessions"])
    annual = float(spec["annualization_factor"])
    target_vol = float(spec["target_volatility"])
    floor = float(spec["exposure_floor"])
    cap = float(spec["exposure_cap"])
    tolerance = float(spec.get("unchanged_tolerance", 1e-12))
    spec_hash = model_spec_hash(spec)
    work = prices.merge(schedule, left_on="date", right_on="observation_date", how="inner", validate="one_to_one")
    returns = work["benchmark_return"]
    work["realized_volatility"] = returns.rolling(window=window, min_periods=window).std(ddof=1) * math.sqrt(annual)
    target_exposures: list[float | None] = []
    labels: list[str] = []
    changes: list[float | None] = []
    priors: list[float | None] = []
    prior: float | None = None
    for _, row in work.iterrows():
        vol = row["realized_volatility"]
        if pd.isna(vol) or not math.isfinite(float(vol)) or float(vol) <= 0:
            target = None
            change = None
            label = UNAVAILABLE_LABEL
        else:
            target = max(floor, min(cap, target_vol / float(vol)))
            change = None if prior is None else target - prior
            label = exposure_label(change, tolerance)
        priors.append(prior)
        target_exposures.append(target)
        changes.append(change)
        labels.append(label)
        if target is not None:
            prior = target
    work["target_exposure"] = target_exposures
    work["prior_target_exposure"] = priors
    work["exposure_change"] = changes
    work["exposure_change_label"] = labels
    rows = []
    for _, row in work.iterrows():
        rows.append(
            {
                "observation_date": row["observation_date"],
                "effective_session": row["effective_session"],
                "benchmark_instrument": instrument,
                "benchmark_mode": benchmark_mode,
                "raw_close": row["raw_close"],
                "benchmark_return": row["benchmark_return"],
                "trailing_window_sessions": window,
                "annualization_factor": annual,
                "realized_volatility": row["realized_volatility"],
                "target_volatility": target_vol,
                "target_exposure": "" if row["target_exposure"] is None else row["target_exposure"],
                "prior_target_exposure": "" if row["prior_target_exposure"] is None else row["prior_target_exposure"],
                "exposure_change": "" if row["exposure_change"] is None else row["exposure_change"],
                "exposure_change_label": row["exposure_change_label"],
                "exposure_change_normalized": "" if row["exposure_change"] is None else row["exposure_change"],
                "decision_timestamp_utc": row["decision_timestamp_utc"],
                "feature_cutoff_date": row["observation_date"],
                "decision_timing_status": "valid_next_session_eod_decision",
                "session_source": row.get("session_source", ""),
                "model_spec_id": spec["model_spec_id"],
                "model_spec_content_hash": spec_hash,
                "source_manifest_hash": manifest_hash,
                "run_id": run_id,
                "research_only": True,
                "actionization_allowed": ACTIONIZATION_ALLOWED,
                "predictive_pit_eligible": False,
                "phase2_eligible": False,
                "not_actual_manager_flow_estimate": True,
                "not_market_impact_estimate": True,
                "not_a_trading_signal": True,
                "benchmark_exact_or_proxy": exact_or_proxy,
            }
        )
    return pd.DataFrame(rows)


def run_historical(root: Path, input_id: str, benchmark_mode: str, model_spec_id: str) -> dict[str, Any]:
    validation = validate_input(root, input_id)
    if validation["validation_status"] != "valid":
        raise SystemExit("vol_control_input_validation_blocked")
    registry, spec, registry_hash = get_model_spec(root, model_spec_id)
    if str(spec.get("frequency")) != "daily":
        raise SystemExit("model_spec_frequency_must_be_daily")
    prices = prepare_prices(root, input_id, benchmark_mode)
    schedule = prepare_schedule(root, input_id)
    run_id = f"{utc_now_compact()}_{bytes_sha256((input_id + benchmark_mode + model_spec_id + str(uuid.uuid4())).encode())[:12]}"
    out = historical_run_dir(root, run_id)
    if out.exists():
        raise SystemExit("vol_control_run_artifact_not_immutable")
    out.mkdir(parents=True, exist_ok=False)
    manifest_hash = file_sha256(source_manifest_path(root, input_id))
    daily = compute_daily_exposure(prices, schedule, spec, benchmark_mode, input_id, run_id, manifest_hash)
    timing = daily[["observation_date", "decision_timestamp_utc", "effective_session", "feature_cutoff_date", "decision_timing_status", "session_source"]].copy()
    write_json(out / "vol_control_input_validation_report.json", validation)
    write_json(out / "vol_control_model_spec_snapshot.json", {"registry": registry, "registry_content_sha256": registry_hash, "selected_model_spec": spec, "selected_model_spec_content_sha256": model_spec_hash(spec)})
    write_csv(out / "vol_control_decision_timing_audit.csv", timing.to_dict("records"))
    write_csv(out / "vol_control_daily_exposure.csv", daily.to_dict("records"))
    (out / "vol_control_summary.md").write_text(summary_md(run_id, input_id, benchmark_mode, model_spec_id, daily), encoding="utf-8")
    (out / "vol_control_limitations.md").write_text(limitations_md(), encoding="utf-8")
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "run_id": run_id,
        "input_id": input_id,
        "mode": HISTORICAL_MODE,
        "benchmark_mode": benchmark_mode,
        "model_spec_id": model_spec_id,
        "model_spec_registry_hash": registry_hash,
        "research_only": True,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "not_a_trading_signal": True,
        "not_actual_manager_flow_estimate": True,
        "not_market_impact_estimate": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "phase1_3_readiness_run": False,
        "phase2_run": False,
        "release_created": False,
        "backtest_run": False,
    }
    write_json(out / "vol_control_run_receipt.json", receipt)
    write_json(out / "vol_control_content_manifest.json", build_content_manifest(out, run_id))
    return {"run_status": "completed", "run_artifact": str(out), **receipt}


def summary_md(run_id: str, input_id: str, benchmark_mode: str, model_spec_id: str, daily: pd.DataFrame) -> str:
    counts = daily["exposure_change_label"].value_counts(dropna=False).to_dict() if not daily.empty else {}
    return "\n".join(
        [
            "# Vol-Control Transparent Replication Summary",
            "",
            f"- module_name: `{MODULE_NAME}`",
            f"- run_id: `{run_id}`",
            f"- input_id: `{input_id}`",
            f"- benchmark_mode: `{benchmark_mode}`",
            f"- model_spec_id: `{model_spec_id}`",
            "- mode: `historical_descriptive_vol_control_replication`",
            "- predictive_pit_eligible: `false`",
            "- phase2_eligible: `false`",
            "- actionization_allowed: `false`",
            "- not_a_trading_signal: `true`",
            "",
            "This is a transparent normalized exposure model, not actual manager flow or market impact.",
            "",
            f"Exposure change label counts: `{counts}`",
        ]
    ) + "\n"


def limitations_md() -> str:
    return """# Vol-Control Research Limitations

This artifact is historical descriptive research only.

The output is a transparent fixed-specification model exposure path. It is not observed institutional flow, not actual vol-control manager positioning, not a market-impact estimate, not a trade instruction, and not a prediction ledger.

The decision at observation date t uses only the close and trailing returns through t. It is interpreted as a next eligible session allocation instruction proxy, not same-close execution.

No output can unlock strict Phase 1.3 readiness, Phase 2 admission, release builds, statistical backtests, notifications, trading, sizing, execution, ranking, or actionization.
"""


def build_content_manifest(out_dir: Path, run_id: str) -> dict[str, Any]:
    files = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "vol_control_content_manifest.json":
            files.append({"relative_path": path.relative_to(out_dir).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "run_id": run_id,
        "content_set_hash": bytes_sha256(json_dumps(files).encode("utf-8")),
        "files": files,
    }


def verify_manifested_dir(run_artifact: Path) -> dict[str, Any]:
    manifest_path = run_artifact / "vol_control_content_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("missing vol_control_content_manifest.json")
    manifest = load_json(manifest_path)
    failures = []
    expected = {entry["relative_path"]: entry for entry in manifest.get("files", [])}
    actual = {p.relative_to(run_artifact).as_posix(): p for p in run_artifact.rglob("*") if p.is_file() and p.name != "vol_control_content_manifest.json"}
    for rel, entry in expected.items():
        path = run_artifact / rel
        if not path.exists():
            failures.append({"relative_path": rel, "reason": "missing"})
        elif file_sha256(path) != entry.get("sha256"):
            failures.append({"relative_path": rel, "reason": "sha256_mismatch"})
    for rel in sorted(set(actual) - set(expected)):
        failures.append({"relative_path": rel, "reason": "extra_file"})
    return {"verification_status": "valid" if not failures else "tampered", "failures": failures, "run_artifact": str(run_artifact)}


def verify_run(run_artifact: str) -> dict[str, Any]:
    path = Path(run_artifact).resolve()
    result = verify_manifested_dir(path)
    receipt = load_json(path / "vol_control_run_receipt.json")
    for field in ["actionization_allowed", "predictive_pit_eligible", "phase2_eligible", "phase1_3_readiness_run", "phase2_run", "release_created", "backtest_run"]:
        if receipt.get(field) is not False:
            result["verification_status"] = "tampered"
            result.setdefault("failures", []).append({"relative_path": "vol_control_run_receipt.json", "reason": f"{field}_must_be_false"})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=MODULE_NAME)
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build-vol-control-template")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("inspect-vol-control-input-contract")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("validate-vol-control-input")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("run-vol-control-historical-descriptive")
    p.add_argument("--input-id", required=True)
    p.add_argument("--benchmark-mode", choices=["ndx_exact_descriptive", "qqq_proxy_only_descriptive"], required=True)
    p.add_argument("--model-spec-id", required=True)
    p = sub.add_parser("verify-vol-control-run")
    p.add_argument("--run-artifact", required=True)
    p = sub.add_parser("build-vol-control-cot-sanity-template")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("inspect-vol-control-cot-sanity-input")
    p.add_argument("--input-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.command == "build-vol-control-template":
        result = build_template(root, args.input_id)
    elif args.command == "inspect-vol-control-input-contract":
        result = inspect_input_contract(root, args.input_id)
    elif args.command == "validate-vol-control-input":
        result = validate_input(root, args.input_id)
    elif args.command == "run-vol-control-historical-descriptive":
        result = run_historical(root, args.input_id, args.benchmark_mode, args.model_spec_id)
    elif args.command == "verify-vol-control-run":
        result = verify_run(args.run_artifact)
    elif args.command == "build-vol-control-cot-sanity-template":
        result = build_cot_template(root, args.input_id)
    elif args.command == "inspect-vol-control-cot-sanity-input":
        result = inspect_cot_sanity_input(root, args.input_id)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    print(json_dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
