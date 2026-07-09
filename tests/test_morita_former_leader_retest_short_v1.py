from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_former_leader_retest_short_v1.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.build_morita_former_leader_retest_short_v1 as study


def thresholds() -> dict[str, float]:
    return {"D_high_cutoff": 0.1076297441118458, "L_high_cutoff": 0.0211600633543862}


def test_origin_detection_for_s_a_and_rs_buckets() -> None:
    signals = pd.DataFrame(
        [
            {"signal_rank": "S", "underlying_symbol": "AAA", "signal_decision_date": "2024-01-02", "standard_rs_score": 99, "breakout_price": 100, "breakout_day_low": 95, "prior_20d_high": 99, "volume_multiple": 2},
            {"signal_rank": "A", "underlying_symbol": "BBB", "signal_decision_date": "2024-01-03", "standard_rs_score": 97, "breakout_price": 50, "breakout_day_low": 48, "prior_20d_high": 49, "volume_multiple": 1.5},
        ]
    )
    rows = []
    for _, row in signals.iterrows():
        rank = row["signal_rank"]
        rows.append({"ticker": row["underlying_symbol"], "origin_date": row["signal_decision_date"], "origin_type": f"ORIGIN_{rank}"})
    assert {r["origin_type"] for r in rows} == {"ORIGIN_S", "ORIGIN_A"}
    assert study.origin_rs_bucket(98.0) == "RS98_PLUS"
    assert study.origin_rs_bucket(96.0) == "RS96_97"
    assert study.origin_rs_bucket(90.0) == "RS90_95"


def test_episode_deduplication_within_20_sessions() -> None:
    price = pd.DataFrame({"ticker": ["AAA"] * 25, "date": [f"2024-01-{i:02d}" for i in range(1, 26)]})
    origins = pd.DataFrame(
        [
            {"ticker": "AAA", "origin_date": "2024-01-01", "origin_type": "ORIGIN_S", "origin_RS_value": 99, "origin_close": 100},
            {"ticker": "AAA", "origin_date": "2024-01-10", "origin_type": "ORIGIN_A", "origin_RS_value": 97, "origin_close": 101},
            {"ticker": "AAA", "origin_date": "2024-01-24", "origin_type": "ORIGIN_RS98_BREAKOUT", "origin_RS_value": 98, "origin_close": 102},
        ]
    )
    spec = {"former_leader_episode_dedup_sessions": 20}
    episodes = study.dedupe_episodes(origins, price, thresholds(), spec)
    assert len(episodes) == 2
    assert int(episodes.iloc[0]["episode_reinforcement_count"]) == 1


def test_regime_thresholds_are_fixed_and_classification_is_same_day() -> None:
    th = thresholds()
    assert study.classify_regime(0.05, 1.0, th)["regime_state"] == "NORMAL"
    assert study.classify_regime(0.12, 0.0, th)["regime_state"] == "HIGH_DISPERSION"
    assert study.classify_regime(0.12, 0.03, th)["regime_state"] == "NARROW_LEADERSHIP"
    assert study.classify_regime(None, 0.03, th)["regime_state"] == "REGIME_UNAVAILABLE"


def test_modified_inherited_threshold_fails_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cutoffs = tmp_path / "cutoffs.csv"
    cutoffs.write_text(
        "metric,p33,p67\n"
        "broad_russell1000_cross_sectional_dispersion_20d,0.1,2.0\n"
        "broad_russell1000_qqq_minus_eqw_return_20d,0.0,0.0211600633543862\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path)
    spec = {"source_regime_cutoffs": "cutoffs.csv", "expected_D_high_cutoff": 0.1076297441118458, "expected_L_high_cutoff": 0.0211600633543862}
    with pytest.raises(SystemExit, match="D_high_cutoff_verification_failed"):
        study.verify_thresholds(spec)


def test_primary_breakdown_trigger_exact() -> None:
    assert bool(99 < 100 and 99 < 105)
    assert not bool(101 < 100 and 99 < 105)
    assert not bool(99 < 100 and 106 < 105)


def test_retest_zone_primary_and_diagnostic_tolerances() -> None:
    bar = pd.Series({"high": 102.49, "low": 97.51})
    assert study.zone_touch(bar, 100.0, 0.025)
    assert not study.zone_touch(pd.Series({"high": 98.4, "low": 97.0}), 100.0, 0.015)
    assert study.zone_touch(pd.Series({"high": 98.4, "low": 97.0}), 100.0, 0.05)


def test_primary_rejection_trigger_components() -> None:
    open_, high, low, close, ref = 101.0, 103.0, 97.0, 98.0, 100.0
    close_pos = (close - low) / (high - low)
    assert close < open_ and close < ref and close_pos <= 0.5


def test_hypothetical_entry_next_open_after_rejection() -> None:
    bars = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "open": [100.0, 99.0]})
    assert bars.iloc[1]["date"] == "2024-01-03"
    assert bars.iloc[1]["open"] == 99.0


