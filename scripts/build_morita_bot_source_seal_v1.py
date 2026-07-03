from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "config" / "morita_bot_source_seal_v1" / "source_seal_spec.json"
HISTORY_ROOT = REPO_ROOT / "market_bomb_history" / "morita_bot_source_seal_v1"
INVENTORY_ROOT = HISTORY_ROOT / "inventory"
ARTIFACT_ROOT = HISTORY_ROOT / "source_artifacts"

SIGNAL_COLUMNS = [
    "signal_id",
    "signal_decision_date",
    "signal_decision_timestamp_utc",
    "entry_session",
    "underlying_symbol",
    "signal_rank",
    "strategy_family",
    "theme",
    "source_rule_version",
    "source_rule_config_hash",
    "source_run_id",
    "source_manifest_hash",
]
OUTCOME_COLUMNS = [
    "signal_id",
    "outcome_status",
    "breakout_day_low_breach_before_timeout",
    "timeout_10_sessions_under_threshold",
    "reached_plus_5pct_within_10_sessions",
    "holding_sessions_at_exit_or_timeout",
    "exit_event_category",
    "outcome_observed_through_session",
    "outcome_rule_version",
    "outcome_rule_config_hash",
]
OPTION_COLUMNS = [
    "signal_id",
    "option_profit_target_125pct_reached",
    "option_return_at_declared_exit",
    "underlying_return_at_declared_exit",
    "maximum_adverse_excursion",
    "maximum_favorable_excursion",
    "fees_included_status",
    "option_outcome_rule_version",
    "option_outcome_rule_config_hash",
]
REQUIRED_ARTIFACT_FILES = [
    "morita_bot_signal_events.csv",
    "morita_bot_signal_outcomes.csv",
    "source_schema_map.json",
    "source_rule_snapshot.json",
    "source_timing_contract.json",
    "source_input_lineage.json",
    "source_validation_report.csv",
    "source_receipt.json",
    "source_artifact_summary.md",
]
SAFETY_FLAGS = {
    "research_only": True,
    "actionization_allowed": False,
    "not_a_trading_signal": True,
    "not_a_trade_execution_system": True,
    "not_a_new_strategy_backtest": True,
    "not_a_parameter_optimization": True,
    "not_a_model_selection_study": True,
    "not_a_predictive_model": True,
    "predictive_pit_eligible": False,
    "phase2_eligible": False,
    "release_created": False,
}
ALLOWED_RANKS = {"S", "A", "B"}
ALLOWED_EXITS = {
    "profit_target",
    "hard_stop",
    "breakout_day_low_breach",
    "timeout_10_sessions_under_threshold",
    "other_predeclared_rule",
    "unavailable",
}
def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def git_status_label() -> str:
    try:
        status = subprocess.check_output(["git", "status", "--short"], cwd=REPO_ROOT, text=True)
    except Exception:
        return "unknown"
    tracked = [line for line in status.splitlines() if line and not line.startswith("?? ")]
    return "clean_tracked_files" if not tracked else "tracked_files_modified"


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def row_count(path: Path) -> int:
    if path.suffix.lower() != ".csv":
        return 0
    try:
        return len(pd.read_csv(path, dtype=str))
    except Exception:
        return 0


def load_spec(spec_id: str) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    if spec.get("spec_id") != spec_id:
        raise SystemExit(f"morita_bot_source_seal_unknown_spec:{spec_id}")
    return spec


def ensure_local_roots() -> None:
    INVENTORY_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)


def is_ignored(path: Path) -> bool:
    rel = repo_relative(path)
    result = subprocess.run(["git", "check-ignore", rel], cwd=REPO_ROOT, text=True, capture_output=True)
    return result.returncode == 0


def require_output_root(output_dir: Path) -> None:
    root = ARTIFACT_ROOT.resolve()
    try:
        output_dir.resolve().relative_to(root)
    except ValueError:
        raise SystemExit("morita_bot_source_seal_output_root_rejected")


def find_first(path: Path, names: list[str]) -> Path | None:
    for name in names:
        p = path / name
        if p.exists():
            return p
    return None


def build_manifest_for_dir(path: Path, manifest_name: str) -> dict[str, Any]:
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and child.name != manifest_name:
            files.append(
                {
                    "relative_path": child.relative_to(path).as_posix(),
                    "sha256": file_sha256(child),
                    "byte_count": child.stat().st_size,
                    "row_count_if_tabular": row_count(child),
                    "required": child.name in REQUIRED_ARTIFACT_FILES or child.name == "morita_bot_option_outcomes_optional.csv",
                }
            )
    return {"artifact_version": "morita_bot_source_seal_v1_0_0", "files": files}


