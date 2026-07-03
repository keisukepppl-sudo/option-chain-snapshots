from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_phase1_6b_cross_module_downside_study as study


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
    _write_json(path / manifest_name, {"files": files, "content_set_hash": "synthetic"})


def _receipt(model: str, module: str) -> dict:
    payload = {
        "run_id": f"run_{model}",
        "model_spec_id": model,
        "source_manifest_hash": "source_hash",
        "model_spec_registry_hash": "registry_hash",
        "repository_commit_sha": "a" * 40,
        "module_source_sha256": "b" * 64,
        "module_name": module,
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "not_market_impact_estimate": True,
    }
    if module == "cta_transparent_trend_replication_v1":
        payload.update({"not_actual_cta_position_estimate": True, "not_actual_cta_flow_estimate": True})
    if module == "vol_control_transparent_replication_v1":
        payload.update({"not_actual_manager_flow_estimate": True, "benchmark_instrument": "NDX", "benchmark_mode": "ndx_exact_descriptive"})
    return payload


def _etf_receipt() -> dict:
    return {
        "run_id": "etf_run",
        "model_spec_id": study.ETF_MODEL,
        "benchmark_mode": "ndx_exact",
        "source_manifest_hash": "etf_source",
        "model_spec_registry_hash": "etf_registry",
        "repository_commit_sha": "c" * 40,
        "module_source_sha256": "d" * 64,
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "not_market_impact_estimate": True,
        "not_actual_creation_redemption_flow": True,
        "not_actual_investor_flow": True,
        "not_actual_manager_trade_estimate": True,
        "tqqq_lagged_capital_coverage_ratio": 1.0,
        "sqqq_lagged_capital_coverage_ratio": 1.0,
        "combined_overlap_coverage_ratio": 1.0,
    }


def _dates(n: int = 80) -> list[str]:
    return pd.bdate_range("2024-01-02", periods=n).strftime("%Y-%m-%d").tolist()


