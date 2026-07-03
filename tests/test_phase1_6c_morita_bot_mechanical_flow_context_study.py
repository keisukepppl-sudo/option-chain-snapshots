from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_phase1_6c_morita_bot_mechanical_flow_context_study as study


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _manifest(path: Path, manifest_name: str) -> None:
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and child.name != manifest_name:
            files.append({"relative_path": child.relative_to(path).as_posix(), "sha256": study.file_sha256(child), "bytes": child.stat().st_size})
    _write_json(path / manifest_name, {"files": files, "content_set_hash": study.text_hash(json.dumps(files, sort_keys=True))})


def _dates(n: int = 90) -> list[pd.Timestamp]:
    return list(pd.bdate_range("2024-01-02", periods=n))


def _phase16b(root: Path, n: int = 90, missing_context_tail: int = 0) -> Path:
    out = root / "phase16b"
    dates = _dates(n)
    rows = []
    cta = ["cta_all_risk_on", "cta_all_risk_off", "cta_mixed", "cta_incomplete"]
    vol = ["vol_all_increase_risk", "vol_all_reduce_risk", "vol_mixed_or_unchanged", "vol_incomplete"]
    etf = ["etf_sensitivity_q1_to_q3", "etf_sensitivity_q4_ex_post", "etf_sensitivity_unavailable"]
    for i, date in enumerate(dates[: n - missing_context_tail]):
        etf_cat = etf[i % len(etf)]
        rows.append(
            {
                "observation_date": date.strftime("%Y-%m-%d"),
                "next_effective_session": (date + pd.offsets.BDay(1)).strftime("%Y-%m-%d"),
                "cta_consensus_category": cta[i % len(cta)],
                "vol_change_consensus_category": vol[i % len(vol)],
                "combined_mechanical_sensitivity_ex_post_quartile": etf_cat,
                "combined_scale_status": "combined_exact_prior_session_capital_available" if etf_cat != "etf_sensitivity_unavailable" else "unavailable",
            }
        )
    _write_csv(out / study.PHASE16B_PANEL, rows)
    _write_json(
        out / study.PHASE16B_RECEIPT,
        {
            "run_status": "phase1_6b_cross_module_downside_completed",
            "run_id": "phase16b_fixture",
            "study_spec_id": "phase1_6b_ndx_cross_module_downside_v1",
            "repository_commit_sha": "a" * 40,
            "research_only": True,
            "actionization_allowed": False,
            "not_a_trading_signal": True,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
        },
    )
    (out / "phase1_6b_cross_module_downside_summary.md").write_text("summary\n", encoding="utf-8")
    (out / "phase1_6b_cross_module_downside_limitations.md").write_text("limitations\n", encoding="utf-8")
    _manifest(out, study.PHASE16B_MANIFEST)
    return out


def _morita_artifact(root: Path, n: int = 90, with_option: bool = False) -> Path:
    artifact = root / "morita_artifact"
    dates = _dates(n)
    signals = []
    outcomes = []
    ranks = ["S", "A", "B"]
    themes = ["Software", "Semiconductor", "AI Infrastructure"]
    for i, date in enumerate(dates):
        sid = f"sig_{i:03d}"
        entry = date + pd.offsets.BDay(1)
        signals.append(
            {
                "source_signal_id": sid,
                "decision_date": date.strftime("%Y-%m-%d"),
                "decision_ts": f"{date.strftime('%Y-%m-%d')}T21:00:00Z",
                "entry_session": entry.strftime("%Y-%m-%d"),
                "symbol": f"SYM{i % 12:02d}",
                "rank": ranks[i % 3],
                "strategy": "Breakout Momentum",
                "theme": themes[i % 3],
                "rule_version": "morita_fixture_v1",
                "config_hash": "cfg_hash",
                "source_run_id": "morita_fixture_run",
                "source_manifest_hash": "source_manifest_hash",
            }
        )
        outcome = {
            "source_signal_id": sid,
            "outcome_status": "complete",
            "bdl_breach": str(i % 5 == 0).lower(),
            "timeout_under": str(i % 7 == 0).lower(),
            "plus5_10": str(i % 4 == 0).lower(),
            "hold_sessions": str((i % 10) + 1),
            "exit_category": "profit_target" if i % 4 == 0 else "timeout_10_sessions_under_threshold",
        }
        if with_option:
            outcome["opt125"] = str(i % 4 == 0).lower()
            outcome["opt_return"] = str(1.25 if i % 4 == 0 else -0.35)
        outcomes.append(outcome)
    _write_csv(artifact / "signals.csv", signals)
    _write_csv(artifact / "outcomes.csv", outcomes)
    optional = {}
    if with_option:
        optional = {
            "option_profit_target_125pct_reached": "opt125",
            "option_return_at_declared_exit": "opt_return",
        }
    _write_json(
        artifact / "source_schema_map.json",
        {
            "signal_file": "signals.csv",
            "outcome_file": "outcomes.csv",
            "source_rule_version": "morita_fixture_v1",
            "signal_columns": {
                "signal_id": "source_signal_id",
                "signal_decision_date": "decision_date",
                "signal_decision_timestamp_utc": "decision_ts",
                "entry_session": "entry_session",
                "underlying_symbol": "symbol",
                "signal_rank": "rank",
                "strategy_family": "strategy",
                "theme": "theme",
                "source_rule_version": "rule_version",
                "source_rule_config_hash": "config_hash",
                "source_run_id": "source_run_id",
                "source_manifest_hash": "source_manifest_hash",
            },
            "outcome_columns": {
                "signal_id": "source_signal_id",
                "outcome_status": "outcome_status",
                "breakout_day_low_breach_before_timeout": "bdl_breach",
                "timeout_10_sessions_under_threshold": "timeout_under",
                "reached_plus_5pct_within_10_sessions": "plus5_10",
                "holding_sessions_at_exit_or_timeout": "hold_sessions",
                "exit_event_category": "exit_category",
            },
            "optional_outcome_columns": optional,
        },
    )
    _write_json(
        artifact / "run_receipt.json",
        {
            "run_status": "morita_fixture_completed",
            "run_id": "morita_fixture_run",
            "source_module": "morita_fixture",
            "source_rule_version": "morita_fixture_v1",
            "repository_commit_sha": "b" * 40,
            "module_source_sha256": "c" * 64,
            "research_only": True,
            "actionization_allowed": False,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
        },
    )
    _manifest(artifact, "content_manifest.json")
    return artifact


