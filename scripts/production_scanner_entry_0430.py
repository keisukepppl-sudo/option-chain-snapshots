from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.production_scanner_entry as entry
from scanner.pushover_notify import send_pushover_message as REAL_SEND_PUSHOVER_MESSAGE


TARGET_0430_CRON = "30 19 * * 0-4"
MORNING_1000_CRON = "0 1 * * 1-5"
MORNING_1015_CRON = "15 1 * * 1-5"
FINAL_0430_CRONS = {
    TARGET_0430_CRON,
    "30 19 * * 1-5",
}
MORNING_STATUS_CRONS = {MORNING_1000_CRON, MORNING_1015_CRON}
STATUS_NOTIFICATION_CRONS = set(FINAL_0430_CRONS) | MORNING_STATUS_CRONS
PRE_CLOSE_CRONS = {
    "15 19 * * 1-5",
    "25 19 * * 1-5",
    "35 19 * * 1-5",
    "30 19 * * 1-5",
    TARGET_0430_CRON,
}


REAL_SEND_DISCORD_ALERT = entry.sn.send_discord_alert
REAL_PUSHOVER_ENABLED = entry.sn.pushover_enabled
REAL_SEND_PUSHOVER_EMERGENCY = entry.REAL_SEND_PUSHOVER_EMERGENCY
REAL_SAVE_CANDIDATES = entry.sn.save_candidates
EMERGENCY_RANKS = ["S", "A", "B", "C"]
EMERGENCY_RANK_SET = set(EMERGENCY_RANKS)
SCAN_CONTEXT: dict[str, Any] = {
    "candidates_total": 0,
    "notifiable_candidates": 0,
    "rank_counts": {rank: 0 for rank in EMERGENCY_RANKS},
    "pushover_sent_count": 0,
    "notification_sent": False,
    "csv_path": None,
}


def _logged_send_discord_alert(*args: Any, **kwargs: Any) -> Any:
    try:
        result = REAL_SEND_DISCORD_ALERT(*args, **kwargs)
        print("Discord sent", flush=True)
        return result
    except Exception as exc:
        print(f"Discord failed/skipped: {exc}", flush=True)
        raise


def _logged_pushover_enabled(*args: Any, **kwargs: Any) -> bool:
    enabled = REAL_PUSHOVER_ENABLED(*args, **kwargs)
    print(f"Pushover enabled: {enabled}", flush=True)
    if not enabled:
        print("Pushover skipped: PUSHOVER_ENABLED is false", flush=True)
    return enabled


def _logged_save_candidates(candidates: pd.DataFrame, outdir: Path) -> Path:
    path = REAL_SAVE_CANDIDATES(candidates, outdir)
    rank_counts = _rank_counts(candidates)
    notifiable_count = _notifiable_count(candidates)
    SCAN_CONTEXT.update(
        {
            "candidates_total": int(len(candidates)),
            "notifiable_candidates": int(notifiable_count),
            "rank_counts": rank_counts,
            "csv_path": path,
        }
    )
    print(f"candidates count: {len(candidates)}", flush=True)
    print(f"notifiable S/A/B/C candidates count: {notifiable_count}", flush=True)
    print(f"rank counts: {_format_rank_counts(rank_counts)}", flush=True)
    if notifiable_count == 0:
        print("No breakout candidates found", flush=True)
    return path


def _select_sabcd_pushover_candidates(candidates: pd.DataFrame, schedule_utc: str, config: dict[str, Any]) -> pd.DataFrame:
    if schedule_utc not in PRE_CLOSE_CRONS or candidates.empty:
        print("Pushover skipped: not pre-close schedule or no scanner candidates", flush=True)
        return candidates.iloc[0:0].copy()
    base = candidates[(candidates["exclusion_reason"].fillna("") == "") & candidates["alert_rank"].isin(EMERGENCY_RANKS)].copy()
    if base.empty:
        print("Pushover skipped: no S/A/B/C candidates", flush=True)
    state_path = entry._state_path(Path("scanner_alerts") / entry.sn.today_str() / "russell1000_momentum_candidates.csv")
    state = entry._load_state(state_path)
    sendable = pd.DataFrame([row for _, row in base.iterrows() if entry._needs_emergency(row, state)])
    if not base.empty and sendable.empty:
        print("Pushover skipped: duplicate S/A/B/C emergency candidates already sent", flush=True)
    entry.EMERGENCY_CONTEXT.clear()
    entry.EMERGENCY_CONTEXT.update({"state_path": state_path, "state": state, "candidates": sendable})
    return sendable


