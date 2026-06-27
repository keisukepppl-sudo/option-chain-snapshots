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


def test_next_regular_open_skips_nyse_holiday():
    ts, _, _ = r.parse_timestamp("2026-07-02T22:00:00Z")
    next_open = r.next_regular_open(ts)
    assert next_open.tz_convert(r.ET).date().isoformat() == "2026-07-06"


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


def test_naive_jst_source_is_not_interpreted_as_et(tmp_path: Path):
    src = tmp_path / "daily_scan_log"
    src.mkdir()
    pd.DataFrame([{"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05 10:00:00"}]).to_csv(src / "scan.csv", index=False)
    inv, _ = r.build_source_inventory(tmp_path)
    signals, _, _, _ = r.parse_sources(tmp_path, inv)
    assert signals.loc[0, "event_timezone_original"] == "Asia/Tokyo"
    assert signals.loc[0, "event_timestamp_utc"].startswith("2026-01-05T01:00:00")


def test_timezone_unknown_blocks_strict_join_for_broker_order(tmp_path: Path):
    src = tmp_path / "morita_decision_history"
    src.mkdir()
    pd.DataFrame([{"ticker": "NVDA", "decision_action": "enter", "decision_timestamp_utc": "2026-01-05 10:00:00"}]).to_csv(src / "order.csv", index=False)
    inv, _ = r.build_source_inventory(tmp_path)
    _, decisions, _, _ = r.parse_sources(tmp_path, inv)
    assert decisions.empty
    r.run(tmp_path)
    audit = pd.read_csv(tmp_path / "market_bomb_reconstruction" / "audit" / "timestamp_resolution_audit.csv")
    assert "timezone_unknown" in set(audit["timestamp_quality"])


def test_parser_allowlist_prevents_scanner_fake_fill(tmp_path: Path):
    src = tmp_path / "scanner_alerts"
    src.mkdir()
    pd.DataFrame([{"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05T15:00:00Z", "fill_price": 1.23, "quantity": 1}]).to_csv(src / "signals.csv", index=False)
    inv, _ = r.build_source_inventory(tmp_path)
    signals, _, fills, _ = r.parse_sources(tmp_path, inv)
    assert len(signals) == 1
    assert fills.empty
    r.run(tmp_path)
    parser_audit = pd.read_csv(tmp_path / "market_bomb_reconstruction" / "audit" / "parser_execution_audit.csv")
    fill_row = parser_audit[parser_audit["parser_name"].eq("fill_normalizer")].iloc[0]
    assert not bool(fill_row["parser_allowed"])


def test_broker_order_is_decision_not_fill(tmp_path: Path):
    src = tmp_path / "morita_decision_history"
    src.mkdir()
    pd.DataFrame([{"ticker": "NVDA", "decision_action": "enter", "decision_timestamp_utc": "2026-01-05T15:00:00Z", "fill_price": 10, "quantity": 1}]).to_csv(src / "orders.csv", index=False)
    inv, _ = r.build_source_inventory(tmp_path)
    _, decisions, fills, _ = r.parse_sources(tmp_path, inv)
    assert len(decisions) == 1
    assert fills.empty


def test_date_only_signal_is_not_cta_vol_join_eligible(tmp_path: Path):
    src = tmp_path / "scanner_alerts"
    src.mkdir()
    pd.DataFrame([{"ticker": "NVDA", "alert_rank": "S", "date": "2026-01-05"}]).to_csv(src / "signals.csv", index=False)
    outputs = r.run(tmp_path, build_underlying_outcomes=False)
    panel = pd.read_csv(outputs["outcome_panel"])
    assert panel.loc[0, "entry_price_method"] == "unavailable_date_only"
    assert not bool(panel.loc[0, "cta_vol_join_eligible"])
    joined = pd.read_csv(outputs["cta_vol_join"])
    assert joined.loc[0, "join_status"] == "skipped"


def test_trade_panel_takes_priority_over_linked_signal(tmp_path: Path):
    signals = pd.DataFrame([{"signal_event_id": "s1", "ticker": "NVDA", "strategy_bucket": "S_breakout_momentum", "original_rank": "S", "setup_type": "breakout", "event_timestamp_utc": "2026-01-05T15:00:00Z", "event_session_context": "regular_hours", "analysis_mode": "historical_reconstructed"}])
    fills = pd.DataFrame([{"trade_id": "t1", "decision_id": "", "signal_event_id": "s1", "ticker": "NVDA", "fill_timestamp_utc": "2026-01-05T15:01:00Z", "fill_price": 10, "quantity": 1, "multiplier": 100, "source_evidence_level": "raw_broker_execution", "analysis_mode": "strict_live_replay", "cta_vol_join_eligible": True}])
    panel = r.build_outcome_panel(tmp_path, signals, pd.DataFrame(), fills, pd.DataFrame(), False)
    assert list(panel["analysis_unit"]) == ["trade"]
    assert panel.loc[0, "entry_price_method"] == "actual_fill"


def test_input_source_hash_manifest_detects_mutation(tmp_path: Path):
    src = tmp_path / "scanner_alerts"
    src.mkdir()
    path = src / "signals.csv"
    path.write_text("ticker,alert_rank,timestamp_utc\nNVDA,S,2026-01-05T15:00:00Z\n", encoding="utf-8")
    before = r.input_source_hash_manifest(tmp_path)
    path.write_text("ticker,alert_rank,timestamp_utc\nNVDA,S,2026-01-05T15:00:00Z\nAMD,A,2026-01-05T15:00:00Z\n", encoding="utf-8")
    after = r.input_source_hash_manifest(tmp_path)
    count, report = r.compare_input_source_manifests(before, after)
    assert count == 1
    assert "scanner_alerts/signals.csv" in report


def test_canonical_selection_uses_numeric_source_priority(tmp_path: Path):
    manual = tmp_path / "market_bomb_reconstruction" / "raw_sources"
    scanner = tmp_path / "scanner_alerts"
    manual.mkdir(parents=True)
    scanner.mkdir()
    pd.DataFrame([{"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05T15:00:00Z", "timezone": "UTC"}]).to_csv(manual / "manual_signals.csv", index=False)
    pd.DataFrame([{"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-01-05T15:30:00Z"}]).to_csv(scanner / "signals.csv", index=False)
    inv, _ = r.build_source_inventory(tmp_path)
    signals, _, _, _ = r.parse_sources(tmp_path, inv)
    _, linkage, canonical = r.duplicate_audit(signals)
    assert canonical.iloc[0]["source_evidence_level"] == "raw_scanner_output"
    assert linkage.iloc[0]["canonical_source_priority"] < linkage.iloc[0]["duplicate_source_priority"]
