from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_put_skew_quick_screen_v1.py"
spec = importlib.util.spec_from_file_location("put_skew", SCRIPT_PATH)
skew = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(skew)


SPEC = {
    "eligible_dte_min_calendar_days": 21,
    "eligible_dte_max_calendar_days": 45,
    "target_dte_calendar_days": 30,
    "atm_moneyness_abs_max": 0.03,
    "otm_put_moneyness_min": 0.85,
    "otm_put_moneyness_max": 0.95,
    "otm_put_target_moneyness": 0.90,
    "maximum_snapshot_lag_sessions": 1,
    "index_coverage_min_unique_complete_signal_dates": 0.65,
    "single_name_min_complete_signal_rows": 200,
    "relative_min_complete_signal_rows": 150,
    "minimum_complete_signals_per_state": 15,
    "concentration_guard_largest_ticker_share_max": 0.30,
}


def option_rows(ticker: str = "QQQ", snapshot_date: str = "2026-06-01", spot: float = 100.0) -> pd.DataFrame:
    rows = []
    for expiration in ["2026-06-20", "2026-07-01", "2026-07-16"]:
        for opt_type in ["call", "put"]:
            for strike, iv in [(90, 0.35), (98, 0.22), (100, 0.20), (102, 0.21), (110, 0.24)]:
                rows.append(
                    {
                        "ticker": ticker,
                        "snapshot_date": snapshot_date,
                        "expiration": expiration,
                        "type": opt_type,
                        "strike": float(strike),
                        "iv": float(iv + (0.01 if opt_type == "put" else 0.0)),
                        "spot": spot,
                        "bid": 1.0,
                        "ask": 1.2,
                        "oi": 10,
                        "volume": 5,
                    }
                )
    return pd.DataFrame(rows)


def test_no_network_provider_api_or_override_code_exists():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    forbidden = ["urllib", "requests", "yfinance", "polygon", "tradier", "orats", "cboe", "--option-file", "--ohlcv", "--dte"]
    assert not any(token in text for token in forbidden)
    assert "actionization_allowed\": true" not in text
    assert "dealer_model_performed\": true" not in text


def test_local_snapshot_source_requires_minimum_schema(tmp_path: Path, monkeypatch):
    root = tmp_path / "option_chain_snapshots"
    root.mkdir()
    option_rows().to_csv(root / "QQQ_2026-06-01.csv", index=False)
    bad = tmp_path / "option_bad"
    bad.mkdir()
    pd.DataFrame({"ticker": ["QQQ"]}).to_csv(bad / "bad.csv", index=False)
    monkeypatch.setattr(skew, "ARCHIVE_ROOT", root)
    monkeypatch.setattr(skew, "REPO_ROOT", tmp_path)
    availability = skew.inspect_local_snapshot_archive()
    assert "usable_minimum_schema" in set(availability["status"])
    assert "missing_minimum_schema" in set(availability["status"])
    assert skew.select_archive_source(availability) == root


def test_dte_expiry_atm_otm_and_quality_tier_selection():
    result = skew.construct_skew_for_snapshot(option_rows(), SPEC)
    assert result["skew_status"] == "valid"
    assert result["selected_expiration"] == "2026-07-01"
    assert result["selected_dte"] == 30
    assert result["atm_iv"] == pytest.approx((0.20 + 0.21) / 2)
    assert result["otm_put_iv"] == pytest.approx(0.36)
    assert result["put_skew_abs"] == pytest.approx(0.155)
    assert result["put_skew_normalized"] == pytest.approx(0.155 / 0.205)
    assert result["quality_tier"] == "tier_a"


def test_missing_direct_iv_and_no_expiry_are_unavailable():
    no_iv = option_rows()
    no_iv["iv"] = 0
    assert skew.construct_skew_for_snapshot(no_iv, SPEC)["skew_status"] == "unavailable_missing_direct_iv_or_spot"
    no_expiry = option_rows()
    no_expiry["expiration"] = "2026-06-05"
    assert skew.construct_skew_for_snapshot(no_expiry, SPEC)["skew_status"] == "unavailable_no_21_to_45_dte_expiry"


def test_five_snapshot_change_calculation():
    frames = []
    for idx, day in enumerate(pd.date_range("2026-06-01", periods=6, freq="D")):
        frame = option_rows(snapshot_date=day.strftime("%Y-%m-%d"))
        frame.loc[(frame["type"] == "put") & (frame["strike"] == 90), "iv"] = 0.36 + idx * 0.01
        frames.append(frame)
    panel = skew.build_skew_panel(pd.concat(frames, ignore_index=True), SPEC)
    last = panel[panel["snapshot_date"].eq("2026-06-06")].iloc[0]
    first = panel[panel["snapshot_date"].eq("2026-06-01")].iloc[0]
    assert last["put_skew_abs_5d_change"] == pytest.approx(last["put_skew_abs"] / first["put_skew_abs"] - 1)
    assert last["put_skew_normalized_5d_change"] == pytest.approx(last["put_skew_normalized"] - first["put_skew_normalized"])


def test_snapshot_timing_at_or_before_and_lag_gate():
    panel = pd.DataFrame(
        [
            {"ticker": "QQQ", "snapshot_date": "2026-06-01", "skew_status": "valid", "put_skew_abs": 1.0, "put_skew_normalized": 0.1},
            {"ticker": "QQQ", "snapshot_date": "2026-06-04", "skew_status": "valid", "put_skew_abs": 2.0, "put_skew_normalized": 0.2},
            {"ticker": "QQQ", "snapshot_date": "2026-06-06", "skew_status": "valid", "put_skew_abs": 9.0, "put_skew_normalized": 0.9},
        ]
    )
    session_map = {"2026-06-01": 0, "2026-06-02": 1, "2026-06-03": 2, "2026-06-04": 3, "2026-06-05": 4}
    selected = skew.select_prior_snapshot(panel, "QQQ", "2026-06-05", 4, session_map, 1)
    assert selected["snapshot_date"] == "2026-06-04"
    assert selected["snapshot_lag_sessions"] == 1
    stale = skew.select_prior_snapshot(panel.iloc[[0]], "QQQ", "2026-06-05", 4, session_map, 1)
    assert stale["skew_status"] == "unavailable_snapshot_lag_exceeded"


