from __future__ import annotations

import os
from datetime import time
from typing import Any

import pandas as pd


# User-facing checkpoint labels are fixed Japan times. The values are
# (actual JST execution time, day offset from the U.S. trading date).
# The 22:30 slot executes at 22:35 so the first regular-session 5-minute bar
# is complete; this remains inside the user's accepted five-minute tolerance.
# "24:00" means midnight at the end of the U.S. trading date's JST date.
CHECKPOINT_TIMES = {
    "22:30": (time(22, 35), 0),
    "23:00": (time(23, 0), 0),
    "24:00": (time(0, 0), 1),
}
FINAL_EXECUTION_SLOT = "24:00"
PRECOMPUTE_START_JST = time(21, 0)
PRECOMPUTE_END_JST = time(22, 20)
WAKE_START = time(15, 15)
WAKE_END = time(15, 40)
CHECKPOINT_WINDOW_MINUTES = 15


def now_et() -> pd.Timestamp:
    return pd.Timestamp.now(tz="America/New_York")


def normalize_et(value: pd.Timestamp | str | None) -> pd.Timestamp:
    if value is None:
        return now_et()
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("America/New_York")
    return timestamp.tz_convert("America/New_York")


def normalize_jst(value: pd.Timestamp | str | None) -> pd.Timestamp:
    return normalize_et(value).tz_convert("Asia/Tokyo")


def trading_date_et(timestamp: pd.Timestamp) -> str:
    return normalize_et(timestamp).date().isoformat()


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def state_blob_name(date_et: str, mode: str) -> str:
    return f"state/{mode}/{date_et}.json"


def default_state(date_et: str) -> dict[str, Any]:
    return {
        "trading_date_et": date_et,
        "precompute_complete": False,
        "precompute_manifest": "",
        "slots": {},
        # These field names are retained for backward-compatible state files.
        # They now represent the final 24:00 JST execution baseline.
        "noon_snapshot_complete": False,
        "noon_execution_tickers": [],
        "late_s_emergency_sent": {},
        "last_wake_scan_at_et": None,
    }


def market_session(timestamp_et: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    import pandas_market_calendars as mcal

    timestamp = normalize_et(timestamp_et)
    calendar = mcal.get_calendar("NYSE")
    schedule = calendar.schedule(
        start_date=timestamp.date().isoformat(),
        end_date=timestamp.date().isoformat(),
    )
    if schedule.empty:
        return None
    market_open = pd.Timestamp(schedule.iloc[0]["market_open"]).tz_convert("America/New_York")
    market_close = pd.Timestamp(schedule.iloc[0]["market_close"]).tz_convert("America/New_York")
    return market_open, market_close


def checkpoint_timestamp(timestamp_et: pd.Timestamp, slot: str) -> pd.Timestamp:
    target_time, day_offset = CHECKPOINT_TIMES[slot]
    timestamp = normalize_et(timestamp_et)
    # Anchor the fixed JST wall-clock target to the U.S. trading date. This
    # automatically moves the corresponding ET time when U.S. DST changes.
    base_jst = pd.Timestamp(timestamp.date(), tz="Asia/Tokyo") + pd.Timedelta(days=day_offset)
    target_jst = base_jst + pd.Timedelta(hours=target_time.hour, minutes=target_time.minute)
    return target_jst.tz_convert("America/New_York")


def determine_action(
    timestamp_et: pd.Timestamp,
    state: dict[str, Any],
    cache_exists: bool,
    force_action: str | None = None,
) -> str | None:
    if force_action:
        normalized = force_action.strip().upper()
        aliases = {"PRECOMPUTE": "PRECOMPUTE", "WAKE": "WAKE", "15:30": "WAKE"}
        if normalized in aliases:
            return aliases[normalized]
        if force_action in CHECKPOINT_TIMES:
            return force_action
        raise ValueError(f"Unsupported force_action: {force_action}")

    timestamp = normalize_et(timestamp_et)
    current_time_et = timestamp.time().replace(tzinfo=None)
    current_time_jst = timestamp.tz_convert("Asia/Tokyo").time().replace(tzinfo=None)
    if not cache_exists and PRECOMPUTE_START_JST <= current_time_jst <= PRECOMPUTE_END_JST:
        return "PRECOMPUTE"

    for slot in CHECKPOINT_TIMES:
        target = checkpoint_timestamp(timestamp, slot)
        if target <= timestamp < target + pd.Timedelta(minutes=CHECKPOINT_WINDOW_MINUTES):
            completed = bool(state.get("slots", {}).get(slot, {}).get("completed"))
            if not completed:
                return slot

    if WAKE_START <= current_time_et <= WAKE_END:
        return "WAKE"
    return None


def eligible(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    frame = candidates.copy()
    if "exclusion_reason" in frame.columns:
        frame = frame[frame["exclusion_reason"].fillna("") == ""]
    return frame


def checkpoint_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = eligible(candidates)
    if frame.empty or "alert_rank" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame["alert_rank"].isin(["S", "A"])].copy()


def new_late_s_candidates(candidates: pd.DataFrame, state: dict[str, Any]) -> pd.DataFrame:
    frame = eligible(candidates)
    if frame.empty or "alert_rank" not in frame.columns:
        return frame.iloc[0:0].copy()
    frame = frame[frame["alert_rank"] == "S"].copy()
    if frame.empty:
        return frame

    baseline = set(map(str, state.get("noon_execution_tickers", [])))
    already_sent = set(map(str, state.get("late_s_emergency_sent", {}).keys()))
    tickers = frame["ticker"].astype(str)
    return frame[~tickers.isin(baseline | already_sent)].copy()


def ticker_lists(candidates: pd.DataFrame) -> tuple[list[str], list[str]]:
    visible = checkpoint_candidates(candidates)
    if visible.empty:
        return [], []
    s = sorted(visible.loc[visible["alert_rank"] == "S", "ticker"].astype(str).unique().tolist())
    a = sorted(visible.loc[visible["alert_rank"] == "A", "ticker"].astype(str).unique().tolist())
    return s, a
