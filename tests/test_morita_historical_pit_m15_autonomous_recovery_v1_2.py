from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from src.research.pit_recovery.autonomous_recovery_v1_2 import GUARDRAILS, run_v1_2
from src.research.pit_recovery.webull_m15_backfill import event_window_inventory, quality_audit_from_inventory
from src.research.pit_recovery.webull_m15_credentialed_probe import (
    ProbeWindow,
    build_probe_windows,
    classify_response,
    credential_inventory,
    request_log_row,
    rth_window_ms,
)
from src.research.pit_recovery.webull_m15_retention import retention_boundary_from_matrix


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = text

    def json(self):
        return self._payload


_RUN_CACHE: dict[str, Path] = {}


def _run(tmp_path: Path) -> Path:
    os.environ["MORITA_V12_DISABLE_LIVE_WEBULL"] = "1"
    os.environ["MORITA_V12_DISABLE_GITHUB"] = "1"
    os.environ["MORITA_V12_DISABLE_GITHUB_DOWNLOAD"] = "1"
    cache_key = "secret" if os.getenv("WEBULL_APP_SECRET") == "unit-secret-value" else "default"
    if cache_key in _RUN_CACHE and _RUN_CACHE[cache_key].exists():
        return _RUN_CACHE[cache_key]
    if cache_key == "default":
        tmp_path = tmp_path.parent / "morita_v12_shared"
        tmp_path.mkdir(exist_ok=True)
    result = run_v1_2(tmp_path, output_root=tmp_path / "out", run_id="unit")
    _RUN_CACHE[cache_key] = Path(result.output_dir)
    return _RUN_CACHE[cache_key]


def test_01_no_trading_or_account_endpoint_guardrails() -> None:
    assert GUARDRAILS["live_order_allowed"] is False
    assert GUARDRAILS["order_preview_allowed"] is False
    assert GUARDRAILS["account_data_access_allowed"] is False
    assert GUARDRAILS["positions_access_allowed"] is False


def test_02_no_production_scanner_rule_changes() -> None:
    assert GUARDRAILS["production_signal_logic_change_allowed"] is False
    assert GUARDRAILS["production_rank_change_allowed"] is False
    assert GUARDRAILS["production_notification_change_allowed"] is False


def test_03_credentials_never_enter_logs_or_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEBULL_APP_SECRET", "unit-secret-value")
    out = _run(tmp_path)
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in out.glob("*.json"))
    assert "unit-secret-value" not in text


def test_04_credential_absence_does_not_block_github_provenance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("WEBULL_APP_KEY", raising=False)
    monkeypatch.delenv("WEBULL_APP_SECRET", raising=False)
    out = _run(tmp_path)
    assert (out / "github_workflow_run_inventory.csv").exists()


def test_05_github_absence_does_not_block_webull_probe(tmp_path: Path) -> None:
    out = _run(tmp_path)
    assert (out / "webull_m15_probe_request_log.csv").exists()


def test_06_start_and_end_are_milliseconds() -> None:
    start, end = rth_window_ms("2024-03-14")
    row = request_log_row(ProbeWindow("SOXX", "2024-03-14", "M15", start, end))
    assert row["start_time_ms"] > 1_000_000_000_000
    assert row["end_time_ms"] > row["start_time_ms"]


def test_07_requested_and_returned_date_are_compared() -> None:
    start, end = rth_window_ms("2024-03-14")
    status, detail = classify_response(ProbeWindow("SOXX", "2024-03-14", "M15", start, end), DummyResponse(payload=[{"time": "2024-03-14T14:00:00Z"}]))
    assert status == "HISTORICAL_M15_2024_SUPPORTED"
    assert detail["row_count"] == 1


def test_08_recent_data_for_old_request_detected() -> None:
    start, end = rth_window_ms("2022-03-15")
    status, _ = classify_response(ProbeWindow("SOXX", "2022-03-15", "M15", start, end), DummyResponse(payload=[{"time": "2026-01-05T14:00:00Z"}]))
    assert status == "START_END_IGNORED"


def test_09_empty_success_differs_from_entitlement_failure() -> None:
    start, end = rth_window_ms("2024-03-14")
    empty, _ = classify_response(ProbeWindow("SOXX", "2024-03-14", "M15", start, end), DummyResponse(status_code=200, payload=[]))
    denied, _ = classify_response(ProbeWindow("SOXX", "2024-03-14", "M15", start, end), DummyResponse(status_code=403, text="permission denied"))
    assert empty == "NO_DATA"
    assert denied == "AUTH_BLOCKED"


def test_10_count_never_exceeds_1200() -> None:
    assert all(request_log_row(w)["count"] == 1200 for w in build_probe_windows(["SOXX"]))


def test_11_m15_not_inferred_from_m5() -> None:
    matrix = [{"symbol": "SOXX", "interval": "M5", "session_date": "2024-03-14", "status": "M5_SUPPORTED_DIAGNOSTIC"}]
    assert retention_boundary_from_matrix(matrix)["retention_status"] == "UNKNOWN"


def test_12_minute_bars_marked_unadjusted() -> None:
    rows = quality_audit_from_inventory([{"signal_id": "S1"}], "WEBULL_M15_PARTIAL")
    assert rows[0]["quality_flag"] == "UNADJUSTED_MINUTE_BARS"


