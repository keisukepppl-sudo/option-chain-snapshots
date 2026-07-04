from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "morita_s_setup_episode_identity_v0_1"
BUNDLE = REPO_ROOT / "morita_s_setup_episode_identity_v0_1_bundle.md"
SPEC_PATH = REPO_ROOT / "config" / "morita_s_setup_episode_identity_v0_1" / "setup_episode_state_spec.json"
BASELINE_DIR = (
    REPO_ROOT
    / "market_bomb_history"
    / "morita_bot_historical_baseline_v1"
    / "historical_runs"
    / "morita_baseline_20260703T123912Z_4994e3744ffa"
)
FORMAL_PANEL = BASELINE_DIR / "morita_bot_baseline_panel.csv"
OLD_ROOT = Path(r"C:\Users\keisu\Documents\Codex\2026-06-14\files-mentioned-by-the-user-codex")
OLD_COOLDOWN_SCRIPT = OLD_ROOT / "work" / "option-chain-snapshots" / "analyze_options_momentum_grid_fast.py"
OLD_PULLBACK_ARTIFACT = OLD_ROOT / "outputs" / "s_plus_a_pullback" / "s_plus_a_pullback_trades.csv"

CLASSIFICATION_RULE_VERSION = "morita_s_setup_episode_identity_v0_1_no_rebreakout_without_source_base_evidence"
REQUIRED_OUTPUTS = [
    "source_verification.csv",
    "legacy_identity_evidence.csv",
    "legacy_identity_reusability_gate.csv",
    "legacy_identity_recovery_notes.md",
    "current_s_setup_episode_state.csv",
    "classification_coverage_summary.csv",
    "unresolved_state_inventory.csv",
    "setup_episode_receipt.json",
    "setup_episode_content_manifest.json",
    "setup_episode_summary.md",
]
FORBIDDEN_OUTPUT_TOKENS = ["profit_factor_result", "portfolio_dd_result", "equity_curve", "BUY_NOW", "SELL_NOW", "WEBULL_ORDER"]


def utc_now() -> str:
    return pd.Timestamp.now(tz="UTC").replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def baseline_receipt() -> dict[str, Any]:
    return json.loads((BASELINE_DIR / "baseline_receipt.json").read_text(encoding="utf-8"))


def baseline_input_root() -> Path:
    lineage = json.loads((BASELINE_DIR / "source_input_lineage.json").read_text(encoding="utf-8"))
    return REPO_ROOT / lineage["inputs"][0]["repository_relative_path_or_local_alias"]


def load_sessions() -> list[str]:
    schedule = pd.read_csv(baseline_input_root() / "sources" / "decision_schedule.csv", dtype=str).fillna("")
    dates = sorted(set(schedule["observation_date"]) | set(schedule["next_eligible_session"]))
    return [d for d in dates if d]


def session_gap(session_pos: dict[str, int], start: str, end: str) -> int | None:
    if start not in session_pos or end not in session_pos:
        return None
    return session_pos[end] - session_pos[start]


def norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(ts) else str(ts.date())


def load_formal_s() -> pd.DataFrame:
    panel = pd.read_csv(FORMAL_PANEL, dtype={"signal_id": str}).fillna("")
    s = panel[panel["signal_rank"].astype(str).eq("S")].copy()
    s["ticker"] = s["underlying_symbol"].astype(str).str.upper()
    s["signal_date"] = s["signal_decision_date"].map(norm_date)
    s["entry_date"] = s["entry_session"].map(norm_date)
    return s.sort_values(["ticker", "entry_date", "signal_id"]).reset_index(drop=True)


def source_verification_rows() -> list[dict[str, Any]]:
    receipt = baseline_receipt()
    paths = {
        "formal_baseline_panel": FORMAL_PANEL,
        "formal_baseline_receipt": BASELINE_DIR / "baseline_receipt.json",
        "formal_source_lineage": BASELINE_DIR / "source_input_lineage.json",
        "setup_episode_state_spec": SPEC_PATH,
        "old_cooldown_grid_script": OLD_COOLDOWN_SCRIPT,
        "old_pullback_artifact_with_original_breakout_date": OLD_PULLBACK_ARTIFACT,
        "current_reconciliation_audit": REPO_ROOT / "scripts" / "build_morita_s_reconciliation_audit_v1.py",
        "current_notification_quality_audit": REPO_ROOT / "scripts" / "build_morita_current_s_notification_quality_audit_v0_1.py",
    }
    rows = []
    for component, path in paths.items():
        rows.append(
            {
                "component": component,
                "path": repo_relative(path),
                "exists": path.exists(),
                "sha256": sha256_file(path) if path.exists() else "",
                "source_run_id": receipt.get("run_id", ""),
                "source_commit": receipt.get("repository_commit_sha", ""),
                "status": "verified" if path.exists() else "missing",
            }
        )
    return rows


