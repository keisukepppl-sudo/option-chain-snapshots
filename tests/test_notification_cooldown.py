from __future__ import annotations

import pandas as pd

from morita_cloud.notification_cooldown import (
    filter_recently_notified,
    prior_trading_session_dates,
    recently_notified_tickers_gcs,
    successful_notified_tickers,
)


class FakeStore:
    def __init__(self, states: dict[str, dict]) -> None:
        self.states = states
        self.read_names: list[str] = []

    def read_json(self, name: str, default: dict | None = None):
        self.read_names.append(name)
        return self.states.get(name, dict(default or {})), None


def sent_slot(s: list[str] | None = None, a: list[str] | None = None) -> dict:
    return {
        "s_tickers": list(s or []),
        "a_tickers": list(a or []),
        "notification": {"status": "SENT"},
    }


def test_prior_trading_sessions_uses_nyse_calendar_and_returns_d1_through_d19() -> None:
    dates = prior_trading_session_dates("2026-07-31", 20)
    assert len(dates) == 19
    assert dates[-1] == "2026-07-30"
    assert "2026-07-03" not in dates  # Independence Day observed holiday.


def test_successful_notification_state_excludes_dry_run_and_prefers_notified_lists() -> None:
    state = {
        "slots": {
            "22:30": sent_slot(["OLD_S"], ["OLD_A"]),
            "23:00": {
                "s_tickers": ["DRY"],
                "a_tickers": [],
                "notification": {"status": "DRY_RUN"},
            },
            "24:00": {
                "s_tickers": ["RAW_S", "SENT_S"],
                "a_tickers": ["RAW_A"],
                "notified_s_tickers": ["SENT_S"],
                "notified_a_tickers": [],
                "notification": {"status": "SENT"},
            },
        },
        "late_s_emergency_sent": {
            "WAKE_S": {"notification": {"status": "SENT"}},
            "WAKE_DRY": {"notification": {"status": "DRY_RUN"}},
        },
    }
    assert successful_notified_tickers(state) == {"OLD_S", "OLD_A", "SENT_S", "WAKE_S"}


def test_filter_recently_notified_changes_notification_population_only() -> None:
    raw = pd.DataFrame(
        [
            {"ticker": "AMAT", "alert_rank": "A"},
            {"ticker": "WDC", "alert_rank": "S"},
        ]
    )
    filtered = filter_recently_notified(raw, {"AMAT"})
    assert filtered["ticker"].tolist() == ["WDC"]
    assert raw["ticker"].tolist() == ["AMAT", "WDC"]


def test_gcs_cooldown_blocks_same_day_and_previous_19_sessions_but_not_d20() -> None:
    current = "2026-07-31"
    d1_to_d19 = prior_trading_session_dates(current, 20)
    d1_to_d20 = prior_trading_session_dates(current, 21)
    d20 = d1_to_d20[0]

    states = {
        f"state/live/{d1_to_d19[-1]}.json": {"slots": {"22:30": sent_slot(["AMAT"], [])}},
        f"state/live/{d20}.json": {"slots": {"22:30": sent_slot(["WDC"], [])}},
    }
    current_state = {"slots": {"22:30": sent_slot([], ["MKSI"])}}
    store = FakeStore(states)

    blocked = recently_notified_tickers_gcs(store, current, "live", current_state, 20)

    assert "AMAT" in blocked
    assert "MKSI" in blocked
    assert "WDC" not in blocked
    assert f"state/live/{d20}.json" not in store.read_names
