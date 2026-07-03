from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_theme_breadth_quick_screen_v1.py"


spec = importlib.util.spec_from_file_location("breadth", SCRIPT_PATH)
breadth = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(breadth)


def make_price_frame(members: list[str], periods: int = 90) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    rows = []
    for ticker_index, ticker in enumerate(members):
        base = 50 + ticker_index
        for idx, dt in enumerate(dates):
            rows.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "open": base + idx * 0.1,
                    "high": base + idx * 0.1 + 1,
                    "low": base + idx * 0.1 - 1,
                    "close": base + idx * 0.1,
                    "volume": 1000 + idx,
                    "raw_or_adjusted": "synthetic",
                }
            )
    return pd.DataFrame(rows)


def make_baseline_fixture(tmp_path: Path) -> tuple[Path, Path]:
    baskets = breadth.read_baskets()
    members = sorted(set(baskets["ai_infrastructure_extended"]))
    input_root = tmp_path / "input"
    source_dir = input_root / "sources"
    source_dir.mkdir(parents=True)
    ohlcv = make_price_frame(members)
    ohlcv.to_csv(source_dir / "daily_ohlcv_merged.csv", index=False)
    decisions = pd.DataFrame(
        {
            "observation_date": pd.bdate_range("2024-04-01", periods=20).strftime("%Y-%m-%d"),
            "next_eligible_session": pd.bdate_range("2024-04-02", periods=20).strftime("%Y-%m-%d"),
            "decision_timestamp_convention": "synthetic_close",
        }
    )
    decisions.to_csv(source_dir / "decision_schedule.csv", index=False)
    (input_root / "source_manifest.json").write_text('{"fixture": true}\n', encoding="utf-8")
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    signals = pd.DataFrame(
        [
            {
                "signal_id": "s1",
                "signal_decision_date": "2024-04-01",
                "signal_decision_timestamp_utc": "2024-04-01T21:00:00Z",
                "entry_session": "2024-04-02",
                "underlying_symbol": "NVDA",
                "signal_rank": "S",
                "strategy_family": "fixture",
                "theme": "Semiconductor",
                "outcome_status": "complete",
                "breakout_day_low_breach_before_timeout": False,
                "timeout_10_sessions_under_threshold": False,
                "reached_plus_5pct_within_10_sessions": True,
            },
            {
                "signal_id": "s2",
                "signal_decision_date": "2024-04-02",
                "signal_decision_timestamp_utc": "2024-04-02T21:00:00Z",
                "entry_session": "2024-04-03",
                "underlying_symbol": "ANET",
                "signal_rank": "A",
                "strategy_family": "fixture",
                "theme": "AI Infrastructure",
                "outcome_status": "ambiguous_intraday_order",
                "breakout_day_low_breach_before_timeout": False,
                "timeout_10_sessions_under_threshold": False,
                "reached_plus_5pct_within_10_sessions": False,
            },
        ]
    )
    signals.to_csv(baseline / "morita_bot_baseline_panel.csv", index=False)
    lineage = {
        "inputs": [
            {
                "input_id": "fixture",
                "repository_relative_path_or_local_alias": str(input_root),
                "sha256": breadth.file_sha256(input_root / "source_manifest.json"),
                "required_for_signal_or_outcome": True,
            }
        ]
    }
    (baseline / "source_input_lineage.json").write_text(json.dumps(lineage), encoding="utf-8")
    breadth.build_manifest(baseline, "source_content_manifest.json")
    return baseline, input_root


def test_no_network_provider_or_actionization_code_exists():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    forbidden = ["import requests", "yfinance", "urllib", "socket", "aiohttp", "option_pnl", "delta", "slippage"]
    assert not any(token in text for token in forbidden)
    assert "--ohlcv" not in text


def test_static_baskets_are_deterministic_deduped_and_nested():
    baskets = breadth.read_baskets()
    assert len(baskets["semiconductor_core"]) == len(set(baskets["semiconductor_core"]))
    assert len(baskets["ai_infrastructure_extended"]) == len(set(baskets["ai_infrastructure_extended"]))
    assert set(baskets["semiconductor_core"]).issubset(set(baskets["ai_infrastructure_extended"]))
    assert len(baskets["semiconductor_core"]) == 34
    assert len(baskets["ai_infrastructure_extended"]) == 46


