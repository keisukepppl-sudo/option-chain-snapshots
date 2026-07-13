from __future__ import annotations

import math
import os
from typing import Any

import pandas as pd

import discord_alert
import scripts.production_scanner_entry as production_entry
from morita_cloud.logic import FINAL_EXECUTION_SLOT, checkpoint_candidates, eligible, normalize_et
from scanner.pushover_notify import send_pushover_message


def candidate_summary_line(row: pd.Series) -> str:
    ticker = str(row.get("ticker", ""))
    rank = str(row.get("alert_rank", ""))
    price = float(row.get("latest_price", row.get("close", math.nan)))
    volume = float(row.get("volume_multiple", math.nan))
    score = float(row.get("production_adjusted_score", math.nan))
    return f"{rank} {ticker} price={price:.2f} vol={volume:.2f}x score={score:.1f}"


def checkpoint_message(
    slot: str,
    candidates: pd.DataFrame,
    cutoff_et: pd.Timestamp,
    diagnostics: dict[str, Any] | None = None,
) -> str:
    diagnostics = diagnostics or {}
    visible = checkpoint_candidates(candidates)
    cutoff = normalize_et(cutoff_et)
    lines = [
        f"{slot} JST S+A Scan",
        f"scheduled_slot_jst={slot}",
        f"decision_cutoff_jst={cutoff.tz_convert('Asia/Tokyo').isoformat()}",
        f"decision_cutoff_et={cutoff.isoformat()}",
    ]
    if diagnostics.get("market_not_open"):
        lines.append("U.S. market is not open yet; S/A cannot be evaluated at this fixed JST slot.")
    elif visible.empty:
        lines.append("No S/A candidates.")
    else:
        for _, row in visible.head(12).iterrows():
            lines.append(candidate_summary_line(row))
        if len(visible) > 12:
            lines.append(f"... plus {len(visible) - 12} more")
    if slot == FINAL_EXECUTION_SLOT:
        lines.append("This set becomes the 24:00 JST execution baseline.")
    return "\n".join(lines)


def wake_message(candidates: pd.DataFrame, state: dict[str, Any], cutoff_et: pd.Timestamp) -> str:
    cutoff = normalize_et(cutoff_et)
    lines = [
        "POST-24:00 JST NEW S: WAKE AND CHECK",
        f"decision_cutoff_jst={cutoff.tz_convert('Asia/Tokyo').isoformat()}",
        f"decision_cutoff_et={cutoff.isoformat()}",
    ]
    for _, row in candidates.head(10).iterrows():
        lines.append(candidate_summary_line(row))
    if len(candidates) > 10:
        lines.append(f"... plus {len(candidates) - 10} more")
    if not bool(state.get("noon_snapshot_complete")):
        lines.append("WARNING: 24:00 JST baseline missing; fail-safe woke for every current S.")
    lines.append("No order was placed automatically.")
    return "\n".join(lines)


def full_discord_message(title: str, candidates: pd.DataFrame, cutoff_et: pd.Timestamp) -> str:
    cutoff = normalize_et(cutoff_et)
    lines = [
        title,
        f"decision_cutoff_jst={cutoff.tz_convert('Asia/Tokyo').isoformat()}",
        f"decision_cutoff_et={cutoff.isoformat()}",
    ]
    visible = eligible(candidates)
    if visible.empty:
        lines.append("No eligible candidates.")
    else:
        for _, row in visible.head(20).iterrows():
            lines.append(production_entry._patched_candidate_block(row))
    return "\n\n".join(lines)


def send_notification(
    message: str,
    title: str,
    priority: int,
    discord_message: str,
    dry_run: bool,
    retry: int | None = None,
    expire: int | None = None,
    sound: str | None = None,
) -> dict[str, Any]:
    if dry_run:
        print(f"[DRY RUN] {title}\n{message}", flush=True)
        return {"status": "DRY_RUN", "priority": priority}

    result = send_pushover_message(
        message,
        title=title,
        priority=priority,
        retry=retry,
        expire=expire,
        sound=sound,
    )
    if os.environ.get("STOCK"):
        try:
            discord_alert.send_discord_alert(discord_message, env_var="STOCK")
        except Exception as exc:
            print(f"Discord send failed after Pushover success: {exc}", flush=True)
    return {
        "status": "SENT",
        "status_code": result.get("status_code"),
        "priority": priority,
    }
