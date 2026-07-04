from __future__ import annotations

from typing import Any

from .notification_state_machine import ACTIVE_STATES, alert_id, utc_now


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def freeze_setup_snapshot(entry: dict[str, Any], spec: dict[str, Any], convention: dict[str, Any]) -> dict[str, Any]:
    if entry.get("entry_source_type") not in {"confirmed_webull_fill", "manual_entry_registration"}:
        raise ValueError("timer_requires_confirmed_fill_or_manual_entry")
    price = float(entry["entry_price_underlying"])
    frozen = spec["frozen_setup"]
    route = str(entry["strategy_route"])
    if route not in {"S_BREAKOUT", "A_PULLBACK", "B_PULLBACK"}:
        raise ValueError("unsupported_strategy_route")
    setup = dict(entry)
    setup["progress_target_price"] = round(price * float(frozen["progress_target_multiplier"]), 6)
    setup["max_holding_sessions"] = int(frozen["max_holding_sessions"])
    setup["time_stop_rule_label"] = frozen["time_stop_rule_label"]
    setup["session_count_convention_source"] = frozen["session_count_convention_source"]
    setup["baseline_timeout_convention_sha256"] = convention["sha256"]
    setup["current_status"] = entry.get("current_status") or "ACTIVE"
    setup["state_transition_version"] = "morita_notification_v2"
    setup["created_at_utc"] = entry.get("created_at_utc") or utc_now()
    return setup


def session_count(entry_exchange_trade_date: str, exchange_session_date: str, eligible_sessions: list[str]) -> int | None:
    sessions = [str(s) for s in eligible_sessions]
    if entry_exchange_trade_date not in sessions or exchange_session_date not in sessions:
        return None
    start = sessions.index(entry_exchange_trade_date)
    current = sessions.index(exchange_session_date)
    if current < start:
        return None
    return current - start + 1


def progress_status(setup: dict[str, Any], market_rows: list[dict[str, Any]], exchange_session_date: str) -> dict[str, Any]:
    target = float(setup["progress_target_price"])
    ticker = str(setup["ticker"]).upper()
    relevant = [
        row for row in market_rows
        if str(row.get("ticker", "")).upper() == ticker
        and str(row.get("exchange_session_date", "")) >= str(setup["entry_exchange_trade_date"])
        and str(row.get("exchange_session_date", "")) <= exchange_session_date
    ]
    if not relevant:
        return {"progress_status": "unknown_market_data", "progress_met_timestamp_or_session": "", "progress_observation_source": ""}
    for row in relevant:
        try:
            high = float(row.get("high"))
        except Exception:
            continue
        if high >= target:
            return {"progress_status": "progress_condition_met", "progress_met_timestamp_or_session": row.get("exchange_session_date", ""), "progress_observation_source": row.get("source", "market_data")}
    return {"progress_status": "not_reached", "progress_met_timestamp_or_session": "", "progress_observation_source": relevant[-1].get("source", "market_data")}


def current_underlying_price(setup: dict[str, Any], market_rows: list[dict[str, Any]], exchange_session_date: str) -> float | None:
    ticker = str(setup["ticker"]).upper()
    matches = [row for row in market_rows if str(row.get("ticker", "")).upper() == ticker and str(row.get("exchange_session_date", "")) == exchange_session_date]
    if not matches:
        return None
    for key in ["close", "last", "price"]:
        try:
            return float(matches[-1].get(key))
        except Exception:
            pass
    return None


