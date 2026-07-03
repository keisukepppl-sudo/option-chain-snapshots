from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

from scripts import fetch_morita_bot_baseline_tail_ohlcv_v1 as tail


def _history(start: str = "2026-05-20", periods: int = 20, base: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods)
    return pd.DataFrame(
        {
            "Open": [base + i for i in range(periods)],
            "High": [base + i + 1 for i in range(periods)],
            "Low": [base + i - 1 for i in range(periods)],
            "Close": [base + i + 0.5 for i in range(periods)],
            "Volume": [1_000_000 + i for i in range(periods)],
        },
        index=dates,
    )


def test_normalize_provider_frame_keeps_raw_unadjusted_close_and_no_adj_close() -> None:
    dates = pd.to_datetime(["2026-06-01", "2026-06-02"])
    raw = pd.DataFrame(
        {
            ("AAA", "Open"): [10.0, 11.0],
            ("AAA", "High"): [11.0, 12.0],
            ("AAA", "Low"): [9.0, 10.0],
            ("AAA", "Close"): [10.5, 11.5],
            ("AAA", "Adj Close"): [99.0, 99.0],
            ("AAA", "Volume"): [1000, 2000],
        },
        index=dates,
    )
    out = tail.normalize_provider_frame(raw, ["AAA"])
    assert list(out.columns) == ["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"]
    assert out["close"].tolist() == [10.5, 11.5]
    assert set(out["raw_or_adjusted"]) == {"raw_unadjusted_provider_tail"}


def test_overlap_reconciliation_and_coverage_are_deterministic() -> None:
    existing = pd.DataFrame(
        [
            {"date": "2026-06-01", "ticker": "AAA", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "raw_or_adjusted": "old"},
            {"date": "2026-06-01", "ticker": "QQQ", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "raw_or_adjusted": "old"},
        ]
    )
    provider = pd.concat(
        [
            existing.assign(raw_or_adjusted="raw_unadjusted_provider_tail"),
            pd.DataFrame(
                [
                    {"date": "2026-06-15", "ticker": "AAA", "open": 3, "high": 4, "low": 2, "close": 3.5, "volume": 200, "raw_or_adjusted": "raw_unadjusted_provider_tail"},
                    {"date": "2026-06-15", "ticker": "QQQ", "open": 3, "high": 4, "low": 2, "close": 3.5, "volume": 200, "raw_or_adjusted": "raw_unadjusted_provider_tail"},
                    {"date": "2026-07-02", "ticker": "AAA", "open": 5, "high": 6, "low": 4, "close": 5.5, "volume": 300, "raw_or_adjusted": "raw_unadjusted_provider_tail"},
                    {"date": "2026-07-02", "ticker": "QQQ", "open": 5, "high": 6, "low": 4, "close": 5.5, "volume": 300, "raw_or_adjusted": "raw_unadjusted_provider_tail"},
                ]
            ),
        ],
        ignore_index=True,
    )
    overlap = tail.compare_overlap(existing, provider)
    coverage = tail.tail_coverage(provider, ["AAA", "QQQ"])
    assert overlap["overlap_status"] == "passed"
    assert overlap["price_field_match_rate"] == 1.0
    assert coverage["QQQ_tail_complete"] is True
    assert coverage["tail_coverage_status"] == "tail_coverage_passed"


def test_build_input_from_cached_raw_does_not_call_provider_or_overwrite_pickle(tmp_path: Path) -> None:
    pkl = tmp_path / "histories.pkl"
    histories = {"AAA": _history(), "QQQ": _history(base=200)}
    with pkl.open("wb") as f:
        pickle.dump(histories, f)
    before = pkl.read_bytes()
    root = tmp_path / "input"
    raw_dir = root / "sources" / "yahoo_tail_raw"
    raw_dir.mkdir(parents=True)
    existing = tail.normalize_existing_rows(histories, tail.EXISTING_CUTOFF)
    tail_rows = []
    for ticker in ["AAA", "QQQ"]:
        for date in ["2026-06-15", "2026-06-16", "2026-07-02"]:
            tail_rows.append({"date": date, "ticker": ticker, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 123, "raw_or_adjusted": "raw_unadjusted_provider_tail"})
    provider = pd.concat([existing.assign(raw_or_adjusted="raw_unadjusted_provider_tail"), pd.DataFrame(tail_rows)], ignore_index=True)
    provider.to_csv(raw_dir / "batch_0001_normalized.csv", index=False)
    result = tail.build_input(pkl, root, batch_size=10, retries=0, sleep_seconds=0, use_existing_raw=True)
    assert result["status"] == "morita_tail_intake_completed"
    assert pkl.read_bytes() == before
    merged = pd.read_csv(root / "sources" / "daily_ohlcv_merged.csv")
    assert "2026-06-15" in set(merged["date"])
    assert (root / "source_manifest.json").exists()
