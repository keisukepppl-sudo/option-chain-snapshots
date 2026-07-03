from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_realized_dispersion_quick_screen_v1.py"
spec = importlib.util.spec_from_file_location("dispersion", SCRIPT_PATH)
disp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(disp)


SPEC = {
    "realized_window_sessions": 20,
    "annualization_sessions": 252,
    "minimum_valid_members": {"broad_russell1000_local_proxy": 3, "semiconductor_core": 3, "ai_infrastructure_extended": 3},
    "benchmark_exclusions": ["QQQ"],
    "minimum_complete_signals_per_high_or_low_state": 15,
    "concentration_guard_largest_ticker_share_max": 0.30,
}


def make_ohlcv(tickers: list[str], periods: int = 70) -> pd.DataFrame:
    rows = []
    dates = pd.bdate_range("2024-01-02", periods=periods)
    for t_idx, ticker in enumerate(["QQQ", *tickers]):
        for i, dt in enumerate(dates):
            rows.append({"date": dt, "ticker": ticker, "close": 100 + t_idx * 2 + i * (1 + t_idx * 0.05)})
    return pd.DataFrame(rows)


def test_no_network_provider_option_or_actionization_code_exists():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    forbidden = ["requests", "urllib", "yfinance", "--ohlcv", "vix", "vxn", "option_chain"]
    assert not any(token in text for token in forbidden)
    assert "actionization_allowed\": true" not in text


def test_static_baskets_are_deterministic_and_broad_comes_from_ohlcv_only():
    ohlcv = make_ohlcv(["A", "B", "C", "SMH"])
    baskets = disp.build_baskets(ohlcv, SPEC)
    assert "QQQ" not in baskets["broad_russell1000_local_proxy"]
    assert set(["A", "B", "C", "SMH"]).issubset(set(baskets["broad_russell1000_local_proxy"]))
    static = disp.read_static_baskets()
    assert len(static["semiconductor_core"]) == len(set(static["semiconductor_core"]))
    assert set(static["semiconductor_core"]).issubset(set(static["ai_infrastructure_extended"]))


def test_equal_weight_dispersion_participation_vol_corr_and_divergence():
    tickers = ["A", "B", "C"]
    ohlcv = make_ohlcv(tickers, periods=45)
    decision_dates = pd.bdate_range("2024-02-20", periods=2).strftime("%Y-%m-%d").tolist()
    panel = disp.compute_daily_panel(ohlcv, decision_dates, {"broad_russell1000_local_proxy": tickers, "semiconductor_core": tickers, "ai_infrastructure_extended": tickers}, SPEC)
    row = panel[(panel["basket"] == "broad_russell1000_local_proxy")].iloc[0]
    assert row["valid_member_count"] == 3
    assert row["coverage_status"] == "valid_basket_coverage"
    assert 0 <= row["pct_positive_return_20d"] <= 1
    assert row["cross_sectional_dispersion_20d"] >= 0
    assert row["eqw_realized_vol_20d"] >= 0
    assert pd.notna(row["qqq_minus_eqw_return_20d"])
    assert pd.notna(row["realized_average_correlation_proxy_20d"])


def test_missing_members_excluded_never_filled_and_coverage_gate():
    ohlcv = make_ohlcv(["A", "B"], periods=45)
    decision_dates = pd.bdate_range("2024-02-20", periods=1).strftime("%Y-%m-%d").tolist()
    panel = disp.compute_daily_panel(ohlcv, decision_dates, {"broad_russell1000_local_proxy": ["A", "B", "MISSING"], "semiconductor_core": ["A", "B", "MISSING"], "ai_infrastructure_extended": ["A", "B", "MISSING"]}, SPEC)
    assert set(panel["coverage_status"]) == {"insufficient_basket_coverage"}
    assert panel["valid_member_count"].max() == 2


def test_future_ohlcv_mutation_cannot_change_prior_metrics():
    tickers = ["A", "B", "C"]
    ohlcv = make_ohlcv(tickers, periods=60)
    decision_date = pd.bdate_range("2024-02-20", periods=1).strftime("%Y-%m-%d").tolist()
    panel = disp.compute_daily_panel(ohlcv, decision_date, {"broad_russell1000_local_proxy": tickers, "semiconductor_core": tickers, "ai_infrastructure_extended": tickers}, SPEC)
    mutated = ohlcv.copy()
    mutated.loc[mutated["date"] > pd.Timestamp(decision_date[0]), "close"] *= 100
    mutated_panel = disp.compute_daily_panel(mutated, decision_date, {"broad_russell1000_local_proxy": tickers, "semiconductor_core": tickers, "ai_infrastructure_extended": tickers}, SPEC)
    cols = ["cross_sectional_dispersion_20d", "pct_positive_return_20d", "eqw_realized_vol_20d", "qqq_minus_eqw_return_20d"]
    pd.testing.assert_series_equal(panel.loc[0, cols], mutated_panel.loc[0, cols], check_names=False)