def test_daily_breadth_excludes_absent_members_has_valid_gate_and_no_future_dependency():
    members = breadth.read_baskets()["semiconductor_core"][:12]
    ohlcv = make_price_frame(members, periods=90)
    decision_dates = pd.bdate_range("2024-04-15", periods=5).strftime("%Y-%m-%d").tolist()
    baskets = {"semiconductor_core": members + ["MISSING"]}
    first = breadth.compute_daily_breadth(ohlcv, decision_dates, baskets, 12)
    assert first["valid_member_count"].min() == 12
    assert set(first["breadth_status"]) == {"valid_basket_coverage"}
    mutated = ohlcv.copy()
    future_mask = pd.to_datetime(mutated["date"]) > pd.Timestamp(decision_dates[0])
    mutated.loc[future_mask, "close"] = mutated.loc[future_mask, "close"] * 10
    second = breadth.compute_daily_breadth(mutated, decision_dates, baskets, 12)
    cols = ["pct_above_20d_ma", "pct_above_50d_ma", "pct_at_65d_high", "median_return_20d"]
    pd.testing.assert_series_equal(first.loc[0, cols], second.loc[0, cols], check_names=False)
    too_sparse = breadth.compute_daily_breadth(ohlcv[ohlcv["ticker"].isin(members[:11])], decision_dates, baskets, 12)
    assert set(too_sparse["breadth_status"]) == {"insufficient_basket_coverage"}


def test_state_cutoffs_are_full_coverage_p25_p75_once():
    daily = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=100).strftime("%Y-%m-%d"),
            "basket": "semiconductor_core",
            "basket_membership_status": breadth.BASKET_STATUS,
            "valid_member_count": 12,
            "breadth_status": "valid_basket_coverage",
        }
    )
    for metric in breadth.METRICS:
        daily[metric] = list(range(100))
        daily[f"{metric}_valid_member_count"] = 12
    stated, cutoffs = breadth.assign_states(daily, 12)
    pct_row = cutoffs[(cutoffs["metric"] == "pct_above_20d_ma")].iloc[0]
    assert pct_row["p25"] == pytest.approx(24.75)
    assert pct_row["p75"] == pytest.approx(74.25)
    assert stated.loc[0, "pct_above_20d_ma_state"] == "low"
    assert stated.loc[99, "pct_above_20d_ma_state"] == "high"
    assert stated.loc[0, "cross_sectional_dispersion_20d_state"] == "low_dispersion"
    assert stated.loc[99, "cross_sectional_dispersion_20d_state"] == "high_dispersion"


def test_signal_join_uses_decision_date_not_entry_date_and_complete_denominator_only():
    panel = pd.DataFrame(
        [
            {
                "signal_id": "s1",
                "signal_decision_date": "2024-01-02",
                "entry_session": "2024-01-03",
                "underlying_symbol": "NVDA",
                "signal_rank": "S",
                "theme": "Semiconductor",
                "outcome_status": "complete",
                "reached_plus_5pct_within_10_sessions": True,
                "breakout_day_low_breach_before_timeout": False,
                "timeout_10_sessions_under_threshold": False,
            },
            {
                "signal_id": "s2",
                "signal_decision_date": "2024-01-02",
                "entry_session": "2024-01-03",
                "underlying_symbol": "NVDA",
                "signal_rank": "S",
                "theme": "Semiconductor",
                "outcome_status": "ambiguous_intraday_order",
                "reached_plus_5pct_within_10_sessions": False,
                "breakout_day_low_breach_before_timeout": True,
                "timeout_10_sessions_under_threshold": False,
            },
        ]
    )
    daily = pd.DataFrame(
        [
            {
                "date": "2024-01-02",
                "basket": "semiconductor_core",
                "basket_membership_status": breadth.BASKET_STATUS,
                "breadth_status": "valid_basket_coverage",
                "valid_member_count": 12,
                **{m: 1.0 for m in breadth.METRICS},
                **{f"{m}_valid_member_count": 12 for m in breadth.METRICS},
                **{f"{m}_state": ("high_dispersion" if m == breadth.DISPERSION_METRIC else "high") for m in breadth.METRICS},
            },
            {
                "date": "2024-01-03",
                "basket": "semiconductor_core",
                "basket_membership_status": breadth.BASKET_STATUS,
                "breadth_status": "valid_basket_coverage",
                "valid_member_count": 12,
                **{m: 0.0 for m in breadth.METRICS},
                **{f"{m}_valid_member_count": 12 for m in breadth.METRICS},
                **{f"{m}_state": ("low_dispersion" if m == breadth.DISPERSION_METRIC else "low") for m in breadth.METRICS},
            },
        ]
    )
    baskets = {"semiconductor_core": ["NVDA"], "ai_infrastructure_extended": ["NVDA"]}
    context = breadth.build_signal_context(panel, daily, baskets)
    assert set(context[context["metric"] == "pct_above_20d_ma"]["breadth_state"]) == {"high"}
    summary = breadth.state_summary(context)
    row = summary[(summary["metric"] == "pct_above_20d_ma") & (summary["breadth_state"] == "high") & (summary["rank"] == "S")].iloc[0]
    assert row["complete_signal_count"] == 1
    assert row["collision_signal_count"] == 1
    assert row["plus5_success_rate"] == pytest.approx(1.0)


