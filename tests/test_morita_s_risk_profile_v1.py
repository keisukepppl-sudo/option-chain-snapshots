from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_s_risk_profile_v1.py"
spec = importlib.util.spec_from_file_location("s_risk", SCRIPT_PATH)
s_risk = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(s_risk)


SPEC = {
    "baseline_run_id": "fixture",
    "baseline_entry_price_field": "entry_price",
    "baseline_stop_reference_field": "breakout_day_low",
    "primary_rank": "S",
    "complete_status": "complete",
    "collision_status": "ambiguous_intraday_order",
    "incomplete_status": "incomplete_horizon",
    "fixed_horizon_sessions": [1, 5, 10, 20],
    "mae_thresholds": [-0.05, -0.1, -0.15, -0.2],
    "stop_distance_thresholds": [-0.03, -0.05, -0.08, -0.1],
    "stop_overshoot_thresholds": [-0.02, -0.05, -0.1, -0.15],
    "post_breach_horizons": [5, 10],
    "recovery_horizons": [5, 10],
    "percentile_method": "pandas_linear_interpolation",
    "execution_label": "daily_bar_execution_proxy_only",
}


def baseline() -> pd.DataFrame:
    rows = [
        {
            "signal_id": "s1",
            "signal_decision_date": "2024-01-02",
            "entry_session": "2024-01-03",
            "underlying_symbol": "AAA",
            "signal_rank": "S",
            "theme": "Semi",
            "entry_price": 100.0,
            "breakout_day_low": 95.0,
            "outcome_status": "complete",
            "breakout_day_low_breach_before_timeout": True,
            "timeout_10_sessions_under_threshold": False,
            "reached_plus_5pct_within_10_sessions": False,
            "holding_sessions_at_exit_or_timeout": 3,
            "exit_event_category": "breakout_day_low_breach",
            "outcome_observed_through_session": "2024-01-05",
        },
        {
            "signal_id": "s2",
            "signal_decision_date": "2024-01-02",
            "entry_session": "2024-01-03",
            "underlying_symbol": "BBB",
            "signal_rank": "A",
            "theme": "Other",
            "entry_price": 50.0,
            "breakout_day_low": 49.0,
            "outcome_status": "complete",
            "breakout_day_low_breach_before_timeout": False,
            "timeout_10_sessions_under_threshold": False,
            "reached_plus_5pct_within_10_sessions": True,
            "holding_sessions_at_exit_or_timeout": 2,
            "exit_event_category": "profit_target",
            "outcome_observed_through_session": "2024-01-04",
        },
        {
            "signal_id": "s3",
            "signal_decision_date": "2024-01-03",
            "entry_session": "2024-01-04",
            "underlying_symbol": "AAA",
            "signal_rank": "S",
            "theme": "Semi",
            "entry_price": 101.0,
            "breakout_day_low": 98.0,
            "outcome_status": "ambiguous_intraday_order",
            "breakout_day_low_breach_before_timeout": True,
            "timeout_10_sessions_under_threshold": False,
            "reached_plus_5pct_within_10_sessions": False,
            "holding_sessions_at_exit_or_timeout": 1,
            "exit_event_category": "ambiguous",
            "outcome_observed_through_session": "2024-01-04",
        },
    ]
    df = pd.DataFrame(rows)
    df["entry_session"] = pd.to_datetime(df["entry_session"])
    df["signal_decision_date"] = pd.to_datetime(df["signal_decision_date"])
    df["outcome_observed_through_session"] = pd.to_datetime(df["outcome_observed_through_session"])
    return df


def ohlcv() -> pd.DataFrame:
    rows = [{"date": "2024-01-02", "ticker": "AAA", "open": 150, "high": 151, "low": 50, "close": 150}]
    lows = [99, 97, 94, 93, 92, 96, 97, 100, 106, 104]
    opens = [100, 96, 94, 93, 92, 97, 98, 105, 105, 103]
    for i, (lo, opn) in enumerate(zip(lows, opens), start=3):
        rows.append({"date": f"2024-01-{i:02d}", "ticker": "AAA", "open": opn, "high": max(opn, lo) + 2, "low": lo, "close": opn + 1})
    for i in range(3, 8):
        rows.append({"date": f"2024-01-{i:02d}", "ticker": "BBB", "open": 50, "high": 55, "low": 49, "close": 54})
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"])
    return out


