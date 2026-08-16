from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

import scripts.production_scanner_entry_0430 as legacy
from morita_cloud.notification_cooldown import (
    filter_recently_notified,
    recently_notified_tickers_files,
)

entry = legacy.entry

STATE_DIR = Path(os.environ.get("SCANNER_STATE_DIR", ".scanner_state"))
CHECKPOINT_SLOTS = {"10:00", "11:30", "12:00"}
WAKE_SLOT = "WAKE"
ACTIONABLE_CHECKPOINT_RANKS = {"S", "A"}

# GitHub Actions cron is UTC. Schedule both EDT and EST variants and activate
# only the variant matching America/New_York's current UTC offset. The +10-minute
# checkpoint entries are fallbacks and are suppressed after a successful primary.
CRON_RUNS: dict[str, tuple[str, str, bool]] = {
    # 10:00 ET primary/fallback
    "0 14 * * 1-5": ("10:00", "-0400", False),
    "10 14 * * 1-5": ("10:00", "-0400", True),
    "0 15 * * 1-5": ("10:00", "-0500", False),
    "10 15 * * 1-5": ("10:00", "-0500", True),
    # 11:30 ET primary/fallback
    "30 15 * * 1-5": ("11:30", "-0400", False),
    "40 15 * * 1-5": ("11:30", "-0400", True),
    "30 16 * * 1-5": ("11:30", "-0500", False),
    "40 16 * * 1-5": ("11:30", "-0500", True),
    # 12:00 ET primary/fallback
    "0 16 * * 1-5": ("12:00", "-0400", False),
    "10 16 * * 1-5": ("12:00", "-0400", True),
    "0 17 * * 1-5": ("12:00", "-0500", False),
    "10 17 * * 1-5": ("12:00", "-0500", True),
    # Post-noon wake checks: 15:15 / 15:25 / 15:30 / 15:35 ET.
    "15 19 * * 1-5": (WAKE_SLOT, "-0400", False),
    "25 19 * * 1-5": (WAKE_SLOT, "-0400", False),
    "30 19 * * 1-5": (WAKE_SLOT, "-0400", False),
    "35 19 * * 1-5": (WAKE_SLOT, "-0400", False),
    "15 20 * * 1-5": (WAKE_SLOT, "-0500", False),
    "25 20 * * 1-5": (WAKE_SLOT, "-0500", False),
    "30 20 * * 1-5": (WAKE_SLOT, "-0500", False),
    "35 20 * * 1-5": (WAKE_SLOT, "-0500", False),
}

CAPTURE: dict[str, Any] = {"candidates": pd.DataFrame(), "csv_path": None}
RUN_CONTEXT: dict[str, Any] = {"slot": None, "state": {}, "fallback": False, "cooldown_blocked": set()}


def now_et() -> pd.Timestamp:
    return pd.Timestamp.now(tz="America/New_York")


def trading_date_et(timestamp: pd.Timestamp | None = None) -> str:
    current = timestamp if timestamp is not None else now_et()
    current = current.tz_localize("America/New_York") if current.tzinfo is None else current.tz_convert("America/New_York")
    return current.strftime("%Y-%m-%d")


def state_path(timestamp: pd.Timestamp | None = None) -> Path:
    return STATE_DIR / f"morita_notification_state_{trading_date_et(timestamp)}.json"


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "trading_date_et": trading_date_et(),
            "slots": {},
            "noon_snapshot_complete": False,
            "noon_execution_tickers": [],
            "late_emergency_sent": {},
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    raw.setdefault("trading_date_et", trading_date_et())
    raw.setdefault("slots", {})
    raw.setdefault("noon_snapshot_complete", False)
    raw.setdefault("noon_execution_tickers", [])
    raw.setdefault("late_emergency_sent", {})
    return raw


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def resolve_run(
    schedule_utc: str,
    manual_slot: str = "auto",
    timestamp_et: pd.Timestamp | None = None,
) -> tuple[str | None, bool]:
    manual = str(manual_slot or "auto").strip().upper()
    if manual != "AUTO":
        normalized = "WAKE" if manual in {"WAKE", "15:30"} else manual
        if normalized not in CHECKPOINT_SLOTS | {WAKE_SLOT}:
            raise ValueError(f"Unsupported SCANNER_SLOT_ET: {manual_slot}")
        return normalized, False

    run = CRON_RUNS.get(str(schedule_utc or "").strip())
    if run is None:
        return None, False
    slot, required_offset, fallback = run
    current = timestamp_et if timestamp_et is not None else now_et()
    current = current.tz_localize("America/New_York") if current.tzinfo is None else current.tz_convert("America/New_York")
    if current.strftime("%z") != required_offset:
        return None, fallback
    return slot, fallback


