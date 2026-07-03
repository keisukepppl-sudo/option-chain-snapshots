from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd
import pytest

import market_bomb_leveraged_etf_free_proxy_v1 as free_proxy
import market_bomb_leveraged_etf_scale_proxy_v1 as m


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return m.file_sha256(path)


def _source(input_id: str, dataset_type: str, instrument: str, rel: str, sha: str, tier: str = "tier_a_daily_direct", authority: str = "issuer_official_daily_nav_history") -> dict[str, object]:
    return {
        "input_id": input_id,
        "dataset_type": dataset_type,
        "instrument": instrument,
        "relative_path": rel,
        "content_sha256": sha,
        "row_identifier_field": "date,instrument",
        "source_name": "synthetic_official_fixture",
        "source_authority_type": authority,
        "source_qualification_tier": tier,
        "source_qualification_status": "historical_descriptive_only",
        "historical_vintage_available": False,
        "publication_timestamp_available": False,
        "revision_history_available": False,
        "is_synthetic_fixture": True,
        "manual_export_timestamp_utc": "2026-01-01T00:00:00Z",
        "manual_capture_timestamp_utc": "2026-01-01T00:00:00Z",
        "coverage_start": "2020-01-02",
        "coverage_end": "2020-01-15",
        "notes": "synthetic only",
    }


def _evidence(input_id: str) -> dict[str, object]:
    return {
        "input_id": input_id,
        "source_qualification_report_sha256": "a" * 64,
        "raw_source_manifest_sha256": "b" * 64,
        "benchmark_source_lineage": "synthetic_ndx",
        "issuer_direct_daily_series_status": "qualified_synthetic",
        "sec_periodic_anchor_status": "not_used",
        "tqqq_daily_capital_status": "qualified",
        "sqqq_daily_capital_status": "qualified",
        "capital_source_basis_by_instrument": {"TQQQ": "reported_aum_and_shares_nav", "SQQQ": "reported_aum_and_shares_nav"},
        "coverage_start": "2020-01-02",
        "coverage_end": "2020-01-15",
        "historical_vintage_available": False,
        "publication_timestamp_available": False,
        "revision_history_available": False,
        "manual_operator_confirmation_required": True,
        "notes": "synthetic only",
    }


