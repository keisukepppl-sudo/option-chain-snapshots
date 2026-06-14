from __future__ import annotations

from pathlib import Path

import pandas as pd

from discord_alert import send_discord_alert
from scanner_notify import build_discord_message, select_alert_candidates


def notify_config() -> dict:
    return {
        "notify": {
            "rule": {
                "standard_rs_min": 95,
                "breakout_rs_min": 95,
                "accumulation_min": 30,
                "vcp_min": 50,
                "distance_to_pivot_max": 0.12,
            },
            "filters": {
                "min_avg_volume_50d": 2_000_000,
                "min_price": 10.0,
                "min_market_cap_proxy": 2_000_000_000,
            },
            "alert_ranks": ["S", "A", "B"],
            "backtest_reference": {
                "signals": 159,
                "hit_rate_10pct_20d": 0.515723,
                "hit_rate_15pct_20d": 0.402516,
                "hit_rate_20pct_20d": 0.264151,
            },
        }
    }


def candidate_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "SFAST",
                "rank": "S",
                "trend_passed": True,
                "standard_rs_score": 98,
                "breakout_rs_score": 97,
                "accumulation_score": 45,
                "vcp_score": 60,
                "distance_to_pivot": 0.08,
                "avg_volume_50d": 3_000_000,
                "close": 50.0,
                "market_cap": 5_000_000_000,
                "total_score": 78.0,
                "pivot": 54.0,
            },
            {
                "ticker": "AGOOD",
                "rank": "A",
                "trend_passed": True,
                "standard_rs_score": 97,
                "breakout_rs_score": 96,
                "accumulation_score": 72,
                "vcp_score": 58,
                "distance_to_pivot": 0.041,
                "avg_volume_50d": 4_800_000,
                "close": 50.0,
                "market_cap": 5_000_000_000,
                "total_score": 91.0,
                "pivot": 52.2,
            },
            {
                "ticker": "BSETUP",
                "rank": "B",
                "trend_passed": True,
                "standard_rs_score": 96,
                "breakout_rs_score": 95,
                "accumulation_score": 55,
                "vcp_score": 60,
                "distance_to_pivot": 0.075,
                "avg_volume_50d": 2_500_000,
                "close": 30.0,
                "market_cap": 3_000_000_000,
                "total_score": 84.0,
                "pivot": 32.4,
            },
            {
                "ticker": "LOWVOL",
                "rank": "A",
                "trend_passed": True,
                "standard_rs_score": 99,
                "breakout_rs_score": 99,
                "accumulation_score": 60,
                "vcp_score": 73,
                "distance_to_pivot": 0.04,
                "avg_volume_50d": 500_000,
                "close": 80.0,
                "market_cap": 8_000_000_000,
                "total_score": 88.0,
                "pivot": 83.0,
            },
        ]
    )


def test_select_alert_candidates_applies_options_momentum_filters():
    selected = select_alert_candidates(candidate_rows(), notify_config())
    assert selected["ticker"].tolist() == ["SFAST", "AGOOD", "BSETUP"]
    assert selected["backtest_hit_rate_15pct_20d"].iloc[0] == 0.402516


def test_build_discord_message_groups_s_a_b_ranks_in_order():
    selected = select_alert_candidates(candidate_rows(), notify_config())
    message = build_discord_message(selected, Path("scanner_alerts/2026-06-14/russell1000_momentum_candidates.csv"), notify_config())
    assert "\U0001f525 S Rank" in message
    assert "\U0001f6a8 A Rank" in message
    assert "\u26a0\ufe0f B Rank" in message
    assert message.index("SFAST") < message.index("AGOOD") < message.index("BSETUP")
    assert "Rank: A" in message
    assert "Score: 91" in message
    assert "RS: 98" in message
    assert "Breakout RS: 96" in message
    assert "Accumulation: 72" in message
    assert "VCP: 60" in message
    assert "Pivot Distance: 4.1%" in message
    assert "Volume: 4.8M" in message


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