def _send_sabcd_emergency(message: str, title: str = "04:30 Breakout Alert", **kwargs: Any) -> dict[str, Any]:
    candidates = entry.EMERGENCY_CONTEXT.get("candidates", pd.DataFrame())
    try:
        result = REAL_SEND_PUSHOVER_EMERGENCY(message, title=title, **kwargs)
        print(f"Pushover sent: status_code={result.get('status_code')}", flush=True)
        SCAN_CONTEXT["pushover_sent_count"] = int(SCAN_CONTEXT.get("pushover_sent_count", 0)) + 1
        SCAN_CONTEXT["notification_sent"] = True
        entry._record_emergency(candidates, result.get("status_code"), True)
        return result
    except Exception as exc:
        print(f"Pushover failed: {exc}", flush=True)
        entry._record_emergency(candidates, f"ERROR: {exc}", False)
        raise


def _is_final_0430_schedule(schedule_utc: str) -> bool:
    return schedule_utc in FINAL_0430_CRONS


def _is_status_notification_schedule(schedule_utc: str) -> bool:
    return schedule_utc in STATUS_NOTIFICATION_CRONS


def _scheduled_scan_jst(schedule_utc: str) -> str:
    if schedule_utc == MORNING_1000_CRON:
        return "10:00"
    if schedule_utc == MORNING_1015_CRON:
        return "10:15"
    if schedule_utc in FINAL_0430_CRONS:
        return "04:30"
    return "N/A"


def _rank_counts(candidates: pd.DataFrame) -> dict[str, int]:
    counts = {rank: 0 for rank in EMERGENCY_RANKS}
    if candidates.empty:
        return counts
    rank_col = "alert_rank" if "alert_rank" in candidates.columns else "production_rank" if "production_rank" in candidates.columns else "rank"
    if rank_col not in candidates.columns:
        return counts
    frame = candidates.copy()
    if "exclusion_reason" in frame.columns:
        frame = frame[frame["exclusion_reason"].fillna("") == ""]
    elif "excluded" in frame.columns:
        frame = frame[~frame["excluded"].astype(bool)]
    values = frame[rank_col].value_counts(dropna=False).to_dict()
    for rank in EMERGENCY_RANKS:
        counts[rank] = int(values.get(rank, 0))
    return counts


def _notifiable_count(candidates: pd.DataFrame) -> int:
    return int(sum(_rank_counts(candidates).values()))


def _format_rank_counts(counts: dict[str, int]) -> str:
    return " ".join(f"{rank}={int(counts.get(rank, 0))}" for rank in EMERGENCY_RANKS)


def _scan_time_jst() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Tokyo")


def _scan_time_text() -> str:
    return _scan_time_jst().strftime("%Y-%m-%d %H:%M JST")


def _completion_message(status: str = "SUCCESS") -> str:
    counts = SCAN_CONTEXT.get("rank_counts") or {rank: 0 for rank in EMERGENCY_RANKS}
    candidates = int(SCAN_CONTEXT.get("notifiable_candidates", 0))
    schedule_utc = str(SCAN_CONTEXT.get("schedule_utc", ""))
    scheduled_scan_jst = _scheduled_scan_jst(schedule_utc)
    today_line = "No S/A/B/C candidates found." if candidates == 0 else "S/A/B/C candidates found. See Discord/CSV for details."
    return (
        "Russell1000 Scanner\n\n"
        f"{scheduled_scan_jst} JST Scan Complete\n\n"
        f"scheduled_scan_jst: {scheduled_scan_jst}\n"
        f"actual_run_time_jst: {_scan_time_text()}\n"
        f"SCANNER_SCHEDULE_UTC: {schedule_utc}\n"
        "notification_sent: YES\n\n"
        f"Scan Time:\n{_scan_time_text()}\n\n"
        f"Candidates:\n{candidates}\n\n"
        "Rank Count:\n"
        f"{_format_rank_counts(counts)}\n\n"
        f"Today:\n{today_line}\n\n"
        f"Scanner Status:\n{status}\n\n"
        "Market Status:\nscanned successfully"
    )


def _error_message(exc: BaseException) -> str:
    schedule_utc = str(SCAN_CONTEXT.get("schedule_utc", ""))
    scheduled_scan_jst = _scheduled_scan_jst(schedule_utc)
    return (
        "Russell1000 Scanner ERROR\n\n"
        f"scheduled_scan_jst: {scheduled_scan_jst}\n"
        f"actual_run_time_jst: {_scan_time_text()}\n"
        f"SCANNER_SCHEDULE_UTC: {schedule_utc}\n"
        "notification_sent: YES\n\n"
        f"Scan Time:\n{_scan_time_text()}\n\n"
        "Error:\n"
        f"{exc}"
    )