def _eligible(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    frame = candidates.copy()
    if "exclusion_reason" in frame.columns:
        frame = frame[frame["exclusion_reason"].fillna("") == ""]
    if "notification_eligible" in frame.columns:
        frame = frame[frame["notification_eligible"].fillna(False).astype(bool)]
    return frame


def checkpoint_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = _eligible(candidates)
    if frame.empty or "alert_rank" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame["alert_rank"].isin(ACTIONABLE_CHECKPOINT_RANKS)].copy()


def wake_candidates(candidates: pd.DataFrame, state: dict[str, Any]) -> pd.DataFrame:
    frame = _eligible(candidates)
    if frame.empty or "alert_rank" not in frame.columns:
        return frame.iloc[0:0].copy()
    frame = frame[frame["alert_rank"] == "S"].copy()
    if frame.empty:
        return frame

    noon_execution = set(map(str, state.get("noon_execution_tickers", [])))
    already_sent = set(map(str, state.get("late_emergency_sent", {}).keys()))
    tickers = frame["ticker"].astype(str)
    return frame[~tickers.isin(noon_execution | already_sent)].copy()


def notification_candidates(candidates: pd.DataFrame, slot: str, state: dict[str, Any]) -> pd.DataFrame:
    if slot in CHECKPOINT_SLOTS:
        return checkpoint_candidates(candidates)
    if slot == WAKE_SLOT:
        return wake_candidates(candidates, state)
    return candidates.iloc[0:0].copy()


def _capturing_save_candidates(candidates: pd.DataFrame, outdir: Path) -> Path:
    CAPTURE["candidates"] = candidates.copy()
    path = legacy.REAL_SAVE_CANDIDATES(candidates, outdir)
    CAPTURE["csv_path"] = path
    return path


def _build_message(candidates: pd.DataFrame, csv_path: Path, schedule_utc: str, limit: int = 10) -> str:
    slot = str(RUN_CONTEXT.get("slot") or "")
    state = RUN_CONTEXT.get("state") or {}
    visible = notification_candidates(candidates, slot, state)
    visible = filter_recently_notified(visible, RUN_CONTEXT.get("cooldown_blocked", set()))

    if slot in CHECKPOINT_SLOTS:
        title = f"{slot} ET S+A Breakout Check"
        if visible.empty:
            return f"{title}\n\nNo new S/A candidates after notification cooldown.\nCSV: `{csv_path}`"
    else:
        title = "Post-Noon New S Wake Check"
        if visible.empty:
            return "NO_NEW_POST_NOON_S"

    sections = [
        title,
        "RS98 + 20-day breakout + volume pace. Candidate discovery only.",
    ]
    shown = 0
    for rank in ["S", "A"]:
        group = visible[visible["alert_rank"] == rank].head(max(0, limit - shown))
        if group.empty:
            continue
        sections.append(f"{rank} Tier")
        for _, row in group.iterrows():
            sections.append(entry._patched_candidate_block(row))
            shown += 1
        if shown >= limit:
            break
    sections.append(f"CSV: `{csv_path}`")
    return "\n\n".join(sections)


