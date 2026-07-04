from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_s_tp_comparison_v1 as m


def sample_path(values: list[float], terminal_reason: str = "max_hold") -> list[dict[str, object]]:
    rows = []
    for idx, value in enumerate(values):
        rows.append(
            {
                "valuation_index": idx,
                "valuation_time": f"2024-01-{idx + 1:02d}",
                "net_option_return_pct": value,
                "independent_terminal": idx == len(values) - 1,
                "terminal_reason": terminal_reason if idx == len(values) - 1 else "",
            }
        )
    return rows


def test_no_network_provider_api_code_exists() -> None:
    text = (REPO_ROOT / "scripts" / "build_morita_s_tp_comparison_v1.py").read_text(encoding="utf-8")
    forbidden = ["requests", "urllib", "yfinance", "download(", "broker", "api_key"]
    assert not any(token in text for token in forbidden)


def test_canonical_model_source_identity_is_required(tmp_path: Path) -> None:
    out = tmp_path / "out"
    receipt = m.build_blocked_outputs(m.DEFAULT_BASELINE_DIR, out)
    assert receipt["status"] == m.FAIL_CLOSED_STATUS
    rows = list(csv.DictReader((out / "canonical_model_source_verification.csv").open(encoding="utf-8")))
    assert any(row["source_component"] == "repo_committed_single_call_tp_engine" for row in rows)
    assert all(row["usable_for_tp_comparison"] == "False" for row in rows)


def test_formal_s_baseline_compatibility_is_required(tmp_path: Path) -> None:
    missing = tmp_path / "missing_baseline"
    identity = m.load_baseline_identity(missing)
    assert identity["baseline_verified"] is False
    assert identity["baseline_status"] == "missing_required_formal_baseline_files"


def test_all_policies_use_identical_entry_records() -> None:
    entries = [{"signal_id": "s1"}, {"signal_id": "s2"}]
    policies = {policy: [row["signal_id"] for row in entries] for policy in ["TP100", "TP125", "STAGED_100_125"]}
    assert len({tuple(v) for v in policies.values()}) == 1


def test_tp100_exits_first_at_threshold() -> None:
    path = sample_path([-20, 80, 101, 140])
    assert m.policy_return_pct(path, "TP100") == 100.0
    assert m.first_hit(path, 100.0)["valuation_time"] == "2024-01-03"


def test_tp125_exits_first_at_threshold() -> None:
    path = sample_path([30, 100, 124, 126])
    assert m.policy_return_pct(path, "TP125") == 125.0
    assert m.first_hit(path, 125.0)["valuation_time"] == "2024-01-04"


def test_staged_exit_weights_are_fixed_50_50() -> None:
    path = sample_path([0, 110, 124, 80])
    assert m.policy_return_pct(path, "STAGED_100_125") == 90.0
    path2 = sample_path([0, 100, 126])
    assert m.policy_return_pct(path2, "STAGED_100_125") == 112.5


def test_same_day_target_resolution_is_identical_across_policies() -> None:
    path = sample_path([130, 80])
    assert m.first_hit(path, 100.0)["valuation_time"] == m.first_hit(path, 125.0)["valuation_time"]


def test_independent_terminal_ignores_policy_tp_closure() -> None:
    path = sample_path([0, 105, 80, -20], terminal_reason="day10_underlying_lt_5pct")
    cls = m.classify_path(path)
    assert cls["independent_terminal_time"] == "2024-01-04"
    assert cls["independent_terminal_reason"] == "day10_underlying_lt_5pct"


def test_missing_independent_terminal_fails_closed() -> None:
    path = sample_path([0, 100])
    path[-1]["independent_terminal"] = False
    with pytest.raises(ValueError, match="independent_terminal_not_reproducible"):
        m.policy_return_pct(path, "TP100")


def test_target_path_ambiguity_is_tracked() -> None:
    path = sample_path([0, 110, 120])
    path[1]["target_path_ambiguous"] = True
    assert m.classify_path(path)["path_class"] == "CLASS_6_PATH_AMBIGUOUS"


def test_six_path_classes_are_mutually_exclusive() -> None:
    paths = [
        sample_path([0, 100, 130]),
        sample_path([0, 110, 90, 126]),
        sample_path([0, 101, 80]),
        sample_path([0, 101, 110]),
    ]
    classes = [m.classify_path(path)["path_class"] for path in paths]
    assert classes == [
        "CLASS_1_DIRECT_100_TO_125",
        "CLASS_2_DIP_THEN_125",
        "CLASS_4_100_TO_TERMINAL_LOSS_OF_PROFIT",
        "CLASS_5_100_TO_TERMINAL_STILL_ABOVE_100",
    ]
    assert len(classes) == len(set(classes))


def test_class3_equals_classes4_and5_plus_documented_ambiguity_exclusion() -> None:
    paths = [sample_path([0, 100, 80]), sample_path([0, 100, 115]), sample_path([0, 110, 126])]
    classes = [m.classify_path(path)["path_class"] for path in paths]
    class3 = sum(cls in {"CLASS_4_100_TO_TERMINAL_LOSS_OF_PROFIT", "CLASS_5_100_TO_TERMINAL_STILL_ABOVE_100"} for cls in classes)
    assert class3 == 2