def test_no_network_provider_actionization_code_exists():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for token in ["requests", "urllib", "yfinance", "--ohlcv", "--entry", "--stop", "--threshold"]:
        assert token not in text
    assert '"actionization_allowed": true' not in text


def test_baseline_required_fields_are_mandatory(tmp_path: Path):
    p = tmp_path / "morita_bot_baseline_panel.csv"
    pd.DataFrame({"signal_id": ["x"]}).to_csv(p, index=False)
    with pytest.raises(SystemExit):
        s_risk.load_baseline(tmp_path)


def test_s_only_complete_filter_mae_no_pre_entry_gap_and_recovery():
    context = s_risk.build_signal_context(baseline(), ohlcv(), SPEC)
    assert set(context["rank"]) == {"S"}
    s1 = context[context["signal_id"] == "s1"].iloc[0]
    assert s1["fixed_horizon_mae_1d"] == pytest.approx(-0.01)
    assert s1["fixed_horizon_mae_5d"] == pytest.approx(-0.08)
    assert s1["fixed_horizon_mae_10d"] == pytest.approx(-0.08)
    assert pd.isna(s1["fixed_horizon_mae_20d"])
    assert s1["initial_stop_distance"] == pytest.approx(-0.05)
    assert s1["first_breach_date"] == "2024-01-05"
    assert s1["first_breach_low_undershoot"] == pytest.approx(94 / 95 - 1)
    assert bool(s1["gap_through_stop"]) is True
    assert s1["gap_through_amount"] == pytest.approx(94 / 95 - 1)
    assert s1["daily_open_fill_proxy_loss_from_entry"] == pytest.approx(-0.06)
    assert bool(s1["reclaim_stop_on_close_within_5d"]) is True
    assert bool(s1["reach_plus_5pct_from_entry_on_high_within_5d_after_breach"]) is True
    coverage = s_risk.build_coverage(context, SPEC)
    assert int(coverage.loc[coverage["cohort"] == "primary_complete_S", "signal_count"].iloc[0]) == 1
    assert int(coverage.loc[coverage["cohort"] == "diagnostic_collision_S", "signal_count"].iloc[0]) == 1


def test_future_ohlcv_mutation_cannot_change_earlier_horizon():
    original = s_risk.build_signal_context(baseline(), ohlcv(), SPEC)
    mutated = ohlcv()
    mutated.loc[mutated["date"] > pd.Timestamp("2024-01-07"), "low"] = 1
    changed = s_risk.build_signal_context(baseline(), mutated, SPEC)
    assert original.loc[0, "fixed_horizon_mae_5d"] == changed.loc[0, "fixed_horizon_mae_5d"]
    assert original.loc[0, "fixed_horizon_mae_10d"] != changed.loc[0, "fixed_horizon_mae_10d"]


def test_distribution_tail_order_and_manifest(tmp_path: Path):
    context = s_risk.build_signal_context(baseline(), ohlcv(), SPEC)
    mae = s_risk.build_mae_summary(context, SPEC)
    row = mae[(mae["cohort"] == "primary_complete_S") & (mae["horizon_sessions"] == 5)].iloc[0]
    assert row["mae_share_lte_minus_5pct"] == pytest.approx(1.0)
    tails = s_risk.build_tail_episodes(context)
    assert "fixed_horizon_mae_10d" in set(tails["tail_episode_type"])
    out = tmp_path / "out"
    out.mkdir()
    for name in s_risk.REQUIRED_OUTPUTS:
        (out / name).write_text("fixture\n", encoding="utf-8")
    s_risk.build_manifest(out)
    assert s_risk.verify_run(out)["status"] == "morita_s_risk_profile_verified"
    (out / "extra.csv").write_text("bad\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        s_risk.verify_run(out)
