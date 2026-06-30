from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

import market_bomb_flow_pressure_source_qualification_v1 as q


REPO_ROOT = Path(__file__).resolve().parents[1]


def _valid_mapping(etf: str = "TQQQ") -> dict[str, object]:
    return {
        "etf_instrument": etf,
        "target_benchmark_instrument": "NDX",
        "market_proxy_instrument": "QQQ",
        "target_leverage": 3.0 if etf == "TQQQ" else -3.0,
        "directionality": "long" if etf == "TQQQ" else "inverse",
        "is_proxy_underlying": False,
        "proxy_relationship_description": "QQQ is tradable proxy only",
        "benchmark_source_authority": "ProShares fund documentation",
        "benchmark_exact_or_proxy": "benchmark_exact",
    }


def _source(**overrides: object) -> dict[str, object]:
    base = {
        "source_authority_type": "issuer",
        "historical_vintage_available": False,
        "publication_timestamp_available": False,
        "revision_history_available": False,
        "availability_evidence_type": "unknown",
        "availability_evidence_reference": "",
        "raw_or_adjusted": "raw",
        "corporate_action_treatment": "split_ledger",
        "current_revised_export_only": False,
        "unresolved_reconciliation_break": False,
    }
    base.update(overrides)
    return base


def test_tqqq_ndx_exact_mapping_passes() -> None:
    assert q.validate_benchmark_mapping(_valid_mapping("TQQQ"))["mapping_status"] == "valid"


def test_sqqq_ndx_exact_mapping_passes() -> None:
    assert q.validate_benchmark_mapping(_valid_mapping("SQQQ"))["mapping_status"] == "valid"


def test_qqq_is_proxy_not_underlying() -> None:
    row = _valid_mapping("TQQQ")
    row["is_proxy_underlying"] = True
    result = q.validate_benchmark_mapping(row)
    assert result["mapping_status"] == "blocked_by_mapping"
    assert result["blocking_reason"] == "qqq_cannot_be_exact_underlying"


def test_tqqq_to_qqq_exact_production_mapping_rejects() -> None:
    row = _valid_mapping("TQQQ")
    row["target_benchmark_instrument"] = "QQQ"
    result = q.validate_benchmark_mapping(row)
    assert result["mapping_status"] == "blocked_by_mapping"
    assert result["blocking_reason"] == "target_benchmark_must_be_NDX"


def test_legacy_qqq_proxy_fixture_is_synthetic_only() -> None:
    result = q.validate_legacy_proxy_fixture(
        {"underlying_instrument": "QQQ", "legacy_proxy_fixture": True, "is_synthetic_fixture": True}
    )
    assert result["mapping_status"] == "synthetic_fixture_only"
    assert result["not_for_real_data_readiness"] is True


def test_benchmark_exact_metadata_is_returned() -> None:
    result = q.validate_benchmark_mapping(_valid_mapping("SQQQ"))
    assert result["benchmark_exact_or_proxy"] == "benchmark_exact"


def test_issuer_csv_without_vintage_is_not_gold() -> None:
    result = q.classify_source(_source(availability_evidence_type="source_documentation"))
    assert result["qualification_status"] == q.AUTHORITATIVE_UNPROVEN
    assert result["predictive_pit_eligible"] is False


def test_documented_schedule_can_be_silver_with_evidence_fields() -> None:
    result = q.classify_source(
        _source(
            publication_timestamp_available=True,
            availability_evidence_type="provider_documented_publication_schedule",
            availability_evidence_reference="issuer methodology PDF",
        )
    )
    assert result["qualification_status"] == q.SILVER
    assert result["predictive_pit_eligible"] is True


def test_vendor_history_without_vintage_cannot_claim_predictive_pit() -> None:
    result = q.classify_source(
        _source(source_authority_type="licensed_vendor", publication_timestamp_available=True, availability_evidence_type="source_documentation")
    )
    assert result["qualification_status"] == q.AUTHORITATIVE_UNPROVEN
    assert result["predictive_pit_eligible"] is False


def test_vendor_sample_with_publication_timestamp_and_revision_id_can_be_gold() -> None:
    result = q.classify_source(
        _source(
            source_authority_type="licensed_vendor",
            historical_vintage_available=True,
            publication_timestamp_available=True,
            revision_history_available=True,
            availability_evidence_type="provider_versioned_export",
            raw_or_adjusted="raw_and_adjusted_separate",
        )
    )
    assert result["qualification_status"] == q.GOLD
    assert result["predictive_pit_eligible"] is True


