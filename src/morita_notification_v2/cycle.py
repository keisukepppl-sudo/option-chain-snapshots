from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .ab_pullback_lifecycle import evaluate_ab_candidate
from .notification_state_machine import append_jsonl, load_spec, read_jsonl, record_alert, state_paths, utc_now, verify_baseline_timeout_convention, write_csv
from .time_stop_engine import breakout_low_risk_alert, progress_status, session_count, time_stop_alert_for_setup


def read_csv_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def narrow_status_from_rows(rows: list[dict[str, Any]], ticker: str | None = None) -> str:
    if not rows:
        return "UNAVAILABLE"
    if ticker:
        matches = [row for row in rows if str(row.get("ticker", "")).upper() == ticker.upper()]
        if matches:
            value = str(matches[-1].get("narrow_leadership_status", "UNAVAILABLE")).upper()
            return value if value in {"ON", "OFF", "UNAVAILABLE"} else "UNAVAILABLE"
    value = str(rows[-1].get("narrow_leadership_status", rows[-1].get("status", "UNAVAILABLE"))).upper()
    return value if value in {"ON", "OFF", "UNAVAILABLE"} else "UNAVAILABLE"


def run_notification_cycle(exchange_session_date: str, eligible_sessions: list[str], market_rows: list[dict[str, Any]] | None = None, narrow_rows: list[dict[str, Any]] | None = None, spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec or load_spec()
    verify_baseline_timeout_convention(spec)
    paths = state_paths(spec)
    setup_rows = read_jsonl(paths["setup_registry"])
    candidate_rows = read_jsonl(paths["ab_candidate_registry"])
    alert_rows = read_jsonl(paths["alert_events"])
    ack_rows = read_jsonl(paths["manual_acknowledgements"])
    acked_setup_ids = {str(row.get("setup_id")) for row in ack_rows}
    market_rows = market_rows or []
    narrow_rows = narrow_rows or []
    emitted: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []

    for candidate in candidate_rows:
        state, event = evaluate_ab_candidate(candidate, spec, candidate_rows, alert_rows + emitted, exchange_session_date, narrow_status_from_rows(narrow_rows, candidate.get("ticker")))
        state["ticker"] = candidate.get("ticker", "")
        state["rank"] = candidate.get("rank", "")
        state["evaluated_at_utc"] = utc_now()
        lifecycle_rows.append(state)
        if event:
            emitted.append(record_alert(paths["alert_events"], alert_rows + emitted, event))

    for setup in setup_rows:
        if str(setup.get("setup_id")) in acked_setup_ids:
            continue
        narrow = narrow_status_from_rows(narrow_rows, setup.get("ticker"))
        event = time_stop_alert_for_setup(setup, eligible_sessions, exchange_session_date, market_rows, narrow)
        if event:
            emitted.append(record_alert(paths["alert_events"], alert_rows + emitted, event))
        if setup.get("strategy_route") == "S_BREAKOUT" and setup.get("breakout_day_low_reference"):
            ticker = str(setup.get("ticker", "")).upper()
            todays = [row for row in market_rows if str(row.get("ticker", "")).upper() == ticker and str(row.get("exchange_session_date", "")) == exchange_session_date]
            for row in todays[-1:]:
                try:
                    low = float(row.get("low"))
                    stop = float(setup["breakout_day_low_reference"])
                except Exception:
                    continue
                if low <= stop:
                    count = session_count(str(setup["entry_exchange_trade_date"]), exchange_session_date, eligible_sessions)
                    progress = progress_status(setup, market_rows, exchange_session_date)
                    risk = breakout_low_risk_alert(setup, low, row.get("source", "market_data"), exchange_session_date, count, progress, narrow)
                    emitted.append(record_alert(paths["alert_events"], alert_rows + emitted, risk))

    audit = paths["audit_output_dir"]
    alert_rows_after = read_jsonl(paths["alert_events"])
    write_csv(audit / "ab_pullback_lifecycle_log.csv", lifecycle_rows)
    write_csv(audit / "ab_buy_ready_alert_log.csv", [row for row in alert_rows_after if row.get("alert_type") in {"AB_PULLBACK_BUY_READY", "AB_ALERT_EXPIRED_NO_CHASE"}])
    write_csv(audit / "time_stop_alert_log.csv", [row for row in alert_rows_after if "TIME_STOP" in str(row.get("alert_type", "")) or row.get("alert_type") == "BREAKOUT_LOW_BREACH_RISK_ALERT"])
    write_csv(audit / "execution_ack_log.csv", read_jsonl(paths["manual_acknowledgements"]))
    return {"status": "morita_notification_cycle_completed", "emitted_alert_count": len([row for row in emitted if row.get("delivery_status") != "duplicate_suppressed"]), "suppressed_duplicate_count": len([row for row in emitted if row.get("delivery_status") == "duplicate_suppressed"])}


def register_setup(entry: dict[str, Any], spec: dict[str, Any] | None = None) -> dict[str, Any]:
    from .time_stop_engine import freeze_setup_snapshot

    spec = spec or load_spec()
    convention = verify_baseline_timeout_convention(spec)
    paths = state_paths(spec)
    existing = read_jsonl(paths["setup_registry"])
    setup_id = str(entry["setup_id"])
    if setup_id in {str(row.get("setup_id")) for row in existing}:
        raise SystemExit("duplicate_setup_id")
    frozen = freeze_setup_snapshot(entry, spec, convention)
    append_jsonl(paths["setup_registry"], frozen)
    return {"status": "live_setup_registered", "setup_id": setup_id, "progress_target_price": frozen["progress_target_price"], "max_holding_sessions": frozen["max_holding_sessions"]}


def acknowledge_exit(setup_id: str, reason: str, note: str = "", source: str = "manual") -> dict[str, Any]:
    from .notification_state_machine import ALLOWED_ACK_REASONS

    if reason not in ALLOWED_ACK_REASONS:
        raise SystemExit("invalid_ack_reason")
    paths = state_paths()
    row = {"setup_id": setup_id, "reason": reason, "note": note, "source": source, "acknowledged_at_utc": utc_now(), "automatic_order": False}
    append_jsonl(paths["manual_acknowledgements"], row)
    alert = {
        "alert_id": f"ack_{setup_id}_{reason}",
        "setup_id": setup_id,
        "alert_type": "EXIT_ACKNOWLEDGED",
        "alert_title": "[EXIT ACKNOWLEDGED]",
        "reason": reason,
        "source": source,
        "remaining_position": "",
        "exchange_session_date": "",
        "state_transition_version": "morita_notification_v2",
        "notification_only": True,
        "automatic_order": False,
    }
    existing = read_jsonl(paths["alert_events"])
    record_alert(paths["alert_events"], existing, alert)
    return {"status": "exit_acknowledged", "setup_id": setup_id, "reason": reason, "source": source}
