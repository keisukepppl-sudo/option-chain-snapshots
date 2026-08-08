from __future__ import annotations

import math

import pandas as pd
import pytest

import scanner_notify as sn
import scripts.production_scanner_entry as production_entry
from scripts.production_scanner_entry import _strict_notification_gate, _visible


def strict_config() -> dict:
    return {
        "notify": {
            "mode": "production_momentum",
            "production_momentum": {
                "strict_notification_gate": {
                    "enabled": True,
                    "version": "strict_v1",
                    "actionable_ranks": ["S", "A"],
                    "breakout_lookback_days": 65,
                    "min_time_adjusted_volume_multiple": 1.5,
                    "min_confirmation_bars": 2,
                    "require_above_vwap": True,
                    "require_not_fading_from_open": True,
                    "require_near_intraday_high": True,
                    "max_distance_to_intraday_high": 0.01,
                    "require_qqq_above_20ema": True,
                }
            },
        }
    }


def passing_row() -> dict:
    return {
        "ticker": "PASS",
        "alert_rank": "S",
        "breakout65": True,
        "prior_65d_high": 100.0,
        "time_adjusted_volume_multiple": 1.5,
        "confirmation_bar_count": 2,
        "recent_close_min": 101.0,
        "latest_price": 102.0,
        "intraday_vwap": 101.5,
        "intraday_open": 100.5,
        "intraday_high": 102.5,
        "qqq_above_20ema": True,
        "exclusion_reason": "",
    }


def test_strict_notification_gate_accepts_only_fully_confirmed_breakout() -> None:
    eligible, reasons = _strict_notification_gate(passing_row(), strict_config())
    assert eligible is True
    assert reasons == []


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"alert_rank": "B"}, "rank_below_actionable"),
        ({"breakout65": False}, "not_above_prior_65d_high"),
        ({"time_adjusted_volume_multiple": 1.49}, "time_adjusted_volume_below_min"),
        ({"confirmation_bar_count": 1}, "insufficient_completed_bar_confirmation"),
        ({"recent_close_min": 100.0}, "insufficient_completed_bar_confirmation"),
        ({"intraday_vwap": 102.0}, "below_or_missing_vwap"),
        ({"intraday_open": 103.0}, "below_or_missing_open"),
        ({"intraday_high": 104.0}, "too_far_below_intraday_high"),
        ({"intraday_high": math.nan}, "too_far_below_intraday_high"),
        ({"qqq_above_20ema": False}, "qqq_not_above_20ema"),
        ({"qqq_above_20ema": math.nan}, "qqq_not_above_20ema"),
        ({"breakout65": math.nan}, "not_above_prior_65d_high"),
    ],
)
def test_strict_notification_gate_rejects_each_missing_confirmation(
    updates: dict, reason: str
) -> None:
    row = passing_row()
    row.update(updates)
    eligible, reasons = _strict_notification_gate(row, strict_config())
    assert eligible is False
    assert reason in reasons


def test_nan_confirmation_count_fails_closed_without_crashing() -> None:
    row = passing_row()
    row["confirmation_bar_count"] = math.nan
    eligible, reasons = _strict_notification_gate(row, strict_config())
    assert eligible is False
    assert "insufficient_completed_bar_confirmation" in reasons


def test_time_adjusted_volume_curve_reduces_opening_clock_time_inflation() -> None:
    at_1000 = pd.Timestamp("2026-07-10 10:00", tz="America/New_York")
    at_close = pd.Timestamp("2026-07-10 16:00", tz="America/New_York")
    assert sn.expected_cumulative_volume_fraction(at_1000) == pytest.approx(0.17)
    assert sn.session_fraction_from_timestamp(at_1000) == pytest.approx(30 / 390)
    assert sn.expected_cumulative_volume_fraction(at_close) == pytest.approx(1.0)


def test_qqq_regime_fails_closed_without_enough_history() -> None:
    short = pd.DataFrame({"Close": list(range(19))})
    assert sn.benchmark_regime_fields(short)["qqq_above_20ema"] is False
    assert sn.benchmark_regime_fields(pd.DataFrame())["qqq_above_20ema"] is False


