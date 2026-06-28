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


def _write_csv(path: Path, df: pd.DataFrame) -> str:
    df.to_csv(path, index=False)
    return m.file_sha256(path)


def _contract_source(source_id: str, dataset_type: str, rel: str, instrument: str, module: str, sha: str) -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_name": "unit_test_local_csv",
        "source_file": rel,
        "relative_path": rel,
        "dataset_type": dataset_type,
        "dataset_version": "unit_test_v1",
        "coverage_start_date": "2020-01-02",
        "coverage_end_date": "2020-02-20",
        "timezone": "UTC",
        "row_identifier_field": "source_row_id",
        "content_sha256": sha,
        "is_synthetic_fixture": True,
        "source_as_of_timestamp": "2020-02-20T21:30:00Z",
        "available_at_timestamp": "2020-02-20T21:45:00Z",
        "market_timestamp": "2020-02-20T21:00:00Z",
        "instrument": instrument,
        "asset_class": "synthetic",
        "module": module,
    }


def _daily_price_contract(ticker: str, start: str = "2020-01-02", n: int = 36, base: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=n)
    close = [base + i * step + (i % 5) * 0.15 for i in range(n)]
    rows = []
    for i, (date, px) in enumerate(zip(dates, close)):
        market_ts = pd.Timestamp(date).tz_localize("UTC") + pd.Timedelta(hours=21)
        available = market_ts + pd.Timedelta(minutes=45)
        rows.append(
            {
                "source_row_id": f"{ticker}_D_{i:03d}",
                "instrument": ticker,
                "asset_class": "equity_index_etf",
                "market": "US",
                "market_timestamp": market_ts.isoformat().replace("+00:00", "Z"),
                "available_at_timestamp": available.isoformat().replace("+00:00", "Z"),
                "source_as_of_timestamp": market_ts.isoformat().replace("+00:00", "Z"),
                "session_date": date.strftime("%Y-%m-%d"),
                "open": px - 0.2,
                "high": px + 0.4,
                "low": px - 0.5,
                "close": px,
                "adjusted_close": px,
                "volume": 1000000 + i,
                "currency": "USD",
                "source_name": "unit_test_local_csv",
                "source_file": "prices_daily.csv",
                "dataset_version": "unit_test_v1",
            }
        )
    return pd.DataFrame(rows)


def _vol_returns_contract(ticker: str = "QQQ", start: str = "2020-01-02", n: int = 36) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=n)
    returns = [0.002 + ((i % 7) - 3) * 0.001 for i in range(n)]
    rows = []
    for i, (date, ret) in enumerate(zip(dates, returns)):
        end_ts = pd.Timestamp(date).tz_localize("UTC") + pd.Timedelta(hours=21)
        rows.append(
            {
                "source_row_id": f"{ticker}_R_{i:03d}",
                "instrument": ticker,
                "asset_class": "equity_index_etf",
                "market": "US",
                "return_start_timestamp": (end_ts - pd.Timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "return_end_timestamp": end_ts.isoformat().replace("+00:00", "Z"),
                "available_at_timestamp": (end_ts + pd.Timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
                "source_as_of_timestamp": end_ts.isoformat().replace("+00:00", "Z"),
                "simple_return": ret,
                "log_return": "",
                "price_basis": "adjusted_close",
                "source_name": "unit_test_local_csv",
                "source_file": "vol_control_returns.csv",
                "dataset_version": "unit_test_v1",
            }
        )
    return pd.DataFrame(rows)


def _aum_contract() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_row_id": "AUM_TQQQ_001",
                "etf_instrument": "TQQQ",
                "as_of_timestamp": "2020-02-20T21:00:00Z",
                "available_at_timestamp": "2020-02-20T21:30:00Z",
                "source_as_of_timestamp": "2020-02-20T21:00:00Z",
                "aum_usd": 1000000000.0,
                "shares_outstanding": "",
                "nav_per_share": "",
                "currency": "USD",
                "publication_status": "published",
                "valid_until_timestamp": "2020-02-24T21:30:00Z",
                "source_name": "unit_test_local_csv",
                "source_file": "leveraged_etf_aum.csv",
                "dataset_version": "unit_test_v1",
            },
            {
                "source_row_id": "AUM_SQQQ_001",
                "etf_instrument": "SQQQ",
                "as_of_timestamp": "2020-02-20T21:00:00Z",
                "available_at_timestamp": "2020-02-20T21:30:00Z",
                "source_as_of_timestamp": "2020-02-20T21:00:00Z",
                "aum_usd": 700000000.0,
                "shares_outstanding": "",
                "nav_per_share": "",
                "currency": "USD",
                "publication_status": "published",
                "valid_until_timestamp": "2020-02-24T21:30:00Z",
                "source_name": "unit_test_local_csv",
                "source_file": "leveraged_etf_aum.csv",
                "dataset_version": "unit_test_v1",
            },
        ]
    )