def verify_manifest(path: Path, manifest_name: str) -> dict[str, Any]:
    manifest_path = path / manifest_name
    if not manifest_path.exists():
        raise SystemExit("morita_bot_source_seal_artifact_verification_failed:manifest_missing")
    manifest = load_json(manifest_path)
    expected = {entry["relative_path"]: entry["sha256"] for entry in manifest.get("files", [])}
    actual = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file() and p.name != manifest_name}
    for rel, expected_hash in expected.items():
        target = path / rel
        if not target.exists():
            raise SystemExit(f"morita_bot_source_seal_artifact_verification_failed:missing:{rel}")
        if file_sha256(target) != expected_hash:
            raise SystemExit(f"morita_bot_source_seal_artifact_verification_failed:sha:{rel}")
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise SystemExit(f"morita_bot_source_seal_artifact_verification_failed:extra:{extras[0]}")
    return manifest


def inspect_candidate_dir(path: Path) -> dict[str, Any]:
    manifest = find_first(path, ["source_content_manifest.json", "content_manifest.json", "morita_bot_source_content_manifest.json"])
    receipt = find_first(path, ["source_receipt.json", "run_receipt.json", "receipt.json"])
    schema = find_first(path, ["source_schema_map.json", "schema_map.json"])
    signals = find_first(path, ["morita_bot_signal_events.csv", "signals.csv", "signal_events.csv"])
    outcomes = find_first(path, ["morita_bot_signal_outcomes.csv", "outcomes.csv", "signal_outcomes.csv"])
    rule = path / "source_rule_snapshot.json"
    timing = path / "source_timing_contract.json"
    lineage = path / "source_input_lineage.json"
    block: list[str] = []
    if not manifest:
        block.append("source_manifest_missing")
    if not receipt:
        block.append("source_receipt_missing")
    if not schema:
        block.append("source_schema_map_missing")
    if not signals:
        block.append("signal_level_rows_missing")
    if not outcomes:
        block.append("outcome_rows_missing")
    if not rule.exists():
        block.append("source_rule_snapshot_missing")
    if not timing.exists():
        block.append("source_timing_contract_missing")
    if not lineage.exists():
        block.append("source_input_lineage_missing")
    return {
        "candidate_id": text_hash(str(path.resolve()))[:16],
        "candidate_type": "existing_run_export" if manifest and receipt else "unknown_or_partial",
        "repository_relative_path": repo_relative(path),
        "availability_status": "candidate_available" if not block else "candidate_incomplete",
        "source_commit_sha_if_known": "",
        "source_rule_version_if_known": "",
        "source_config_hash_if_known": "",
        "source_input_manifest_hash_if_known": "",
        "signal_level_rows_available": bool(signals),
        "outcome_rows_available": bool(outcomes),
        "decision_timing_available": bool(signals and timing.exists()),
        "entry_timing_available": bool(signals and timing.exists()),
        "core_outcome_rules_available": bool(outcomes and rule.exists()),
        "eligible_path_a": not block,
        "eligible_path_b": False,
        "block_reasons": ";".join(block),
    }


def inspect_candidates(write_evidence: bool = True) -> dict[str, Any]:
    ensure_local_roots()
    candidates: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in [REPO_ROOT / "outputs", REPO_ROOT / "market_bomb_history", REPO_ROOT]:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_dir() or path in seen:
                continue
            seen.add(path)
            try:
                names = {p.name for p in path.iterdir() if p.is_file()}
            except PermissionError:
                continue
            if names & {"morita_bot_signal_events.csv", "signals.csv", "signal_events.csv", "morita_bot_signal_outcomes.csv", "outcomes.csv", "signal_outcomes.csv", "source_receipt.json", "run_receipt.json", "source_schema_map.json"}:
                candidates.append(inspect_candidate_dir(path))
    payload = {
        "status": "morita_bot_source_candidates_inventoried",
        "candidate_count": len(candidates),
        "candidates": candidates,
        **SAFETY_FLAGS,
    }
    if write_evidence:
        write_json(INVENTORY_ROOT / "morita_bot_source_inventory.json", payload)
        lines = ["# Morita Bot Source Inventory", "", f"Candidate count: `{len(candidates)}`", ""]
        for c in candidates:
            lines.append(f"- `{c['repository_relative_path']}`: `{c['availability_status']}` `{c['block_reasons']}`")
        (INVENTORY_ROOT / "morita_bot_source_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_json(
            INVENTORY_ROOT / "morita_bot_candidate_lineage_manifest.json",
            {
                "candidate_count": len(candidates),
                "candidate_hash": text_hash(json_dumps(candidates)),
                "repository_commit_sha": git_head(),
                **SAFETY_FLAGS,
            },
        )
    return payload


