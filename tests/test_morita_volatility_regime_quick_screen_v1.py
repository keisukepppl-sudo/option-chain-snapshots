from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_volatility_regime_quick_screen_v1.py"
spec = importlib.util.spec_from_file_location("vol_screen", SCRIPT_PATH)
vol = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(vol)


def make_ohlcv(members: list[str], periods: int = 80) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    rows = []
    for ticker_idx, ticker in enumerate(["QQQ", *members]):
        base = 100 + ticker_idx
        for idx, dt in enumerate(dates):
            rows.append({"date": dt, "ticker": ticker, "close": base * (1.0 + 0.001 * idx + 0.0001 * ticker_idx * idx)})
    return pd.DataFrame(rows)


def test_basket_mapping_deterministic_and_deduped():
    baskets = vol.read_baskets()
    assert len(baskets["semiconductor_core"]) == 34
    assert len(baskets["ai_infrastructure_extended"]) == 46
    assert len(baskets["semiconductor_core"]) == len(set(baskets["semiconductor_core"]))
    assert set(baskets["semiconductor_core"]).issubset(set(baskets["ai_infrastructure_extended"]))


def test_theme_vol_excludes_missing_members_never_fills_and_future_mutation_does_not_change_prior_metric():
    members = vol.read_baskets()["semiconductor_core"][:12]
    ohlcv = make_ohlcv(members)
    decisions = pd.bdate_range("2024-04-15", periods=5).strftime("%Y-%m-%d").tolist()
    spec = {"realized_vol_window_sessions": 20, "minimum_valid_member_count": 12, "annualization_sessions": 252}
    panel = vol.compute_theme_volatility(ohlcv, decisions, {"semiconductor_core": members + ["MISSING"], "ai_infrastructure_extended": members}, spec)
    assert panel["semiconductor_core_valid_member_count"].min() == 12
    assert panel["semiconductor_core_theme_realized_vol_20d"].notna().all()
    mutated = ohlcv.copy()
    first_date = pd.Timestamp(decisions[0])
    mutated.loc[mutated["date"] > first_date, "close"] *= 100
    mutated_panel = vol.compute_theme_volatility(mutated, decisions, {"semiconductor_core": members + ["MISSING"], "ai_infrastructure_extended": members}, spec)
    assert panel.loc[0, "semiconductor_core_theme_realized_vol_20d"] == pytest.approx(mutated_panel.loc[0, "semiconductor_core_theme_realized_vol_20d"])
    sparse = vol.compute_theme_volatility(ohlcv[~ohlcv["ticker"].eq(members[-1])], decisions, {"semiconductor_core": members, "ai_infrastructure_extended": members}, spec)
    assert sparse["semiconductor_core_theme_realized_vol_20d"].isna().all()


def test_qqq_realized_vol_and_relative_ratio_handle_zero_denominator():
    returns = pd.Series([0.01] * 20)
    annualized = vol.annualized_vol(returns, 20, 252)
    assert annualized.iloc[-1] == pytest.approx(0.0)
    members = vol.read_baskets()["semiconductor_core"][:12]
    dates = pd.bdate_range("2024-01-02", periods=80)
    rows = []
    for ticker in ["QQQ", *members]:
        for idx, dt in enumerate(dates):
            close = 100 if ticker == "QQQ" else 100 + idx + len(ticker) * 0.01
            rows.append({"date": dt, "ticker": ticker, "close": close})
    panel = vol.compute_theme_volatility(pd.DataFrame(rows), pd.bdate_range("2024-04-15", periods=2).strftime("%Y-%m-%d").tolist(), {"semiconductor_core": members, "ai_infrastructure_extended": members}, {"realized_vol_window_sessions": 20, "minimum_valid_member_count": 12, "annualization_sessions": 252})
    assert panel["semiconductor_core_theme_to_qqq_realized_vol_ratio_20d"].isna().all()


def test_states_use_unique_complete_signal_dates_once():
    panel = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=90).strftime("%Y-%m-%d"), "vxn_level": range(90), "vxn_change_5d": range(90)})
    complete_dates = pd.bdate_range("2024-02-01", periods=30).strftime("%Y-%m-%d").tolist()
    stated, cutoffs = vol.assign_states(panel, complete_dates, ["vxn_level", "vxn_change_5d"])
    assert cutoffs[cutoffs["metric"].eq("vxn_level")]["valid_complete_signal_date_count"].iloc[0] == 30
    assert "low" in set(stated["vxn_level_state"])
    assert "high" in set(stated["vxn_level_state"])
    assert "vxn_falling_or_low_change" in set(stated["vxn_change_5d_state"])
    assert "vxn_rising_or_high_change" in set(stated["vxn_change_5d_state"])