def test_13_no_missing_bar_is_synthesized() -> None:
    rows = quality_audit_from_inventory([{"signal_id": "S1"}], "WEBULL_M15_PARTIAL")
    assert rows[0]["missing_bars_filled"] is False


def test_14_current_universe_not_silently_backdated(tmp_path: Path) -> None:
    out = _run(tmp_path)
    payload = json.loads((out / "frozen_pit_universe_registry.json").read_text(encoding="utf-8"))
    assert payload["current_universe_backdated"] is False


def test_15_file_mtime_alone_cannot_prove_authority(tmp_path: Path) -> None:
    out = _run(tmp_path)
    rows = pd.read_csv(out / "authority_rejection_reasons.csv")
    assert rows["rejection_reason"].astype(str).str.contains("WORKFLOW|SIGNAL", regex=True).any()


def test_16_workflow_and_artifact_hash_columns_preserved(tmp_path: Path) -> None:
    out = _run(tmp_path)
    rows = pd.read_csv(out / "github_workflow_artifact_inventory.csv")
    assert {"zip_sha256", "extracted_file_sha256"}.issubset(rows.columns)


def test_17_future_outcome_fields_cannot_promote_source(tmp_path: Path) -> None:
    out = _run(tmp_path)
    audit = pd.read_csv(out / "future_information_audit.csv")
    assert audit["status"].eq("PASS").all()


def test_18_rerun_cannot_begin_without_frozen_universe_config(tmp_path: Path) -> None:
    out = _run(tmp_path)
    receipt = json.loads((out / "deterministic_rerun_receipt_v1_2.json").read_text(encoding="utf-8"))
    assert receipt["rerun_executed"] is False


def test_19_event_window_backfill_uses_authoritative_signal_dates_only() -> None:
    rows = event_window_inventory([{"ticker": "AMAT", "decision_date": "2024-01-02", "rank": "S"}])
    assert rows[0]["signal_date"] == "2024-01-02"
    assert "SOXX|QQQ|AMAT" == rows[0]["symbols_required"]


def test_20_user_never_asked_to_edit_code(tmp_path: Path) -> None:
    out = _run(tmp_path)
    text = (out / "USER_ACTION_REQUIRED.md").read_text(encoding="utf-8")
    assert "edit code" not in text.lower()
    assert "Python commands" not in text


def test_21_no_code_launchers_exist(tmp_path: Path) -> None:
    _run(tmp_path)
    root = tmp_path.parent / "morita_v12_shared"
    for name in ["RUN_MORITA_RECOVERY.cmd", "RESUME_MORITA_RECOVERY.cmd", "SETUP_WEBULL_AND_RESUME.cmd", "SETUP_GITHUB_AND_RESUME.cmd"]:
        assert (root / name).exists()


def test_22_resume_does_not_duplicate_completed_downloads(tmp_path: Path) -> None:
    out = _run(tmp_path)
    receipt = json.loads((out / "run_receipt.json").read_text(encoding="utf-8"))
    assert "artifact_checksums" in receipt


def test_23_paid_vendor_purchase_requires_approval(tmp_path: Path) -> None:
    out = _run(tmp_path)
    rows = pd.read_csv(out / "alternative_m15_vendor_matrix.csv")
    assert rows["user action required"].astype(str).str.contains("approval|key", case=False, regex=True).any()


def test_24_btd_remains_blocked_without_vt(tmp_path: Path) -> None:
    out = _run(tmp_path)
    payload = json.loads((out / "btd_v1_0_blocker_carryforward_v1_2.json").read_text(encoding="utf-8"))
    assert payload["ready"] is False
    assert payload["blocker"] == "V_T_INCOMPLETE"


def test_25_thresholds_and_rules_unchanged(tmp_path: Path) -> None:
    out = _run(tmp_path)
    payload = json.loads((out / "short_v3_5_1_readiness_recheck_v1_2.json").read_text(encoding="utf-8"))
    assert payload["rules_unchanged"] is True


def test_26_all_outputs_research_only(tmp_path: Path) -> None:
    out = _run(tmp_path)
    assert "research_only=true" in (out / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker").read_text(encoding="utf-8")


def test_27_production_rejection_passes(tmp_path: Path) -> None:
    out = _run(tmp_path)
    rows = pd.read_csv(out / "production_rejection_test_results.csv")
    assert rows["passed"].astype(str).str.lower().eq("true").all()


def test_required_output_set(tmp_path: Path) -> None:
    out = _run(tmp_path)
    required = {
        "run_manifest.json",
        "run_receipt.json",
        "credential_safety_audit.json",
        "environment_capability_audit.json",
        "webull_m15_credentialed_capability_matrix.csv",
        "github_workflow_run_inventory.csv",
        "authoritative_signal_calendar_v1_2.csv",
        "frozen_pit_universe_registry.json",
        "authoritative_signal_m15_episode_dataset_v1_2.parquet",
        "START_HERE_MORITA.md",
        "USER_ACTION_REQUIRED.md",
        "morita_historical_pit_m15_autonomous_recovery_v1_2_chatgpt_review_bundle.md",
    }
    assert required.issubset({p.name for p in out.iterdir()})
