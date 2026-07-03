from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import morita_portfolio_ledger_v1 as m


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "history"
    monkeypatch.setattr(m, "HISTORY_ROOT", root)
    monkeypatch.setattr(m, "PHASE16B_OUTPUT", tmp_path / "phase16b")
    m.init_local_templates()
    return root


def _fixture_dir(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture"
    _write_csv(
        fixture / "account_snapshots.csv",
        [
            {
                "as_of_timestamp_utc": "2026-01-02T21:00:00Z",
                "broker_account_ref_hash": "acct_hash",
                "account_type": "cash",
                "base_currency": "USD",
                "net_liquidation_value": "10000",
                "cash_balance": "8000",
                "buying_power": "8000",
                "margin_used": "0",
                "unrealized_pnl": "0",
                "realized_pnl": "0",
                "source_snapshot_id_hash": "snap1",
                "source_payload_hash": "payload1",
                "availability_status": "available",
            }
        ],
        m.ACCOUNT_COLUMNS,
    )
    _write_csv(
        fixture / "position_snapshots.csv",
        [
            {
                "as_of_timestamp_utc": "2026-01-02T21:00:00Z",
                "broker_account_ref_hash": "acct_hash",
                "broker_position_ref_hash": "pos1",
                "instrument_type": "option",
                "underlying_symbol": "NVDA",
                "option_contract_ref_hash": "contract1",
                "option_expiration_date": "2026-03-20",
                "option_right": "CALL",
                "option_strike": "150",
                "quantity": "1",
                "average_open_price": "2.5",
                "mark_price": "2.6",
                "market_value": "260",
                "unrealized_pnl": "10",
                "currency": "USD",
                "position_status": "open",
                "source_snapshot_id_hash": "snap1",
                "source_payload_hash": "payload2",
                "availability_status": "available",
            }
        ],
        m.POSITION_COLUMNS,
    )
    _write_csv(
        fixture / "order_fill_events.csv",
        [
            {
                "broker_order_ref_hash": "order1",
                "broker_fill_ref_hash": "fill1",
                "submitted_timestamp_utc": "2026-01-02T15:00:00Z",
                "updated_timestamp_utc": "2026-01-02T15:05:00Z",
                "fill_timestamp_utc": "2026-01-02T15:05:00Z",
                "order_status": "filled",
                "side": "BUY",
                "instrument_type": "option",
                "underlying_symbol": "NVDA",
                "option_contract_ref_hash": "contract1",
                "option_expiration_date": "2026-03-20",
                "option_right": "CALL",
                "option_strike": "150",
                "quantity_requested": "1",
                "filled_quantity": "1",
                "fill_price": "2.5",
                "average_fill_price": "2.5",
                "fees": "0",
                "limit_price": "2.6",
                "stop_price": "",
                "time_in_force": "DAY",
                "order_type": "LIMIT",
                "source_snapshot_id_hash": "snap1",
                "source_payload_hash": "payload3",
            }
        ],
        m.ORDER_FILL_COLUMNS,
    )
    return fixture


def _signal_intent_files(tmp_path: Path) -> tuple[Path, Path]:
    signal = tmp_path / "signals.csv"
    intent = tmp_path / "intents.csv"
    _write_csv(
        signal,
        [
            {
                "signal_id": "sig1",
                "signal_timestamp_utc": "2026-01-02T14:30:00Z",
                "signal_date": "2026-01-02",
                "underlying_symbol": "NVDA",
                "signal_rank": "S",
                "strategy_family": "Breakout Momentum",
                "signal_source_version": "test",
                "theme": "AI Infrastructure",
                "planned_instrument_type": "option",
                "planned_option_right": "CALL",
                "planned_expiry_date": "2026-03-20",
                "planned_strike_or_delta_target": "Delta0.6",
                "planned_dte_min": "60",
                "planned_dte_max": "90",
                "planned_max_premium_at_risk": "300",
                "planned_premium_at_risk_unit": "USD",
                "planned_entry_rule": "manual_check",
                "planned_profit_rule": "tp",
                "planned_stop_rule": "sl",
                "planned_timeout_rule": "timeout",
                "notes": "",
            }
        ],
        m.SIGNAL_COLUMNS,
    )
    _write_csv(
        intent,
        [
            {
                "intent_id": "intent1",
                "signal_id": "sig1",
                "intent_created_timestamp_utc": "2026-01-02T14:45:00Z",
                "intent_status": "filled",
                "underlying_symbol": "NVDA",
                "planned_instrument_type": "option",
                "planned_option_right": "CALL",
                "planned_expiry_date": "2026-03-20",
                "planned_strike_or_delta_target": "Delta0.6",
                "planned_dte_min": "60",
                "planned_dte_max": "90",
                "planned_contract_multiplier": "100",
                "planned_quantity": "1",
                "planned_limit_or_max_price": "2.6",
                "planned_max_premium_at_risk": "300",
                "planned_premium_at_risk_unit": "USD",
                "manual_execution_confirmation_required": "true",
                "notes": "",
            }
        ],
        m.INTENT_COLUMNS,
    )
    return signal, intent


def test_no_live_order_or_arbitrary_endpoint_methods_exist() -> None:
    names = set(dir(m.BrokerReadOnlyAdapter)) | set(dir(m.WebullOfficialReadOnlyAdapter))
    forbidden = {"submit_order", "cancel_order", "replace_order", "amend_order", "exercise_option", "transfer_cash", "request", "call_endpoint", "generic_endpoint"}
    assert not (names & forbidden)
    text = (REPO_ROOT / "morita_portfolio_ledger_v1.py").read_text(encoding="utf-8").lower()
    assert "requests." not in text
    assert "selenium" not in text
    assert "playwright" not in text


def test_webull_unknown_onboarding_blocks_real_sync_and_no_watermark(isolated: Path) -> None:
    result = m.sync_webull_read_only("local")
    assert result["status"] == "webull_api_read_only_sync_blocked"
    assert "official_api_account_eligibility_unknown" in result["blockers"]
    assert not (isolated / "broker_sync" / "watermarks" / "latest_successful_sync.json").exists()


def test_webull_audit_records_official_capture_without_unlocking_sync(isolated: Path) -> None:
    raw = isolated / "onboarding" / "official_docs_raw" / "webull_sdk_docs.html"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        "Webull provides official SDKs ApiClient webull.core.client TradeClient webull.trade.trade_client "
        "TradeClientV2 get_account_list Place, modify, and cancel orders Order Events Individual clients",
        encoding="utf-8",
    )
    audit = m.audit_webull_official_docs()
    manifest = m.load_json(isolated / "onboarding" / "webull_official_docs_capture_manifest.json")
    assert audit["real_sync_allowed"] is False
    assert audit["observed_official_docs_facts"]["account_list_example_observed"] is True
    assert manifest["captures"][0]["sha256"] == m.file_sha256(raw)


