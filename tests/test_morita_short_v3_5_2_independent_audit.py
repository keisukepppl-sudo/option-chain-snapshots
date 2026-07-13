from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_morita_short_v3_5_2_independent_audit.py"
spec = importlib.util.spec_from_file_location("audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["audit"] = audit
spec.loader.exec_module(audit)


def test_expected_count_constants_are_frozen():
    assert audit.EXPECTED_COUNTS == {"S": 309, "A": 504, "S+A": 813, "base_candidates": 1147}


def test_profit_factor_short_return_positive_and_negative():
    metrics = audit.performance_metrics(pd.Series([0.10, -0.05, 0.05]))
    assert round(metrics["profit_factor"], 6) == 3.0
    assert metrics["n"] == 3


def test_ticker_episode_collapse_merges_nearby_sessions():
    candidates = pd.DataFrame(
        [
            {"candidate_id": "a", "ticker": "AAA", "d0_date": "2026-01-02", "rank": "S", "construction_status": "CANDIDATE_CONSTRUCTED"},
            {"candidate_id": "b", "ticker": "AAA", "d0_date": "2026-01-06", "rank": "S", "construction_status": "CANDIDATE_CONSTRUCTED"},
            {"candidate_id": "c", "ticker": "AAA", "d0_date": "2026-01-20", "rank": "S", "construction_status": "CANDIDATE_CONSTRUCTED"},
        ]
    )
    idx = {"2026-01-02": 0, "2026-01-06": 2, "2026-01-20": 10}
    out = audit.build_ticker_episode_map(candidates, idx, 5)
    assert out["ticker_episode_id"].nunique() == 2


def test_missing_m15_is_not_filled():
    candidates = pd.DataFrame(
        [{"candidate_id": "a", "ticker": "AAA", "d1_date": "2026-01-05", "construction_status": "CANDIDATE_CONSTRUCTED"}]
    )
    out = audit.build_m15_coverage_audit(candidates, pd.DataFrame(), Path("missing.parquet"))
    assert out.iloc[0]["coverage_status"] == "M15_SOURCE_MISSING"


def test_safety_contract_disables_execution():
    fields = audit.safety_fields()
    assert fields["research_only"] is True
    assert fields["execution_allowed"] is False
    assert fields["live_order_allowed"] is False
    assert fields["synthetic_intraday_data_allowed"] is False