def _send_pushover_status(message: str, title: str) -> bool:
    if not REAL_PUSHOVER_ENABLED():
        print("Pushover status skipped: PUSHOVER_ENABLED is false", flush=True)
        return False
    try:
        result = REAL_SEND_PUSHOVER_MESSAGE(message, title=title, priority=0)
        print(f"Pushover status sent: status_code={result.get('status_code')}", flush=True)
        SCAN_CONTEXT["pushover_sent_count"] = int(SCAN_CONTEXT.get("pushover_sent_count", 0)) + 1
        SCAN_CONTEXT["notification_sent"] = True
        return True
    except Exception as exc:
        print(f"Pushover status failed: {exc}", flush=True)
        return False


def _send_final_completion_if_needed(raw_schedule: str) -> None:
    if not _is_status_notification_schedule(raw_schedule):
        return
    if bool(SCAN_CONTEXT.get("notification_sent")):
        return
    scheduled_scan_jst = _scheduled_scan_jst(raw_schedule)
    _send_pushover_status(
        _completion_message("SUCCESS"),
        title=f"Russell1000 Scanner {scheduled_scan_jst} JST",
    )


def _send_error_notification(raw_schedule: str, exc: BaseException) -> None:
    if not _is_status_notification_schedule(raw_schedule):
        return
    _send_pushover_status(
        _error_message(exc),
        title="Russell1000 Scanner ERROR",
    )


def _print_required_log(raw_schedule: str) -> None:
    print("[SCANNER]", flush=True)
    print(f"schedule={raw_schedule}", flush=True)
    print("", flush=True)
    print("[JST]", flush=True)
    print(_scan_time_jst().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    print("", flush=True)
    print("Candidates:", flush=True)
    print(int(SCAN_CONTEXT.get("notifiable_candidates", 0)), flush=True)
    print("", flush=True)
    print("Notification sent:", flush=True)
    print("YES" if bool(SCAN_CONTEXT.get("notification_sent")) else "NO", flush=True)


def main() -> None:
    schedule = os.environ.get("SCANNER_SCHEDULE_UTC", "")
    SCAN_CONTEXT["schedule_utc"] = schedule
    print(f"scanner started: current_jst={pd.Timestamp.now(tz='Asia/Tokyo').isoformat()} schedule_utc={schedule}", flush=True)
    if not os.environ.get("PUSHOVER_APP_TOKEN") and os.environ.get("PUSHOVER_API_TOKEN"):
        os.environ["PUSHOVER_APP_TOKEN"] = os.environ["PUSHOVER_API_TOKEN"]
    has_token = bool(os.environ.get("PUSHOVER_APP_TOKEN") or os.environ.get("PUSHOVER_API_TOKEN"))
    has_user = bool(os.environ.get("PUSHOVER_USER_KEY"))
    print(f"Pushover token exists: {has_token}", flush=True)
    print(f"Pushover user key exists: {has_user}", flush=True)
    if not has_token or not has_user:
        print("Pushover skipped: token/user key missing", flush=True)
    if schedule in PRE_CLOSE_CRONS:
        os.environ["SCANNER_SCHEDULE_UTC"] = TARGET_0430_CRON

    entry.PRE_CLOSE_SCAN_SCHEDULES.add(TARGET_0430_CRON)
    entry.EMERGENCY_RANKS = list(EMERGENCY_RANKS)
    entry.EMERGENCY_RANK_SET = set(EMERGENCY_RANKS)
    entry.sn.EMERGENCY_RANKS = list(EMERGENCY_RANKS)
    entry.sn.EMERGENCY_RANK_SET = set(EMERGENCY_RANKS)
    entry.sn.PUSHOVER_EMERGENCY_SCHEDULE = TARGET_0430_CRON
    entry.sn.send_discord_alert = _logged_send_discord_alert
    entry.sn.pushover_enabled = _logged_pushover_enabled
    entry.sn.save_candidates = _logged_save_candidates
    entry.sn.select_pushover_candidates = _select_sabcd_pushover_candidates
    entry.sn.send_pushover_emergency = _send_sabcd_emergency

    try:
        entry.sn.main()
        _send_final_completion_if_needed(schedule)
    except Exception as exc:
        print(f"scanner error: {exc}", flush=True)
        _send_error_notification(schedule, exc)
        raise
    finally:
        _print_required_log(schedule)
        print(f"scanner finished: current_jst={pd.Timestamp.now(tz='Asia/Tokyo').isoformat()}", flush=True)


if __name__ == "__main__":
    main()
