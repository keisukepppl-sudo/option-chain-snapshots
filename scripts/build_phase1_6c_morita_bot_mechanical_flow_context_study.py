from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "config" / "research_review_v1" / "phase1_6c_morita_bot_mechanical_flow_context_spec.json"

PHASE16B_RECEIPT = "phase1_6b_cross_module_downside_receipt.json"
PHASE16B_MANIFEST = "phase1_6b_cross_module_downside_content_manifest.json"
PHASE16B_PANEL = "cross_module_daily_panel.csv"

MORITA_MANIFEST_NAMES = [
    "morita_bot_source_content_manifest.json",
    "morita_source_content_manifest.json",
    "source_content_manifest.json",
    "content_manifest.json",
]
MORITA_RECEIPT_NAMES = [
    "source_receipt.json",
    "morita_bot_source_receipt.json",
    "morita_run_receipt.json",
    "run_receipt.json",
    "receipt.json",
]
MORITA_SCHEMA_MAP_NAMES = [
    "morita_bot_source_schema_map.json",
    "source_schema_map.json",
    "schema_map.json",
]

SIGNAL_REQUIRED = [
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
OUTCOME_REQUIRED = [
    "signal_id",
    "outcome_status",
    "breakout_day_low_breach_before_timeout",
    "timeout_10_sessions_under_threshold",
    "reached_plus_5pct_within_10_sessions",
    "holding_sessions_at_exit_or_timeout",
    "exit_event_category",
]
OPTIONAL_OUTCOME = [
    "option_profit_target_125pct_reached",
    "option_return_at_declared_exit",
    "underlying_return_at_declared_exit",
    "maximum_adverse_excursion",
    "maximum_favorable_excursion",
    "fees_included_status",
]
ALLOWED_RANKS = ["S", "A", "B"]
ALLOWED_EXIT_EVENTS = {
    "profit_target",
    "hard_stop",
    "breakout_day_low_breach",
    "timeout_10_sessions_under_threshold",
    "other_predeclared_rule",
    "unavailable",
}
REQUIRED_OUTPUT_FILES = [
    "morita_bot_source_artifact_integrity.csv",
    "morita_bot_signal_context_alignment_audit.csv",
    "morita_bot_canonical_signal_outcome_panel.csv",
    "morita_bot_outcome_definitions.json",
    "morita_bot_context_condition_summary.csv",
    "morita_bot_rank_context_summary.csv",
    "morita_bot_joint_context_summary.csv",
    "morita_bot_context_concentration_diagnostics.csv",
    "morita_bot_window_coverage.csv",
    "phase1_6c_morita_bot_mechanical_flow_context_receipt.json",
    "phase1_6c_morita_bot_mechanical_flow_context_summary.md",
    "phase1_6c_morita_bot_mechanical_flow_context_limitations.md",
    "phase1_6c_morita_bot_mechanical_flow_context_content_manifest.json",
]
PANEL_COLUMNS = [
    "signal_id_hash",
    "signal_decision_date",
    "entry_session",
    "underlying_symbol",
    "signal_rank",
    "strategy_family",
    "theme",
    "source_rule_version",
    "source_run_id",
    "cta_context_category",
    "vol_context_category",
    "etf_scale_context_category",
    "context_combination_id",
    "breakout_day_low_breach_before_timeout",
    "timeout_10_sessions_under_threshold",
    "reached_plus_5pct_within_10_sessions",
    "holding_sessions_at_exit_or_timeout",
    "exit_event_category",
    "option_profit_target_125pct_reached_if_available",
    "option_return_at_declared_exit_if_available",
    "outcome_data_completeness_status",
]
FORBIDDEN_OUTPUT_FIELDS = {
    "raw_price",
    "raw_close",
    "raw_option",
    "option_chain",
    "broker_account",
    "credential",
    "account_number",
    "recommendation",
    "trade_filter",
    "composite_score",
    "ranking_score",
}
SAFETY_FLAGS = {
    "research_only": True,
    "actionization_allowed": False,
    "not_a_trading_signal": True,
    "not_a_trade_execution_system": True,
    "not_a_model_selection_study": True,
    "not_a_predictive_model": True,
    "not_a_causal_study": True,
    "not_an_actual_cta_position_estimate": True,
    "not_an_actual_cta_flow_estimate": True,
    "not_an_actual_manager_flow_estimate": True,
    "not_an_actual_etf_flow_estimate": True,
    "not_an_actual_market_impact_estimate": True,
    "predictive_pit_eligible": False,
    "phase2_eligible": False,
    "release_created": False,
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


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def boolish_to_float(value: Any) -> float | None:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return 1.0
    if text in {"false", "0", "no", "n"}:
        return 0.0
    return None


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    blocked = sorted({name.lower() for name in fieldnames} & FORBIDDEN_OUTPUT_FIELDS)
    if blocked:
        raise SystemExit(f"phase1_6c_forbidden_output_field:{blocked[0]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def load_spec(spec_id: str) -> dict[str, Any]:
    registry = load_json(SPEC_PATH)
    for spec in registry.get("specs", []):
        if spec.get("study_spec_id") == spec_id:
            return spec
    raise SystemExit(f"phase1_6c_unknown_spec_id:{spec_id}")


def reject_output_dir(path: Path) -> None:
    parts = {part.lower() for part in path.resolve().parts}
    if "market_bomb_history" in parts:
        raise SystemExit("phase1_6c_output_dir_rejected")


def verify_manifested_dir(path: Path, manifest_name: str, code_prefix: str) -> dict[str, Any]:
    manifest_path = path / manifest_name
    if not manifest_path.exists():
        raise SystemExit(f"{code_prefix}_manifest_missing")
    manifest = load_json(manifest_path)
    expected = {str(entry["relative_path"]): str(entry["sha256"]) for entry in manifest.get("files", [])}
    actual = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file() and p.name != manifest_name}
    for rel, expected_hash in expected.items():
        target = path / rel
        if not target.exists():
            raise SystemExit(f"{code_prefix}_manifest_invalid:missing:{rel}")
        if file_sha256(target) != expected_hash:
            raise SystemExit(f"{code_prefix}_manifest_invalid:sha:{rel}")
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise SystemExit(f"{code_prefix}_manifest_invalid:extra:{extras[0]}")
    return manifest


def verify_output_manifest(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifested_dir(output_dir, "phase1_6c_morita_bot_mechanical_flow_context_content_manifest.json", "phase1_6c_output")
    expected = {str(entry["relative_path"]) for entry in manifest.get("files", [])}
    missing = [name for name in REQUIRED_OUTPUT_FILES if name != "phase1_6c_morita_bot_mechanical_flow_context_content_manifest.json" and name not in expected]
    if missing:
        raise SystemExit(f"phase1_6c_output_manifest_missing_entry:{missing[0]}")
    return manifest


def require_phase16b_context(path: Path, spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    if path.resolve().parts and "market_bomb_history" in {p.lower() for p in path.resolve().parts}:
        raise SystemExit("phase1_6c_phase1_6b_source_dir_rejected")
    manifest = verify_manifested_dir(path, PHASE16B_MANIFEST, "phase1_6c_phase1_6b_source")
    receipt_path = path / PHASE16B_RECEIPT
    if not receipt_path.exists():
        raise SystemExit("phase1_6c_phase1_6b_receipt_missing")
    receipt = load_json(receipt_path)
    if receipt.get("run_status") != "phase1_6b_cross_module_downside_completed":
        raise SystemExit("phase1_6c_phase1_6b_receipt_not_completed")
    for key, expected in {
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }.items():
        if bool_value(receipt.get(key)) is not expected:
            raise SystemExit(f"phase1_6c_phase1_6b_safety_flag_mismatch:{key}")
    panel = pd.read_csv(path / PHASE16B_PANEL, dtype=str).fillna("")
    required = [
        "observation_date",
        "next_effective_session",
        "cta_consensus_category",
        "vol_change_consensus_category",
        "combined_mechanical_sensitivity_ex_post_quartile",
        "combined_scale_status",
    ]
    missing = [col for col in required if col not in panel.columns]
    if missing:
        raise SystemExit(f"phase1_6c_phase1_6b_missing_panel_column:{missing[0]}")
    if panel["observation_date"].duplicated().any():
        raise SystemExit("morita_bot_context_duplicate_date")
    panel = panel[required].copy()
    panel["etf_scale_context_category"] = panel["combined_mechanical_sensitivity_ex_post_quartile"].where(
        panel["combined_scale_status"].astype(str).str.contains("available", case=False, na=False),
        "etf_sensitivity_unavailable",
    )
    for col, allowed in [
        ("cta_consensus_category", spec["context_categories"]["cta"]),
        ("vol_change_consensus_category", spec["context_categories"]["vol"]),
        ("etf_scale_context_category", spec["context_categories"]["etf"]),
    ]:
        bad = sorted(set(panel[col]) - set(allowed))
        if bad:
            raise SystemExit(f"phase1_6c_phase1_6b_unexpected_context_category:{col}:{bad[0]}")
    return panel, receipt, manifest


def first_existing(path: Path, names: list[str]) -> Path | None:
    for name in names:
        candidate = path / name
        if candidate.exists():
            return candidate
    return None


def inspect_morita_bot_source_artifacts(root: Path | None = None) -> dict[str, Any]:
    base = root or REPO_ROOT
    candidates: list[dict[str, Any]] = []
    search_roots = [base / "outputs", base / "market_bomb_history", base]
    seen: set[Path] = set()
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for child in search_root.rglob("*"):
            if not child.is_dir() or child in seen:
                continue
            seen.add(child)
            manifest = first_existing(child, MORITA_MANIFEST_NAMES)
            receipt = first_existing(child, MORITA_RECEIPT_NAMES)
            schema = first_existing(child, MORITA_SCHEMA_MAP_NAMES)
            has_signal_file = any(p.name.lower() in {"morita_bot_signal_rows.csv", "signals.csv", "signal_rows.csv"} for p in child.glob("*.csv"))
            has_outcome_file = any(p.name.lower() in {"morita_bot_outcome_rows.csv", "outcomes.csv", "outcome_rows.csv"} for p in child.glob("*.csv"))
            if manifest or receipt or schema or (has_signal_file and has_outcome_file):
                reasons = []
                if not manifest:
                    reasons.append("morita_bot_source_manifest_invalid")
                if not receipt:
                    reasons.append("morita_bot_source_receipt_missing")
                if not schema:
                    reasons.append("morita_bot_outcome_contract_incomplete")
                if not has_signal_file:
                    reasons.append("morita_bot_signal_level_rows_missing")
                if not has_outcome_file:
                    reasons.append("morita_bot_outcome_contract_incomplete")
                candidates.append(
                    {
                        "artifact_path_relative": repo_relative(child),
                        "manifest_present": bool(manifest),
                        "receipt_present": bool(receipt),
                        "schema_map_present": bool(schema),
                        "signal_rows_present": has_signal_file,
                        "outcome_rows_present": has_outcome_file,
                        "eligibility_status": "candidate_needs_validation" if not reasons else "ineligible",
                        "block_codes": ";".join(dict.fromkeys(reasons)),
                    }
                )
    status = "morita_bot_source_artifact_not_found" if not candidates else "morita_bot_source_artifact_candidates_found"
    return {"status": status, "candidate_count": len(candidates), "candidates": candidates, **SAFETY_FLAGS}


def manifest_name_for_artifact(path: Path) -> str:
    found = first_existing(path, MORITA_MANIFEST_NAMES)
    if not found:
        raise SystemExit("morita_bot_source_manifest_invalid")
    return found.name


def receipt_path_for_artifact(path: Path) -> Path:
    found = first_existing(path, MORITA_RECEIPT_NAMES)
    if not found:
        raise SystemExit("morita_bot_source_receipt_missing")
    return found


def schema_path_for_artifact(path: Path) -> Path:
    found = first_existing(path, MORITA_SCHEMA_MAP_NAMES)
    if not found:
        raise SystemExit("morita_bot_outcome_contract_incomplete")
    return found


def mapped_frame(path: Path, filename: str, column_map: dict[str, str], required: list[str], code: str) -> pd.DataFrame:
    target = path / filename
    if not target.exists():
        raise SystemExit(code)
    src = pd.read_csv(target, dtype=str).fillna("")
    missing_source = [src_col for src_col in column_map.values() if src_col not in src.columns]
    if missing_source:
        raise SystemExit(f"{code}:{missing_source[0]}")
    out = pd.DataFrame()
    for canonical, source_col in column_map.items():
        out[canonical] = src[source_col].astype(str)
    missing_canonical = [col for col in required if col not in out.columns]
    if missing_canonical:
        raise SystemExit(f"{code}:{missing_canonical[0]}")
    return out


def validate_morita_bot_run_artifact(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_dir():
        raise SystemExit("morita_bot_source_artifact_not_found")
    manifest_name = manifest_name_for_artifact(path)
    manifest = verify_manifested_dir(path, manifest_name, "morita_bot_source")
    receipt = load_json(receipt_path_for_artifact(path))
    schema = load_json(schema_path_for_artifact(path))
    if not receipt.get("repository_commit_sha"):
        raise SystemExit("morita_bot_source_receipt_missing")
    if not (receipt.get("run_status") or receipt.get("source_run_status") or receipt.get("status")):
        raise SystemExit("morita_bot_source_receipt_missing")
    if not (receipt.get("source_rule_version") or receipt.get("rule_version") or schema.get("source_rule_version")):
        raise SystemExit("morita_bot_rule_version_missing")
    signal_file = str(schema.get("signal_file", ""))
    outcome_file = str(schema.get("outcome_file", ""))
    signal_map = dict(schema.get("signal_columns", {}))
    outcome_map = dict(schema.get("outcome_columns", {}))
    optional_map = dict(schema.get("optional_outcome_columns", {}))
    signals = mapped_frame(path, signal_file, signal_map, SIGNAL_REQUIRED, "morita_bot_signal_level_rows_missing")
    outcomes = mapped_frame(path, outcome_file, {**outcome_map, **optional_map}, OUTCOME_REQUIRED, "morita_bot_outcome_contract_incomplete")
    if signals["signal_id"].duplicated().any():
        raise SystemExit("morita_bot_duplicate_signal_id")
    if outcomes["signal_id"].duplicated().any():
        raise SystemExit("morita_bot_outcome_contract_incomplete:duplicate_signal_id")
    bad_rank = sorted(set(signals["signal_rank"]) - set(ALLOWED_RANKS))
    if bad_rank:
        raise SystemExit(f"morita_bot_source_artifact_ineligible:invalid_rank:{bad_rank[0]}")
    bad_exit = sorted(set(outcomes["exit_event_category"]) - ALLOWED_EXIT_EVENTS)
    if bad_exit:
        raise SystemExit(f"morita_bot_source_artifact_ineligible:invalid_exit_event:{bad_exit[0]}")
    decision_dates = pd.to_datetime(signals["signal_decision_date"], errors="coerce")
    decision_ts = pd.to_datetime(signals["signal_decision_timestamp_utc"], utc=True, errors="coerce")
    entries = pd.to_datetime(signals["entry_session"], errors="coerce")
    if decision_dates.isna().any() or decision_ts.isna().any():
        raise SystemExit("morita_bot_signal_timing_ambiguous")
    if entries.isna().any() or (entries.dt.date <= decision_dates.dt.date).any():
        raise SystemExit("morita_bot_entry_session_invalid")
    if set(outcomes["signal_id"]) - set(signals["signal_id"]):
        raise SystemExit("morita_bot_outcome_contract_incomplete:orphan_outcome")
    merged = signals.merge(outcomes, on="signal_id", how="inner")
    if len(merged) != len(signals):
        raise SystemExit("morita_bot_outcome_contract_incomplete:missing_outcome")
    result = {
        "status": "morita_bot_source_artifact_eligible",
        "artifact_path_relative": repo_relative(path),
        "signal_rows": int(len(signals)),
        "outcome_rows": int(len(outcomes)),
        "manifest_hash": file_sha256(path / manifest_name),
        "receipt_hash": file_sha256(receipt_path_for_artifact(path)),
        "schema_map_hash": file_sha256(schema_path_for_artifact(path)),
        "source_manifest_hash": manifest.get("content_set_hash", file_sha256(path / manifest_name)),
        "repository_commit_sha": receipt.get("repository_commit_sha", ""),
        "rule_version_or_model_spec_id": receipt.get("source_rule_version") or receipt.get("rule_version") or schema.get("source_rule_version", ""),
        "module_or_builder_source_sha256": receipt.get("module_source_sha256", ""),
        "source_module": receipt.get("source_module", "morita_bot_source_artifact"),
        "signals": signals,
        "outcomes": outcomes,
        "receipt": receipt,
        "manifest": manifest,
        "schema": schema,
    }
    return result


def context_combination_id(cta: str, vol: str, etf: str) -> str:
    return f"{cta}__{vol}__{etf}"


def hash_id(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def build_panel(signals: pd.DataFrame, outcomes: pd.DataFrame, context: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    merged = signals.merge(outcomes, on="signal_id", how="left", suffixes=("", "_outcome"))
    ctx = context.rename(
        columns={
            "cta_consensus_category": "cta_context_category",
            "vol_change_consensus_category": "vol_context_category",
        }
    )
    out = merged.merge(ctx, left_on="signal_decision_date", right_on="observation_date", how="left")
    missing_context = int((out["cta_context_category"].isna() | out["cta_context_category"].eq("")).sum() if "cta_context_category" in out else len(out))
    out["cta_context_category"] = out["cta_context_category"].replace("", pd.NA).fillna("cta_incomplete")
    out["vol_context_category"] = out["vol_context_category"].replace("", pd.NA).fillna("vol_incomplete")
    out["etf_scale_context_category"] = out["etf_scale_context_category"].replace("", pd.NA).fillna("etf_sensitivity_unavailable")
    out["context_combination_id"] = [
        context_combination_id(c, v, e)
        for c, v, e in zip(out["cta_context_category"], out["vol_context_category"], out["etf_scale_context_category"])
    ]
    completeness_cols = [
        "breakout_day_low_breach_before_timeout",
        "timeout_10_sessions_under_threshold",
        "reached_plus_5pct_within_10_sessions",
        "holding_sessions_at_exit_or_timeout",
    ]
    out["outcome_data_completeness_status"] = out[completeness_cols].apply(lambda row: "complete" if all(str(v).strip() != "" for v in row) else "incomplete", axis=1)
    if "option_profit_target_125pct_reached" not in out.columns:
        out["option_profit_target_125pct_reached"] = ""
    if "option_return_at_declared_exit" not in out.columns:
        out["option_return_at_declared_exit"] = ""
    panel = pd.DataFrame(
        {
            "signal_id_hash": out["signal_id"].map(hash_id),
            "signal_decision_date": out["signal_decision_date"],
            "entry_session": out["entry_session"],
            "underlying_symbol": out["underlying_symbol"],
            "signal_rank": out["signal_rank"],
            "strategy_family": out["strategy_family"],
            "theme": out["theme"],
            "source_rule_version": out["source_rule_version"],
            "source_run_id": out["source_run_id"],
            "cta_context_category": out["cta_context_category"],
            "vol_context_category": out["vol_context_category"],
            "etf_scale_context_category": out["etf_scale_context_category"],
            "context_combination_id": out["context_combination_id"],
            "breakout_day_low_breach_before_timeout": out["breakout_day_low_breach_before_timeout"],
            "timeout_10_sessions_under_threshold": out["timeout_10_sessions_under_threshold"],
            "reached_plus_5pct_within_10_sessions": out["reached_plus_5pct_within_10_sessions"],
            "holding_sessions_at_exit_or_timeout": out["holding_sessions_at_exit_or_timeout"],
            "exit_event_category": out["exit_event_category"],
            "option_profit_target_125pct_reached_if_available": out["option_profit_target_125pct_reached"],
            "option_return_at_declared_exit_if_available": out["option_return_at_declared_exit"],
            "outcome_data_completeness_status": out["outcome_data_completeness_status"],
        }
    )
    return panel, {"missing_context_rows": missing_context}


def window_filter(panel: pd.DataFrame, window: dict[str, Any]) -> pd.DataFrame:
    dates = pd.to_datetime(panel["signal_decision_date"], errors="coerce")
    mask = dates.notna()
    if window.get("start"):
        mask &= dates >= pd.Timestamp(window["start"])
    if window.get("end"):
        mask &= dates <= pd.Timestamp(window["end"])
    return panel.loc[mask].copy()


def pct_quantile(values: pd.Series, q: float) -> str:
    nums = pd.to_numeric(values, errors="coerce").dropna()
    if nums.empty:
        return ""
    return float(nums.quantile(q))


def rate(values: pd.Series) -> str:
    nums = [v for v in (boolish_to_float(x) for x in values) if v is not None]
    if not nums:
        return ""
    return sum(nums) / len(nums)


def concentration_fields(df: pd.DataFrame) -> dict[str, Any]:
    n = len(df)
    if n == 0:
        return {
            "unique_underlying_count": 0,
            "unique_theme_count": 0,
            "largest_single_underlying_signal_share": "",
            "top_3_underlying_signal_share": "",
            "largest_single_theme_signal_share": "",
            "source_run_count": 0,
            "rank_mix": "",
        }
    underlying_counts = df["underlying_symbol"].value_counts()
    theme_counts = df["theme"].value_counts()
    rank_counts = df["signal_rank"].value_counts().sort_index()
    return {
        "unique_underlying_count": int(df["underlying_symbol"].nunique()),
        "unique_theme_count": int(df["theme"].nunique()),
        "largest_single_underlying_signal_share": float(underlying_counts.iloc[0] / n) if not underlying_counts.empty else "",
        "top_3_underlying_signal_share": float(underlying_counts.head(3).sum() / n) if not underlying_counts.empty else "",
        "largest_single_theme_signal_share": float(theme_counts.iloc[0] / n) if not theme_counts.empty else "",
        "source_run_count": int(df["source_run_id"].nunique()),
        "rank_mix": ";".join(f"{rank}:{count}" for rank, count in rank_counts.items()),
    }


def concentration_label(count: int, share: Any, gate: int) -> str:
    if count < gate or share == "":
        return "concentration_not_assessed"
    return "concentration_present" if float(share) >= 0.5 else "concentration_not_present"


def option_metrics(df: pd.DataFrame) -> dict[str, Any]:
    option_available = df["option_return_at_declared_exit_if_available"].astype(str).str.strip().ne("").all() and len(df) > 0
    target_available = df["option_profit_target_125pct_reached_if_available"].astype(str).str.strip().ne("").all() and len(df) > 0
    if not option_available:
        return {
            "option_metrics_available": False,
            "option_metrics_unavailable_reason": "option_outcome_not_available_from_source",
            "option_profit_target_125pct_reached_rate": rate(df["option_profit_target_125pct_reached_if_available"]) if target_available else "",
            "option_return_at_declared_exit_mean": "",
            "option_return_at_declared_exit_median": "",
            "option_return_at_declared_exit_p10": "",
            "option_return_at_declared_exit_p25": "",
            "option_return_at_declared_exit_p75": "",
            "option_return_at_declared_exit_p90": "",
            "option_positive_return_rate": "",
            "option_profit_factor": "",
        }
    vals = pd.to_numeric(df["option_return_at_declared_exit_if_available"], errors="coerce").dropna()
    gains = vals[vals > 0].sum()
    losses = vals[vals < 0].sum()
    return {
        "option_metrics_available": True,
        "option_metrics_unavailable_reason": "",
        "option_profit_target_125pct_reached_rate": rate(df["option_profit_target_125pct_reached_if_available"]) if target_available else "",
        "option_return_at_declared_exit_mean": float(vals.mean()) if len(vals) else "",
        "option_return_at_declared_exit_median": float(vals.median()) if len(vals) else "",
        "option_return_at_declared_exit_p10": float(vals.quantile(0.10)) if len(vals) else "",
        "option_return_at_declared_exit_p25": float(vals.quantile(0.25)) if len(vals) else "",
        "option_return_at_declared_exit_p75": float(vals.quantile(0.75)) if len(vals) else "",
        "option_return_at_declared_exit_p90": float(vals.quantile(0.90)) if len(vals) else "",
        "option_positive_return_rate": float((vals > 0).mean()) if len(vals) else "",
        "option_profit_factor": float(gains / abs(losses)) if losses < 0 else "",
    }


def summary_metrics(df: pd.DataFrame, minimum: int) -> dict[str, Any]:
    n = len(df)
    available = n >= minimum
    base = {
        "signal_count": n,
        "metrics_available": available,
        "metrics_unavailable_reason": "" if available else "signal_count_below_minimum",
        "breakout_day_low_breach_rate": "",
        "timeout_10_sessions_under_threshold_rate": "",
        "reached_plus_5pct_within_10_sessions_rate": "",
        "median_holding_sessions": "",
        "p25_holding_sessions": "",
        "p75_holding_sessions": "",
        "outcome_data_completeness_rate": "",
    }
    if available:
        base.update(
            {
                "breakout_day_low_breach_rate": rate(df["breakout_day_low_breach_before_timeout"]),
                "timeout_10_sessions_under_threshold_rate": rate(df["timeout_10_sessions_under_threshold"]),
                "reached_plus_5pct_within_10_sessions_rate": rate(df["reached_plus_5pct_within_10_sessions"]),
                "median_holding_sessions": pct_quantile(df["holding_sessions_at_exit_or_timeout"], 0.50),
                "p25_holding_sessions": pct_quantile(df["holding_sessions_at_exit_or_timeout"], 0.25),
                "p75_holding_sessions": pct_quantile(df["holding_sessions_at_exit_or_timeout"], 0.75),
                "outcome_data_completeness_rate": float(df["outcome_data_completeness_status"].eq("complete").mean()) if n else "",
            }
        )
    base.update(option_metrics(df) if available else {
        "option_metrics_available": False,
        "option_metrics_unavailable_reason": "signal_count_below_minimum",
        "option_profit_target_125pct_reached_rate": "",
        "option_return_at_declared_exit_mean": "",
        "option_return_at_declared_exit_median": "",
        "option_return_at_declared_exit_p10": "",
        "option_return_at_declared_exit_p25": "",
        "option_return_at_declared_exit_p75": "",
        "option_return_at_declared_exit_p90": "",
        "option_positive_return_rate": "",
        "option_profit_factor": "",
    })
    base.update(concentration_fields(df))
    return base


def build_summaries(panel: pd.DataFrame, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    condition_rows: list[dict[str, Any]] = []
    rank_rows: list[dict[str, Any]] = []
    joint_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    for window in spec["analysis_windows"]:
        wid = window["analysis_window_id"]
        wdf = window_filter(panel, window)
        coverage_rows.append({"analysis_window_id": wid, "window_class": window["window_class"], "start": window.get("start") or "", "end": window.get("end") or "", "signal_count": len(wdf)})
        for layer, col, categories in [
            ("CTA", "cta_context_category", spec["context_categories"]["cta"]),
            ("Vol", "vol_context_category", spec["context_categories"]["vol"]),
            ("ETF", "etf_scale_context_category", spec["context_categories"]["etf"]),
        ]:
            for category in categories:
                cdf = wdf[wdf[col] == category]
                metrics = summary_metrics(cdf, int(spec["minimum_signal_count_for_single_context_summary"]))
                row = {
                    "context_layer": layer,
                    "context_category": category,
                    "analysis_window_id": wid,
                    "window_class": window["window_class"],
                    **metrics,
                    "ex_post_only": True,
                    "not_predictive": True,
                    "not_a_trade_filter": True,
                }
                condition_rows.append(row)
                concentration_rows.append(concentration_row("single_context", wid, category, cdf, spec))
                for rank in ALLOWED_RANKS:
                    rdf = cdf[cdf["signal_rank"] == rank]
                    rmetrics = summary_metrics(rdf, int(spec["minimum_signal_count_for_single_rank_summary"]))
                    rank_rows.append(
                        {
                            "signal_rank": rank,
                            "context_layer": layer,
                            "context_category": category,
                            "analysis_window_id": wid,
                            "window_class": window["window_class"],
                            "signal_count": rmetrics["signal_count"],
                            "metrics_available": rmetrics["metrics_available"],
                            "metrics_unavailable_reason": rmetrics["metrics_unavailable_reason"],
                            "breakout_day_low_breach_rate": rmetrics["breakout_day_low_breach_rate"],
                            "timeout_10_sessions_under_threshold_rate": rmetrics["timeout_10_sessions_under_threshold_rate"],
                            "reached_plus_5pct_within_10_sessions_rate": rmetrics["reached_plus_5pct_within_10_sessions_rate"],
                            "median_holding_sessions": rmetrics["median_holding_sessions"],
                            "outcome_data_completeness_rate": rmetrics["outcome_data_completeness_rate"],
                            "option_metrics_available": rmetrics["option_metrics_available"],
                            "option_profit_target_125pct_reached_rate": rmetrics["option_profit_target_125pct_reached_rate"],
                            "option_return_at_declared_exit_median": rmetrics["option_return_at_declared_exit_median"],
                            "option_profit_factor": rmetrics["option_profit_factor"],
                            "unique_underlying_count": rmetrics["unique_underlying_count"],
                            "unique_theme_count": rmetrics["unique_theme_count"],
                            "ex_post_only": True,
                            "not_predictive": True,
                            "not_a_rank_sizing_rule": True,
                        }
                    )
        for cta, vol, etf in product(spec["context_categories"]["cta"], spec["context_categories"]["vol"], spec["context_categories"]["etf"]):
            combo = context_combination_id(cta, vol, etf)
            jdf = wdf[wdf["context_combination_id"] == combo]
            jmetrics = summary_metrics(jdf, int(spec["minimum_signal_count_for_joint_context_summary"]))
            joint_rows.append(
                {
                    "cta_context_category": cta,
                    "vol_context_category": vol,
                    "etf_scale_context_category": etf,
                    "context_combination_id": combo,
                    "analysis_window_id": wid,
                    "window_class": window["window_class"],
                    "signal_count": jmetrics["signal_count"],
                    "metrics_available": jmetrics["metrics_available"],
                    "metrics_unavailable_reason": jmetrics["metrics_unavailable_reason"],
                    "breakout_day_low_breach_rate": jmetrics["breakout_day_low_breach_rate"],
                    "timeout_10_sessions_under_threshold_rate": jmetrics["timeout_10_sessions_under_threshold_rate"],
                    "reached_plus_5pct_within_10_sessions_rate": jmetrics["reached_plus_5pct_within_10_sessions_rate"],
                    "median_holding_sessions": jmetrics["median_holding_sessions"],
                    "outcome_data_completeness_rate": jmetrics["outcome_data_completeness_rate"],
                    "option_metrics_available": jmetrics["option_metrics_available"],
                    "option_profit_target_125pct_reached_rate": jmetrics["option_profit_target_125pct_reached_rate"],
                    "option_return_at_declared_exit_median": jmetrics["option_return_at_declared_exit_median"],
                    "option_profit_factor": jmetrics["option_profit_factor"],
                    "unique_underlying_count": jmetrics["unique_underlying_count"],
                    "unique_theme_count": jmetrics["unique_theme_count"],
                    "largest_single_underlying_signal_share": jmetrics["largest_single_underlying_signal_share"],
                    "top_3_underlying_signal_share": jmetrics["top_3_underlying_signal_share"],
                    "ex_post_only": True,
                    "not_predictive": True,
                    "not_a_composite_score": True,
                    "not_a_trade_filter": True,
                }
            )
            concentration_rows.append(concentration_row("joint_context", wid, combo, jdf, spec))
    return condition_rows, rank_rows, joint_rows, concentration_rows, coverage_rows


def concentration_row(kind: str, window_id: str, cohort_id: str, df: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    fields = concentration_fields(df)
    gate = int(spec["minimum_signal_count_for_symbol_concentration_diagnostic"])
    return {
        "cohort_type": kind,
        "analysis_window_id": window_id,
        "cohort_id": cohort_id,
        "signal_count": len(df),
        "unique_underlying_count": fields["unique_underlying_count"],
        "unique_theme_count": fields["unique_theme_count"],
        "largest_single_underlying_signal_share": fields["largest_single_underlying_signal_share"],
        "top_3_underlying_signal_share": fields["top_3_underlying_signal_share"],
        "largest_single_theme_signal_share": fields["largest_single_theme_signal_share"],
        "source_run_count": fields["source_run_count"],
        "rank_mix": fields["rank_mix"],
        "underlying_concentration_diagnostic": concentration_label(len(df), fields["largest_single_underlying_signal_share"], gate),
        "theme_concentration_diagnostic": concentration_label(len(df), fields["largest_single_theme_signal_share"], gate),
        "source_run_concentration_diagnostic": "concentration_present" if fields["source_run_count"] == 1 and len(df) >= gate else ("concentration_not_assessed" if len(df) < gate else "concentration_not_present"),
    }


def build_alignment_rows(panel: pd.DataFrame, stats: dict[str, int], spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    total = len(panel)
    matched = total - int(stats.get("missing_context_rows", 0))
    ratio = matched / total if total else 0.0
    status = "valid" if ratio >= float(spec["minimum_signal_context_alignment_ratio"]) else "morita_bot_context_alignment_inadequate"
    for window in spec["analysis_windows"]:
        wdf = window_filter(panel, window)
        rows.append(
            {
                "analysis_window_id": window["analysis_window_id"],
                "source_signal_rows": total,
                "valid_signal_rows": len(wdf),
                "exact_context_matched_rows": int((wdf["cta_context_category"] != "cta_incomplete").sum()),
                "missing_context_rows": int((wdf["cta_context_category"] == "cta_incomplete").sum()),
                "timing_ambiguous_rows": 0,
                "invalid_entry_session_rows": 0,
                "pre_entry_outcome_invalid_rows": 0,
                "duplicate_signal_id_rows": 0,
                "context_alignment_ratio": ratio,
                "status": status,
            }
        )
    return rows


def build_content_manifest(output_dir: Path, run_id: str) -> dict[str, Any]:
    manifest_name = "phase1_6c_morita_bot_mechanical_flow_context_content_manifest.json"
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != manifest_name:
            files.append({"relative_path": path.relative_to(output_dir).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "artifact_version": "phase1_6c_morita_bot_mechanical_flow_context_v1_0_0",
        "module_name": "phase1_6c_morita_bot_mechanical_flow_context_study",
        "run_id": run_id,
        "files": files,
    }
    write_json(output_dir / manifest_name, manifest)
    return manifest


def base_receipt(status: str, spec_id: str, run_id: str) -> dict[str, Any]:
    return {
        "run_status": status,
        "study_spec_id": spec_id,
        "run_id": run_id,
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        **SAFETY_FLAGS,
    }


def write_blocked_outputs(output_dir: Path, spec: dict[str, Any], status: str, block_codes: list[str], phase16b_status: str, inventory: dict[str, Any]) -> dict[str, Any]:
    reject_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = "blocked_" + text_hash(json_dumps({"status": status, "block_codes": block_codes, "inventory": inventory}) )[:12]
    integrity_cols = ["source_module", "artifact_path_relative", "run_id", "rule_version_or_model_spec_id", "verification_status", "source_manifest_hash", "repository_commit_sha", "module_or_builder_source_sha256", "research_only", "actionization_allowed", "predictive_pit_eligible", "phase2_eligible"]
    integrity_rows = [
        {
            "source_module": "morita_bot_source_artifact",
            "artifact_path_relative": "",
            "run_id": "",
            "rule_version_or_model_spec_id": "",
            "verification_status": ";".join(block_codes),
            "source_manifest_hash": "",
            "repository_commit_sha": "",
            "module_or_builder_source_sha256": "",
            "research_only": True,
            "actionization_allowed": False,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
        }
    ]
    write_csv(output_dir / "morita_bot_source_artifact_integrity.csv", integrity_rows, integrity_cols)
    empty_alignment = [{"analysis_window_id": w["analysis_window_id"], "source_signal_rows": 0, "valid_signal_rows": 0, "exact_context_matched_rows": 0, "missing_context_rows": 0, "timing_ambiguous_rows": 0, "invalid_entry_session_rows": 0, "pre_entry_outcome_invalid_rows": 0, "duplicate_signal_id_rows": 0, "context_alignment_ratio": 0, "status": ";".join(block_codes)} for w in spec["analysis_windows"]]
    write_csv(output_dir / "morita_bot_signal_context_alignment_audit.csv", empty_alignment, list(empty_alignment[0].keys()))
    write_csv(output_dir / "morita_bot_canonical_signal_outcome_panel.csv", [], PANEL_COLUMNS)
    write_json(output_dir / "morita_bot_outcome_definitions.json", {"minimum_eligible_outcome_set": OUTCOME_REQUIRED, "option_outcome_analysis_status": "unavailable_from_source_artifact", **SAFETY_FLAGS})
    condition_rows, rank_rows, joint_rows, concentration_rows, coverage_rows = build_summaries(pd.DataFrame(columns=PANEL_COLUMNS), spec)
    write_summary_tables(output_dir, condition_rows, rank_rows, joint_rows, concentration_rows, coverage_rows)
    receipt = base_receipt(status, spec["study_spec_id"], run_id)
    receipt.update({"block_codes": block_codes, "phase1_6b_integrity_status": phase16b_status, "morita_bot_source_artifact_eligibility": "ineligible_or_missing", "real_study_run_occurred": False, "inventory": inventory})
    write_json(output_dir / "phase1_6c_morita_bot_mechanical_flow_context_receipt.json", receipt)
    write_markdown(output_dir, receipt, [], option_status="unavailable_from_source_artifact")
    build_content_manifest(output_dir, run_id)
    return receipt


def write_summary_tables(output_dir: Path, condition_rows: list[dict[str, Any]], rank_rows: list[dict[str, Any]], joint_rows: list[dict[str, Any]], concentration_rows: list[dict[str, Any]], coverage_rows: list[dict[str, Any]]) -> None:
    condition_cols = ["context_layer", "context_category", "analysis_window_id", "window_class", "signal_count", "metrics_available", "metrics_unavailable_reason", "breakout_day_low_breach_rate", "timeout_10_sessions_under_threshold_rate", "reached_plus_5pct_within_10_sessions_rate", "median_holding_sessions", "p25_holding_sessions", "p75_holding_sessions", "outcome_data_completeness_rate", "option_metrics_available", "option_metrics_unavailable_reason", "option_profit_target_125pct_reached_rate", "option_return_at_declared_exit_mean", "option_return_at_declared_exit_median", "option_return_at_declared_exit_p10", "option_return_at_declared_exit_p25", "option_return_at_declared_exit_p75", "option_return_at_declared_exit_p90", "option_positive_return_rate", "option_profit_factor", "unique_underlying_count", "unique_theme_count", "largest_single_underlying_signal_share", "top_3_underlying_signal_share", "largest_single_theme_signal_share", "ex_post_only", "not_predictive", "not_a_trade_filter"]
    rank_cols = ["signal_rank", "context_layer", "context_category", "analysis_window_id", "window_class", "signal_count", "metrics_available", "metrics_unavailable_reason", "breakout_day_low_breach_rate", "timeout_10_sessions_under_threshold_rate", "reached_plus_5pct_within_10_sessions_rate", "median_holding_sessions", "outcome_data_completeness_rate", "option_metrics_available", "option_profit_target_125pct_reached_rate", "option_return_at_declared_exit_median", "option_profit_factor", "unique_underlying_count", "unique_theme_count", "ex_post_only", "not_predictive", "not_a_rank_sizing_rule"]
    joint_cols = ["cta_context_category", "vol_context_category", "etf_scale_context_category", "context_combination_id", "analysis_window_id", "window_class", "signal_count", "metrics_available", "metrics_unavailable_reason", "breakout_day_low_breach_rate", "timeout_10_sessions_under_threshold_rate", "reached_plus_5pct_within_10_sessions_rate", "median_holding_sessions", "outcome_data_completeness_rate", "option_metrics_available", "option_profit_target_125pct_reached_rate", "option_return_at_declared_exit_median", "option_profit_factor", "unique_underlying_count", "unique_theme_count", "largest_single_underlying_signal_share", "top_3_underlying_signal_share", "ex_post_only", "not_predictive", "not_a_composite_score", "not_a_trade_filter"]
    concentration_cols = ["cohort_type", "analysis_window_id", "cohort_id", "signal_count", "unique_underlying_count", "unique_theme_count", "largest_single_underlying_signal_share", "top_3_underlying_signal_share", "largest_single_theme_signal_share", "source_run_count", "rank_mix", "underlying_concentration_diagnostic", "theme_concentration_diagnostic", "source_run_concentration_diagnostic"]
    coverage_cols = ["analysis_window_id", "window_class", "start", "end", "signal_count"]
    write_csv(output_dir / "morita_bot_context_condition_summary.csv", condition_rows, condition_cols)
    write_csv(output_dir / "morita_bot_rank_context_summary.csv", rank_rows, rank_cols)
    write_csv(output_dir / "morita_bot_joint_context_summary.csv", joint_rows, joint_cols)
    write_csv(output_dir / "morita_bot_context_concentration_diagnostics.csv", concentration_rows, concentration_cols)
    write_csv(output_dir / "morita_bot_window_coverage.csv", coverage_rows, coverage_cols)


def write_markdown(output_dir: Path, receipt: dict[str, Any], notable_rows: list[dict[str, Any]], option_status: str) -> None:
    lines = [
        "# Phase 1.6C Morita Bot Mechanical-Flow Context Study",
        "",
        f"Primary status: `{receipt['run_status']}`",
        "",
        "This is a historical association review and not a selection decision.",
        "",
        "## Source Integrity",
        f"- Phase 1.6B integrity: `{receipt.get('phase1_6b_integrity_status', '')}`",
        f"- Morita source eligibility: `{receipt.get('morita_bot_source_artifact_eligibility', '')}`",
        f"- Real study run occurred: `{receipt.get('real_study_run_occurred', False)}`",
        "",
        "## Timing Alignment",
        f"- Alignment status: `{receipt.get('signal_context_alignment_status', '')}`",
        f"- Alignment ratio: `{receipt.get('signal_context_alignment_ratio', '')}`",
        "",
        "## Option Outcomes",
        f"- Option outcome availability: `{option_status}`",
        "",
        "## Boundaries",
        "- No external data was acquired.",
        "- No source artifact was mutated.",
        "- No Morita Bot generation or option-outcome command was invoked.",
        "- No CTA / Vol / ETF composite score was created.",
        "- No Dealer or 0DTE work was performed.",
        "- No ranking, selection, causal, predictive, execution, sizing, or exit actionization was created.",
    ]
    (output_dir / "phase1_6c_morita_bot_mechanical_flow_context_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    limitations = [
        "# Phase 1.6C Limitations",
        "",
        "- In-sample descriptive study only.",
        "- Multiple cohorts are reported without selection or ranking.",
        "- Sparse cells remain sparse and are not merged.",
        "- Phase 1.6B mechanical context is proxy context, not actual manager flow or market impact.",
        "- Source-vintage and strict point-in-time limits depend on the sealed Morita source artifact.",
        "- No actionization conclusion is permitted.",
    ]
    (output_dir / "phase1_6c_morita_bot_mechanical_flow_context_limitations.md").write_text("\n".join(limitations) + "\n", encoding="utf-8")


def build_study(spec_id: str, phase16b_output_dir: Path, morita_artifact: Path | None, output_dir: Path) -> dict[str, Any]:
    spec = load_spec(spec_id)
    reject_output_dir(output_dir)
    context, phase_receipt, phase_manifest = require_phase16b_context(phase16b_output_dir, spec)
    phase_status = "valid"
    if morita_artifact is None:
        inventory = inspect_morita_bot_source_artifacts()
        return write_blocked_outputs(output_dir, spec, "phase1_6c_morita_bot_mechanical_flow_context_source_validation_blocked", ["morita_bot_source_artifact_not_found"], phase_status, inventory)
    try:
        source = validate_morita_bot_run_artifact(morita_artifact)
    except SystemExit as exc:
        inventory = inspect_morita_bot_source_artifacts()
        return write_blocked_outputs(output_dir, spec, "phase1_6c_morita_bot_mechanical_flow_context_source_validation_blocked", [str(exc)], phase_status, inventory)
    panel, stats = build_panel(source["signals"], source["outcomes"], context)
    alignment_ratio = 1.0 - (stats["missing_context_rows"] / len(panel) if len(panel) else 1.0)
    if alignment_ratio < float(spec["minimum_signal_context_alignment_ratio"]):
        inventory = {"status": "morita_bot_source_artifact_eligible", "candidate_count": 1, "candidates": [{"artifact_path_relative": repo_relative(morita_artifact), "eligibility_status": "eligible"}]}
        return write_blocked_outputs(output_dir, spec, "phase1_6c_morita_bot_mechanical_flow_context_alignment_inadequate", ["morita_bot_context_alignment_inadequate"], phase_status, inventory)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = "phase1_6c_" + text_hash(file_sha256(phase16b_output_dir / PHASE16B_MANIFEST) + source["manifest_hash"] + spec_id)[:12]
    integrity_rows = [
        {
            "source_module": "phase1_6b_cross_module_downside",
            "artifact_path_relative": repo_relative(phase16b_output_dir),
            "run_id": phase_receipt.get("run_id", ""),
            "rule_version_or_model_spec_id": phase_receipt.get("study_spec_id", ""),
            "verification_status": "valid",
            "source_manifest_hash": file_sha256(phase16b_output_dir / PHASE16B_MANIFEST),
            "repository_commit_sha": phase_receipt.get("repository_commit_sha", ""),
            "module_or_builder_source_sha256": "",
            "research_only": True,
            "actionization_allowed": False,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
        },
        {
            "source_module": source["source_module"],
            "artifact_path_relative": repo_relative(morita_artifact),
            "run_id": source["receipt"].get("run_id", source["receipt"].get("source_run_id", "")),
            "rule_version_or_model_spec_id": source["rule_version_or_model_spec_id"],
            "verification_status": "valid",
            "source_manifest_hash": source["manifest_hash"],
            "repository_commit_sha": source["repository_commit_sha"],
            "module_or_builder_source_sha256": source["module_or_builder_source_sha256"],
            "research_only": True,
            "actionization_allowed": False,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
        },
    ]
    write_csv(output_dir / "morita_bot_source_artifact_integrity.csv", integrity_rows, list(integrity_rows[0].keys()))
    alignment_rows = build_alignment_rows(panel, stats, spec)
    write_csv(output_dir / "morita_bot_signal_context_alignment_audit.csv", alignment_rows, list(alignment_rows[0].keys()))
    write_csv(output_dir / "morita_bot_canonical_signal_outcome_panel.csv", panel.to_dict("records"), PANEL_COLUMNS)
    option_status = "available_from_source_artifact" if panel["option_return_at_declared_exit_if_available"].astype(str).str.strip().ne("").all() and len(panel) else "unavailable_from_source_artifact"
    write_json(output_dir / "morita_bot_outcome_definitions.json", {"required_core_outcomes": OUTCOME_REQUIRED, "optional_option_outcomes": OPTIONAL_OUTCOME, "option_outcome_analysis_status": option_status, **SAFETY_FLAGS})
    condition_rows, rank_rows, joint_rows, concentration_rows, coverage_rows = build_summaries(panel, spec)
    write_summary_tables(output_dir, condition_rows, rank_rows, joint_rows, concentration_rows, coverage_rows)
    status = "phase1_6c_morita_bot_mechanical_flow_context_completed" if option_status == "available_from_source_artifact" else "phase1_6c_morita_bot_mechanical_flow_context_option_outcomes_unavailable"
    receipt = base_receipt(status, spec_id, run_id)
    receipt.update(
        {
            "phase1_6b_integrity_status": phase_status,
            "morita_bot_source_artifact_eligibility": "eligible",
            "real_study_run_occurred": True,
            "source_signal_rows": int(len(source["signals"])),
            "canonical_panel_rows": int(len(panel)),
            "signal_context_alignment_status": "valid",
            "signal_context_alignment_ratio": alignment_ratio,
            "option_outcome_analysis_status": option_status,
        }
    )
    write_json(output_dir / "phase1_6c_morita_bot_mechanical_flow_context_receipt.json", receipt)
    write_markdown(output_dir, receipt, condition_rows[:3], option_status)
    build_content_manifest(output_dir, run_id)
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-morita-bot-source-artifacts", action="store_true")
    parser.add_argument("--validate-morita-bot-run-artifact")
    parser.add_argument("--verify-output-dir")
    parser.add_argument("--spec-id", default="phase1_6c_morita_bot_mechanical_flow_context_v1")
    parser.add_argument("--phase1-6b-output-dir", default="outputs/phase1_6b_cross_module_downside")
    parser.add_argument("--morita-bot-run-artifact")
    parser.add_argument("--output-dir", default="outputs/phase1_6c_morita_bot_mechanical_flow_context")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.inspect_morita_bot_source_artifacts:
        print(json_dumps(inspect_morita_bot_source_artifacts()))
        return 0
    if args.validate_morita_bot_run_artifact:
        result = validate_morita_bot_run_artifact(Path(args.validate_morita_bot_run_artifact))
        public = {k: v for k, v in result.items() if k not in {"signals", "outcomes", "receipt", "manifest", "schema"}}
        public.update(SAFETY_FLAGS)
        print(json_dumps(public))
        return 0
    if args.verify_output_dir:
        print(json_dumps(verify_output_manifest(Path(args.verify_output_dir))))
        return 0
    morita = Path(args.morita_bot_run_artifact) if args.morita_bot_run_artifact else None
    receipt = build_study(args.spec_id, Path(args.phase1_6b_output_dir), morita, Path(args.output_dir))
    print(json_dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