def test_signal_alignment_complete_denominator_and_rank_separation():
    baseline = pd.DataFrame(
        [
            {"signal_id": "s1", "signal_decision_date": "2024-01-02", "entry_session": "2024-01-03", "underlying_symbol": "NVDA", "signal_rank": "S", "theme": "Semi", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": True, "breakout_day_low_breach_before_timeout": False, "timeout_10_sessions_under_threshold": False},
            {"signal_id": "s2", "signal_decision_date": "2024-01-02", "entry_session": "2024-01-03", "underlying_symbol": "NVDA", "signal_rank": "S", "theme": "Semi", "outcome_status": "ambiguous_intraday_order", "reached_plus_5pct_within_10_sessions": False, "breakout_day_low_breach_before_timeout": True, "timeout_10_sessions_under_threshold": False},
            {"signal_id": "s3", "signal_decision_date": "2024-01-03", "entry_session": "2024-01-04", "underlying_symbol": "NVDA", "signal_rank": "A", "theme": "Semi", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": False, "breakout_day_low_breach_before_timeout": True, "timeout_10_sessions_under_threshold": False},
        ]
    )
    vxn_panel = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "vxn_level": [10, 99], "vxn_level_state": ["low", "high"], "vxn_change_5d": [0.0, 1.0], "vxn_change_5d_state": ["vxn_falling_or_low_change", "vxn_rising_or_high_change"]})
    theme_panel = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"]})
    for metric in vol.THEME_METRICS:
        theme_panel[metric] = [1.0, 2.0]
        theme_panel[f"{metric}_state"] = ["low", "high"]
    baskets = {"semiconductor_core": ["NVDA"], "ai_infrastructure_extended": ["NVDA"]}
    context = vol.build_signal_context(baseline, vxn_panel, theme_panel, baskets)
    assert set(context[context["metric"].eq("vxn_level") & context["signal_id"].eq("s1")]["metric_state"]) == {"low"}
    summary = vol.build_outcome_summary(context)
    row = summary[(summary["scope"].eq("nasdaq_volatility")) & (summary["metric"].eq("vxn_level")) & (summary["metric_state"].eq("low")) & (summary["rank"].eq("S"))].iloc[0]
    assert row["complete_signal_count"] == 1
    assert row["collision_signal_count"] == 1
    assert row["plus5_success_rate"] == pytest.approx(1.0)


def test_high_low_sample_gate_and_concentration():
    rows = []
    for idx in range(15):
        rows.append({"scope": "nasdaq_volatility", "scope_type": "primary", "basket": "all", "metric": "vxn_level", "metric_state": "high", "signal_rank": "S", "underlying_symbol": "NVDA" if idx < 5 else f"H{idx}", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": True, "breakout_day_low_breach_before_timeout": False, "timeout_10_sessions_under_threshold": False})
        rows.append({"scope": "nasdaq_volatility", "scope_type": "primary", "basket": "all", "metric": "vxn_level", "metric_state": "low", "signal_rank": "S", "underlying_symbol": f"L{idx}", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": False, "breakout_day_low_breach_before_timeout": True, "timeout_10_sessions_under_threshold": False})
    rows.append({**rows[0], "signal_rank": "B", "underlying_symbol": "B1"})
    summary, concentration = vol.build_rank_summary(pd.DataFrame(rows), 15, 0.30)
    s_row = summary[(summary["rank"].eq("S")) & (summary["metric"].eq("vxn_level"))].iloc[0]
    b_row = summary[(summary["rank"].eq("B")) & (summary["metric"].eq("vxn_level"))].iloc[0]
    assert s_row["comparison_status"] == "sufficient_sample"
    assert s_row["concentration_guard_status"] == "concentration_breach"
    assert s_row["relationship_label"] == "inconsistent_relationship"
    assert b_row["comparison_status"] == "insufficient_sample"
    assert concentration[concentration["rank"].eq("S")]["largest_single_ticker_share_high"].iloc[0] == pytest.approx(5 / 15)


def test_manifest_rejects_missing_changed_extra(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    for name in vol.REQUIRED_OUTPUTS:
        (out / name).write_text("fixture\n", encoding="utf-8")
    vol.build_manifest(out, vol.MANIFEST_NAME)
    assert vol.verify_run(out)["status"] == "morita_volatility_regime_quick_screen_verified"
    (out / "extra.csv").write_text("bad\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        vol.verify_run(out)


def test_no_composite_actionization_or_arbitrary_ohlcv_override_code_exists():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "--ohlcv" not in text
    assert "composite" not in text.lower()
    assert "actionization_allowed\": True" not in text
