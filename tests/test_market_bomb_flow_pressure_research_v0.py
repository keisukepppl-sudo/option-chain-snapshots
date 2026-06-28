from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

import market_bomb_flow_pressure_research_v0 as m


FIXED_NOW = "2020-02-20T22:00:00Z"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "market_bomb_config").mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "market_bomb_config" / "flow_pressure_research_v0_policy.json", root / "market_bomb_config" / "flow_pressure_research_v0_policy.json")
    return root


def _price_rows(start: str, n: int, base: float, step: float) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=n)
    close = [base + i * step + (i % 5) * 0.15 for i in range(n)]
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "close": close})


def _stage(root: Path, staging_id: str = "fixture_flow") -> Path:
    stage = m.staging_dir(root, staging_id)
    (stage / "sources").mkdir(parents=True)
    specs = [
        ("price_qqq", "QQQ", "equity_index_etf", "vol_control_deleveraging", 100, 0.7, None),
        ("price_spy", "SPY", "equity_index_etf", "vol_control_deleveraging", 300, 0.5, None),
        ("price_tqqq", "TQQQ", "leveraged_etf", "leveraged_etf_rebalance", 45, 0.9, 1000000000.0),
        ("price_sqqq", "SQQQ", "leveraged_etf", "leveraged_etf_rebalance", 35, -0.35, 700000000.0),
    ]
    sources = []
    for source_id, ticker, asset_class, module, base, step, aum_base in specs:
        df = _price_rows("2020-01-02", 36, base, step)
        if aum_base is not None:
            df["aum"] = [aum_base + i * 1000000 for i in range(len(df))]
        rel = f"sources/{source_id}.csv"
        df.to_csv(stage / rel, index=False)
        sources.append(
            {
                "source_id": source_id,
                "source_name": "unit_test_local_csv",
                "source_file": f"{source_id}.csv",
                "source_as_of_timestamp": "2020-02-20T21:30:00Z",
                "available_at_timestamp": "2020-02-20T21:45:00Z",
                "market_timestamp": "2020-02-20T21:00:00Z",
                "instrument": ticker,
                "asset_class": asset_class,
                "module": module,
                "relative_path": rel,
                "coverage_start_date": str(df["date"].iloc[0]),
                "coverage_end_date": str(df["date"].iloc[-1]),
                "dataset_version": "unit_test_v1",
            }
        )
    manifest = {
        "artifact_version": "flow_pressure_research_v0_fixture",
        "staging_id": staging_id,
        "operator_attestation": {"personal_research_only": True},
        "sources": sources,
        "leveraged_etf_universe": [
            {"ticker": "TQQQ", "target": "QQQ", "leverage": 3.0},
            {"ticker": "SQQQ", "target": "QQQ", "leverage": -3.0},
        ],
    }
    (stage / "source_bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return stage


def _manifest(stage: Path) -> dict[str, object]:
    return json.loads((stage / "source_bundle_manifest.json").read_text(encoding="utf-8"))


def _write_manifest(stage: Path, manifest: dict[str, object]) -> None:
    (stage / "source_bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_verify_flow_staging_dry_preflight_no_persistent_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    _stage(root)
    monkeypatch.setenv("FLOW_PRESSURE_NOW_UTC", FIXED_NOW)
    result = m.verify_staging(root, "fixture_flow", now_utc=FIXED_NOW)
    assert result["candidate_quality_status"] == "valid_research_candidate"
    assert result["source_count"] == 4
    assert not m.releases_dir(root).exists()


def test_build_and_verify_flow_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    _stage(root)
    monkeypatch.setenv("FLOW_PRESSURE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_flow", now_utc=FIXED_NOW)
    meta = m.verify_release(root, release_id)
    rel = m.release_dir(root, release_id)
    assert meta["release_quality_status"] == "valid_research_candidate"
    features = pd.read_csv(rel / "features" / "flow_pressure_features.csv")
    assert {"leveraged_etf_rebalance", "vol_control_deleveraging", "cta_trend_flow", "dealer_gamma_regime"}.issubset(set(features["module"]))
    assert features["is_observed_flow"].fillna(False).astype(bool).sum() == 0
    assert features["actionization_allowed"].fillna(False).astype(bool).sum() == 0


@pytest.mark.parametrize("bad_path", ["../outside.csv", "/tmp/outside.csv", "C:/temp/outside.csv", "\\\\server\\share\\outside.csv"])
def test_flow_staging_path_escape_rejected(tmp_path: Path, bad_path: str) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    manifest = _manifest(stage)
    manifest["sources"][0]["relative_path"] = bad_path
    _write_manifest(stage, manifest)
    with pytest.raises(SystemExit):
        m.verify_staging(root, "fixture_flow", now_utc=FIXED_NOW)


def test_flow_duplicate_source_path_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    manifest = _manifest(stage)
    manifest["sources"][1]["relative_path"] = manifest["sources"][0]["relative_path"]
    _write_manifest(stage, manifest)
    with pytest.raises(SystemExit, match="duplicate staged source path"):
        m.verify_staging(root, "fixture_flow", now_utc=FIXED_NOW)


def test_flow_symlink_source_rejected_when_supported(tmp_path: Path) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    target = stage / "sources" / "price_qqq.csv"
    link = stage / "sources" / "link.csv"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    manifest = _manifest(stage)
    manifest["sources"][0]["relative_path"] = "sources/link.csv"
    _write_manifest(stage, manifest)
    with pytest.raises(SystemExit, match="symlink"):
        m.verify_staging(root, "fixture_flow", now_utc=FIXED_NOW)


def test_flow_timestamp_naive_and_future_available_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    manifest = _manifest(stage)
    manifest["sources"][0]["available_at_timestamp"] = "2020-02-20 21:45:00"
    _write_manifest(stage, manifest)
    with pytest.raises(SystemExit, match="timezone-aware"):
        m.verify_staging(root, "fixture_flow", now_utc=FIXED_NOW)
    manifest["sources"][0]["available_at_timestamp"] = "2020-02-21T21:45:00Z"
    _write_manifest(stage, manifest)
    with pytest.raises(SystemExit, match="future"):
        m.verify_staging(root, "fixture_flow", now_utc=FIXED_NOW)


def test_flow_release_detects_tamper_and_extra_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    _stage(root)
    monkeypatch.setenv("FLOW_PRESSURE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_flow", now_utc=FIXED_NOW)
    rel = m.release_dir(root, release_id)
    features = rel / "features" / "flow_pressure_features.csv"
    original = features.read_text(encoding="utf-8")
    features.write_text(original + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="sha mismatch"):
        m.verify_release(root, release_id)
    features.write_text(original, encoding="utf-8")
    (rel / "features" / "extra.csv").write_text("x\n1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="file set"):
        m.verify_release(root, release_id)


def test_flow_backtest_run_and_verify_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    _stage(root)
    monkeypatch.setenv("FLOW_PRESSURE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_flow", now_utc=FIXED_NOW)
    run_id = m.run_flow_backtest(root, release_id)
    assert m.verify_backtest(root, release_id, run_id)["status"] == "valid"
    run_dir = m.release_dir(root, release_id) / "backtest_runs" / run_id
    (run_dir / "backtest_results.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="sha mismatch"):
        m.verify_backtest(root, release_id, run_id)