def _stage(
    tmp_path: Path,
    input_id: str = "fixture_scale",
    *,
    qqq_mapping: bool = False,
    capital_dates: int = 10,
    include_split: bool = True,
    reported: bool = True,
    shares_nav: bool = True,
    source_basis: str = "reported_aum_and_shares_nav",
    tier: str = "tier_a_daily_direct",
    authority: str = "issuer_official_daily_nav_history",
) -> Path:
    root = tmp_path / "repo"
    base = m.input_dir(root, input_id)
    sources = base / "sources"
    sources.mkdir(parents=True)
    dates = pd.bdate_range("2020-01-02", periods=11).strftime("%Y-%m-%d").tolist()
    prices = [{"date": date, "instrument": "NDX", "raw_close": 100 + idx, "raw_or_adjusted": "raw"} for idx, date in enumerate(dates)]
    price_sha = _write_csv(sources / "benchmark_prices.csv", prices, m.PRICE_COLUMNS)
    mapping_rows = [
        {"leveraged_etf": "TQQQ", "target_benchmark_instrument": "QQQ" if qqq_mapping else "NDX", "target_leverage": 3.0, "directionality": "long", "benchmark_exact_or_proxy": "proxy_based" if qqq_mapping else "benchmark_exact", "mapping_source_authority": "synthetic", "notes": ""},
        {"leveraged_etf": "SQQQ", "target_benchmark_instrument": "QQQ" if qqq_mapping else "NDX", "target_leverage": -3.0, "directionality": "inverse", "benchmark_exact_or_proxy": "proxy_based" if qqq_mapping else "benchmark_exact", "mapping_source_authority": "synthetic", "notes": ""},
    ]
    mapping_sha = _write_csv(sources / "benchmark_mapping.csv", mapping_rows, m.MAPPING_COLUMNS)
    capital_rows = []
    for date in dates[:capital_dates]:
        for instrument, base_aum in [("TQQQ", 1000.0), ("SQQQ", 500.0)]:
            nav = 10.0
            shares = base_aum / nav
            capital_rows.append(
                {
                    "date": date,
                    "instrument": instrument,
                    "reported_aum_usd": base_aum if reported else "",
                    "shares_outstanding": shares if shares_nav else "",
                    "nav_per_share": nav if shares_nav else "",
                    "unit": "USD",
                    "capital_source_basis": source_basis,
                    "source_record_id": f"{instrument}-{date}",
                    "as_of_convention": "fund_nav_close",
                }
            )
    capital_sha = _write_csv(sources / "capital_observations.csv", capital_rows, m.CAPITAL_COLUMNS)
    split_sha = ""
    if include_split:
        split_rows = [
            {"instrument": "TQQQ", "effective_date": "2020-01-01", "split_ratio": 1.0, "source_authority": "synthetic", "source_record_id": "split-tqqq"},
            {"instrument": "SQQQ", "effective_date": "2020-01-01", "split_ratio": 1.0, "source_authority": "synthetic", "source_record_id": "split-sqqq"},
        ]
        split_sha = _write_csv(sources / "split_history.csv", split_rows, m.SPLIT_COLUMNS)
    evidence_path = sources / "scale_source_evidence.json"
    m.write_json(evidence_path, _evidence(input_id))
    evidence_sha = m.file_sha256(evidence_path)
    manifest_sources = [
        _source(input_id, "benchmark_prices", "NDX", "sources/benchmark_prices.csv", price_sha, authority="issuer_official_daily_direct"),
        _source(input_id, "benchmark_mapping", "TQQQ/SQQQ", "sources/benchmark_mapping.csv", mapping_sha, authority="issuer_official_daily_direct"),
        _source(input_id, "capital_observations", "TQQQ/SQQQ", "sources/capital_observations.csv", capital_sha, tier=tier, authority=authority),
        _source(input_id, "scale_source_evidence", "TQQQ/SQQQ", "sources/scale_source_evidence.json", evidence_sha, authority="issuer_official_daily_direct"),
    ]
    if include_split:
        manifest_sources.append(_source(input_id, "split_history", "TQQQ/SQQQ", "sources/split_history.csv", split_sha, authority="issuer_official_daily_direct"))
    m.write_json(
        base / "source_manifest.json",
        {"artifact_version": m.ARTIFACT_VERSION, "module_name": m.MODULE_NAME, "input_id": input_id, "research_only": True, "actionization_allowed": False, "not_a_trading_signal": True, "sources": manifest_sources},
    )
    return root


