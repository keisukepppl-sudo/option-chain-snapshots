from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from src.morita_notification_v2 import ab_pullback_lifecycle as ab
from src.morita_notification_v2 import cycle
from src.morita_notification_v2 import notification_state_machine as sm
from src.morita_notification_v2 import time_stop_engine as ts
from src.morita_notification_v2 import webull_account_adapter as webull
from src.morita_notification_v2.weekly_report import build_weekly_rows


def spec(tmp_path: Path) -> dict:
    base = sm.load_spec()
    base["local_state"] = {
        "setup_registry": str(tmp_path / "live_setup_registry.jsonl"),
        "ab_candidate_registry": str(tmp_path / "ab_pullback_candidate_registry.jsonl"),
        "alert_events": str(tmp_path / "live_alert_events.jsonl"),
        "manual_acknowledgements": str(tmp_path / "manual_exit_acknowledgements.jsonl"),
        "audit_output_dir": str(tmp_path / "notification_audit"),
    }
    return base


def setup_payload(setup_id: str = "setup_1", route: str = "S_BREAKOUT", entry_source_type: str = "confirmed_webull_fill") -> dict:
    return {
        "setup_id": setup_id,
        "strategy_route": route,
        "base_breakout_id": "bb_1",
        "source_signal_id": "sig_1",
        "ticker": "NVDA",
        "rank_at_source_signal": "S" if route == "S_BREAKOUT" else "A",
        "accumulation_score_at_source_signal": 70,
        "signal_decision_date": "2026-01-01",
        "base_breakout_date": "2026-01-01",
        "entry_confirmed_at": "2026-01-02T14:30:00Z",
        "entry_exchange_trade_date": "2026-01-02",
        "entry_price_underlying": 100.0,
        "entry_price_source": "confirmed_webull_fill",
        "entry_source_type": entry_source_type,
        "current_status": "ACTIVE",
        "breakout_day_low_reference": 95.0,
    }


def sessions() -> list[str]:
    return [f"2026-01-{day:02d}" for day in range(2, 16)]


def market(high: float = 103.0, low: float = 96.0, close: float = 101.0, day: str = "2026-01-11") -> list[dict]:
    return [{"ticker": "NVDA", "exchange_session_date": day, "high": high, "low": low, "close": close, "source": "fixture_daily"}]


def test_no_broker_write_capability_exists():
    names = {name for name, _ in inspect.getmembers(webull.ReadOnlyWebullAccountAdapter, inspect.isfunction)}
    assert {"positions", "orders", "fills", "average_entry_price", "remaining_quantity", "symbol_mapping"}.issubset(names)
    assert not {"place_order", "modify_order", "cancel_order", "transfer_funds", "change_account_settings"} & names
    assert webull.ReadOnlyWebullAccountAdapter.broker_write_allowed is False


def test_confirmed_entry_freezes_route_target_and_timeout(tmp_path: Path):
    sp = spec(tmp_path)
    result = cycle.register_setup(setup_payload(), sp)
    assert result["progress_target_price"] == 105.0
    row = sm.read_jsonl(Path(sp["local_state"]["setup_registry"]))[0]
    assert row["max_holding_sessions"] == 10
    assert row["time_stop_rule_label"] == "ten_eligible_sessions_without_plus_5pct_progress"
    assert row["session_count_convention_source"] == "formal_baseline_timeout_convention"


def test_timer_cannot_start_from_scanner_or_buy_ready_alert(tmp_path: Path):
    with pytest.raises(ValueError):
        ts.freeze_setup_snapshot(setup_payload(entry_source_type="scanner_alert"), spec(tmp_path), sm.verify_baseline_timeout_convention())


def test_baseline_session_count_convention_is_mandatory():
    verified = sm.verify_baseline_timeout_convention()
    assert verified["outcome_window_sessions"] == 10
    bad = sm.load_spec()
    bad["baseline_required"]["outcome_window_sessions"] = 9
    with pytest.raises(SystemExit):
        sm.verify_baseline_timeout_convention(bad)


def test_s_breakout_low_breach_is_risk_alert_not_exit():
    setup = ts.freeze_setup_snapshot(setup_payload(), sm.load_spec(), sm.verify_baseline_timeout_convention())
    alert = ts.breakout_low_risk_alert(setup, 94.0, "fixture", "2026-01-05", 4, {"progress_status": "not_reached"}, "ON")
    assert alert["alert_type"] == "BREAKOUT_LOW_BREACH_RISK_ALERT"
    assert alert["risk_alert_only"] is True
    assert alert["automatic_order"] is False
    assert "not an automatic sell" in alert["message_footer"]


