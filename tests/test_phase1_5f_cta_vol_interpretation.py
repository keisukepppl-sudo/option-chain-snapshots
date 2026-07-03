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

from scripts import build_phase1_5f_cta_vol_interpretation as interp


CTA_MODELS = [
    "cta_ts_20d_binary_v1",
    "cta_ts_60d_binary_v1",
    "cta_ts_120d_binary_v1",
    "cta_ts_20_60_120_equal_weight_v1",
]
VOL_MODELS = [
    "vc_daily_20d_target10_cap100_v1",
    "vc_daily_40d_target10_cap100_v1",
    "vc_daily_60d_target10_cap100_v1",
    "vc_daily_20d_target12_cap100_v1",
    "vc_daily_40d_target12_cap100_v1",
    "vc_daily_60d_target12_cap100_v1",
]
WINDOWS = ["full_covered_period", "pre_2025", "from_2025", "calendar_2024", "calendar_2025", "calendar_2023_h2", "calendar_2026_ytd"]


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
            files.append({"relative_path": child.relative_to(path).as_posix(), "sha256": interp.file_sha256(child), "bytes": child.stat().st_size})
    _write_json(path / manifest_name, {"files": files, "content_set_hash": "synthetic"})


def _common_receipt(model: str, module: str) -> dict:
    return {
        "run_id": f"run_{model}",
        "input_id": "input_a",
        "market_id": "market_a",
        "benchmark_mode": "ndx_exact_descriptive",
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
    }


def _cta_rows(model: str) -> list[dict]:
    exposures_by_model = {
        CTA_MODELS[0]: [None, 1, 1, None, -1, -1, 1],
        CTA_MODELS[1]: [None, 1, -1, None, -1, 1, 1],
        CTA_MODELS[2]: [None, -1, -1, None, 1, 1, 1],
        CTA_MODELS[3]: [None, 0, -1, None, 0, 1, 1],
    }
    rows = []
    for idx, value in enumerate(exposures_by_model[model]):
        rows.append(
            {
                "observation_date": f"2024-01-0{idx + 1}",
                "target_exposure": "" if value is None else value,
                "exposure_change_label": "input_unavailable" if value is None else ["increase_risk", "reduce_risk", "unchanged"][idx % 3],
                "model_spec_id": model,
            }
        )
    return rows


def _vol_rows(model: str, offset: float) -> list[dict]:
    rows = []
    for idx in range(7):
        value = "" if idx == 0 else min(1.0, 0.2 + offset)
        rows.append({"observation_date": f"2024-01-0{idx + 1}", "target_exposure": value, "exposure_change_label": "input_unavailable" if value == "" else "increase_risk", "model_spec_id": model})
    return rows