def read_mapped_csv(path: Path, file_name: str, mapping: dict[str, str], required: list[str], code: str) -> pd.DataFrame:
    target = path / file_name
    if not target.exists():
        raise SystemExit(code)
    source = pd.read_csv(target, dtype=str).fillna("")
    missing_src = [src for src in mapping.values() if src not in source.columns]
    if missing_src:
        raise SystemExit(f"{code}:{missing_src[0]}")
    out = pd.DataFrame()
    for canonical, source_col in mapping.items():
        out[canonical] = source[source_col].astype(str)
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise SystemExit(f"{code}:{missing[0]}")
    return out[required]


def require_snapshot_complete(rule: dict[str, Any]) -> None:
    required = [
        "strategy_family",
        "source_rule_version",
        "source_rule_config_hash",
        "source_code_commit_sha",
        "signal_universe_identifier",
        "rank_definition_reference",
        "breakout_definition_reference",
        "relative_strength_definition_reference",
        "volume_definition_reference",
        "signal_decision_timing_reference",
        "entry_timing_reference",
        "breakout_day_low_definition_reference",
        "timeout_rule_reference",
        "plus_5pct_rule_reference",
    ]
    for key in required:
        value = str(rule.get(key, "")).strip()
        if not value or value == "unavailable_from_existing_source":
            raise SystemExit(f"morita_bot_source_seal_rule_snapshot_incomplete:{key}")


def require_timing_complete(timing: dict[str, Any]) -> None:
    required = [
        "signal_observation_convention",
        "decision_timestamp_convention",
        "t_close_usage",
        "entry_session_convention",
        "first_outcome_observation_session",
        "breakout_day_low_reference_date",
        "timeout_session_counting",
        "plus_5pct_reference_price_date",
        "outcome_cutoff",
        "timezone",
        "holiday_handling",
    ]
    for key in required:
        value = str(timing.get(key, "")).strip()
        if not value or value == "unavailable_from_existing_source":
            raise SystemExit(f"morita_bot_source_seal_timing_validation_blocked:{key}")


def require_lineage_complete(lineage: dict[str, Any]) -> None:
    inputs = lineage.get("inputs", [])
    if not inputs:
        raise SystemExit("morita_bot_source_seal_input_lineage_incomplete:no_inputs")
    for idx, item in enumerate(inputs):
        for key in ["input_id", "repository_relative_path_or_local_alias", "input_role", "local_only_or_committed", "sha256", "byte_count", "required_for_signal_or_outcome"]:
            if str(item.get(key, "")).strip() == "":
                raise SystemExit(f"morita_bot_source_seal_input_lineage_incomplete:{idx}:{key}")


def validate_signal_outcome_contract(signals: pd.DataFrame, outcomes: pd.DataFrame) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    if signals["signal_id"].duplicated().any():
        raise SystemExit("morita_bot_source_seal_timing_validation_blocked:duplicate_signal_id")
    bad_rank = sorted(set(signals["signal_rank"]) - ALLOWED_RANKS)
    if bad_rank:
        raise SystemExit(f"morita_bot_source_seal_timing_validation_blocked:invalid_rank:{bad_rank[0]}")
    if outcomes["signal_id"].duplicated().any():
        raise SystemExit("morita_bot_source_seal_outcome_contract_incomplete:duplicate_outcome_signal_id")
    orphan = sorted(set(outcomes["signal_id"]) - set(signals["signal_id"]))
    if orphan:
        raise SystemExit(f"morita_bot_source_seal_outcome_contract_incomplete:orphan:{orphan[0]}")
    missing = sorted(set(signals["signal_id"]) - set(outcomes["signal_id"]))
    if missing:
        raise SystemExit(f"morita_bot_source_seal_outcome_contract_incomplete:missing:{missing[0]}")
    bad_exit = sorted(set(outcomes["exit_event_category"]) - ALLOWED_EXITS)
    if bad_exit:
        raise SystemExit(f"morita_bot_source_seal_outcome_contract_incomplete:invalid_exit:{bad_exit[0]}")
    decision_dates = pd.to_datetime(signals["signal_decision_date"], errors="coerce")
    decision_ts = pd.to_datetime(signals["signal_decision_timestamp_utc"], utc=True, errors="coerce")
    entries = pd.to_datetime(signals["entry_session"], errors="coerce")
    if decision_dates.isna().any() or decision_ts.isna().any():
        raise SystemExit("morita_bot_source_signal_timing_ambiguous")
    if entries.isna().any() or (entries.dt.date <= decision_dates.dt.date).any():
        raise SystemExit("morita_bot_source_entry_timing_ambiguous")
    merged = signals[["signal_id", "entry_session"]].merge(outcomes[["signal_id", "outcome_observed_through_session"]], on="signal_id", how="inner")
    observed = pd.to_datetime(merged["outcome_observed_through_session"], errors="coerce")
    entry_dt = pd.to_datetime(merged["entry_session"], errors="coerce")
    if observed.isna().any():
        raise SystemExit("morita_bot_source_outcome_timing_ambiguous")
    if (observed.dt.date < entry_dt.dt.date).any():
        raise SystemExit("morita_bot_source_outcome_pre_entry_invalid")
    report.append({"validation_check": "signal_outcome_contract", "status": "passed", "details": f"signals={len(signals)} outcomes={len(outcomes)}"})
    return report


