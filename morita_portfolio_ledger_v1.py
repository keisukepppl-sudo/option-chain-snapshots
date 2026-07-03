from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
MODULE_NAME = "morita_portfolio_ledger_v1"
ARTIFACT_VERSION = "morita_portfolio_ledger_v1_0_0"
HISTORY_ROOT = REPO_ROOT / "market_bomb_history" / "morita_portfolio_ledger_v1"
CONFIG_ROOT = REPO_ROOT / "config" / "morita_portfolio_ledger_v1"
PHASE16B_OUTPUT = REPO_ROOT / "outputs" / "phase1_6b_cross_module_downside"

LOCAL_SUBDIRS = [
    "onboarding",
    "credentials",
    "signal_import",
    "order_intents",
    "exit_reasons",
    "broker_sync/raw_api_snapshots",
    "broker_sync/canonical_events",
    "broker_sync/sync_receipts",
    "broker_sync/watermarks",
    "manual_import",
    "manual_links",
    "regime_context_cache",
    "daily_ledger_runs",
]

ACCOUNT_COLUMNS = [
    "as_of_timestamp_utc",
    "broker_account_ref_hash",
    "account_type",
    "base_currency",
    "net_liquidation_value",
    "cash_balance",
    "buying_power",
    "margin_used",
    "unrealized_pnl",
    "realized_pnl",
    "source_snapshot_id_hash",
    "source_payload_hash",
    "availability_status",
]
POSITION_COLUMNS = [
    "as_of_timestamp_utc",
    "broker_account_ref_hash",
    "broker_position_ref_hash",
    "instrument_type",
    "underlying_symbol",
    "option_contract_ref_hash",
    "option_expiration_date",
    "option_right",
    "option_strike",
    "quantity",
    "average_open_price",
    "mark_price",
    "market_value",
    "unrealized_pnl",
    "currency",
    "position_status",
    "source_snapshot_id_hash",
    "source_payload_hash",
    "availability_status",
]
ORDER_FILL_COLUMNS = [
    "broker_order_ref_hash",
    "broker_fill_ref_hash",
    "submitted_timestamp_utc",
    "updated_timestamp_utc",
    "fill_timestamp_utc",
    "order_status",
    "side",
    "instrument_type",
    "underlying_symbol",
    "option_contract_ref_hash",
    "option_expiration_date",
    "option_right",
    "option_strike",
    "quantity_requested",
    "filled_quantity",
    "fill_price",
    "average_fill_price",
    "fees",
    "limit_price",
    "stop_price",
    "time_in_force",
    "order_type",
    "source_snapshot_id_hash",
    "source_payload_hash",
]
OPTIONAL_ORDER_LINK_COLUMNS = ["intent_id", "signal_id"]
SIGNAL_COLUMNS = [
    "signal_id",
    "signal_timestamp_utc",
    "signal_date",
    "underlying_symbol",
    "signal_rank",
    "strategy_family",
    "signal_source_version",
    "theme",
    "planned_instrument_type",
    "planned_option_right",
    "planned_expiry_date",
    "planned_strike_or_delta_target",
    "planned_dte_min",
    "planned_dte_max",
    "planned_max_premium_at_risk",
    "planned_premium_at_risk_unit",
    "planned_entry_rule",
    "planned_profit_rule",
    "planned_stop_rule",
    "planned_timeout_rule",
    "notes",
]
INTENT_COLUMNS = [
    "intent_id",
    "signal_id",
    "intent_created_timestamp_utc",
    "intent_status",
    "underlying_symbol",
    "planned_instrument_type",
    "planned_option_right",
    "planned_expiry_date",
    "planned_strike_or_delta_target",
    "planned_dte_min",
    "planned_dte_max",
    "planned_contract_multiplier",
    "planned_quantity",
    "planned_limit_or_max_price",
    "planned_max_premium_at_risk",
    "planned_premium_at_risk_unit",
    "manual_execution_confirmation_required",
    "notes",
]
EXIT_COLUMNS = [
    "exit_event_id",
    "monitoring_lot_id",
    "exit_timestamp_utc",
    "exit_reason",
    "exit_rule_version",
    "notes",
    "recorded_by",
    "recorded_timestamp_utc",
]

