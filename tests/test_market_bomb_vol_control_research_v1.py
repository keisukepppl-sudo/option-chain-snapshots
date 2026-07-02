from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import market_bomb_vol_control_research_v1 as vc


SPEC_ID = "vc_daily_20d_target10_cap100_v1"


def _copy_config(root: Path) -> None:
    dst = root / "config" / "vol_control_research_v1"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / "config" / "vol_control_research_v1" / "model_specs.json", dst / "model_specs.json")


def _price_rows(instrument: str = "NDX", count: int = 35, start: float = 100.0, basis: str = "raw") -> list[dict[str, object]]:
    rows = []
    price = start
    base_date = pd.Timestamp("2025-01-01")
    for i in range(count):
        price *= 1.0 + (0.004 if i % 2 == 0 else -0.002)
        rows.append({"date": (base_date + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), "instrument": instrument, "raw_close": round(price, 6), "raw_or_adjusted": basis})
    return rows


def _schedule_rows(count: int = 35) -> list[dict[str, object]]:
    base_date = pd.Timestamp("2025-01-01")
    return [
        {
            "observation_date": (base_date + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "effective_session": (base_date + pd.Timedelta(days=i + 1)).strftime("%Y-%m-%d"),
            "decision_timestamp_utc": (base_date + pd.Timedelta(days=i)).strftime("%Y-%m-%dT21:00:00Z"),
            "session_source": "synthetic_explicit_schedule",
        }
        for i in range(count)
    ]


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _manifest_entry(input_id: str, dataset_type: str, rel: str, path: Path, instrument: str = "NDX", strict: bool = False) -> dict[str, object]:
    return {
        "input_id": input_id,
        "dataset_type": dataset_type,
        "instrument": instrument,
        "relative_path": rel,
        "content_sha256": vc.file_sha256(path),
        "row_identifier_field": "date" if dataset_type != "decision_schedule" else "observation_date",
        "source_name": "synthetic_fixture",
        "source_authority_type": "synthetic_fixture",
        "source_qualification_status": "gold_point_in_time_eligible" if strict else vc.HISTORICAL_CONFIDENCE,
        "historical_vintage_available": False,
        "publication_timestamp_available": False,
        "revision_history_available": False,
        "is_synthetic_fixture": True,
        "manual_export_timestamp_utc": "2026-07-02T00:00:00Z",
        "manual_capture_timestamp_utc": "2026-07-02T00:00:00Z",
        "raw_or_adjusted": "raw",
        "corporate_action_treatment": "none",
        "coverage_start": "2025-01-01",
        "coverage_end": "2025-02-04",
        "notes": "synthetic fixture only",
    }


def _stage(root: Path, input_id: str = "fixture_vc", prices: list[dict[str, object]] | None = None, schedule: list[dict[str, object]] | None = None, strict: bool = False) -> Path:
    _copy_config(root)
    base = root / "market_bomb_history" / "vol_control_research_v1" / "input" / input_id
    prices = prices or _price_rows()
    schedule = schedule or _schedule_rows(len(prices))
    price_path = base / "sources" / "benchmark_prices.csv"
    schedule_path = base / "sources" / "decision_schedule.csv"
    _write_csv(price_path, prices, vc.PRICE_COLUMNS)
    _write_csv(schedule_path, schedule, vc.SCHEDULE_COLUMNS)
    manifest = {
        "artifact_version": vc.ARTIFACT_VERSION,
        "module_name": vc.MODULE_NAME,
        "input_id": input_id,
        "research_only": True,
        "actionization_allowed": False,
        "sources": [
            _manifest_entry(input_id, "benchmark_prices", "sources/benchmark_prices.csv", price_path, str(prices[0]["instrument"]), strict),
            _manifest_entry(input_id, "decision_schedule", "sources/decision_schedule.csv", schedule_path, str(prices[0]["instrument"]), strict),
        ],
    }
    vc.write_json(base / "source_manifest.json", manifest)
    return base


def _run(root: Path, input_id: str = "fixture_vc", mode: str = "ndx_exact_descriptive") -> tuple[dict[str, object], pd.DataFrame]:
    result = vc.run_historical(root, input_id, mode, SPEC_ID)
    daily = pd.read_csv(Path(str(result["run_artifact"])) / "vol_control_daily_exposure.csv")
    return result, daily


def test_template_and_inspect_create_contract_without_run_artifact(tmp_path: Path) -> None:
    result = vc.build_template(tmp_path, "empty")
    inspect = vc.inspect_input_contract(tmp_path, "empty")
    assert result["template_status"] == "created_or_existing"
    assert inspect["creates_run_artifact"] is False
    assert inspect["actionization_allowed"] is False


def test_rolling_math_uses_only_observation_date_returns_and_caps_exposure(tmp_path: Path) -> None:
    _stage(tmp_path)
    _, daily = _run(tmp_path)
    valid = daily[daily["exposure_change_label"] != vc.UNAVAILABLE_LABEL].iloc[0]
    prices = pd.DataFrame(_price_rows())
    returns = prices["raw_close"].pct_change()
    expected_vol = returns.iloc[:22].std(ddof=1) * math.sqrt(252)
    expected_target = min(1.0, 0.10 / expected_vol)
    assert valid["observation_date"] == "2025-01-22"
    assert valid["target_exposure"] == pytest.approx(expected_target)
    assert valid["target_exposure"] <= 1.0


def test_insufficient_history_and_zero_volatility_are_input_unavailable(tmp_path: Path) -> None:
    flat = [{"date": f"2025-01-{i + 1:02d}", "instrument": "NDX", "raw_close": 100.0, "raw_or_adjusted": "raw"} for i in range(25)]
    _stage(tmp_path, prices=flat)
    _, daily = _run(tmp_path)
    assert set(daily["exposure_change_label"]) == {vc.UNAVAILABLE_LABEL}


def test_missing_price_rows_are_not_forward_filled(tmp_path: Path) -> None:
    prices = _price_rows(count=35)
    schedule = _schedule_rows(count=35)
    schedule.append({"observation_date": "2025-03-01", "effective_session": "2025-03-02", "decision_timestamp_utc": "2025-03-01T21:00:00Z", "session_source": "synthetic"})
    _stage(tmp_path, prices=prices, schedule=schedule)
    validation = vc.validate_input(tmp_path, "fixture_vc")
    assert any(d["code"] == "schedule_observation_missing_price" for d in validation["diagnostics"])


def test_exposure_change_sign_and_unchanged_labels(tmp_path: Path) -> None:
    prices = []
    price = 100.0
    for i in range(45):
        if i < 25:
            ret = 0.003 if i % 2 == 0 else -0.002
        elif i < 35:
            ret = 0.02 if i % 2 == 0 else -0.015
        else:
            ret = 0.002 if i % 2 == 0 else -0.001
        price *= 1 + ret
        prices.append({"date": (pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), "instrument": "NDX", "raw_close": round(price, 6), "raw_or_adjusted": "raw"})
    _stage(tmp_path, prices=prices)
    _, daily = _run(tmp_path)
    labels = set(daily["exposure_change_label"])
    assert vc.UNCHANGED_LABEL in labels
    assert {vc.INCREASE_LABEL, vc.REDUCE_LABEL} & labels


def test_decision_timing_requires_next_session_and_records_source(tmp_path: Path) -> None:
    bad = _schedule_rows()
    bad[0]["effective_session"] = bad[0]["observation_date"]
    _stage(tmp_path, schedule=bad)
    validation = vc.validate_input(tmp_path, "fixture_vc")
    assert any(d["code"] == "same_day_or_prior_effective_session" for d in validation["diagnostics"])
    good = _schedule_rows()
    good[0]["session_source"] = "unit_test_calendar"
    _stage(tmp_path / "ok", schedule=good)
    _, daily = _run(tmp_path / "ok")
    assert "unit_test_calendar" in set(daily["session_source"])
    assert (daily["feature_cutoff_date"] == daily["observation_date"]).all()


def test_future_price_changes_do_not_change_prior_decision(tmp_path: Path) -> None:
    _stage(tmp_path)
    _, first = _run(tmp_path)
    prior = first[first["observation_date"] == "2025-01-25"].iloc[0]["target_exposure"]
    prices = _price_rows()
    prices[-1]["raw_close"] = 9999.0
    _stage(tmp_path / "changed", prices=prices)
    _, changed = _run(tmp_path / "changed")
    assert changed[changed["observation_date"] == "2025-01-25"].iloc[0]["target_exposure"] == pytest.approx(prior)


def test_effective_session_return_is_not_used_for_observation_decision(tmp_path: Path) -> None:
    prices = _price_rows()
    prices[21]["raw_close"] = 10000.0
    _stage(tmp_path, prices=prices)
    _, daily = _run(tmp_path)
    first_valid = daily[daily["exposure_change_label"] != vc.UNAVAILABLE_LABEL].iloc[0]
    assert first_valid["observation_date"] == "2025-01-22"
    assert first_valid["effective_session"] == "2025-01-23"


def test_hash_mismatch_duplicate_key_mixed_basis_and_strict_claim_block(tmp_path: Path) -> None:
    prices = _price_rows()
    prices.append(dict(prices[-1]))
    prices[-1]["raw_or_adjusted"] = "adjusted"
    _stage(tmp_path, prices=prices, strict=True)
    manifest_path = tmp_path / "market_bomb_history" / "vol_control_research_v1" / "input" / "fixture_vc" / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sources"][0]["content_sha256"] = "bad"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    diagnostics = vc.validate_input(tmp_path, "fixture_vc")["diagnostics"]
    codes = {d["code"] for d in diagnostics}
    assert {"content_sha256_mismatch", "duplicate_benchmark_price_key", "mixed_raw_adjusted_basis", "vol_control_requires_descriptive_status", "vol_control_cannot_emit_strict_status"} <= codes


def test_ndx_and_qqq_modes_do_not_substitute_instruments(tmp_path: Path) -> None:
    _stage(tmp_path, prices=_price_rows("QQQ"))
    with pytest.raises(SystemExit, match="missing_benchmark_instrument:NDX"):
        vc.run_historical(tmp_path, "fixture_vc", "ndx_exact_descriptive", SPEC_ID)
    _, daily = _run(tmp_path, mode="qqq_proxy_only_descriptive")
    assert set(daily["benchmark_instrument"]) == {"QQQ"}
    assert set(daily["benchmark_exact_or_proxy"]) == {"proxy_only"}


def test_missing_decision_schedule_blocks_validation(tmp_path: Path) -> None:
    base = _stage(tmp_path)
    (base / "sources" / "decision_schedule.csv").unlink()
    diagnostics = vc.validate_input(tmp_path, "fixture_vc")["diagnostics"]
    assert any(d["code"] == "missing_source_file" for d in diagnostics)


def test_ignored_raw_root_and_module_isolation_contract() -> None:
    ignore = (REPO_ROOT / ".gitignore").read_text()
    source = (REPO_ROOT / "market_bomb_vol_control_research_v1.py").read_text()
    assert "market_bomb_history/vol_control_research_v1/" in ignore
    assert "leveraged_etf_free_proxy" not in source
    assert "phase3_2_cta" not in source
    assert vc.ACTIONIZATION_ALLOWED is False
    assert not vc.tracked_vol_control_history(REPO_ROOT)


def test_run_artifact_receipt_content_manifest_and_tamper_detection(tmp_path: Path) -> None:
    _stage(tmp_path)
    result, _ = _run(tmp_path)
    run_artifact = Path(str(result["run_artifact"]))
    receipt = json.loads((run_artifact / "vol_control_run_receipt.json").read_text())
    assert receipt["actionization_allowed"] is False
    assert receipt["phase2_run"] is False
    assert vc.verify_run(str(run_artifact))["verification_status"] == "valid"
    (run_artifact / "vol_control_summary.md").write_text("tampered", encoding="utf-8")
    assert vc.verify_run(str(run_artifact))["verification_status"] == "tampered"


def test_run_directories_are_unique_and_not_release_backtest_or_phase_runs(tmp_path: Path) -> None:
    _stage(tmp_path)
    first, _ = _run(tmp_path)
    second, _ = _run(tmp_path)
    assert first["run_artifact"] != second["run_artifact"]
    assert first["release_created"] is False
    assert first["backtest_run"] is False
    assert first["phase1_3_readiness_run"] is False
    assert first["phase2_run"] is False


def test_cot_template_and_inspection_are_sanity_only(tmp_path: Path) -> None:
    vc.build_cot_template(tmp_path, "cot")
    path = tmp_path / "market_bomb_history" / "vol_control_research_v1" / "input" / "cot" / "sources" / "cot_weekly.csv"
    _write_csv(
        path,
        [
            {
                "market_name": "NASDAQ 100",
                "cftc_market_code": "209742",
                "position_as_of_date": "2025-01-07",
                "publication_timestamp_utc": "2025-01-10T20:30:00Z",
                "available_timestamp_utc": "2025-01-10T20:31:00Z",
                "reporting_group": "leveraged_funds",
                "long_contracts": 100,
                "short_contracts": 90,
                "spreading_contracts": 5,
                "open_interest_contracts": 1000,
                "source_authority": "synthetic_cftc_fixture",
                "revision_status": "synthetic",
            }
        ],
        vc.COT_COLUMNS,
    )
    inspection = vc.inspect_cot_sanity_input(tmp_path, "cot")
    assert inspection["cot_is_not_vol_control_ground_truth"] is True
    assert inspection["daily_validation_allowed"] is False
    assert inspection["rows"][0]["position_as_of_is_publication_time"] is False
    assert inspection["rows"][0]["timing_fields_present"] is True


def test_cot_unavailable_timing_rows_are_visible_but_not_daily_validation(tmp_path: Path) -> None:
    vc.build_cot_template(tmp_path, "cot")
    path = tmp_path / "market_bomb_history" / "vol_control_research_v1" / "input" / "cot" / "sources" / "cot_weekly.csv"
    _write_csv(
        path,
        [
            {
                "market_name": "NASDAQ 100",
                "cftc_market_code": "209742",
                "position_as_of_date": "2025-01-07",
                "publication_timestamp_utc": "",
                "available_timestamp_utc": "",
                "reporting_group": "asset_manager",
                "long_contracts": 100,
                "short_contracts": 90,
                "spreading_contracts": 5,
                "open_interest_contracts": 1000,
                "source_authority": "synthetic_cftc_fixture",
                "revision_status": "synthetic",
            }
        ],
        vc.COT_COLUMNS,
    )
    inspection = vc.inspect_cot_sanity_input(tmp_path, "cot")
    assert inspection["weekly_sanity_check_only"] is True
    assert inspection["rows"][0]["timing_fields_present"] is False