def load_candidate(path: Path) -> dict[str, Any]:
    manifest_name = (find_first(path, ["source_content_manifest.json", "content_manifest.json", "morita_bot_source_content_manifest.json"]) or Path("")).name
    if not manifest_name:
        raise SystemExit("morita_bot_source_seal_candidate_validation_blocked:manifest_missing")
    verify_manifest(path, manifest_name)
    schema_path = find_first(path, ["source_schema_map.json", "schema_map.json"])
    receipt_path = find_first(path, ["source_receipt.json", "run_receipt.json", "receipt.json"])
    if not schema_path:
        raise SystemExit("morita_bot_source_seal_candidate_validation_blocked:schema_missing")
    if not receipt_path:
        raise SystemExit("morita_bot_source_seal_candidate_validation_blocked:receipt_missing")
    for required_path, code in [
        (path / "source_rule_snapshot.json", "morita_bot_source_seal_rule_snapshot_incomplete:missing"),
        (path / "source_timing_contract.json", "morita_bot_source_seal_timing_validation_blocked:missing"),
        (path / "source_input_lineage.json", "morita_bot_source_seal_input_lineage_incomplete:missing"),
    ]:
        if not required_path.exists():
            raise SystemExit(code)
    schema = load_json(schema_path)
    receipt = load_json(receipt_path)
    rule = load_json(path / "source_rule_snapshot.json")
    timing = load_json(path / "source_timing_contract.json")
    lineage = load_json(path / "source_input_lineage.json")
    require_snapshot_complete(rule)
    require_timing_complete(timing)
    require_lineage_complete(lineage)
    if not receipt.get("repository_commit_sha") or not (receipt.get("run_status") or receipt.get("status")):
        raise SystemExit("morita_bot_source_seal_candidate_validation_blocked:receipt_incomplete")
    signals = read_mapped_csv(path, schema["signal_file"], schema["signal_columns"], SIGNAL_COLUMNS, "morita_bot_source_seal_candidate_validation_blocked:signals")
    outcomes = read_mapped_csv(path, schema["outcome_file"], schema["outcome_columns"], OUTCOME_COLUMNS, "morita_bot_source_seal_outcome_contract_incomplete")
    option_file = schema.get("optional_option_file", "")
    option_map = schema.get("optional_option_columns", {})
    options = pd.DataFrame(columns=OPTION_COLUMNS)
    if option_file:
        options = read_mapped_csv(path, option_file, option_map, OPTION_COLUMNS, "morita_bot_source_seal_outcome_contract_incomplete:options")
        if set(options["signal_id"]) != set(signals["signal_id"]):
            raise SystemExit("morita_bot_source_seal_outcome_contract_incomplete:option_signal_mismatch")
    validation = validate_signal_outcome_contract(signals, outcomes)
    return {
        "path": path,
        "manifest_name": manifest_name,
        "manifest_hash": file_sha256(path / manifest_name),
        "schema": schema,
        "receipt": receipt,
        "rule": rule,
        "timing": timing,
        "lineage": lineage,
        "signals": signals,
        "outcomes": outcomes,
        "options": options,
        "validation": validation,
    }