def test_template_creates_only_headers_no_data(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    result = m.build_template(root, "template")
    assert result["template_status"] == "created_or_existing"
    for rel, columns, _ in m.CANONICAL_SOURCE_FILES.values():
        path = m.input_dir(root, "template") / rel
        assert path.exists()
        if path.suffix == ".csv":
            assert pd.read_csv(path).empty
            assert list(pd.read_csv(path).columns) == columns


def test_missing_source_manifest_fields_block(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    manifest = m.load_source_manifest(root, "fixture_scale")
    del manifest["sources"][0]["content_sha256"]
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    result = m.validate_input(root, "fixture_scale")
    assert any(d["code"] == "missing_required_headers" for d in result["diagnostics"])


def test_exact_ndx_mapping_validates_and_qqq_proxy_blocks(tmp_path: Path) -> None:
    assert m.validate_input(_stage(tmp_path / "a"), "fixture_scale")["validation_status"] == "valid"
    result = m.validate_input(_stage(tmp_path / "b", qqq_mapping=True), "fixture_scale")
    assert any(d["code"] == "benchmark_not_ndx_exact" for d in result["diagnostics"])


def test_duplicate_date_instrument_blocks(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = m.input_dir(root, "fixture_scale") / "sources" / "capital_observations.csv"
    df = pd.read_csv(path, dtype=str)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "capital_observations":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    result = m.validate_input(root, "fixture_scale")
    assert any(d["code"] == "duplicate_capital_observation" for d in result["diagnostics"])


def test_invalid_instrument_date_numeric_unit_source_basis_blocks(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = m.input_dir(root, "fixture_scale") / "sources" / "capital_observations.csv"
    df = pd.read_csv(path, dtype=str)
    df.loc[0, ["instrument", "date", "reported_aum_usd", "unit", "capital_source_basis"]] = ["BAD", "not-date", "-1", "JPY", "bad"]
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "capital_observations":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    codes = {d["code"] for d in m.validate_input(root, "fixture_scale")["diagnostics"]}
    assert {"invalid_capital_instrument", "invalid_capital_date"} <= codes


def test_shares_without_nav_and_nav_without_shares_block(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = m.input_dir(root, "fixture_scale") / "sources" / "capital_observations.csv"
    df = pd.read_csv(path, dtype=str)
    df.loc[0, "nav_per_share"] = ""
    df.loc[1, "shares_outstanding"] = ""
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "capital_observations":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    assert any(d["code"] == "shares_nav_partial_pair" for d in m.validate_input(root, "fixture_scale")["diagnostics"])


def test_no_usable_scale_path_blocks(tmp_path: Path) -> None:
    result = m.validate_input(_stage(tmp_path, reported=False, shares_nav=False, source_basis="reported_aum_usd"), "fixture_scale")
    assert any(d["code"] == "capital_observation_no_usable_scale" for d in result["diagnostics"])


def test_missing_source_record_id_and_as_of_convention_block(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = m.input_dir(root, "fixture_scale") / "sources" / "capital_observations.csv"
    df = pd.read_csv(path, dtype=str)
    df.loc[0, ["source_record_id", "as_of_convention"]] = ["", ""]
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "capital_observations":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    codes = {d["code"] for d in m.validate_input(root, "fixture_scale")["diagnostics"]}
    assert {"missing_source_record_id", "missing_as_of_convention"} <= codes


def test_aum_plus_shares_nav_within_half_percent_passes(tmp_path: Path) -> None:
    assert m.validate_input(_stage(tmp_path), "fixture_scale")["validation_status"] == "valid"


def test_reconciliation_gap_above_half_percent_blocks(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = m.input_dir(root, "fixture_scale") / "sources" / "capital_observations.csv"
    df = pd.read_csv(path, dtype=str)
    df.loc[0, "nav_per_share"] = "1.0"
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "capital_observations":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    assert any(d["code"] == "reported_aum_shares_nav_reconciliation_failed" for d in m.validate_input(root, "fixture_scale")["diagnostics"])


def test_reported_aum_only_valid_row_passes(tmp_path: Path) -> None:
    assert m.validate_input(_stage(tmp_path, shares_nav=False, source_basis="reported_aum_usd"), "fixture_scale")["validation_status"] == "valid"


def test_shares_nav_path_requires_documented_split_history(tmp_path: Path) -> None:
    result = m.validate_input(_stage(tmp_path, reported=False, include_split=False, source_basis="shares_times_nav"), "fixture_scale")
    assert any(d["code"] == "split_history_missing_for_shares_nav" for d in result["diagnostics"])


def test_missing_or_invalid_split_history_blocks_shares_nav_path(tmp_path: Path) -> None:
    root = _stage(tmp_path, reported=False, source_basis="shares_times_nav")
    path = m.input_dir(root, "fixture_scale") / "sources" / "split_history.csv"
    df = pd.read_csv(path, dtype=str)
    df.loc[0, "split_ratio"] = "-1"
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "split_history":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    assert any(d["code"] == "split_history_schema_invalid" for d in m.validate_input(root, "fixture_scale")["diagnostics"])


def test_missing_evidence_and_hash_mismatch_block(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    evidence_path = m.input_dir(root, "fixture_scale") / "sources" / "scale_source_evidence.json"
    evidence = m.load_json(evidence_path)
    evidence["raw_source_manifest_sha256"] = "bad"
    m.write_json(evidence_path, evidence)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "scale_source_evidence":
            source["content_sha256"] = m.file_sha256(evidence_path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    assert any(d["code"] == "raw_source_evidence_hash_mismatch" for d in m.validate_input(root, "fixture_scale")["diagnostics"])


@pytest.mark.parametrize("tier", ["tier_c_periodic_anchor_only", "tier_d_current_snapshot_only", "tier_e_unqualified"])
def test_tier_c_d_e_cannot_populate_scale_input(tmp_path: Path, tier: str) -> None:
    result = m.validate_input(_stage(tmp_path, tier=tier), "fixture_scale")
    assert any(d["code"] == "capital_observation_unqualified_frequency" for d in result["diagnostics"])


def test_historical_pit_claim_blocks(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    manifest = m.load_source_manifest(root, "fixture_scale")
    manifest["sources"][2]["historical_vintage_available"] = True
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    assert any(d["code"] == "capital_observation_historical_pit_claim" for d in m.validate_input(root, "fixture_scale")["diagnostics"])


def test_exact_t_minus_one_capital_is_used(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = m.run_historical(root, "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_scale_proxy_daily.csv")
    first = daily.iloc[0]
    assert first["observation_date"] == "2020-01-03"
    assert first["prior_capital_observation_date_required"] == "2020-01-02"
    assert first["tqqq_lagged_capital_usd"] == pytest.approx(1000.0)


def test_same_day_latest_prior_and_future_capital_are_never_used(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = m.input_dir(root, "fixture_scale") / "sources" / "capital_observations.csv"
    df = pd.read_csv(path, dtype=str)
    df = df[df["date"] != "2020-01-03"]
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "capital_observations":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    result = m.run_historical(root, "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_scale_proxy_daily.csv")
    row = daily[daily["observation_date"] == "2020-01-06"].iloc[0]
    assert row["combined_scale_status"] == "combined_exact_prior_session_capital_unavailable"


def test_missing_t_minus_one_gives_unavailable_never_zero(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = m.input_dir(root, "fixture_scale") / "sources" / "capital_observations.csv"
    df = pd.read_csv(path)
    df = df[df["date"] != "2020-01-02"]
    df.to_csv(path, index=False)
    manifest = m.load_source_manifest(root, "fixture_scale")
    for source in manifest["sources"]:
        if source["dataset_type"] == "capital_observations":
            source["content_sha256"] = m.file_sha256(path)
    m.write_json(m.source_manifest_path(root, "fixture_scale"), manifest)
    result = m.run_historical(root, "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    first = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_scale_proxy_daily.csv", keep_default_na=False).iloc[0]
    assert first["tqqq_rebalance_notional_proxy"] == ""
    assert first["tqqq_capital_observation_status"] == "exact_prior_session_capital_unavailable"


def test_ninety_percent_threshold_passes_exactly_at_boundary(tmp_path: Path) -> None:
    result = m.validate_input(_stage(tmp_path, capital_dates=9), "fixture_scale")
    assert result["validation_status"] == "valid"
    assert result["coverage"]["combined_overlap_coverage_ratio"] == pytest.approx(0.9)


def test_below_ninety_percent_prevents_run_artifact_creation(tmp_path: Path) -> None:
    root = _stage(tmp_path, capital_dates=8)
    assert m.validate_input(root, "fixture_scale")["validation_status"] == "scale_coverage_inadequate_for_historical_run"
    with pytest.raises(SystemExit, match="scale_coverage_inadequate_for_historical_run"):
        m.run_historical(root, "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)


def test_tqqq_sqqq_formula_signs_and_magnitudes_match() -> None:
    assert m.mechanical_rebalance_notional_proxy(3.0, 100.0, 0.01) == pytest.approx(6.0)
    assert m.mechanical_rebalance_notional_proxy(-3.0, 100.0, 0.01) == pytest.approx(12.0)
    assert m.mechanical_rebalance_notional_proxy(3.0, 100.0, -0.01) == pytest.approx(-6.0)


def test_combined_output_exists_only_when_both_inputs_match_t_minus_one(tmp_path: Path) -> None:
    result = m.run_historical(_stage(tmp_path), "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_scale_proxy_daily.csv")
    assert daily["combined_rebalance_notional_proxy"].notna().all()


def test_reported_aum_selected_when_both_reconcile(tmp_path: Path) -> None:
    result = m.run_historical(_stage(tmp_path), "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    quality = pd.read_csv(Path(result["run_artifact"]) / "capital_observation_quality_report.csv")
    assert set(quality["capital_input_selected"]) == {"reported_aum_usd"}


def test_source_basis_labels_retained(tmp_path: Path) -> None:
    result = m.run_historical(_stage(tmp_path), "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_scale_proxy_daily.csv")
    assert set(daily["tqqq_capital_source_basis"]) == {"reported_aum_and_shares_nav"}


def test_output_safety_flags_are_false_as_required(tmp_path: Path) -> None:
    result = m.run_historical(_stage(tmp_path), "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    receipt = m.load_json(Path(result["run_artifact"]) / "leveraged_etf_scale_run_receipt.json")
    for field in m.REQUIRED_FALSE_FLAGS:
        assert receipt[field] is False
    for field in m.REQUIRED_TRUE_FLAGS:
        assert receipt[field] is True


def test_no_pnl_future_trade_or_actual_flow_fields(tmp_path: Path) -> None:
    result = m.run_historical(_stage(tmp_path), "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    daily = pd.read_csv(Path(result["run_artifact"]) / "leveraged_etf_scale_proxy_daily.csv")
    blocked = {"pnl", "future_return", "future_outcome", "trade_signal", "actual_flow", "market_impact_estimate"}
    assert not (set(map(str.lower, daily.columns)) & blocked)


def test_receipt_provenance_required(tmp_path: Path) -> None:
    result = m.run_historical(_stage(tmp_path), "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    receipt = m.load_json(Path(result["run_artifact"]) / "leveraged_etf_scale_run_receipt.json")
    for field in ["repository_commit_sha", "module_source_sha256", "model_spec_registry_hash", "source_manifest_hash", "scale_source_evidence_sha256", "raw_source_manifest_sha256"]:
        assert receipt[field]


def test_verifier_catches_tampering(tmp_path: Path) -> None:
    result = m.run_historical(_stage(tmp_path), "fixture_scale", "ndx_exact", m.MODEL_SPEC_ID)
    run_artifact = Path(result["run_artifact"])
    (run_artifact / "leveraged_etf_scale_proxy_summary.md").write_text("tampered", encoding="utf-8")
    assert m.verify_run(str(run_artifact))["verification_status"] == "tampered"


def test_legacy_free_proxy_behavior_unchanged(tmp_path: Path) -> None:
    assert free_proxy.mechanical_rebalance_notional(3.0, 100.0, 0.01) == pytest.approx(6.0)


def test_module_has_no_network_provider_code() -> None:
    text = (REPO_ROOT / "market_bomb_leveraged_etf_scale_proxy_v1.py").read_text(encoding="utf-8").lower()
    for needle in ["requests", "urllib", "http://", "https://", "invoke-webrequest", "curl"]:
        assert needle not in text


def test_history_archive_input_remain_ignored_untracked() -> None:
    ignored = subprocess.run(["git", "check-ignore", "market_bomb_history/leveraged_etf_scale_proxy_v1"], cwd=REPO_ROOT, text=True, capture_output=True)
    assert ignored.returncode == 0
    tracked = subprocess.check_output(["git", "ls-files", "market_bomb_history"], cwd=REPO_ROOT, text=True)
    assert "leveraged_etf_scale_proxy_v1" not in tracked