def test_rank_separation_sample_gate_and_concentration_guard():
    rows = []
    for idx in range(20):
        rows.append(
            {
                "scope": "semiconductor_signals",
                "scope_type": "primary",
                "basket": "semiconductor_core",
                "metric": "pct_above_20d_ma",
                "breadth_state": "high",
                "signal_rank": "S",
                "underlying_symbol": "NVDA" if idx < 6 else f"T{idx}",
                "outcome_status": "complete",
                "reached_plus_5pct_within_10_sessions": True,
                "breakout_day_low_breach_before_timeout": False,
                "timeout_10_sessions_under_threshold": False,
            }
        )
        rows.append(
            {
                "scope": "semiconductor_signals",
                "scope_type": "primary",
                "basket": "semiconductor_core",
                "metric": "pct_above_20d_ma",
                "breadth_state": "low",
                "signal_rank": "S",
                "underlying_symbol": f"L{idx}",
                "outcome_status": "complete",
                "reached_plus_5pct_within_10_sessions": False,
                "breakout_day_low_breach_before_timeout": True,
                "timeout_10_sessions_under_threshold": False,
            }
        )
    rows.append({**rows[0], "signal_rank": "A", "underlying_symbol": "A1"})
    rank_summary, concentration = breadth.build_rank_summary(pd.DataFrame(rows), min_complete=20, concentration_max=0.25)
    s_row = rank_summary[(rank_summary["rank"] == "S") & (rank_summary["metric"] == "pct_above_20d_ma")].iloc[0]
    a_row = rank_summary[(rank_summary["rank"] == "A") & (rank_summary["metric"] == "pct_above_20d_ma")].iloc[0]
    assert s_row["comparison_status"] == "sufficient_sample"
    assert s_row["concentration_guard_status"] == "concentration_breach"
    assert s_row["relationship_label"] == "inconsistent_relationship"
    assert a_row["comparison_status"] == "insufficient_sample"
    assert concentration[concentration["rank"].eq("S")]["largest_single_ticker_share_high"].iloc[0] == pytest.approx(0.30)


def test_manifest_verification_detects_missing_changed_and_extra_files(tmp_path: Path):
    out = tmp_path / "manifested"
    out.mkdir()
    (out / "breadth_daily_panel.csv").write_text("a\n1\n", encoding="utf-8")
    for name in breadth.REQUIRED_OUTPUTS:
        path = out / name
        if not path.exists():
            path.write_text("fixture\n", encoding="utf-8")
    breadth.build_manifest(out, breadth.MANIFEST_NAME)
    assert breadth.verify_run(out)["status"] == "morita_theme_breadth_quick_screen_verified"
    (out / "extra.csv").write_text("bad\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        breadth.verify_run(out)


def test_full_fixture_run_has_no_composite_or_actionization_and_does_not_change_baseline(tmp_path: Path):
    baseline, _ = make_baseline_fixture(tmp_path)
    before = breadth.file_sha256(baseline / "source_content_manifest.json")
    output_dir = tmp_path / "out"
    result = breadth.build_run(baseline, output_dir)
    after = breadth.file_sha256(baseline / "source_content_manifest.json")
    assert result["status"] == "morita_theme_breadth_quick_screen_completed"
    assert before == after
    for file_name in ["breadth_daily_panel.csv", "breadth_signal_context_panel.csv", "breadth_rank_summary.csv"]:
        cols = pd.read_csv(output_dir / file_name, nrows=1).columns
        joined = ",".join(cols).lower()
        assert "composite" not in joined
        assert "sizing" not in joined
        assert "alert" not in joined
    receipt = json.loads((output_dir / "breadth_receipt.json").read_text(encoding="utf-8"))
    assert receipt["new_data_used"] is False
    assert receipt["bot_rerun_or_rule_change"] is False
    assert receipt["option_analysis_performed"] is False
    assert receipt["parameter_optimization_performed"] is False
    assert receipt["actionization_allowed"] is False
