from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_bot_source_seal_v1 as seal


@pytest.fixture(autouse=True)
def isolated_history_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = tmp_path / "history" / "morita_bot_source_seal_v1"
    monkeypatch.setattr(seal, "HISTORY_ROOT", history)
    monkeypatch.setattr(seal, "INVENTORY_ROOT", history / "inventory")
    monkeypatch.setattr(seal, "ARTIFACT_ROOT", history / "source_artifacts")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = columns or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def _manifest(path: Path) -> None:
    manifest = seal.build_manifest_for_dir(path, "content_manifest.json")
    _write_json(path / "content_manifest.json", manifest)


def _candidate(root: Path, with_option: bool = False, n: int = 20) -> Path:
    c = root / "candidate"
    signals = []
    outcomes = []
    opts = []
    for i in range(n):
        day = pd.Timestamp("2024-01-02") + pd.offsets.BDay(i)
        entry = day + pd.offsets.BDay(1)
        observed = entry + pd.offsets.BDay(10)
        sid = f"sig_{i:03d}"
        signals.append(
            {
                "signal_id": sid,
                "signal_decision_date": day.strftime("%Y-%m-%d"),
                "signal_decision_timestamp_utc": f"{day.strftime('%Y-%m-%d')}T21:00:00Z",
                "entry_session": entry.strftime("%Y-%m-%d"),
                "underlying_symbol": f"SYM{i % 4}",
                "signal_rank": ["S", "A", "B"][i % 3],
                "strategy_family": "Breakout Momentum",
                "theme": "Software",
                "source_rule_version": "morita_fixture_rules_v1",
                "source_rule_config_hash": "cfg_hash",
                "source_run_id": "fixture_run",
                "source_manifest_hash": "source_manifest_hash",
            }
        )
        outcomes.append(
            {
                "signal_id": sid,
                "outcome_status": "complete",
                "breakout_day_low_breach_before_timeout": str(i % 5 == 0).lower(),
                "timeout_10_sessions_under_threshold": str(i % 7 == 0).lower(),
                "reached_plus_5pct_within_10_sessions": str(i % 4 == 0).lower(),
                "holding_sessions_at_exit_or_timeout": "10",
                "exit_event_category": "profit_target" if i % 4 == 0 else "timeout_10_sessions_under_threshold",
                "outcome_observed_through_session": observed.strftime("%Y-%m-%d"),
                "outcome_rule_version": "morita_fixture_outcome_v1",
                "outcome_rule_config_hash": "outcome_cfg_hash",
            }
        )
        if with_option:
            opts.append(
                {
                    "signal_id": sid,
                    "option_profit_target_125pct_reached": str(i % 4 == 0).lower(),
                    "option_return_at_declared_exit": "1.25" if i % 4 == 0 else "-0.50",
                    "underlying_return_at_declared_exit": "0.05",
                    "maximum_adverse_excursion": "-0.08",
                    "maximum_favorable_excursion": "0.12",
                    "fees_included_status": "included",
                    "option_outcome_rule_version": "optional_exact_fixture_v1",
                    "option_outcome_rule_config_hash": "optional_hash",
                }
            )
    _write_csv(c / "signals.csv", signals)
    _write_csv(c / "outcomes.csv", outcomes)
    if with_option:
        _write_csv(c / "options.csv", opts)
    schema = {
        "signal_file": "signals.csv",
        "outcome_file": "outcomes.csv",
        "signal_columns": {col: col for col in seal.SIGNAL_COLUMNS},
        "outcome_columns": {col: col for col in seal.OUTCOME_COLUMNS},
    }
    if with_option:
        schema["optional_option_file"] = "options.csv"
        schema["optional_option_columns"] = {col: col for col in seal.OPTION_COLUMNS}
    _write_json(c / "source_schema_map.json", schema)
    _write_json(
        c / "source_rule_snapshot.json",
        {
            "strategy_family": "Breakout Momentum",
            "source_rule_version": "morita_fixture_rules_v1",
            "source_rule_config_hash": "cfg_hash",
            "source_code_commit_sha": "a" * 40,
            "signal_universe_identifier": "fixture_universe",
            "rank_definition_reference": "fixture_rank_reference",
            "breakout_definition_reference": "fixture_breakout_reference",
            "relative_strength_definition_reference": "fixture_rs_reference",
            "volume_definition_reference": "fixture_volume_reference",
            "signal_decision_timing_reference": "after_close_utc",
            "entry_timing_reference": "next_regular_session",
            "breakout_day_low_definition_reference": "breakout_session_low",
            "timeout_rule_reference": "day10_under_threshold",
            "plus_5pct_rule_reference": "entry_reference_plus_5pct_within_10",
            "profit_target_rule_reference_if_existing": "fixture_profit_target",
            "hard_stop_rule_reference_if_existing": "fixture_hard_stop",
            "option_outcome_rule_reference_if_existing": "fixture_exact_option" if with_option else "unavailable_from_existing_source",
        },
    )
    _write_json(
        c / "source_timing_contract.json",
        {
            "signal_observation_convention": "close_after_session",
            "decision_timestamp_convention": "utc_after_close",
            "t_close_usage": "decision_after_t_close",
            "entry_session_convention": "first_regular_session_after_decision",
            "first_outcome_observation_session": "entry_session",
            "breakout_day_low_reference_date": "signal_decision_date",
            "timeout_session_counting": "business_sessions_from_entry",
            "plus_5pct_reference_price_date": "entry_reference",
            "outcome_cutoff": "declared_timeout",
            "timezone": "UTC",
            "holiday_handling": "source_calendar",
        },
    )
    _write_json(
        c / "source_input_lineage.json",
        {
            "inputs": [
                {
                    "input_id": "fixture_input",
                    "repository_relative_path_or_local_alias": "fixture/local",
                    "input_role": "signal_and_outcome_fixture",
                    "local_only_or_committed": "local_only",
                    "sha256": "b" * 64,
                    "byte_count": 123,
                    "row_count_if_tabular": n,
                    "date_coverage_if_known": "2024-01",
                    "raw_or_adjusted_status_if_known": "fixture",
                    "source_manifest_hash_if_available": "fixture_manifest",
                    "required_for_signal_or_outcome": "both",
                }
            ]
        },
    )
    _write_json(c / "run_receipt.json", {"run_status": "fixture_completed", "repository_commit_sha": "c" * 40})
    _manifest(c)
    return c


