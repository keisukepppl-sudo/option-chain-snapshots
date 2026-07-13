from __future__ import annotations

import pandas as pd

from morita_cloud.intraday import snapshot_from_frame
from morita_cloud.logic import (
    checkpoint_candidates,
    checkpoint_timestamp,
    default_state,
    determine_action,
    new_late_s_candidates,
)


def sample_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "SNEW", "alert_rank": "S", "exclusion_reason": ""},
            {"ticker": "SBASE", "alert_rank": "S", "exclusion_reason": ""},
            {"ticker": "ABASE", "alert_rank": "A", "exclusion_reason": ""},
            {"ticker": "BNAME", "alert_rank": "B", "exclusion_reason": ""},
            {"ticker": "EXCLUDED", "alert_rank": "S", "exclusion_reason": "excluded_gap_ge_10"},
        ]
    )


def test_determine_action_uses_fixed_jst_checkpoint_retry_window_in_summer() -> None:
    state = default_state("2026-07-10")
    assert determine_action(pd.Timestamp("2026-07-10 09:30", tz="America/New_York"), state, True) is None
    assert determine_action(pd.Timestamp("2026-07-10 09:35", tz="America/New_York"), state, True) == "22:30"
    assert determine_action(pd.Timestamp("2026-07-10 09:44", tz="America/New_York"), state, True) == "22:30"
    assert determine_action(pd.Timestamp("2026-07-10 09:50", tz="America/New_York"), state, True) is None
    assert determine_action(pd.Timestamp("2026-07-10 10:00", tz="America/New_York"), state, True) == "23:00"
    assert determine_action(pd.Timestamp("2026-07-10 11:00", tz="America/New_York"), state, True) == "24:00"


def test_fixed_jst_checkpoints_shift_et_automatically_in_winter() -> None:
    state = default_state("2026-12-10")
    assert determine_action(pd.Timestamp("2026-12-10 08:35", tz="America/New_York"), state, True) == "22:30"
    assert determine_action(pd.Timestamp("2026-12-10 09:00", tz="America/New_York"), state, True) == "23:00"
    assert determine_action(pd.Timestamp("2026-12-10 10:00", tz="America/New_York"), state, True) == "24:00"


def test_checkpoint_timestamp_uses_fixed_jst_execution_instants() -> None:
    summer = pd.Timestamp("2026-07-10 12:00", tz="America/New_York")
    winter = pd.Timestamp("2026-12-10 12:00", tz="America/New_York")
    assert checkpoint_timestamp(summer, "22:30").tz_convert("Asia/Tokyo").strftime("%Y-%m-%d %H:%M") == "2026-07-10 22:35"
    assert checkpoint_timestamp(summer, "23:00").tz_convert("Asia/Tokyo").strftime("%Y-%m-%d %H:%M") == "2026-07-10 23:00"
    assert checkpoint_timestamp(summer, "24:00").tz_convert("Asia/Tokyo").strftime("%Y-%m-%d %H:%M") == "2026-07-11 00:00"
    assert checkpoint_timestamp(winter, "22:30").tz_convert("Asia/Tokyo").strftime("%Y-%m-%d %H:%M") == "2026-12-10 22:35"
    assert checkpoint_timestamp(winter, "24:00").tz_convert("Asia/Tokyo").strftime("%Y-%m-%d %H:%M") == "2026-12-11 00:00"


def test_completed_checkpoint_is_idempotent() -> None:
    state = default_state("2026-07-10")
    state["slots"]["24:00"] = {"completed": True}
    assert determine_action(pd.Timestamp("2026-07-10 11:05", tz="America/New_York"), state, True) is None


def test_precompute_is_due_in_fixed_jst_window_when_cache_missing() -> None:
    state = default_state("2026-07-10")
    assert determine_action(pd.Timestamp("2026-07-10 08:00", tz="America/New_York"), state, False) == "PRECOMPUTE"


def test_checkpoint_filters_to_unexcluded_s_and_a() -> None:
    selected = checkpoint_candidates(sample_candidates())
    assert selected["ticker"].tolist() == ["SNEW", "SBASE", "ABASE"]


def test_wake_only_for_current_s_absent_from_final_baseline_and_unsent() -> None:
    state = default_state("2026-07-10")
    state["noon_snapshot_complete"] = True
    state["noon_execution_tickers"] = ["SBASE", "ABASE"]
    selected = new_late_s_candidates(sample_candidates(), state)
    assert selected["ticker"].tolist() == ["SNEW"]


def test_missing_final_baseline_fails_safe_for_all_current_s() -> None:
    state = default_state("2026-07-10")
    selected = new_late_s_candidates(sample_candidates(), state)
    assert selected["ticker"].tolist() == ["SNEW", "SBASE"]


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
