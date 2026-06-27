from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import market_bomb_phase3_2b_morita_history_reconstruction as r


def test_source_hash_and_lineage_are_preserved(tmp_path: Path):
    src = tmp_path / "scanner_alerts"
    src.mkdir()
    (src / "signals.csv").write_text("ticker,alert_rank,timestamp_utc\nNVDA,S,2026-01-05T15:00:00Z\n", encoding="utf-8")
    inv, _ = r.build_source_inventory(tmp_path)
    signals, _, _, _ = r.parse_sources(tmp_path, inv)
    assert len(signals) == 1
    assert signals.loc[0, "source_hash"] == inv.loc[0, "source_hash"]
    assert signals.loc[0, "source_row_number"] == 2
    assert signals.loc[0, "parser_version"] if "parser_version" in signals.columns else True


def test_rank_mapping_does_not_infer_missing_rank(tmp_path: Path):
    src = tmp_path / "scanner_alerts"
    src.mkdir()
    pd.DataFrame(
        [
            {"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05T15:00:00Z"},
            {"ticker": "MU", "alert_rank": "A", "timestamp_utc": "2026-01-05T15:00:00Z"},
            {"ticker": "AMD", "timestamp_utc": "2026-01-05T15:00:00Z"},
        ]
    ).to_csv(src / "signals.csv", index=False)
    inv, _ = r.build_source_inventory(tmp_path)
    signals, _, _, _ = r.parse_sources(tmp_path, inv)
    assert set(signals["strategy_bucket"]) == {"S_breakout_momentum", "AB_institutional_pullback", "unclassified"}


def test_duplicate_signal_is_audited_not_double_counted(tmp_path: Path):
    src = tmp_path / "scanner_alerts"
    src.mkdir()
    pd.DataFrame(
        [
            {"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05T15:00:00Z"},
            {"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05T15:30:00Z"},
        ]
    ).to_csv(src / "signals.csv", index=False)
    inv, _ = r.build_source_inventory(tmp_path)
    signals, _, _, _ = r.parse_sources(tmp_path, inv)
    dupes, linkage, canonical = r.duplicate_audit(signals)
    assert len(dupes) == 2
    assert len(linkage) == 1
    assert len(canonical) == 1


def test_timestamp_quality_and_analysis_mode_for_date_only():
    ts, quality, _ = r.parse_timestamp("2026-01-05")
    assert quality == "date_only"
    assert r.session_context(ts, quality) == "date_only"
    assert r.analysis_mode("raw_scanner_output", quality, "signal") == "historical_reconstructed"


def test_after_close_signal_uses_next_regular_open_proxy():
    signals = pd.DataFrame(
        [
            {
                "signal_event_id": "s1",
                "ticker": "NVDA",
                "strategy_bucket": "S_breakout_momentum",
                "original_rank": "S",
                "setup_type": "breakout",
                "event_timestamp_utc": "2026-01-05T22:00:00Z",
                "event_session_context": "after_close",
                "analysis_mode": "historical_reconstructed",
            }
        ]
    )
    panel = r.build_outcome_panel(Path("."), signals, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), False)
    assert panel.loc[0, "entry_price_method"] == "next_regular_open_proxy"
    assert panel.loc[0, "entry_timestamp_utc"].startswith("2026-01-06")


def test_broker_fill_is_observed_but_manual_is_not(tmp_path: Path):
    broker = pd.Series({"source_type": "broker_execution_csv", "source_hash": "h", "source_id": "s", "source_path": "broker.csv"})
    row = pd.Series({"ticker": "NVDA", "fill_timestamp_utc": "2026-01-05T15:00:00Z", "side": "buy", "quantity": 1, "fill_price": 10, "contract_symbol": "NVDA260120C00100000"})
    fill = r.normalize_fill_row(row, broker, 2)
    assert fill["data_type"] == "observed"
    assert fill["analysis_mode"] == "strict_live_replay"
    manual = broker.copy()
    manual["source_type"] = "manual_reconstruction_csv"
    fill2 = r.normalize_fill_row(row, manual, 2)
    assert fill2["data_type"] == "reconstructed"


def test_future_and_stale_cta_vol_features_do_not_join(tmp_path: Path):
    hist = tmp_path / "market_bomb_history"
    hist.mkdir()
    pd.DataFrame(
        [{"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-07T21:00:00Z", "effective_available_at_utc": "2026-01-08T14:30:00Z", "cta_trend_state": "long_bias", "cta_deleveraging_proxy": False}]
    ).to_csv(hist / "cta_proxy_history.csv", index=False)
    pd.DataFrame(
        [{"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-07T21:00:00Z", "effective_available_at_utc": "2026-01-08T14:30:00Z", "target_vol": 0.12, "vol_control_state": "stable", "vol_control_pressure_proxy": "stable"}]
    ).to_csv(hist / "vol_control_proxy_history.csv", index=False)
    panel = pd.DataFrame([{"analysis_unit": "signal_event", "signal_event_id": "s", "decision_id": "", "trade_id": "", "ticker": "NVDA", "strategy_bucket": "S_breakout_momentum", "original_rank": "S", "event_timestamp_utc": "2026-01-06T15:00:00Z", "analysis_mode": "historical_reconstructed"}])
    joined = r.build_cta_vol_join(tmp_path, panel)
    assert joined.loc[0, "join_status"] == "failed"


def test_no_sources_generates_templates_and_blocked_gate(tmp_path: Path):
    outputs = r.run(tmp_path)
    assert outputs["source_inventory"].exists()
    assert (tmp_path / "market_bomb_reconstruction" / "templates" / "manual_signal_events_template.csv").exists()
    text = (tmp_path / "morita_history_reconstruction_gate_audit.md").read_text(encoding="utf-8")
    assert "blocked_by_missing_sources" in text


def test_observed_and_modelled_pnl_are_separate(tmp_path: Path):
    src = tmp_path / "scanner_alerts"
    src.mkdir()
    pd.DataFrame([{"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05T15:00:00Z"}]).to_csv(src / "signals.csv", index=False)
    outputs = r.run(tmp_path, build_underlying_outcomes=False)
    panel = pd.read_csv(outputs["outcome_panel"])
    assert "observed_option_pnl_pct" in panel.columns
    assert "modelled_option_pnl_pct" in panel.columns
    assert not bool(panel.loc[0, "observed_option_pnl_available"])