ALLOWED_RANKS = {"S", "A", "B"}
ALLOWED_INTENT_STATES = {"draft", "submitted_manually", "partially_filled", "filled", "cancelled_manually", "expired_unfilled", "superseded"}
ALLOWED_EXIT_REASONS = {"profit_target", "hard_stop", "breakout_day_low_breach", "timeout_10_sessions_under_threshold", "manual_discretion", "broker_or_corporate_action", "data_correction", "other_documented"}
SAFE_ADVISORY_CODES = {
    "survival_data_incomplete",
    "single_position_concentration_watch",
    "total_premium_risk_watch",
    "theme_concentration_watch",
    "underlying_concentration_watch",
    "same_expiry_concentration_watch",
    "drawdown_watch",
    "drawdown_critical",
    "rank_allocation_reference_unconfigured",
    "rank_allocation_drift_watch",
    "execution_review_required",
    "manual_link_required",
    "outcome_sample_insufficient",
}
FORBIDDEN_ADVICE_WORDS = {"must buy", "must sell", "do not trade", "close now", "buy now", "sell now"}


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def module_source_sha256() -> str:
    return file_sha256(Path(__file__))


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def git_status_label() -> str:
    try:
        status = subprocess.check_output(["git", "status", "--short"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"
    tracked = [line for line in status.splitlines() if line and not line.startswith("?? ")]
    return "clean_tracked_files" if not tracked else "tracked_files_modified"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id(prefix: str = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}{stamp}" if prefix else stamp


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def read_csv(path: Path, required: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        if required is not None:
            return pd.DataFrame(columns=required)
        raise SystemExit(f"missing_csv:{path}")
    df = pd.read_csv(path, dtype=str).fillna("")
    if required:
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise SystemExit(f"missing_required_column:{path.name}:{missing[0]}")
    return df


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def ensure_local_roots() -> None:
    for rel in LOCAL_SUBDIRS:
        (HISTORY_ROOT / rel).mkdir(parents=True, exist_ok=True)


def write_template_if_missing(path: Path, columns: list[str]) -> None:
    if not path.exists():
        write_csv(path, [], columns)


def init_local_templates() -> dict[str, Any]:
    ensure_local_roots()
    write_template_if_missing(HISTORY_ROOT / "signal_import" / "morita_signal_events.csv", SIGNAL_COLUMNS)
    write_template_if_missing(HISTORY_ROOT / "order_intents" / "morita_manual_order_intents.csv", INTENT_COLUMNS)
    write_template_if_missing(HISTORY_ROOT / "exit_reasons" / "morita_exit_reason_events.csv", EXIT_COLUMNS)
    for name, cols in {
        "account_snapshots.csv": ACCOUNT_COLUMNS,
        "position_snapshots.csv": POSITION_COLUMNS,
        "order_fill_events.csv": ORDER_FILL_COLUMNS,
    }.items():
        write_template_if_missing(HISTORY_ROOT / "manual_import" / name, cols)
    return status_payload("morita_portfolio_local_templates_ready")


def status_payload(status: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "research_only": True,
        "actionization_allowed": False,
        "live_order_submission_enabled": False,
        "not_a_trading_signal": True,
        "not_a_trade_execution_system": True,
        "not_a_broker_of_record": True,
        "not_tax_advice": True,
        "not_investment_advice": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }
    payload.update(extra)
    return payload


def default_receipt(status: str, **extra: Any) -> dict[str, Any]:
    payload = status_payload(
        status,
        created_at_utc=utc_now(),
        repository_commit_sha=git_head(),
        repository_commit_status=git_status_label(),
        module_source_sha256=module_source_sha256(),
        artifact_version=ARTIFACT_VERSION,
    )
    payload.update(extra)
    return payload


def validate_no_trading_advice(text: str) -> None:
    low = text.lower()
    for word in FORBIDDEN_ADVICE_WORDS:
        if word in low:
            raise SystemExit(f"forbidden_trading_command:{word}")


def numeric(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def hash_identifier(value: Any) -> str:
    if value is None or str(value) == "":
        return ""
    return text_hash(str(value))[:24]


def canonical_event_key(row: dict[str, Any], fallback_fields: list[str]) -> str:
    parts = [str(row.get(field, "")) for field in fallback_fields]
    if any(parts):
        return text_hash("|".join(parts))
    return text_hash(json_dumps(row))


class BrokerReadOnlyAdapter:
    def capability_check(self) -> dict[str, Any]:
        raise NotImplementedError

    def list_accounts(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_account_snapshot(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_balances(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_fills(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_instrument_metadata_if_officially_available(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class WebullOfficialReadOnlyAdapter(BrokerReadOnlyAdapter):
    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        self.audit_path = HISTORY_ROOT / "onboarding" / "webull_official_api_capability_audit.json"

    def capability_check(self) -> dict[str, Any]:
        if not self.audit_path.exists():
            return {
                "capability_status": "webull_api_docs_or_account_access_incomplete",
                "blockers": [
                    "official_api_account_eligibility_unknown",
                    "official_auth_flow_unknown",
                    "official_read_only_scope_unknown",
                    "official_endpoint_contract_unknown",
                    "official_option_position_coverage_unknown",
                    "official_option_order_or_fill_coverage_unknown",
                ],
            }
        audit = load_json(self.audit_path)
        blockers = [code for code in audit.get("stop_condition_codes", []) if code]
        return {"capability_status": "ready_for_read_only_sync" if not blockers else "webull_api_docs_or_account_access_incomplete", "blockers": blockers, "audit": audit}


class FixtureBrokerReadOnlyAdapter(BrokerReadOnlyAdapter):
    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir

    def capability_check(self) -> dict[str, Any]:
        return {"capability_status": "fixture_available", "blockers": []}

    def get_account_snapshot(self) -> list[dict[str, Any]]:
        return read_csv(self.fixture_dir / "account_snapshots.csv", ACCOUNT_COLUMNS).to_dict("records")

    def list_positions(self) -> list[dict[str, Any]]:
        return read_csv(self.fixture_dir / "position_snapshots.csv", POSITION_COLUMNS).to_dict("records")

    def list_orders(self) -> list[dict[str, Any]]:
        return read_csv(self.fixture_dir / "order_fill_events.csv", ORDER_FILL_COLUMNS).to_dict("records")

    def list_fills(self) -> list[dict[str, Any]]:
        return self.list_orders()


class ManualCsvBrokerAdapter(FixtureBrokerReadOnlyAdapter):
    pass


def copy_raw_fixture(input_dir: Path, sync_id: str) -> list[dict[str, Any]]:
    raw_dir = HISTORY_ROOT / "broker_sync" / "raw_api_snapshots" / sync_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in ["account_snapshots.csv", "position_snapshots.csv", "order_fill_events.csv"]:
        src = input_dir / name
        if src.exists():
            dst = raw_dir / name
            shutil.copy2(src, dst)
            copied.append({"relative_path": repo_relative(dst), "sha256": file_sha256(dst)})
    return copied


def merge_canonical(target: Path, rows: list[dict[str, Any]], columns: list[str], key_fields: list[str]) -> dict[str, Any]:
    existing = read_csv(target, columns) if target.exists() else pd.DataFrame(columns=columns)
    existing_rows = existing.to_dict("records")
    by_key = {canonical_event_key(row, key_fields): row for row in existing_rows}
    inserted = 0
    for row in rows:
        normalized = {col: row.get(col, "") for col in columns}
        if not normalized.get("source_payload_hash"):
            normalized["source_payload_hash"] = text_hash(json_dumps(normalized))
        key = canonical_event_key(normalized, key_fields)
        if key not in by_key:
            by_key[key] = normalized
            inserted += 1
    write_csv(target, list(by_key.values()), columns)
    return {"target": repo_relative(target), "existing_rows": len(existing_rows), "input_rows": len(rows), "inserted_rows": inserted, "total_rows": len(by_key)}


def import_broker_from_adapter(adapter: FixtureBrokerReadOnlyAdapter, source_dir: Path, status: str) -> dict[str, Any]:
    ensure_local_roots()
    sync_id = run_id("broker_sync_")
    cap = adapter.capability_check()
    if cap.get("blockers"):
        return write_sync_receipt(sync_id, status_payload("broker_sync_schema_changed_fail_closed", blockers=cap["blockers"]))
    try:
        accounts = adapter.get_account_snapshot()
        positions = adapter.list_positions()
        fills = adapter.list_fills()
    except SystemExit as exc:
        return write_sync_receipt(sync_id, status_payload("broker_sync_schema_changed_fail_closed", schema_error=str(exc), watermark_advanced=False))
    for rows, columns, label in [(accounts, ACCOUNT_COLUMNS, "account"), (positions, POSITION_COLUMNS, "position"), (fills, ORDER_FILL_COLUMNS, "fill")]:
        for row in rows:
            missing = [col for col in columns if col not in row]
            if missing:
                return write_sync_receipt(sync_id, status_payload("broker_sync_schema_changed_fail_closed", schema=label, missing_column=missing[0]))
    raw = copy_raw_fixture(source_dir, sync_id)
    canonical_dir = HISTORY_ROOT / "broker_sync" / "canonical_events"
    merge_results = [
        merge_canonical(canonical_dir / "account_snapshots.csv", accounts, ACCOUNT_COLUMNS, ["as_of_timestamp_utc", "broker_account_ref_hash", "source_snapshot_id_hash"]),
        merge_canonical(canonical_dir / "position_snapshots.csv", positions, POSITION_COLUMNS, ["as_of_timestamp_utc", "broker_position_ref_hash", "source_snapshot_id_hash"]),
        merge_canonical(canonical_dir / "order_fill_events.csv", fills, ORDER_FILL_COLUMNS + OPTIONAL_ORDER_LINK_COLUMNS, ["broker_order_ref_hash", "broker_fill_ref_hash", "fill_timestamp_utc"]),
    ]
    watermark = {"sync_id": sync_id, "updated_at_utc": utc_now(), "status": status}
    write_json(HISTORY_ROOT / "broker_sync" / "watermarks" / "latest_successful_sync.json", watermark)
    return write_sync_receipt(sync_id, default_receipt(status, raw_snapshots=raw, merge_results=merge_results, watermark_advanced=True))


def write_sync_receipt(sync_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    path = HISTORY_ROOT / "broker_sync" / "sync_receipts" / f"{sync_id}.json"
    write_json(path, receipt)
    return receipt


def sync_webull_read_only(profile_id: str, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    ensure_local_roots()
    adapter = WebullOfficialReadOnlyAdapter(profile_id)
    cap = adapter.capability_check()
    if cap.get("blockers"):
        receipt = default_receipt("webull_api_read_only_sync_blocked", profile_id=profile_id, since=since or "", until=until or "", capability_status=cap.get("capability_status"), blockers=cap.get("blockers"), watermark_advanced=False)
        write_sync_receipt(run_id("webull_blocked_"), receipt)
        return receipt
    receipt = default_receipt("webull_api_docs_or_account_access_incomplete", profile_id=profile_id, blocker="adapter_has_no_live_network_client_by_design", watermark_advanced=False)
    write_sync_receipt(run_id("webull_incomplete_"), receipt)
    return receipt


def backfill_webull_read_only(profile_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    return sync_webull_read_only(profile_id, since=start_date, until=end_date)


def validate_signal_import(df: pd.DataFrame) -> None:
    bad = sorted(set(df["signal_rank"]) - ALLOWED_RANKS)
    if bad:
        raise SystemExit(f"invalid_signal_rank:{bad[0]}")


def validate_intent_import(df: pd.DataFrame) -> None:
    bad = sorted(set(df["intent_status"]) - ALLOWED_INTENT_STATES)
    if bad:
        raise SystemExit(f"invalid_intent_status:{bad[0]}")


def validate_exit_import(df: pd.DataFrame) -> None:
    bad = sorted(set(df["exit_reason"]) - ALLOWED_EXIT_REASONS)
    if bad:
        raise SystemExit(f"invalid_exit_reason:{bad[0]}")


def import_morita_signals(path: Path) -> dict[str, Any]:
    ensure_local_roots()
    df = read_csv(path, SIGNAL_COLUMNS)
    validate_signal_import(df)
    target = HISTORY_ROOT / "signal_import" / "morita_signal_events.csv"
    result = merge_canonical(target, df.to_dict("records"), SIGNAL_COLUMNS, ["signal_id"])
    receipt = default_receipt("morita_signal_import_completed", source_file_hash=file_sha256(path), import_result=result)
    write_json(HISTORY_ROOT / "signal_import" / f"signal_import_receipt_{run_id()}.json", receipt)
    return receipt


def import_manual_order_intents(path: Path) -> dict[str, Any]:
    ensure_local_roots()
    df = read_csv(path, INTENT_COLUMNS)
    validate_intent_import(df)
    target = HISTORY_ROOT / "order_intents" / "morita_manual_order_intents.csv"
    result = merge_canonical(target, df.to_dict("records"), INTENT_COLUMNS, ["intent_id"])
    receipt = default_receipt("morita_manual_intent_import_completed", source_file_hash=file_sha256(path), import_result=result)
    write_json(HISTORY_ROOT / "order_intents" / f"intent_import_receipt_{run_id()}.json", receipt)
    return receipt


def import_exit_reasons(path: Path) -> dict[str, Any]:
    ensure_local_roots()
    df = read_csv(path, EXIT_COLUMNS)
    validate_exit_import(df)
    target = HISTORY_ROOT / "exit_reasons" / "morita_exit_reason_events.csv"
    result = merge_canonical(target, df.to_dict("records"), EXIT_COLUMNS, ["exit_event_id"])
    receipt = default_receipt("morita_exit_reason_import_completed", source_file_hash=file_sha256(path), import_result=result)
    write_json(HISTORY_ROOT / "exit_reasons" / f"exit_import_receipt_{run_id()}.json", receipt)
    return receipt


def latest_df(path: Path, columns: list[str]) -> pd.DataFrame:
    return read_csv(path, columns)


def canonical_paths() -> dict[str, Path]:
    return {
        "accounts": HISTORY_ROOT / "broker_sync" / "canonical_events" / "account_snapshots.csv",
        "positions": HISTORY_ROOT / "broker_sync" / "canonical_events" / "position_snapshots.csv",
        "fills": HISTORY_ROOT / "broker_sync" / "canonical_events" / "order_fill_events.csv",
        "signals": HISTORY_ROOT / "signal_import" / "morita_signal_events.csv",
        "intents": HISTORY_ROOT / "order_intents" / "morita_manual_order_intents.csv",
        "exits": HISTORY_ROOT / "exit_reasons" / "morita_exit_reason_events.csv",
    }


def dte_days(expiration: str, fill_ts: str) -> int | None:
    try:
        exp = datetime.fromisoformat(expiration).date()
        fill_date = datetime.fromisoformat(fill_ts.replace("Z", "+00:00")).date()
    except Exception:
        return None
    return (exp - fill_date).days


def first_nonempty(*values: Any) -> str:
    for value in values:
        if value is not None and str(value) != "":
            return str(value)
    return ""


def build_monitoring_lots() -> pd.DataFrame:
    paths = canonical_paths()
    fills = latest_df(paths["fills"], ORDER_FILL_COLUMNS)
    signals = latest_df(paths["signals"], SIGNAL_COLUMNS)
    intents = latest_df(paths["intents"], INTENT_COLUMNS)
    exits = latest_df(paths["exits"], EXIT_COLUMNS)
    signal_by_id = {row["signal_id"]: row for row in signals.to_dict("records") if row.get("signal_id")}
    intent_by_id = {row["intent_id"]: row for row in intents.to_dict("records") if row.get("intent_id")}
    exits_by_lot: dict[str, list[dict[str, Any]]] = {}
    for row in exits.to_dict("records"):
        exits_by_lot.setdefault(row.get("monitoring_lot_id", ""), []).append(row)
    lots = []
    for row in fills.to_dict("records"):
        if str(row.get("side", "")).upper() not in {"BUY", "BOT", "BTO"}:
            continue
        if str(row.get("instrument_type", "")).lower() not in {"option", "options"}:
            continue
        link = link_fill(row, signal_by_id, intent_by_id)
        qty = numeric(row.get("filled_quantity"))
        price = numeric(first_nonempty(row.get("average_fill_price"), row.get("fill_price")))
        multiplier = numeric(link.get("planned_contract_multiplier"))
        if qty is not None and price is not None and multiplier is not None:
            premium = abs(qty) * price * multiplier
            premium_status = "available"
        else:
            premium = ""
            premium_status = "unavailable"
        lot_id = "mlot_" + text_hash("|".join([row.get("broker_fill_ref_hash", ""), row.get("broker_order_ref_hash", ""), row.get("fill_timestamp_utc", "")]))[:24]
        exit_rows = exits_by_lot.get(lot_id, [])
        lots.append(
            {
                "monitoring_lot_id": lot_id,
                "source_fill_ref_hash": row.get("broker_fill_ref_hash", ""),
                "signal_id": link.get("signal_id", ""),
                "intent_id": link.get("intent_id", ""),
                "underlying_symbol": row.get("underlying_symbol", ""),
                "option_contract_ref_hash": row.get("option_contract_ref_hash", ""),
                "option_expiration_date": row.get("option_expiration_date", ""),
                "option_right": row.get("option_right", ""),
                "option_strike": row.get("option_strike", ""),
                "open_quantity": row.get("filled_quantity", ""),
                "open_premium_cost_basis": premium,
                "premium_at_risk_status": premium_status,
                "open_timestamp": row.get("fill_timestamp_utc", ""),
                "close_quantity": "",
                "close_proceeds": "",
                "closed_timestamp": exit_rows[0]["exit_timestamp_utc"] if exit_rows else "",
                "monitoring_lot_status": "closed_documented" if exit_rows else "open",
                "linkage_status": link["linkage_status"],
                "signal_rank": link.get("signal_rank", ""),
                "strategy_family": link.get("strategy_family", ""),
                "theme": link.get("theme", ""),
                "planned_dte_min": link.get("planned_dte_min", ""),
                "planned_dte_max": link.get("planned_dte_max", ""),
                "planned_option_right": link.get("planned_option_right", ""),
                "planned_max_premium_at_risk": link.get("planned_max_premium_at_risk", ""),
                "planned_entry_rule": link.get("planned_entry_rule", ""),
                "planned_profit_rule": link.get("planned_profit_rule", ""),
                "planned_stop_rule": link.get("planned_stop_rule", ""),
                "planned_timeout_rule": link.get("planned_timeout_rule", ""),
            }
        )
    return pd.DataFrame(lots)


def link_fill(fill: dict[str, Any], signals: dict[str, dict[str, Any]], intents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    explicit_intent = fill.get("intent_id", "")
    if explicit_intent and explicit_intent in intents:
        intent = intents[explicit_intent]
        sig = signals.get(intent.get("signal_id", ""), {})
        return merged_link("linked_exact_intent_id", sig, intent)
    explicit_signal = fill.get("signal_id", "")
    if explicit_signal and explicit_signal in signals:
        return merged_link("linked_exact_signal_id", signals[explicit_signal], {})
    candidates = []
    for intent in intents.values():
        if intent.get("underlying_symbol") != fill.get("underlying_symbol"):
            continue
        if intent.get("planned_option_right") and intent.get("planned_option_right") != fill.get("option_right"):
            continue
        if intent.get("planned_expiry_date") and intent.get("planned_expiry_date") != fill.get("option_expiration_date"):
            continue
        dte = dte_days(fill.get("option_expiration_date", ""), fill.get("fill_timestamp_utc", ""))
        dte_min = numeric(intent.get("planned_dte_min"))
        dte_max = numeric(intent.get("planned_dte_max"))
        if dte is not None and dte_min is not None and dte < dte_min:
            continue
        if dte is not None and dte_max is not None and dte > dte_max:
            continue
        candidates.append(intent)
    if len(candidates) == 1:
        intent = candidates[0]
        return merged_link("linked_rule_based_candidate", signals.get(intent.get("signal_id", ""), {}), intent)
    if len(candidates) > 1:
        return {"linkage_status": "ambiguous_signal_link"}
    return {"linkage_status": "manual_link_required"}


def merged_link(status: str, signal: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    out = {"linkage_status": status}
    out.update(signal)
    out.update(intent)
    return out


def reconcile_morita_execution() -> dict[str, Any]:
    ensure_local_roots()
    lots = build_monitoring_lots()
    path = HISTORY_ROOT / "manual_links" / "monitoring_lots.csv"
    cols = [
        "monitoring_lot_id",
        "source_fill_ref_hash",
        "signal_id",
        "intent_id",
        "underlying_symbol",
        "option_contract_ref_hash",
        "option_expiration_date",
        "option_right",
        "option_strike",
        "open_quantity",
        "open_premium_cost_basis",
        "premium_at_risk_status",
        "open_timestamp",
        "close_quantity",
        "close_proceeds",
        "closed_timestamp",
        "monitoring_lot_status",
        "linkage_status",
        "signal_rank",
        "strategy_family",
        "theme",
        "planned_dte_min",
        "planned_dte_max",
        "planned_option_right",
        "planned_max_premium_at_risk",
        "planned_entry_rule",
        "planned_profit_rule",
        "planned_stop_rule",
        "planned_timeout_rule",
    ]
    write_csv(path, lots.to_dict("records"), cols)
    return default_receipt("broker_sync_reconciliation_incomplete" if lots.empty or (lots["linkage_status"] != "linked_exact_intent_id").any() else "morita_execution_reconciliation_completed", monitoring_lot_count=len(lots), manual_link_required_count=int((lots.get("linkage_status", pd.Series(dtype=str)) == "manual_link_required").sum()) if not lots.empty else 0)


def latest_account_row() -> dict[str, Any]:
    df = latest_df(canonical_paths()["accounts"], ACCOUNT_COLUMNS)
    if df.empty:
        return {}
    return df.sort_values("as_of_timestamp_utc").iloc[-1].to_dict()


def load_policy(path: Path) -> dict[str, Any]:
    return load_json(path)


def policy_hash(path: Path) -> str:
    return file_sha256(path)


def build_survival_ledger(risk_policy_id: str, as_of: str | None = None, output_dir: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ensure_local_roots()
    policy_path = CONFIG_ROOT / "risk_policy_v1.json"
    policy = load_policy(policy_path)
    if policy.get("risk_policy_id") != risk_policy_id:
        raise SystemExit("unknown_risk_policy_id")
    account = latest_account_row()
    lots = read_csv(HISTORY_ROOT / "manual_links" / "monitoring_lots.csv") if (HISTORY_ROOT / "manual_links" / "monitoring_lots.csv").exists() else pd.DataFrame()
    nav = numeric(account.get("net_liquidation_value")) if account else None
    open_lots = lots[lots.get("monitoring_lot_status", pd.Series(dtype=str)) == "open"].copy() if not lots.empty else pd.DataFrame()
    premium_values = pd.to_numeric(open_lots.get("open_premium_cost_basis", pd.Series(dtype=str)), errors="coerce") if not open_lots.empty else pd.Series(dtype=float)
    total_premium = float(premium_values.sum()) if not premium_values.empty else 0.0
    advisory: list[str] = []
    if nav is None or nav <= 0:
        advisory.append("survival_data_incomplete")
    if policy.get("rank_reference_unit") == "UNSET_REQUIRED":
        advisory.append("rank_allocation_reference_unconfigured")
    premium_fraction = total_premium / nav if nav else ""
    if nav and premium_fraction != "" and premium_fraction >= float(policy.get("total_premium_risk_watch_fraction_of_nav", 0.25)):
        advisory.append("total_premium_risk_watch")
    drawdown = ""
    hwm = nav
    if nav is not None:
        accounts = latest_df(canonical_paths()["accounts"], ACCOUNT_COLUMNS)
        navs = pd.to_numeric(accounts["net_liquidation_value"], errors="coerce").dropna()
        if not navs.empty:
            hwm = float(navs.max())
            drawdown = (nav - hwm) / hwm if hwm else 0.0
            if drawdown <= -float(policy.get("drawdown_critical_fraction", 0.30)):
                advisory.append("drawdown_critical")
            elif drawdown <= -float(policy.get("drawdown_watch_fraction", 0.15)):
                advisory.append("drawdown_watch")
    row = {
        "as_of_timestamp_utc": as_of or utc_now(),
        "net_liquidation_value": account.get("net_liquidation_value", ""),
        "cash_balance": account.get("cash_balance", ""),
        "open_long_option_cost_basis_at_risk": total_premium,
        "open_long_call_cost_basis_at_risk": total_premium,
        "premium_at_risk_fraction_of_nav": premium_fraction,
        "single_position_max_premium_at_risk_fraction_of_nav": (float(premium_values.max()) / nav) if nav and not premium_values.empty else "",
        "single_underlying_premium_at_risk_fraction_of_nav": concentration_fraction(open_lots, "underlying_symbol", nav),
        "single_theme_premium_at_risk_fraction_of_nav": concentration_fraction(open_lots, "theme", nav),
        "same_expiry_week_premium_at_risk_fraction_of_nav": concentration_fraction(open_lots, "option_expiration_date", nav),
        "open_position_count": len(open_lots),
        "open_long_option_count": len(open_lots),
        "remaining_dte_distribution": "",
        "theme_concentration_distribution": distribution_json(open_lots, "theme"),
        "underlying_concentration_distribution": distribution_json(open_lots, "underlying_symbol"),
        "rank_concentration_distribution": distribution_json(open_lots, "signal_rank"),
        "daily_nav_drawdown_from_high_water_mark": drawdown,
        "current_drawdown_from_high_water_mark": drawdown,
        "risk_policy_status": "survival_review_required" if advisory else "survival_metrics_available",
        "advisory_alert_codes": ";".join(sorted(set(advisory))),
        "data_completeness_status": "incomplete" if "survival_data_incomplete" in advisory else "available",
        "research_only": True,
        "actionization_allowed": False,
        "live_order_submission_enabled": False,
    }
    validate_no_trading_advice(json_dumps(row))
    return default_receipt("portfolio_survival_ledger_completed", risk_policy_hash=policy_hash(policy_path), risk_policy_status=row["risk_policy_status"]), [row]


def distribution_json(df: pd.DataFrame, col: str) -> str:
    if df.empty or col not in df.columns:
        return "{}"
    return json.dumps(df[col].fillna("").replace("", "unknown").value_counts().to_dict(), sort_keys=True)


def concentration_fraction(df: pd.DataFrame, col: str, nav: float | None) -> Any:
    if df.empty or col not in df.columns or not nav:
        return ""
    work = df.copy()
    work["premium"] = pd.to_numeric(work.get("open_premium_cost_basis", ""), errors="coerce").fillna(0)
    grouped = work.groupby(col)["premium"].sum()
    return float(grouped.max() / nav) if not grouped.empty else ""


def context_for_date(date_text: str) -> dict[str, Any]:
    manifest = PHASE16B_OUTPUT / "phase1_6b_cross_module_downside_content_manifest.json"
    receipt = PHASE16B_OUTPUT / "phase1_6b_cross_module_downside_receipt.json"
    panel = PHASE16B_OUTPUT / "cross_module_daily_panel.csv"
    if not (manifest.exists() and receipt.exists() and panel.exists()):
        return {"regime_context_status": "unavailable"}
    if not verify_manifest(PHASE16B_OUTPUT, "phase1_6b_cross_module_downside_content_manifest.json"):
        return {"regime_context_status": "unavailable"}
    rec = load_json(receipt)
    if rec.get("run_status") != "phase1_6b_cross_module_downside_completed" or rec.get("actionization_allowed") is not False:
        return {"regime_context_status": "unavailable"}
    df = read_csv(panel)
    row = df[df["observation_date"] == date_text]
    if row.empty:
        return {"regime_context_status": "unavailable"}
    r = row.iloc[0].to_dict()
    return {
        "regime_context_status": "available",
        "cta_context_category": r.get("cta_consensus_category", ""),
        "vol_context_category": r.get("vol_change_consensus_category", ""),
        "etf_scale_context_category": r.get("combined_mechanical_sensitivity_ex_post_quartile", ""),
        "phase1_6b_context_source_run_id": rec.get("run_id", ""),
    }


def verify_manifest(root: Path, manifest_name: str) -> bool:
    try:
        manifest = load_json(root / manifest_name)
        expected = {entry["relative_path"]: entry["sha256"] for entry in manifest.get("files", [])}
        actual = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file() and p.name != manifest_name}
        for rel, sha in expected.items():
            if rel not in actual or file_sha256(actual[rel]) != sha:
                return False
        return not (set(actual) - set(expected))
    except Exception:
        return False


def build_execution_fidelity_ledger(execution_policy_id: str, include_context: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    policy_path = CONFIG_ROOT / "execution_policy_v1.json"
    policy = load_policy(policy_path)
    if policy.get("execution_policy_id") != execution_policy_id:
        raise SystemExit("unknown_execution_policy_id")
    reconcile_morita_execution()
    lots = read_csv(HISTORY_ROOT / "manual_links" / "monitoring_lots.csv")
    rows = []
    exit_events = read_csv(canonical_paths()["exits"], EXIT_COLUMNS)
    exit_by_lot = {r["monitoring_lot_id"]: r for r in exit_events.to_dict("records") if r.get("monitoring_lot_id")}
    signals = {r["signal_id"]: r for r in read_csv(canonical_paths()["signals"], SIGNAL_COLUMNS).to_dict("records") if r.get("signal_id")}
    intents = {r["intent_id"]: r for r in read_csv(canonical_paths()["intents"], INTENT_COLUMNS).to_dict("records") if r.get("intent_id")}
    for lot in lots.to_dict("records"):
        signal = signals.get(lot.get("signal_id", ""), {})
        intent = intents.get(lot.get("intent_id", ""), {})
        actual_dte = dte_days(lot.get("option_expiration_date", ""), lot.get("open_timestamp", ""))
        dte_min = numeric(lot.get("planned_dte_min"))
        dte_max = numeric(lot.get("planned_dte_max"))
        dte_ok = "" if actual_dte is None or dte_min is None or dte_max is None else dte_min <= actual_dte <= dte_max
        premium = numeric(lot.get("open_premium_cost_basis"))
        planned_premium = numeric(lot.get("planned_max_premium_at_risk"))
        premium_ok = "" if premium is None or planned_premium is None else premium <= planned_premium
        alerts = []
        if lot.get("linkage_status") not in {"linked_exact_intent_id", "linked_exact_signal_id"}:
            alerts.append("signal_link_missing")
        if dte_ok is False:
            alerts.append("dte_outside_plan")
        if lot.get("planned_option_right") and lot.get("option_right") != lot.get("planned_option_right"):
            alerts.append("option_right_outside_plan")
        if premium_ok is False:
            alerts.append("premium_risk_outside_plan")
        exit_row = exit_by_lot.get(lot.get("monitoring_lot_id", ""), {})
        if lot.get("monitoring_lot_status") != "open" and not exit_row:
            alerts.append("exit_reason_missing")
        date_key = (lot.get("open_timestamp", "")[:10] if lot.get("open_timestamp") else signal.get("signal_date", ""))
        context = context_for_date(date_key) if include_context else {"regime_context_status": "not_requested"}
        row = {
            "signal_id_hash": hash_identifier(lot.get("signal_id")),
            "intent_id_hash": hash_identifier(lot.get("intent_id")),
            "monitoring_lot_id_hash": hash_identifier(lot.get("monitoring_lot_id")),
            "signal_rank": lot.get("signal_rank", ""),
            "underlying_symbol": lot.get("underlying_symbol", ""),
            "strategy_family": lot.get("strategy_family", ""),
            "theme": lot.get("theme", ""),
            "signal_timestamp_utc": signal.get("signal_timestamp_utc", ""),
            "intent_timestamp_utc": intent.get("intent_created_timestamp_utc", ""),
            "first_fill_timestamp_utc": lot.get("open_timestamp", ""),
            "signal_to_intent_minutes": minutes_between(signal.get("signal_timestamp_utc", ""), intent.get("intent_created_timestamp_utc", "")),
            "intent_to_first_fill_minutes": minutes_between(intent.get("intent_created_timestamp_utc", ""), lot.get("open_timestamp", "")),
            "linkage_status": lot.get("linkage_status", ""),
            "planned_dte_band": f"{lot.get('planned_dte_min', '')}-{lot.get('planned_dte_max', '')}",
            "actual_dte_at_first_fill": actual_dte if actual_dte is not None else "",
            "dte_within_plan": dte_ok,
            "planned_option_right": lot.get("planned_option_right", ""),
            "actual_option_right": lot.get("option_right", ""),
            "option_right_within_plan": lot.get("option_right") == lot.get("planned_option_right") if lot.get("planned_option_right") else "",
            "planned_max_premium_at_risk": lot.get("planned_max_premium_at_risk", ""),
            "actual_initial_premium_at_risk": lot.get("open_premium_cost_basis", ""),
            "premium_at_risk_within_plan": premium_ok,
            "planned_entry_rule": lot.get("planned_entry_rule", ""),
            "planned_profit_rule": lot.get("planned_profit_rule", ""),
            "planned_stop_rule": lot.get("planned_stop_rule", ""),
            "planned_timeout_rule": lot.get("planned_timeout_rule", ""),
            "exit_fill_timestamp_utc": lot.get("closed_timestamp", ""),
            "holding_sessions": "",
            "exit_reason_status": "available" if exit_row else ("not_closed" if lot.get("monitoring_lot_status") == "open" else "missing"),
            "exit_reason": exit_row.get("exit_reason", ""),
            "execution_fidelity_status": "fidelity_review_required" if alerts else "fidelity_confirmed",
            "data_completeness_status": "incomplete" if alerts else "available",
            **context,
        }
        validate_no_trading_advice(json_dumps(row))
        rows.append(row)
    return default_receipt("execution_fidelity_ledger_completed", execution_policy_hash=policy_hash(policy_path), row_count=len(rows)), rows


def minutes_between(start: str, end: str) -> Any:
    if not start or not end:
        return ""
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except Exception:
        return ""
    return (e - s).total_seconds() / 60.0


def build_outcome_distribution_audit(outcome_policy_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    policy_path = CONFIG_ROOT / "outcome_distribution_policy_v1.json"
    policy = load_policy(policy_path)
    if policy.get("outcome_policy_id") != outcome_policy_id:
        raise SystemExit("unknown_outcome_policy_id")
    lots = read_csv(HISTORY_ROOT / "manual_links" / "monitoring_lots.csv") if (HISTORY_ROOT / "manual_links" / "monitoring_lots.csv").exists() else pd.DataFrame()
    closed = lots[lots.get("monitoring_lot_status", pd.Series(dtype=str)) == "closed_documented"].copy() if not lots.empty else pd.DataFrame()
    returns = pd.Series(dtype=float)
    if not closed.empty and "close_proceeds" in closed:
        cost = pd.to_numeric(closed.get("open_premium_cost_basis", ""), errors="coerce")
        proceeds = pd.to_numeric(closed.get("close_proceeds", ""), errors="coerce")
        returns = ((proceeds - cost) / cost).dropna()
    min_count = int(policy["minimum_closed_monitoring_lots_for_aggregate_metrics"])
    if len(returns) < min_count:
        row = {
            "scope": "aggregate",
            "closed_monitoring_lot_count": len(returns),
            "metrics_available": False,
            "metrics_unavailable_reason": "closed_lot_count_below_minimum",
            "research_only": True,
            "actionization_allowed": False,
        }
    else:
        positives = returns[returns > 0]
        negatives = returns[returns < 0]
        gross_profit = float(positives.sum())
        gross_loss = float(abs(negatives.sum()))
        row = {
            "scope": "aggregate",
            "closed_monitoring_lot_count": len(returns),
            "metrics_available": True,
            "metrics_unavailable_reason": "",
            "net_return_on_initial_premium_mean": float(returns.mean()),
            "net_return_on_initial_premium_median": float(returns.median()),
            "net_return_on_initial_premium_p10": float(returns.quantile(0.10)),
            "net_return_on_initial_premium_p25": float(returns.quantile(0.25)),
            "net_return_on_initial_premium_p75": float(returns.quantile(0.75)),
            "net_return_on_initial_premium_p90": float(returns.quantile(0.90)),
            "positive_return_rate": float((returns > 0).mean()),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss else "",
            "average_positive_return": float(positives.mean()) if not positives.empty else "",
            "average_negative_return": float(negatives.mean()) if not negatives.empty else "",
            "mean_to_median_gap": float(returns.mean() - returns.median()),
            "top_1_positive_profit_share": top_profit_share(positives, 1),
            "top_3_positive_profit_share": top_profit_share(positives, 3),
            "largest_positive_return": float(returns.max()),
            "largest_negative_return": float(returns.min()),
            "maximum_consecutive_negative_lot_run": max_negative_run(list(returns)),
            "rank_distribution": distribution_json(closed, "signal_rank"),
            "theme_distribution": distribution_json(closed, "theme"),
            "execution_fidelity_distribution": "",
            "research_only": True,
            "actionization_allowed": False,
        }
    return default_receipt("outcome_distribution_audit_completed", outcome_policy_hash=policy_hash(policy_path), metrics_available=row["metrics_available"]), [row]


def top_profit_share(positives: pd.Series, n: int) -> Any:
    if positives.empty or positives.sum() == 0:
        return ""
    return float(positives.sort_values(ascending=False).head(n).sum() / positives.sum())


def max_negative_run(values: list[float]) -> int:
    best = cur = 0
    for value in values:
        if value < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def build_content_manifest(root: Path, manifest_name: str = "ledger_content_manifest.json") -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != manifest_name:
            files.append({"relative_path": path.relative_to(root).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    manifest = {"artifact_version": ARTIFACT_VERSION, "module_name": MODULE_NAME, "files": files}
    write_json(root / manifest_name, manifest)
    return manifest


def verify_ledger_run(run_dir: Path) -> dict[str, Any]:
    if verify_manifest(run_dir, "ledger_content_manifest.json"):
        return {"verification_status": "valid"}
    raise SystemExit("ledger_content_manifest_invalid")


def build_daily_ledger_run(risk_policy_id: str, execution_policy_id: str, outcome_policy_id: str, include_context: bool = False) -> dict[str, Any]:
    ensure_local_roots()
    reconcile_morita_execution()
    rid = run_id("ledger_")
    out = HISTORY_ROOT / "daily_ledger_runs" / rid
    out.mkdir(parents=True, exist_ok=True)
    survival_receipt, survival_rows = build_survival_ledger(risk_policy_id, output_dir=out)
    fidelity_receipt, fidelity_rows = build_execution_fidelity_ledger(execution_policy_id, include_context)
    outcome_receipt, outcome_rows = build_outcome_distribution_audit(outcome_policy_id)
    write_json(out / "ledger_source_integrity_report.json", default_receipt("ledger_source_integrity_recorded"))
    write_json(out / "broker_sync_reference.json", {"canonical_root": repo_relative(HISTORY_ROOT / "broker_sync" / "canonical_events")})
    write_json(out / "signal_import_reference.json", {"signal_import": repo_relative(canonical_paths()["signals"])})
    write_json(out / "intent_import_reference.json", {"intent_import": repo_relative(canonical_paths()["intents"])})
    write_json(out / "regime_context_reference.json", {"phase1_6b_context_requested": include_context, "source": repo_relative(PHASE16B_OUTPUT)})
    write_csv(out / "reconciliation_summary.csv", [{"metric": "monitoring_lot_count", "value": len(fidelity_rows)}], ["metric", "value"])
    write_csv(out / "unmatched_fills.csv", [r for r in fidelity_rows if r.get("linkage_status") == "manual_link_required"], list(fidelity_rows[0].keys()) if fidelity_rows else ["linkage_status"])
    write_csv(out / "unexecuted_signals.csv", [], ["signal_id_hash", "status"])
    write_csv(out / "ambiguous_links.csv", [r for r in fidelity_rows if r.get("linkage_status") == "ambiguous_signal_link"], list(fidelity_rows[0].keys()) if fidelity_rows else ["linkage_status"])
    survival_cols = list(survival_rows[0].keys())
    write_csv(out / "portfolio_survival_daily.csv", survival_rows, survival_cols)
    write_md(out / "portfolio_survival_summary.md", "Portfolio survival ledger", survival_receipt)
    write_csv(out / "theme_concentration_audit.csv", concentration_rows("theme"), ["group", "premium_at_risk"])
    write_csv(out / "underlying_concentration_audit.csv", concentration_rows("underlying_symbol"), ["group", "premium_at_risk"])
    write_csv(out / "expiry_concentration_audit.csv", concentration_rows("option_expiration_date"), ["group", "premium_at_risk"])
    write_csv(out / "rank_allocation_audit.csv", [{"rank_allocation_status": "unconfigured_reference_unit"}], ["rank_allocation_status"])
    fidelity_cols = list(fidelity_rows[0].keys()) if fidelity_rows else ["execution_fidelity_status"]
    write_csv(out / "execution_fidelity_trade_audit.csv", fidelity_rows, fidelity_cols)
    write_md(out / "execution_fidelity_summary.md", "Execution fidelity ledger", fidelity_receipt)
    write_csv(out / "outcome_distribution_audit.csv", outcome_rows, list(outcome_rows[0].keys()))
    write_md(out / "outcome_distribution_summary.md", "Outcome distribution audit", outcome_receipt)
    receipt = default_receipt(
        "morita_daily_ledger_run_completed",
        run_id=rid,
        risk_policy_hash=policy_hash(CONFIG_ROOT / "risk_policy_v1.json"),
        execution_policy_hash=policy_hash(CONFIG_ROOT / "execution_policy_v1.json"),
        outcome_policy_hash=policy_hash(CONFIG_ROOT / "outcome_distribution_policy_v1.json"),
        broker_sync_manifest_hash="",
        signal_import_hash=file_sha256(canonical_paths()["signals"]) if canonical_paths()["signals"].exists() else "",
        intent_import_hash=file_sha256(canonical_paths()["intents"]) if canonical_paths()["intents"].exists() else "",
        regime_context_manifest_hash_if_used=file_sha256(PHASE16B_OUTPUT / "phase1_6b_cross_module_downside_content_manifest.json") if include_context and (PHASE16B_OUTPUT / "phase1_6b_cross_module_downside_content_manifest.json").exists() else "",
    )
    write_json(out / "ledger_run_receipt.json", receipt)
    build_content_manifest(out)
    return receipt


def concentration_rows(col: str) -> list[dict[str, Any]]:
    path = HISTORY_ROOT / "manual_links" / "monitoring_lots.csv"
    if not path.exists():
        return []
    df = read_csv(path)
    if df.empty or col not in df.columns:
        return []
    df["premium"] = pd.to_numeric(df.get("open_premium_cost_basis", ""), errors="coerce").fillna(0)
    return [{"group": str(k), "premium_at_risk": float(v)} for k, v in df.groupby(col)["premium"].sum().items()]


def write_md(path: Path, title: str, receipt: dict[str, Any]) -> None:
    text = f"# {title}\n\n- status: `{receipt.get('status')}`\n- research_only: `true`\n- actionization_allowed: `false`\n- live_order_submission_enabled: `false`\n\nNo trading command is generated.\n"
    validate_no_trading_advice(text)
    path.write_text(text, encoding="utf-8")


def audit_webull_official_docs(captured_status: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_local_roots()
    raw_doc = HISTORY_ROOT / "onboarding" / "official_docs_raw" / "webull_sdk_docs.html"
    captures: list[dict[str, Any]] = []
    observed: dict[str, Any] = {
        "sdk_page_fetched": False,
        "python_api_client_observed": False,
        "python_trade_client_observed": False,
        "java_trade_client_v2_observed": False,
        "account_list_example_observed": False,
        "official_docs_include_order_submission_capability": False,
        "official_docs_include_order_events_capability": False,
        "official_docs_include_individual_client_management_tool": False,
    }
    if raw_doc.exists():
        raw_text = raw_doc.read_text(encoding="utf-8", errors="ignore")
        observed = {
            "sdk_page_fetched": True,
            "python_api_client_observed": "ApiClient" in raw_text and ("webull.core.client" in raw_text or all(token in raw_text for token in ["webull", "core", "client"])),
            "python_trade_client_observed": "TradeClient" in raw_text and ("webull.trade.trade_client" in raw_text or "trade_client" in raw_text),
            "java_trade_client_v2_observed": "TradeClientV2" in raw_text,
            "account_list_example_observed": "get_account_list" in raw_text or "getAccountList" in raw_text,
            "official_docs_include_order_submission_capability": "Place, modify, and cancel orders" in raw_text,
            "official_docs_include_order_events_capability": "Order Events" in raw_text,
            "official_docs_include_individual_client_management_tool": "Individual clients" in raw_text,
        }
        captures.append(
            {
                "official_url": "https://developer.webull.co.jp/apis/docs/sdk",
                "local_path": repo_relative(raw_doc),
                "sha256": file_sha256(raw_doc),
                "bytes": raw_doc.stat().st_size,
                "file_created_at_utc": datetime.fromtimestamp(raw_doc.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_role": "official_webull_sdk_docs_snapshot",
            }
        )
    blockers = [
        "official_api_account_eligibility_unknown",
        "official_auth_flow_unknown",
        "official_read_only_scope_unknown",
        "official_endpoint_contract_unknown",
        "official_option_position_coverage_unknown",
        "official_option_order_or_fill_coverage_unknown",
    ]
    audit = {
        "audit_status": "webull_api_docs_or_account_access_incomplete",
        "official_docs_entrypoint": "developer.webull.co.jp/apis/docs/sdk",
        "captured_status": captured_status or {},
        "official_docs_captures": captures,
        "observed_official_docs_facts": observed,
        "japan_individual_account_eligibility": "unconfirmed",
        "authentication_process_and_token_lifecycle": "partial_sdk_page_mentions_signature_generation_and_token_management_but_lifecycle_unconfirmed",
        "official_sdk_package_identity": "partial_observed_official_sdk_page_python_and_java_clients" if observed["sdk_page_fetched"] else "unconfirmed",
        "account_balance_positions_orders_fills_availability": "partial_account_list_example_observed_other_contracts_unconfirmed" if observed["account_list_example_observed"] else "unconfirmed",
        "us_option_position_order_fill_coverage": "unconfirmed",
        "timestamp_timezone_semantics": "unconfirmed",
        "historical_retention_limits": "unconfirmed",
        "stop_condition_codes": blockers,
        "real_sync_allowed": False,
        "research_only": True,
        "actionization_allowed": False,
        "live_order_submission_enabled": False,
        "not_a_trading_signal": True,
        "not_a_trade_execution_system": True,
        "not_a_broker_of_record": True,
        "not_tax_advice": True,
        "not_investment_advice": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }
    write_json(HISTORY_ROOT / "onboarding" / "webull_official_api_capability_audit.json", audit)
    capture_lines = "\n".join(f"- `{c['local_path']}` sha256 `{c['sha256']}`" for c in captures) or "- No official raw capture file found."
    observed_lines = "\n".join(f"- {key}: `{value}`" for key, value in observed.items())
    md = (
        "# Webull Official API Capability Audit\n\n"
        "Status: `webull_api_docs_or_account_access_incomplete`\n\n"
        "Official documentation evidence was recorded, but account eligibility, read-only scope, full endpoint contracts, "
        "and U.S. option position/order/fill coverage remain unresolved. Real sync is blocked until all stop conditions "
        "are cleared from official Webull documentation and local account onboarding evidence.\n\n"
        "## Captures\n"
        f"{capture_lines}\n\n"
        "## Observed Facts\n"
        f"{observed_lines}\n\n"
        "## Active Stop Conditions\n"
        + "\n".join(f"- `{code}`" for code in blockers)
        + "\n"
    )
    (HISTORY_ROOT / "onboarding" / "webull_official_api_capability_audit.md").write_text(md, encoding="utf-8")
    write_json(HISTORY_ROOT / "onboarding" / "webull_official_docs_capture_manifest.json", {"captures": captures, "audit_hash": file_sha256(HISTORY_ROOT / "onboarding" / "webull_official_api_capability_audit.json")})
    return audit


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-local-templates")
    sub.add_parser("audit-webull-official-docs")
    s = sub.add_parser("sync-webull-read-only")
    s.add_argument("--profile-id", required=True)
    s.add_argument("--since")
    s.add_argument("--until")
    b = sub.add_parser("backfill-webull-read-only")
    b.add_argument("--profile-id", required=True)
    b.add_argument("--start-date", required=True)
    b.add_argument("--end-date", required=True)
    f = sub.add_parser("import-broker-fixture")
    f.add_argument("--fixture-dir", required=True)
    m = sub.add_parser("import-broker-csv-manual")
    m.add_argument("--input-dir", required=True)
    sig = sub.add_parser("import-morita-signals")
    sig.add_argument("--signal-file", required=True)
    intent = sub.add_parser("import-manual-order-intents")
    intent.add_argument("--intent-file", required=True)
    ex = sub.add_parser("import-exit-reasons")
    ex.add_argument("--exit-file", required=True)
    sub.add_parser("reconcile-morita-execution")
    surv = sub.add_parser("build-survival-ledger")
    surv.add_argument("--risk-policy-id", required=True)
    surv.add_argument("--as-of")
    fid = sub.add_parser("build-execution-fidelity-ledger")
    fid.add_argument("--execution-policy-id", required=True)
    out = sub.add_parser("build-outcome-distribution-audit")
    out.add_argument("--outcome-policy-id", required=True)
    daily = sub.add_parser("build-daily-ledger-run")
    daily.add_argument("--risk-policy-id", required=True)
    daily.add_argument("--execution-policy-id", required=True)
    daily.add_argument("--outcome-policy-id", required=True)
    daily.add_argument("--include-phase1-6b-context-if-valid", action="store_true")
    ver = sub.add_parser("verify-ledger-run")
    ver.add_argument("--run-dir", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.cmd == "init-local-templates":
        result = init_local_templates()
    elif args.cmd == "audit-webull-official-docs":
        result = audit_webull_official_docs()
    elif args.cmd == "sync-webull-read-only":
        result = sync_webull_read_only(args.profile_id, args.since, args.until)
    elif args.cmd == "backfill-webull-read-only":
        result = backfill_webull_read_only(args.profile_id, args.start_date, args.end_date)
    elif args.cmd == "import-broker-fixture":
        result = import_broker_from_adapter(FixtureBrokerReadOnlyAdapter(Path(args.fixture_dir)), Path(args.fixture_dir), "broker_manual_import_completed")
    elif args.cmd == "import-broker-csv-manual":
        result = import_broker_from_adapter(ManualCsvBrokerAdapter(Path(args.input_dir)), Path(args.input_dir), "broker_manual_import_completed")
    elif args.cmd == "import-morita-signals":
        result = import_morita_signals(Path(args.signal_file))
    elif args.cmd == "import-manual-order-intents":
        result = import_manual_order_intents(Path(args.intent_file))
    elif args.cmd == "import-exit-reasons":
        result = import_exit_reasons(Path(args.exit_file))
    elif args.cmd == "reconcile-morita-execution":
        result = reconcile_morita_execution()
    elif args.cmd == "build-survival-ledger":
        result, rows = build_survival_ledger(args.risk_policy_id, args.as_of)
        result["rows"] = rows
    elif args.cmd == "build-execution-fidelity-ledger":
        result, rows = build_execution_fidelity_ledger(args.execution_policy_id)
        result["rows"] = rows
    elif args.cmd == "build-outcome-distribution-audit":
        result, rows = build_outcome_distribution_audit(args.outcome_policy_id)
        result["rows"] = rows
    elif args.cmd == "build-daily-ledger-run":
        result = build_daily_ledger_run(args.risk_policy_id, args.execution_policy_id, args.outcome_policy_id, args.include_phase1_6b_context_if_valid)
    elif args.cmd == "verify-ledger-run":
        result = verify_ledger_run(Path(args.run_dir))
    else:
        raise SystemExit(f"unknown_command:{args.cmd}")
    print(json_dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
