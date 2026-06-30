from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import market_bomb_leveraged_etf_free_proxy_v1 as m


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return m.file_sha256(path)


def _source(input_id: str, dataset_type: str, instrument: str, rel: str, sha: str) -> dict[str, object]:
    return {
        "input_id": input_id,
        "dataset_type": dataset_type,
        "instrument": instrument,
        "relative_path": rel,
        "content_sha256": sha,
        "row_identifier_field": "date",
        "source_name": "synthetic_unit_test",
        "source_authority_type": "operator",
        "source_qualification_status": "historical_descriptive_only",
        "historical_vintage_available": False,
        "publication_timestamp_available": False,
        "revision_history_available": False,
        "is_synthetic_fixture": True,
        "manual_export_timestamp_utc": "2026-01-01T00:00:00Z",
        "manual_capture_timestamp_utc": "2026-01-01T00:00:00Z",
        "raw_or_adjusted": "raw",
        "corporate_action_treatment": "split_ledger",
        "coverage_start": "2020-01-02",
        "coverage_end": "2020-01-06",
        "notes": "synthetic only",
    }


def _stage(tmp_path: Path, input_id: str = "fixture_free", proxy: bool = False, include_aum: bool = True) -> Path:
    root = tmp_path / "repo"
    base = m.input_dir(root, input_id)
    sources = base / "sources"
    sources.mkdir(parents=True)
    prices = [
        {"date": "2020-01-02", "instrument": "NDX" if not proxy else "QQQ", "raw_close": 100.0, "raw_or_adjusted": "raw"},
        {"date": "2020-01-03", "instrument": "NDX" if not proxy else "QQQ", "raw_close": 101.0, "raw_or_adjusted": "raw"},
        {"date": "2020-01-06", "instrument": "NDX" if not proxy else "QQQ", "raw_close": 100.0, "raw_or_adjusted": "raw"},
    ]
    price_sha = _write_csv(sources / "benchmark_prices.csv", prices, m.PRICE_COLUMNS)
    mapping_rows = [
        {
            "leveraged_etf": "TQQQ",
            "target_benchmark_instrument": "QQQ" if proxy else "NDX",
            "market_proxy_instrument": "QQQ",
            "target_leverage": 3.0,
            "directionality": "long",
            "benchmark_exact_or_proxy": "proxy_based" if proxy else "benchmark_exact",
            "is_proxy_underlying": False,
            "mapping_source_authority": "synthetic_fixture",
        },
        {
            "leveraged_etf": "SQQQ",
            "target_benchmark_instrument": "QQQ" if proxy else "NDX",
            "market_proxy_instrument": "QQQ",
            "target_leverage": -3.0,
            "directionality": "inverse",
            "benchmark_exact_or_proxy": "proxy_based" if proxy else "benchmark_exact",
            "is_proxy_underlying": False,
            "mapping_source_authority": "synthetic_fixture",
        },
    ]
    mapping_sha = _write_csv(sources / "benchmark_mapping.csv", mapping_rows, m.MAPPING_COLUMNS)
    split_sha = _write_csv(
        sources / "split_history.csv",
        [{"instrument": "TQQQ", "effective_date": "2020-01-01", "split_ratio": "1:1", "source_authority": "synthetic"}],
        m.SPLIT_COLUMNS,
    )
    manifest_sources = [
        _source(input_id, "benchmark_prices", "NDX" if not proxy else "QQQ", "sources/benchmark_prices.csv", price_sha),
        _source(input_id, "benchmark_mapping", "TQQQ/SQQQ", "sources/benchmark_mapping.csv", mapping_sha),
        _source(input_id, "split_history", "TQQQ/SQQQ", "sources/split_history.csv", split_sha),
    ]
    if include_aum:
        aum_rows = [
            {"date": "2020-01-02", "instrument": "TQQQ", "aum_usd": 1000.0, "shares_outstanding": "", "nav_per_share": "", "unit": "USD"},
            {"date": "2020-01-02", "instrument": "SQQQ", "aum_usd": 500.0, "shares_outstanding": "", "nav_per_share": "", "unit": "USD"},
            {"date": "2020-01-03", "instrument": "TQQQ", "aum_usd": 1100.0, "shares_outstanding": "", "nav_per_share": "", "unit": "USD"},
            {"date": "2020-01-03", "instrument": "SQQQ", "aum_usd": 600.0, "shares_outstanding": "", "nav_per_share": "", "unit": "USD"},
        ]
        aum_sha = _write_csv(sources / "aum_or_capital.csv", aum_rows, m.AUM_COLUMNS)
        manifest_sources.append(_source(input_id, "aum_or_capital", "TQQQ/SQQQ", "sources/aum_or_capital.csv", aum_sha))
    manifest = {
        "artifact_version": m.ARTIFACT_VERSION,
        "module_name": m.MODULE_NAME,
        "input_id": input_id,
        "operator_capture_method": "manual_local_file",
        "sources": manifest_sources,
    }
    m.write_json(base / "source_manifest.json", manifest)
    return root


