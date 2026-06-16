from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

import scripts.production_scanner_entry as entry


TARGET_0430_CRON = "30 19 * * 0-4"
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
    print(f"candidates count: {len(candidates)}", flush=True)
    if candidates.empty:
        print("No breakout candidates found", flush=True)
    return path


def _select_rank_a_pushover_candidates(candidates: pd.DataFrame, schedule_utc: str, config: dict[str, Any]) -> pd.DataFrame:
    if schedule_utc not in PRE_CLOSE_CRONS or candidates.empty:
        print("Pushover skipped: not pre-close schedule or no scanner candidates", flush=True)
        return candidates.iloc[0:0].copy()
    base = candidates[(candidates["exclusion_reason"].fillna("") == "") & (candidates["alert_rank"] == "A")].copy()
    if base.empty:
        print("Pushover skipped: no Rank A emergency candidates", flush=True)
    state_path = entry._state_path(Path("scanner_alerts") / entry.sn.today_str() / "russell1000_momentum_candidates.csv")
    state = entry._load_state(state_path)
    sendable = pd.DataFrame([row for _, row in base.iterrows() if entry._needs_emergency(row, state)])
    if not base.empty and sendable.empty:
        print("Pushover skipped: duplicate Rank A emergency candidates already sent", flush=True)
    entry.EMERGENCY_CONTEXT.clear()
    entry.EMERGENCY_CONTEXT.update({"state_path": state_path, "state": state, "candidates": sendable})
    return sendable


def _send_rank_a_emergency(message: str, title: str = "Rank A Breakout Alert", **kwargs: Any) -> dict[str, Any]:
    candidates = entry.EMERGENCY_CONTEXT.get("candidates", pd.DataFrame())
    try:
        print("Pushover sending: priority=2 retry=60 expire=3600 sound=climb", flush=True)
        result = REAL_SEND_PUSHOVER_EMERGENCY(message, title=title, **kwargs)
        print(f"Pushover sent: status_code={result.get('status_code')}", flush=True)
        entry._record_emergency(candidates, result.get("status_code"), True)
        return result
    except Exception as exc:
        print(f"Pushover failed: {exc}", flush=True)
        entry._record_emergency(candidates, f"ERROR: {exc}", False)
        raise


def main() -> None:
    schedule = os.environ.get("SCANNER_SCHEDULE_UTC", "")
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
    entry.sn.PUSHOVER_EMERGENCY_SCHEDULE = TARGET_0430_CRON
    entry.sn.send_discord_alert = _logged_send_discord_alert
    entry.sn.pushover_enabled = _logged_pushover_enabled
    entry.sn.save_candidates = _logged_save_candidates
    entry.sn.select_pushover_candidates = _select_rank_a_pushover_candidates
    entry.sn.send_pushover_emergency = _send_rank_a_emergency

    try:
        entry.sn.main()
    finally:
        print(f"scanner finished: current_jst={pd.Timestamp.now(tz='Asia/Tokyo').isoformat()}", flush=True)


if __name__ == "__main__":
    main()