def _send_discord_guarded(message: str, *args: Any, **kwargs: Any) -> Any:
    if message == "NO_NEW_POST_NOON_S":
        print("Discord skipped: no post-noon new S candidates", flush=True)
        return None
    return legacy.REAL_SEND_DISCORD_ALERT(message, *args, **kwargs)


def _disable_builtin_pushover(candidates: pd.DataFrame, schedule_utc: str, config: dict[str, Any]) -> pd.DataFrame:
    return candidates.iloc[0:0].copy()


def _ticker_lists(candidates: pd.DataFrame) -> tuple[list[str], list[str]]:
    visible = checkpoint_candidates(candidates)
    if visible.empty:
        return [], []
    s = sorted(visible.loc[visible["alert_rank"] == "S", "ticker"].astype(str).unique().tolist())
    a = sorted(visible.loc[visible["alert_rank"] == "A", "ticker"].astype(str).unique().tolist())
    return s, a


def _checkpoint_pushover_message(slot: str, candidates: pd.DataFrame) -> str:
    s, a = _ticker_lists(candidates)
    lines = [
        f"{slot} ET S+A Scan Complete",
        f"scan_time_et={now_et().isoformat()}",
        f"S ({len(s)}): {', '.join(s) if s else 'None'}",
        f"A ({len(a)}): {', '.join(a) if a else 'None'}",
    ]
    if slot == "12:00":
        lines.append("This S+A set is the noon execution baseline. A later S absent from this set will trigger Emergency wake-up.")
    return "\n".join(lines)


def _wake_pushover_message(candidates: pd.DataFrame, state: dict[str, Any]) -> str:
    tickers = sorted(candidates["ticker"].astype(str).unique().tolist())
    lines = [
        "POST-NOON NEW S: WAKE AND CHECK",
        f"scan_time_et={now_et().isoformat()}",
        f"New S absent from 12:00 S+A baseline: {', '.join(tickers)}",
    ]
    if not bool(state.get("noon_snapshot_complete")):
        lines.append("WARNING: 12:00 state is missing; fail-safe mode woke for every current S.")
    lines.append("Review immediately; no order is placed automatically.")
    return "\n".join(lines)


def _require_pushover() -> None:
    if not legacy.REAL_PUSHOVER_ENABLED():
        raise RuntimeError("PUSHOVER_ENABLED is false; required checkpoint/wake notification was not sent")
    if not (os.environ.get("PUSHOVER_APP_TOKEN") or os.environ.get("PUSHOVER_API_TOKEN")):
        raise RuntimeError("Pushover app token is missing")
    if not os.environ.get("PUSHOVER_USER_KEY"):
        raise RuntimeError("Pushover user key is missing")


def _run_scanner() -> pd.DataFrame:
    entry.sn.save_candidates = _capturing_save_candidates
    entry.sn.build_message = _build_message
    entry.sn.send_discord_alert = _send_discord_guarded
    entry.sn.select_pushover_candidates = _disable_builtin_pushover
    entry.sn.PUSHOVER_EMERGENCY_SCHEDULE = "DISABLED_BY_ET_SLOT_WRAPPER"
    entry.sn.main()
    candidates = CAPTURE.get("candidates")
    return candidates.copy() if isinstance(candidates, pd.DataFrame) else pd.DataFrame()


