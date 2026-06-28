from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

import market_bomb_flow_pressure_research_v0 as flow
import market_bomb_flow_pressure_statistical_backtest_v1 as stat


HELPER_PATH = Path(__file__).resolve().parent / "test_market_bomb_flow_pressure_research_v0.py"
HELPER_SPEC = importlib.util.spec_from_file_location("flow_research_helpers", HELPER_PATH)
helpers = importlib.util.module_from_spec(HELPER_SPEC)
assert HELPER_SPEC.loader is not None
HELPER_SPEC.loader.exec_module(helpers)


FIXED_NOW = helpers.FIXED_NOW


def _root(tmp_path: Path) -> Path:
    root = helpers._root(tmp_path)
    repo_config = Path(__file__).resolve().parents[1] / "market_bomb_config"
    for name in [
        "flow_pressure_statistical_backtest_v1_policy.json",
        "flow_pressure_statistical_backtest_v1_spec.json",
        "flow_pressure_statistical_backtest_v1_schema.json",
    ]:
        shutil.copyfile(repo_config / name, root / "market_bomb_config" / name)
    policy_path = root / "market_bomb_config" / "flow_pressure_statistical_backtest_v1_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["minimum_bootstrap_replicates"] = 5
    policy["minimum_partition_rows"] = 3
    policy["minimum_partition_unique_dates"] = 3
    policy["minimum_holdout_rows"] = 2
    policy["minimum_holdout_unique_dates"] = 2
    policy["minimum_quantile_rows"] = 3
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    spec_path = root / "market_bomb_config" / "flow_pressure_statistical_backtest_v1_spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["outcomes"] = [
        "next_session_close_to_close_return",
        "three_session_close_to_close_return",
    ]
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return root


def _release(root: Path) -> str:
    helpers._stage(root)
    return flow.build_release(root, "fixture_flow", now_utc=FIXED_NOW, research_timing_class="eod_next_session")


def _run(root: Path) -> tuple[str, str, Path]:
    release_id = _release(root)
    run_id = stat.run_flow_statistical_backtest(root, release_id)
    return release_id, run_id, stat.statistical_run_dir(root, release_id, run_id)


def test_statistical_backtest_outputs_verify_and_research_only(tmp_path: Path) -> None:
    root = _root(tmp_path)
    release_id, run_id, run_dir = _run(root)
    assert stat.verify_flow_statistical_backtest(root, release_id, run_id)["status"] == "valid"
    for name in stat.REQUIRED_OUTPUTS:
        assert os.path.isfile(stat.io_path(run_dir / name))
    receipt = json.loads((run_dir / "statistical_backtest_receipt.json").read_text(encoding="utf-8"))
    assert receipt["actionization_allowed"] is False
    conclusion = (run_dir / "research_conclusion.md").read_text(encoding="utf-8")
    assert conclusion.startswith(stat.CONCLUSION_OPENING)
    evidence = pd.read_csv(run_dir / "evidence_classification.csv")
    assert not evidence["evidence_label"].isin(["confirmed", "tradeable", "buy", "sell"]).any()


def test_statistical_backtest_tamper_and_extra_file_detected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    release_id, run_id, run_dir = _run(root)
    split_path = run_dir / "chronological_split_manifest.json"
    original = open(stat.io_path(split_path), "r", encoding="utf-8").read()
    with stat.open_for_write(split_path) as handle:
        handle.write(original + "\n")
    with pytest.raises(SystemExit, match="hash mismatch"):
        stat.verify_flow_statistical_backtest(root, release_id, run_id)
    with stat.open_for_write(split_path) as handle:
        handle.write(original)
    assert stat.verify_flow_statistical_backtest(root, release_id, run_id)["status"] == "valid"
    with stat.open_for_write(run_dir / "undeclared.csv") as handle:
        handle.write("x\n1\n")
    with pytest.raises(SystemExit, match="file set mismatch"):
        stat.verify_flow_statistical_backtest(root, release_id, run_id)


def test_panel_point_in_time_rule_and_exclusions(tmp_path: Path) -> None:
    root = _root(tmp_path)
    release_id = _release(root)
    study_spec = stat.spec(root)
    policy = stat.policy(root)
    panel, exclusions = stat.construct_feature_outcome_panel(root, release_id, study_spec, policy)
    assert not panel.empty
    assert pd.to_datetime(panel["feature_available_at_timestamp"], utc=True).le(pd.to_datetime(panel["decision_time"], utc=True)).all()
    assert pd.to_datetime(panel["decision_time"], utc=True).lt(pd.to_datetime(panel["target_start_timestamp"], utc=True)).all()
    assert "methodology_incomplete" in set(exclusions["reason_code"])


def test_chronological_split_no_overlap_same_date_and_reorder_stable(tmp_path: Path) -> None:
    root = _root(tmp_path)
    release_id = _release(root)
    panel, _ = stat.construct_feature_outcome_panel(root, release_id, stat.spec(root), stat.policy(root))
    split_a, manifest_a = stat.split_panel(panel, stat.spec(root))
    split_b, manifest_b = stat.split_panel(panel.sample(frac=1, random_state=7), stat.spec(root))
    assert manifest_a == manifest_b
    date_splits = split_a.groupby("decision_date")["split"].nunique()
    assert int(date_splits.max()) == 1
    parts = manifest_a["partitions"]
    assert parts["train"]["end_date"] <= parts["validation"]["start_date"] if parts["validation"]["start_date"] else True
    assert parts["validation"]["end_date"] <= parts["final_holdout"]["start_date"] if parts["final_holdout"]["start_date"] else True


