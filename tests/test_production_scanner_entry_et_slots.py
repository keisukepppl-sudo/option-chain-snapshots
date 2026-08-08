from __future__ import annotations

import pandas as pd

from scripts.production_scanner_entry_et_slots import (
    WAKE_SLOT,
    checkpoint_candidates,
    resolve_run,
    wake_candidates,
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


def test_resolve_run_uses_active_edt_variant_only() -> None:
    now = pd.Timestamp("2026-07-10 10:00", tz="America/New_York")
    assert resolve_run("0 14 * * 1-5", timestamp_et=now) == ("10:00", False)
    assert resolve_run("0 15 * * 1-5", timestamp_et=now) == (None, False)


def test_resolve_run_maps_winter_variant_and_manual_wake() -> None:
    now = pd.Timestamp("2026-12-10 10:00", tz="America/New_York")
    assert resolve_run("0 15 * * 1-5", timestamp_et=now) == ("10:00", False)
    assert resolve_run("", manual_slot="wake", timestamp_et=now) == (WAKE_SLOT, False)


def test_checkpoint_notifications_include_only_unexcluded_s_and_a() -> None:
    selected = checkpoint_candidates(sample_candidates())
    assert selected["ticker"].tolist() == ["SNEW", "SNOON", "ANOON"]


def test_checkpoint_notifications_exclude_noneligible_shadow_candidate() -> None:
    candidates = sample_candidates()
    candidates["notification_eligible"] = True
    candidates.loc[candidates["ticker"] == "SNEW", "notification_eligible"] = False
    selected = checkpoint_candidates(candidates)
    assert selected["ticker"].tolist() == ["SNOON", "ANOON"]


def test_wake_only_for_current_s_absent_from_noon_execution_and_not_sent() -> None:
    state = {
        "noon_snapshot_complete": True,
        "noon_execution_tickers": ["SNOON", "ANOON"],
        "late_emergency_sent": {"SALREADY": {}},
    }
    selected = wake_candidates(sample_candidates(), state)
    assert selected["ticker"].tolist() == ["SNEW"]


def test_missing_noon_state_fails_safe_by_waking_for_all_current_s() -> None:
    state = {"noon_snapshot_complete": False, "noon_execution_tickers": [], "late_emergency_sent": {}}
    selected = wake_candidates(sample_candidates(), state)
    assert selected["ticker"].tolist() == ["SNEW", "SNOON"]