class MoritaBotSourceAdapter:
    def inspect_candidates(self) -> dict[str, Any]:
        return inspect_candidates()

    def validate_candidate(self, candidate: Path) -> dict[str, Any]:
        loaded = load_candidate(candidate)
        return {"status": "morita_bot_source_seal_candidate_valid", "signal_row_count": len(loaded["signals"]), "outcome_row_count": len(loaded["outcomes"]), "optional_option_outcome_row_count": len(loaded["options"]), **SAFETY_FLAGS}

    def materialize_if_eligible(self, candidate: Path, output_dir: Path, spec_id: str) -> dict[str, Any]:
        return build_source_artifact(candidate, output_dir, spec_id)

    def build_source_artifact(self, candidate: Path, output_dir: Path, spec_id: str) -> dict[str, Any]:
        return build_source_artifact(candidate, output_dir, spec_id)

    def verify_source_artifact(self, artifact_dir: Path) -> dict[str, Any]:
        return verify_source_artifact(artifact_dir)


class ExistingRunExportAdapter(MoritaBotSourceAdapter):
    pass


class FrozenDeterministicMaterializationAdapter(MoritaBotSourceAdapter):
    pass


class FixtureMoritaBotSourceAdapter(MoritaBotSourceAdapter):
    pass


def write_summary(path: Path, receipt: dict[str, Any]) -> None:
    text = [
        "# Morita Bot Source Seal Artifact",
        "",
        f"Status: `{receipt['status']}`",
        f"Artifact ID: `{receipt['artifact_id']}`",
        f"Signal rows: `{receipt['signal_row_count']}`",
        f"Outcome rows: `{receipt['outcome_row_count']}`",
        "",
        "This artifact is local only and research only. It is not a strategy change, not a trading signal, and not a trade execution system.",
    ]
    (path / "source_artifact_summary.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def build_source_artifact(candidate: Path, output_dir: Path, spec_id: str) -> dict[str, Any]:
    spec = load_spec(spec_id)
    ensure_local_roots()
    require_output_root(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    loaded = load_candidate(candidate)
    artifact_id = output_dir.name
    loaded["signals"].to_csv(output_dir / "morita_bot_signal_events.csv", index=False)
    loaded["outcomes"].to_csv(output_dir / "morita_bot_signal_outcomes.csv", index=False)
    if len(loaded["options"]) > 0:
        loaded["options"].to_csv(output_dir / "morita_bot_option_outcomes_optional.csv", index=False)
    schema_map = {
        "signal_file": "morita_bot_signal_events.csv",
        "outcome_file": "morita_bot_signal_outcomes.csv",
        "source_rule_version": loaded["rule"]["source_rule_version"],
        "signal_columns": {col: col for col in SIGNAL_COLUMNS},
        "outcome_columns": {col: col for col in OUTCOME_COLUMNS},
    }
    if len(loaded["options"]) > 0:
        schema_map["optional_option_file"] = "morita_bot_option_outcomes_optional.csv"
        schema_map["optional_option_columns"] = {col: col for col in OPTION_COLUMNS}
    write_json(output_dir / "source_schema_map.json", schema_map)
    write_json(output_dir / "source_rule_snapshot.json", loaded["rule"])
    write_json(output_dir / "source_timing_contract.json", loaded["timing"])
    write_json(output_dir / "source_input_lineage.json", loaded["lineage"])
    write_csv(output_dir / "source_validation_report.csv", loaded["validation"], ["validation_check", "status", "details"])
    receipt = {
        "artifact_id": artifact_id,
        "status": "morita_bot_source_seal_completed",
        "created_timestamp_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "repository_commit_status": git_status_label(),
        "builder_script_sha256": file_sha256(Path(__file__)),
        "source_seal_spec_hash": file_sha256(SPEC_PATH),
        "source_rule_snapshot_hash": file_sha256(output_dir / "source_rule_snapshot.json"),
        "source_timing_contract_hash": file_sha256(output_dir / "source_timing_contract.json"),
        "source_input_lineage_hash": file_sha256(output_dir / "source_input_lineage.json"),
        "source_content_manifest_hash": "",
        "candidate_id": text_hash(str(candidate.resolve()))[:16],
        "candidate_type": "existing_run_export",
        "source_code_commit_sha": loaded["rule"]["source_code_commit_sha"],
        "source_rule_version": loaded["rule"]["source_rule_version"],
        "source_rule_config_hash": loaded["rule"]["source_rule_config_hash"],
        "signal_row_count": int(len(loaded["signals"])),
        "outcome_row_count": int(len(loaded["outcomes"])),
        "optional_option_outcome_row_count": int(len(loaded["options"])),
        "signal_date_min": str(loaded["signals"]["signal_decision_date"].min()),
        "signal_date_max": str(loaded["signals"]["signal_decision_date"].max()),
        **SAFETY_FLAGS,
    }
    write_summary(output_dir, receipt)
    write_json(output_dir / "source_receipt.json", receipt)
    manifest = build_manifest_for_dir(output_dir, "source_content_manifest.json")
    write_json(output_dir / "source_content_manifest.json", manifest)
    receipt["source_content_manifest_hash"] = file_sha256(output_dir / "source_content_manifest.json")
    write_json(output_dir / "source_receipt.json", receipt)
    manifest = build_manifest_for_dir(output_dir, "source_content_manifest.json")
    write_json(output_dir / "source_content_manifest.json", manifest)
    verify_source_artifact(output_dir)
    return receipt


def verify_source_artifact(artifact_dir: Path) -> dict[str, Any]:
    require_output_root(artifact_dir)
    manifest = verify_manifest(artifact_dir, "source_content_manifest.json")
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    required = set(REQUIRED_ARTIFACT_FILES)
    missing = sorted(required - files)
    if missing:
        raise SystemExit(f"morita_bot_source_seal_artifact_verification_failed:missing_manifest_entry:{missing[0]}")
    loaded = load_candidate(artifact_dir)
    receipt = load_json(artifact_dir / "source_receipt.json")
    required_receipt = [
        "artifact_id",
        "status",
        "created_timestamp_utc",
        "repository_commit_sha",
        "repository_commit_status",
        "builder_script_sha256",
        "source_seal_spec_hash",
        "source_rule_snapshot_hash",
        "source_timing_contract_hash",
        "source_input_lineage_hash",
        "source_content_manifest_hash",
        "candidate_id",
        "candidate_type",
        "source_code_commit_sha",
        "source_rule_version",
        "source_rule_config_hash",
        "signal_row_count",
        "outcome_row_count",
        "optional_option_outcome_row_count",
        "signal_date_min",
        "signal_date_max",
    ]
    for key in required_receipt:
        if str(receipt.get(key, "")).strip() == "":
            raise SystemExit(f"morita_bot_source_seal_artifact_verification_failed:receipt:{key}")
    for key, expected in SAFETY_FLAGS.items():
        if bool(receipt.get(key)) is not expected:
            raise SystemExit(f"morita_bot_source_seal_artifact_verification_failed:safety:{key}")
    return {
        "status": "morita_bot_source_seal_artifact_verified",
        "artifact_dir": repo_relative(artifact_dir),
        "signal_row_count": len(loaded["signals"]),
        "outcome_row_count": len(loaded["outcomes"]),
        "optional_option_outcome_row_count": len(loaded["options"]),
        **SAFETY_FLAGS,
    }


def validate_candidate(candidate: str) -> dict[str, Any]:
    path = Path(candidate)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return ExistingRunExportAdapter().validate_candidate(path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-candidates", action="store_true")
    parser.add_argument("--validate-candidate")
    parser.add_argument("--build-source-artifact", action="store_true")
    parser.add_argument("--spec-id", default="morita_bot_source_seal_v1")
    parser.add_argument("--candidate")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-source-artifact", action="store_true")
    parser.add_argument("--artifact-dir")
    parser.add_argument("--parameter-override", action="store_true")
    parser.add_argument("--input-override")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.parameter_override or args.input_override:
        raise SystemExit("morita_bot_source_seal_parameter_or_input_override_rejected")
    if args.inspect_candidates:
        print(json_dumps(inspect_candidates()))
        return 0
    if args.validate_candidate:
        print(json_dumps(validate_candidate(args.validate_candidate)))
        return 0
    if args.build_source_artifact:
        if not args.candidate or not args.output_dir:
            raise SystemExit("morita_bot_source_seal_source_materialization_blocked:missing_candidate_or_output")
        print(json_dumps(build_source_artifact(Path(args.candidate), Path(args.output_dir), args.spec_id)))
        return 0
    if args.verify_source_artifact:
        if not args.artifact_dir:
            raise SystemExit("morita_bot_source_seal_artifact_verification_failed:missing_artifact_dir")
        print(json_dumps(verify_source_artifact(Path(args.artifact_dir))))
        return 0
    raise SystemExit("morita_bot_source_seal_no_command")


if __name__ == "__main__":
    raise SystemExit(main())
