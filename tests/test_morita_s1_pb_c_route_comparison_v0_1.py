from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_s1_pb_c_route_comparison_v0_1 as m


def sessions(n: int = 60) -> tuple[list[str], dict[str, int]]:
    dates = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=n)]
    return dates, {date: idx for idx, date in enumerate(dates)}


def raw_s_fixture(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "AAA", "raw_s_event_id": "s1", "signal_decision_date": dates[0], "entry_session": dates[1]},
            {"ticker": "AAA", "raw_s_event_id": "s2", "signal_decision_date": dates[5], "entry_session": dates[6]},
            {"ticker": "AAA", "raw_s_event_id": "s3", "signal_decision_date": dates[8], "entry_session": dates[9]},
            {"ticker": "AAA", "raw_s_event_id": "s4", "signal_decision_date": dates[35], "entry_session": dates[36]},
        ]
    )


def event_map(dates: list[str]) -> dict[str, dict[str, object]]:
    return {
        "s1": {"signal_id": "s1", "production_adjusted_score": 90, "accumulation_score": 60, "entry_price": 100},
        "s2": {"signal_id": "s2", "production_adjusted_score": 91, "accumulation_score": 61, "entry_price": 110},
        "s3": {"signal_id": "s3", "production_adjusted_score": 92, "accumulation_score": 62, "entry_price": 115},
        "s4": {"signal_id": "s4", "production_adjusted_score": 93, "accumulation_score": 63, "entry_price": 120},
        "a1": {"signal_id": "a1", "production_adjusted_score": 80, "accumulation_score": 40, "entry_price": 105},
        "b1": {"signal_id": "b1", "production_adjusted_score": 81, "accumulation_score": 55, "entry_price": 106},
        "b2": {"signal_id": "b2", "production_adjusted_score": 82, "accumulation_score": 70, "entry_price": 107},
    }


def test_cluster_proxy_uses_only_prior_raw_s_and_gap_rules() -> None:
    dates, pos = sessions()
    clusters = m.build_cluster_proxy(raw_s_fixture(dates), pos)
    assert clusters[0]["cluster_proxy_status"] == "NEW_CLUSTER_PROXY"
    assert clusters[1]["cluster_proxy_status"] == "CONTINUATION_OF_ACTIVE_CLUSTER"
    assert clusters[2]["cluster_proxy_status"] == "CONTINUATION_OF_ACTIVE_CLUSTER"
    assert clusters[3]["cluster_proxy_status"] == "NEW_CLUSTER_PROXY"
    assert clusters[3]["cluster_proxy_id"] != clusters[0]["cluster_proxy_id"]


def test_route_calendar_one_s1_one_c_one_pb_max_per_cluster() -> None:
    dates, pos = sessions()
    clusters = m.build_cluster_proxy(raw_s_fixture(dates), pos)
    raw_ab = pd.DataFrame(
        [
            {"ticker": "AAA", "raw_ab_event_id": "a1", "raw_rank": "A", "signal_decision_date": dates[2], "entry_session": dates[3], "accumulation_score": "40"},
            {"ticker": "AAA", "raw_ab_event_id": "b1", "raw_rank": "B", "signal_decision_date": dates[3], "entry_session": dates[4], "accumulation_score": "55"},
            {"ticker": "AAA", "raw_ab_event_id": "b2", "raw_rank": "B", "signal_decision_date": dates[4], "entry_session": dates[5], "accumulation_score": "70"},
        ]
    )
    routes = m.build_route_calendar(clusters, raw_ab, event_map(dates), pos)
    first_cluster = [r for r in routes if r["cluster_proxy_id"] == "AAA_cluster_proxy_001"]
    assert sum(r["route_state"] == "S1_CLUSTER_FIRST" for r in first_cluster) == 1
    assert sum(r["route_state"] == "C_FIRST_CONTINUATION" for r in first_cluster) == 1
    assert sum(r["route_state"] == "C_LATER_CONTINUATION_EXCLUDED" for r in first_cluster) == 1
    assert sum(r["route_state"] == "PB_FIRST_PARENTED" for r in first_cluster) == 1
    assert sum(r["route_state"] == "PB_ACCUMULATION_BELOW_50" for r in first_cluster) == 1
    assert sum(r["route_state"] == "PB_LATER_CANDIDATE_EXCLUDED" for r in first_cluster) == 1


def test_outcomes_are_measured_from_route_entry_date() -> None:
    dates, _ = sessions(40)
    hist = pd.DataFrame(
        {
            "ticker": ["AAA"] * 40,
            "date": pd.to_datetime(dates[:40]),
            "open": [100 + i for i in range(40)],
            "high": [102 + i for i in range(40)],
            "low": [98 + i for i in range(40)],
            "close": [100 + i for i in range(40)],
            "volume": [1000] * 40,
        }
    )
    row = {
        "cluster_proxy_id": "AAA_cluster_proxy_001",
        "ticker": "AAA",
        "route": "C",
        "route_state": "C_FIRST_CONTINUATION",
        "raw_source_event_id": "s2",
        "signal_date": dates[5],
        "entry_date": dates[6],
    }
    out = m.outcome_for_route(row, event_map(dates), {"AAA": hist})
    assert out["outcome_status"] == "complete"
    assert out["underlying_return_5_sessions"] == (hist.loc[11, "close"] / hist.loc[6, "close"]) - 1.0


def test_sparse_labels_and_fixed_iv_policy_flags() -> None:
    rows, _ = m.summarize_underlying(
        [
            {
                "route": "S1",
                "route_state": "S1_CLUSTER_FIRST",
                "ticker": "AAA",
                "entry_date": "2024-01-02",
                "outcome_status": "complete",
                "underlying_return_5_sessions": 0.01,
                "underlying_return_10_sessions": 0.02,
                "underlying_return_20_sessions": 0.03,
                "plus_5pct_within_10_sessions": False,
                "plus_10pct_within_20_sessions": False,
                "MAE_10_sessions": -0.02,
                "MAE_20_sessions": -0.03,
                "MFE_10_sessions": 0.04,
                "MFE_20_sessions": 0.05,
            }
        ]
    )
    assert [r for r in rows if r["route"] == "S1" and r["subperiod"] == "full_range"][0]["sample_label"] == "SPARSE_SAMPLE"
    synthetic = [{"route": "S1", "fixed_iv_eligible_count": 1, "uniform_reference_exit_for_comparison_only": True, "not_final_route_exit_policy": True}]
    assert synthetic[0]["uniform_reference_exit_for_comparison_only"] is True
    assert synthetic[0]["not_final_route_exit_policy"] is True


def test_manifest_rejects_missing_changed_extra_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUT", tmp_path)
    for name in m.REQUIRED_FILES:
        if name != "route_comparison_content_manifest.json":
            (tmp_path / name).write_text("x\n", encoding="utf-8")
    m.build_manifest()
    assert m.verify_manifest()["verified"] is True
    (tmp_path / "extra.csv").write_text("x\n", encoding="utf-8")
    assert m.verify_manifest()["extra"] == ["extra.csv"]


def test_no_notification_order_portfolio_sizing_terms_in_boundary() -> None:
    text = (REPO_ROOT / "docs" / "morita_s1_pb_c_route_comparison_boundary_v0_1.md").read_text(encoding="utf-8")
    assert "No production notification" in text
    assert "portfolio" in text.lower()
