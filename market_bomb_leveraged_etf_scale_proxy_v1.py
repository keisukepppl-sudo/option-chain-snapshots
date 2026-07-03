#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pandas as pd


MODULE_NAME = "leveraged_etf_scale_proxy_v1"
ARTIFACT_VERSION = "leveraged_etf_scale_proxy_v1_0_0"
MODEL_SPEC_PATH = Path("config/leveraged_etf_scale_proxy_v1/model_specs.json")
MODEL_SPEC_ID = "tqqq_sqqq_static_daily_reset_scale_v1"
MODE = "historical_descriptive_capital_scaled_proxy"
BENCHMARK_MODE = "ndx_exact"
BENCHMARK_INSTRUMENT = "NDX"
MAX_RELATIVE_AUM_RECONCILIATION_GAP = 0.005
MINIMUM_COVERAGE_RATIO = 0.90
MIN_ABS_BENCHMARK_RETURN = 0.001
APPROVED_CAPITAL_TIERS = {"tier_a_daily_direct", "tier_b_daily_reconciled"}
APPROVED_CAPITAL_AUTHORITIES = {"issuer_official_daily_nav_history", "issuer_official_daily_direct"}

PRICE_COLUMNS = ["date", "instrument", "raw_close", "raw_or_adjusted"]
MAPPING_COLUMNS = [
    "leveraged_etf",
    "target_benchmark_instrument",
    "target_leverage",
    "directionality",
    "benchmark_exact_or_proxy",
    "mapping_source_authority",
    "notes",
]
CAPITAL_COLUMNS = [
    "date",
    "instrument",
    "reported_aum_usd",
    "shares_outstanding",
    "nav_per_share",
    "unit",
    "capital_source_basis",
    "source_record_id",
    "as_of_convention",
]
SPLIT_COLUMNS = ["instrument", "effective_date", "split_ratio", "source_authority", "source_record_id"]
EVIDENCE_FIELDS = [
    "input_id",
    "source_qualification_report_sha256",
    "raw_source_manifest_sha256",
    "benchmark_source_lineage",
    "issuer_direct_daily_series_status",
    "sec_periodic_anchor_status",
    "tqqq_daily_capital_status",
    "sqqq_daily_capital_status",
    "capital_source_basis_by_instrument",
    "coverage_start",
    "coverage_end",
    "historical_vintage_available",
    "publication_timestamp_available",
    "revision_history_available",
    "manual_operator_confirmation_required",
    "notes",
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
    "source_qualification_tier",
    "source_qualification_status",
    "historical_vintage_available",
    "publication_timestamp_available",
    "revision_history_available",
    "is_synthetic_fixture",
    "manual_export_timestamp_utc",
    "manual_capture_timestamp_utc",
    "coverage_start",
    "coverage_end",
    "notes",
]
CANONICAL_SOURCE_FILES = {
    "benchmark_prices": ("sources/benchmark_prices.csv", PRICE_COLUMNS, True),
    "benchmark_mapping": ("sources/benchmark_mapping.csv", MAPPING_COLUMNS, True),
    "leveraged_etf_prices": ("sources/leveraged_etf_prices.csv", PRICE_COLUMNS, False),
    "capital_observations": ("sources/capital_observations.csv", CAPITAL_COLUMNS, True),
    "split_history": ("sources/split_history.csv", SPLIT_COLUMNS, False),
    "scale_source_evidence": ("sources/scale_source_evidence.json", EVIDENCE_FIELDS, True),
}
REQUIRED_FALSE_FLAGS = [
    "actionization_allowed",
    "predictive_pit_eligible",
    "phase2_eligible",
    "phase1_3_readiness_run",
    "phase2_run",
    "release_created",
    "backtest_run",
    "ranking_allowed",
    "model_selection_allowed",
    "returns_analysis_allowed",
]
REQUIRED_TRUE_FLAGS = [
    "research_only",
    "not_a_trading_signal",
    "not_actual_creation_redemption_flow",
    "not_actual_investor_flow",
    "not_actual_manager_trade_estimate",
    "not_dealer_inventory_estimate",
    "not_market_impact_estimate",
]
FORBIDDEN_DAILY_FIELDS = {"pnl", "future_return", "future_outcome", "trade_signal", "actual_flow", "market_impact_estimate"}