def test_fixture_import_idempotent_and_schema_drift_fails_closed(isolated: Path, tmp_path: Path) -> None:
    fixture = _fixture_dir(tmp_path)
    first = m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(fixture), fixture, "broker_manual_import_completed")
    second = m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(fixture), fixture, "broker_manual_import_completed")
    assert first["status"] == "broker_manual_import_completed"
    assert second["merge_results"][2]["inserted_rows"] == 0
    assert (isolated / "broker_sync" / "watermarks" / "latest_successful_sync.json").exists()

    bad = tmp_path / "bad_fixture"
    bad.mkdir()
    (bad / "account_snapshots.csv").write_text("bad\n1\n", encoding="utf-8")
    _write_csv(bad / "position_snapshots.csv", [], m.POSITION_COLUMNS)
    _write_csv(bad / "order_fill_events.csv", [], m.ORDER_FILL_COLUMNS)
    result = m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(bad), bad, "broker_manual_import_completed")
    assert result["status"] == "broker_sync_schema_changed_fail_closed"


def test_signal_intent_validation_and_candidate_link(isolated: Path, tmp_path: Path) -> None:
    fixture = _fixture_dir(tmp_path)
    signal, intent = _signal_intent_files(tmp_path)
    m.import_morita_signals(signal)
    m.import_manual_order_intents(intent)
    m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(fixture), fixture, "broker_manual_import_completed")
    result = m.reconcile_morita_execution()
    assert result["monitoring_lot_count"] == 1
    lots = pd.read_csv(isolated / "manual_links" / "monitoring_lots.csv")
    assert lots.iloc[0]["linkage_status"] == "linked_rule_based_candidate"
    assert lots.iloc[0]["open_premium_cost_basis"] == 250.0

    bad_signal = tmp_path / "bad_signal.csv"
    rows = list(csv.DictReader(signal.open(newline="", encoding="utf-8")))
    rows[0]["signal_rank"] = "C"
    _write_csv(bad_signal, rows, m.SIGNAL_COLUMNS)
    with pytest.raises(SystemExit, match="invalid_signal_rank"):
        m.import_morita_signals(bad_signal)


