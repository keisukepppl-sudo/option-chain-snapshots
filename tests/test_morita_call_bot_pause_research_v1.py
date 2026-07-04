from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_long_call_completion_research import engine as e


def trade_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": ["s1", "s2", "s3"],
            "ticker": ["A", "B", "C"],
            "entry_date": ["2024-01-03", "2024-01-04", "2024-01-05"],
            "signal_decision_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "TP125_return_pct": [-50.0, 125.0, -20.0],
            "signal_rank": ["S", "S", "S"],
            "reached_plus_5pct_within_10_sessions": ["false", "true", "false"],
            "breakout_day_low_breach_before_timeout": ["true", "false", "true"],
            "timeout_10_sessions_under_threshold": ["true", "false", "true"],
        }
    )


def qqq_history() -> pd.DataFrame:
    dates = pd.bdate_range("2023-10-01", periods=90)
    closes = [100.0 + i * 0.1 for i in range(60)] + [95.0 - i * 0.5 for i in range(30)]
    qqq = pd.DataFrame({"date": dates, "ticker": "QQQ", "open": closes, "high": closes, "low": closes, "close": closes})
    qqq["sma20"] = qqq["close"].rolling(20, min_periods=20).mean()
    qqq["sma50"] = qqq["close"].rolling(50, min_periods=50).mean()
    qqq["QQQ_TREND_BREAK_ON"] = (qqq["close"] < qqq["sma50"]) & (qqq["sma20"] < qqq["sma50"])
    return qqq


def test_no_network_provider_api_code_exists() -> None:
    text = "\n".join(
        [
            (REPO_ROOT / "src" / "morita_long_call_completion_research" / "engine.py").read_text(encoding="utf-8"),
            (REPO_ROOT / "scripts" / "build_morita_call_bot_pause_research_v1.py").read_text(encoding="utf-8"),
        ]
    )
    forbidden = ["requests", "urllib", "yfinance", "download(", "api_key"]
    assert not any(token in text for token in forbidden)


def test_qqq_trend_break_uses_exact_20_50_sma_formula() -> None:
    qqq = qqq_history()
    row = qqq.iloc[-1]
    assert bool(row["QQQ_TREND_BREAK_ON"]) == bool(row["close"] < row["sma50"] and row["sma20"] < row["sma50"])


def test_forward_qqq_drawdown_metrics_are_decision_day_only(monkeypatch: pytest.MonkeyPatch) -> None:
    qqq = qqq_history()
    trades = trade_panel()
    trades.loc[0, "signal_decision_date"] = qqq.iloc[50]["date"].strftime("%Y-%m-%d")
    trades.loc[1, "signal_decision_date"] = qqq.iloc[51]["date"].strftime("%Y-%m-%d")
    trades.loc[2, "signal_decision_date"] = qqq.iloc[52]["date"].strftime("%Y-%m-%d")
    narrow = pd.DataFrame({"signal_id": ["s1", "s2", "s3"], "NARROW_LEADERSHIP_ON": [False, False, False]})
    cross = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(trades["signal_decision_date"]),
            "cta_consensus_category": ["cta_all_risk_on", "cta_all_risk_on", "cta_all_risk_on"],
            "vol_change_consensus_category": ["vol_mixed_or_unchanged", "vol_mixed_or_unchanged", "vol_mixed_or_unchanged"],
        }
    )
    monkeypatch.setattr(e, "narrow_leadership_states", lambda: narrow)
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: cross)
    out = e.add_pause_states(trades, qqq)
    loc = qqq.index[qqq["date"] == pd.Timestamp(trades.loc[0, "signal_decision_date"])][0]
    base_close = qqq.loc[loc, "close"]
    expected = qqq.iloc[loc + 1 : loc + 21]["close"].min() / base_close - 1.0
    assert abs(float(out.loc[0, "forward_20_session_max_drawdown_from_decision_close"]) - float(expected)) < 1e-12


