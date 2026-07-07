from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_narrow_leadership_2023_replication_v1.py"
spec = importlib.util.spec_from_file_location("replication", SCRIPT_PATH)
replication = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(replication)


def test_assign_state_uses_frozen_p67_high_boundary():
    assert replication.assign_state(0.01, 0.02, 0.03) == "low"
    assert replication.assign_state(0.025, 0.02, 0.03) == "middle"
    assert replication.assign_state(0.03, 0.02, 0.03) == "high"
    assert replication.assign_state(None, 0.02, 0.03) == "metric_unavailable"


def test_cell_mapping_is_fixed_2x2():
    assert replication.cell_for(True, True) == "A"
    assert replication.cell_for(True, False) == "B"
    assert replication.cell_for(False, True) == "C"
    assert replication.cell_for(False, False) == "D"


def test_empty_signal_tables_keep_required_cells_and_insufficient_comparisons():
    empty = pd.DataFrame(columns=["cell", "underlying_symbol", "reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"])
    coverage, summary, tickers = replication.build_cell_tables(empty)
    comparisons = replication.build_comparisons(empty, 20)
    assert set(coverage["cell"]) == {"A", "B", "C", "D"}
    assert int(summary["complete_signal_count"].sum()) == 0
    assert tickers.empty
    assert set(comparisons["comparison_status"]) == {"insufficient_sample"}


def test_replication_label_zero_signals_is_not_confirmed():
    empty = pd.DataFrame(columns=["cell"])
    comps = replication.build_comparisons(empty, 20)
    label = replication.replication_label(empty, comps)
    assert label["replication_label"] == "no_2023_s_signals_available_for_2x2_replication"
    assert label["live_action_allowed"] is False


def test_manifest_verify_rejects_extra_file(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    for name in replication.REQUIRED_OUTPUTS:
        (out / name).write_text("fixture\n", encoding="utf-8")
    replication.build_manifest(out)
    assert replication.verify_run(out)["status"] == "morita_narrow_leadership_2023_replication_verified"
    (out / "extra.csv").write_text("bad\n", encoding="utf-8")
    try:
        replication.verify_run(out)
    except SystemExit as exc:
        assert "manifest_extra_file" in str(exc)
    else:
        raise AssertionError("verify_run should reject extras")
