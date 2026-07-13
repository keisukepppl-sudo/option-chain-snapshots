from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from morita_unified_flow_v3_8_pit_band_recovery import engine as e


def test_01_safety_flags_block_execution():
    fields = e.safety_fields()
    assert fields["research_only"] is True
    assert fields["execution_allowed"] is False
    assert fields["live_order_allowed"] is False
    assert fields["broker_access_allowed"] is False
    assert fields["account_access_allowed"] is False


def test_02_options_and_thresholds_disabled():
    fields = e.safety_fields()
    assert fields["options_modeled"] is False
    assert fields["thresholds_optimized"] is False
    assert fields["consumable_by_production"] is False


def test_03_source_whitelist_marks_tier_c_diagnostic_only():
    wl = e.source_whitelist()
    c = wl[wl["tier"].eq("C_DIAGNOSTIC_ONLY")]
    assert not c["allowed_for_primary"].any()


def test_04_missing_eps_maps_to_revenue_bridge_blocker():
    row = pd.Series({"quality": "UNAVAILABLE", "blocking_fields": "EPS_low|EPS_high|diluted_shares|reference_multiple|lineage"})
    assert e.blocking_reason_from_row(row) == "MISSING_REVENUE_BRIDGE"


def test_05_incomplete_vt_is_not_valid():
    row = pd.Series({"quality": "V_T_INCOMPLETE", "V_t": ""})
    assert e.row_vt_blocker(row) in {"MISSING_REVENUE_BRIDGE", "V_T_NOT_PER_SHARE"}


def test_06_registry_quality_d_is_not_production_eligible():
    inputs = {"v37_registry": pd.DataFrame([{"ticker": "AMAT", "session_date": "2026-07-10"}])}
    out = e.registry_outputs(inputs, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())["pit_band_registry_v3_8.csv"]
    assert out["registry_quality"].iloc[0] == "QUALITY_D_UNUSABLE"
    assert not out["production_eligible"].any()


def test_07_replay_keeps_band_unavailable_blocked():
    registry = pd.DataFrame([{"ticker": "AMAT", "valid_from": "2026-07-10", "registry_quality": "QUALITY_D_UNUSABLE", "row_blocker": "NO_VALID_A"}])
    daily = e.replay_outputs({}, registry)["unified_flow_v3_8_daily_state.csv"]
    assert daily["unified_state"].iloc[0] == "BAND_UNAVAILABLE"
    assert not daily["direct_long_to_short_allowed"].any()


def test_08_policy_audit_preserves_break_rules():
    registry = pd.DataFrame([{"ticker": "AMAT", "valid_from": "2026-07-10", "registry_quality": "QUALITY_D_UNUSABLE", "row_blocker": "NO_VALID_A"}])
    policy = e.replay_outputs({}, registry)["unified_flow_v3_8_policy_matrix_audit.csv"]
    assert policy["pass"].all()
    assert "close break to Flat" in set(policy["policy_check"])


def test_09_sa_receipt_counts_reconciled_in_receipt(tmp_path):
    inputs = {
        "sa_receipt": {"s_count": 309, "a_count": 504, "signal_rows": 813, "base_candidate_rows": 1147},
        "v37_receipt": {"valid_pit_band_count": 0},
        "episodes": pd.DataFrame(),
    }
    tables = {
        "pit_band_registry_v3_8.csv": pd.DataFrame([{"registry_quality": "QUALITY_D_UNUSABLE"}]),
        "valuation_snapshot_Vt_v3_8.csv": pd.DataFrame([{"coverage_grade": "D_UNUSABLE"}]),
        "observed_A_by_episode_v3_8.csv": pd.DataFrame([{"valid_A": False}]),
        "unified_flow_v3_8_daily_state.csv": pd.DataFrame([{"unified_state": "BAND_UNAVAILABLE"}]),
        "future_information_audit_v3_8.csv": pd.DataFrame([{"future_information_detected": False}]),
        "A_stability_by_ticker_v3_8.csv": pd.DataFrame([{"A_stability_label": "INSUFFICIENT_HISTORY"}]),
        "B_stability_by_cluster_v3_8.csv": pd.DataFrame([{"valid_B": False}]),
        "absorption_event_labels_v3_8.csv": pd.DataFrame([{"absorption_label_status": "BLOCKED"}]),
    }
    receipt = e.build_receipt(tmp_path, tmp_path, inputs, tables, cycles=3)
    assert receipt["S_signal_count_reconciled"] == 309
    assert receipt["A_signal_count_reconciled"] == 504
    assert receipt["highest_milestone"] == "M1_REGISTRY_SCHEMA_ACTIVATED"


def test_10_required_outputs_include_bundle_and_receipt():
    assert "morita_unified_flow_v3_8_chatgpt_review_bundle.md" in e.REQUIRED_OUTPUTS
    assert "run_receipt_v3_8.json" in e.REQUIRED_OUTPUTS