def legacy_identity_evidence_rows() -> list[dict[str, Any]]:
    rows = []
    rows.append(
        {
            "evidence_id": "legacy_cooldown_indices",
            "recovery_outcome": "LEGACY_IDENTITY_RECOVERED_NON_EQUIVALENT",
            "source_path": str(OLD_COOLDOWN_SCRIPT),
            "git_commit_or_file_hash": sha256_file(OLD_COOLDOWN_SCRIPT) if OLD_COOLDOWN_SCRIPT.exists() else "",
            "function_or_query_name": "cooldown_indices",
            "input_fields": "mask,ticker_code,day_num",
            "decision_date_contract": "sorted date converted to day_num from options_momentum_feature_forward_dataset.csv",
            "exact_dedupe_key": "ticker_code plus day_num gap greater than COOLDOWN_DAYS=20",
            "source_proven_or_artifact_inferred": "source_proven",
            "answer": "Old local grid code implemented a 20 trading-day ticker cooldown, not a chart-base or valid rebreakout identity.",
            "reusable_for_current_classification": False,
            "not_reusable_reason": "No new-base/reset proof; old universe/features differ from formal current-S stream.",
        }
    )
    rows.append(
        {
            "evidence_id": "legacy_original_breakout_date_artifact",
            "recovery_outcome": "LEGACY_IDENTITY_ARTIFACT_ONLY",
            "source_path": str(OLD_PULLBACK_ARTIFACT),
            "git_commit_or_file_hash": sha256_file(OLD_PULLBACK_ARTIFACT) if OLD_PULLBACK_ARTIFACT.exists() else "",
            "function_or_query_name": "csv_column_original_breakout_date",
            "input_fields": "ticker,entry_type,original_breakout_date,entry_date",
            "decision_date_contract": "artifact column only; generating query not recovered",
            "exact_dedupe_key": "not source-proven",
            "source_proven_or_artifact_inferred": "artifact_inferred",
            "answer": "Old S/A pullback artifact contains original_breakout_date but the generating rule was not recovered.",
            "reusable_for_current_classification": False,
            "not_reusable_reason": "Artifact field alone does not prove setup identity generation logic.",
        }
    )
    rows.append(
        {
            "evidence_id": "current_formal_stream_no_base_id",
            "recovery_outcome": "LEGACY_IDENTITY_RECOVERED_NON_EQUIVALENT",
            "source_path": "scripts/build_morita_s_reconciliation_audit_v1.py",
            "git_commit_or_file_hash": "25f96fb",
            "function_or_query_name": "label_layers/infer_cooldown_status",
            "input_fields": "formal S signal_id,ticker,signal_decision_date,entry_session",
            "decision_date_contract": "formal baseline decision date to next eligible entry session",
            "exact_dedupe_key": "research overlay only; not persisted formal raw stream",
            "source_proven_or_artifact_inferred": "source_proven_current_audit",
            "answer": "Current formal S stream has no persisted base id or cooldown field.",
            "reusable_for_current_classification": False,
            "not_reusable_reason": "Prior audit layer is a research overlay, not native current setup identity.",
        }
    )
    rows.append(
        {
            "evidence_id": "ab_pullback_base_breakout_id",
            "recovery_outcome": "LEGACY_IDENTITY_RECOVERED_NON_EQUIVALENT",
            "source_path": "src/morita_notification_v2/ab_pullback_lifecycle.py",
            "git_commit_or_file_hash": "25f96fb",
            "function_or_query_name": "base_breakout_id",
            "input_fields": "source_signal_id,ticker,base_breakout_date",
            "decision_date_contract": "A/B pullback lifecycle, not formal S breakout stream",
            "exact_dedupe_key": "stable_id(source_signal_id,ticker,base_breakout_date)",
            "source_proven_or_artifact_inferred": "source_proven",
            "answer": "A/B lifecycle has base_breakout_id mechanics, but it is not current raw S setup identity.",
            "reusable_for_current_classification": False,
            "not_reusable_reason": "Route-specific A/B state, not historical formal S classification source.",
        }
    )
    return rows


