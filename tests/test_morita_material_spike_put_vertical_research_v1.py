from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_material_spike_put_vertical_research_v1 as mspv


def _policy(path: Path, override: dict | None = None) -> Path:
    payload = {
        "policy_version": "morita_material_spike_put_vertical_v1",
        "mode": "research_only",
        "broker_execution_enabled": False,
        "auto_trade_action_enabled": False,
        "live_signal_enabled": False,
        "rank_change_allowed": False,
        "sizing_change_allowed": False,
        "notification_change_allowed": False,
        "existing_morita_behavior_change_allowed": False,
        "future_leakage_allowed": False,
        "baseline_population": "existing_morita_initial_breakout_candidates",
        "universe_expansion_status": "fixture",
        "material_spike_proxy": {
            "candidate_material_spike": {"gap_pct_min": 0.08, "signal_date_return_min": 0.10, "volume_multiple_min": 3.0, "breakout_excess_pct_min": 0.05},
            "candidate_extreme_material_spike": {"gap_pct_min": 0.15, "signal_date_return_min": 0.20, "volume_multiple_min": 5.0},
        },
        "failure_window_sessions": 5,
        "put_vertical_reference_model": {
            "model_status": "synthetic_fixed_iv_not_historical_option_fill_reconstruction",
            "dte_calendar_days": 35,
            "buy_put_delta": -0.35,
            "sell_put_delta": -0.20,
            "entry_markup": 0.05,
            "exit_haircut": 0.05,
            "iv_scenarios": [0.60, 0.80],
            "post_catalyst_iv_crush_scenarios": [0.0, -0.10],
            "risk_free_rate": 0.0,
        },
        "exit_policies": {
            "PV_5D_TP50_STOP50": {"take_profit_return": 0.50, "stop_loss_return": -0.50, "max_holding_sessions": 5, "exit_on_close_above_d0_high_next_open": True},
            "PV_10D_TP75_STOP50": {"take_profit_return": 0.75, "stop_loss_return": -0.50, "max_holding_sessions": 10, "exit_on_close_above_d0_high_next_open": True},
        },
    }
    if override:
        payload.update(override)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _baseline() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_date": "2026-01-05",
                "ticker": "MRLN",
                "close": 15.0,
                "prior_high": 14.0,
                "volume_multiple": 5.5,
                "gap_pct": 0.18,
                "signal_date_return": 0.22,
                "breakout_excess_pct": 0.071,
                "standard_rs_score": 93.0,
                "production_adjusted_score": 38.0,
                "accumulation_score": 30.0,
                "theme": "AI Infrastructure",
                "d0_low_risk_width_pct": 0.20,
                "market_cap_at_signal": 900_000_000,
                "option_liquidity_available": "false",
                "option_bid_ask_proxy": 0.18,
                "catalyst_type": "ai_pr_or_theme_pr",
            },
            {
                "signal_date": "2026-01-05",
                "ticker": "MRVL",
                "close": 80.0,
                "prior_high": 76.0,
                "volume_multiple": 2.4,
                "gap_pct": 0.06,
                "signal_date_return": 0.07,
                "breakout_excess_pct": 0.052,
                "standard_rs_score": 98.5,
                "production_adjusted_score": 55.0,
                "accumulation_score": 80.0,
                "theme": "Semiconductor",
                "d0_low_risk_width_pct": 0.08,
                "market_cap_at_signal": 90_000_000_000,
                "option_liquidity_available": "true",
                "option_bid_ask_proxy": 0.04,
                "catalyst_type": "earnings_or_guidance",
            },
        ]
    )


def _prices() -> pd.DataFrame:
    dates = pd.bdate_range("2025-12-30", periods=35)
    rows = []
    for ticker in ["MRLN", "MRVL"]:
        for i, date in enumerate(dates):
            if ticker == "MRLN":
                base = 12.0 + i * 0.05
                high = base + 0.3
                low = base - 0.3
                close = base
                volume = 1000
                if date.strftime("%Y-%m-%d") == "2026-01-05":
                    close, high, low, volume = 15.0, 16.0, 13.0, 6000
                elif date.strftime("%Y-%m-%d") == "2026-01-06":
                    close, high, low, volume = 14.2, 15.1, 13.9, 2500
                elif date.strftime("%Y-%m-%d") == "2026-01-07":
                    close, high, low, volume = 13.7, 14.5, 13.2, 2300
                elif date.strftime("%Y-%m-%d") >= "2026-01-08":
                    close = max(10.5, 13.5 - i * 0.18)
                    high = close + 0.4
                    low = close - 0.6
                    volume = 1600
            else:
                base = 74.0 + i * 0.9
                high = base + 1.2
                low = base - 1.0
                close = base
                volume = 3000
                if date.strftime("%Y-%m-%d") == "2026-01-05":
                    close, high, low, volume = 80.0, 82.0, 78.0, 7200
                elif date.strftime("%Y-%m-%d") >= "2026-01-06":
                    close = 81.0 + i * 0.8
                    high = close + 1.5
                    low = close - 0.8
                    volume = 5000
            rows.append({"ticker": ticker, "date": date.strftime("%Y-%m-%d"), "open": close + 0.1, "high": high, "low": low, "close": close, "volume": volume})
    return pd.DataFrame(rows)


