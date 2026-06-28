from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

import market_bomb_fragility_data_release_v0 as m


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fragility_data_release_v0_nonempty"
FIXED_NOW = "2023-09-20T00:00:00Z"


def _copy_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "market_bomb_config").mkdir(parents=True)
    for name in [
        "nyse_regular_sessions_v1.csv",
        "fragility_score_v0_rules.json",
        "fragility_data_release_v0_policy.json",
        "fragility_data_release_v0_schema.json",
    ]:
        shutil.copyfile(ROOT / "market_bomb_config" / name, root / "market_bomb_config" / name)
    (root / ".gitignore").write_text(
        "market_bomb_history/fragility_score_v0/staging/\n"
        "market_bomb_history/fragility_score_v0/releases/\n"
        "market_bomb_history/fragility_score_v0/active_release.json\n",
        encoding="utf-8",
    )
    return root


def _stage_fixture(root: Path, staging_id: str = "fixture_nonempty") -> Path:
    dst = m.staging_dir(root, staging_id)
    shutil.copytree(FIXTURE, dst)
    manifest = json.loads((dst / "source_bundle_manifest.json").read_text(encoding="utf-8"))
    manifest["staging_id"] = staging_id
    (dst / "source_bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dst


def _manifest(path: Path) -> dict[str, object]:
    return json.loads((path / "source_bundle_manifest.json").read_text(encoding="utf-8"))


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    (path / "source_bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    root = _copy_root(tmp_path)
    _stage_fixture(root)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_nonempty", now_utc=FIXED_NOW)
    return root, release_id


def test_verify_staging_accepts_complete_local_bundle(tmp_path: Path) -> None:
    root = _copy_root(tmp_path)
    _stage_fixture(root)
    result = m.verify_staging(root, "fixture_nonempty")
    assert result["status"] == "valid"
    assert result["source_count"] == 5


def test_build_release_writes_canonical_audits_and_score(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    rel = m.release_dir(root, release_id)
    assert (rel / "canonical_input" / "daily_prices" / "SPY.csv").exists()
    assert (rel / "source_attestations.csv").exists()
    assert (rel / "source_coverage_audit.csv").exists()
    assert (rel / "release_quality_gate.csv").exists()
    assert (rel / "fragility_outputs" / "fragility_score_latest_v0.csv").exists()
    assert not m.active_pointer_path(root).exists()
    gate = pd.read_csv(rel / "release_quality_gate.csv")
    assert gate[gate["gate_scope"] == "release"].iloc[0]["quality_gate_status"] == "valid_current"


def test_promote_and_run_active_score_are_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    m.promote_release(root, release_id)
    assert m.active_pointer_path(root).exists()
    receipt = m.run_active_score(root)
    assert receipt["release_id"] == release_id
    assert receipt["market_score_status"] == "valid"
    assert receipt["actionization_allowed"] is False
    assert (root / "market_bomb_fragility_v0" / "active_release_summary.json").exists()


def test_release_cannot_be_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = _build(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="cannot be overwritten"):
        m.build_release(root, "fixture_nonempty", now_utc=FIXED_NOW)


def test_missing_required_source_blocks_staging(tmp_path: Path) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    manifest = _manifest(staged)
    manifest["sources"] = [s for s in manifest["sources"] if s["ticker"] != "VIX3M"]
    _write_manifest(staged, manifest)
    with pytest.raises(SystemExit, match="missing required source"):
        m.verify_staging(root, "fixture_nonempty")


def test_secret_like_manifest_key_is_rejected(tmp_path: Path) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    manifest = _manifest(staged)
    manifest["api_key"] = "redacted"
    _write_manifest(staged, manifest)
    with pytest.raises(SystemExit, match="credential-like"):
        m.verify_staging(root, "fixture_nonempty")


def test_required_source_price_basis_must_be_as_traded_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    manifest = _manifest(staged)
    manifest["sources"][0]["price_basis"] = "adjusted_close"
    _write_manifest(staged, manifest)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_nonempty", now_utc=FIXED_NOW)
    gate = pd.read_csv(m.release_dir(root, release_id) / "release_quality_gate.csv")
    release_row = gate[gate["gate_scope"] == "release"].iloc[0]
    assert release_row["quality_gate_status"] == "data_quality_blocked"
    assert release_row["terms_gate_status"] == "data_quality_blocked"


def test_naive_effective_timestamp_rows_are_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    spy_path = staged / "sources" / "price_spy.csv"
    df = pd.read_csv(spy_path)
    df.loc[0, "effective_available_at_utc"] = "2022-01-03T21:15:00"
    df.head(1).to_csv(spy_path, index=False)
    manifest = _manifest(staged)
    manifest["sources"] = [s for s in manifest["sources"] if s["ticker"] in {"SPY", "QQQ", "VIX", "VIX3M"}]
    _write_manifest(staged, manifest)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", "2022-01-04T00:00:00Z")
    release_id = m.build_release(root, "fixture_nonempty", now_utc="2022-01-04T00:00:00Z")
    inv = pd.read_csv(m.release_dir(root, release_id) / "source_file_inventory.csv")
    spy = inv[inv["ticker"] == "SPY"].iloc[0]
    assert spy["canonical_valid_row_count"] == 0
    assert spy["selected_invalid_row_count"] == 1


def test_missing_effective_timestamp_uses_assumed_medium_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    spy_path = staged / "sources" / "price_spy.csv"
    df = pd.read_csv(spy_path).drop(columns=["effective_available_at_utc"]).head(3)
    df.to_csv(spy_path, index=False)
    manifest = _manifest(staged)
    manifest["sources"] = [s for s in manifest["sources"] if s["ticker"] in {"SPY", "QQQ", "VIX", "VIX3M"}]
    _write_manifest(staged, manifest)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", "2022-01-06T00:00:00Z")
    release_id = m.build_release(root, "fixture_nonempty", now_utc="2022-01-06T00:00:00Z")
    canon = pd.read_csv(m.release_dir(root, release_id) / "canonical_input" / "daily_prices" / "SPY.csv")
    assert set(canon["availability_confidence"]) == {"medium"}
    assert set(canon["availability_basis"]) == {"assumed_nyse_close_plus_15_minutes_v0_2"}


def test_optional_vix9d_absence_does_not_block_market_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    attest = pd.read_csv(m.release_dir(root, release_id) / "source_attestations.csv")
    assert "VIX9D" not in set(attest["ticker"])
    gate = pd.read_csv(m.release_dir(root, release_id) / "release_quality_gate.csv")
    assert gate[gate["gate_scope"] == "release"].iloc[0]["promotion_eligible"] is True or str(gate[gate["gate_scope"] == "release"].iloc[0]["promotion_eligible"]).lower() == "true"