def test_raw_ab_rank_signal_cannot_create_buy_ready_when_rule_unresolved(tmp_path: Path):
    sp = spec(tmp_path)
    candidate = {"ticker": "MU", "rank": "A", "accumulation_score": 70, "source_signal_id": "s", "base_breakout_date": "2026-01-02"}
    state, event = ab.evaluate_ab_candidate(candidate, sp, [], [], "2026-01-10")
    assert state["state"] == "A_B_PULLBACK_RULE_UNRESOLVED"
    assert event is None


def test_ab_requires_rank_ab_accumulation_valid_base_and_20_sessions_when_rule_resolved(tmp_path: Path):
    sp = spec(tmp_path)
    sp["ab_pullback"]["rule_source_status"] = "resolved_committed_source"
    base = {
        "ticker": "MU", "rank": "A", "accumulation_score": 50, "source_signal_id": "s", "base_breakout_date": "2026-01-02",
        "valid_base_breakout_exists": True, "within_20_sessions": True, "first_eligible_pullback": True,
        "low_volume_adjustment_confirmed": True, "base_breakout_remains_valid": True, "rebound_confirmation_complete": True,
    }
    ok, reason = ab.validate_ab_route_gates(base, sp)
    assert ok and reason == "buy_ready"
    for key, value in [("rank", "S"), ("accumulation_score", 49), ("valid_base_breakout_exists", False), ("within_20_sessions", False)]:
        bad = dict(base)
        bad[key] = value
        assert ab.validate_ab_route_gates(bad, sp)[0] is False


def test_only_first_eligible_pullback_can_alert_and_locked_base_cannot_reopen(tmp_path: Path):
    sp = spec(tmp_path)
    sp["ab_pullback"]["rule_source_status"] = "resolved_committed_source"
    candidate = {
        "ticker": "MU", "rank": "A", "accumulation_score": 60, "source_signal_id": "s", "base_breakout_date": "2026-01-02",
        "valid_base_breakout_exists": True, "within_20_sessions": True, "first_eligible_pullback": True,
        "low_volume_adjustment_confirmed": True, "base_breakout_remains_valid": True, "rebound_confirmation_complete": True,
    }
    state, event = ab.evaluate_ab_candidate(candidate, sp, [], [], "2026-01-10")
    assert state["state"] == "BUY_READY_ALERTED"
    assert event and event["alert_type"] == "AB_PULLBACK_BUY_READY"
    state2, event2 = ab.evaluate_ab_candidate(candidate, sp, [state], [event], "2026-01-11")
    assert state2["state"] == "BUY_ALERT_EXPIRED_NO_CHASE"
    assert event2 is None


def test_no_intraday_premature_rebound_alert_and_expired_no_chase():
    sp = sm.load_spec()
    sp["ab_pullback"]["rule_source_status"] = "resolved_committed_source"
    candidate = {"ticker": "MU", "rank": "A", "accumulation_score": 60, "source_signal_id": "s", "base_breakout_date": "2026-01-02", "valid_base_breakout_exists": True, "within_20_sessions": True, "first_eligible_pullback": True, "low_volume_adjustment_confirmed": True, "base_breakout_remains_valid": True, "rebound_confirmation_complete": False}
    assert ab.validate_ab_route_gates(candidate, sp)[0] is False
    expired = ab.expired_no_chase_event({"candidate_id": "c1", "base_breakout_id": "bb1", "ticker": "MU"}, "2026-01-12")
    assert expired["alert_type"] == "AB_ALERT_EXPIRED_NO_CHASE"
    assert expired["automatic_order"] is False


def test_reminders_at_sessions_8_9_10_and_target_met_suppresses_exit(tmp_path: Path):
    sp = spec(tmp_path)
    setup = ts.freeze_setup_snapshot(setup_payload(), sp, sm.verify_baseline_timeout_convention(sp))
    assert ts.time_stop_alert_for_setup(setup, sessions(), "2026-01-09", market(day="2026-01-09"), "OFF")["alert_type"] == "TIME_STOP_IN_2_SESSIONS"
    assert ts.time_stop_alert_for_setup(setup, sessions(), "2026-01-10", market(day="2026-01-10"), "OFF")["alert_type"] == "TIME_STOP_TOMORROW"
    assert ts.time_stop_alert_for_setup(setup, sessions(), "2026-01-11", market(day="2026-01-11"), "OFF")["alert_type"] == "EXIT_TODAY_10_SESSION_TIME_STOP"
    assert ts.time_stop_alert_for_setup(setup, sessions(), "2026-01-11", market(high=106, day="2026-01-11"), "OFF") is None