def test_buckets_material_proxy_and_catalyst_strength_separate_mrln_from_mrvl(tmp_path: Path) -> None:
    policy = mspv.load_policy(_policy(tmp_path / "policy.json"))
    candidates = mspv.build_candidate_panel(_baseline(), policy)
    by_ticker = {row["ticker"]: row for row in candidates}
    assert by_ticker["MRLN"]["market_cap_bucket"] == "SMALL_300M_2B"
    assert by_ticker["MRLN"]["price_bucket"] == "10_20"
    assert by_ticker["MRLN"]["catalyst_strength_label"] == "PR_WEAK"
    assert by_ticker["MRLN"]["material_spike_label"] == "CANDIDATE_EXTREME_MATERIAL_SPIKE"
    assert by_ticker["MRLN"]["option_liquidity_available"] is False
    assert by_ticker["MRVL"]["market_cap_bucket"] == "LARGE_GT_20B"
    assert by_ticker["MRVL"]["catalyst_strength_label"] == "FUNDAMENTAL_STRONG"


def test_failure_entry_uses_d1_to_d5_and_next_open_without_future_leakage(tmp_path: Path) -> None:
    policy = mspv.load_policy(_policy(tmp_path / "policy.json"))
    candidates = mspv.build_candidate_panel(_baseline(), policy)
    entries = mspv.build_failure_entries(candidates, _prices(), policy)
    mrl_entries = [row for row in entries if row["ticker"] == "MRLN"]
    assert {row["failure_rule"][:2] for row in mrl_entries} == {"F1", "F2", "F3", "F4", "F5"}
    mrl = [row for row in mrl_entries if row["failure_rule"].startswith("F1")][0]
    assert mrl["failure_rule"] == "F1_no_close_update_D0_high_and_close_below_D0_close"
    assert mrl["failure_confirm_date"] == "2026-01-06"
    assert mrl["entry_date"] == "2026-01-07"
    assert mrl["no_live_signal"] is True
    assert all(row["ticker"] != "MRVL" for row in entries)

    missing_d1 = _prices()
    missing_d1.loc[(missing_d1["ticker"] == "MRLN") & (missing_d1["date"] == "2026-01-06"), "close"] = 15.5
    entries2 = mspv.build_failure_entries(candidates, missing_d1, policy)
    mrl2 = [row for row in entries2 if row["ticker"] == "MRLN" and row["failure_rule"].startswith("F1")][0]
    assert mrl2["failure_confirm_date"] == "2026-01-07"


def test_underlying_outcomes_and_synthetic_vertical_reference(tmp_path: Path) -> None:
    receipt = mspv.build_research(_baseline(), _prices(), tmp_path / "out", _policy(tmp_path / "policy.json"))
    assert receipt["run_status"] == "material_spike_put_vertical_research_completed"
    assert receipt["model_status"] == "synthetic_fixed_iv_not_historical_option_fill_reconstruction"
    assert mspv.verify_output_manifest(tmp_path / "out")

    underlying = pd.read_csv(tmp_path / "out" / "material_spike_underlying_outcomes.csv")
    assert (underlying["forward_5d_return"] < 0).any()
    assert set(underlying["no_broker_action"].astype(str).str.lower()) == {"true"}

    vertical = pd.read_csv(tmp_path / "out" / "material_spike_put_vertical_reference.csv")
    assert not vertical.empty
    assert set(vertical["model_status"]) == {"synthetic_fixed_iv_not_historical_option_fill_reconstruction"}
    assert set(vertical["no_auto_execution"].astype(str).str.lower()) == {"true"}


def test_policy_blocks_live_paths_and_manifest_rejects_extra_outputs(tmp_path: Path) -> None:
    for key in ["broker_execution_enabled", "auto_trade_action_enabled", "live_signal_enabled", "rank_change_allowed", "existing_morita_behavior_change_allowed", "future_leakage_allowed"]:
        with pytest.raises(SystemExit, match="material_spike_policy_safety_flag_mismatch"):
            mspv.load_policy(_policy(tmp_path / f"{key}.json", override={key: True}))

    mspv.build_research(_baseline(), _prices(), tmp_path / "out", _policy(tmp_path / "policy.json"))
    (tmp_path / "out" / "extra.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="material_spike_manifest_file_set_mismatch"):
        mspv.verify_output_manifest(tmp_path / "out")