def test_train_only_thresholds_are_frozen_for_validation_and_holdout(tmp_path: Path) -> None:
    root = _root(tmp_path)
    release_id = _release(root)
    panel, _ = stat.construct_feature_outcome_panel(root, release_id, stat.spec(root), stat.policy(root))
    split_panel, _ = stat.split_panel(panel, stat.spec(root))
    thresholds, boundaries = stat.derive_thresholds_and_boundaries(split_panel, stat.policy(root))
    applied = stat.apply_train_thresholds(split_panel, thresholds, boundaries)
    assert thresholds["thresholds"]
    assert boundaries["boundaries"]
    train_ranges = {(row["module_name"], row["underlying_instrument"], row["target_name"]): (row["train_start"], row["train_end"]) for row in thresholds["thresholds"]}
    assert all(start <= end for start, end in train_ranges.values())
    assert "downside_tail" in applied.columns
    assert "absolute_pressure_quintile" in applied.columns


def test_statistics_effect_ratio_and_bootstrap_are_deterministic(tmp_path: Path) -> None:
    root = _root(tmp_path)
    release_id = _release(root)
    panel, _ = stat.construct_feature_outcome_panel(root, release_id, stat.spec(root), stat.policy(root))
    split_panel, _ = stat.split_panel(panel, stat.spec(root))
    thresholds, boundaries = stat.derive_thresholds_and_boundaries(split_panel, stat.policy(root))
    applied = stat.apply_train_thresholds(split_panel, thresholds, boundaries)
    summary = stat.build_statistical_summary(applied, stat.policy(root))
    effects = stat.build_effect_sizes(summary)
    boot_a, meta_a = stat.build_bootstrap(applied, summary, stat.policy(root))
    boot_b, meta_b = stat.build_bootstrap(applied, summary, stat.policy(root))
    assert not summary.empty
    assert not effects.empty
    assert "not_estimable" in set(effects["risk_ratio_status"]) or effects["risk_ratio_vs_unconditional"].notna().any()
    pd.testing.assert_frame_equal(boot_a, boot_b)
    assert meta_a == meta_b
    assert set(boot_a["block_length"]).issuperset({3, 5, 10})


def test_interaction_did_hand_calculated() -> None:
    panel = pd.DataFrame(
        [
            {"split": "validation", "module_name": "leveraged_etf_rebalance", "underlying_instrument": "QQQ", "feature_name": "f", "target_name": "r", "fragility_regime": "high", "flow_regime": "adverse", "target_value": -0.04, "downside_tail": True, "decision_date": "2020-01-01"},
            {"split": "validation", "module_name": "leveraged_etf_rebalance", "underlying_instrument": "QQQ", "feature_name": "f", "target_name": "r", "fragility_regime": "high", "flow_regime": "non_adverse", "target_value": -0.01, "downside_tail": False, "decision_date": "2020-01-02"},
            {"split": "validation", "module_name": "leveraged_etf_rebalance", "underlying_instrument": "QQQ", "feature_name": "f", "target_name": "r", "fragility_regime": "not_high", "flow_regime": "adverse", "target_value": -0.02, "downside_tail": True, "decision_date": "2020-01-03"},
            {"split": "validation", "module_name": "leveraged_etf_rebalance", "underlying_instrument": "QQQ", "feature_name": "f", "target_name": "r", "fragility_regime": "not_high", "flow_regime": "non_adverse", "target_value": 0.01, "downside_tail": False, "decision_date": "2020-01-04"},
        ]
    )
    _, did = stat.build_interactions(panel)
    assert bool(did.iloc[0]["estimable"]) is True
    assert did.iloc[0]["interaction_difference_in_differences"] == pytest.approx(0.0)


def test_evidence_classifier_conservative_on_reversal_and_historical_mode() -> None:
    summary = pd.DataFrame(
        [
            {"analysis_id": "v", "module_name": "m", "underlying_instrument": "Q", "feature_name": "f", "target_name": "r", "flow_regime": "adverse", "split": "validation", "mean": 0.02, "sample_count": 10, "unique_decision_dates": 10, "status": "ok"},
            {"analysis_id": "h", "module_name": "m", "underlying_instrument": "Q", "feature_name": "f", "target_name": "r", "flow_regime": "adverse", "split": "final_holdout", "mean": -0.02, "sample_count": 10, "unique_decision_dates": 10, "status": "ok"},
        ]
    )
    boot = pd.DataFrame({"analysis_id": ["v"], "status": ["ok"]})
    stability = pd.DataFrame({"analysis_id": ["v", "h"], "stability_status": ["stable_enough_for_screening", "stable_enough_for_screening"]})
    policy = {"minimum_partition_rows": 3, "minimum_partition_unique_dates": 3, "minimum_holdout_rows": 2, "minimum_holdout_unique_dates": 2}
    evidence = stat.classify_evidence(summary, boot, stability, policy, "eod_next_session")
    assert evidence.iloc[0]["evidence_label"] == "no_reliable_evidence"
    historical = stat.classify_evidence(summary, boot, stability, policy, "historical_descriptive_only")
    assert historical.iloc[0]["primary_reason"] == "historical_descriptive_only_no_predictive_label"


def test_release_linkage_mismatch_detected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    release_id, run_id, run_dir = _run(root)
    receipt_path = run_dir / "statistical_backtest_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["release_id"] = "wrong_release"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    with pytest.raises(SystemExit, match="release id mismatch"):
        stat.verify_flow_statistical_backtest(root, release_id, run_id)
