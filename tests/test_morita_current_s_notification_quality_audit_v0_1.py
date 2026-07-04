from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_current_s_notification_quality_audit_v0_1 as m


def session_pos(n: int = 80) -> tuple[list[str], dict[str, int]]:
    dates = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=n)]
    return dates, {date: idx for idx, date in enumerate(dates)}


def s_fixture(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"signal_id": "s1", "ticker": "AAA", "underlying_symbol": "AAA", "signal_rank": "S", "signal_date": dates[0], "signal_decision_date": dates[0], "entry_date": dates[1], "entry_session": dates[1], "production_adjusted_score": 80},
            {"signal_id": "s2", "ticker": "AAA", "underlying_symbol": "AAA", "signal_rank": "S", "signal_date": dates[5], "signal_decision_date": dates[5], "entry_date": dates[6], "entry_session": dates[6], "production_adjusted_score": 81},
            {"signal_id": "s3", "ticker": "AAA", "underlying_symbol": "AAA", "signal_rank": "S", "signal_date": dates[40], "signal_decision_date": dates[40], "entry_date": dates[41], "entry_session": dates[41], "production_adjusted_score": 82},
        ]
    )


def test_every_source_row_gets_one_classification_and_no_gap_rebreakout() -> None:
    dates, pos = session_pos()
    rows, native = m.classify_notifications(s_fixture(dates), pos)
    assert native["status"] == "NATIVE_CURRENT_S_LOGIC_NOT_FOUND"
    assert len(rows) == 3
    assert [r["classification"] for r in rows] == [
        "CURRENT_S_INITIAL_BREAKOUT",
        "CURRENT_S_EXTENDED_FOMO",
        "CURRENT_S_UNRESOLVED",
    ]
    assert all(r["classification"] != "CURRENT_S_REBREAKOUT" for r in rows)


def test_missing_native_fields_cannot_be_native_confirmed() -> None:
    native = m.native_logic_status(["signal_id", "entry_session", "prior_20d_high"])
    assert native["status"] == "NATIVE_CURRENT_S_LOGIC_NOT_FOUND"


def test_outcomes_use_entry_price_low_close_high_definitions() -> None:
    dates, _ = session_pos(40)
    hist = pd.DataFrame(
        {
            "ticker": ["AAA"] * 40,
            "date": pd.to_datetime(dates[:40]),
            "open": [100.0] * 40,
            "high": [100.0 + i for i in range(40)],
            "low": [100.0 - i for i in range(40)],
            "close": [100.0 - (i / 2) for i in range(40)],
            "volume": [1000] * 40,
        }
    )
    row = {
        "raw_s_event_id": "s1",
        "ticker": "AAA",
        "entry_session": dates[1],
        "signal_decision_date": dates[0],
        "classification": "CURRENT_S_INITIAL_BREAKOUT",
        "classification_confidence": "PROXY_CONFIRMED",
    }
    source_by_id = {"s1": {"entry_price": 100.0}}
    out = m.outcome_for_row(row, source_by_id, {"AAA": hist})
    assert out["outcome_coverage_status"] == "complete"
    assert out["MAE_LOW_10"] == (hist.loc[11, "low"] / 100.0) - 1.0
    assert out["CLOSE_DRAWDOWN_10"] == (hist.loc[11, "close"] / 100.0) - 1.0
    assert out["MFE_HIGH_10"] == (hist.loc[11, "high"] / 100.0) - 1.0


def test_native_only_empty_and_proxy_summary_sparse() -> None:
    rows = [
        {
            "classification": "CURRENT_S_INITIAL_BREAKOUT",
            "classification_confidence": "PROXY_CONFIRMED",
            "ticker": "AAA",
            "entry_session": "2024-01-02",
            "outcome_coverage_status": "complete",
            "underlying_return_5_sessions": 0.01,
            "underlying_return_10_sessions": 0.02,
            "underlying_return_20_sessions": 0.03,
            "plus_5pct_within_10_sessions": False,
            "plus_10pct_within_20_sessions": False,
            "MAE_LOW_20": -0.01,
            "CLOSE_DRAWDOWN_20": -0.005,
            "MFE_HIGH_20": 0.04,
        }
    ]
    native_only = m.performance_summary(rows, "native_only", ["full_range"])
    assert len(native_only) == len(m.FINAL_CLASSES)
    assert all(row["notification_count"] == 0 for row in native_only)
    summary = m.performance_summary(rows, "native_plus_proxy", ["full_range"])
    initial = [r for r in summary if r["classification"] == "CURRENT_S_INITIAL_BREAKOUT"][0]
    assert initial["sample_label"] == "SPARSE_SAMPLE"


def test_manifest_rejects_missing_changed_extra_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUT", tmp_path)
    for name in m.REQUIRED_OUTPUTS:
        if name != "audit_content_manifest.json":
            (tmp_path / name).write_text("x\n", encoding="utf-8")
    m.build_manifest()
    assert m.verify_manifest()["verified"] is True
    (tmp_path / "extra.csv").write_text("x\n", encoding="utf-8")
    assert m.verify_manifest()["extra"] == ["extra.csv"]


def test_no_live_action_boundary() -> None:
    text = (REPO_ROOT / "docs" / "morita_current_s_notification_audit_boundary_v0_1.md").read_text(encoding="utf-8")
    assert "live notification behavior changes" in text
    assert "portfolio drawdown" in text