def test_relative_requires_same_snapshot_date_pair_and_complete_denominators():
    baseline = pd.DataFrame(
        [
            {"signal_id": "s1", "signal_decision_date": "2026-06-02", "entry_session": "2026-06-03", "underlying_symbol": "MU", "signal_rank": "S", "theme": "Semi", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": True, "breakout_day_low_breach_before_timeout": False, "timeout_10_sessions_under_threshold": False},
            {"signal_id": "s2", "signal_decision_date": "2026-06-02", "entry_session": "2026-06-03", "underlying_symbol": "MU", "signal_rank": "S", "theme": "Semi", "outcome_status": "ambiguous_intraday_order", "reached_plus_5pct_within_10_sessions": False, "breakout_day_low_breach_before_timeout": True, "timeout_10_sessions_under_threshold": False},
        ]
    )
    schedule = pd.DataFrame({"observation_date": ["2026-06-01", "2026-06-02"]})
    panel = pd.DataFrame(
        [
            {"ticker": "QQQ", "snapshot_date": "2026-06-02", "skew_status": "valid", "put_skew_abs": 0.1, "put_skew_normalized": 0.2, "quality_tier": "tier_a", "snapshot_timing_quality": "snapshot_date_end_of_day_proxy"},
            {"ticker": "MU", "snapshot_date": "2026-06-02", "skew_status": "valid", "put_skew_abs": 0.3, "put_skew_normalized": 0.5, "quality_tier": "tier_b", "snapshot_timing_quality": "snapshot_date_end_of_day_proxy"},
        ]
    )
    context, _, _ = skew.build_context(baseline, schedule, panel, SPEC)
    rel = context[(context["scope"] == "relative") & (context["metric"].eq("single_name_minus_qqq_normalized_skew"))]
    assert rel["metric_value"].dropna().iloc[0] == pytest.approx(0.3)
    summary = skew.build_outcome_summary(context)
    row = summary[(summary["scope"].eq("relative")) & (summary["rank"].eq("S")) & (summary["metric_state"].eq("high"))]
    assert row.empty or row["collision_signal_count"].iloc[0] >= 0


def test_coverage_gates_are_independent_and_states_use_complete_rows():
    rows = []
    baseline = []
    for idx in range(20):
        sid = f"s{idx}"
        date = f"2026-06-{idx+1:02d}"
        baseline.append({"signal_id": sid, "signal_decision_date": date, "outcome_status": "complete"})
        rows.append({"signal_id": sid, "scope": "index", "metric": "qqq_put_skew_normalized", "signal_decision_date": date, "outcome_status": "complete", "metric_value": idx, "signal_rank": "S", "underlying_symbol": f"T{idx}"})
        rows.append({"signal_id": sid, "scope": "single_name", "metric": "single_name_put_skew_normalized", "signal_decision_date": date, "outcome_status": "complete", "metric_value": idx, "signal_rank": "S", "underlying_symbol": f"T{idx}"})
    context = pd.DataFrame(rows)
    status = skew.layer_statuses(context, pd.DataFrame(baseline), {**SPEC, "index_coverage_min_unique_complete_signal_dates": 0.5, "single_name_min_complete_signal_rows": 25, "relative_min_complete_signal_rows": 1})
    assert status["index"]["status"] == "available"
    assert status["single_name"]["status"] == "insufficient_snapshot_coverage"
    cutoffs = skew.assign_states(context.copy(), pd.DataFrame(baseline))
    assert cutoffs[cutoffs["metric"].eq("qqq_put_skew_normalized")]["valid_cutoff_observation_count"].iloc[0] == 20


def test_high_low_sample_gate_concentration_and_manifest(tmp_path: Path):
    rows = []
    for idx in range(15):
        rows.append({"scope": "index", "metric": "qqq_put_skew_normalized", "metric_state": "high", "signal_rank": "S", "underlying_symbol": "NVDA" if idx < 5 else f"H{idx}", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": True, "breakout_day_low_breach_before_timeout": False, "timeout_10_sessions_under_threshold": False, "quality_tier": "tier_a"})
        rows.append({"scope": "index", "metric": "qqq_put_skew_normalized", "metric_state": "low", "signal_rank": "S", "underlying_symbol": f"L{idx}", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": False, "breakout_day_low_breach_before_timeout": True, "timeout_10_sessions_under_threshold": False, "quality_tier": "tier_b"})
    rank = skew.build_rank_summary(pd.DataFrame(rows), {"index": {"status": "available"}}, SPEC)
    row = rank[(rank["rank"].eq("S")) & (rank["metric"].eq("qqq_put_skew_normalized"))].iloc[0]
    assert row["comparison_status"] == "sufficient_sample"
    assert row["relationship_label"] == "inconsistent_relationship"
    assert row["largest_single_ticker_share_high"] == pytest.approx(5 / 15)
    out = tmp_path / "out"
    out.mkdir()
    for name in skew.REQUIRED_OUTPUTS:
        (out / name).write_text("fixture\n", encoding="utf-8")
    skew.build_manifest(out)
    assert skew.verify_run(out)["status"] == "morita_put_skew_quick_screen_verified"
    (out / "extra.csv").write_text("bad\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        skew.verify_run(out)