def _reference_contract() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_row_id": "REF_TQQQ_001",
                "etf_instrument": "TQQQ",
                "underlying_instrument": "QQQ",
                "target_leverage": 3.0,
                "directionality": "long",
                "asset_class": "leveraged_etf",
                "market": "US",
                "effective_start_timestamp": "2019-01-01T00:00:00Z",
                "effective_end_timestamp": "",
                "available_at_timestamp": "2019-01-01T00:00:00Z",
                "source_as_of_timestamp": "2019-01-01T00:00:00Z",
                "source_name": "unit_test_local_csv",
                "source_file": "leveraged_etf_reference.csv",
                "dataset_version": "unit_test_v1",
            },
            {
                "source_row_id": "REF_SQQQ_001",
                "etf_instrument": "SQQQ",
                "underlying_instrument": "QQQ",
                "target_leverage": -3.0,
                "directionality": "inverse",
                "asset_class": "leveraged_etf",
                "market": "US",
                "effective_start_timestamp": "2019-01-01T00:00:00Z",
                "effective_end_timestamp": "",
                "available_at_timestamp": "2019-01-01T00:00:00Z",
                "source_as_of_timestamp": "2019-01-01T00:00:00Z",
                "source_name": "unit_test_local_csv",
                "source_file": "leveraged_etf_reference.csv",
                "dataset_version": "unit_test_v1",
            },
        ]
    )