def time_stop_alert_for_setup(setup: dict[str, Any], eligible_sessions: list[str], exchange_session_date: str, market_rows: list[dict[str, Any]], narrow_status: str = "UNAVAILABLE") -> dict[str, Any] | None:
    if setup.get("current_status") not in ACTIVE_STATES:
        return None
    count = session_count(str(setup["entry_exchange_trade_date"]), exchange_session_date, eligible_sessions)
    if count is None or count not in {8, 9, 10}:
        return None
    progress = progress_status(setup, market_rows, exchange_session_date)
    if progress["progress_status"] == "progress_condition_met":
        return None
    if progress["progress_status"] == "unknown_market_data":
        alert_type = "TIME_STOP_PROGRESS_UNKNOWN"
        title = "[TIME STOP DATA UNKNOWN]"
    elif count == 8:
        alert_type = "TIME_STOP_IN_2_SESSIONS"
        title = "[TIME STOP IN 2 SESSIONS]"
    elif count == 9:
        alert_type = "TIME_STOP_TOMORROW"
        title = "[TIME STOP TOMORROW]"
    else:
        alert_type = "EXIT_TODAY_10_SESSION_TIME_STOP"
        title = "[EXIT TODAY - 10-SESSION TIME STOP]"
    current = current_underlying_price(setup, market_rows, exchange_session_date)
    pnl = None if current is None else current / float(setup["entry_price_underlying"]) - 1.0
    return {
        "alert_id": alert_id(str(setup["setup_id"]), alert_type, exchange_session_date),
        "setup_id": setup["setup_id"],
        "base_breakout_id": setup.get("base_breakout_id", ""),
        "ticker": setup["ticker"],
        "strategy_route": setup["strategy_route"],
        "alert_type": alert_type,
        "alert_title": title,
        "exchange_session_date": exchange_session_date,
        "state_transition_version": "morita_notification_v2",
        "session_count": count,
        "session_count_text": f"{count} / {setup['max_holding_sessions']}",
        "entry_price_underlying": setup["entry_price_underlying"],
        "current_underlying_price": current,
        "underlying_pnl_only": pnl,
        "progress_target_price": setup["progress_target_price"],
        **progress,
        "narrow_leadership_status": narrow_status,
        "required_action": "close or reduce according to execution policy, then acknowledge" if count == 10 and progress["progress_status"] == "not_reached" else "monitor; no automatic order",
        "notification_only": True,
        "automatic_order": False,
    }


def breakout_low_risk_alert(setup: dict[str, Any], observed_price: float, observed_source: str, exchange_session_date: str, session_count_value: int | None, progress: dict[str, Any], narrow_status: str = "UNAVAILABLE") -> dict[str, Any]:
    stop_ref = float(setup["breakout_day_low_reference"])
    return {
        "alert_id": alert_id(str(setup["setup_id"]), "BREAKOUT_LOW_BREACH_RISK_ALERT", exchange_session_date),
        "setup_id": setup["setup_id"],
        "base_breakout_id": setup.get("base_breakout_id", ""),
        "ticker": setup["ticker"],
        "strategy_route": setup["strategy_route"],
        "alert_type": "BREAKOUT_LOW_BREACH_RISK_ALERT",
        "alert_title": "[BREAKOUT LOW BREACH - RISK ALERT]",
        "exchange_session_date": exchange_session_date,
        "state_transition_version": "morita_notification_v2",
        "observed_price": observed_price,
        "observed_price_source": observed_source,
        "breakout_day_low_reference": stop_ref,
        "distance_below_reference": observed_price / stop_ref - 1.0,
        "session_count_text": "" if session_count_value is None else f"{session_count_value} / {setup['max_holding_sessions']}",
        "progress_status": progress.get("progress_status", "unknown_market_data"),
        "narrow_leadership_status": narrow_status,
        "risk_alert_only": True,
        "message_footer": "Risk alert only. This is not an automatic sell instruction. The 10-session time-stop rule remains active.",
        "automatic_order": False,
    }


def s_breakout_buy_ready_alert(candidate: dict[str, Any], exchange_session_date: str, narrow_status: str, spec: dict[str, Any]) -> dict[str, Any]:
    sleeve = int(spec["s_breakout"]["standard_suggested_premium_sleeve_pct"])
    return {
        "alert_id": alert_id(str(candidate["candidate_id"]), "S_BREAKOUT_BUY_READY", exchange_session_date),
        "setup_id": candidate["candidate_id"],
        "base_breakout_id": candidate.get("base_breakout_id", ""),
        "ticker": candidate["ticker"],
        "rank": "S",
        "alert_type": "S_BREAKOUT_BUY_READY",
        "alert_title": "[S BREAKOUT - BUY READY]",
        "exchange_session_date": exchange_session_date,
        "state_transition_version": "morita_notification_v2",
        "signal_date": candidate.get("signal_decision_date", ""),
        "entry_convention": candidate.get("entry_convention", "next_eligible_session_open"),
        "breakout_day_low_reference": candidate.get("breakout_day_low_reference", ""),
        "narrow_leadership_status": narrow_status,
        "suggested_premium_sleeve_pct": sleeve,
        "fifty_pct_exception_available": False if narrow_status == "ON" else True,
        "notification_only": True,
        "automatic_order": False,
    }