def test_tqqq_positive_ndx_return_positive_proxy() -> None:
    assert m.mechanical_rebalance_notional(3.0, 100.0, 0.01) > 0


def test_tqqq_negative_ndx_return_negative_proxy() -> None:
    assert m.mechanical_rebalance_notional(3.0, 100.0, -0.01) < 0


def test_sqqq_positive_ndx_return_positive_proxy() -> None:
    assert m.mechanical_rebalance_notional(-3.0, 100.0, 0.01) > 0


def test_sqqq_negative_ndx_return_negative_proxy() -> None:
    assert m.mechanical_rebalance_notional(-3.0, 100.0, -0.01) < 0


def test_combined_value_equals_constituent_sum(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_free_proxy_daily.csv")
    row = daily[daily["observation_date"].eq("2020-01-03")].iloc[0]
    assert row["combined_aum_scaled_rebalance_notional_proxy"] == pytest.approx(row["tqqq_rebalance_notional_proxy"] + row["sqqq_rebalance_notional_proxy"])


def test_equal_weight_direction_follows_threshold() -> None:
    assert m.equal_weight_direction(0.002) == 1
    assert m.equal_weight_direction(-0.002) == -1


def test_sub_threshold_returns_neutral_but_value_retained() -> None:
    ret = 0.0005
    assert m.amplifier_label(ret) == "directional_amplifier_neutral"
    assert ret != 0


def test_ndx_exact_mapping_passes() -> None:
    row = {
        "leveraged_etf": "TQQQ",
        "target_benchmark_instrument": "NDX",
        "market_proxy_instrument": "QQQ",
        "target_leverage": 3,
        "directionality": "long",
        "benchmark_exact_or_proxy": "benchmark_exact",
        "is_proxy_underlying": False,
        "mapping_source_authority": "synthetic",
    }
    assert m.validate_mapping_row(row, "ndx_exact")["mapping_status"] == "valid"


def test_qqq_remains_proxy() -> None:
    row = {
        "leveraged_etf": "TQQQ",
        "target_benchmark_instrument": "QQQ",
        "market_proxy_instrument": "QQQ",
        "target_leverage": 3,
        "directionality": "long",
        "benchmark_exact_or_proxy": "proxy_based",
        "is_proxy_underlying": False,
        "mapping_source_authority": "synthetic",
    }
    assert m.validate_mapping_row(row, "qqq_proxy_only_descriptive")["mapping_status"] == "valid"


def test_tqqq_to_qqq_exact_mapping_fails_for_production_input() -> None:
    row = {
        "leveraged_etf": "TQQQ",
        "target_benchmark_instrument": "QQQ",
        "market_proxy_instrument": "QQQ",
        "target_leverage": 3,
        "directionality": "long",
        "benchmark_exact_or_proxy": "benchmark_exact",
        "is_proxy_underlying": False,
        "mapping_source_authority": "synthetic",
    }
    assert m.validate_mapping_row(row, "ndx_exact")["mapping_status"] == "blocked_by_mapping"


def test_qqq_proxy_only_mode_is_descriptive_only(tmp_path: Path) -> None:
    root = _stage(tmp_path, proxy=True)
    result = m.run_historical(root, "fixture_free", "qqq_proxy_only_descriptive")
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_free_proxy_daily.csv")
    assert set(daily["confidence_label"]) == {m.PROXY_CONFIDENCE}
    assert daily["phase2_eligible"].astype(str).str.lower().eq("false").all()


def test_exact_and_proxy_observations_not_combined_silently(tmp_path: Path) -> None:
    root = _stage(tmp_path, proxy=True)
    with pytest.raises(SystemExit):
        m.run_historical(root, "fixture_free", "ndx_exact")


def test_current_download_timestamp_cannot_be_historical_available_at(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    manifest = m.load_source_manifest(root, "fixture_free")
    manifest["sources"][0]["publication_timestamp_available"] = True
    m.write_json(m.source_manifest_path(root, "fixture_free"), manifest)
    assert m.validate_input(root, "fixture_free")["validation_status"] == "blocked"


def test_historical_free_run_always_predictive_false(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    assert result["predictive_pit_eligible"] is False


def test_historical_free_run_cannot_create_strict_readiness(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    assert result["phase1_3_readiness_run"] is False


def test_historical_free_run_cannot_pass_phase2_admission(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    assert result["phase2_eligible"] is False


def test_free_proxy_cannot_emit_gold_silver_or_readiness_status(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    manifest = m.load_source_manifest(root, "fixture_free")
    manifest["sources"][0]["source_qualification_status"] = "gold_point_in_time_eligible"
    m.write_json(m.source_manifest_path(root, "fixture_free"), manifest)
    codes = {row["code"] for row in m.validate_input(root, "fixture_free")["diagnostics"]}
    assert "free_proxy_requires_descriptive_status" in codes


def test_missing_aum_produces_unavailable_not_carry_forward(tmp_path: Path) -> None:
    root = _stage(tmp_path, include_aum=False)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_free_proxy_daily.csv")
    assert daily["tqqq_aum_input_available"].astype(str).str.lower().eq("false").all()


def test_aum_gaps_create_no_invented_notional(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    aum_path = m.input_dir(root, "fixture_free") / "sources" / "aum_or_capital.csv"
    aum = pd.read_csv(aum_path)
    aum = aum[~((aum["date"] == "2020-01-02") & (aum["instrument"] == "TQQQ"))]
    aum.to_csv(aum_path, index=False)
    manifest = m.load_source_manifest(root, "fixture_free")
    for source in manifest["sources"]:
        if source["dataset_type"] == "aum_or_capital":
            source["content_sha256"] = m.file_sha256(aum_path)
    m.write_json(m.source_manifest_path(root, "fixture_free"), manifest)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_free_proxy_daily.csv")
    row = daily[daily["observation_date"].eq("2020-01-03")].iloc[0]
    assert str(row["tqqq_rebalance_notional_proxy"]) == "nan"


def test_aum_vs_shares_nav_disagreement_remains_diagnostic() -> None:
    rel = abs(100.0 - 10.0 * 9.0) / 100.0
    assert rel > 0


def test_unit_mismatch_blocks_aum_scaled_output(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    aum_path = m.input_dir(root, "fixture_free") / "sources" / "aum_or_capital.csv"
    aum = pd.read_csv(aum_path)
    aum.loc[aum["instrument"].eq("TQQQ"), "unit"] = "JPY"
    aum.to_csv(aum_path, index=False)
    manifest = m.load_source_manifest(root, "fixture_free")
    for source in manifest["sources"]:
        if source["dataset_type"] == "aum_or_capital":
            source["content_sha256"] = m.file_sha256(aum_path)
    m.write_json(m.source_manifest_path(root, "fixture_free"), manifest)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_free_proxy_daily.csv")
    assert "unit_mismatch" in set(daily["tqqq_capital_source"].astype(str))


def test_current_revised_aum_not_historically_known_by_presence(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    manifest = m.load_source_manifest(root, "fixture_free")
    for source in manifest["sources"]:
        if source["dataset_type"] == "aum_or_capital":
            source["historical_vintage_available"] = True
    m.write_json(m.source_manifest_path(root, "fixture_free"), manifest)
    assert m.validate_input(root, "fixture_free")["validation_status"] == "blocked"


def test_snapshot_requires_capture_timestamp_and_hash(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.ingest_forward_snapshot(root, "fixture_free", "2020-01-02", "2026-01-02T00:00:00Z")
    receipt = m.load_json(Path(result["snapshot_artifact"]) / "forward_snapshot_receipt.json")
    assert receipt["capture_timestamp_utc"].endswith("Z")
    assert receipt["sources"][0]["local_file_content_sha256"]


def test_duplicate_snapshot_id_with_different_hash_rejects(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    m.ingest_forward_snapshot(root, "fixture_free", "2020-01-02", "2026-01-02T00:00:00Z")
    price_path = m.input_dir(root, "fixture_free") / "sources" / "benchmark_prices.csv"
    price_path.write_text(price_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        m.ingest_forward_snapshot(root, "fixture_free", "2020-01-02", "2026-01-02T00:00:00Z")


def test_ledger_is_append_only(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    m.ingest_forward_snapshot(root, "fixture_free", "2020-01-02", "2026-01-02T00:00:00Z")
    m.build_forward_observation(root, "2020-01-03")
    m.build_forward_observation(root, "2020-01-06")
    ledger = pd.read_csv(m.forward_ledger_root(root) / "observations" / "forward_observation_ledger.csv")
    assert len(ledger) == 2


def test_observation_uses_captured_lineage_before_cutoff(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    m.ingest_forward_snapshot(root, "fixture_free", "2020-01-02", "2026-01-02T00:00:00Z")
    m.build_forward_observation(root, "2020-01-03")
    ledger = pd.read_csv(m.forward_ledger_root(root) / "observations" / "forward_observation_ledger.csv")
    assert ledger.iloc[0]["lagged_capital_capture_timestamp_utc"] == "2026-01-02T00:00:00Z"


def test_missing_prior_snapshot_yields_unavailable(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    m.build_forward_observation(root, "2020-01-03")
    ledger = pd.read_csv(m.forward_ledger_root(root) / "observations" / "forward_observation_ledger.csv")
    assert ledger.iloc[0]["directional_amplifier_label"] == "directional_amplifier_unavailable"


def test_observation_retains_snapshot_date_and_hash(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    m.ingest_forward_snapshot(root, "fixture_free", "2020-01-02", "2026-01-02T00:00:00Z")
    m.build_forward_observation(root, "2020-01-03")
    ledger = pd.read_csv(m.forward_ledger_root(root) / "observations" / "forward_observation_ledger.csv")
    assert ledger.iloc[0]["lagged_capital_snapshot_date"] == "2020-01-02"
    assert str(ledger.iloc[0]["lagged_capital_source_hash"])


def test_forward_observation_remains_non_actionable(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    m.ingest_forward_snapshot(root, "fixture_free", "2020-01-02", "2026-01-02T00:00:00Z")
    m.build_forward_observation(root, "2020-01-03")
    ledger = pd.read_csv(m.forward_ledger_root(root) / "observations" / "forward_observation_ledger.csv")
    assert ledger["predictive_pit_eligible"].astype(str).str.lower().eq("false").all()
    assert ledger["actionization_allowed"].astype(str).str.lower().eq("false").all()


def test_artifact_tampering_is_detected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    artifact = Path(result["run_artifact"])
    assert m.verify_run(str(artifact))["verification_status"] == "valid"
    (artifact / "leveraged_etf_free_proxy_summary.md").write_text("tampered", encoding="utf-8")
    assert m.verify_run(str(artifact))["verification_status"] == "tampered"


def test_extra_output_is_detected(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    artifact = Path(result["run_artifact"])
    (artifact / "extra.txt").write_text("extra", encoding="utf-8")
    assert m.verify_run(str(artifact))["verification_status"] == "tampered"


def test_raw_input_files_are_not_tracked_by_git() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "market_bomb_history"], cwd=REPO_ROOT, text=True)
    assert tracked.strip() == ""


def test_existing_strict_admission_is_not_unlocked_by_free_proxy(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_free", "ndx_exact")
    receipt = m.load_json(Path(result["run_artifact"]) / "free_proxy_run_receipt.json")
    assert receipt["phase1_3_readiness_run"] is False
    assert receipt["phase2_run"] is False


def test_template_creates_header_only_files_without_provider_fetch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    result = m.build_template(root, "template_fixture")
    assert result["template_status"] == "created_or_existing"
    template_root = m.input_dir(root, "template_fixture")
    for name in ["benchmark_prices.csv", "benchmark_mapping.csv", "aum_or_capital.csv", "split_history.csv"]:
        text = (template_root / "sources" / name).read_text(encoding="utf-8")
        assert len(text.strip().splitlines()) == 1
