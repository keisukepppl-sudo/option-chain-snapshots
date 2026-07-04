from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import scripts.build_morita_s_reconciliation_audit_v1 as audit


def synthetic_s() -> pd.DataFrame:
    rows = [
        {
            "signal_id": "s1",
            "underlying_symbol": "AAA",
            "signal_decision_date": "2024-01-02",
            "entry_session": "2024-01-03",
            "signal_rank": "S",
            "production_adjusted_score": 60,
            "accumulation_score": 70,
            "prior_20d_high": 100,
            "outcome_status": "complete",
        },
        {
            "signal_id": "s2",
            "underlying_symbol": "AAA",
            "signal_decision_date": "2024-01-04",
            "entry_session": "2024-01-05",
            "signal_rank": "S",
            "production_adjusted_score": 61,
            "accumulation_score": 71,
            "prior_20d_high": 101,
            "outcome_status": "complete",
        },
        {
            "signal_id": "s3",
            "underlying_symbol": "BBB",
            "signal_decision_date": "2024-02-01",
            "entry_session": "2024-02-02",
            "signal_rank": "S",
            "production_adjusted_score": 62,
            "accumulation_score": 72,
            "prior_20d_high": 102,
            "outcome_status": "complete",
        },
    ]
    out = pd.DataFrame(rows)
    out["signal_date"] = pd.to_datetime(out["signal_decision_date"])
    out["entry_date_ts"] = pd.to_datetime(out["entry_session"])
    return out


def test_no_network_provider_access_code_exists() -> None:
    text = (REPO_ROOT / "scripts" / "build_morita_s_reconciliation_audit_v1.py").read_text(encoding="utf-8")
    forbidden = ["requests", "urllib", "yfinance", "download(", "api_key"]
    assert not any(token in text for token in forbidden)


def test_profit_factor_uses_single_return_convention() -> None:
    assert audit.profit_factor([125.0, -50.0, 25.0]) == 3.0
    stats = audit.return_summary([125.0, -50.0, 25.0])
    assert stats["gross_profit"] == 150.0
    assert stats["gross_loss"] == 50.0


def test_session_gap_repeat_and_same_day_classifications() -> None:
    sessions = list(pd.bdate_range("2024-01-01", periods=40))
    assert audit.session_gap("2024-01-03", "2024-01-05", sessions) == 2
    assert audit.classify_repeat(0, 0) == "same_day_duplicate"
    assert audit.classify_repeat(2, 2) == "within_20_session_repeat"
    assert audit.classify_repeat(40, 22) == "post_20_session_repeat"


def test_label_layer_does_not_alter_raw_formal_events() -> None:
    s = synthetic_s()
    before = s.copy(deep=True)
    sessions = list(pd.bdate_range("2024-01-01", periods=60))
    rows, layers = audit.label_layers(s, sessions)
    pd.testing.assert_frame_equal(s, before)
    assert "s1" in layers["cooldown"]
    assert "s2" not in layers["cooldown"]
    assert "s1" in layers["first"]
    assert "s2" not in layers["first"]
    row2 = [row for row in rows if row["formal_event_id"] == "s2"][0]
    assert row2["INTENDED_NEW_BASE_REENTRY_ONLY"] == "reject_new_base_unverifiable"


def test_no_new_base_label_without_point_in_time_base_id() -> None:
    s = synthetic_s()
    sessions = list(pd.bdate_range("2024-01-01", periods=60))
    rows, _ = audit.label_layers(s, sessions)
    assert all(row["new_base_evidence_status"] != "new_base_confirmed" for row in rows)


def test_formal_export_required_fields_present() -> None:
    rows = audit.export_formal_events(synthetic_s())
    required = {"formal_event_id", "ticker", "signal_date", "entry_date", "rank", "base_id_if_existing", "cooldown_flag_if_existing"}
    assert required.issubset(rows[0])


def test_car_rows_complete_for_fixture() -> None:
    s = synthetic_s()
    car = s.copy()
    car["underlying_symbol"] = "CAR"
    car["signal_decision_date"] = ["2026-04-07", "2026-04-08", "2026-04-09"]
    car["entry_session"] = ["2026-04-08", "2026-04-09", "2026-04-10"]
    car["signal_date"] = pd.to_datetime(car["signal_decision_date"])
    sessions = list(pd.bdate_range("2026-04-01", periods=30))
    repeats = audit.repeat_audit(car, sessions)
    rows = audit.car_case(car, repeats)
    assert len(rows) == 3
    assert all(row["new_base_objectively_formed"] == "unverifiable_with_current_artifacts" for row in rows)


def test_legacy_pf_unverified_without_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = tmp_path / "morita_old_pf_call_backtest.md"
    artifact.write_text("S rank PF 4.0 trades 20 single call TP125\n", encoding="utf-8")
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(audit, "DISCOVERY_EXTRA_ROOTS", [])
    rows, legacy, trades = audit.source_discovery()
    assert legacy[0]["reproducibility_status"] == "unverifiable_legacy_result"


def test_manifest_rejects_extra_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "OUT", tmp_path)
    for name in audit.REQUIRED_FILES:
        if name != "reconciliation_content_manifest.json":
            (tmp_path / name).write_text("x\n", encoding="utf-8")
    audit.build_manifest()
    assert audit.verify_manifest()["verified"] is True
    (tmp_path / "extra.csv").write_text("x\n", encoding="utf-8")
    assert audit.verify_manifest()["extra"] == ["extra.csv"]


def test_production_discrepancy_labels_are_traceable() -> None:
    md = audit.code_path_audit_markdown()
    allowed = {
        "confirmed_implementation_defect",
        "confirmed_semantic_difference",
        "unverified_due_to_missing_artifact",
        "no_difference_found",
    }
    assert any(label in md for label in allowed)
    assert "No code remediation is implemented" in md


def test_subperiod_boundaries_are_available_in_performance_table() -> None:
    s = synthetic_s()
    term = pd.DataFrame(
        {
            "signal_id": ["s1", "s2", "s3"],
            "reference_return": [125.0, -50.0, 25.0],
            "first_hit_125_date": ["2024-01-10", "", ""],
            "terminal_reason": ["max_holding_30_sessions", "day10_plus5_not_reached", "max_holding_30_sessions"],
        }
    )
    cov = pd.DataFrame({"signal_id": ["s1", "s2", "s3"], "status": ["eligible", "eligible", "eligible"]})
    layers = {"formal": {"s1", "s2", "s3"}, "cooldown": {"s1", "s3"}, "first": {"s1", "s3"}, "newbase": {"s1", "s3"}}
    _, annual = audit.performance_tables(s, term, cov, layers)
    labels = {row["subperiod"] for row in annual}
    assert {"2024", "2025", "2026_H1", "full_range"}.issubset(labels)