def test_missing_market_data_cannot_create_false_time_stop(tmp_path: Path):
    setup = ts.freeze_setup_snapshot(setup_payload(), spec(tmp_path), sm.verify_baseline_timeout_convention())
    alert = ts.time_stop_alert_for_setup(setup, sessions(), "2026-01-11", [], "UNAVAILABLE")
    assert alert["alert_type"] == "TIME_STOP_PROGRESS_UNKNOWN"
    assert alert["progress_status"] == "unknown_market_data"
    assert alert["required_action"] == "monitor; no automatic order"


def test_exit_alerts_are_idempotent_and_acknowledgement_suppresses_repeats(tmp_path: Path):
    sp = spec(tmp_path)
    cycle.register_setup(setup_payload(), sp)
    result1 = cycle.run_notification_cycle("2026-01-11", sessions(), market(day="2026-01-11"), [], sp)
    result2 = cycle.run_notification_cycle("2026-01-11", sessions(), market(day="2026-01-11"), [], sp)
    assert result1["emitted_alert_count"] >= 1
    assert result2["emitted_alert_count"] == 0
    cycle.acknowledge_exit("setup_1", "time_stop", "closed", "manual")
    result3 = cycle.run_notification_cycle("2026-01-11", sessions(), market(day="2026-01-11"), [], sp)
    assert result3["emitted_alert_count"] == 0


def test_incomplete_broker_data_cannot_fake_closure(tmp_path: Path):
    adapter = webull.ReadOnlyWebullAccountAdapter(positions_path=tmp_path / "missing.jsonl")
    assert adapter.remaining_quantity("NVDA") is None
    assert adapter.average_entry_price("NVDA") is None


def test_narrow_leadership_changes_display_and_sleeve_caution_only():
    sp = sm.load_spec()
    alert = ts.s_breakout_buy_ready_alert({"candidate_id": "c", "ticker": "NVDA", "breakout_day_low_reference": 95}, "2026-01-02", "ON", sp)
    assert alert["narrow_leadership_status"] == "ON"
    assert alert["suggested_premium_sleeve_pct"] == 30
    assert alert["fifty_pct_exception_available"] is False
    ab_event = {"suggested_premium_sleeve_pct": sp["ab_pullback"]["suggested_premium_sleeve_pct"], "narrow_leadership_status": "ON"}
    assert ab_event["suggested_premium_sleeve_pct"] == 10


def test_duplicate_setup_ids_rejected_but_multiple_tickers_distinct(tmp_path: Path):
    sp = spec(tmp_path)
    cycle.register_setup(setup_payload("same"), sp)
    with pytest.raises(SystemExit):
        cycle.register_setup(setup_payload("same"), sp)
    other = setup_payload("other")
    other["ticker"] = "AMD"
    assert cycle.register_setup(other, sp)["setup_id"] == "other"


def test_weekly_report_separates_strategy_notification_compliance_and_sync():
    rows = build_weekly_rows(
        [{"rank": "A", "state": "A_B_PULLBACK_RULE_UNRESOLVED"}],
        [{"alert_type": "EXIT_TODAY_10_SESSION_TIME_STOP"}],
        [{"strategy_route": "S_BREAKOUT", "current_status": "ACTIVE"}],
        [{"reason": "broker_sync_unavailable"}],
    )
    ts_row = [row for row in rows if row["section"] == "time_stop_discipline"][0]
    assert ts_row["bot_setup_performance"] == "separate_from_notification_correctness"
    assert ts_row["notification_correctness"] == "event_log_based"
    assert ts_row["user_execution_compliance"] == "acknowledgement_based"
    assert ts_row["webull_synchronization_quality"] == "read_only_or_manual"


def test_credentials_account_ids_cannot_enter_committed_outputs():
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in [
        Path("config/morita_notification_v2/ab_pullback_and_time_stop_spec.json"),
        Path("docs/morita_ab_pullback_and_time_stop_notification_v2.md"),
    ])
    forbidden = ["PUSHOVER_APP_TOKEN=", "WEBULL_PASSWORD", "account_id", "raw_order_id"]
    assert not any(token in text for token in forbidden)


def test_existing_bot_baseline_research_modules_are_not_imported_for_mutation():
    text = Path("src/morita_notification_v2/cycle.py").read_text(encoding="utf-8")
    assert "scan_universe" not in text
    assert "place_order" not in text
    assert "cancel_order" not in text
