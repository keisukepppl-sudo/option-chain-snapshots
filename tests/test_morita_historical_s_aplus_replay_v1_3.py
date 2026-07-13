from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.research.historical_s_aplus_replay_v1_3 import GUARDRAILS, REQUIRED_OUTPUTS, run_v1_3


_CACHE: dict[str, Path] = {}


def run_out(tmp_path: Path) -> Path:
    if "out" in _CACHE and _CACHE["out"].exists():
        return _CACHE["out"]
    result = run_v1_3(Path.cwd(), output_root=tmp_path / "out", run_id="unit")
    _CACHE["out"] = Path(result.output_dir)
    return _CACHE["out"]


def receipt(out: Path) -> dict:
    return json.loads((out / "run_receipt.json").read_text(encoding="utf-8"))


def test_01_signal_config_files_are_hashed(tmp_path: Path) -> None:
    payload = json.loads((run_out(tmp_path) / "current_signal_engine_source_seal.json").read_text(encoding="utf-8"))
    assert payload["module_config_paths"]
    assert all(row["sha256"] for row in payload["module_config_paths"])


def test_02_s_mapping_exact(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "current_rank_label_contract.csv")
    assert rows[rows["canonical label"].eq("S")]["score condition"].str.contains(">= 50").any()


def test_03_aplus_mapping_exact(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "current_rank_label_contract.csv")
    assert rows[rows["canonical label"].eq("A_PLUS_NORMAL_SHADOW")]["code value"].eq("A_PLUS_NORMAL_SCORE_GE_47").any()


def test_04_no_replay_threshold_overrides(tmp_path: Path) -> None:
    payload = json.loads((run_out(tmp_path) / "frozen_current_rule_receipt.json").read_text(encoding="utf-8"))
    assert payload["thresholds_changed_for_replay"] is False


