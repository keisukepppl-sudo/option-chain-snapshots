from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_narrow_leadership_2023_frozen_replication_v2.py"
spec = importlib.util.spec_from_file_location("replication_v2", SCRIPT_PATH)
rep = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(rep)


SPEC = {
    "primary_rank": "S",
    "complete_status": "complete",
    "decision_start": "2023-01-03",
    "decision_end": "2023-12-29",
    "primary_sample_gate_cell_a_min": 10,
    "primary_sample_gate_pooled_non_a_min": 20,
    "component_sample_gate_min_per_side": 10,
    "ticker_concentration_largest_share_max": 0.3,
    "replicated_plus5_gate_pp": -10.0,
    "replicated_breach_gate_pp": 10.0,
    "validation_type": "pre_2024_frozen_threshold_historical_replication",
}


def make_primary(a=12, b=12, c=12, d=12, a_good=False, ticker="A0") -> pd.DataFrame:
    rows = []
    idx = 0
    for cell, n in [("A", a), ("B", b), ("C", c), ("D", d)]:
        for i in range(n):
            idx += 1
            plus = cell != "A" if not a_good else True
            breach = cell == "A" if not a_good else False
            rows.append(
                {
                    "signal_id": f"s{idx}",
                    "signal_decision_date": f"2023-07-{(i % 20) + 1:02d}",
                    "underlying_symbol": ticker if cell == "A" and ticker else f"{cell}{i % 10}",
                    "signal_rank": "S",
                    "outcome_status": "complete",
                    "reached_plus_5pct_within_10_sessions": plus,
                    "breakout_day_low_breach_before_timeout": breach,
                    "timeout_10_sessions_under_threshold": False,
                    "D_state": "high" if cell in {"A", "B"} else "low",
                    "L_state": "high" if cell in {"A", "C"} else "low",
                    "cell": cell,
                    "D_state_available": True,
                    "L_state_available": True,
                    "combined_state_available": True,
                }
            )
    return pd.DataFrame(rows)


