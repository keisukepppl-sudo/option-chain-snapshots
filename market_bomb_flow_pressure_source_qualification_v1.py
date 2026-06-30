#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


QUALIFICATION_VERSION = "flow_pressure_source_qualification_v1"

GOLD = "gold_point_in_time_eligible"
SILVER = "silver_documented_schedule_eligible"
AUTHORITATIVE_UNPROVEN = "authoritative_but_historical_vintage_unproven"
DESCRIPTIVE_ONLY = "historical_descriptive_only"
BLOCKED_QUALITY = "blocked_by_data_quality"
BLOCKED_TIMING = "blocked_by_timing"

PREDICTIVE_STATUSES = {GOLD, SILVER}

REQUIRED_MATRIX_FIELDS = [
    "dataset_type",
    "instrument",
    "source_tier",
    "provider_or_issuer",
    "source_authority_type",
    "economic_value_authority",
    "historical_vintage_available",
    "publication_timestamp_available",
    "revision_history_available",
    "availability_evidence_type",
    "availability_evidence_reference",
    "raw_or_adjusted",
    "corporate_action_treatment",
    "units",
    "timezone",
    "coverage_start",
    "coverage_end",
    "delivery_mechanism",
    "manual_export_date",
    "source_contract_eligible",
    "predictive_pit_eligible",
    "reconciliation_source",
    "qualification_status",
    "blocking_reason",
]

REQUIRED_MAPPING_FIELDS = [
    "etf_instrument",
    "target_benchmark_instrument",
    "market_proxy_instrument",
    "target_leverage",
    "directionality",
    "is_proxy_underlying",
    "proxy_relationship_description",
    "benchmark_source_authority",
    "benchmark_exact_or_proxy",
]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def validate_benchmark_mapping(row: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_MAPPING_FIELDS if field not in row or _blank(row.get(field))]
    if missing:
        return {
            "mapping_status": "blocked_by_mapping",
            "benchmark_exact_or_proxy": str(row.get("benchmark_exact_or_proxy", "")),
            "blocking_reason": f"missing_fields:{','.join(missing)}",
        }

    etf = str(row.get("etf_instrument", "")).upper()
    target = str(row.get("target_benchmark_instrument", "")).upper()
    proxy = str(row.get("market_proxy_instrument", "")).upper()
    exact_or_proxy = str(row.get("benchmark_exact_or_proxy", ""))
    is_proxy_underlying = _truthy(row.get("is_proxy_underlying"))

    if etf not in {"TQQQ", "SQQQ"}:
        return {"mapping_status": "blocked_by_mapping", "benchmark_exact_or_proxy": exact_or_proxy, "blocking_reason": "unsupported_etf"}
    if target != "NDX":
        return {"mapping_status": "blocked_by_mapping", "benchmark_exact_or_proxy": exact_or_proxy, "blocking_reason": "target_benchmark_must_be_NDX"}
    if proxy != "QQQ":
        return {"mapping_status": "blocked_by_mapping", "benchmark_exact_or_proxy": exact_or_proxy, "blocking_reason": "market_proxy_must_be_QQQ"}
    if is_proxy_underlying:
        return {"mapping_status": "blocked_by_mapping", "benchmark_exact_or_proxy": exact_or_proxy, "blocking_reason": "qqq_cannot_be_exact_underlying"}
    if exact_or_proxy != "benchmark_exact":
        return {"mapping_status": "blocked_by_mapping", "benchmark_exact_or_proxy": exact_or_proxy, "blocking_reason": "leveraged_etf_target_must_be_benchmark_exact"}
    return {"mapping_status": "valid", "benchmark_exact_or_proxy": exact_or_proxy, "blocking_reason": ""}


def validate_legacy_proxy_fixture(row: dict[str, Any]) -> dict[str, Any]:
    underlying = str(row.get("underlying_instrument", "")).upper()
    legacy = _truthy(row.get("legacy_proxy_fixture"))
    synthetic = _truthy(row.get("is_synthetic_fixture"))
    if underlying == "QQQ" and legacy and synthetic:
        return {"mapping_status": "synthetic_fixture_only", "not_for_real_data_readiness": True}
    if underlying == "QQQ":
        return {"mapping_status": "blocked_by_mapping", "not_for_real_data_readiness": True}
    return {"mapping_status": "not_legacy_proxy_fixture", "not_for_real_data_readiness": False}