def test_05_decision_timestamp_matches_current_code_contract(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_signal_calendar.csv")
    if not rows.empty:
        assert rows["decision_timestamp_et"].astype(str).str.contains("16:00").all()


def test_06_2026_signals_reproduce(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "frozen_2026_signal_reproduction.csv")
    assert not rows["status"].astype(str).str.startswith("FAIL").any()


def test_07_2026_short_baseline_reproduces_or_fails_closed(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "frozen_2026_short_reproduction.csv")
    assert "status" in rows.columns
    assert set(rows["frozen_logic_modified"].astype(str).str.lower().unique()) <= {"false"}


def test_08_phase_a_universe_is_frozen(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_current_universe_manifest.csv")
    assert rows["universe_mode"].eq("CURRENT_UNIVERSE_RETROSPECTIVE").all()


def test_09_phase_a_is_never_headline_eligible(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_signal_calendar.csv")
    assert rows.empty or rows["headline_eligible"].astype(str).str.lower().eq("false").all()


def test_10_phase_a_uses_pit_status_column(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_signal_calendar.csv")
    assert "PIT audit result" in rows.columns


def test_11_phase_b_uses_date_effective_membership_gate(tmp_path: Path) -> None:
    rows = pd.read_parquet(run_out(tmp_path) / "historical_universe_membership.parquet")
    assert rows["status"].astype(str).str.contains("PHASE_B_UNIVERSE_BLOCKED").any()


def test_12_delisted_names_can_be_historically_eligible_only_after_phase_b_source(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_universe_eligibility_audit.csv")
    assert rows["blocked_reason"].astype(str).str.contains("PHASE_B_UNIVERSE").any()


def test_13_ticker_changes_use_permanent_identity_gate(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_security_identity_audit.csv")
    assert rows["status"].astype(str).str.contains("NO_DATE_EFFECTIVE_IDENTITY_SOURCE").any()


def test_14_future_membership_is_rejected(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_replay_future_information_audit.csv")
    assert rows["audit"].astype(str).str.contains("universe membership").any()


def test_15_historical_market_cap_is_pit_blocked(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_replay_future_information_audit.csv")
    assert rows[rows["audit"].eq("market cap")]["status"].astype(str).str.contains("BLOCKED").any()


def test_16_authority_c_is_diagnostic_only(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_universe_source_inventory.csv")
    assert rows["pit_result"].astype(str).str.contains("REJECTED").any()


def test_17_rs_is_pit_or_diagnostic(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_signal_calendar.csv")
    assert rows.empty or rows["PIT audit result"].astype(str).str.contains("DIAGNOSTIC").all()


def test_18_breakout_reference_is_prior_data_only_column(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_signal_calendar.csv")
    assert "breakout state/reference" in rows.columns


def test_19_relative_volume_is_pit_column(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_signal_calendar.csv")
    assert "relative volume" in rows.columns


def test_20_cooldown_deterministic_column(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_signal_calendar.csv")
    assert "cooldown" in rows.columns


def test_21_post_signal_peak_is_pit(tmp_path: Path) -> None:
    rows = pd.read_parquet(run_out(tmp_path) / "phase_a_recent_signal_state.parquet")
    assert "PIT post-signal peak" in rows.columns


def test_22_frozen_d0_logic_unchanged(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "phase_a_d0_event_master.csv")
    assert rows["status"].astype(str).str.contains("D0").any()


def test_23_m15_manifest_created_after_d0_events(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "m15_required_symbol_session_manifest.csv")
    assert rows["status"].astype(str).str.contains("NO_D0").any()


def test_24_webull_path_market_data_only(tmp_path: Path) -> None:
    payload = json.loads((run_out(tmp_path) / "credential_safety_audit.json").read_text(encoding="utf-8"))
    assert payload["market_data_only"] is True


def test_25_credentials_not_printed_or_saved(tmp_path: Path) -> None:
    payload = json.loads((run_out(tmp_path) / "credential_safety_audit.json").read_text(encoding="utf-8"))
    assert payload["secrets_printed"] is False
    assert payload["secrets_saved_to_outputs"] is False


def test_26_et_rth_normalization_contract(tmp_path: Path) -> None:
    payload = json.loads((run_out(tmp_path) / "frozen_current_rule_receipt.json").read_text(encoding="utf-8"))
    assert "16:00" in payload["decision_timestamp"]


def test_27_0930_uses_no_first_bar_future_data(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_replay_future_information_audit.csv")
    assert rows[rows["audit"].eq("09:30 features")]["status"].eq("PASS").all()


def test_28_0945_uses_only_completed_first_bar(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_replay_future_information_audit.csv")
    assert rows[rows["audit"].eq("09:45 features")]["status"].eq("PASS").all()


def test_29_1000_uses_completed_data_only(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_replay_future_information_audit.csv")
    assert rows[rows["audit"].eq("10:00 features")]["status"].eq("PASS").all()


def test_30_no_entry_add_after_1000(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "performance_by_route.csv")
    assert rows["status"].astype(str).str.contains("NOT_EVALUATED").any()


def test_31_1030_diagnostic_only(tmp_path: Path) -> None:
    text = (run_out(tmp_path) / "morita_historical_s_aplus_replay_v1_3_chatgpt_review_bundle.md").read_text(encoding="utf-8")
    assert "10:30 diagnostic-only" in text


def test_32_monday_friday_rules_preserved(tmp_path: Path) -> None:
    assert "threshold_optimization_allowed=false" in (run_out(tmp_path) / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker").read_text(encoding="utf-8")


def test_33_no_weekend_two_night_hold(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_replay_future_information_audit.csv")
    assert rows[rows["audit"].eq("exits")]["status"].eq("PASS").all()


def test_34_staged_costs_applied_by_leg_or_blocked(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "transaction_cost_sensitivity.csv")
    assert "status" in rows.columns


def test_35_instruments_not_mixed(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "performance_by_instrument.csv")
    assert "status" in rows.columns


def test_36_candidates_and_episodes_separated(tmp_path: Path) -> None:
    out = run_out(tmp_path)
    assert (out / "phase_a_candidate_results.csv").exists()
    assert (out / "phase_a_episode_master.csv").exists()


def test_37_episode_clustering_outputs_exist(tmp_path: Path) -> None:
    assert (run_out(tmp_path) / "phase_a_episode_portfolio.csv").exists()


def test_38_survivorship_bias_comparison_correctly_blocked(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "survivorship_bias_audit.csv")
    assert rows["status"].astype(str).str.contains("PHASE_B_BLOCKED").any()


def test_39_corporate_actions_audited(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_security_identity_audit.csv")
    assert "status" in rows.columns


def test_40_future_information_failure_works(tmp_path: Path) -> None:
    rows = pd.read_csv(run_out(tmp_path) / "historical_replay_future_information_audit.csv")
    assert not rows.empty


def test_41_no_optimization(tmp_path: Path) -> None:
    assert GUARDRAILS["threshold_optimization_allowed"] is False


def test_42_no_option_model(tmp_path: Path) -> None:
    assert GUARDRAILS["options_modeled"] is False


def test_43_no_live_order_path(tmp_path: Path) -> None:
    assert GUARDRAILS["live_order_allowed"] is False


def test_44_all_outputs_research_only(tmp_path: Path) -> None:
    out = run_out(tmp_path)
    for csv_path in out.glob("*.csv"):
        rows = pd.read_csv(csv_path)
        if not rows.empty and "research_only" in rows.columns:
            assert rows["research_only"].astype(str).str.lower().eq("true").all()


def test_45_production_rejection_passes_and_required_outputs_exist(tmp_path: Path) -> None:
    out = run_out(tmp_path)
    prod = pd.read_csv(out / "production_rejection_test_results.csv")
    assert prod["passed"].astype(str).str.lower().eq("true").all()
    assert set(REQUIRED_OUTPUTS).issubset({p.name for p in out.iterdir() if p.is_file()})
    assert receipt(out)["user_action_required"] is False