def test_completed_study_outputs_manifest_fixed_grid_and_no_raw_fields(tmp_path: Path) -> None:
    phase = _phase16b(tmp_path)
    morita = _morita_artifact(tmp_path, with_option=True)
    out = tmp_path / "out"
    receipt = study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, morita, out)
    assert receipt["run_status"] == "phase1_6c_morita_bot_mechanical_flow_context_completed"
    assert study.verify_output_manifest(out)["run_id"] == receipt["run_id"]
    for name in study.REQUIRED_OUTPUT_FILES:
        assert (out / name).exists()
    joint = pd.read_csv(out / "morita_bot_joint_context_summary.csv")
    assert len(joint) == 4 * 4 * 3 * 7
    assert set(joint["not_a_trade_filter"].astype(str).str.lower()) == {"true"}
    panel_cols = set(pd.read_csv(out / "morita_bot_canonical_signal_outcome_panel.csv", nrows=0).columns.str.lower())
    assert not (panel_cols & study.FORBIDDEN_OUTPUT_FIELDS)


def test_missing_morita_source_creates_controlled_blocked_report(tmp_path: Path) -> None:
    phase = _phase16b(tmp_path)
    out = tmp_path / "blocked"
    receipt = study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, None, out)
    assert receipt["run_status"] == "phase1_6c_morita_bot_mechanical_flow_context_source_validation_blocked"
    assert "morita_bot_source_artifact_not_found" in receipt["block_codes"]
    assert pd.read_csv(out / "morita_bot_canonical_signal_outcome_panel.csv").empty
    assert study.verify_output_manifest(out)


def test_phase16b_manifest_receipt_and_safety_flags_required(tmp_path: Path) -> None:
    phase = _phase16b(tmp_path)
    (phase / study.PHASE16B_PANEL).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="phase1_6c_phase1_6b_source_manifest_invalid"):
        study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, _morita_artifact(tmp_path), tmp_path / "out")

    phase = _phase16b(tmp_path / "badflag")
    receipt = json.loads((phase / study.PHASE16B_RECEIPT).read_text(encoding="utf-8"))
    receipt["actionization_allowed"] = True
    _write_json(phase / study.PHASE16B_RECEIPT, receipt)
    _manifest(phase, study.PHASE16B_MANIFEST)
    with pytest.raises(SystemExit, match="phase1_6c_phase1_6b_safety_flag_mismatch"):
        study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, _morita_artifact(tmp_path / "m2"), tmp_path / "out2")


def test_morita_source_validation_blocks_aggregate_missing_schema_duplicate_rank_and_timing(tmp_path: Path) -> None:
    morita = _morita_artifact(tmp_path)
    (morita / "source_schema_map.json").unlink()
    _manifest(morita, "content_manifest.json")
    with pytest.raises(SystemExit, match="morita_bot_outcome_contract_incomplete"):
        study.validate_morita_bot_run_artifact(morita)

    morita = _morita_artifact(tmp_path / "dup")
    rows = list(csv.DictReader((morita / "signals.csv").open(newline="", encoding="utf-8")))
    rows[1]["source_signal_id"] = rows[0]["source_signal_id"]
    _write_csv(morita / "signals.csv", rows)
    _manifest(morita, "content_manifest.json")
    with pytest.raises(SystemExit, match="morita_bot_duplicate_signal_id"):
        study.validate_morita_bot_run_artifact(morita)

    morita = _morita_artifact(tmp_path / "rank")
    rows = list(csv.DictReader((morita / "signals.csv").open(newline="", encoding="utf-8")))
    rows[0]["rank"] = "C"
    _write_csv(morita / "signals.csv", rows)
    _manifest(morita, "content_manifest.json")
    with pytest.raises(SystemExit, match="invalid_rank"):
        study.validate_morita_bot_run_artifact(morita)

    morita = _morita_artifact(tmp_path / "time")
    rows = list(csv.DictReader((morita / "signals.csv").open(newline="", encoding="utf-8")))
    rows[0]["entry_session"] = rows[0]["decision_date"]
    _write_csv(morita / "signals.csv", rows)
    _manifest(morita, "content_manifest.json")
    with pytest.raises(SystemExit, match="morita_bot_entry_session_invalid"):
        study.validate_morita_bot_run_artifact(morita)


