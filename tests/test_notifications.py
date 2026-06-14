from __future__ import annotations

from pathlib import Path

import pandas as pd

from discord_alert import send_discord_alert
from scanner_notify import build_discord_message, enrich_option_liquidity, select_alert_candidates


def notify_config() -> dict:
    return {
        "notify": {
            "mode": "production_momentum",
            "production_momentum": {
                "rs_min": 98,
                "breakout_lookback_days": 20,
                "volume_multiple_min": 1.2,
                "volume_flag_high": 2.0,
                "volume_flag_extreme": 3.0,
                "min_price": 5.0,
                "min_avg_volume_50d": 500_000,
                "market_cap_warning_threshold": 2_000_000_000,
                "gap_warning_pct": 0.15,
                "iv_warning_threshold": 1.0,
                "vertical_upper_pcts": [0.15, 0.20],
                "option_liquidity": {"enabled": False},
                "exit_rules": {
                    "profit_take": 1.25,
                    "time_stop_days": 10,
                    "time_stop_underlying_gain": 0.05,
                },
            },
            "backtest_reference": {
                "test_pf": 2.39,
                "test_avg_return": 0.286,
                "test_win_rate": 0.525,
            },
        }
    }


def candidate_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "MU",
                "rank": "A",
                "trend_passed": True,
                "standard_rs_score": 99,
                "breakout_rs_score": 99,
                "breakout_today": True,
                "volume_multiple": 1.35,
                "avg_volume_50d": 8_000_000,
                "close": 150.0,
                "pivot": 147.5,
                "market_cap": 180_000_000_000,
                "total_score": 90.0,
            },
            {
                "ticker": "AMD",
                "rank": "A",
                "trend_passed": True,
                "standard_rs_score": 98.5,
                "breakout_rs_score": 98.2,
                "breakout_today": True,
                "volume_multiple": 2.2,
                "avg_volume_50d": 40_000_000,
                "close": 210.0,
                "pivot": 205.0,
                "market_cap": 300_000_000_000,
                "total_score": 88.0,
            },
            {
                "ticker": "LOWRS",
                "rank": "A",
                "trend_passed": True,
                "standard_rs_score": 97.9,
                "breakout_rs_score": 99,
                "breakout_today": True,
                "volume_multiple": 1.5,
                "avg_volume_50d": 2_000_000,
                "close": 60.0,
                "pivot": 58.0,
                "market_cap": 10_000_000_000,
                "total_score": 88.0,
            },
            {
                "ticker": "LOWVOLMULT",
                "rank": "A",
                "trend_passed": True,
                "standard_rs_score": 99,
                "breakout_rs_score": 99,
                "breakout_today": True,
                "volume_multiple": 1.1,
                "avg_volume_50d": 2_000_000,
                "close": 60.0,
                "pivot": 58.0,
                "market_cap": 10_000_000_000,
                "total_score": 88.0,
            },
        ]
    )


def test_select_alert_candidates_applies_production_momentum_filters():
    selected = select_alert_candidates(candidate_rows(), notify_config())
    assert selected["ticker"].tolist() == ["MU", "AMD"]
    assert selected["market_cap_bucket"].tolist() == ["50B-200B", "200B+"]
    assert selected.loc[selected["ticker"] == "AMD", "volume_2x_flag"].iloc[0]


def test_enrich_option_liquidity_can_be_disabled_and_promotes_s_rank():
    selected = select_alert_candidates(candidate_rows(), notify_config())
    enriched = enrich_option_liquidity(selected, notify_config())
    assert set(enriched["alert_rank"]) == {"S"}
    assert set(enriched["option_liquidity"]) == {"Skipped"}


def test_build_discord_message_production_momentum_format():
    selected = select_alert_candidates(candidate_rows(), notify_config())
    enriched = enrich_option_liquidity(selected, notify_config())
    message = build_discord_message(enriched, Path("scanner_alerts/2026-06-14/russell1000_momentum_candidates.csv"), notify_config())
    assert "Production Momentum Alert" in message
    assert "RS>=98" in message
    assert "MarketCap displayed only" in message
    assert "MU" in message
    assert "AMD" in message
    assert "60DTE ATM/+15%" in message
    assert "+125% profit take" in message


def test_build_discord_message_returns_no_signals_today_for_empty_candidates():
    empty = select_alert_candidates(candidate_rows().iloc[0:0], notify_config())
    message = build_discord_message(empty, Path("scanner_alerts/empty.csv"), notify_config())
    assert message == "No signals today"


class FakeResponse:
    status_code = 204
    text = ""


class FakeSession:
    def __init__(self) -> None:
        self.payload = None

    def post(self, url, json, timeout):
        self.payload = {"url": url, "json": json, "timeout": timeout}
        return FakeResponse()


def test_discord_notifier_posts_webhook_payload():
    session = FakeSession()
    send_discord_alert("hello", webhook_url="https://example.test/webhook", session=session)
    assert session.payload["url"] == "https://example.test/webhook"
    assert session.payload["json"]["content"] == "hello"
    assert session.payload["json"]["username"] == "Russell1000 Minervini Scanner"