def test_pause_state_formulas_and_unavailable_components_are_not_inferred(monkeypatch: pytest.MonkeyPatch) -> None:
    trades = trade_panel()
    qqq = qqq_history()
    trades["signal_decision_date"] = [qqq.iloc[-45]["date"].strftime("%Y-%m-%d"), qqq.iloc[-44]["date"].strftime("%Y-%m-%d"), qqq.iloc[-43]["date"].strftime("%Y-%m-%d")]
    narrow = pd.DataFrame({"signal_id": ["s1", "s2", "s3"], "NARROW_LEADERSHIP_ON": [True, False, True]})
    cross = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(trades["signal_decision_date"]),
            "cta_consensus_category": ["cta_all_risk_off", "cta_incomplete", "cta_all_risk_on"],
            "vol_change_consensus_category": ["vol_incomplete", "vol_all_reduce_risk", "vol_incomplete"],
        }
    )
    monkeypatch.setattr(e, "narrow_leadership_states", lambda: narrow)
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: cross)
    out = e.add_pause_states(trades, qqq)
    assert out["CTA_AVAILABLE"].tolist() == [True, False, True]
    assert out["VOL_AVAILABLE"].tolist() == [False, True, False]
    assert (out["STATE_3_CASCADE"] == (out["QQQ_TREND_BREAK_ON"].fillna(False).astype(bool) & (out["CTA_RISK_OFF"] | out["VOL_ALL_REDUCE"]))).all()
    assert (out["STATE_4_FULL_CASCADE"] == (out["STATE_3_CASCADE"] & out["NARROW_LEADERSHIP_ON"])).all()


def test_pause_label_fixed_criteria() -> None:
    paused = {"count": 25, "profit_factor": 0.7, "breakout_day_low_breach_rate": 0.30}
    allowed = {"count": 150, "profit_factor": 1.2, "breakout_day_low_breach_rate": 0.10}
    rpaused = {"FWD20_DD10_incidence": 0.25}
    rallowed = {"FWD20_DD10_incidence": 0.05}
    assert e.label_pause_state(paused, allowed, rpaused, rallowed, False, 1.0) == "pause_candidate_supported_descriptively"
    assert e.label_pause_state({**paused, "count": 10}, allowed, rpaused, rallowed, False, 1.0) == "insufficient_sample_or_coverage"


def test_skipped_trades_are_not_reallocated_in_group_stats() -> None:
    panel = trade_panel()
    paused = panel.iloc[[0]]
    allowed = panel.iloc[[1, 2]]
    assert e.pause_group_stats(paused, "STATE_X", "PAUSED")["count"] == 1
    assert e.pause_group_stats(allowed, "STATE_X", "ALLOW")["count"] == 2


def test_s_only_denominator_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = pd.DataFrame({"signal_id": ["s1"], "terminal_net_return_pct": [1.0], "first_hit_125_date": [""]})
    s_panel = pd.DataFrame(
        {
            "signal_id": ["s1"],
            "underlying_symbol": ["A"],
            "signal_rank": ["A"],
            "reached_plus_5pct_within_10_sessions": ["true"],
            "breakout_day_low_breach_before_timeout": ["false"],
            "timeout_10_sessions_under_threshold": ["false"],
        }
    )
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: terminal)
    from src.morita_single_call_reference import s_single_call_reference_engine as ref

    monkeypatch.setattr(ref, "load_formal_s_panel", lambda _: (s_panel, {}))
    with pytest.raises(ValueError, match="pause_denominator_not_s_only"):
        e.load_pause_trade_panel()


def test_concentration_is_deterministic() -> None:
    rows = [
        {"ticker": "A", "entry_date": "2024-01-01"},
        {"ticker": "A", "entry_date": "2024-01-02"},
        {"ticker": "B", "entry_date": "2024-04-01"},
    ]
    conc = e.concentration(rows)
    assert conc["unique_ticker_count"] == 2
    assert conc["concentration_flag"] is True


def test_manifest_check_rejects_missing_changed_extra_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    for name in e.PAUSE_REQUIRED_FILES:
        if name != "call_bot_pause_content_manifest.json":
            (out / name).write_text("x\n", encoding="utf-8")
    from src.morita_single_call_reference import s_single_call_reference_engine as ref

    ref.build_manifest(out, "call_bot_pause_content_manifest.json", e.PAUSE_REQUIRED_FILES)
    assert e.verify_pause_manifest(out)["verified"] is True
    (out / "extra.csv").write_text("x\n", encoding="utf-8")
    assert e.verify_pause_manifest(out)["extra"] == ["extra.csv"]


def test_cli_rejects_parameter_overrides() -> None:
    from scripts.build_morita_call_bot_pause_research_v1 import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--run", "--state", "custom"])