def main() -> None:
    raw_schedule = os.environ.get("SCANNER_SCHEDULE_UTC", "")
    manual_slot = os.environ.get("SCANNER_SLOT_ET", "auto")
    slot, fallback = resolve_run(raw_schedule, manual_slot=manual_slot)
    print(
        f"ET slot wrapper: schedule={raw_schedule!r} manual_slot={manual_slot!r} "
        f"resolved_slot={slot!r} fallback={fallback} now_et={now_et().isoformat()}",
        flush=True,
    )
    if slot is None:
        print("Seasonal duplicate or unknown schedule: no scan needed", flush=True)
        return

    path = state_path()
    state = load_state(path)
    blocked_tickers = recently_notified_tickers_files(
        STATE_DIR,
        trading_date_et(),
        state,
    )
    RUN_CONTEXT.update(
        {
            "slot": slot,
            "state": state,
            "fallback": fallback,
            "cooldown_blocked": blocked_tickers,
        }
    )

    if slot in CHECKPOINT_SLOTS and bool(state.get("slots", {}).get(slot, {}).get("completed")):
        print(f"Checkpoint {slot} ET already completed; duplicate/fallback suppressed", flush=True)
        return

    # Prevent legacy fixed-JST emergency routing. This wrapper owns all Pushover sends.
    os.environ["SCANNER_SCHEDULE_UTC"] = raw_schedule
    candidates = _run_scanner()

    _require_pushover()
    if slot in CHECKPOINT_SLOTS:
        priority = 0 if slot == "10:00" else 1
        raw_s_tickers, raw_a_tickers = _ticker_lists(candidates)
        notification_frame = filter_recently_notified(candidates, blocked_tickers)
        notified_s_tickers, notified_a_tickers = _ticker_lists(notification_frame)
        raw_visible = set(raw_s_tickers + raw_a_tickers)
        notified_visible = set(notified_s_tickers + notified_a_tickers)
        cooldown_suppressed = sorted(raw_visible - notified_visible)
        result = legacy.REAL_SEND_PUSHOVER_MESSAGE(
            _checkpoint_pushover_message(slot, notification_frame),
            title=f"Morita Bot {slot} ET",
            priority=priority,
        )
        state.setdefault("slots", {})[slot] = {
            "completed": True,
            "completed_at_et": now_et().isoformat(),
            "s_tickers": raw_s_tickers,
            "a_tickers": raw_a_tickers,
            "notified_s_tickers": notified_s_tickers,
            "notified_a_tickers": notified_a_tickers,
            "notification_cooldown_suppressed_tickers": cooldown_suppressed,
            "pushover_status": result.get("status_code"),
            "fallback_run": bool(fallback),
        }
        if slot == "12:00":
            state["noon_snapshot_complete"] = True
            state["noon_execution_tickers"] = sorted(set(raw_s_tickers + raw_a_tickers))
        save_state(path, state)
        print(
            f"Checkpoint {slot} ET recorded: raw_S={raw_s_tickers} raw_A={raw_a_tickers} "
            f"notified_S={notified_s_tickers} notified_A={notified_a_tickers} "
            f"cooldown_suppressed={cooldown_suppressed}",
            flush=True,
        )
        return

    raw_new_s = wake_candidates(candidates, state)
    new_s = filter_recently_notified(raw_new_s, blocked_tickers)
    raw_new_tickers = set(raw_new_s["ticker"].astype(str).tolist()) if not raw_new_s.empty else set()
    new_tickers = set(new_s["ticker"].astype(str).tolist()) if not new_s.empty else set()
    cooldown_suppressed = sorted(raw_new_tickers - new_tickers)
    state["last_wake_scan_at_et"] = now_et().isoformat()
    if new_s.empty:
        save_state(path, state)
        print(
            f"No post-noon new S candidates; no wake notification; cooldown_suppressed={cooldown_suppressed}",
            flush=True,
        )
        return

    result = legacy.REAL_SEND_PUSHOVER_MESSAGE(
        _wake_pushover_message(new_s, state),
        title="Morita Bot NEW S - WAKE",
        priority=2,
        retry=60,
        expire=600,
        sound="siren",
    )
    sent_map = state.setdefault("late_emergency_sent", {})
    for _, row in new_s.iterrows():
        ticker = str(row.get("ticker", ""))
        sent_map[ticker] = {
            "rank": "S",
            "sent_at_et": now_et().isoformat(),
            "production_adjusted_score": float(row.get("production_adjusted_score", 0) or 0),
            "pushover_status": result.get("status_code"),
        }
    save_state(path, state)
    print(
        f"Emergency sent for post-noon new S: {sorted(new_tickers)}; cooldown_suppressed={cooldown_suppressed}",
        flush=True,
    )


if __name__ == "__main__":
    main()