def test_context_alignment_uses_observation_date_and_gate_blocks(tmp_path: Path) -> None:
    phase = _phase16b(tmp_path, missing_context_tail=20)
    morita = _morita_artifact(tmp_path)
    receipt = study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, morita, tmp_path / "out")
    assert receipt["run_status"] == "phase1_6c_morita_bot_mechanical_flow_context_alignment_inadequate"

    phase = _phase16b(tmp_path / "ok")
    morita = _morita_artifact(tmp_path / "ok")
    out = tmp_path / "ok_out"
    study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, morita, out)
    panel = pd.read_csv(out / "morita_bot_canonical_signal_outcome_panel.csv")
    source_phase = pd.read_csv(phase / study.PHASE16B_PANEL)
    first_date = panel.iloc[0]["signal_decision_date"]
    expected_cta = source_phase.loc[source_phase["observation_date"] == first_date, "cta_consensus_category"].iloc[0]
    assert panel.iloc[0]["cta_context_category"] == expected_cta


def test_sample_gates_optional_option_unavailable_and_available(tmp_path: Path) -> None:
    phase = _phase16b(tmp_path, n=90)
    morita = _morita_artifact(tmp_path, n=90, with_option=False)
    out = tmp_path / "out"
    receipt = study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, morita, out)
    assert receipt["run_status"] == "phase1_6c_morita_bot_mechanical_flow_context_option_outcomes_unavailable"
    cond = pd.read_csv(out / "morita_bot_context_condition_summary.csv")
    assert (cond.loc[cond["signal_count"] < 20, "metrics_available"].astype(str).str.lower() == "false").all()
    assert "option_outcome_not_available_from_source" in set(cond["option_metrics_unavailable_reason"])

    phase = _phase16b(tmp_path / "opt", n=90)
    morita = _morita_artifact(tmp_path / "opt", n=90, with_option=True)
    out = tmp_path / "opt_out"
    study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, morita, out)
    cond = pd.read_csv(out / "morita_bot_context_condition_summary.csv")
    assert cond["option_metrics_available"].astype(str).str.lower().eq("true").any()


def test_concentration_diagnostics_manifest_tamper_output_dir_reject_and_no_forbidden_code(tmp_path: Path) -> None:
    phase = _phase16b(tmp_path)
    morita = _morita_artifact(tmp_path, with_option=True)
    out = tmp_path / "out"
    study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, morita, out)
    diag = pd.read_csv(out / "morita_bot_context_concentration_diagnostics.csv")
    assert {"concentration_present", "concentration_not_present", "concentration_not_assessed"} >= set(diag["underlying_concentration_diagnostic"])
    (out / "morita_bot_window_coverage.csv").write_text("tamper\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="phase1_6c_output_manifest_invalid"):
        study.verify_output_manifest(out)
    with pytest.raises(SystemExit, match="phase1_6c_output_dir_rejected"):
        study.build_study("phase1_6c_morita_bot_mechanical_flow_context_v1", phase, morita, tmp_path / "market_bomb_history" / "bad")
    source = (REPO_ROOT / "scripts" / "build_phase1_6c_morita_bot_mechanical_flow_context_study.py").read_text(encoding="utf-8").lower()
    for needle in ["requests.", "urllib", "socket.", "selenium", "playwright", "submit_order", "cancel_order", "composite market score"]:
        assert needle not in source


def test_inventory_validate_cli_and_no_category_merging(tmp_path: Path) -> None:
    morita = _morita_artifact(tmp_path, with_option=True)
    validated = study.validate_morita_bot_run_artifact(morita)
    assert validated["status"] == "morita_bot_source_artifact_eligible"
    inventory = study.inspect_morita_bot_source_artifacts(tmp_path)
    assert inventory["candidate_count"] >= 1
    assert set(study.load_spec("phase1_6c_morita_bot_mechanical_flow_context_v1")["context_categories"]["etf"]) == {
        "etf_sensitivity_q1_to_q3",
        "etf_sensitivity_q4_ex_post",
        "etf_sensitivity_unavailable",
    }
