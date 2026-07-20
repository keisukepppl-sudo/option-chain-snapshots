from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.research.morita_2026_scanner_artifact_recovery_v1 import run_recovery


def write_fixture(root: Path, artifact_id: str, capture_date: str, score: float) -> None:
    directory = root / artifact_id / "scanner" / capture_date
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ticker": "AMAT",
                "rank": "A",
                "production_rank": "S",
                "latest_price_time": "2026-06-25T15:55:00-04:00",
                "production_adjusted_score": score,
                "total_score": 85.0,
                "latest_price": 668.24,
                "prior_20d_high": 641.18,
                "volume_multiple": 1.63,
                "standard_rs_score": 98.46,
                "breakout_today": True,
                "failed_breakout": False,
            }
        ]
    ).to_csv(directory / f"daily_scan_log_{artifact_id}.csv", index=False)
    pd.DataFrame([{"ticker": "AMAT"}]).to_csv(
        directory / f"notified_candidates_{artifact_id}.csv", index=False
    )


def test_recovery_uses_production_rank_and_keeps_provenance(tmp_path: Path) -> None:
    artifact_root = tmp_path / "data" / "pit_recovery" / "github_artifacts"
    write_fixture(artifact_root, "100", "2026-06-26", 54.0)
    result = run_recovery(tmp_path, artifact_root=artifact_root, output_root=tmp_path / "out", run_id="unit")
    calendar = pd.read_csv(Path(result.output_dir) / "rank_weighted_signal_calendar_recovered.csv")
    assert len(calendar) == 1
    assert calendar.loc[0, "rank"] == "S"
    assert calendar.loc[0, "signal_decision_date"] == "2026-06-25"
    assert bool(calendar.loc[0, "notified_in_source_artifact"]) is True
    assert str(calendar.loc[0, "source_artifact_id"]) == "100"
    assert calendar.loc[0, "pit_status"] == "PIT_ARTIFACT_CAPTURED_CURRENT_UNIVERSE_PARTIAL"


def test_duplicate_observation_keeps_latest_artifact(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    write_fixture(artifact_root, "100", "2026-06-26", 54.0)
    write_fixture(artifact_root, "200", "2026-06-26", 56.0)
    result = run_recovery(tmp_path, artifact_root=artifact_root, output_root=tmp_path / "out", run_id="unit")
    calendar = pd.read_csv(Path(result.output_dir) / "rank_weighted_signal_calendar_recovered.csv")
    assert len(calendar) == 1
    assert float(calendar.loc[0, "production_adjusted_score"]) == 56.0
    assert str(calendar.loc[0, "source_artifact_id"]) == "200"


def test_receipt_fails_closed_and_does_not_claim_complete_baseline(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    write_fixture(artifact_root, "100", "2026-06-26", 54.0)
    result = run_recovery(tmp_path, artifact_root=artifact_root, output_root=tmp_path / "out", run_id="unit")
    receipt = json.loads((Path(result.output_dir) / "run_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PARTIAL_RECOVERY_ONLY"
    assert receipt["complete_frozen_2026_source"] is False
    assert receipt["execution_allowed"] is False
    assert receipt["headline_eligible"] is False


def test_empty_artifact_tree_writes_stable_outputs(tmp_path: Path) -> None:
    result = run_recovery(
        tmp_path,
        artifact_root=tmp_path / "missing",
        output_root=tmp_path / "out",
        run_id="unit",
    )
    out = Path(result.output_dir)
    calendar = pd.read_csv(out / "rank_weighted_signal_calendar_recovered.csv")
    assert calendar.empty
    assert "signal_decision_date" in calendar.columns
    assert (out / "source_inventory.csv").exists()


def test_momentum_candidates_is_used_when_daily_log_is_absent(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    directory = artifact_root / "300" / "scanner" / "2026-06-15"
    directory.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ticker": "AMKR",
                "rank": "D",
                "alert_rank": "A",
                "latest_price_time": "2026-06-12T15:55:00-04:00",
            }
        ]
    ).to_csv(directory / "russell1000_momentum_candidates.csv", index=False)
    result = run_recovery(tmp_path, artifact_root=artifact_root, output_root=tmp_path / "out", run_id="unit")
    calendar = pd.read_csv(Path(result.output_dir) / "rank_weighted_signal_calendar_recovered.csv")
    inventory = pd.read_csv(Path(result.output_dir) / "source_inventory.csv")
    assert calendar.loc[0, "ticker"] == "AMKR"
    assert calendar.loc[0, "rank"] == "A"
    assert inventory.loc[0, "source_kind"] == "momentum_candidates_fallback"