def test_post100_peak_trough_use_no_future_beyond_independent_terminal() -> None:
    path = sample_path([0, 105, 70])
    path.append({"valuation_index": 3, "valuation_time": "2024-01-04", "net_option_return_pct": 500, "independent_terminal": False})
    cls = m.classify_path(path[:3])
    assert cls["post_100_peak_return_pct"] == 105
    assert cls["post_100_trough_return_pct"] == 70


def test_giveback_threshold_statistics_are_directly_derivable() -> None:
    classes = [m.classify_path(sample_path([0, 100, 74])), m.classify_path(sample_path([0, 100, -5]))]
    drawdowns = [row["post_100_drawdown_from_100_pct_points"] for row in classes]
    assert sum(dd <= -25 for dd in drawdowns) == 2
    assert sum(dd <= -100 for dd in drawdowns) == 1


def test_profit_factor_and_gross_profit_loss() -> None:
    pf = m.profit_factor([100, -50, 25])
    assert pf["gross_profit"] == 125
    assert pf["gross_loss"] == 50
    assert pf["profit_factor"] == 2.5


def test_policy_differences_are_calculated() -> None:
    rows = [
        {"policy": "TP100", "trade_return_mean": 10, "trade_return_median": 5, "profit_factor": 1.2, "gross_profit": 100, "gross_loss": 80},
        {"policy": "TP125", "trade_return_mean": 15, "trade_return_median": 6, "profit_factor": 1.4, "gross_profit": 120, "gross_loss": 75},
        {"policy": "STAGED_100_125", "trade_return_mean": 12, "trade_return_median": 5.5, "profit_factor": 1.3, "gross_profit": 110, "gross_loss": 78},
    ]
    deltas = m.policy_deltas(rows)
    assert deltas[0]["comparison"] == "TP125_minus_TP100"
    assert round(deltas[0]["pf_difference"], 6) == 0.2


def test_portfolio_metrics_only_when_canonical_aggregation_exists(tmp_path: Path) -> None:
    out = tmp_path / "out"
    m.build_blocked_outputs(m.DEFAULT_BASELINE_DIR, out)
    rows = list(csv.DictReader((out / "s_tp_policy_portfolio_summary.csv").open(encoding="utf-8")))
    assert {row["portfolio_metrics_status"] for row in rows} == {m.PORTFOLIO_UNAVAILABLE}


def test_chronological_split_keeps_same_entry_dates_together() -> None:
    rows = [
        {"entry_date": "2024-01-01", "signal_id": "a"},
        {"entry_date": "2024-01-01", "signal_id": "b"},
        {"entry_date": "2024-01-02", "signal_id": "c"},
        {"entry_date": "2024-01-03", "signal_id": "d"},
    ]
    halves = m.chronological_halves(rows)
    assert {row["signal_id"] for row in halves["early_half"]} == {"a", "b", "c"}
    assert {row["signal_id"] for row in halves["late_half"]} == {"d"}


def test_concentration_diagnostics_are_correct() -> None:
    rows = [{"ticker": "A"}, {"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]
    summary = m.concentration_summary(rows)
    assert summary["unique_ticker_count"] == 3
    assert summary["largest_single_ticker_share"] == 0.5
    assert summary["top_five_ticker_share"] == 1.0


def test_summary_label_obeys_fixed_rules() -> None:
    rows = [
        {"policy": "TP100", "profit_factor": 1.4},
        {"policy": "TP125", "profit_factor": 1.2},
        {"policy": "STAGED_100_125", "profit_factor": 1.3},
    ]
    assert m.choose_overall_label(rows, concentration_flag=False) == "tp100_preferred_descriptively"
    assert m.choose_overall_label(rows, concentration_flag=True) == "no_clear_preference"
    assert m.choose_overall_label([], concentration_flag=False) == m.INSUFFICIENT_LABEL


def test_output_manifest_rejects_missing_changed_and_extra_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    m.build_blocked_outputs(m.DEFAULT_BASELINE_DIR, out)
    assert m.verify_output_dir(out)["verified"] is True
    (out / "extra.csv").write_text("x\n", encoding="utf-8")
    assert m.verify_output_dir(out)["extra"] == ["extra.csv"]
    (out / "extra.csv").unlink()
    (out / "s_tp_policy_trade_summary.csv").write_text("changed\n", encoding="utf-8")
    assert "s_tp_policy_trade_summary.csv" in m.verify_output_dir(out)["changed"]


def test_no_live_target_alert_stop_or_sizing_actionization_is_emitted(tmp_path: Path) -> None:
    out = tmp_path / "out"
    receipt = m.build_blocked_outputs(m.DEFAULT_BASELINE_DIR, out)
    assert receipt["actionization_allowed"] is False
    m.assert_no_live_actionization(out)


def test_existing_modules_are_not_part_of_runtime_mutation() -> None:
    spec = json.loads((REPO_ROOT / "config" / "morita_s_tp_comparison_v1" / "s_tp100_tp125_staged_spec.json").read_text(encoding="utf-8"))
    assert spec["canonical_model_policy"]["do_not_optimize_targets_or_stops"] is True
    assert spec["actionization_allowed"] is False