def _build_synthetic(root: Path) -> dict:
    cta_runs = []
    for model in CTA_MODELS:
        path = root / "cta" / model
        _write_json(path / interp.CTA_RUN_RECEIPT, _common_receipt(model, "cta_transparent_trend_replication_v1"))
        _write_csv(path / interp.CTA_DAILY, _cta_rows(model))
        _manifest(path, interp.CTA_RUN_MANIFEST)
        cta_runs.append(path)
    robust = root / "cta_robust"
    robust_rows = []
    for model in CTA_MODELS:
        for alignment in ["as_of_ex_post_only", "availability_monitoring_only"]:
            for window in WINDOWS:
                robust_rows.append({"model_spec_id": model, "alignment_mode": alignment, "analysis_window_id": window, "weekly_pair_count": 5, "thin_window_flag": window.endswith("ytd"), "price_to_cot_relation": "cash_index_proxy_for_futures_cot", "ranking_allowed": False, "model_selection_allowed": False})
    robust_receipt = _common_receipt("", "cta_transparent_trend_replication_v1")
    robust_receipt.update({"run_id": "robust", "model_spec_id": "", "market_id": "market_a"})
    _write_json(robust / interp.CTA_ROBUSTNESS_RECEIPT, robust_receipt)
    _write_csv(robust / interp.CTA_ROBUSTNESS_SUMMARY, robust_rows)
    _manifest(robust, interp.CTA_ROBUSTNESS_MANIFEST)

    vol_runs = []
    for idx, model in enumerate(VOL_MODELS):
        path = root / "vol" / model
        receipt = _common_receipt(model, "vol_control_transparent_replication_v1")
        receipt["market_id"] = ""
        _write_json(path / interp.VOL_RUN_RECEIPT, receipt)
        _write_csv(path / interp.VOL_DAILY, _vol_rows(model, idx * 0.05))
        _manifest(path, interp.VOL_RUN_MANIFEST)
        vol_runs.append(path)
    vol_char = root / "vol_char"
    vol_summary_rows = []
    for model in VOL_MODELS:
        for window in WINDOWS:
            vol_summary_rows.append({"model_spec_id": model, "analysis_window_id": window, "observation_count": 7, "valid_target_exposure_count": 6, "cap_binding_session_count": 0, "nonzero_rebalance_count": 6, "ranking_allowed": False, "model_selection_allowed": False, "returns_analysis_allowed": False})
    vol_pair_rows = []
    for window in WINDOWS:
        for left_i, left in enumerate(VOL_MODELS):
            for right in VOL_MODELS[left_i + 1 :]:
                vol_pair_rows.append({"analysis_window_id": window, "left_model_spec_id": left, "right_model_spec_id": right, "overlapping_valid_exposure_count": 6, "mean_absolute_exposure_difference": 0.1})
    vol_receipt = _common_receipt("", "vol_control_transparent_replication_v1")
    vol_receipt.update({"run_id": "vol_char", "model_spec_id": "", "market_id": ""})
    _write_json(vol_char / interp.VOL_CHARACTERIZATION_RECEIPT, vol_receipt)
    _write_csv(vol_char / interp.VOL_SUMMARY, vol_summary_rows)
    _write_csv(vol_char / interp.VOL_PAIRWISE, vol_pair_rows)
    _manifest(vol_char, interp.VOL_CHARACTERIZATION_MANIFEST)
    return {"cta_runs": cta_runs, "cta_robust": robust, "vol_runs": vol_runs, "vol_char": vol_char}


def _args(paths: dict, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        cta_robustness_artifact=str(paths["cta_robust"]),
        cta_run_artifact=[str(path) for path in paths["cta_runs"]],
        vol_characterization_artifact=str(paths["vol_char"]),
        vol_run_artifact=[str(path) for path in paths["vol_runs"]],
        interpretation_spec_id="phase1_5f_cta_vol_descriptive_atlas_v1",
        output_dir=str(output),
    )


def test_build_synthetic_atlas_and_forbidden_fields_absent(tmp_path: Path) -> None:
    paths = _build_synthetic(tmp_path)
    receipt = interp.build_atlas(_args(paths, tmp_path / "outputs"))
    assert receipt["cross_module_metrics_computed"] is False
    assert receipt["cross_module_integration_performed"] is False
    for csv_path in (tmp_path / "outputs").glob("*.csv"):
        cols = pd.read_csv(csv_path, nrows=0).columns.str.lower().tolist()
        assert not (set(cols) & interp.FORBIDDEN_OUTPUT_FIELDS)
    assert (tmp_path / "outputs" / "phase1_5f_interpretation_receipt.json").exists()


def test_exact_model_set_duplicate_missing_and_mismatch_rejection(tmp_path: Path) -> None:
    paths = _build_synthetic(tmp_path)
    duplicate = dict(paths)
    duplicate["cta_runs"] = [paths["cta_runs"][0], *paths["cta_runs"][0:3]]
    with pytest.raises(SystemExit, match="cta_duplicate_model_spec"):
        interp.build_atlas(_args(duplicate, tmp_path / "out_dup"))
    missing = dict(paths)
    missing["vol_runs"] = paths["vol_runs"][:-1]
    with pytest.raises(SystemExit, match="vol_missing_model_spec"):
        interp.build_atlas(_args(missing, tmp_path / "out_missing"))