def _build_source_tree(root: Path, n: int = 80) -> dict:
    dates = _dates(n)
    etf = root / "etf"
    etf_rows = []
    for i, date in enumerate(dates):
        ret = ((i % 7) - 3) / 1000.0
        if i in {20, 45}:
            ret = -0.025
        tqqq = 1000.0 + i
        sqqq = 500.0 + i
        sensitivity = 6 * tqqq + 12 * sqqq
        etf_rows.append(
            {
                "observation_date": date,
                "prior_capital_observation_date_required": dates[max(i - 1, 0)],
                "benchmark_instrument": "NDX",
                "benchmark_exact_or_proxy": "benchmark_exact",
                "benchmark_return": ret,
                "tqqq_lagged_capital_usd": tqqq,
                "sqqq_lagged_capital_usd": sqqq,
                "tqqq_capital_source_basis": "reported_aum_and_shares_nav",
                "sqqq_capital_source_basis": "reported_aum_and_shares_nav",
                "tqqq_capital_observation_status": "exact_prior_session_capital_available",
                "sqqq_capital_observation_status": "exact_prior_session_capital_available",
                "tqqq_rebalance_notional_proxy": 6 * tqqq * ret,
                "sqqq_rebalance_notional_proxy": 12 * sqqq * ret,
                "combined_rebalance_notional_proxy": sensitivity * ret,
                "combined_scale_status": "combined_exact_prior_session_capital_available",
                "model_spec_id": study.ETF_MODEL,
                "source_manifest_hash": "etf_source",
                "run_id": "etf_run",
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
    _write_json(etf / study.ETF_RECEIPT, _etf_receipt())
    _write_csv(etf / study.ETF_DAILY, etf_rows)
    _write_json(etf / "leveraged_etf_scale_model_spec_snapshot.json", {"model_spec_id": study.ETF_MODEL})
    _manifest(etf, study.ETF_MANIFEST)

    cta_paths = []
    for m_idx, model in enumerate(study.CTA_MODELS):
        path = root / "cta" / model
        rows = []
        for i, date in enumerate(dates[:-1]):
            state_value = 1 if (i + m_idx) % 5 else -1
            prior = 1 if (i + m_idx - 1) % 5 else -1
            rows.append(
                {
                    "observation_date": date,
                    "effective_session": dates[i + 1],
                    "target_exposure": state_value,
                    "prior_target_exposure": prior,
                    "exposure_change": state_value - prior,
                    "model_spec_id": model,
                    "research_only": True,
                    "actionization_allowed": False,
                    "not_a_trading_signal": True,
                    "predictive_pit_eligible": False,
                    "phase2_eligible": False,
                    "not_actual_cta_position_estimate": True,
                    "not_actual_cta_flow_estimate": True,
                    "not_market_impact_estimate": True,
                }
            )
        _write_json(path / study.CTA_RECEIPT, _receipt(model, "cta_transparent_trend_replication_v1"))
        _write_csv(path / study.CTA_DAILY, rows)
        _manifest(path, study.CTA_MANIFEST)
        cta_paths.append(path)

    vol_paths = []
    for m_idx, model in enumerate(study.VOL_MODELS):
        path = root / "vol" / model
        rows = []
        for i, date in enumerate(dates[:-1]):
            target = 1.0 if i % 3 else 0.75
            change = -0.1 if (i + m_idx) % 4 == 0 else 0.05
            rows.append(
                {
                    "observation_date": date,
                    "effective_session": dates[i + 1],
                    "benchmark_instrument": "NDX",
                    "benchmark_mode": "ndx_exact_descriptive",
                    "target_exposure": target,
                    "prior_target_exposure": target - change,
                    "exposure_change": change,
                    "model_spec_id": model,
                    "research_only": True,
                    "actionization_allowed": False,
                    "not_a_trading_signal": True,
                    "predictive_pit_eligible": False,
                    "phase2_eligible": False,
                    "not_actual_manager_flow_estimate": True,
                    "not_market_impact_estimate": True,
                }
            )
        _write_json(path / study.VOL_RECEIPT, _receipt(model, "vol_control_transparent_replication_v1"))
        _write_csv(path / study.VOL_DAILY, rows)
        _manifest(path, study.VOL_MANIFEST)
        vol_paths.append(path)
    return {"cta": cta_paths, "vol": vol_paths, "etf": etf}


def _args(paths: dict, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        spec_id="phase1_6b_ndx_cross_module_downside_v1",
        cta_run_artifact=[str(p) for p in paths["cta"]],
        vol_run_artifact=[str(p) for p in paths["vol"]],
        etf_scale_run_artifact=str(paths["etf"]),
        output_dir=str(output),
    )


def test_build_outputs_and_verify_manifest(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path)
    receipt = study.build_study(_args(paths, tmp_path / "out"))
    assert receipt["run_status"] == "phase1_6b_cross_module_downside_completed"
    verify = study.verify_output_manifest(tmp_path / "out")
    assert verify["run_id"] == receipt["run_id"]
    for name in study.REQUIRED_OUTPUT_FILES:
        assert (tmp_path / "out" / name).exists()
    assoc = pd.read_csv(tmp_path / "out" / "cross_module_association_summary.csv")
    assert "combined_rebalance_notional_proxy" not in set(assoc["feature_id"])
    panel_cols = set(pd.read_csv(tmp_path / "out" / "cross_module_daily_panel.csv", nrows=0).columns.str.lower())
    assert not (panel_cols & study.FORBIDDEN_OUTPUT_FIELDS)


def test_manifest_tamper_and_extra_file_block(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path)
    (paths["cta"][0] / study.CTA_DAILY).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="cross_module_source_artifact_tampered"):
        study.build_study(_args(paths, tmp_path / "out"))

    paths = _build_source_tree(tmp_path / "extra")
    (paths["vol"][0] / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="cross_module_source_artifact_tampered"):
        study.build_study(_args(paths, tmp_path / "out2"))


def test_model_roster_and_etf_mode_enforced(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path)
    bad = dict(paths)
    bad["cta"] = [paths["cta"][0], *paths["cta"][:3]]
    with pytest.raises(SystemExit, match="cross_module_cta_model_set_mismatch"):
        study.build_study(_args(bad, tmp_path / "out"))

    paths = _build_source_tree(tmp_path / "etf")
    receipt_path = paths["etf"] / study.ETF_RECEIPT
    payload = json.loads(receipt_path.read_text())
    payload["benchmark_mode"] = "qqq_proxy"
    _write_json(receipt_path, payload)
    _manifest(paths["etf"], study.ETF_MANIFEST)
    with pytest.raises(SystemExit, match="cross_module_etf_benchmark_mismatch"):
        study.build_study(_args(paths, tmp_path / "out2"))


def test_duplicate_dates_and_alignment_gate(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path)
    p = paths["cta"][0] / study.CTA_DAILY
    rows = list(csv.DictReader(p.open(newline="", encoding="utf-8")))
    rows.append(rows[0])
    _write_csv(p, rows)
    _manifest(paths["cta"][0], study.CTA_MANIFEST)
    with pytest.raises(SystemExit, match="cross_module_duplicate_observation_date"):
        study.build_study(_args(paths, tmp_path / "out"))

    paths = _build_source_tree(tmp_path / "align")
    p = paths["vol"][0] / study.VOL_DAILY
    rows = list(csv.DictReader(p.open(newline="", encoding="utf-8")))
    for row in rows:
        row["effective_session"] = "2099-01-01"
    _write_csv(p, rows)
    _manifest(paths["vol"][0], study.VOL_MANIFEST)
    with pytest.raises(SystemExit, match="cross_module_alignment_coverage_inadequate"):
        study.build_study(_args(paths, tmp_path / "out2"))


def test_forward_outcomes_sensitivity_identity_and_quantile(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path)
    study.build_study(_args(paths, tmp_path / "out"))
    panel = pd.read_csv(tmp_path / "out" / "cross_module_daily_panel.csv")
    first = panel.iloc[0]
    returns = pd.read_csv(paths["etf"] / study.ETF_DAILY)["benchmark_return"].astype(float).tolist()
    expected_cum = 1.0
    for r in returns[1:6]:
        expected_cum *= 1 + r
    assert first["forward_5_session_cumulative_return"] == pytest.approx(expected_cum - 1)
    assert first["combined_mechanical_sensitivity"] == pytest.approx(6 * first["tqqq_lagged_capital_usd"] + 12 * first["sqqq_lagged_capital_usd"])
    identity = pd.read_csv(tmp_path / "out" / "cross_module_etf_mechanical_identity_audit.csv")
    assert identity.loc[identity["valid_rows"] > 0, "identity_match_status"].eq("valid").all()
    assert set(identity.loc[identity["valid_rows"] == 0, "identity_match_status"]) <= {"no_valid_rows"}
    assert set(panel["combined_mechanical_sensitivity_ex_post_quartile"]) == {"etf_sensitivity_q1_to_q3", "etf_sensitivity_q4_ex_post"}


def test_metric_gates_sparse_cells_and_all_windows(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path, n=25)
    study.build_study(_args(paths, tmp_path / "out"))
    assoc = pd.read_csv(tmp_path / "out" / "cross_module_association_summary.csv")
    assert not assoc["metrics_available"].any()
    joint = pd.read_csv(tmp_path / "out" / "cross_module_joint_condition_summary.csv")
    assert {"joint_cell_count_below_20"} <= set(joint["metrics_unavailable_reason"])
    coverage = pd.read_csv(tmp_path / "out" / "cross_module_window_coverage.csv")
    assert list(coverage["analysis_window_id"]) == [w["analysis_window_id"] for w in study.load_spec("phase1_6b_ndx_cross_module_downside_v1")["analysis_windows"]]


def test_output_dir_rejected_output_tamper_and_no_network_code(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path)
    args = _args(paths, tmp_path / "market_bomb_history" / "out")
    with pytest.raises(SystemExit, match="cross_module_output_dir_rejected"):
        study.build_study(args)

    study.build_study(_args(paths, tmp_path / "out"))
    (tmp_path / "out" / "cross_module_window_coverage.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="cross_module_output_tampered"):
        study.verify_output_manifest(tmp_path / "out")

    source = (REPO_ROOT / "scripts" / "build_phase1_6b_cross_module_downside_study.py").read_text(encoding="utf-8").lower()
    for needle in ["requests.", "urllib", "http://", "https://", "socket."]:
        assert needle not in source


def test_source_safety_flags_and_forbidden_output_field_guard(tmp_path: Path) -> None:
    paths = _build_source_tree(tmp_path)
    receipt_path = paths["cta"][0] / study.CTA_RECEIPT
    payload = json.loads(receipt_path.read_text())
    payload["actionization_allowed"] = True
    _write_json(receipt_path, payload)
    _manifest(paths["cta"][0], study.CTA_MANIFEST)
    with pytest.raises(SystemExit, match="cross_module_source_safety_flag_mismatch"):
        study.build_study(_args(paths, tmp_path / "out"))

    with pytest.raises(SystemExit, match="cross_module_forbidden_output_field"):
        study.write_csv(tmp_path / "bad.csv", [{"raw_close": 1}], ["raw_close"])
