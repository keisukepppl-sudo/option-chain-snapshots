from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "fetch_morita_vxn_history_v1.py"
spec = importlib.util.spec_from_file_location("vxn_fetch", SCRIPT_PATH)
vxn_fetch = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(vxn_fetch)


def test_vxn_fetcher_only_accepts_authorized_symbol_and_dates():
    vxn_fetch.validate_authorized_request("2023-06-01", "2026-07-02", symbol="^VXN")
    with pytest.raises(SystemExit, match="unauthorized_symbol"):
        vxn_fetch.validate_authorized_request("2023-06-01", "2026-07-02", symbol="^VIX")
    with pytest.raises(SystemExit, match="unauthorized_date_range"):
        vxn_fetch.validate_authorized_request("2023-06-02", "2026-07-02", symbol="^VXN")
    with pytest.raises(SystemExit, match="unauthorized_date_range"):
        vxn_fetch.validate_authorized_request("2023-06-01", "2026-07-03", symbol="^VXN")


def test_yahoo_chart_url_uses_daily_raw_unadjusted_settings():
    url = vxn_fetch.yahoo_chart_url("^VXN", "2023-06-01", "2026-07-02")
    assert "%5EVXN" in url
    assert "interval=1d" in url
    assert "includePrePost=false" in url
    assert "events=history" in url
    assert "VIX" not in url.replace("%5EVXN", "")


def test_normalize_chart_payload_outputs_vxn_rows():
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704153600, 1704240000],
                    "indicators": {
                        "quote": [
                            {
                                "open": [20.0, 21.0],
                                "high": [22.0, 23.0],
                                "low": [19.0, 20.0],
                                "close": [21.0, 22.0],
                                "volume": [0, 0],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }
    df = vxn_fetch.normalize_chart(payload)
    assert list(df.columns) == ["date", "symbol", "open", "high", "low", "close", "volume"]
    assert set(df["symbol"]) == {"^VXN"}
    assert df["close"].tolist() == [21.0, 22.0]


def test_run_fetch_uses_mocked_single_authorized_remote_call(tmp_path: Path, monkeypatch):
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704153600 + i * 86400 for i in range(6)],
                    "indicators": {
                        "quote": [
                            {
                                "open": [20 + i for i in range(6)],
                                "high": [21 + i for i in range(6)],
                                "low": [19 + i for i in range(6)],
                                "close": [20.5 + i for i in range(6)],
                                "volume": [0 for _ in range(6)],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }
    calls = []

    def fake_fetch(symbol: str, start_date: str, end_date: str, timeout: int = 60):
        calls.append((symbol, start_date, end_date, timeout))
        return payload

    monkeypatch.setattr(vxn_fetch, "fetch_yahoo_chart", fake_fetch)
    result = vxn_fetch.run_fetch("2023-06-01", "2026-07-02", tmp_path)
    assert calls == [("^VXN", "2023-06-01", "2026-07-02", 60)]
    assert result["status"] == "vxn_history_intake_completed"
    assert (tmp_path / "vxn_history_raw" / "vxn_yahoo_chart_raw.json").exists()
    assert (tmp_path / "vxn_history_normalized.csv").exists()
    assert (tmp_path / "vxn_intake_receipt.json").exists()
    assert (tmp_path / "vxn_input_manifest.json").exists()
