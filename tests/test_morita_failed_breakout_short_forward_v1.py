from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_failed_breakout_short_forward_v1 as fb
from scripts import build_morita_failed_breakout_short_forward_review_v1 as review


def _policy(path: Path, d: float = fb.EXPECTED_D_HIGH, l: float = fb.EXPECTED_L_HIGH, override: dict | None = None) -> Path:
    payload = {
        "policy_version": "morita_failed_breakout_short_forward_v1",
        "mode": "research_logging_only",
        "daily_research_summary_enabled": False,
        "pushover_emergency_enabled": False,
        "broker_execution_enabled": False,
        "auto_trade_action_enabled": False,
        "live_short_signal_enabled": False,
        "put_alert_enabled": False,
        "long_s_logic_change_allowed": False,
        "rank_universe_rule_change_allowed": False,
        "regime_sizing_policy_change_allowed": False,
        "regime_thresholds": {
            "D_high_cutoff": d,
            "L_high_cutoff": l,
            "D_metric_name": "broad_russell1000_cross_sectional_dispersion_20d",
            "L_metric_name": "broad_russell1000_qqq_minus_eqw_return_20d",
            "threshold_source_lineage": {
                "source": "inherited_morita_regime_sizing_overlay",
                "verification_status": "fixture",
                "expected_D_high_cutoff": fb.EXPECTED_D_HIGH,
                "expected_L_high_cutoff": fb.EXPECTED_L_HIGH,
            },
        },
        "breakout_rule": {
            "prior_high_lookback_sessions": 65,
            "volume_lookback_sessions": 50,
            "volume_multiple_min": 1.2,
            "source_scanner_rule": "scanner.breakout.detect_breakout close_above_prior_65d_high_with_volume",
        },
        "failure_rule": {
            "tracking_sessions_after_breakout": 10,
            "primary_trigger": "close_below_breakout_day_low",
            "diagnostic_only_trigger": "intraday_low_below_breakout_day_low",
            "hypothetical_entry": "next_regular_session_open_after_failure_close",
        },
        "option_model_status": "not_implemented_in_forward_logger_v1",
    }
    if override:
        payload.update(override)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _panels() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2026-01-02", periods=95)
    rows = []
    for i, date in enumerate(dates):
        close = 100.0 + i * 0.05
        high = close + 1.0
        low = close - 1.0
        volume = 1000.0
        if i == 65:
            close = 112.0
            high = 113.0
            low = 110.0
            volume = 2500.0
        if i == 66:
            close = 110.5
            high = 111.0
            low = 109.5
        if i == 67:
            close = 109.0
            high = 110.0
            low = 108.5
        if i == 68:
            close = 108.0
            high = 109.0
            low = 107.0
        if i == 69:
            close = 101.0
            high = 104.0
            low = 98.0
        if i == 70:
            close = 97.0
            high = 100.0
            low = 95.0
        if i == 77:
            close = 96.0
            high = 99.0
            low = 94.0
        if i == 88:
            close = 94.0
            high = 98.0
            low = 92.0
        rows.append(
            {
                "ticker": "AAA",
                "date": date.strftime("%Y-%m-%d"),
                "open": close + 0.5,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    prices = pd.DataFrame(rows)
    breakout_date = dates[65].strftime("%Y-%m-%d")
    rs = pd.DataFrame(
        [
            {"ticker": "AAA", "date": breakout_date, "RS_value": 94.5},
            {"ticker": "AAA", "date": dates[64].strftime("%Y-%m-%d"), "RS_value": 99.0},
        ]
    )
    regimes = pd.DataFrame(
        [
            {"date": dates[64].strftime("%Y-%m-%d"), "D_value": fb.EXPECTED_D_HIGH + 0.01, "L_value": fb.EXPECTED_L_HIGH + 0.01},
            {"date": breakout_date, "D_value": fb.EXPECTED_D_HIGH + 0.01, "L_value": fb.EXPECTED_L_HIGH - 0.01},
        ]
    )
    return prices, rs, regimes


def test_rs_buckets_and_regime_thresholds_are_loaded_with_lineage(tmp_path: Path) -> None:
    assert fb.classify_rs_bucket(89.9) == "RS_BELOW_90"
    assert fb.classify_rs_bucket(90.0) == "RS90_95"
    assert fb.classify_rs_bucket(95.999) == "RS90_95"
    assert fb.classify_rs_bucket(96.0) == "RS96_97"
    assert fb.classify_rs_bucket(98.0) == "RS98_PLUS"

    policy = fb.load_policy(_policy(tmp_path / "policy.json"))
    assert fb.verify_threshold_lineage(policy) == {"D_high_cutoff": fb.EXPECTED_D_HIGH, "L_high_cutoff": fb.EXPECTED_L_HIGH}
    with pytest.raises(SystemExit, match="failed_breakout_D_threshold_lineage_mismatch"):
        fb.load_policy(_policy(tmp_path / "bad.json", d=0.2))


def test_regime_join_requires_exact_decision_date_and_future_value_cannot_leak(tmp_path: Path) -> None:
    prices, rs, regimes = _panels()
    policy = fb.load_policy(_policy(tmp_path / "policy.json"))
    only_future_regime = regimes[regimes["date"] != prices.iloc[65]["date"]]
    assert fb.build_breakout_candidates(prices, rs, only_future_regime, policy) == []

    candidates = fb.build_breakout_candidates(prices, rs, regimes, policy)
    assert len(candidates) == 1
    assert candidates[0]["regime_state"] == "HIGH_DISPERSION"
    assert candidates[0]["RS_bucket"] == "RS90_95"


def test_breakout_primary_failure_entry_and_intraday_diagnostic_only(tmp_path: Path) -> None:
    prices, rs, regimes = _panels()
    policy = fb.load_policy(_policy(tmp_path / "policy.json"))
    candidates = fb.build_breakout_candidates(prices, rs, regimes, policy)
    entries = fb.build_failed_breakout_entries(candidates, prices, policy)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["failure_trigger"] == "close_below_breakout_day_low"
    assert entry["failure_confirm_date"] == prices.iloc[67]["date"]
    assert entry["hypothetical_entry_date"] == prices.iloc[68]["date"]
    assert entry["diagnostic_intraday_low_breach_before_primary"] is True
    assert entry["no_live_signal"] is True
    assert entry["no_broker_action"] is True
    assert entry["no_auto_execution"] is True


def test_forward_outcomes_short_mfe_mae_recovery_and_stop_are_calculated(tmp_path: Path) -> None:
    prices, rs, regimes = _panels()
    policy = fb.load_policy(_policy(tmp_path / "policy.json"))
    candidates = fb.build_breakout_candidates(prices, rs, regimes, policy)
    entries = fb.build_failed_breakout_entries(candidates, prices, policy)
    outcomes = fb.build_forward_outcomes(entries, prices)
    row = outcomes[0]
    assert row["outcome_status"] == "complete"
    assert row["underlying_return_5d"] < 0
    assert row["reached_minus_8pct_within_10d"] is True
    assert row["max_favorable_excursion_10d"] > 0
    assert row["max_adverse_excursion_10d"] >= 0
    assert row["recovered_breakout_high_within_10d"] is False
    assert row["close_above_breakout_high_stop_triggered"] is False


def test_build_logger_outputs_manifest_summaries_no_execution_and_review(tmp_path: Path) -> None:
    prices, rs, regimes = _panels()
    receipt = fb.build_forward_logger(prices, rs, regimes, tmp_path / "out", _policy(tmp_path / "policy.json"))
    assert receipt["run_status"] == "failed_breakout_forward_logger_completed"
    assert receipt["D_high_cutoff"] == fb.EXPECTED_D_HIGH
    assert receipt["L_high_cutoff"] == fb.EXPECTED_L_HIGH
    assert fb.verify_output_manifest(tmp_path / "out")
    entries = pd.read_csv(tmp_path / "out" / "failed_breakout_entry_log.csv")
    assert set(entries["no_live_signal"].astype(str).str.lower()) == {"true"}
    assert set(entries["no_broker_action"].astype(str).str.lower()) == {"true"}
    assert "not_implemented_in_forward_logger_v1" in set(entries["option_model_status"])

    rows = review.build_review(tmp_path / "out", tmp_path / "out" / "review.csv")
    assert rows
    assert (tmp_path / "out" / "review.csv").exists()


def test_summary_disabled_by_default_and_policy_blocks_live_paths(tmp_path: Path) -> None:
    policy = fb.load_policy(_policy(tmp_path / "policy.json"))
    assert policy["daily_research_summary_enabled"] is False
    for key in ["broker_execution_enabled", "auto_trade_action_enabled", "live_short_signal_enabled", "put_alert_enabled"]:
        with pytest.raises(SystemExit, match="failed_breakout_policy_safety_flag_mismatch"):
            fb.load_policy(_policy(tmp_path / f"{key}.json", override={key: True}))


def test_manifest_rejects_missing_or_unexpected_outputs(tmp_path: Path) -> None:
    prices, rs, regimes = _panels()
    fb.build_forward_logger(prices, rs, regimes, tmp_path / "out", _policy(tmp_path / "policy.json"))
    (tmp_path / "out" / "extra.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="failed_breakout_manifest_file_set_mismatch"):
        fb.verify_output_manifest(tmp_path / "out")