def test_correlation_proxy_formula_and_invalid_variance():
    returns = pd.DataFrame({"A": [0.01] * 20, "B": [0.02] * 20, "C": [0.03] * 20})
    assert disp.corr_proxy(returns) is None
    returns = pd.DataFrame({"A": [0.01, -0.01] * 10, "B": [0.02, -0.02] * 10, "C": [0.03, -0.03] * 10})
    value = disp.corr_proxy(returns)
    eqw = returns.mean(axis=1)
    expected = (3 * eqw.var(ddof=0) - returns.var(axis=0, ddof=0).mean()) / (2 * returns.var(axis=0, ddof=0).mean())
    assert value == pytest.approx(expected)


def test_states_use_unique_complete_signal_dates_once():
    daily = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=30).strftime("%Y-%m-%d"), "broad_russell1000_cross_sectional_dispersion_20d": range(30)})
    stated, cutoffs = disp.assign_states(daily, daily["date"].tolist())
    assert cutoffs["valid_complete_signal_date_count"].iloc[0] == 30
    assert set(stated["broad_russell1000_cross_sectional_dispersion_20d_state"]) == {"low", "middle", "high"}


def test_decision_date_alignment_and_complete_denominator():
    baseline = pd.DataFrame(
        [
            {"signal_id": "s1", "signal_decision_date": "2024-01-02", "entry_session": "2024-01-03", "underlying_symbol": "A", "signal_rank": "S", "theme": "", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": True, "breakout_day_low_breach_before_timeout": False, "timeout_10_sessions_under_threshold": False},
            {"signal_id": "s2", "signal_decision_date": "2024-01-02", "entry_session": "2024-01-03", "underlying_symbol": "A", "signal_rank": "S", "theme": "", "outcome_status": "ambiguous_intraday_order", "reached_plus_5pct_within_10_sessions": False, "breakout_day_low_breach_before_timeout": True, "timeout_10_sessions_under_threshold": False},
        ]
    )
    daily = pd.DataFrame({"date": ["2024-01-02"], "broad_russell1000_cross_sectional_dispersion_20d": [1.0], "broad_russell1000_cross_sectional_dispersion_20d_state": ["high"]})
    for base in disp.BASE_METRICS[1:]:
        daily[f"broad_russell1000_{base}"] = 1.0
        daily[f"broad_russell1000_{base}_state"] = "high"
    context = disp.build_signal_context(baseline, daily, {"broad_russell1000_local_proxy": ["A"], "semiconductor_core": [], "ai_infrastructure_extended": []})
    summary = disp.build_outcome_summary(context)
    row = summary[(summary["rank"] == "S") & (summary["metric_state"] == "high")].iloc[0]
    assert row["complete_signal_count"] == 1
    assert row["collision_signal_count"] == 1
    assert row["plus5_success_rate"] == pytest.approx(1.0)


def test_high_low_sample_gate_concentration_and_manifest(tmp_path: Path):
    rows = []
    for i in range(15):
        rows.append({"scope": "broad_market_context", "basket": "broad_russell1000_local_proxy", "metric": "broad_russell1000_pct_positive_return_20d", "metric_state": "high", "signal_rank": "S", "underlying_symbol": "NVDA" if i < 5 else f"H{i}", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": True, "breakout_day_low_breach_before_timeout": False, "timeout_10_sessions_under_threshold": False})
        rows.append({"scope": "broad_market_context", "basket": "broad_russell1000_local_proxy", "metric": "broad_russell1000_pct_positive_return_20d", "metric_state": "low", "signal_rank": "S", "underlying_symbol": f"L{i}", "outcome_status": "complete", "reached_plus_5pct_within_10_sessions": False, "breakout_day_low_breach_before_timeout": True, "timeout_10_sessions_under_threshold": False})
    rank, conc = disp.build_rank_summary(pd.DataFrame(rows), SPEC)
    row = rank[(rank["rank"] == "S")].iloc[0]
    assert row["comparison_status"] == "sufficient_sample"
    assert row["relationship_label"] == "inconsistent_relationship"
    assert conc["largest_single_ticker_share_high"].iloc[0] == pytest.approx(5 / 15)
    out = tmp_path / "out"
    out.mkdir()
    for name in disp.REQUIRED_OUTPUTS:
        (out / name).write_text("fixture\n", encoding="utf-8")
    disp.build_manifest(out)
    assert disp.verify_run(out)["status"] == "morita_realized_dispersion_quick_screen_verified"
    (out / "extra.csv").write_text("bad\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        disp.verify_run(out)