def utc_now_compact() -> str:
    return pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    blocked = sorted({name.lower() for name in fieldnames} & FORBIDDEN_DAILY_FIELDS)
    if blocked:
        raise SystemExit(f"forbidden_output_field:{blocked[0]}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def scale_root(repo_root: Path) -> Path:
    return repo_root / "market_bomb_history" / "leveraged_etf_scale_proxy_v1"


def input_dir(repo_root: Path, input_id: str) -> Path:
    return scale_root(repo_root) / "input" / input_id


def historical_root(repo_root: Path) -> Path:
    return scale_root(repo_root) / "historical_runs"


def source_manifest_path(repo_root: Path, input_id: str) -> Path:
    return input_dir(repo_root, input_id) / "source_manifest.json"


def safe_rel(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise SystemExit("path_escape_rejected")
    return target


def load_source_manifest(repo_root: Path, input_id: str) -> dict[str, Any]:
    path = source_manifest_path(repo_root, input_id)
    if not path.exists():
        raise SystemExit("missing_required_dataset:source_manifest")
    return load_json(path)


def source_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = manifest.get("sources", [])
    if not isinstance(entries, list):
        raise SystemExit("missing_required_headers:source_manifest_sources")
    return entries


def source_by_dataset(entries: list[dict[str, Any]], dataset_type: str) -> dict[str, Any] | None:
    matches = [entry for entry in entries if str(entry.get("dataset_type")) == dataset_type]
    return matches[0] if matches else None


def build_template(repo_root: Path, input_id: str) -> dict[str, Any]:
    base = input_dir(repo_root, input_id)
    sources = base / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    for _, (rel, columns, _) in CANONICAL_SOURCE_FILES.items():
        path = safe_rel(base, rel)
        if path.suffix == ".csv" and not path.exists():
            write_csv(path, [], columns)
        elif path.suffix == ".json" and not path.exists():
            write_json(path, {"input_id": input_id, "manual_operator_confirmation_required": True})
    manifest = source_manifest_path(repo_root, input_id)
    if not manifest.exists():
        write_json(
            manifest,
            {
                "artifact_version": ARTIFACT_VERSION,
                "module_name": MODULE_NAME,
                "input_id": input_id,
                "research_only": True,
                "actionization_allowed": False,
                "not_a_trading_signal": True,
                "sources": [],
            },
        )
    return {"template_status": "created_or_existing", "input_id": input_id, "template_root": str(base)}


def finite_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        out = float(str(value).replace(",", ""))
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def positive_float(value: Any) -> float | None:
    out = finite_float(value)
    if out is None or out <= 0:
        return None
    return out


def parse_date(value: Any) -> str | None:
    ts = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d")


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def model_spec(repo_root: Path) -> dict[str, Any]:
    path = repo_root / MODEL_SPEC_PATH
    if not path.exists():
        path = Path(__file__).resolve().parent / MODEL_SPEC_PATH
    registry = load_json(path)
    matches = [model for model in registry.get("models", []) if model.get("model_spec_id") == MODEL_SPEC_ID]
    if len(matches) != 1:
        raise SystemExit("model_spec_missing")
    return matches[0]


def model_spec_hash(repo_root: Path) -> str:
    path = repo_root / MODEL_SPEC_PATH
    if not path.exists():
        path = Path(__file__).resolve().parent / MODEL_SPEC_PATH
    return file_sha256(path)


def module_source_hash(repo_root: Path) -> str:
    path = repo_root / "market_bomb_leveraged_etf_scale_proxy_v1.py"
    if not path.exists():
        path = Path(__file__).resolve()
    return file_sha256(path)


def repository_commit_sha(repo_root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    except Exception:
        return "unknown"


def repository_commit_status(repo_root: Path) -> str:
    try:
        status = subprocess.check_output(["git", "status", "--short", "--untracked-files=no"], cwd=repo_root, text=True)
    except Exception:
        return "unknown"
    return "clean_tracked_files" if not status.strip() else "tracked_changes_present"


def git_tracked_market_bomb(repo_root: Path) -> list[str]:
    try:
        out = subprocess.check_output(["git", "ls-files", "market_bomb_history"], cwd=repo_root, text=True)
    except Exception:
        return []
    return [line for line in out.splitlines() if line.strip()]


def validate_manifest(repo_root: Path, input_id: str, diagnostics: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_source_manifest(repo_root, input_id)
    for field in ["artifact_version", "module_name", "input_id", "sources"]:
        if field not in manifest:
            diagnostics.append({"code": "missing_required_headers", "details": field})
    if manifest.get("module_name") != MODULE_NAME:
        diagnostics.append({"code": "missing_required_headers", "details": "module_name"})
    entries = source_entries(manifest)
    seen_paths: set[str] = set()
    for entry in entries:
        missing = [field for field in SOURCE_MANIFEST_FIELDS if field not in entry]
        if missing:
            diagnostics.append({"code": "missing_required_headers", "dataset_type": entry.get("dataset_type", ""), "details": ",".join(missing)})
        rel = str(entry.get("relative_path", ""))
        if rel in seen_paths:
            diagnostics.append({"code": "duplicate_source_path", "relative_path": rel})
        seen_paths.add(rel)
        if rel:
            path = safe_rel(input_dir(repo_root, input_id), rel)
            if not path.exists():
                diagnostics.append({"code": "missing_required_dataset", "dataset_type": entry.get("dataset_type", ""), "relative_path": rel})
            elif str(entry.get("content_sha256", "")) != file_sha256(path):
                diagnostics.append({"code": "content_sha256_mismatch", "dataset_type": entry.get("dataset_type", ""), "relative_path": rel})
        if normalize_bool(entry.get("historical_vintage_available")) or normalize_bool(entry.get("publication_timestamp_available")) or normalize_bool(entry.get("revision_history_available")):
            diagnostics.append({"code": "capital_observation_historical_pit_claim", "dataset_type": entry.get("dataset_type", ""), "relative_path": rel})
    for dataset_type, (_, _, required) in CANONICAL_SOURCE_FILES.items():
        if required and source_by_dataset(entries, dataset_type) is None:
            diagnostics.append({"code": "missing_required_dataset", "dataset_type": dataset_type})
    if git_tracked_market_bomb(repo_root):
        diagnostics.append({"code": "raw_provider_files_tracked", "details": "market_bomb_history has tracked files"})
    return manifest, entries


def validate_headers(df: pd.DataFrame, required: list[str], dataset_type: str, diagnostics: list[dict[str, Any]]) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        diagnostics.append({"code": "missing_required_headers", "dataset_type": dataset_type, "details": ",".join(missing)})


def load_source_csv(repo_root: Path, input_id: str, entry: dict[str, Any], required: list[str], diagnostics: list[dict[str, Any]]) -> pd.DataFrame:
    path = safe_rel(input_dir(repo_root, input_id), str(entry.get("relative_path", "")))
    df = read_csv(path)
    validate_headers(df, required, str(entry.get("dataset_type", "")), diagnostics)
    return df


def validate_mapping(mapping: pd.DataFrame, diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected = {
        "TQQQ": ("NDX", 3.0, "long"),
        "SQQQ": ("NDX", -3.0, "inverse"),
    }
    for _, row in mapping.iterrows():
        ticker = str(row.get("leveraged_etf", ""))
        status = "valid"
        reason = ""
        if ticker not in expected:
            status, reason = "invalid", "unexpected_leveraged_etf"
        else:
            benchmark, lev, direction = expected[ticker]
            if str(row.get("target_benchmark_instrument")) != benchmark or str(row.get("benchmark_exact_or_proxy")) != "benchmark_exact":
                status, reason = "invalid", "benchmark_not_ndx_exact"
            elif abs(float(row.get("target_leverage", "nan")) - lev) > 1e-12 or str(row.get("directionality")) != direction:
                status, reason = "invalid", "benchmark_mapping_invalid"
        if status != "valid":
            diagnostics.append({"code": reason or "benchmark_mapping_invalid", "leveraged_etf": ticker})
        rows.append({"leveraged_etf": ticker, "mapping_status": status, "reason": reason})
    if set(mapping.get("leveraged_etf", [])) != {"TQQQ", "SQQQ"}:
        diagnostics.append({"code": "benchmark_mapping_invalid", "details": "must contain exactly TQQQ and SQQQ"})
    return rows


def normalize_benchmark_prices(prices: pd.DataFrame, diagnostics: list[dict[str, Any]]) -> pd.DataFrame:
    if prices.empty:
        diagnostics.append({"code": "missing_required_dataset", "dataset_type": "benchmark_prices"})
        return prices
    if set(prices["instrument"].astype(str)) != {"NDX"}:
        diagnostics.append({"code": "benchmark_not_ndx_exact", "details": "instrument must be NDX only"})
    if len(set(prices["raw_or_adjusted"].astype(str))) != 1:
        diagnostics.append({"code": "mixed_price_basis", "dataset_type": "benchmark_prices"})
    rows = []
    for _, row in prices.iterrows():
        date = parse_date(row["date"])
        close = positive_float(row["raw_close"])
        if date is None or close is None:
            diagnostics.append({"code": "invalid_capital_date", "dataset_type": "benchmark_prices"})
            continue
        rows.append({"date": date, "instrument": "NDX", "raw_close": close, "raw_or_adjusted": str(row["raw_or_adjusted"])})
    out = pd.DataFrame(rows).sort_values("date")
    if out["date"].duplicated().any():
        diagnostics.append({"code": "duplicate_capital_observation", "dataset_type": "benchmark_prices"})
    return out


def validate_capital_source(entry: dict[str, Any], diagnostics: list[dict[str, Any]]) -> None:
    if str(entry.get("source_authority_type")) not in APPROVED_CAPITAL_AUTHORITIES:
        diagnostics.append({"code": "capital_observation_unapproved_source", "details": str(entry.get("source_authority_type", ""))})
    if str(entry.get("source_qualification_tier")) not in APPROVED_CAPITAL_TIERS:
        diagnostics.append({"code": "capital_observation_unqualified_frequency", "details": str(entry.get("source_qualification_tier", ""))})


def normalize_capital(capital: pd.DataFrame, capital_entry: dict[str, Any], split_df: pd.DataFrame | None, diagnostics: list[dict[str, Any]]) -> pd.DataFrame:
    validate_capital_source(capital_entry, diagnostics)
    rows = []
    seen: set[tuple[str, str]] = set()
    for _, row in capital.iterrows():
        date = parse_date(row.get("date", ""))
        instrument = str(row.get("instrument", ""))
        if date is None:
            diagnostics.append({"code": "invalid_capital_date", "instrument": instrument})
        if instrument not in {"TQQQ", "SQQQ"}:
            diagnostics.append({"code": "invalid_capital_instrument", "instrument": instrument})
            continue
        key = (date, instrument)
        if key in seen:
            diagnostics.append({"code": "duplicate_capital_observation", "instrument": instrument, "date": date})
        seen.add(key)
        unit = str(row.get("unit", ""))
        basis = str(row.get("capital_source_basis", ""))
        if unit != "USD":
            diagnostics.append({"code": "invalid_capital_unit", "instrument": instrument, "date": date})
        if basis not in {"reported_aum_usd", "shares_times_nav", "reported_aum_and_shares_nav"}:
            diagnostics.append({"code": "invalid_capital_source_basis", "instrument": instrument, "date": date})
        if not str(row.get("source_record_id", "")).strip():
            diagnostics.append({"code": "missing_source_record_id", "instrument": instrument, "date": date})
        if not str(row.get("as_of_convention", "")).strip():
            diagnostics.append({"code": "missing_as_of_convention", "instrument": instrument, "date": date})
        reported = positive_float(row.get("reported_aum_usd", ""))
        shares = positive_float(row.get("shares_outstanding", ""))
        nav = positive_float(row.get("nav_per_share", ""))
        if (shares is None) ^ (nav is None):
            diagnostics.append({"code": "shares_nav_partial_pair", "instrument": instrument, "date": date})
        if reported is None and (shares is None or nav is None):
            diagnostics.append({"code": "capital_observation_no_usable_scale", "instrument": instrument, "date": date})
        derived = None
        gap = ""
        if shares is not None and nav is not None:
            derived = shares * nav
            if reported is not None:
                rel_gap = abs(reported - derived) / reported
                gap = rel_gap
                if rel_gap > MAX_RELATIVE_AUM_RECONCILIATION_GAP:
                    diagnostics.append({"code": "reported_aum_shares_nav_reconciliation_failed", "instrument": instrument, "date": date, "relative_gap": rel_gap})
            elif basis == "shares_times_nav" and (split_df is None or split_df.empty):
                diagnostics.append({"code": "split_history_missing_for_shares_nav", "instrument": instrument, "date": date})
        capital_value = reported if reported is not None else derived
        rows.append(
            {
                "date": date,
                "instrument": instrument,
                "reported_aum_usd": reported,
                "shares_outstanding": shares,
                "nav_per_share": nav,
                "derived_aum_usd": derived,
                "relative_reconciliation_gap": gap,
                "capital_input_usd": capital_value,
                "capital_source_basis": basis,
                "source_record_id": str(row.get("source_record_id", "")),
                "as_of_convention": str(row.get("as_of_convention", "")),
            }
        )
    return pd.DataFrame(rows)


def validate_split_history(split_df: pd.DataFrame | None, diagnostics: list[dict[str, Any]]) -> None:
    if split_df is None:
        return
    missing = [col for col in SPLIT_COLUMNS if col not in split_df.columns]
    if missing:
        diagnostics.append({"code": "split_history_schema_invalid", "details": ",".join(missing)})
        return
    for _, row in split_df.iterrows():
        if str(row.get("instrument", "")) not in {"TQQQ", "SQQQ"}:
            diagnostics.append({"code": "split_history_schema_invalid", "details": "invalid instrument"})
        if parse_date(row.get("effective_date", "")) is None:
            diagnostics.append({"code": "split_history_schema_invalid", "details": "invalid effective_date"})
        ratio = positive_float(row.get("split_ratio", ""))
        if ratio is None:
            diagnostics.append({"code": "split_history_schema_invalid", "details": "invalid split_ratio"})


def validate_evidence(repo_root: Path, input_id: str, evidence_entry: dict[str, Any] | None, diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    if evidence_entry is None:
        diagnostics.append({"code": "raw_source_evidence_missing"})
        return {}
    path = safe_rel(input_dir(repo_root, input_id), str(evidence_entry.get("relative_path", "")))
    evidence = load_json(path)
    missing = [field for field in EVIDENCE_FIELDS if field not in evidence]
    if missing:
        diagnostics.append({"code": "raw_source_evidence_missing", "details": ",".join(missing)})
    for field in ["historical_vintage_available", "revision_history_available"]:
        if normalize_bool(evidence.get(field)):
            diagnostics.append({"code": "capital_observation_historical_pit_claim", "details": field})
    for field in ["source_qualification_report_sha256", "raw_source_manifest_sha256"]:
        value = str(evidence.get(field, ""))
        if not value or len(value) != 64:
            diagnostics.append({"code": "raw_source_evidence_hash_mismatch", "details": field})
    return evidence


def benchmark_return_rows(prices: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    ordered = prices.sort_values("date").reset_index(drop=True)
    for i in range(1, len(ordered)):
        prev = ordered.iloc[i - 1]
        cur = ordered.iloc[i]
        ret = float(cur["raw_close"]) / float(prev["raw_close"]) - 1.0
        rows.append(
            {
                "observation_date": cur["date"],
                "prior_capital_observation_date_required": prev["date"],
                "benchmark_instrument": "NDX",
                "benchmark_exact_or_proxy": "benchmark_exact",
                "benchmark_return": ret,
            }
        )
    return rows


def capital_lookup(capital: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for _, row in capital.iterrows():
        if positive_float(row.get("capital_input_usd", "")) is not None:
            out[(str(row["date"]), str(row["instrument"]))] = row.to_dict()
    return out


def mechanical_rebalance_notional_proxy(leverage: float, prior_capital: float, benchmark_return: float) -> float:
    return leverage * (leverage - 1.0) * prior_capital * benchmark_return


def directional_label(value: float | None) -> str:
    if value is None or abs(value) < MIN_ABS_BENCHMARK_RETURN:
        return "directional_neutral_or_small_move"
    return "directional_positive_benchmark_move" if value > 0 else "directional_negative_benchmark_move"


def build_daily_rows(prices: pd.DataFrame, capital: pd.DataFrame, manifest_hash: str, run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lookup = capital_lookup(capital)
    rows = []
    tqqq_ok = sqqq_ok = both_ok = 0
    returns = benchmark_return_rows(prices)
    for base in returns:
        required_date = base["prior_capital_observation_date_required"]
        tqqq_cap = lookup.get((required_date, "TQQQ"))
        sqqq_cap = lookup.get((required_date, "SQQQ"))
        ret = float(base["benchmark_return"])
        tqqq_val = positive_float(tqqq_cap.get("capital_input_usd")) if tqqq_cap else None
        sqqq_val = positive_float(sqqq_cap.get("capital_input_usd")) if sqqq_cap else None
        if tqqq_val is not None:
            tqqq_ok += 1
        if sqqq_val is not None:
            sqqq_ok += 1
        if tqqq_val is not None and sqqq_val is not None:
            both_ok += 1
        tqqq_proxy = "" if tqqq_val is None else mechanical_rebalance_notional_proxy(3.0, tqqq_val, ret)
        sqqq_proxy = "" if sqqq_val is None else mechanical_rebalance_notional_proxy(-3.0, sqqq_val, ret)
        combined = "" if tqqq_proxy == "" or sqqq_proxy == "" else tqqq_proxy + sqqq_proxy
        rows.append(
            {
                **base,
                "tqqq_lagged_capital_usd": "" if tqqq_val is None else tqqq_val,
                "sqqq_lagged_capital_usd": "" if sqqq_val is None else sqqq_val,
                "tqqq_capital_source_basis": "" if tqqq_cap is None else tqqq_cap.get("capital_source_basis", ""),
                "sqqq_capital_source_basis": "" if sqqq_cap is None else sqqq_cap.get("capital_source_basis", ""),
                "tqqq_capital_observation_status": "exact_prior_session_capital_available" if tqqq_val is not None else "exact_prior_session_capital_unavailable",
                "sqqq_capital_observation_status": "exact_prior_session_capital_available" if sqqq_val is not None else "exact_prior_session_capital_unavailable",
                "tqqq_rebalance_notional_proxy": tqqq_proxy,
                "sqqq_rebalance_notional_proxy": sqqq_proxy,
                "combined_rebalance_notional_proxy": combined,
                "combined_scale_status": "combined_exact_prior_session_capital_available" if combined != "" else "combined_exact_prior_session_capital_unavailable",
                "equal_weight_directional_proxy": 0 if abs(ret) < MIN_ABS_BENCHMARK_RETURN else (1 if ret > 0 else -1),
                "directional_amplifier_label": directional_label(ret),
                "model_spec_id": MODEL_SPEC_ID,
                "source_manifest_hash": manifest_hash,
                "run_id": run_id,
                "research_only": True,
                "actionization_allowed": False,
                "predictive_pit_eligible": False,
                "phase2_eligible": False,
                "not_actual_creation_redemption_flow": True,
                "not_actual_investor_flow": True,
                "not_actual_manager_trade_estimate": True,
                "not_market_impact_estimate": True,
            }
        )
    denom = len(returns)
    coverage = {
        "ndx_return_rows": denom,
        "tqqq_lagged_capital_coverage_ratio": 0.0 if denom == 0 else tqqq_ok / denom,
        "sqqq_lagged_capital_coverage_ratio": 0.0 if denom == 0 else sqqq_ok / denom,
        "combined_overlap_coverage_ratio": 0.0 if denom == 0 else both_ok / denom,
        "tqqq_available_rows": tqqq_ok,
        "sqqq_available_rows": sqqq_ok,
        "combined_available_rows": both_ok,
    }
    return rows, coverage


def load_validated_input(repo_root: Path, input_id: str) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    manifest, entries = validate_manifest(repo_root, input_id, diagnostics)
    price_entry = source_by_dataset(entries, "benchmark_prices")
    mapping_entry = source_by_dataset(entries, "benchmark_mapping")
    capital_entry = source_by_dataset(entries, "capital_observations")
    split_entry = source_by_dataset(entries, "split_history")
    evidence_entry = source_by_dataset(entries, "scale_source_evidence")
    prices = pd.DataFrame(columns=PRICE_COLUMNS)
    mapping_rows: list[dict[str, Any]] = []
    capital = pd.DataFrame()
    split_df = None
    evidence = validate_evidence(repo_root, input_id, evidence_entry, diagnostics)
    if price_entry:
        prices = normalize_benchmark_prices(load_source_csv(repo_root, input_id, price_entry, PRICE_COLUMNS, diagnostics), diagnostics)
    if mapping_entry:
        mapping = load_source_csv(repo_root, input_id, mapping_entry, MAPPING_COLUMNS, diagnostics)
        mapping_rows = validate_mapping(mapping, diagnostics)
    if split_entry:
        split_df = load_source_csv(repo_root, input_id, split_entry, SPLIT_COLUMNS, diagnostics)
        validate_split_history(split_df, diagnostics)
    if capital_entry:
        cap_df = load_source_csv(repo_root, input_id, capital_entry, CAPITAL_COLUMNS, diagnostics)
        capital = normalize_capital(cap_df, capital_entry, split_df, diagnostics)
    if not capital_entry:
        diagnostics.append({"code": "missing_tqqq_daily_capital"})
        diagnostics.append({"code": "missing_sqqq_daily_capital"})
    elif not capital.empty:
        instruments = set(capital["instrument"].astype(str))
        if "TQQQ" not in instruments:
            diagnostics.append({"code": "missing_tqqq_daily_capital"})
        if "SQQQ" not in instruments:
            diagnostics.append({"code": "missing_sqqq_daily_capital"})
    manifest_hash = file_sha256(source_manifest_path(repo_root, input_id)) if source_manifest_path(repo_root, input_id).exists() else ""
    run_id = "validation_preview"
    daily_rows, coverage = build_daily_rows(prices, capital, manifest_hash, run_id) if not prices.empty else ([], {"ndx_return_rows": 0, "tqqq_lagged_capital_coverage_ratio": 0.0, "sqqq_lagged_capital_coverage_ratio": 0.0, "combined_overlap_coverage_ratio": 0.0})
    coverage_codes = []
    for field in ["tqqq_lagged_capital_coverage_ratio", "sqqq_lagged_capital_coverage_ratio", "combined_overlap_coverage_ratio"]:
        if float(coverage.get(field, 0.0)) < MINIMUM_COVERAGE_RATIO:
            coverage_codes.append(field)
    validation_status = "valid" if not diagnostics and not coverage_codes else "blocked"
    if not diagnostics and coverage_codes:
        validation_status = "scale_coverage_inadequate_for_historical_run"
    return {
        "manifest": manifest,
        "entries": entries,
        "prices": prices,
        "mapping_validation_rows": mapping_rows,
        "capital": capital,
        "split_df": split_df,
        "evidence": evidence,
        "daily_preview_rows": daily_rows,
        "coverage": coverage,
        "coverage_blockers": coverage_codes,
        "diagnostics": diagnostics,
        "validation_status": validation_status,
    }


def validate_input(repo_root: Path, input_id: str) -> dict[str, Any]:
    data = load_validated_input(repo_root, input_id)
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "validation_status": data["validation_status"],
        "diagnostics": data["diagnostics"],
        "coverage": data["coverage"],
        "coverage_blockers": data["coverage_blockers"],
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }


def inspect_input(repo_root: Path, input_id: str) -> dict[str, Any]:
    base = input_dir(repo_root, input_id)
    files = []
    for dataset_type, (rel, columns, required) in CANONICAL_SOURCE_FILES.items():
        path = safe_rel(base, rel)
        present = path.exists()
        headers = []
        if present and path.suffix == ".csv":
            try:
                headers = list(read_csv(path).columns)
            except Exception:
                headers = []
        files.append(
            {
                "dataset_type": dataset_type,
                "relative_path": rel,
                "present": present,
                "required": required,
                "expected_headers": columns,
                "observed_headers": headers,
                "content_sha256": file_sha256(path) if present and path.is_file() else "",
            }
        )
    try:
        validation = validate_input(repo_root, input_id)
    except SystemExit as exc:
        validation = {"validation_status": "blocked", "diagnostics": [{"code": str(exc)}]}
    return {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "input_id": input_id,
        "inspection_status": "completed",
        "canonical_layout": "market_bomb_history/leveraged_etf_scale_proxy_v1/input/<input_id>",
        "files": files,
        "validation": validation,
    }


def capital_quality_rows(capital: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for _, row in capital.iterrows():
        rows.append(
            {
                "date": row["date"],
                "instrument": row["instrument"],
                "capital_source_basis": row["capital_source_basis"],
                "reported_aum_usd_present": row.get("reported_aum_usd", "") != "",
                "shares_nav_present": row.get("shares_outstanding", "") != "" and row.get("nav_per_share", "") != "",
                "relative_reconciliation_gap": row.get("relative_reconciliation_gap", ""),
                "quality_status": "valid_for_scale",
                "capital_input_selected": "reported_aum_usd" if row.get("reported_aum_usd", "") != "" else "shares_times_nav",
            }
        )
    return rows


def coverage_rows(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"coverage_metric": "ndx_return_rows", "value": coverage.get("ndx_return_rows", 0), "minimum_required": ""},
        {"coverage_metric": "tqqq_lagged_capital_coverage_ratio", "value": coverage.get("tqqq_lagged_capital_coverage_ratio", 0), "minimum_required": MINIMUM_COVERAGE_RATIO},
        {"coverage_metric": "sqqq_lagged_capital_coverage_ratio", "value": coverage.get("sqqq_lagged_capital_coverage_ratio", 0), "minimum_required": MINIMUM_COVERAGE_RATIO},
        {"coverage_metric": "combined_overlap_coverage_ratio", "value": coverage.get("combined_overlap_coverage_ratio", 0), "minimum_required": MINIMUM_COVERAGE_RATIO},
    ]


def split_reconciliation_rows(split_df: pd.DataFrame | None, capital: pd.DataFrame) -> list[dict[str, Any]]:
    basis_needs_split = bool((capital.get("capital_source_basis", pd.Series(dtype=str)).astype(str) == "shares_times_nav").any()) if not capital.empty else False
    if split_df is None or split_df.empty:
        return [{"instrument": "TQQQ/SQQQ", "split_diagnostic_status": "not_blocking_reported_aum_selected" if not basis_needs_split else "missing_required_split_history", "documented_split_count": 0}]
    return [
        {
            "instrument": instrument,
            "split_diagnostic_status": "documented",
            "documented_split_count": int(len(group)),
        }
        for instrument, group in split_df.groupby("instrument")
    ]


def summary_md(run_id: str, input_id: str, coverage: dict[str, Any], daily_rows: list[dict[str, Any]], capital: pd.DataFrame) -> str:
    available = sum(1 for row in daily_rows if row["combined_scale_status"] == "combined_exact_prior_session_capital_available")
    unavailable = len(daily_rows) - available
    values = [abs(float(row["combined_rebalance_notional_proxy"])) for row in daily_rows if row["combined_rebalance_notional_proxy"] != ""]
    series = pd.Series(values, dtype=float)
    basis_counts = capital.groupby(["instrument", "capital_source_basis"]).size().to_dict() if not capital.empty else {}
    return "\n".join(
        [
            "# Leveraged ETF Scale Proxy Summary",
            "",
            f"- run_id: `{run_id}`",
            f"- input_id: `{input_id}`",
            f"- mode: `{MODE}`",
            f"- model_spec_id: `{MODEL_SPEC_ID}`",
            f"- NDX return rows: `{coverage.get('ndx_return_rows', 0)}`",
            f"- TQQQ lagged capital coverage ratio: `{coverage.get('tqqq_lagged_capital_coverage_ratio', 0)}`",
            f"- SQQQ lagged capital coverage ratio: `{coverage.get('sqqq_lagged_capital_coverage_ratio', 0)}`",
            f"- Combined overlap coverage ratio: `{coverage.get('combined_overlap_coverage_ratio', 0)}`",
            f"- Combined proxy available rows: `{available}`",
            f"- Combined proxy unavailable rows: `{unavailable}`",
            f"- Capital source basis counts: `{basis_counts}`",
            "",
            "Mechanical notional proxy magnitude:",
            "",
            f"- count: `{int(series.count())}`",
            f"- mean: `{'' if series.empty else float(series.mean())}`",
            f"- median: `{'' if series.empty else float(series.median())}`",
            f"- p90: `{'' if series.empty else float(series.quantile(0.90))}`",
            f"- p95: `{'' if series.empty else float(series.quantile(0.95))}`",
            f"- maximum_absolute_value: `{'' if series.empty else float(series.max())}`",
            "",
            "These magnitude statistics are mechanics of the fixed daily-reset proxy, not actual flow.",
        ]
    ) + "\n"


def limitations_md() -> str:
    return """# Historical Descriptive Limitations

This artifact is a capital-scaled mechanical daily-reset approximation for TQQQ and SQQQ.

It is not actual creation/redemption flow, shareholder flow, manager trading, dealer inventory, market impact, a forecast, or a trading signal. It does not unlock strict PIT eligibility, Phase 1.3 readiness, Phase 2, release promotion, notification logic, sizing, or execution.
"""


def build_content_manifest(out_dir: Path, run_id: str) -> dict[str, Any]:
    files = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "leveraged_etf_scale_content_manifest.json":
            files.append({"relative_path": path.relative_to(out_dir).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {"artifact_version": ARTIFACT_VERSION, "module_name": MODULE_NAME, "run_id": run_id, "files": files}


def run_historical(repo_root: Path, input_id: str, benchmark_mode: str, model_spec_id: str) -> dict[str, Any]:
    if benchmark_mode != BENCHMARK_MODE:
        raise SystemExit("benchmark_not_ndx_exact")
    if model_spec_id != MODEL_SPEC_ID:
        raise SystemExit("model_spec_invalid")
    spec = model_spec(repo_root)
    data = load_validated_input(repo_root, input_id)
    if data["diagnostics"]:
        raise SystemExit(data["diagnostics"][0]["code"])
    if data["coverage_blockers"]:
        raise SystemExit("scale_coverage_inadequate_for_historical_run")
    run_id = f"{utc_now_compact()}_{bytes_sha256((input_id + str(uuid.uuid4())).encode())[:12]}"
    out = historical_root(repo_root) / run_id
    out.mkdir(parents=True, exist_ok=False)
    manifest_hash = file_sha256(source_manifest_path(repo_root, input_id))
    daily_rows, coverage = build_daily_rows(data["prices"], data["capital"], manifest_hash, run_id)
    write_json(out / "leveraged_etf_scale_input_validation_report.json", validate_input(repo_root, input_id))
    write_json(out / "leveraged_etf_scale_model_spec_snapshot.json", spec)
    write_json(out / "leveraged_etf_scale_source_evidence_snapshot.json", data["evidence"])
    write_csv(out / "benchmark_mapping_validation.csv", data["mapping_validation_rows"])
    write_csv(out / "capital_observation_quality_report.csv", capital_quality_rows(data["capital"]))
    write_csv(out / "capital_coverage_report.csv", coverage_rows(coverage))
    write_csv(out / "split_reconciliation_report.csv", split_reconciliation_rows(data["split_df"], data["capital"]))
    write_csv(out / "leveraged_etf_scale_proxy_daily.csv", daily_rows)
    (out / "leveraged_etf_scale_proxy_summary.md").write_text(summary_md(run_id, input_id, coverage, daily_rows, data["capital"]), encoding="utf-8")
    (out / "historical_descriptive_limitations.md").write_text(limitations_md(), encoding="utf-8")
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "module_name": MODULE_NAME,
        "run_id": run_id,
        "input_id": input_id,
        "mode": MODE,
        "benchmark_mode": BENCHMARK_MODE,
        "model_spec_id": MODEL_SPEC_ID,
        "repository_commit_sha": repository_commit_sha(repo_root),
        "repository_commit_status": repository_commit_status(repo_root),
        "module_source_sha256": module_source_hash(repo_root),
        "model_spec_registry_hash": model_spec_hash(repo_root),
        "source_manifest_hash": manifest_hash,
        "scale_source_evidence_sha256": file_sha256(safe_rel(input_dir(repo_root, input_id), str(source_by_dataset(data["entries"], "scale_source_evidence")["relative_path"]))),
        "raw_source_manifest_sha256": str(data["evidence"].get("raw_source_manifest_sha256", "")),
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "not_actual_creation_redemption_flow": True,
        "not_actual_investor_flow": True,
        "not_actual_manager_trade_estimate": True,
        "not_dealer_inventory_estimate": True,
        "not_market_impact_estimate": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "phase1_3_readiness_run": False,
        "phase2_run": False,
        "release_created": False,
        "backtest_run": False,
        "ranking_allowed": False,
        "model_selection_allowed": False,
        "returns_analysis_allowed": False,
        **coverage,
    }
    write_json(out / "leveraged_etf_scale_run_receipt.json", receipt)
    write_json(out / "leveraged_etf_scale_content_manifest.json", build_content_manifest(out, run_id))
    return {"run_status": "completed", "run_id": run_id, "run_artifact": str(out), **receipt}


def verify_manifested_dir(run_artifact: Path, manifest_name: str) -> dict[str, Any]:
    manifest_path = run_artifact / manifest_name
    if not manifest_path.exists():
        raise SystemExit("missing_manifest")
    manifest = load_json(manifest_path)
    expected = {entry["relative_path"]: entry for entry in manifest.get("files", [])}
    actual = {p.relative_to(run_artifact).as_posix(): p for p in run_artifact.rglob("*") if p.is_file() and p.name != manifest_name}
    failures = []
    for rel, entry in expected.items():
        path = run_artifact / rel
        if not path.exists() or file_sha256(path) != entry.get("sha256"):
            failures.append({"relative_path": rel, "reason": "sha256_mismatch_or_missing"})
    for rel in sorted(set(actual) - set(expected)):
        failures.append({"relative_path": rel, "reason": "unexpected_extra_file"})
    return {"verification_status": "valid" if not failures else "tampered", "failures": failures}


def verify_run(run_artifact: str) -> dict[str, Any]:
    path = Path(run_artifact).resolve()
    result = verify_manifested_dir(path, "leveraged_etf_scale_content_manifest.json")
    receipt = load_json(path / "leveraged_etf_scale_run_receipt.json")
    for field in REQUIRED_FALSE_FLAGS:
        if receipt.get(field) is not False:
            result["verification_status"] = "tampered"
            result.setdefault("failures", []).append({"relative_path": "leveraged_etf_scale_run_receipt.json", "reason": f"{field}_must_be_false"})
    for field in REQUIRED_TRUE_FLAGS:
        if receipt.get(field) is not True:
            result["verification_status"] = "tampered"
            result.setdefault("failures", []).append({"relative_path": "leveraged_etf_scale_run_receipt.json", "reason": f"{field}_must_be_true"})
    if receipt.get("model_spec_id") != MODEL_SPEC_ID or receipt.get("benchmark_mode") != BENCHMARK_MODE:
        result["verification_status"] = "tampered"
        result.setdefault("failures", []).append({"relative_path": "leveraged_etf_scale_run_receipt.json", "reason": "model_or_benchmark_mismatch"})
    for field in ["tqqq_lagged_capital_coverage_ratio", "sqqq_lagged_capital_coverage_ratio", "combined_overlap_coverage_ratio"]:
        if float(receipt.get(field, 0.0)) < MINIMUM_COVERAGE_RATIO:
            result["verification_status"] = "tampered"
            result.setdefault("failures", []).append({"relative_path": "leveraged_etf_scale_run_receipt.json", "reason": f"{field}_below_minimum"})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Leveraged ETF capital-scaled mechanical rebalance proxy v1.")
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build-leveraged-etf-scale-template")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("inspect-leveraged-etf-scale-input")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("validate-leveraged-etf-scale-input")
    p.add_argument("--input-id", required=True)
    p = sub.add_parser("run-leveraged-etf-scale-historical-descriptive")
    p.add_argument("--input-id", required=True)
    p.add_argument("--benchmark-mode", required=True)
    p.add_argument("--model-spec-id", required=True)
    p = sub.add_parser("verify-leveraged-etf-scale-run")
    p.add_argument("--run-artifact", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.command == "build-leveraged-etf-scale-template":
        result = build_template(repo_root, args.input_id)
    elif args.command == "inspect-leveraged-etf-scale-input":
        result = inspect_input(repo_root, args.input_id)
    elif args.command == "validate-leveraged-etf-scale-input":
        result = validate_input(repo_root, args.input_id)
    elif args.command == "run-leveraged-etf-scale-historical-descriptive":
        result = run_historical(repo_root, args.input_id, args.benchmark_mode, args.model_spec_id)
    elif args.command == "verify-leveraged-etf-scale-run":
        result = verify_run(args.run_artifact)
    else:
        raise SystemExit("unknown_command")
    print(json_dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
