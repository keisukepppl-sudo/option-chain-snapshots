from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_single_call_reference import s_single_call_reference_engine as e


def row(hit100: bool, hit125: bool, terminal: float, trough: float = 90.0, ticker: str = "AAA") -> dict[str, object]:
    return {
        "signal_id": ticker + "1",
        "ticker": ticker,
        "signal_decision_date": "2024-01-01",
        "entry_date": "2024-01-02",
        "terminal_date": "2024-02-15",
        "terminal_reason": "max_holding_30_sessions",
        "terminal_net_return_pct": terminal,
        "first_hit_100_date": "2024-01-10" if hit100 else "",
        "first_hit_100_session": 5 if hit100 else "",
        "first_hit_125_date": "2024-01-12" if hit125 else "",
        "first_hit_125_session": 7 if hit125 else "",
        "post_100_trough_net_return_pct": trough if hit100 else "",
        "post_100_peak_net_return_pct": 150.0 if hit100 else "",
    }


def test_tp100_and_tp125_fill_exact_thresholds() -> None:
    returns = e.policy_returns(row(True, True, 300.0))
    assert returns["TP100"] == 100.0
    assert returns["TP125"] == 125.0


def test_staged_weighting_is_exactly_50_50() -> None:
    assert e.policy_returns(row(True, True, 300.0))["STAGED"] == 112.5
    assert e.policy_returns(row(True, False, 80.0))["STAGED"] == 90.0


def test_policies_share_identical_terminal_path_inputs() -> None:
    base = row(True, False, -20.0)
    returns = e.policy_returns(base)
    assert set(returns) == {"TP100", "TP125", "STAGED"}
    assert base["terminal_date"] == "2024-02-15"


def test_path_classes_are_exclusive_and_exhaustive() -> None:
    assert e.classify_100_to_125(row(True, True, 150.0, trough=110.0)) == "DIRECT_100_TO_125"
    assert e.classify_100_to_125(row(True, True, 150.0, trough=80.0)) == "DIP_THEN_125"
    assert e.classify_100_to_125(row(True, False, 50.0, trough=40.0)) == "100_ONLY_TERMINAL_BELOW_100"
    assert e.classify_100_to_125(row(True, False, 110.0, trough=105.0)) == "100_ONLY_TERMINAL_AT_OR_ABOVE_100"
    assert e.classify_100_to_125(row(False, False, 10.0)) == "NO_100_HIT"


def test_never_reach_125_and_giveback_statistics_are_correct() -> None:
    rows = [row(True, False, 50.0, trough=40.0), row(True, True, 150.0, trough=80.0)]
    for r in rows:
        r["path_class"] = e.classify_100_to_125(r)
    summary = {item["metric"]: item["value"] for item in e.giveback_summary(rows)}
    assert summary["never_reach_125_after_100_rate"] == 0.5
    assert summary["gave_back_50pp_or_more_rate"] == 0.5
    assert summary["dip_then_125_rate"] == 0.5


def test_pf_and_drawdown_proxy_outputs_are_deterministic() -> None:
    assert e.profit_factor([100.0, -50.0, 25.0]) == 2.5
    rows = []
    for idx, value in enumerate([100.0, -50.0, -25.0, 10.0]):
        r = row(False, False, value, ticker=f"T{idx}")
        r["TP100_return_pct"] = value
        rows.append(r)
    dd = e.drawdown_proxy(rows, "TP100")
    assert dd["max_drawdown_proxy"] == -75.0
    assert dd["worst_10_trade_sum_proxy"] == 35.0


def test_chronology_keeps_same_date_trades_together() -> None:
    rows = [row(False, False, 1, ticker="A"), row(False, False, 2, ticker="B"), row(False, False, 3, ticker="C")]
    rows[0]["entry_date"] = "2024-01-01"
    rows[1]["entry_date"] = "2024-01-01"
    rows[2]["entry_date"] = "2024-01-02"
    halves = e.chronological_halves(rows)
    assert {r["ticker"] for r in halves["early_half"]} == {"A", "B"}
    assert {r["ticker"] for r in halves["late_half"]} == {"C"}


def test_concentration_flags_are_correct() -> None:
    rows = [row(True, True, 100, ticker="A"), row(True, True, 100, ticker="A"), row(True, True, 100, ticker="B")]
    for r in rows:
        r["path_class"] = e.classify_100_to_125(r)
        r.update({f"{policy}_return_pct": 100.0 for policy in ["TP100", "TP125", "STAGED"]})
    conc = {item["scope"]: item for item in e.concentration_by_scope(rows)}
    assert conc["TP100"]["concentration_flag"] is True


def test_fixed_label_criteria_are_followed() -> None:
    policy = [
        {"policy": "TP100", "profit_factor": 1.4},
        {"policy": "TP125", "profit_factor": 1.2},
        {"policy": "STAGED", "profit_factor": 1.3},
    ]
    dd = [
        {"policy": "TP100", "max_drawdown_proxy": -50},
        {"policy": "TP125", "max_drawdown_proxy": -52},
        {"policy": "STAGED", "max_drawdown_proxy": -48},
    ]
    conc = [{"scope": "TP100", "concentration_flag": False}, {"scope": "TP125", "concentration_flag": False}, {"scope": "STAGED", "concentration_flag": False}]
    assert e.choose_label(policy, dd, conc, 0.9) == "tp100_preferred_under_fixed_iv_reference_model"
    assert e.choose_label(policy, dd, conc, 0.5) == "insufficient_formal_path_coverage"


def test_cli_rejects_parameter_overrides() -> None:
    from scripts.build_morita_s_tp_comparison_v2 import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--run", "--iv", "0.8"])