def test_artifact_manifest_verification_detects_missing_modified_and_extra(tmp_path: Path):
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "a.csv").write_text("a\n", encoding="utf-8")
    manifest = {"files": [{"relative_path": "a.csv", "sha256": rep.file_sha256(root / "a.csv")}]}
    rep.write_json(root / "m.json", manifest)
    assert rep.verify_manifest(root, "m.json")
    (root / "a.csv").write_text("b\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        rep.verify_manifest(root, "m.json")
    (root / "a.csv").write_text("a\n", encoding="utf-8")
    (root / "extra.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        rep.verify_manifest(root, "m.json")


def test_thresholds_are_inherited_not_recomputed_and_missing_fails(tmp_path: Path):
    disp = tmp_path / "disp"
    disp.mkdir()
    pd.DataFrame(
        [
            {"metric": "D", "p33": 1.0, "p67": 2.0, "state_construction": "legacy"},
            {"metric": "L", "p33": 3.0, "p67": 4.0, "state_construction": "legacy"},
        ]
    ).to_csv(disp / "realized_dispersion_state_cutoffs.csv", index=False)
    (disp / "realized_dispersion_content_manifest.json").write_text("manifest\n", encoding="utf-8")
    out = rep.load_cutoff_inheritance({"D_metric_name": "D", "L_metric_name": "L"}, disp)
    assert out["D_high_cutoff_numeric"] == 2.0
    assert out["L_high_cutoff_numeric"] == 4.0
    with pytest.raises(SystemExit):
        rep.load_cutoff_inheritance({"D_metric_name": "missing", "L_metric_name": "L"}, disp)


def test_state_date_exact_join_and_no_future_state_leakage():
    panel = pd.DataFrame(
        [
            {"signal_id": "s1", "signal_decision_date": "2023-07-01", "underlying_symbol": "AAA", "signal_rank": "S", "outcome_status": "complete"},
            {"signal_id": "s2", "signal_decision_date": "2023-07-02", "underlying_symbol": "BBB", "signal_rank": "S", "outcome_status": "complete"},
        ]
    )
    state = pd.DataFrame({"date": ["2023-07-02"], "D_state": ["high"], "L_state": ["high"], "cell": ["A"]}).rename(columns={"date": "signal_decision_date"})
    merged = panel.merge(state, on="signal_decision_date", how="left")
    assert pd.isna(merged.loc[merged["signal_id"] == "s1", "cell"].iloc[0])
    assert merged.loc[merged["signal_id"] == "s2", "cell"].iloc[0] == "A"


def test_metric_implementation_reference_is_existing_module():
    assert "build_morita_realized_dispersion_quick_screen_v1" in rep.repo_relative(Path(rep.dispersion.__file__))


def test_cells_are_exclusive_and_exhaustive():
    states = [("high", "high", "A"), ("high", "low", "B"), ("low", "high", "C"), ("middle", "middle", "D")]
    assert [rep.classify_cell(d, l) for d, l, _ in states] == [x[2] for x in states]
    assert rep.classify_cell("metric_unavailable", "high") == "state_unavailable"


def test_reconciliation_excludes_non_s_collisions_incomplete_and_unavailable():
    all_rows = make_primary(1, 1, 1, 1, ticker=None)
    all_rows.loc[0, "signal_rank"] = "A"
    all_rows.loc[1, "outcome_status"] = "ambiguous_intraday_order"
    all_rows.loc[2, "outcome_status"] = "incomplete_horizon"
    all_rows.loc[3, "D_state_available"] = False
    all_rows.loc[3, "combined_state_available"] = False
    primary = all_rows[(all_rows.signal_rank == "S") & (all_rows.outcome_status == "complete") & all_rows.combined_state_available]
    recon = rep.signal_reconciliation(all_rows, primary, SPEC)
    lookup = dict(zip(recon["bucket"], recon["count"]))
    assert lookup["excluded_non_S"] == 1
    assert lookup["excluded_collision"] == 1
    assert lookup["excluded_incomplete"] == 1
    assert lookup["excluded_unavailable_D"] == 1


def test_comparison_signs_sample_gates_and_concentration_flags():
    primary = make_primary(12, 12, 0, 12, ticker="AAA")
    comps = rep.required_comparisons(primary, SPEC)
    main = comps[comps["comparison"] == "A_vs_pooled_BCD"].iloc[0]
    assert main["comparison_status"] == "eligible"
    assert main["plus5_difference_pp"] < 0
    assert main["breach_difference_pp"] > 0
    assert bool(main["ticker_concentration_flag"]) is True
    ab = comps[comps["comparison"] == "A_vs_C"].iloc[0]
    assert ab["comparison_status"] == "insufficient_sample"


def test_primary_label_rules():
    limited = rep.primary_label(rep.required_comparisons(make_primary(5, 20, 0, 0, ticker=None), SPEC), SPEC)
    assert limited["primary_label"] == "insufficient_2023_sample"
    replicated = rep.primary_label(rep.required_comparisons(make_primary(12, 12, 0, 12, ticker=None), SPEC), SPEC)
    assert replicated["primary_label"] == "replicated_directionally_2023"
    concentrated = rep.primary_label(rep.required_comparisons(make_primary(12, 12, 0, 12, ticker="AAA"), SPEC), SPEC)
    assert concentrated["primary_label"] == "directionally_adverse_but_limited"
    inconsistent = rep.primary_label(rep.required_comparisons(make_primary(12, 12, 0, 12, a_good=True, ticker=None), SPEC), SPEC)
    assert inconsistent["primary_label"] == "not_replicated_or_inconsistent"


def test_combined_row_does_not_overwrite_legacy_label():
    primary = make_primary(12, 12, 0, 12, ticker=None)
    table = rep.comparison_table(primary, primary, "replicated_directionally_2023", SPEC)
    combined = table[table["period"] == "combined_2023_2026_descriptive_only"].iloc[0]
    prior = table[table["period"] == "2024_2026_existing_confirmation_reference"].iloc[0]
    assert combined["primary_label"] == "descriptive_only"
    assert prior["primary_label"] == "existing_confirmation_reference"


def test_no_production_or_option_action_tokens_in_script():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    assert "place_order" not in text
    assert "webull" not in text
    assert "pushover" not in text
    assert "tp125" not in text
