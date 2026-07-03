from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_narrow_leadership_confirmation_v1.py"
spec = importlib.util.spec_from_file_location("narrow", SCRIPT_PATH)
narrow = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(narrow)


SPEC = {
    "baseline_run_id": "fixture",
    "rank": "S",
    "complete_status": "complete",
    "dispersion_metric": "broad_russell1000_cross_sectional_dispersion_20d",
    "leadership_metric": "broad_russell1000_qqq_minus_eqw_return_20d",
    "state_source": "completed_realized_dispersion_quick_screen",
    "state_definition": "fixed_full_sample_ex_post_tercile_states",
    "full_sample_min_per_side": 20,
    "chronological_half_min_per_side": 10,
    "concentration_largest_single_ticker_share_max": 0.30,
    "main_plus5_adverse_threshold_pp": -10.0,
    "main_breach_adverse_threshold_pp": 10.0,
    "component_threshold_pp": 7.5,
}


def make_wide() -> pd.DataFrame:
    rows = []
    cells = [("A", True, True), ("B", True, False), ("C", False, True), ("D", False, False)]
    idx = 0
    for cell, d_high, l_high in cells:
        for i in range(22):
            idx += 1
            rows.append(
                {
                    "signal_id": f"s{idx}",
                    "signal_decision_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=idx),
                    "underlying_symbol": f"T{i % 12}",
                    "signal_rank": "S",
                    "outcome_status": "complete",
                    "reached_plus_5pct_within_10_sessions": cell != "A",
                    "breakout_day_low_breach_before_timeout": cell == "A",
                    "timeout_10_sessions_under_threshold": False,
                    "D_state": "high" if d_high else "middle",
                    "L_state": "high" if l_high else "low",
                    "D_high": d_high,
                    "L_high": l_high,
                    "eligible_2x2": True,
                    "cell": cell,
                }
            )
    return pd.DataFrame(rows)


def test_no_network_provider_actionization_code_exists():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for token in ["requests", "urllib", "yfinance", "--metric", "--threshold", "--state"]:
        assert token not in text
    assert '"actionization_allowed": true' not in text


def test_2x2_cells_are_exclusive_and_outcome_summary_correct():
    wide = make_wide()
    cells = narrow.cell_summary(wide)
    assert set(cells["cell"]) == {"A", "B", "C", "D"}
    assert cells["complete_signal_count"].sum() == 88
    a = cells[cells["cell"] == "A"].iloc[0]
    assert a["plus5_success_rate"] == pytest.approx(0.0)
    assert a["breakout_low_breach_rate"] == pytest.approx(1.0)


def test_required_comparisons_sample_gate_and_differences():
    wide = make_wide()
    comps = narrow.build_comparisons(wide, SPEC)
    main = comps[comps["comparison"] == "A_vs_pooled_BCD"].iloc[0]
    assert main["comparison_status"] == "eligible"
    assert main["plus5_difference_pp"] == pytest.approx(-100.0)
    assert main["breach_difference_pp"] == pytest.approx(100.0)
    assert bool(main["directionally_adverse"]) is True
    assert set(comps["comparison"]) == {"A_vs_B", "A_vs_C", "A_vs_D", "A_vs_pooled_BCD", "C_vs_D", "B_vs_D"}


def test_same_decision_date_not_split_and_chronological_gate():
    wide = make_wide()
    wide.loc[wide.index[:4], "signal_decision_date"] = pd.Timestamp("2024-02-01")
    halves = narrow.split_halves(wide)
    assert len(set(halves[wide["signal_decision_date"] == pd.Timestamp("2024-02-01")])) == 1
    chrono = narrow.build_chronological(wide, SPEC)
    assert set(chrono["scope"]) == {"early_half", "late_half"}


def test_confirmation_label_and_concentration_block():
    wide = make_wide()
    comps = narrow.build_comparisons(wide, SPEC)
    chrono = narrow.build_chronological(wide, SPEC)
    label, decision = narrow.confirmation_label(comps, chrono, SPEC)
    assert label in {"confirmed_descriptive_narrow_leadership_pattern", "inconsistent_or_non_incremental"}
    assert "actionization" not in decision
    concentrated = wide.copy()
    concentrated.loc[concentrated["cell"] == "A", "underlying_symbol"] = "NVDA"
    comps2 = narrow.build_comparisons(concentrated, SPEC)
    chrono2 = narrow.build_chronological(concentrated, SPEC)
    label2, _ = narrow.confirmation_label(comps2, chrono2, SPEC)
    assert label2 == "concentration_limited"


def test_reconciliation_manifest_and_verify(tmp_path: Path):
    wide = make_wide()
    wide.loc[0, "signal_rank"] = "A"
    wide.loc[1, "outcome_status"] = "ambiguous_intraday_order"
    recon = narrow.reconciliation(wide, SPEC)
    assert int(recon.loc[recon["bucket"] == "excluded_non_S", "count"].iloc[0]) == 1
    assert int(recon.loc[recon["bucket"] == "excluded_collision", "count"].iloc[0]) == 1
    out = tmp_path / "out"
    out.mkdir()
    for name in narrow.REQUIRED_OUTPUTS:
        (out / name).write_text("fixture\n", encoding="utf-8")
    narrow.build_manifest(out)
    assert narrow.verify_run(out)["status"] == "morita_narrow_leadership_confirmation_verified"
    (out / "extra.csv").write_text("bad\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        narrow.verify_run(out)