def _stage(root: Path, staging_id: str = "fixture_flow") -> Path:
    stage = m.staging_dir(root, staging_id)
    (stage / "sources").mkdir(parents=True)
    sources = []
    files = [
        ("prices_daily", "prices_daily", "sources/prices_daily.csv", "QQQ", "vol_control_deleveraging", pd.concat([_daily_price_contract("QQQ", base=100, step=0.7), _daily_price_contract("SPY", base=300, step=0.5)], ignore_index=True)),
        ("leveraged_etf_reference", "leveraged_etf_reference", "sources/leveraged_etf_reference.csv", "TQQQ", "leveraged_etf_rebalance", _reference_contract()),
        ("leveraged_etf_aum", "leveraged_etf_aum", "sources/leveraged_etf_aum.csv", "TQQQ", "leveraged_etf_rebalance", _aum_contract()),
        ("vol_control_returns", "vol_control_returns", "sources/vol_control_returns.csv", "QQQ", "vol_control_deleveraging", _vol_returns_contract("QQQ")),
    ]
    for source_id, dataset_type, rel, instrument, module, df in files:
        sha = _write_csv(stage / rel, df)
        sources.append(_contract_source(source_id, dataset_type, rel, instrument, module, sha))
    manifest = {
        "artifact_version": "flow_pressure_research_v0_fixture",
        "source_contract_version": "flow_provider_contract_v1",
        "staging_id": staging_id,
        "research_timing_class": "eod_next_session",
        "decision_time_specification": {"type": "explicit_utc_timestamp", "decision_time": FIXED_NOW},
        "operator_attestation": {"personal_research_only": True},
        "sources": sources,
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
    result = m.validate_flow_provider_contract(root, "fixture_flow", FIXED_NOW, "eod_next_session")
    assert result["validation_status"] == "blocked"
    assert any(row["code"] == "duplicate_relative_path" for row in result["diagnostics"])
    with pytest.raises(SystemExit, match="provider contract blocked"):
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
    result = m.validate_flow_provider_contract(root, "fixture_flow", FIXED_NOW, "eod_next_session")
    assert any(row["code"] == "unknown_timezone" for row in result["diagnostics"])
    manifest["sources"][0]["available_at_timestamp"] = "2020-02-21T21:45:00Z"
    _write_manifest(stage, manifest)
    result = m.validate_flow_provider_contract(root, "fixture_flow", FIXED_NOW, "eod_next_session")
    assert any(row["code"] == "available_after_decision_time" for row in result["diagnostics"])


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


def test_build_flow_staging_template_creates_header_only_contract(tmp_path: Path) -> None:
    root = _root(tmp_path)
    result = m.build_flow_staging_template(root, "template_stage")
    stage = m.staging_dir(root, "template_stage")
    assert result["source_contract_version"] == "flow_provider_contract_v1"
    manifest = _manifest(stage)
    assert manifest["source_contract_version"] == "flow_provider_contract_v1"
    assert all(source["is_synthetic_fixture"] is True for source in manifest["sources"])
    assert pd.read_csv(stage / "sources" / "prices_daily.csv").empty
    with pytest.raises(SystemExit, match="not empty"):
        m.build_flow_staging_template(root, "template_stage")


def test_validate_flow_provider_contract_hash_missing_column_and_undeclared_file(tmp_path: Path) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    manifest = _manifest(stage)
    manifest["sources"][0]["content_sha256"] = "0" * 64
    _write_manifest(stage, manifest)
    result = m.validate_flow_provider_contract(root, "fixture_flow", FIXED_NOW, "eod_next_session")
    assert any(row["code"] == "source_hash_mismatch" for row in result["diagnostics"])
    manifest = _manifest(stage)
    path = stage / manifest["sources"][0]["relative_path"]
    df = pd.read_csv(path).drop(columns=["close"])
    df.to_csv(path, index=False)
    manifest["sources"][0]["content_sha256"] = m.file_sha256(path)
    _write_manifest(stage, manifest)
    (stage / "sources" / "undeclared.csv").write_text("x\n1\n", encoding="utf-8")
    result = m.validate_flow_provider_contract(root, "fixture_flow", FIXED_NOW, "eod_next_session")
    assert any(row["code"] == "missing_required_columns" for row in result["diagnostics"])
    assert any(row["code"] == "undeclared_source_file" for row in result["diagnostics"])


def test_intraday_close_window_rejects_daily_only_data(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _stage(root)
    result = m.validate_flow_provider_contract(root, "fixture_flow", FIXED_NOW, "intraday_close_window")
    assert result["validation_status"] == "blocked"
    assert any(row["code"] == "daily_data_not_close_window_eligible" for row in result["diagnostics"])


def test_aum_validity_window_and_stale_observation_are_timing_ineligible(tmp_path: Path) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    manifest = _manifest(stage)
    aum_source = next(s for s in manifest["sources"] if s["dataset_type"] == "leveraged_etf_aum")
    path = stage / aum_source["relative_path"]
    df = pd.read_csv(path)
    df["valid_until_timestamp"] = "2020-02-20T21:00:00Z"
    df.to_csv(path, index=False)
    aum_source["content_sha256"] = m.file_sha256(path)
    _write_manifest(stage, manifest)
    audit = m.audit_flow_timing(root, "fixture_flow", FIXED_NOW, "eod_next_session")
    assert audit["timing_ineligible_count"] >= 1
    assert any(row["timing_reason"] == "stale_observation" for row in audit["timing_audit"])


def test_leveraged_etf_contract_outputs_long_and_inverse_lineage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    _stage(root)
    monkeypatch.setenv("FLOW_PRESSURE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_flow", now_utc=FIXED_NOW, research_timing_class="eod_next_session")
    features = pd.read_csv(m.release_dir(root, release_id) / "features" / "flow_pressure_features.csv")
    lev = features[(features["module"] == "leveraged_etf_rebalance") & (features["feature_state"] == "available")]
    assert {"TQQQ", "SQQQ"}.issubset(set(lev["etf_instrument"].dropna()))
    assert lev["selected_aum_source_row_id"].dropna().astype(str).str.startswith("AUM_").any()
    assert lev["is_observed_flow"].fillna(False).astype(bool).sum() == 0
    assert lev["is_model_estimate"].fillna(False).astype(bool).all()


def test_vol_control_contract_blocks_incomplete_return_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    manifest = _manifest(stage)
    ret_source = next(s for s in manifest["sources"] if s["dataset_type"] == "vol_control_returns")
    path = stage / ret_source["relative_path"]
    df = pd.read_csv(path).iloc[:3]
    df.to_csv(path, index=False)
    ret_source["content_sha256"] = m.file_sha256(path)
    _write_manifest(stage, manifest)
    monkeypatch.setenv("FLOW_PRESSURE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_flow", now_utc=FIXED_NOW, research_timing_class="eod_next_session")
    gate = pd.read_csv(m.release_dir(root, release_id) / "feature_quality_gate.csv")
    release_row = gate[gate["gate_scope"] == "release"].iloc[0]
    assert release_row["quality_gate_status"] == "insufficient_coverage"


def test_timing_audit_hash_is_sealed_and_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    _stage(root)
    monkeypatch.setenv("FLOW_PRESSURE_NOW_UTC", FIXED_NOW)
    release_id = m.build_release(root, "fixture_flow", now_utc=FIXED_NOW, research_timing_class="eod_next_session")
    rel = m.release_dir(root, release_id)
    (rel / "timing_audit.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="timing audit hash mismatch|release core sha mismatch"):
        m.verify_release(root, release_id)


def test_cta_dealer_inputs_are_methodology_incomplete(tmp_path: Path) -> None:
    root = _root(tmp_path)
    stage = _stage(root)
    manifest = _manifest(stage)
    src = manifest["sources"][0].copy()
    src["source_id"] = "cta_attempt"
    src["module"] = "cta_trend_flow"
    src["dataset_type"] = "prices_daily"
    src["relative_path"] = manifest["sources"][0]["relative_path"]
    manifest["sources"] = [src]
    _write_manifest(stage, manifest)
    result = m.validate_flow_provider_contract(root, "fixture_flow", FIXED_NOW, "eod_next_session")
    assert result["validation_status"] == "blocked"
    assert any(row["code"] == "methodology_incomplete" for row in result["diagnostics"])