def legacy_reusability_gate_rows(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = [
        ("generating_code_or_deterministic_query_recovered", False, "original_breakout_date generating rule was not recovered; cooldown code is non-base identity"),
        ("input_fields_exist_in_current_local_history", False, "current formal S lacks base_id/original_breakout_date/reset fields"),
        ("point_in_time_decision_contract_compatible", False, "cooldown is point-in-time but not equivalent to base/rebreakout identity"),
        ("deterministic_fixture_replay_possible", True, "cooldown and current state fallback can be fixture-tested"),
        ("not_tied_to_old_option_pnl", True, "cooldown source itself is signal selection; artifact is excluded from reuse"),
        ("current_raw_event_mapping_explicit", False, "old original_breakout_date artifact cannot be source-proven mapped to current raw S events"),
    ]
    return [
        {
            "gate_check": name,
            "passed": passed,
            "notes": notes,
            "overall_recovery_outcome": "LEGACY_IDENTITY_RECOVERED_NON_EQUIVALENT",
            "legacy_identity_reused_for_current_state": False,
        }
        for name, passed, notes in checks
    ]


def setup_episode_id(ticker: str, anchor_date: str) -> str:
    return "s_episode_" + stable_hash(ticker.upper(), anchor_date, CLASSIFICATION_RULE_VERSION)


def build_state_rows(s: pd.DataFrame, session_pos: dict[str, int]) -> list[dict[str, Any]]:
    receipt = baseline_receipt()
    rows = []
    for ticker, group in s.sort_values(["ticker", "entry_date", "signal_id"]).groupby("ticker"):
        sequence = 0
        active_episode_id = ""
        active_anchor = ""
        active_alert_sequence = 0
        prior_event_id = ""
        prior_episode_id = ""
        prior_entry = ""
        for _, row in group.iterrows():
            gap = session_gap(session_pos, prior_entry, row["entry_date"]) if prior_entry else None
            if not prior_event_id:
                sequence += 1
                active_anchor = row["entry_date"]
                active_episode_id = setup_episode_id(ticker, active_anchor)
                active_alert_sequence = 1
                classification = "INITIAL_OBSERVED_BREAKOUT"
                evidence = "INSUFFICIENT_EVIDENCE"
                confidence = "POINT_IN_TIME_CONFIRMED"
                reason = "first_observed_same_ticker_raw_s_in_available_formal_history_not_lifetime_initial"
                parent = ""
                first_alert = True
            elif gap is not None and gap <= 20:
                active_alert_sequence += 1
                classification = "EXTENDED_NO_NEW_BASE"
                evidence = "REPEATED_NOTIFICATION_WITHOUT_NEW_BASE_EVIDENCE"
                confidence = "POINT_IN_TIME_CONFIRMED"
                reason = "same_ticker_prior_raw_s_within_20_eligible_sessions_no_source_proven_new_base"
                parent = prior_episode_id
                first_alert = False
            else:
                sequence += 1
                active_anchor = row["entry_date"]
                active_episode_id = setup_episode_id(ticker, active_anchor)
                active_alert_sequence = 1
                classification = "UNRESOLVED"
                evidence = "INSUFFICIENT_EVIDENCE"
                confidence = "UNRESOLVED"
                reason = "prior_same_ticker_raw_s_exists_but_gap_alone_cannot_create_valid_rebreakout"
                parent = prior_episode_id
                first_alert = True
            rows.append(
                {
                    "raw_s_event_id": row["signal_id"],
                    "ticker": ticker,
                    "signal_decision_date": row["signal_date"],
                    "entry_session": row["entry_date"],
                    "setup_episode_id": active_episode_id,
                    "setup_episode_sequence_for_ticker": sequence,
                    "parent_setup_episode_id_if_any": parent,
                    "setup_episode_classification": classification,
                    "classification_evidence": evidence,
                    "classification_confidence": confidence,
                    "classification_reason_code": reason,
                    "classification_rule_version": CLASSIFICATION_RULE_VERSION,
                    "base_start_date_if_known": "",
                    "base_end_date_if_known": "",
                    "pivot_or_breakout_date_if_known": "",
                    "base_high_if_known": "",
                    "base_low_if_known": "",
                    "base_duration_sessions_if_known": "",
                    "native_or_recovered_setup_id_if_available": "",
                    "prior_same_ticker_setup_episode_id_if_any": prior_episode_id,
                    "prior_same_ticker_raw_s_event_id_if_any": prior_event_id,
                    "eligible_sessions_since_prior_raw_s": "" if gap is None else gap,
                    "is_first_alert_in_episode": first_alert,
                    "alert_sequence_in_episode": active_alert_sequence,
                    "first_observed_in_available_history": not bool(prior_event_id),
                    "data_as_of_date": row["signal_date"],
                    "source_code_commit": receipt.get("repository_commit_sha", ""),
                    "source_config_identity": row.get("source_rule_config_hash", ""),
                    "source_coverage_status": "formal_s_verified_no_native_base_identity",
                }
            )
            prior_event_id = row["signal_id"]
            prior_episode_id = active_episode_id
            prior_entry = row["entry_date"]
    return rows


def classification_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(rows)
    out = []
    for klass in ["INITIAL_OBSERVED_BREAKOUT", "VALID_REBREAKOUT", "EXTENDED_NO_NEW_BASE", "UNRESOLVED", "OUTSIDE_SOURCE_COVERAGE"]:
        sub = df[df["setup_episode_classification"] == klass]
        out.append(
            {
                "setup_episode_classification": klass,
                "raw_s_event_count": int(len(sub)),
                "unique_tickers": int(sub["ticker"].nunique()) if len(sub) else 0,
                "unique_setup_episode_ids": int(sub["setup_episode_id"].nunique()) if len(sub) else 0,
                "share_of_raw_s": len(sub) / len(df) if len(df) else "",
            }
        )
    return out


def unresolved_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(rows)
    unresolved = df[df["setup_episode_classification"] == "UNRESOLVED"]
    if unresolved.empty:
        return []
    grouped = unresolved.groupby("classification_reason_code")
    return [
        {
            "reason_code": reason,
            "raw_s_event_count": int(len(group)),
            "unique_tickers": int(group["ticker"].nunique()),
            "missing_field_or_rule": "source_proven_new_base_or_reset_identity",
            "required_next_step": "approve separate point-in-time base-definition research or recover deterministic legacy generator",
        }
        for reason, group in grouped
    ]


def write_notes(evidence: list[dict[str, Any]], gate: list[dict[str, Any]]) -> None:
    lines = [
        "# Legacy Identity Recovery Notes",
        "",
        "Outcome: `LEGACY_IDENTITY_RECOVERED_NON_EQUIVALENT`.",
        "",
        "Recovered evidence:",
        "",
        "- Old local grid code has `cooldown_indices(mask, ticker_code, day_num)`, a source-proven 20 trading-day ticker cooldown.",
        "- Old S/A pullback artifact has `original_breakout_date`, but the generating rule was not recovered.",
        "- Current formal S stream has no persisted base id, original breakout date, reset/rebase flag, or cooldown field.",
        "- A/B lifecycle has `base_breakout_id`, but that route-specific state is not a formal S setup identity source.",
        "",
        "Recovery questions:",
        "",
        "A. Durable old original_breakout_date/setup identity: artifact-only, not source-proven.",
        "B. Exact generator: not recovered for `original_breakout_date`; cooldown generator recovered but non-equivalent.",
        "C. Repeated high updates: old cooldown code can dedupe by ticker/day gap, but not by base identity.",
        "D. Valid new base/rebreakout: not recovered as a source-proven point-in-time rule.",
        "E. Source-proven: cooldown mechanics and A/B base id function; artifact-inferred: original_breakout_date meaning.",
        "",
        "Reusability gate failed for current S classification. The current state layer therefore refuses to emit `VALID_REBREAKOUT`.",
    ]
    (OUT / "legacy_identity_recovery_notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def write_summary_bundle(receipt: dict[str, Any], summary: list[dict[str, Any]], gate: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> None:
    lines = [
        "# Morita S Setup-Episode Identity v0.1",
        "",
        "Research/state-architecture only. No return, fixed-IV, MAE, DD, portfolio, scanner, rank, notification, order, or sizing change.",
        "",
        "## Receipt",
        "",
        "```json",
        json.dumps(receipt, indent=2, sort_keys=True),
        "```",
        "",
        "## Classification Coverage",
        "",
        md_table(summary, ["setup_episode_classification", "raw_s_event_count", "unique_tickers", "unique_setup_episode_ids", "share_of_raw_s"]),
        "",
        "## Legacy Reusability Gate",
        "",
        md_table(gate, ["gate_check", "passed", "overall_recovery_outcome", "legacy_identity_reused_for_current_state", "notes"]),
        "",
        "## Unresolved Inventory",
        "",
        md_table(unresolved, ["reason_code", "raw_s_event_count", "unique_tickers", "missing_field_or_rule", "required_next_step"]),
        "",
        "## Guard",
        "",
        "Future S reports must not call the full raw current-S event stream initial-breakout performance, S strategy PF, or S strategy DD unless they stratify by setup_episode_classification and show unresolved share.",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "setup_episode_summary.md").write_text(text, encoding="utf-8")
    BUNDLE.write_text(text, encoding="utf-8")


def build_manifest() -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUTS:
        if name == "setup_episode_content_manifest.json":
            continue
        path = OUT / name
        if path.exists():
            files.append({"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {
        "manifest_version": "morita_s_setup_episode_identity_v0_1",
        "created_at_utc": utc_now(),
        "required_files": REQUIRED_OUTPUTS,
        "files": files,
        "content_set_hash": hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    write_json(OUT / "setup_episode_content_manifest.json", manifest)
    return manifest


def verify_manifest() -> dict[str, Any]:
    missing = [name for name in REQUIRED_OUTPUTS if not (OUT / name).exists()]
    actual = sorted(path.name for path in OUT.iterdir() if path.is_file()) if OUT.exists() else []
    extra = [name for name in actual if name not in REQUIRED_OUTPUTS]
    changed = []
    manifest_path = OUT / "setup_episode_content_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in manifest.get("files", []):
            path = OUT / row["path"]
            if not path.exists() or sha256_file(path) != row["sha256"]:
                changed.append(row["path"])
    return {"verified": not missing and not extra and not changed, "missing": missing, "extra": extra, "changed": changed}


def assert_no_forbidden_outputs() -> None:
    for path in OUT.glob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for token in FORBIDDEN_OUTPUT_TOKENS:
                if token.lower() in text:
                    raise AssertionError(f"forbidden_output_token:{token}:{path.name}")


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = source_verification_rows()
    missing = [row["component"] for row in sources if not row["exists"] and row["component"] not in {"old_pullback_artifact_with_original_breakout_date"}]
    if missing:
        write_csv(OUT / "source_verification.csv", sources)
        raise FileNotFoundError(f"missing_required_sources:{missing}")
    sessions = load_sessions()
    session_pos = {date: idx for idx, date in enumerate(sessions)}
    s = load_formal_s()
    evidence = legacy_identity_evidence_rows()
    gate = legacy_reusability_gate_rows(evidence)
    state_rows = build_state_rows(s, session_pos)
    summary = classification_summary(state_rows)
    unresolved = unresolved_inventory(state_rows)
    receipt = {
        "status": "completed",
        "created_at_utc": utc_now(),
        "research_and_state_architecture_only": True,
        "raw_s_history_immutable": True,
        "no_new_data_downloaded": True,
        "no_web_or_provider_api": True,
        "no_broker_or_webull_access": True,
        "no_live_notification_or_order_change": True,
        "no_future_data_in_classification": True,
        "no_parameter_sweep": True,
        "no_pf_targeting": True,
        "no_portfolio_or_route_performance_replay": True,
        "source_run_id": baseline_receipt().get("run_id", ""),
        "source_commit": baseline_receipt().get("repository_commit_sha", ""),
        "source_date_min": str(s["signal_date"].min()),
        "source_date_max": str(s["signal_date"].max()),
        "raw_s_source_count": int(len(s)),
        "state_row_count": int(len(state_rows)),
        "row_count_reconciled": int(len(s)) == int(len(state_rows)) == 328,
        "legacy_recovery_outcome": "LEGACY_IDENTITY_RECOVERED_NON_EQUIVALENT",
        "legacy_identity_reused_for_current_state": False,
        "valid_rebreakout_count": int(sum(row["setup_episode_classification"] == "VALID_REBREAKOUT" for row in state_rows)),
    }
    write_csv(OUT / "source_verification.csv", sources)
    write_csv(OUT / "legacy_identity_evidence.csv", evidence)
    write_csv(OUT / "legacy_identity_reusability_gate.csv", gate)
    write_notes(evidence, gate)
    write_csv(OUT / "current_s_setup_episode_state.csv", state_rows)
    write_csv(OUT / "classification_coverage_summary.csv", summary)
    write_csv(OUT / "unresolved_state_inventory.csv", unresolved)
    write_json(OUT / "setup_episode_receipt.json", receipt)
    write_summary_bundle(receipt, summary, gate, unresolved)
    build_manifest()
    assert_no_forbidden_outputs()
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.run and not args.verify:
        parser.error("one of --run or --verify is required")
    if args.run:
        print(json.dumps(run(), indent=2, sort_keys=True))
    if args.verify:
        result = verify_manifest()
        print(result)
        return 0 if result["verified"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
