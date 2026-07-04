from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_single_call_reference import s_single_call_reference_engine as e


def synthetic_history(days: int = 40, high_mult: float = 1.05, close_mult: float = 1.02) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=days)
    rows = []
    for idx, date in enumerate(dates):
        base = 100.0 * (1.0 + idx * 0.01)
        rows.append(
            {
                "date": date,
                "ticker": "AAA",
                "open": base,
                "high": base * high_mult,
                "low": base * 0.98,
                "close": base * close_mult,
                "volume": 1000,
            }
        )
    return pd.DataFrame(rows)


def signal(reached_plus5: bool = True) -> dict[str, object]:
    return {
        "signal_id": "s1",
        "underlying_symbol": "AAA",
        "signal_decision_date": "2024-01-01",
        "entry_session": "2024-01-02",
        "entry_price": 100.0,
        "theme": "Test",
        "breakout_day_low": 95.0,
        "reached_plus_5pct_within_10_sessions": str(reached_plus5).lower(),
    }


def test_no_network_provider_broker_api_code_exists() -> None:
    text = "\n".join(
        [
            (REPO_ROOT / "src" / "morita_single_call_reference" / "s_single_call_reference_engine.py").read_text(encoding="utf-8"),
            (REPO_ROOT / "scripts" / "build_morita_s_single_call_reference_v1.py").read_text(encoding="utf-8"),
        ]
    )
    forbidden = ["requests", "urllib", "yfinance", "download(", "broker", "api_key"]
    assert not any(token in text for token in forbidden)


def test_baseline_entry_date_and_price_are_mandatory() -> None:
    bad = signal()
    bad["entry_price"] = ""
    result = e.model_trade(bad, synthetic_history())
    assert result["status"] == "excluded"
    assert result["excluded_reason"] == "missing_entry_price"


def test_only_formal_baseline_ohlcv_lineage_is_accepted(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "source_input_lineage.json").write_text(json.dumps({"inputs": [{"repository_relative_path_or_local_alias": "missing"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="baseline_ohlcv_lineage_missing"):
        e.baseline_input_root(baseline)


def test_entry_markup_and_exit_haircut_are_applied() -> None:
    result = e.model_trade(signal(True), synthetic_history())
    assert result["status"] == "eligible"
    assert abs(float(result["entry_debit"]) - float(result["entry_theoretical_value"]) * 1.05) < 1e-9


def test_future_ohlcv_cannot_affect_earlier_terminal() -> None:
    hist = synthetic_history(40, high_mult=1.0, close_mult=0.9)
    later = hist.copy()
    later.loc[later.index[-1], "high"] = 10000.0
    a = e.model_trade(signal(False), hist)
    b = e.model_trade(signal(False), later)
    assert a["terminal_date"] == b["terminal_date"]
    assert a["terminal_net_return_pct"] == b["terminal_net_return_pct"]


def test_high_triggers_target_touch_and_close_values_terminal_exit() -> None:
    hist = synthetic_history(40, high_mult=2.0, close_mult=0.95)
    result = e.model_trade(signal(True), hist)
    assert result["first_hit_100_date"] != ""
    assert float(result["terminal_net_return_pct"]) < float(result["max_net_return_high_pct"])


def test_formal_plus5_within_10_field_governs_day10_gate() -> None:
    result = e.model_trade(signal(False), synthetic_history(40, high_mult=3.0, close_mult=2.0))
    assert result["terminal_reason"] == "day10_plus5_not_reached"
    assert result["path_session_count"] == 10


def test_breakout_day_low_cannot_create_hard_exit() -> None:
    sig = signal(True)
    sig["breakout_day_low"] = 1000.0
    result = e.model_trade(sig, synthetic_history())
    assert result["terminal_reason"] == "max_holding_30_sessions"


def test_terminal_priority_30_sessions_expiry_missing() -> None:
    ok = e.model_trade(signal(True), synthetic_history(40))
    assert ok["terminal_reason"] == "max_holding_30_sessions"
    missing = e.model_trade(signal(True), synthetic_history(12))
    assert missing["status"] == "excluded"
    assert missing["excluded_reason"] == "unavailable_required_path_data"


def test_manifest_rejects_missing_changed_extra_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    for name in e.REFERENCE_REQUIRED_FILES:
        if name != "s_single_call_reference_content_manifest.json":
            (out / name).write_text("x\n", encoding="utf-8")
    e.build_manifest(out, "s_single_call_reference_content_manifest.json", e.REFERENCE_REQUIRED_FILES)
    assert e.verify_manifest(out, "s_single_call_reference_content_manifest.json", e.REFERENCE_REQUIRED_FILES)["verified"] is True
    (out / "extra.csv").write_text("x\n", encoding="utf-8")
    assert e.verify_manifest(out, "s_single_call_reference_content_manifest.json", e.REFERENCE_REQUIRED_FILES)["extra"] == ["extra.csv"]


def test_no_alert_target_stop_sizing_or_broker_actionization_exists(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "safe.txt").write_text("research only\n", encoding="utf-8")
    e.assert_no_actionization(out)
    (out / "bad.txt").write_text("BUY_NOW\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        e.assert_no_actionization(out)


def test_existing_bot_baseline_risk_dispersion_notification_modules_are_not_mutated_by_model() -> None:
    spec = json.loads((REPO_ROOT / "config" / "morita_s_single_call_reference_v1" / "fixed_iv_reference_model_spec.json").read_text(encoding="utf-8"))
    assert spec["actionization_allowed"] is False
    assert spec["breakout_day_low"] == "diagnostic_only_no_hard_exit"
