from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

import market_bomb_fragility_data_release_v0 as m


ROOT = Path(__file__).resolve().parents[1]
SHORT_FIXTURE = ROOT / "tests" / "fixtures" / "fragility_data_release_v0_nonempty"
CLEAN_FIXTURE = ROOT / "tests" / "fixtures" / "fragility_data_release_v0_2_1_clean"
FIXED_NOW = "2017-09-20T00:00:00Z"


def _copy_root(tmp_path: Path, clean_calendar: bool = True) -> Path:
    root = tmp_path / "repo"
    (root / "market_bomb_config").mkdir(parents=True)
    calendar_src = CLEAN_FIXTURE / "market_bomb_config" / "nyse_regular_sessions_v1.csv" if clean_calendar else ROOT / "market_bomb_config" / "nyse_regular_sessions_v1.csv"
    shutil.copyfile(calendar_src, root / "market_bomb_config" / "nyse_regular_sessions_v1.csv")
    for name in [
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


def _stage_fixture(root: Path, staging_id: str = "fixture_clean", clean: bool = True) -> Path:
    dst = m.staging_dir(root, staging_id)
    src = (CLEAN_FIXTURE / "staging" / "fixture_clean") if clean else SHORT_FIXTURE
    shutil.copytree(src, dst)
    manifest = json.loads((dst / "source_bundle_manifest.json").read_text(encoding="utf-8"))
    manifest["staging_id"] = staging_id
    (dst / "source_bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dst


def _manifest(path: Path) -> dict[str, object]:
    return json.loads((path / "source_bundle_manifest.json").read_text(encoding="utf-8"))


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    (path / "source_bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_calendar: bool = True, clean_stage: bool = True, now_utc: str = FIXED_NOW) -> tuple[Path, str]:
    root = _copy_root(tmp_path, clean_calendar=clean_calendar)
    _stage_fixture(root, clean=clean_stage)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", now_utc)
    release_id = m.build_release(root, "fixture_clean", now_utc=now_utc)
    return root, release_id


def _release_row(root: Path, release_id: str) -> pd.Series:
    gate = pd.read_csv(m.release_dir(root, release_id) / "release_quality_gate.csv")
    return gate[gate["gate_scope"] == "release"].iloc[0]


def test_clean_release_builds_valid_current_with_immutable_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    rel = m.release_dir(root, release_id)
    assert (rel / "preflight_fragility_outputs" / "fragility_score_latest_v0.csv").exists()
    assert not (rel / "fragility_outputs").exists()
    assert (rel / "release_content_manifest.json").exists()
    receipt = m.verify_release(root, release_id)
    assert receipt["release_quality_status"] == "valid_current"
    assert receipt["promotion_eligible_default"] is True
    assert receipt["actionization_allowed"] is False
    assert not m.active_pointer_path(root).exists()


def test_verify_release_is_independent_from_staging_after_delete_and_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    staged = m.staging_dir(root, "fixture_clean")
    shutil.rmtree(staged)
    assert m.verify_release(root, release_id)["release_id"] == release_id
    _stage_fixture(root)
    spy = staged / "sources" / "price_spy.csv"
    spy.write_text(spy.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert m.verify_release(root, release_id)["release_id"] == release_id


def test_verify_release_detects_canonical_audit_and_preflight_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    rel = m.release_dir(root, release_id)
    for path in [
        rel / "canonical_input" / "daily_prices" / "SPY.csv",
        rel / "source_coverage_audit.csv",
        rel / "preflight_fragility_outputs" / "fragility_score_manifest_v0.json",
    ]:
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            m.verify_release(root, release_id)
        path.write_text(original, encoding="utf-8")
        assert m.verify_release(root, release_id)["release_id"] == release_id


def test_run_score_creates_append_only_execution_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    first = m.run_score(root, release_id, strict=True)
    second = m.run_score(root, release_id, strict=True)
    assert first["execution_id"] != second["execution_id"]
    rel = m.release_dir(root, release_id)
    assert m.platform_write_path(rel / "executions" / first["execution_id"] / "fragility_outputs" / "fragility_score_latest_v0.csv").exists()
    assert m.platform_write_path(rel / "executions" / second["execution_id"] / "execution_content_manifest.json").exists()
    manifest_entries = json.loads((rel / "release_content_manifest.json").read_text(encoding="utf-8"))["entries"]
    assert not any(str(e["relative_path"]).startswith("executions/") for e in manifest_entries)
    assert first["release_core_content_set_sha256"] == json.loads((rel / "release_receipt.json").read_text(encoding="utf-8"))["release_core_content_set_sha256"]


def test_calendar_policy_short_repo_calendar_blocks_even_with_allow_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch, clean_calendar=False, clean_stage=False, now_utc="2023-09-20T00:00:00Z")
    row = _release_row(root, release_id)
    assert row["quality_gate_status"] == "data_quality_blocked"
    assert row["calendar_policy_gate_status"] == "data_quality_blocked"
    assert row["quality_gate_reason"] == "calendar_contract_insufficient_for_policy"
    with pytest.raises(SystemExit):
        m.promote_release(root, release_id, allow_stale=True)


def test_policy_start_date_is_not_relaxed_to_calendar_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch, clean_calendar=False, clean_stage=False, now_utc="2023-09-20T00:00:00Z")
    coverage = pd.read_csv(m.release_dir(root, release_id) / "source_coverage_audit.csv")
    assert set(coverage["minimum_required_start_date"]) == {"2016-01-01"}
    assert (coverage["actual_first_valid_session_date"] > "2016-01-01").all()


def test_latest_required_late_effective_timestamp_blocks_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    vix3m_path = staged / "sources" / "vol_vix3m.csv"
    df = pd.read_csv(vix3m_path)
    last_idx = df.index[-1]
    df.loc[last_idx, "effective_available_at_utc"] = "2017-09-20T00:00:00Z"
    df.to_csv(vix3m_path, index=False)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_clean", now_utc=FIXED_NOW)
    rel = m.release_dir(root, release_id)
    timing = pd.read_csv(rel / "source_timeliness_audit.csv")
    late = timing[timing["source_row_timeliness_status"] == "unavailable_coverage_late_effective_timestamp"]
    assert not late.empty
    coverage = pd.read_csv(rel / "source_coverage_audit.csv")
    vix3m = coverage[coverage["ticker"] == "VIX3M"].iloc[0]
    assert str(vix3m["latest_completed_session_timely_source_present"]).lower() == "false"
    assert _release_row(root, release_id)["promotion_eligible_with_stale_override"] is False or str(_release_row(root, release_id)["promotion_eligible_with_stale_override"]).lower() == "false"


def test_late_row_inside_recent_252_window_blocks_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    vix_path = staged / "sources" / "vol_vix.csv"
    df = pd.read_csv(vix_path)
    df.loc[len(df) - 10, "effective_available_at_utc"] = "2017-09-20T00:00:00Z"
    df.to_csv(vix_path, index=False)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_clean", now_utc=FIXED_NOW)
    coverage = pd.read_csv(m.release_dir(root, release_id) / "source_coverage_audit.csv")
    vix = coverage[coverage["ticker"] == "VIX"].iloc[0]
    assert str(vix["recent_252_session_timely_complete"]).lower() == "false"
    assert _release_row(root, release_id)["quality_gate_status"] == "data_quality_blocked"


def test_timestamp_equal_to_decision_and_policy_assumed_rows_are_timely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    spy_path = staged / "sources" / "price_spy.csv"
    df = pd.read_csv(spy_path)
    decision = df.loc[0, "effective_available_at_utc"]
    df.loc[0, "effective_available_at_utc"] = decision
    df = df.drop(columns=["effective_available_at_utc"])
    df.head(3).to_csv(spy_path, index=False)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", "2016-01-06T23:00:00Z")
    release_id = m.build_release(root, "fixture_clean", now_utc="2016-01-06T23:00:00Z")
    timing = pd.read_csv(m.release_dir(root, release_id) / "source_timeliness_audit.csv")
    spy = timing[timing["ticker"] == "SPY"]
    assert set(spy["source_row_timeliness_status"]) == {"valid_timely"}
    canon = pd.read_csv(m.release_dir(root, release_id) / "canonical_input" / "daily_prices" / "SPY.csv")
    assert set(canon["availability_confidence"]) == {"medium"}


def test_early_close_policy_assumed_timestamp_uses_calendar_close_plus_15(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    spy_path = staged / "sources" / "price_spy.csv"
    df = pd.read_csv(spy_path)
    df = df[df["session_date"] == "2016-07-01"].drop(columns=["effective_available_at_utc"])
    df.to_csv(spy_path, index=False)
    manifest = _manifest(staged)
    manifest["sources"] = [s for s in manifest["sources"] if s["ticker"] in {"SPY", "QQQ", "VIX", "VIX3M"}]
    _write_manifest(staged, manifest)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", "2016-07-02T00:00:00Z")
    release_id = m.build_release(root, "fixture_clean", now_utc="2016-07-02T00:00:00Z")
    canon = pd.read_csv(m.release_dir(root, release_id) / "canonical_input" / "daily_prices" / "SPY.csv")
    assert canon.iloc[0]["effective_available_at_utc"] == "2016-07-01T17:15:00Z"


def test_optional_vix9d_absence_does_not_block_market_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    attest = pd.read_csv(m.release_dir(root, release_id) / "source_attestations.csv")
    assert "VIX9D" not in set(attest["ticker"])
    assert _release_row(root, release_id)["quality_gate_status"] == "valid_current"


def test_stale_only_release_and_stale_promotion_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    for source in (staged / "sources").glob("*.csv"):
        df = pd.read_csv(source)
        df.iloc[:-3].to_csv(source, index=False)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_clean", now_utc=FIXED_NOW)
    row = _release_row(root, release_id)
    assert row["quality_gate_status"] == "valid_historical_but_stale"
    assert str(row["promotion_eligible_default"]).lower() == "false"
    assert str(row["promotion_eligible_with_stale_override"]).lower() == "true"
    with pytest.raises(SystemExit):
        m.promote_release(root, release_id)
    m.promote_release(root, release_id, allow_stale=True)
    pointer = json.loads(m.active_pointer_path(root).read_text(encoding="utf-8"))
    assert pointer["stale_override_used"] is True
    assert pointer["market_state_freshness_label"] == "stale_historical_not_current"


def test_active_release_runtime_staleness_fails_default_and_allows_explicit_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, release_id = _build(tmp_path, monkeypatch)
    m.promote_release(root, release_id)
    with pytest.raises(SystemExit, match="active_release_stale_at_runtime"):
        m.run_active_score(root, now_utc="2017-09-23T00:00:00Z")
    receipt = m.run_active_score(root, allow_stale=True, now_utc="2017-09-23T00:00:00Z")
    assert receipt["runtime_freshness_status"] == "stale_historical_not_current"
    summary = json.loads((root / "market_bomb_fragility_v0" / "active_release_summary.json").read_text(encoding="utf-8"))
    assert "NOT CURRENT MARKET STATE" in summary["warning"]


def test_hard_blocked_release_cannot_promote_with_allow_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_root(tmp_path)
    staged = _stage_fixture(root)
    manifest = _manifest(staged)
    manifest["sources"][0]["price_basis"] = "adjusted_close"
    _write_manifest(staged, manifest)
    monkeypatch.setenv("FRAGILITY_RELEASE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_clean", now_utc=FIXED_NOW)
    assert _release_row(root, release_id)["quality_gate_status"] == "data_quality_blocked"
    with pytest.raises(SystemExit):
        m.promote_release(root, release_id, allow_stale=True)