def test_exact_link_beats_candidate_and_missing_basis_unavailable(isolated: Path, tmp_path: Path) -> None:
    fixture = _fixture_dir(tmp_path)
    fill_path = fixture / "order_fill_events.csv"
    rows = list(csv.DictReader(fill_path.open(newline="", encoding="utf-8")))
    rows[0]["intent_id"] = "intent1"
    rows[0]["average_fill_price"] = ""
    rows[0]["fill_price"] = ""
    _write_csv(fill_path, rows, m.ORDER_FILL_COLUMNS + ["intent_id"])
    signal, intent = _signal_intent_files(tmp_path)
    m.import_morita_signals(signal)
    m.import_manual_order_intents(intent)
    m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(fixture), fixture, "broker_manual_import_completed")
    m.reconcile_morita_execution()
    lots = pd.read_csv(isolated / "manual_links" / "monitoring_lots.csv")
    assert lots.iloc[0]["linkage_status"] == "linked_exact_intent_id"
    assert lots.iloc[0]["premium_at_risk_status"] == "unavailable"


def test_survival_ledger_concentration_drawdown_and_unconfigured_rank(isolated: Path, tmp_path: Path) -> None:
    fixture = _fixture_dir(tmp_path)
    signal, intent = _signal_intent_files(tmp_path)
    m.import_morita_signals(signal)
    m.import_manual_order_intents(intent)
    m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(fixture), fixture, "broker_manual_import_completed")
    m.reconcile_morita_execution()
    receipt, rows = m.build_survival_ledger("morita_survival_risk_policy_v1")
    row = rows[0]
    assert receipt["status"] == "portfolio_survival_ledger_completed"
    assert row["premium_at_risk_fraction_of_nav"] == pytest.approx(0.025)
    assert "rank_allocation_reference_unconfigured" in row["advisory_alert_codes"]
    assert "must buy" not in json.dumps(row).lower()


