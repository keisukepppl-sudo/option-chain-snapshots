from __future__ import annotations

from typing import Any

from .notification_state_machine import NON_ENTRY_TERMINAL_STATES, alert_id, stable_id


def rule_source_status(spec: dict[str, Any]) -> dict[str, Any]:
    ab = spec["ab_pullback"]
    return {
        "status": ab["rule_source_status"],
        "fail_closed_status": ab["fail_closed_status"],
        "exact_frozen_rule_source_found": ab["rule_source_status"] == "resolved_committed_source",
    }


def base_breakout_id(source_signal_id: str, ticker: str, base_breakout_date: str) -> str:
    return "bb_" + stable_id(source_signal_id, ticker.upper(), base_breakout_date)


def candidate_id(base_id: str) -> str:
    return "ab_" + stable_id(base_id, "first_eligible_pullback")


def validate_ab_route_gates(candidate: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, str]:
    source = rule_source_status(spec)
    if not source["exact_frozen_rule_source_found"]:
        return False, source["fail_closed_status"]
    ab = spec["ab_pullback"]
    if candidate.get("rank") not in set(ab["eligible_ranks"]):
        return False, "rank_not_ab"
    if float(candidate.get("accumulation_score", -999)) < float(ab["minimum_accumulation_score"]):
        return False, "accumulation_score_below_50"
    required_true = [
        "valid_base_breakout_exists",
        "within_20_sessions",
        "first_eligible_pullback",
        "low_volume_adjustment_confirmed",
        "base_breakout_remains_valid",
        "rebound_confirmation_complete",
    ]
    for key in required_true:
        if not bool(candidate.get(key)):
            return False, f"missing_gate:{key}"
    return True, "buy_ready"


def is_base_locked(base_id: str, registry_rows: list[dict[str, Any]], alert_rows: list[dict[str, Any]]) -> bool:
    terminal = {row.get("base_breakout_id") for row in registry_rows if row.get("state") in NON_ENTRY_TERMINAL_STATES or row.get("state") in {"BUY_READY_ALERTED", "ENTRY_CONFIRMED", "ACTIVE"}}
    alerted = {row.get("base_breakout_id") for row in alert_rows if row.get("alert_type") == "AB_PULLBACK_BUY_READY"}
    return base_id in terminal or base_id in alerted


def evaluate_ab_candidate(candidate: dict[str, Any], spec: dict[str, Any], registry_rows: list[dict[str, Any]], alert_rows: list[dict[str, Any]], exchange_session_date: str, narrow_status: str = "UNAVAILABLE") -> tuple[dict[str, Any], dict[str, Any] | None]:
    base_id = candidate.get("base_breakout_id") or base_breakout_id(str(candidate.get("source_signal_id", "")), str(candidate.get("ticker", "")), str(candidate.get("base_breakout_date", "")))
    cid = candidate.get("candidate_id") or candidate_id(base_id)
    if is_base_locked(base_id, registry_rows, alert_rows):
        return {"candidate_id": cid, "base_breakout_id": base_id, "state": "BUY_ALERT_EXPIRED_NO_CHASE", "reason": "base_breakout_locked"}, None
    ok, reason = validate_ab_route_gates(candidate, spec)
    if not ok:
        state = "A_B_PULLBACK_RULE_UNRESOLVED" if reason == spec["ab_pullback"]["fail_closed_status"] else "PULLBACK_UNDER_OBSERVATION"
        return {"candidate_id": cid, "base_breakout_id": base_id, "state": state, "reason": reason}, None
    rank = str(candidate["rank"])
    event = {
        "alert_id": alert_id(cid, "AB_PULLBACK_BUY_READY", exchange_session_date),
        "setup_id": cid,
        "candidate_id": cid,
        "base_breakout_id": base_id,
        "source_signal_id": candidate.get("source_signal_id", ""),
        "ticker": candidate["ticker"],
        "rank": rank,
        "strategy_route": f"{rank}_PULLBACK",
        "alert_type": "AB_PULLBACK_BUY_READY",
        "alert_title": f"[{rank} PULLBACK - BUY READY]",
        "exchange_session_date": exchange_session_date,
        "state_transition_version": "morita_notification_v2",
        "base_breakout_date": candidate["base_breakout_date"],
        "first_eligible_pullback": candidate.get("first_eligible_pullback_date", ""),
        "accumulation_score": candidate["accumulation_score"],
        "low_volume_summary": candidate.get("low_volume_summary", ""),
        "rebound_confirmation_summary": candidate.get("rebound_confirmation_summary", ""),
        "entry_timing_convention": candidate.get("entry_timing_convention", "confirmation_close_final_then_next_session"),
        "entry_valid_until": candidate.get("entry_valid_until", ""),
        "suggested_premium_sleeve_pct": spec["ab_pullback"]["suggested_premium_sleeve_pct"],
        "narrow_leadership_status": narrow_status,
        "notification_only": True,
        "automatic_order": False,
    }
    return {"candidate_id": cid, "base_breakout_id": base_id, "state": "BUY_READY_ALERTED", "reason": "buy_ready"}, event


def expired_no_chase_event(candidate: dict[str, Any], exchange_session_date: str) -> dict[str, Any]:
    cid = str(candidate["candidate_id"])
    return {
        "alert_id": alert_id(cid, "AB_ALERT_EXPIRED_NO_CHASE", exchange_session_date),
        "setup_id": cid,
        "candidate_id": cid,
        "base_breakout_id": candidate.get("base_breakout_id", ""),
        "ticker": candidate.get("ticker", ""),
        "alert_type": "AB_ALERT_EXPIRED_NO_CHASE",
        "alert_title": "[A/B ALERT EXPIRED - NO CHASE]",
        "exchange_session_date": exchange_session_date,
        "state_transition_version": "morita_notification_v2",
        "notification_only": True,
        "automatic_order": False,
    }
