from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_weekly_rows(candidate_rows: list[dict[str, Any]], alert_rows: list[dict[str, Any]], setup_rows: list[dict[str, Any]], ack_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranks = ["A", "B"]
    rows: list[dict[str, Any]] = []
    for rank in ranks:
        scoped = [row for row in candidate_rows if str(row.get("rank", "")) == rank or str(row.get("strategy_route", "")) == f"{rank}_PULLBACK"]
        rows.append({
            "section": "ab_funnel",
            "rank": rank,
            "base_breakouts_registered": sum(1 for row in scoped if row.get("state") == "BASE_BREAKOUT_REGISTERED"),
            "waiting_for_first_pullback": sum(1 for row in scoped if row.get("state") == "WAITING_FOR_FIRST_ELIGIBLE_PULLBACK"),
            "first_pullbacks_observed": sum(1 for row in scoped if row.get("state") == "PULLBACK_UNDER_OBSERVATION"),
            "rebound_confirmations": sum(1 for row in scoped if row.get("state") == "REBOUND_CONFIRMATION_PENDING"),
            "buy_ready_alerts": sum(1 for row in alert_rows if row.get("alert_type") == "AB_PULLBACK_BUY_READY" and row.get("rank") == rank),
            "expired_no_chase_alerts": sum(1 for row in alert_rows if row.get("alert_type") == "AB_ALERT_EXPIRED_NO_CHASE"),
            "confirmed_entries": sum(1 for row in setup_rows if row.get("strategy_route") == f"{rank}_PULLBACK"),
            "unresolved_rule_admin_failures": sum(1 for row in scoped if row.get("state") == "A_B_PULLBACK_RULE_UNRESOLVED"),
        })
    time_stop_alerts = [row for row in alert_rows if row.get("alert_type") in {"TIME_STOP_IN_2_SESSIONS", "TIME_STOP_TOMORROW", "EXIT_TODAY_10_SESSION_TIME_STOP", "TIME_STOP_PROGRESS_UNKNOWN"}]
    rows.append({
        "section": "time_stop_discipline",
        "rank": "S/A/B",
        "active_setups_start": "",
        "active_setups_end": sum(1 for row in setup_rows if row.get("current_status") in {"ENTRY_CONFIRMED", "ACTIVE", "TIME_STOP_DUE"}),
        "session_8_reminders": sum(1 for row in alert_rows if row.get("alert_type") == "TIME_STOP_IN_2_SESSIONS"),
        "session_9_reminders": sum(1 for row in alert_rows if row.get("alert_type") == "TIME_STOP_TOMORROW"),
        "time_stop_alerts": sum(1 for row in alert_rows if row.get("alert_type") == "EXIT_TODAY_10_SESSION_TIME_STOP"),
        "acknowledgements": len(ack_rows),
        "unacknowledged_alerts": max(0, len(time_stop_alerts) - len(ack_rows)),
        "median_time_to_acknowledgement": "",
        "broker_sync_exceptions": sum(1 for row in ack_rows if row.get("reason") == "broker_sync_unavailable"),
        "bot_setup_performance": "separate_from_notification_correctness",
        "notification_correctness": "event_log_based",
        "user_execution_compliance": "acknowledgement_based",
        "webull_synchronization_quality": "read_only_or_manual",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })
    return rows