def test_execution_fidelity_checks_and_context_cannot_change_verdict(isolated: Path, tmp_path: Path) -> None:
    fixture = _fixture_dir(tmp_path)
    signal, intent = _signal_intent_files(tmp_path)
    m.import_morita_signals(signal)
    m.import_manual_order_intents(intent)
    m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(fixture), fixture, "broker_manual_import_completed")
    m.reconcile_morita_execution()
    receipt, rows_without = m.build_execution_fidelity_ledger("morita_execution_fidelity_policy_v1", include_context=False)
    assert receipt["status"] == "execution_fidelity_ledger_completed"
    assert rows_without[0]["execution_fidelity_status"] == "fidelity_review_required"
    assert rows_without[0]["regime_context_status"] == "not_requested"

    phase = tmp_path / "phase16b"
    _write_csv(
        phase / "cross_module_daily_panel.csv",
        [{"observation_date": "2026-01-02", "cta_consensus_category": "cta_mixed", "vol_change_consensus_category": "vol_mixed_or_unchanged", "combined_mechanical_sensitivity_ex_post_quartile": "etf_sensitivity_q4_ex_post", "combined_scale_status": "ok"}],
        ["observation_date", "cta_consensus_category", "vol_change_consensus_category", "combined_mechanical_sensitivity_ex_post_quartile", "combined_scale_status"],
    )
    _write_json(phase / "phase1_6b_cross_module_downside_receipt.json", {"run_status": "phase1_6b_cross_module_downside_completed", "actionization_allowed": False, "run_id": "ctx"})
    files = []
    for p in phase.rglob("*"):
        if p.is_file() and p.name != "phase1_6b_cross_module_downside_content_manifest.json":
            files.append({"relative_path": p.relative_to(phase).as_posix(), "sha256": m.file_sha256(p), "bytes": p.stat().st_size})
    _write_json(phase / "phase1_6b_cross_module_downside_content_manifest.json", {"files": files})
    receipt, rows_with = m.build_execution_fidelity_ledger("morita_execution_fidelity_policy_v1", include_context=True)
    assert rows_with[0]["regime_context_status"] == "available"
    assert rows_with[0]["execution_fidelity_status"] == rows_without[0]["execution_fidelity_status"]


def test_outcome_metrics_gate_and_distribution(isolated: Path, tmp_path: Path) -> None:
    m.ensure_local_roots()
    rows = []
    for i in range(30):
        rows.append(
            {
                "monitoring_lot_id": f"lot{i}",
                "monitoring_lot_status": "closed_documented",
                "open_premium_cost_basis": "100",
                "close_proceeds": str(80 if i < 10 else 140),
                "signal_rank": "S",
                "theme": "Software",
            }
        )
    _write_csv(isolated / "manual_links" / "monitoring_lots.csv", rows, list(rows[0].keys()))
    receipt, audit_rows = m.build_outcome_distribution_audit("morita_outcome_distribution_policy_v1")
    assert receipt["metrics_available"] is True
    assert audit_rows[0]["positive_return_rate"] == pytest.approx(20 / 30)
    assert audit_rows[0]["maximum_consecutive_negative_lot_run"] == 10

    _write_csv(isolated / "manual_links" / "monitoring_lots.csv", rows[:5], list(rows[0].keys()))
    _, audit_rows = m.build_outcome_distribution_audit("morita_outcome_distribution_policy_v1")
    assert audit_rows[0]["metrics_available"] is False
    assert audit_rows[0]["metrics_unavailable_reason"] == "closed_lot_count_below_minimum"


def test_daily_run_manifest_detects_tamper_and_roots_ignored(isolated: Path, tmp_path: Path) -> None:
    fixture = _fixture_dir(tmp_path)
    signal, intent = _signal_intent_files(tmp_path)
    m.import_morita_signals(signal)
    m.import_manual_order_intents(intent)
    m.import_broker_from_adapter(m.FixtureBrokerReadOnlyAdapter(fixture), fixture, "broker_manual_import_completed")
    receipt = m.build_daily_ledger_run("morita_survival_risk_policy_v1", "morita_execution_fidelity_policy_v1", "morita_outcome_distribution_policy_v1")
    run_dir = isolated / "daily_ledger_runs" / receipt["run_id"]
    assert m.verify_ledger_run(run_dir)["verification_status"] == "valid"
    (run_dir / "portfolio_survival_daily.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="ledger_content_manifest_invalid"):
        m.verify_ledger_run(run_dir)

    ignored = subprocess_run(["git", "check-ignore", "market_bomb_history/morita_portfolio_ledger_v1/placeholder.txt"])
    assert ignored == 0


def subprocess_run(cmd: list[str]) -> int:
    import subprocess

    return subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True).returncode