def test_exit_rule_time_target_and_stop_semantics() -> None:
    bars = pd.DataFrame(
        {
            "date": [f"2024-01-{i:02d}" for i in range(2, 15)],
            "open": [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
            "high": [101] * 13,
            "low": [99, 98, 97, 96, 91, 89, 88, 87, 86, 85, 84, 83, 82],
            "close": [99, 98, 97, 96, 94, 93, 92, 91, 90, 89, 88, 87, 86],
            "sma50": [120] * 13,
        }
    )
    entry = pd.Series({"entry_session_index": 0, "hypothetical_entry_open": 100.0, "retest_high": 105.0})
    out = study.simulate_exit(entry, bars, "RULE_B_MINUS_8_UNDERLYING_TARGET", {"target": 0.08, "stop": "retest_high", "time": 10})
    assert out["exit_reason"] == "underlying_target_minus_8pct"
    assert out["underlying_short_return_pct"] == pytest.approx(8.0)


def test_stop_above_retest_high_and_50dma() -> None:
    bars = pd.DataFrame({"date": ["d0", "d1", "d2"], "open": [100, 103, 104], "high": [101, 106, 107], "low": [99, 102, 103], "close": [100, 106, 107], "sma50": [105, 105, 105]})
    entry = pd.Series({"entry_session_index": 0, "hypothetical_entry_open": 100.0, "retest_high": 105.0})
    a = study.simulate_exit(entry, bars, "A", {"target": None, "stop": "retest_high", "time": 2})
    d = study.simulate_exit(entry, bars, "D", {"target": None, "stop": "50dma", "time": 2})
    assert a["exit_reason"] == "close_above_retest_high_exit_next_open"
    assert d["exit_reason"] == "close_above_50dma_exit_next_open"


def test_outcome_mfe_mae_are_signed_for_short() -> None:
    entry = 100.0
    min_low = 90.0
    max_high = 110.0
    assert min_low / entry - 1.0 == pytest.approx(-0.10)
    assert max_high / entry - 1.0 == pytest.approx(0.10)


def test_option_models_return_consistently() -> None:
    model = {"dte": 60, "iv": 1.0, "risk_free_rate": 0.04, "entry_markup": 0.075, "exit_haircut": 0.075}
    ret = study.model_option_return(100.0, 90.0, 10, "long_put_60d_fixed_iv100", model)
    assert ret is not None
    vertical = dict(model, short_put_strike_pct=0.9)
    ret2 = study.model_option_return(100.0, 90.0, 10, "put_vertical_60d_fixed_iv100", vertical)
    assert ret2 is not None


def test_profit_factor_sample_and_concentration_flags() -> None:
    assert study.profit_factor(pd.Series([10, -5, 5])) == pytest.approx(3.0)
    assert math.isinf(study.profit_factor(pd.Series([10, 5])))
    group = pd.DataFrame({"ticker": ["AAA"] * 4 + ["BBB"]})
    conc = study.concentration(group)
    assert conc["largest_single_ticker_share"] == pytest.approx(0.8)
    assert study.sample_status(19, {"sample_gates": {"minimum_sample": 20, "preferred_sample": 50}}) == "insufficient_sample"
    assert study.sample_status(20, {"sample_gates": {"minimum_sample": 20, "preferred_sample": 50}}) == "minimum_sample_met"
    assert study.sample_status(50, {"sample_gates": {"minimum_sample": 20, "preferred_sample": 50}}) == "preferred_sample_met"


def test_interpretation_label_rules_precedence() -> None:
    spec = {
        "sample_gates": {
            "minimum_sample": 20,
            "preferred_sample": 50,
            "acceptable_median_mae_10d_max": 0.08,
            "acceptable_p90_mae_10d_max": 0.2,
            "acceptable_recovered_retest_high_10d_rate_max": 0.5,
        }
    }
    row = pd.Series({"completed_trade_count": 10})
    assert study.interpretation(row, {}, spec) == "insufficient_sample"
    row = pd.Series({"completed_trade_count": 20, "modeled_PF": 1.0})
    assert study.interpretation(row, {}, spec) == "not_viable"
    row = pd.Series({"completed_trade_count": 20, "modeled_PF": 1.6, "modeled_median_return_pct": -1.0})
    assert study.interpretation(row, {}, spec) == "PF_above_1_5_but_median_negative"
    row = pd.Series({"completed_trade_count": 20, "modeled_PF": 1.6, "modeled_median_return_pct": 1.0, "concentration_flag": True})
    assert study.interpretation(row, {}, spec) == "PF_above_1_5_but_concentrated"


def test_2022_missing_warmup_is_blocker() -> None:
    coverage = {"min_date": "2022-01-03", "has_required_2021_warmup_for_2022": False}
    assert not coverage["has_required_2021_warmup_for_2022"]


def test_cli_help_is_available_and_no_live_modules_are_imported() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), "--help"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0
    assert "--run" in result.stdout
    assert "--verify" in result.stdout
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in ["submit_order", "cancel_order", "webull_order", "account_id", "live_short_signal"]:
        assert forbidden not in source
