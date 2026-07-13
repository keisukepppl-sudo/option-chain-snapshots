from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from morita_first_absorption_reversal_v1.engine import (
    SIGNAL_SCOPE,
    add_safety,
    build_audits,
    build_underlying_trades,
    profit_factor,
    safety_fields,
    summarize_trades,
)


def test_safety_fields_block_live_execution():
    fields = safety_fields()
    assert fields["research_only"] is True
    assert fields["live_order_allowed"] is False
    assert fields["webull_integration_allowed"] is False
    assert fields["signal_scope"] == SIGNAL_SCOPE


def test_add_safety_appends_required_flags():
    out = add_safety(pd.DataFrame([{"ticker": "AMAT"}]))
    assert out["research_only"].all()
    assert not out["execution_allowed"].any()
    assert not out["live_order_allowed"].any()


def test_missing_fundamental_source_fails_to_ambiguous():
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "AMAT_2026-01-02_2026-01-05",
                "ticker": "AMAT",
                "D0_date": "2026-01-02",
                "D1_date": "2026-01-05",
                "fundamental_filter_reason": "No sealed point-in-time news/fundamental event audit source was found",
                "regime_classification": "MIXED",
            }
        ]
    )
    _, filters, _, shocks = build_audits(candidates)
    assert filters["fundamental_filter_status"].tolist() == ["AMBIGUOUS"]
    assert not filters["included_in_primary_clean_analysis"].any()
    assert shocks.empty


def test_underlying_trade_builder_separates_baselines():
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "A",
                "ticker": "AMAT",
                "s_signal_date": "2026-01-01",
                "D0_date": "2026-01-10",
                "D1_date": "2026-01-11",
                "D2_date": "2026-01-12",
                "D3_date": "2026-01-13",
                "D0_absorption_pass": True,
                "D1_absorption_pass": True,
                "two_day_absorption_pass": True,
                "universe_weak_at_D1_pass": True,
                "sell_pressure_fading_pass": True,
                "primary_candidate_pass": True,
                "fundamental_filter_status": "AMBIGUOUS",
                "regime_classification": "DEGROSS_LIKELY",
                "D1_close": 100.0,
                "D2_open": 103.0,
                "D2_close": 104.0,
                "D2_high": 105.0,
                "D2_low": 99.0,
                "D3_open": 102.0,
                "D3_close": 101.0,
            }
        ]
    )
    trades = build_underlying_trades(candidates)
    assert "E_D_PLUS_SELL_PRESSURE_FADING" in set(trades["baseline_level"])
    assert "F_E_CLEAN_FUNDAMENTAL_FILTER" not in set(trades["baseline_level"])
    assert trades["gross_return"].notna().all()


def test_profit_factor_and_summary_are_deterministic():
    trades = pd.DataFrame(
        {
            "baseline_level": ["B", "B", "B"],
            "gross_return": [0.02, -0.01, 0.03],
        }
    )
    assert round(profit_factor(trades["gross_return"]), 4) == 5.0
    summary = summarize_trades(trades, ["baseline_level"])
    assert int(summary["trades"].iloc[0]) == 3
    assert round(float(summary["win_rate"].iloc[0]), 4) == 0.6667

