from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from scripts import build_morita_bot_historical_baseline_v1 as baseline
from scripts import build_phase1_6c_morita_bot_mechanical_flow_context_study as phase1_6c
from scripts import build_morita_bot_source_seal_v1 as seal


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _input_root(tmp_path: Path) -> Path:
    root = tmp_path / "input"
    rows = []
    dates = pd.bdate_range("2022-06-01", "2026-07-02")
    for ticker, base in [("AAA", 100.0), ("BBB", 80.0), ("QQQ", 300.0)]:
        for i, date in enumerate(dates):
            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "open": base + i * 0.01,
                    "high": base + i * 0.01 + 0.5,
                    "low": base + i * 0.01 - 0.5,
                    "close": base + i * 0.01,
                    "volume": 1_000_000,
                    "raw_or_adjusted": "fixture",
                }
            )
    _write_csv(root / "sources" / "daily_ohlcv_merged.csv", rows)
    _write_csv(root / "sources" / "universe_membership.csv", [{"ticker": t, "effective_date": "2023-07-03", "end_date": "", "universe_pit_status": "static_historical_proxy"} for t in ["AAA", "BBB", "QQQ"]])
    schedule = []
    signal_dates = [d for d in dates.strftime("%Y-%m-%d").tolist() if "2023-07-03" <= d <= "2026-07-02"]
    for idx, date in enumerate(signal_dates):
        schedule.append({"observation_date": date, "next_eligible_session": signal_dates[idx + 1] if idx + 1 < len(signal_dates) else "", "decision_timestamp_convention": "fixture"})
    _write_csv(root / "sources" / "decision_schedule.csv", schedule)
    (root / "source_manifest.json").write_text('{"files":[],"content_hash":"fixture"}\n', encoding="utf-8")
    return root


def test_rule_snapshot_freezes_production_paths_and_hashes() -> None:
    snap = baseline.build_rule_snapshot("abc")
    assert snap["production_pipeline_path"] == "scanner/pipeline.py"
    assert snap["production_selection_path"] == "scanner_notify.py"
    assert snap["production_alert_rank_path"] == "scripts/production_scanner_entry.py"
    assert "scanner/pipeline.py" in snap["source_module_hashes"]
    assert snap["actionization_allowed"] is False


def test_baseline_outputs_have_no_option_fields_and_manifest_verifies(tmp_path: Path) -> None:
    root = _input_root(tmp_path)
    result = baseline.build_baseline(root, tmp_path / "runs", max_dates=5)
    run_dir = tmp_path / "runs" / result["run_id"]
    baseline.verify_manifest(run_dir, "source_content_manifest.json")
    signal_cols = pd.read_csv(run_dir / "morita_bot_signal_events.csv", nrows=0).columns
    panel_cols = pd.read_csv(run_dir / "morita_bot_baseline_panel.csv", nrows=0).columns
    forbidden = {"option", "dte", "strike", "delta"}
    assert not any(any(word in col.lower() for word in forbidden) for col in signal_cols)
    assert not any("option_return" in col.lower() for col in panel_cols)


def test_source_seal_accepts_verified_formal_baseline_candidate(tmp_path: Path, monkeypatch) -> None:
    root = _input_root(tmp_path)
    result = baseline.build_baseline(root, tmp_path / "runs", max_dates=5)
    run_dir = tmp_path / "runs" / result["run_id"]
    artifact_root = tmp_path / "market_bomb_history" / "morita_bot_source_seal_v1" / "source_artifacts"
    monkeypatch.setattr(seal, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(seal, "HISTORY_ROOT", artifact_root.parents[1])
    monkeypatch.setattr(seal, "INVENTORY_ROOT", artifact_root.parents[1] / "inventory")
    validation = seal.validate_candidate(str(run_dir))
    assert validation["status"] == "morita_bot_source_seal_candidate_valid"
    receipt = seal.build_source_artifact(run_dir, artifact_root / "fixture_artifact", "morita_bot_source_seal_v1")
    assert receipt["status"] == "morita_bot_source_seal_completed"
    verified = seal.verify_source_artifact(artifact_root / "fixture_artifact")
    assert verified["status"] == "morita_bot_source_seal_artifact_verified"
    accepted = phase1_6c.validate_morita_bot_run_artifact(artifact_root / "fixture_artifact")
    assert accepted["status"] == "morita_bot_source_artifact_eligible"