def test_current_export_date_cannot_be_historical_available_at() -> None:
    result = q.classify_source(_source(current_revised_export_only=True, availability_evidence_type="source_documentation"))
    assert result["qualification_status"] == q.DESCRIPTIVE_ONLY
    assert "current_revised_history_only" in result["blocking_reason"]


def test_unknown_timing_is_descriptive_only() -> None:
    result = q.classify_source(_source(availability_evidence_type="unknown"))
    assert result["qualification_status"] == q.DESCRIPTIVE_ONLY


def test_single_decision_time_does_not_grant_row_level_eligibility() -> None:
    role = q.describe_single_decision_time_role()
    assert "manifest hash validation" in role["single_decision_time_allowed_for"]
    assert "historical row-level timing eligibility" in role["single_decision_time_not_allowed_for"]


def test_2026_revision_unavailable_for_2022_decision_row() -> None:
    result = q.validate_row_level_timing(
        {
            "decision_time_utc": "2022-01-03T22:00:00Z",
            "available_at_timestamp": "2022-01-03T21:30:00Z",
            "revision_available_at_timestamp": "2026-01-01T00:00:00Z",
        }
    )
    assert result["timing_status"] == q.BLOCKED_TIMING
    assert result["timing_reason"] == "later_revision_unavailable_at_decision_time"


def test_phase2_admission_cannot_rely_on_single_provider_contract_validation() -> None:
    role = q.describe_single_decision_time_role()
    assert "Phase 2 admission" in role["single_decision_time_not_allowed_for"]


def test_raw_adjusted_mismatch_detection() -> None:
    result = q.detect_price_basis_mismatch({"raw_or_adjusted": "raw"}, {"raw_or_adjusted": "adjusted"})
    assert result["reconciliation_status"] == "blocked"
    assert result["reason"] == "raw_adjusted_mismatch"


def test_split_ledger_resolves_synthetic_discontinuity() -> None:
    result = q.resolve_split_discontinuity(
        {"instrument": "TQQQ", "effective_date": "2022-01-13"},
        [{"corporate_action_id": "SPLIT_TQQQ_20220113", "instrument": "TQQQ", "effective_date": "2022-01-13", "action_type": "split"}],
    )
    assert result["reconciliation_status"] == "resolved_by_split_ledger"


def test_unresolved_discrepancy_blocks_predictive_qualification() -> None:
    result = q.classify_source(_source(unresolved_reconciliation_break=True))
    assert result["qualification_status"] == q.BLOCKED_QUALITY
    assert result["predictive_pit_eligible"] is False


def test_aum_vs_shares_nav_difference_is_retained_not_overwritten() -> None:
    result = q.compare_aum_nav_shares({"aum_usd": 100.0, "shares_outstanding": 10.0, "nav_per_share": 9.0})
    assert result["reconciliation_status"] == "diagnostic_difference_retained"
    assert result["aum_relative_difference"] > 0


def test_secondary_source_is_diagnostic_only() -> None:
    plan = (REPO_ROOT / "docs" / "flow_pressure_qqq_reconciliation_plan.md").read_text(encoding="utf-8")
    assert "Secondary vendor values are diagnostic only" in plan


def test_persisted_qualification_artifact_tamper_detection(tmp_path: Path) -> None:
    artifact = tmp_path / "qqq_source_qualification_report.md"
    artifact.write_text("original", encoding="utf-8")
    manifest = tmp_path / "qualification_content_manifest.json"
    q.write_artifact_manifest([artifact], manifest)
    assert q.verify_artifact_manifest(manifest)["manifest_status"] == "valid"
    artifact.write_text("tampered", encoding="utf-8")
    assert q.verify_artifact_manifest(manifest)["manifest_status"] == "tampered"


def test_raw_provider_data_not_tracked_by_git() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "market_bomb_history"], cwd=REPO_ROOT, text=True)
    assert tracked.strip() == ""


def test_required_output_matrix_has_schema_fields() -> None:
    matrix = pd.read_csv(REPO_ROOT / "outputs" / "flow_pressure_phase1_3a_precision_data_sourcing" / "qqq_source_qualification_matrix.csv")
    assert set(q.REQUIRED_MATRIX_FIELDS).issubset(matrix.columns)
    assert "historical_descriptive_only" in set(matrix["qualification_status"])


def test_phase1_3a_policy_blocks_release_backtest_notification_and_trading() -> None:
    policy = json.loads((REPO_ROOT / "market_bomb_config" / "flow_pressure_source_qualification_v1_policy.json").read_text(encoding="utf-8"))
    assert policy["actionization_allowed"] is False
    assert policy["phase1_3_readiness_allowed"] is False
    assert policy["phase2_study_allowed"] is False
    assert policy["raw_provider_data_policy"]["raw_provider_commit_allowed"] is False