def test_valid_existing_run_export_builds_and_verifies(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path, with_option=True)
    output = seal.ARTIFACT_ROOT / "fixture_artifact_valid"
    if output.exists():
        import shutil

        shutil.rmtree(output)
    result = seal.build_source_artifact(candidate, output, "morita_bot_source_seal_v1")
    assert result["status"] == "morita_bot_source_seal_completed"
    verified = seal.verify_source_artifact(output)
    assert verified["signal_row_count"] == 20
    assert verified["optional_option_outcome_row_count"] == 20
    assert subprocess.run(["git", "check-ignore", "market_bomb_history/morita_bot_source_seal_v1/placeholder.txt"], cwd=REPO_ROOT, capture_output=True).returncode == 0


def test_inventory_is_read_only_and_records_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _candidate(tmp_path / "root")
    monkeypatch.setattr(seal, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(seal, "HISTORY_ROOT", tmp_path / "market_bomb_history" / "morita_bot_source_seal_v1")
    monkeypatch.setattr(seal, "INVENTORY_ROOT", seal.HISTORY_ROOT / "inventory")
    monkeypatch.setattr(seal, "ARTIFACT_ROOT", seal.HISTORY_ROOT / "source_artifacts")
    result = seal.inspect_candidates()
    assert result["candidate_count"] >= 1
    assert (seal.INVENTORY_ROOT / "morita_bot_source_inventory.json").exists()
    assert not (tmp_path / "root" / "candidate" / "source_content_manifest.json").exists()


def test_missing_lineage_rule_timing_and_aggregate_only_block(tmp_path: Path) -> None:
    c = _candidate(tmp_path / "lineage")
    (c / "source_input_lineage.json").unlink()
    _manifest(c)
    with pytest.raises(SystemExit, match="input_lineage_incomplete"):
        seal.validate_candidate(str(c))

    c = _candidate(tmp_path / "rule")
    payload = json.loads((c / "source_rule_snapshot.json").read_text())
    payload["source_rule_config_hash"] = ""
    _write_json(c / "source_rule_snapshot.json", payload)
    _manifest(c)
    with pytest.raises(SystemExit, match="rule_snapshot_incomplete"):
        seal.validate_candidate(str(c))

    c = _candidate(tmp_path / "timing")
    payload = json.loads((c / "source_timing_contract.json").read_text())
    payload["timeout_session_counting"] = ""
    _write_json(c / "source_timing_contract.json", payload)
    _manifest(c)
    with pytest.raises(SystemExit, match="timing_validation_blocked"):
        seal.validate_candidate(str(c))

    agg = tmp_path / "aggregate"
    _write_csv(agg / "summary.csv", [{"profit_factor": "1.2"}])
    with pytest.raises(SystemExit):
        seal.validate_candidate(str(agg))


def test_signal_and_outcome_validation_blocks_bad_rows(tmp_path: Path) -> None:
    c = _candidate(tmp_path / "dup")
    rows = list(csv.DictReader((c / "signals.csv").open(newline="", encoding="utf-8")))
    rows[1]["signal_id"] = rows[0]["signal_id"]
    _write_csv(c / "signals.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="duplicate_signal_id"):
        seal.validate_candidate(str(c))

    c = _candidate(tmp_path / "rank")
    rows = list(csv.DictReader((c / "signals.csv").open(newline="", encoding="utf-8")))
    rows[0]["signal_rank"] = "C"
    _write_csv(c / "signals.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="invalid_rank"):
        seal.validate_candidate(str(c))

    c = _candidate(tmp_path / "timestamp")
    rows = list(csv.DictReader((c / "signals.csv").open(newline="", encoding="utf-8")))
    rows[0]["signal_decision_timestamp_utc"] = ""
    _write_csv(c / "signals.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="signal_timing_ambiguous"):
        seal.validate_candidate(str(c))

    c = _candidate(tmp_path / "entry")
    rows = list(csv.DictReader((c / "signals.csv").open(newline="", encoding="utf-8")))
    rows[0]["entry_session"] = rows[0]["signal_decision_date"]
    _write_csv(c / "signals.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="entry_timing_ambiguous"):
        seal.validate_candidate(str(c))


def test_outcome_contract_blocks_missing_orphan_and_pre_entry(tmp_path: Path) -> None:
    c = _candidate(tmp_path / "missing")
    rows = list(csv.DictReader((c / "outcomes.csv").open(newline="", encoding="utf-8")))
    rows = rows[:-1]
    _write_csv(c / "outcomes.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="missing"):
        seal.validate_candidate(str(c))

    c = _candidate(tmp_path / "orphan")
    rows = list(csv.DictReader((c / "outcomes.csv").open(newline="", encoding="utf-8")))
    rows[0]["signal_id"] = "orphan"
    _write_csv(c / "outcomes.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="orphan"):
        seal.validate_candidate(str(c))

    c = _candidate(tmp_path / "pre")
    rows = list(csv.DictReader((c / "outcomes.csv").open(newline="", encoding="utf-8")))
    rows[0]["outcome_observed_through_session"] = "2024-01-01"
    _write_csv(c / "outcomes.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="outcome_pre_entry_invalid"):
        seal.validate_candidate(str(c))


def test_optional_options_absent_unless_exact_and_complete(tmp_path: Path) -> None:
    c = _candidate(tmp_path / "no_option", with_option=False)
    out = seal.ARTIFACT_ROOT / "fixture_no_option"
    if out.exists():
        import shutil

        shutil.rmtree(out)
    receipt = seal.build_source_artifact(c, out, "morita_bot_source_seal_v1")
    assert receipt["optional_option_outcome_row_count"] == 0
    assert not (out / "morita_bot_option_outcomes_optional.csv").exists()

    c = _candidate(tmp_path / "bad_option", with_option=True)
    rows = list(csv.DictReader((c / "options.csv").open(newline="", encoding="utf-8")))
    rows = rows[:-1]
    _write_csv(c / "options.csv", rows)
    _manifest(c)
    with pytest.raises(SystemExit, match="option_signal_mismatch"):
        seal.validate_candidate(str(c))


def test_manifest_missing_changed_extra_and_receipt_fields_fail(tmp_path: Path) -> None:
    c = _candidate(tmp_path / "manifest")
    out = seal.ARTIFACT_ROOT / "fixture_manifest"
    import shutil

    if out.exists():
        shutil.rmtree(out)
    seal.build_source_artifact(c, out, "morita_bot_source_seal_v1")
    (out / "morita_bot_signal_events.csv").write_text("tamper\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="artifact_verification_failed:sha"):
        seal.verify_source_artifact(out)

    shutil.rmtree(out)
    seal.build_source_artifact(c, out, "morita_bot_source_seal_v1")
    (out / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="artifact_verification_failed:extra"):
        seal.verify_source_artifact(out)

    shutil.rmtree(out)
    seal.build_source_artifact(c, out, "morita_bot_source_seal_v1")
    receipt = json.loads((out / "source_receipt.json").read_text())
    receipt["source_rule_config_hash"] = ""
    _write_json(out / "source_receipt.json", receipt)
    _write_json(out / "source_content_manifest.json", seal.build_manifest_for_dir(out, "source_content_manifest.json"))
    with pytest.raises(SystemExit, match="receipt:source_rule_config_hash"):
        seal.verify_source_artifact(out)


def test_output_root_parameter_override_and_no_network_code(tmp_path: Path) -> None:
    c = _candidate(tmp_path)
    with pytest.raises(SystemExit, match="output_root_rejected"):
        seal.build_source_artifact(c, tmp_path / "outside", "morita_bot_source_seal_v1")

    with pytest.raises(SystemExit, match="parameter_or_input_override_rejected"):
        seal.main(["--parameter-override"])
    with pytest.raises(SystemExit, match="parameter_or_input_override_rejected"):
        seal.main(["--input-override", str(tmp_path)])

    source = (REPO_ROOT / "scripts" / "build_morita_bot_source_seal_v1.py").read_text(encoding="utf-8").lower()
    for needle in ["requests.", "urllib", "socket.", "selenium", "playwright", "submit_order", "cancel_order", "ranking_score", "trade_filter"]:
        assert needle not in source


def test_deterministic_manifest_for_same_fixture_lineage(tmp_path: Path) -> None:
    c = _candidate(tmp_path)
    out1 = seal.ARTIFACT_ROOT / "fixture_deterministic_1"
    out2 = seal.ARTIFACT_ROOT / "fixture_deterministic_2"
    import shutil

    for out in [out1, out2]:
        if out.exists():
            shutil.rmtree(out)
    seal.build_source_artifact(c, out1, "morita_bot_source_seal_v1")
    seal.build_source_artifact(c, out2, "morita_bot_source_seal_v1")
    m1 = json.loads((out1 / "source_content_manifest.json").read_text())
    m2 = json.loads((out2 / "source_content_manifest.json").read_text())
    by_name1 = {f["relative_path"]: f["sha256"] for f in m1["files"] if f["relative_path"] != "source_receipt.json" and f["relative_path"] != "source_artifact_summary.md"}
    by_name2 = {f["relative_path"]: f["sha256"] for f in m2["files"] if f["relative_path"] != "source_receipt.json" and f["relative_path"] != "source_artifact_summary.md"}
    assert by_name1 == by_name2