def test_production_score_uses_time_adjusted_not_inflated_legacy_volume() -> None:
    from scripts.production_scanner_entry import _production_live_score

    row = passing_row() | {
        "standard_rs_score": 98.0,
        "volume_multiple": 4.0,
        "time_adjusted_volume_multiple": 1.5,
        "prior_20d_high": 100.0,
        "accumulation_score": 50.0,
        "theme": "Other",
        "market_cap_bucket": "2B-20B",
    }
    corrected = _production_live_score(row)
    legacy = _production_live_score(row | {"time_adjusted_volume_multiple": math.nan})
    assert corrected == 49.0
    assert legacy == 54.0


def test_20_day_breakout_alone_does_not_meet_65_day_gate() -> None:
    dates = pd.bdate_range("2026-03-30", periods=70)
    history = pd.DataFrame(
        {
            "Open": [90.0] * 70,
            "High": [110.0] * 50 + [100.0] * 20,
            "Low": [89.0] * 70,
            "Close": [90.0] * 70,
            "Volume": [1_000_000.0] * 70,
        },
        index=dates,
    )
    intraday = {
        "latest_price": 105.0,
        "intraday_open": 101.0,
        "intraday_high": 105.5,
        "intraday_volume": 300_000.0,
        "intraday_vwap": 103.0,
        "latest_price_date": "2026-07-10",
        "latest_price_time": "2026-07-10T10:00:00-04:00",
        "session_fraction": 30 / 390,
        "expected_volume_fraction": 0.17,
        "confirmation_bar_count": 2,
        "recent_close_min": 104.0,
    }
    metrics = sn.breakout_metrics(history, intraday, strict_lookback_days=65)
    assert metrics["breakout20"] is True
    assert metrics["breakout65"] is False
    assert metrics["confirmed_breakout65"] is False


def test_visible_notifications_exclude_shadow_candidates() -> None:
    passing = passing_row() | {"notification_eligible": True}
    shadow = passing_row() | {"ticker": "SHADOW", "notification_eligible": False}
    selected = _visible(pd.DataFrame([passing, shadow]))
    assert selected["ticker"].tolist() == ["PASS"]


def test_candidate_wrapper_keeps_failed_gate_as_shadow_row(monkeypatch: pytest.MonkeyPatch) -> None:
    base_fields = {
        "standard_rs_score": 99.0,
        "volume_multiple": 4.0,
        "prior_20d_high": 100.0,
        "accumulation_score": 50.0,
        "theme": "Other",
        "sector_proxy": "Industrials",
        "market_cap_bucket": "2B-20B",
        "gap_pct": 0.02,
        "option_liquidity_ok": True,
    }
    accepted = passing_row() | base_fields
    shadow = passing_row() | base_fields | {
        "ticker": "SHADOW",
        "confirmation_bar_count": 1,
    }
    monkeypatch.setattr(
        production_entry,
        "ORIGINAL_SELECT_CANDIDATES",
        lambda *args, **kwargs: pd.DataFrame([accepted, shadow]),
    )
    monkeypatch.setattr(production_entry, "_catalyst_routing_config", lambda: {})
    monkeypatch.setattr(
        production_entry,
        "catalyst_route_for",
        lambda ticker, config: {
            "action_route": "STANDARD_BREAKOUT_REVIEW",
            "action_reason": "strict_gate_passed",
        },
    )

    selected = production_entry._patched_select_candidates(
        pd.DataFrame(), {}, strict_config(), {}, {}
    ).set_index("ticker")

    assert bool(selected.loc["PASS", "notification_eligible"]) is True
    assert bool(selected.loc["SHADOW", "notification_eligible"]) is False
    assert selected.loc["SHADOW", "suggested_size"] == "WATCH_ONLY"
    assert "insufficient_completed_bar_confirmation" in selected.loc[
        "SHADOW", "notification_gate_reasons"
    ]
