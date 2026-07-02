from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import market_bomb_cta_research_v1 as cta


SPEC_20 = "cta_ts_20d_binary_v1"
SPEC_60 = "cta_ts_60d_binary_v1"
SPEC_120 = "cta_ts_120d_binary_v1"
SPEC_COMP = "cta_ts_20_60_120_equal_weight_v1"


def _copy_config(root: Path) -> None:
    dst = root / "config" / "cta_research_v1"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / "config" / "cta_research_v1" / "model_specs.json", dst / "model_specs.json")


def _prices(count: int = 150, market_id: str = "NQ", instrument: str = "NQ_FUT", basis: str = "raw") -> list[dict[str, object]]:
    rows = []
    base = pd.Timestamp("2025-01-01")
    price = 100.0
    for i in range(count):
        if i < 50:
            ret = 0.004
        elif i < 90:
            ret = -0.005
        else:
            ret = 0.003
        price *= 1 + ret
        rows.append({"date": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), "market_id": market_id, "instrument": instrument, "raw_close": round(price, 6), "raw_or_adjusted": basis})
    return rows


def _schedule(count: int = 150, market_id: str = "NQ") -> list[dict[str, object]]:
    base = pd.Timestamp("2025-01-01")
    return [
        {
            "market_id": market_id,
            "observation_date": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "effective_session": (base + pd.Timedelta(days=i + 1)).strftime("%Y-%m-%d"),
            "decision_timestamp_utc": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%dT23:59:59Z"),
            "session_source": "derived_from_observed_series_for_descriptive_only",
        }
        for i in range(count)
    ]


def _mapping(market_id: str = "NQ", instrument: str = "NQ_FUT", relation: str = "direct_futures_match") -> list[dict[str, object]]:
    return [
        {
            "market_id": market_id,
            "price_instrument": instrument,
            "cot_market_name": "NASDAQ 100",
            "cftc_market_code": "209742",
            "price_to_cot_relation": relation,
            "market_mapping_authority": "synthetic_fixture",
            "notes": "synthetic mapping",
        }
    ]


def _pending_mapping() -> list[dict[str, object]]:
    rows = _mapping(relation="cash_index_proxy_for_futures_cot")
    rows[0]["cot_market_name"] = "pending_manual_cot_identification"
    rows[0]["cftc_market_code"] = "pending_manual_cot_identification"
    return rows


