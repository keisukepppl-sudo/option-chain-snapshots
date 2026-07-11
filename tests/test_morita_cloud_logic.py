from __future__ import annotations

import pandas as pd

from morita_cloud.intraday import snapshot_from_frame
from morita_cloud.logic import (
    checkpoint_candidates,
    default_state,
    determine_action,
    new_late_s_candidates,
)


def sample_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "SNEW", "alert_rank": "S", "exclusion_reason": ""},
            {"ticker": "SNOON", "alert_rank": "S", "exclusion_reason": ""},
            {"ticker": "ANOON", "alert_rank": "A", "exclusion_reason": ""},
            {"ticker": "BNAME", "alert_rank": "B", "exclusion_reason": ""},
            {"ticker": "EXCLUDED", "alert_rank": "S", "exclusion_reason": "excluded_gap_ge_10"},
        ]
    )


def test_determine_action_uses_checkpoint_retry_window() -> None:
    state = default_state("2026-07-10")
    assert determine_action(pd.Timestamp("2026-07-10 10:00", tz="America/New_York"), state, True) == "10:00"
    assert determine_action(pd.Timestamp("2026-07-10 10:09", tz="America/New_York"), state, True) == "10:00"
    assert determine_action(pd.Timestamp("2026-07-10 10:16", tz="America/New_York"), state, True) is None


def test_completed_checkpoint_is_idempotent() -> None:
    state = default_state("2026-07-10")
    state["slots"]["12:00"] = {"completed": True}
    assert determine_action(pd.Timestamp("2026-07-10 12:05", tz="America/New_York"), state, True) is None


def test_precompute_is_due_before_open_when_cache_missing() -> None:
    state = default_state("2026-07-10")
    assert determine_action(pd.Timestamp("2026-07-10 08:15", tz="America/New_York"), state, False) == "PRECOMPUTE"


def test_checkpoint_filters_to_unexcluded_s_and_a() -> None:
    selected = checkpoint_candidates(sample_candidates())
    assert selected["ticker"].tolist() == ["SNEW", "SNOON", "ANOON"]


def test_wake_only_for_current_s_absent_from_noon_and_unsent() -> None:
    state = default_state("2026-07-10")
    state["noon_snapshot_complete"] = True
    state["noon_execution_tickers"] = ["SNOON", "ANOON"]
    selected = new_late_s_candidates(sample_candidates(), state)
    assert selected["ticker"].tolist() == ["SNEW"]


def test_missing_noon_baseline_fails_safe_for_all_current_s() -> None:
    state = default_state("2026-07-10")
    selected = new_late_s_candidates(sample_candidates(), state)
    assert selected["ticker"].tolist() == ["SNEW", "SNOON"]


def test_snapshot_excludes_bar_starting_at_decision_cutoff() -> None:
    index = pd.DatetimeIndex(
        [
            "2026-07-10 09:55:00-04:00",
            "2026-07-10 10:00:00-04:00",
        ]
    )
    frame = pd.DataFrame(
        {
            "Open": [100.0, 999.0],
            "High": [102.0, 999.0],
            "Low": [99.0, 999.0],
            "Close": [101.0, 999.0],
            "Volume": [1000, 999999],
        },
        index=index,
    )
    snapshot = snapshot_from_frame(frame, pd.Timestamp("2026-07-10 10:00", tz="America/New_York"))
    assert snapshot is not None
    assert snapshot["latest_price"] == 101.0
    assert snapshot["intraday_volume"] == 1000.0