def test_tampered_manifest_and_provenance_mismatch_rejected(tmp_path: Path) -> None:
    paths = _build_synthetic(tmp_path)
    receipt_path = paths["cta_runs"][0] / interp.CTA_RUN_RECEIPT
    receipt = json.loads(receipt_path.read_text())
    receipt["source_manifest_hash"] = "different"
    _write_json(receipt_path, receipt)
    _manifest(paths["cta_runs"][0], interp.CTA_RUN_MANIFEST)
    with pytest.raises(SystemExit, match="cta_source_manifest_hash_mismatch"):
        interp.build_atlas(_args(paths, tmp_path / "out_mismatch"))

    paths = _build_synthetic(tmp_path / "tamper")
    (paths["vol_runs"][0] / interp.VOL_DAILY).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="manifest_sha_mismatch"):
        interp.build_atlas(_args(paths, tmp_path / "out_tamper"))


def test_cta_transition_does_not_bridge_unavailable_and_episode_boundaries(tmp_path: Path) -> None:
    paths = _build_synthetic(tmp_path)
    interp.build_atlas(_args(paths, tmp_path / "outputs"))
    transitions = pd.read_csv(tmp_path / "outputs" / "cta_state_transition_atlas.csv")
    first = transitions[(transitions["model_spec_id"] == CTA_MODELS[0]) & (transitions["analysis_window_id"] == "full_covered_period")].iloc[0]
    assert first["state_transition_count"] == 1
    episodes = pd.read_csv(tmp_path / "outputs" / "cta_multi_spec_disagreement_episodes.csv")
    assert list(episodes["episode_start"]) == ["2024-01-02", "2024-01-05"]
    assert list(episodes["episode_end"]) == ["2024-01-03", "2024-01-06"]


def test_top_tie_dates_sort_ascending_and_alignment_split_preserved(tmp_path: Path) -> None:
    paths = _build_synthetic(tmp_path)
    interp.build_atlas(_args(paths, tmp_path / "outputs"))
    top = pd.read_csv(tmp_path / "outputs" / "cta_top_state_divergence_observations.csv")
    assert top.iloc[0]["observation_date"] == "2024-01-02"
    cot = pd.read_csv(tmp_path / "outputs" / "cta_cot_metric_atlas.csv")
    assert set(cot["alignment_mode"]) == {"as_of_ex_post_only", "availability_monitoring_only"}
    assert "score" not in {col.lower() for col in cot.columns}


def test_vol_range_valid_only_and_tie_dates_sort_ascending(tmp_path: Path) -> None:
    paths = _build_synthetic(tmp_path)
    interp.build_atlas(_args(paths, tmp_path / "outputs"))
    spread = pd.read_csv(tmp_path / "outputs" / "vol_control_daily_cross_spec_spread.csv")
    first = spread[spread["observation_date"] == "2024-01-01"].iloc[0]
    assert first["valid_spec_count"] == 0
    assert first["input_unavailable_spec_count"] == 6
    top = pd.read_csv(tmp_path / "outputs" / "vol_control_top_cross_spec_dispersion_observations.csv")
    assert top.iloc[0]["observation_date"] == "2024-01-02"


def test_no_network_and_market_bomb_history_output_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    paths = _build_synthetic(tmp_path)
    def blocked(*args, **kwargs):
        raise AssertionError("network must not be used")
    monkeypatch.setattr("socket.create_connection", blocked)
    with pytest.raises(SystemExit, match="output_dir_inside_market_bomb_history_rejected"):
        interp.build_atlas(_args(paths, tmp_path / "market_bomb_history" / "out"))