def _cot_rows(count: int = 8, market_id: str = "NQ", group: str = "leveraged_funds") -> list[dict[str, object]]:
    rows = []
    base = pd.Timestamp("2025-04-01")
    for i in range(count):
        pos = base + pd.Timedelta(days=i * 7)
        rows.append(
            {
                "market_id": market_id,
                "market_name": "NASDAQ 100",
                "cftc_market_code": "209742",
                "position_as_of_date": pos.strftime("%Y-%m-%d"),
                "publication_timestamp_utc": (pos + pd.Timedelta(days=3)).strftime("%Y-%m-%dT20:30:00Z"),
                "available_timestamp_utc": (pos + pd.Timedelta(days=3, minutes=1)).strftime("%Y-%m-%dT20:31:00Z"),
                "reporting_group": group,
                "long_contracts": 100 + i * 10,
                "short_contracts": 80 + i * 5,
                "spreading_contracts": 2,
                "open_interest_contracts": 1000 + i * 20,
                "source_authority": "synthetic_cftc_fixture",
                "revision_status": "synthetic",
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _manifest_entry(input_id: str, dataset_type: str, rel: str, path: Path, instrument: str = "NQ_FUT", strict: bool = False) -> dict[str, object]:
    return {
        "input_id": input_id,
        "dataset_type": dataset_type,
        "instrument": instrument,
        "relative_path": rel,
        "content_sha256": cta.file_sha256(path),
        "row_identifier_field": "date,market_id,instrument",
        "source_name": "synthetic_fixture",
        "source_authority_type": "synthetic_fixture",
        "source_qualification_status": "gold_point_in_time_eligible" if strict else cta.HISTORICAL_CONFIDENCE,
        "historical_vintage_available": False,
        "publication_timestamp_available": False,
        "revision_history_available": False,
        "is_synthetic_fixture": True,
        "manual_export_timestamp_utc": "2026-07-02T00:00:00Z",
        "manual_capture_timestamp_utc": "2026-07-02T00:00:00Z",
        "raw_or_adjusted": "raw",
        "corporate_action_treatment": "none",
        "coverage_start": "2025-01-01",
        "coverage_end": "2025-05-30",
        "notes": "synthetic fixture only",
    }


def _stage(
    root: Path,
    input_id: str = "fixture_cta",
    prices: list[dict[str, object]] | None = None,
    mapping: list[dict[str, object]] | None = None,
    schedule: list[dict[str, object]] | None = None,
    cot_rows: list[dict[str, object]] | None = None,
    strict: bool = False,
) -> Path:
    _copy_config(root)
    base = root / "market_bomb_history" / "cta_research_v1" / "input" / input_id
    prices = prices or _prices()
    mapping = mapping or _mapping()
    schedule = schedule or _schedule(len(prices))
    files = [
        ("daily_market_prices", "sources/daily_market_prices.csv", prices, cta.PRICE_COLUMNS),
        ("market_mapping", "sources/market_mapping.csv", mapping, cta.MAPPING_COLUMNS),
        ("decision_schedule", "sources/decision_schedule.csv", schedule, cta.SCHEDULE_COLUMNS),
    ]
    if cot_rows is not None:
        files.append(("cot_weekly", "sources/cot_weekly.csv", cot_rows, cta.COT_COLUMNS))
    entries = []
    for dataset, rel, rows, cols in files:
        path = base / rel
        _write_csv(path, rows, cols)
        entries.append(_manifest_entry(input_id, dataset, rel, path, str(prices[0]["instrument"]), strict))
    for rel, cols in {"sources/cot_weekly.csv": cta.COT_COLUMNS}.items():
        path = base / rel
        if not path.exists():
            _write_csv(path, [], cols)
    cta.write_json(base / "source_manifest.json", {"artifact_version": cta.ARTIFACT_VERSION, "module_name": cta.MODULE_NAME, "input_id": input_id, **cta.safety_flags(), "sources": entries})
    return base


def _rewrite_manifest_hash(base: Path, dataset_type: str, rel: str) -> None:
    manifest_path = base / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for source in manifest["sources"]:
        if source["dataset_type"] == dataset_type:
            source["content_sha256"] = cta.file_sha256(base / rel)
    cta.write_json(manifest_path, manifest)


def _refresh_manifest(run_artifact: Path, manifest_name: str) -> None:
    manifest = cta.build_content_manifest(run_artifact, manifest_name, run_artifact.name)
    cta.write_json(run_artifact / manifest_name, manifest)


def _run(root: Path, spec: str = SPEC_20) -> tuple[dict[str, object], pd.DataFrame]:
    result = cta.run_historical(root, "fixture_cta", "NQ", spec)
    daily = pd.read_csv(Path(str(result["run_artifact"])) / "cta_daily_exposure.csv")
    return result, daily


def test_template_and_inspect_create_no_artifact(tmp_path: Path) -> None:
    result = cta.build_template(tmp_path, "empty")
    inspect = cta.inspect_input_contract(tmp_path, "empty")
    assert result["template_status"] == "created_or_existing"
    assert inspect["creates_run_artifact"] is False
    assert inspect["actionization_allowed"] is False


def test_single_horizon_formulas_and_insufficient_history(tmp_path: Path) -> None:
    _stage(tmp_path)
    _, daily20 = _run(tmp_path, SPEC_20)
    first = daily20[pd.to_numeric(daily20["target_exposure"], errors="coerce").notna()].iloc[0]
    assert first["observation_date"] == "2025-01-21"
    assert first["target_exposure"] == 1.0
    assert set(daily20.iloc[:20]["exposure_change_label"]) == {cta.UNAVAILABLE_LABEL}
    _, daily60 = _run(tmp_path, SPEC_60)
    assert daily60[pd.to_numeric(daily60["target_exposure"], errors="coerce").notna()].iloc[0]["observation_date"] == "2025-03-02"
    _, daily120 = _run(tmp_path, SPEC_120)
    assert daily120[pd.to_numeric(daily120["target_exposure"], errors="coerce").notna()].iloc[0]["observation_date"] == "2025-05-01"


def test_composite_equal_weight_and_exposure_bounds(tmp_path: Path) -> None:
    _stage(tmp_path)
    _, daily = _run(tmp_path, SPEC_COMP)
    available = pd.to_numeric(daily["target_exposure"], errors="coerce").dropna()
    assert available.between(-1.0, 1.0).all()
    first = daily[pd.to_numeric(daily["target_exposure"], errors="coerce").notna()].iloc[0]
    assert first["observation_date"] == "2025-05-01"
    assert first["target_exposure"] in {-1.0, 0.0, 1.0}


def test_exposure_change_labels_and_timing_contract(tmp_path: Path) -> None:
    _stage(tmp_path)
    _, daily = _run(tmp_path, SPEC_20)
    assert {cta.INCREASE_LABEL, cta.REDUCE_LABEL, cta.UNCHANGED_LABEL} & set(daily["exposure_change_label"])
    assert (daily["feature_cutoff_date"] == daily["observation_date"]).all()
    assert (pd.to_datetime(daily["effective_session"]) > pd.to_datetime(daily["observation_date"])).all()
    assert set(daily["decision_timing_status"]) == {"valid_next_session_eod_decision"}


def test_future_price_change_cannot_change_prior_decision(tmp_path: Path) -> None:
    _stage(tmp_path)
    _, base = _run(tmp_path, SPEC_20)
    prior = base[base["observation_date"] == "2025-03-10"].iloc[0]["target_exposure"]
    prices = _prices()
    prices[-1]["raw_close"] = 999999
    _stage(tmp_path / "changed", prices=prices)
    result = cta.run_historical(tmp_path / "changed", "fixture_cta", "NQ", SPEC_20)
    changed = pd.read_csv(Path(str(result["run_artifact"])) / "cta_daily_exposure.csv")
    assert changed[changed["observation_date"] == "2025-03-10"].iloc[0]["target_exposure"] == prior


def test_selected_price_instrument_cannot_silently_change(tmp_path: Path) -> None:
    _stage(tmp_path, mapping=_mapping(instrument="OTHER_FUT"))
    validation = cta.validate_input(tmp_path, "fixture_cta")
    assert any(d["code"] == "price_instrument_not_declared_in_mapping" for d in validation["diagnostics"])
    with pytest.raises(SystemExit, match="cta_input_validation_blocked"):
        cta.run_historical(tmp_path, "fixture_cta", "NQ", SPEC_20)


def test_raw_adjusted_duplicate_schedule_and_strict_claims_block(tmp_path: Path) -> None:
    prices = _prices()
    prices.append(dict(prices[-1]))
    prices[-1]["raw_or_adjusted"] = "adjusted"
    schedule = _schedule()
    schedule[0]["effective_session"] = schedule[0]["observation_date"]
    _stage(tmp_path, prices=prices, schedule=schedule, strict=True)
    diagnostics = cta.validate_input(tmp_path, "fixture_cta")["diagnostics"]
    codes = {d["code"] for d in diagnostics}
    assert {"duplicate_market_price_key", "mixed_raw_adjusted_basis", "same_day_or_prior_effective_session", "cta_requires_descriptive_status", "cta_cannot_emit_strict_status"} <= codes


def test_missing_invalid_schedule_blocks_run(tmp_path: Path) -> None:
    base = _stage(tmp_path)
    (base / "sources" / "decision_schedule.csv").unlink()
    validation = cta.validate_input(tmp_path, "fixture_cta")
    assert any(d["code"] == "missing_source_file" for d in validation["diagnostics"])


def test_run_artifact_immutable_flags_and_tamper_detection(tmp_path: Path) -> None:
    _stage(tmp_path)
    result, _ = _run(tmp_path)
    run_artifact = Path(str(result["run_artifact"]))
    receipt = json.loads((run_artifact / "cta_run_receipt.json").read_text())
    assert receipt["actionization_allowed"] is False
    assert receipt["phase2_run"] is False
    assert cta.verify_cta_run(str(run_artifact))["verification_status"] == "valid"
    (run_artifact / "cta_summary.md").write_text("tampered", encoding="utf-8")
    assert cta.verify_cta_run(str(run_artifact))["verification_status"] == "tampered"


def test_cot_template_inspection_requires_timing_fields(tmp_path: Path) -> None:
    cta.build_cot_validation_template(tmp_path, "cot")
    path = tmp_path / "market_bomb_history" / "cta_research_v1" / "input" / "cot" / "sources" / "cot_weekly.csv"
    _write_csv(path, _cot_rows(1), cta.COT_COLUMNS)
    inspection = cta.inspect_cot_validation_input(tmp_path, "cot")
    assert inspection["rows"][0]["timing_fields_present"] is True
    assert inspection["rows"][0]["position_as_of_is_publication_time"] is False
    assert inspection["cot_is_not_cta_ground_truth"] is True


def test_placeholder_policy_blocks_variants() -> None:
    placeholders = [
        "",
        " ",
        None,
        "pending_manual_cot_identification",
        " Pending Manual COT Identification ",
        "tbd",
        "unknown",
        "n/a",
        "unresolved",
        "pending_cftc_code",
        "unknown_market",
        "placeholder_value",
    ]
    assert all(cta.is_placeholder_cot_identifier(value) for value in placeholders)
    assert not cta.is_placeholder_cot_identifier("NASDAQ 100")


def test_mapping_eligibility_reports_unresolved_and_hash() -> None:
    mapping = pd.Series(_pending_mapping()[0])
    eligibility = cta.evaluate_cot_mapping_eligibility(mapping)
    assert eligibility["cot_mapping_status"] == "cot_mapping_unresolved"
    assert eligibility["cot_validation_eligible"] is False
    assert set(eligibility["blocking_codes"]) == {"cot_market_name_placeholder", "cftc_market_code_placeholder"}
    assert eligibility["mapping_identity_hash"] == cta.mapping_identity_hash(mapping)


def test_placeholder_mapping_blocks_before_validation_artifact_creation(tmp_path: Path) -> None:
    _stage(tmp_path, mapping=_pending_mapping(), cot_rows=_cot_rows(4))
    result, _ = _run(tmp_path, SPEC_20)
    before = set((tmp_path / "market_bomb_history" / "cta_research_v1" / "cot_validation_runs").glob("*"))
    with pytest.raises(SystemExit, match="cta_cot_mapping_placeholder_blocked"):
        cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    after = set((tmp_path / "market_bomb_history" / "cta_research_v1" / "cot_validation_runs").glob("*"))
    assert before == after


def test_unresolved_baseline_still_verifies_as_cta_run(tmp_path: Path) -> None:
    _stage(tmp_path, mapping=_pending_mapping())
    result, _ = _run(tmp_path, SPEC_20)
    assert cta.verify_cta_run(str(result["run_artifact"]))["verification_status"] == "valid"
    receipt = json.loads((Path(str(result["run_artifact"])) / "cta_run_receipt.json").read_text())
    assert receipt["cot_validation_eligible"] is False


def test_inspect_reports_mapping_eligibility_without_artifact(tmp_path: Path) -> None:
    _stage(tmp_path, mapping=_pending_mapping())
    before = set((tmp_path / "market_bomb_history" / "cta_research_v1").glob("cot_validation_runs/*"))
    inspection = cta.inspect_cot_validation_input(tmp_path, "fixture_cta")
    after = set((tmp_path / "market_bomb_history" / "cta_research_v1").glob("cot_validation_runs/*"))
    assert before == after
    row = inspection["mapping_rows"][0]
    assert row["cot_mapping_status"] == "cot_mapping_unresolved"
    assert row["cot_validation_eligible"] is False


def test_confirmed_matching_synthetic_mapping_passes_validation_and_verifies(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(30))
    result, _ = _run(tmp_path, SPEC_20)
    validation = cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    artifact = Path(str(validation["validation_artifact"]))
    snapshot = json.loads((artifact / "cta_cot_mapping_eligibility_snapshot.json").read_text())
    assert snapshot["mapping_snapshot_match"] is True
    assert snapshot["cot_rows_full_mapping_match"] == 30
    assert cta.verify_cot_validation(str(artifact))["verification_status"] == "valid"


def test_legacy_snapshot_missing_new_fields_blocks_cot_but_verifies_cta(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(4))
    result, _ = _run(tmp_path, SPEC_20)
    artifact = Path(str(result["run_artifact"]))
    snapshot_path = artifact / "cta_market_mapping_snapshot.json"
    receipt_path = artifact / "cta_run_receipt.json"
    snapshot = json.loads(snapshot_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    for field in ["cot_mapping_status", "cot_validation_eligible", "blocking_codes", "mapping_identity_hash", "cot_mapping_blocking_codes"]:
        snapshot.pop(field, None)
        receipt.pop(field, None)
    cta.write_json(snapshot_path, snapshot)
    cta.write_json(receipt_path, receipt)
    _refresh_manifest(artifact, "cta_content_manifest.json")
    assert cta.verify_cta_run(str(artifact))["verification_status"] == "valid"
    with pytest.raises(SystemExit, match="cta_run_mapping_snapshot_mismatch"):
        cta.run_cot_validation(tmp_path, str(artifact), "fixture_cta", "NQ", "leveraged_funds")


def test_current_mapping_changes_block_snapshot_binding(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(4))
    result, _ = _run(tmp_path, SPEC_20)
    base = tmp_path / "market_bomb_history" / "cta_research_v1" / "input" / "fixture_cta"
    mapping_path = base / "sources" / "market_mapping.csv"
    mapping = pd.read_csv(mapping_path, dtype=str)
    mapping.loc[0, "cftc_market_code"] = "DIFFERENT"
    mapping.to_csv(mapping_path, index=False)
    _rewrite_manifest_hash(base, "market_mapping", "sources/market_mapping.csv")
    with pytest.raises(SystemExit, match="cta_run_mapping_snapshot_mismatch"):
        cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    mapping.loc[0, "cftc_market_code"] = "209742"
    mapping.loc[0, "cot_market_name"] = "DIFFERENT MARKET"
    mapping.to_csv(mapping_path, index=False)
    _rewrite_manifest_hash(base, "market_mapping", "sources/market_mapping.csv")
    with pytest.raises(SystemExit, match="cta_run_mapping_snapshot_mismatch"):
        cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    mapping.loc[0, "cot_market_name"] = "NASDAQ 100"
    mapping.loc[0, "price_to_cot_relation"] = "cash_index_proxy_for_futures_cot"
    mapping.to_csv(mapping_path, index=False)
    _rewrite_manifest_hash(base, "market_mapping", "sources/market_mapping.csv")
    with pytest.raises(SystemExit, match="cta_run_mapping_snapshot_mismatch"):
        cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")


def test_requested_market_id_mismatch_blocks(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(4))
    result, _ = _run(tmp_path, SPEC_20)
    with pytest.raises(SystemExit, match="missing_or_duplicate_market_mapping:OTHER"):
        cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "OTHER", "leveraged_funds")


def test_cot_row_market_name_code_mismatch_and_mixed_rows_block(tmp_path: Path) -> None:
    rows = _cot_rows(4)
    rows[0]["market_name"] = "Different"
    _stage(tmp_path, cot_rows=rows)
    result, _ = _run(tmp_path, SPEC_20)
    with pytest.raises(SystemExit, match="cot_row_market_mapping_mismatch"):
        cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    rows = _cot_rows(4)
    rows[0]["cftc_market_code"] = "DIFFERENT"
    _stage(tmp_path / "code", cot_rows=rows)
    result = cta.run_historical(tmp_path / "code", "fixture_cta", "NQ", SPEC_20)
    with pytest.raises(SystemExit, match="cot_row_market_mapping_mismatch"):
        cta.run_cot_validation(tmp_path / "code", str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")


def test_absent_requested_reporting_group_blocks(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(4, group="asset_manager"))
    result, _ = _run(tmp_path, SPEC_20)
    with pytest.raises(SystemExit, match="cot_reporting_group_not_found_for_confirmed_mapping"):
        cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")


def test_unavailable_cot_rows_do_not_enter_availability_validation(tmp_path: Path) -> None:
    cot_rows = _cot_rows(4)
    cot_rows[1]["available_timestamp_utc"] = "2030-01-01T20:31:00Z"
    _stage(tmp_path, cot_rows=cot_rows)
    result, _ = _run(tmp_path, SPEC_20)
    validation = cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    pairs = pd.read_csv(Path(str(validation["validation_artifact"])) / "cta_cot_weekly_pairs.csv")
    assert len(pairs[pairs["alignment_mode"] == "availability_monitoring_only"]) == 3
    assert set(pairs["ex_post_external_validation_only"]) == {True}
    assert set(pairs["cot_is_not_cta_ground_truth"]) == {True}


def test_cot_does_not_enter_cta_daily_calculation(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(4))
    result, _ = _run(tmp_path, SPEC_20)
    before = cta.file_sha256(Path(str(result["run_artifact"])) / "cta_daily_exposure.csv")
    cot_path = tmp_path / "market_bomb_history" / "cta_research_v1" / "input" / "fixture_cta" / "sources" / "cot_weekly.csv"
    cot_df = pd.read_csv(cot_path)
    cot_df.loc[0, "long_contracts"] = 999999
    cot_df.to_csv(cot_path, index=False)
    after = cta.file_sha256(Path(str(result["run_artifact"])) / "cta_daily_exposure.csv")
    assert before == after


def test_relation_labels_remain_visible_for_direct_and_proxy(tmp_path: Path) -> None:
    _stage(tmp_path, mapping=_mapping(relation="cash_index_proxy_for_futures_cot"), cot_rows=_cot_rows(4))
    result, daily = _run(tmp_path, SPEC_20)
    assert set(daily["price_to_cot_relation"]) == {"cash_index_proxy_for_futures_cot"}
    validation = cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    pairs = pd.read_csv(Path(str(validation["validation_artifact"])) / "cta_cot_weekly_pairs.csv")
    assert set(pairs["price_to_cot_relation"]) == {"cash_index_proxy_for_futures_cot"}


def test_insufficient_pair_coverage_yields_metrics_unavailable(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(4))
    result, _ = _run(tmp_path, SPEC_20)
    validation = cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    summary = pd.read_csv(Path(str(validation["validation_artifact"])) / "cta_cot_validation_summary.csv")
    assert set(summary["metrics_available"]) == {False}
    assert summary["metrics_unavailable_reason"].str.contains("weekly_pair_count_below_26").all()


def test_cot_validation_artifact_is_immutable_and_tamper_detectable(tmp_path: Path) -> None:
    _stage(tmp_path, cot_rows=_cot_rows(6))
    result, _ = _run(tmp_path, SPEC_20)
    validation = cta.run_cot_validation(tmp_path, str(result["run_artifact"]), "fixture_cta", "NQ", "leveraged_funds")
    artifact = Path(str(validation["validation_artifact"]))
    assert cta.verify_cot_validation(str(artifact))["verification_status"] == "valid"
    (artifact / "cta_cot_validation_summary.md").write_text("tampered", encoding="utf-8")
    assert cta.verify_cot_validation(str(artifact))["verification_status"] == "tampered"


def test_isolation_safety_no_forbidden_imports_and_ignored_root() -> None:
    source = (REPO_ROOT / "market_bomb_cta_research_v1.py").read_text()
    for forbidden in ["leveraged_etf", "vol_control", "dealer", "scanner", "requests", "urllib", "yfinance"]:
        assert forbidden not in source
    assert "market_bomb_history/cta_research_v1/" in (REPO_ROOT / ".gitignore").read_text()
    assert cta.ACTIONIZATION_ALLOWED is False
    assert not cta.tracked_cta_history(REPO_ROOT)
