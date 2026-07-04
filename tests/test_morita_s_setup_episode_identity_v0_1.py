from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_s_setup_episode_identity_v0_1 as m


def session_pos(n: int = 80) -> tuple[list[str], dict[str, int]]:
    dates = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=n)]
    return dates, {date: idx for idx, date in enumerate(dates)}


def s_fixture(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"signal_id": "s1", "ticker": "AAA", "underlying_symbol": "AAA", "signal_rank": "S", "signal_date": dates[0], "signal_decision_date": dates[0], "entry_date": dates[1], "entry_session": dates[1], "source_rule_config_hash": "cfg"},
            {"signal_id": "s2", "ticker": "AAA", "underlying_symbol": "AAA", "signal_rank": "S", "signal_date": dates[5], "signal_decision_date": dates[5], "entry_date": dates[6], "entry_session": dates[6], "source_rule_config_hash": "cfg"},
            {"signal_id": "s3", "ticker": "AAA", "underlying_symbol": "AAA", "signal_rank": "S", "signal_date": dates[40], "signal_decision_date": dates[40], "entry_date": dates[41], "entry_session": dates[41], "source_rule_config_hash": "cfg"},
        ]
    )


def test_state_classification_no_gap_rebreakout(monkeypatch) -> None:
    dates, pos = session_pos()
    monkeypatch.setattr(m, "baseline_receipt", lambda: {"repository_commit_sha": "test", "run_id": "run"})
    rows = m.build_state_rows(s_fixture(dates), pos)
    assert len(rows) == 3
    assert [r["setup_episode_classification"] for r in rows] == [
        "INITIAL_OBSERVED_BREAKOUT",
        "EXTENDED_NO_NEW_BASE",
        "UNRESOLVED",
    ]
    assert all(r["setup_episode_classification"] != "VALID_REBREAKOUT" for r in rows)


def test_first_observed_not_lifetime_confirmed(monkeypatch) -> None:
    dates, pos = session_pos()
    monkeypatch.setattr(m, "baseline_receipt", lambda: {"repository_commit_sha": "test", "run_id": "run"})
    row = m.build_state_rows(s_fixture(dates).head(1), pos)[0]
    assert row["setup_episode_classification"] == "INITIAL_OBSERVED_BREAKOUT"
    assert row["first_observed_in_available_history"] is True
    assert "not_lifetime_initial" in row["classification_reason_code"]


def test_setup_episode_id_stable() -> None:
    a = m.setup_episode_id("AAA", "2024-01-03")
    b = m.setup_episode_id("AAA", "2024-01-03")
    c = m.setup_episode_id("AAA", "2024-01-04")
    assert a == b
    assert a != c


def test_legacy_gate_fails_artifact_only() -> None:
    evidence = m.legacy_identity_evidence_rows()
    artifact = [r for r in evidence if r["evidence_id"] == "legacy_original_breakout_date_artifact"][0]
    assert artifact["recovery_outcome"] == "LEGACY_IDENTITY_ARTIFACT_ONLY"
    gate = m.legacy_reusability_gate_rows(evidence)
    assert any(row["passed"] is False for row in gate)
    assert all(row["legacy_identity_reused_for_current_state"] is False for row in gate)


def test_row_count_reconciles_and_summary() -> None:
    dates, pos = session_pos()
    rows = m.build_state_rows(s_fixture(dates), pos)
    summary = m.classification_summary(rows)
    assert sum(row["raw_s_event_count"] for row in summary) == len(rows)


def test_manifest_rejects_extra(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUT", tmp_path)
    for name in m.REQUIRED_OUTPUTS:
        if name != "setup_episode_content_manifest.json":
            (tmp_path / name).write_text("x\n", encoding="utf-8")
    m.build_manifest()
    assert m.verify_manifest()["verified"] is True
    (tmp_path / "extra.csv").write_text("x\n", encoding="utf-8")
    assert m.verify_manifest()["extra"] == ["extra.csv"]


def test_guard_blocks_unstratified_language() -> None:
    text = (REPO_ROOT / "docs" / "morita_s_raw_event_aggregation_guard_v1.md").read_text(encoding="utf-8")
    assert "setup_episode_classification" in text
    assert "portfolio/DD research is blocked" in text