def classify_source(record: dict[str, Any]) -> dict[str, Any]:
    if _truthy(record.get("unresolved_reconciliation_break")):
        return _classified(BLOCKED_QUALITY, False, "unresolved_material_reconciliation_break")
    if str(record.get("availability_evidence_type", "")).lower() in {"unknown", "operator_unverified", ""}:
        return _classified(DESCRIPTIVE_ONLY, False, "historical_availability_unproven")
    if _truthy(record.get("current_revised_export_only")):
        return _classified(DESCRIPTIVE_ONLY, False, "current_revised_history_only")

    has_authority = str(record.get("source_authority_type", "")) in {"issuer", "benchmark_provider", "licensed_vendor"}
    has_publication_time = _truthy(record.get("publication_timestamp_available"))
    has_vintage = _truthy(record.get("historical_vintage_available"))
    has_revision = _truthy(record.get("revision_history_available"))
    has_schedule = str(record.get("availability_evidence_type", "")) == "provider_documented_publication_schedule"
    has_evidence_ref = not _blank(record.get("availability_evidence_reference"))
    has_basis = str(record.get("raw_or_adjusted", "")) in {"raw", "adjusted", "raw_and_adjusted_separate"}
    has_ca_policy = str(record.get("corporate_action_treatment", "")) not in {"", "unknown"}

    if has_authority and has_publication_time and has_vintage and has_revision and has_basis and has_ca_policy:
        return _classified(GOLD, True, "")
    if has_authority and has_publication_time and has_schedule and has_evidence_ref and has_basis and has_ca_policy:
        return _classified(SILVER, True, "documented_schedule_without_full_vintage")
    if has_authority:
        return _classified(AUTHORITATIVE_UNPROVEN, False, "historical_vintage_or_publication_time_missing")
    return _classified(DESCRIPTIVE_ONLY, False, "source_authority_not_sufficient")


def _classified(status: str, predictive: bool, reason: str) -> dict[str, Any]:
    return {
        "qualification_status": status,
        "source_contract_eligible": status in PREDICTIVE_STATUSES or status == AUTHORITATIVE_UNPROVEN,
        "predictive_pit_eligible": predictive,
        "blocking_reason": reason,
    }


def validate_row_level_timing(row: dict[str, Any]) -> dict[str, Any]:
    decision = pd.Timestamp(row["decision_time_utc"])
    available = pd.Timestamp(row["available_at_timestamp"])
    revision_available = pd.Timestamp(row.get("revision_available_at_timestamp", row["available_at_timestamp"]))
    if available.tzinfo is None or revision_available.tzinfo is None or decision.tzinfo is None:
        return {"timing_status": BLOCKED_TIMING, "timing_reason": "timestamps_must_be_timezone_aware"}
    if available > decision:
        return {"timing_status": BLOCKED_TIMING, "timing_reason": "available_after_decision_time"}
    if revision_available > decision:
        return {"timing_status": BLOCKED_TIMING, "timing_reason": "later_revision_unavailable_at_decision_time"}
    return {"timing_status": "eligible", "timing_reason": ""}


def describe_single_decision_time_role() -> dict[str, Any]:
    return {
        "single_decision_time_allowed_for": [
            "CSV schema validation",
            "type validation",
            "path containment",
            "manifest hash validation",
            "generic timestamp ordering checks",
        ],
        "single_decision_time_not_allowed_for": [
            "historical row-level timing eligibility",
            "historical AUM selection",
            "revision eligibility",
            "decision-date coverage",
            "predictive Phase 1 readiness",
            "Phase 2 admission",
        ],
    }


def detect_price_basis_mismatch(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    if str(primary.get("raw_or_adjusted", "")) != str(secondary.get("raw_or_adjusted", "")):
        return {"reconciliation_status": "blocked", "reason": "raw_adjusted_mismatch"}
    return {"reconciliation_status": "matched", "reason": ""}


def resolve_split_discontinuity(row: dict[str, Any], ledger: list[dict[str, Any]]) -> dict[str, Any]:
    instrument = str(row.get("instrument", ""))
    date = str(row.get("effective_date", ""))
    for action in ledger:
        if str(action.get("instrument", "")) == instrument and str(action.get("effective_date", "")) == date and str(action.get("action_type", "")) == "split":
            return {"reconciliation_status": "resolved_by_split_ledger", "corporate_action_id": action.get("corporate_action_id", "")}
    return {"reconciliation_status": "blocked", "reason": "missing_split_ledger_entry"}


def compare_aum_nav_shares(row: dict[str, Any], tolerance: float = 0.005) -> dict[str, Any]:
    aum = float(row["aum_usd"])
    shares_nav = float(row["shares_outstanding"]) * float(row["nav_per_share"])
    rel = abs(aum - shares_nav) / max(abs(aum), 1.0)
    return {
        "aum_relative_difference": rel,
        "reconciliation_status": "matched" if rel <= tolerance else "diagnostic_difference_retained",
    }


def write_artifact_manifest(artifact_paths: list[Path], manifest_path: Path) -> dict[str, Any]:
    manifest = {
        "artifact_version": QUALIFICATION_VERSION,
        "files": [{"path": str(path.as_posix()), "sha256": file_sha256(path)} for path in artifact_paths],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify_artifact_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    failures = []
    for entry in manifest.get("files", []):
        path = base / Path(str(entry["path"])).name
        if not path.exists():
            failures.append({"path": str(path), "reason": "missing"})
        elif file_sha256(path) != entry.get("sha256"):
            failures.append({"path": str(path), "reason": "sha256_mismatch"})
    return {"manifest_status": "valid" if not failures else "tampered", "failures": failures}
