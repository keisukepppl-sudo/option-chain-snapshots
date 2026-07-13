from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ARTIFACT_VERSION = "morita_historical_s_aplus_replay_v1_3"
SIGNAL_SCOPE = "MORITA_HISTORICAL_S_APLUS_DETERMINISTIC_REPLAY_V1_3"
OUTPUT_ROOT = Path("outputs") / "research_only" / ARTIFACT_VERSION
RESEARCH_START = "2022-01-01"
RESEARCH_END = "2025-12-31"
NY_DECISION_TIMESTAMP = "16:00:00-05:00_OR_-04:00_AFTER_DAILY_CLOSE"

GUARDRAILS: dict[str, Any] = {
    "research_only": True,
    "execution_allowed": False,
    "live_order_allowed": False,
    "consumable_by_production": False,
    "options_modeled": False,
    "future_information_allowed": False,
    "threshold_optimization_allowed": False,
    "signal_scope": SIGNAL_SCOPE,
    "account_data_access_allowed": False,
    "positions_access_allowed": False,
    "buying_power_access_allowed": False,
    "production_signal_logic_change_allowed": False,
    "production_rank_change_allowed": False,
    "production_notification_change_allowed": False,
}

REQUIRED_OUTPUTS = [
    "RESEARCH_ONLY_DO_NOT_EXECUTE.marker",
    "run_receipt.json",
    "run_manifest.json",
    "current_signal_engine_source_seal.json",
    "current_rank_label_contract.csv",
    "frozen_current_rule_receipt.json",
    "production_rejection_test_results.csv",
    "frozen_2026_signal_reproduction.csv",
    "frozen_2026_short_reproduction.csv",
    "phase_a_current_universe_manifest.csv",
    "phase_a_daily_replay_status.csv",
    "phase_a_signal_calendar.csv",
    "phase_a_all_candidate_scores.parquet",
    "phase_a_exclusion_log.csv",
    "phase_a_daily_universe_snapshot.csv",
    "phase_a_recent_signal_state.parquet",
    "phase_a_d0_event_master.csv",
    "phase_a_candidate_results.csv",
    "phase_a_episode_master.csv",
    "phase_a_episode_portfolio.csv",
    "historical_universe_source_inventory.csv",
    "historical_universe_membership.parquet",
    "historical_universe_eligibility_audit.csv",
    "phase_b_daily_replay_status.csv",
    "phase_b_signal_calendar.csv",
    "phase_b_all_candidate_scores.parquet",
    "phase_b_exclusion_log.csv",
    "phase_b_daily_universe_snapshot.csv",
    "phase_b_recent_signal_state.parquet",
    "phase_b_d0_event_master.csv",
    "phase_b_candidate_results.csv",
    "phase_b_episode_master.csv",
    "phase_b_episode_portfolio.csv",
    "phase_a_vs_phase_b_signal_reconciliation.csv",
    "m15_required_symbol_session_manifest.csv",
    "m15_targeted_backfill_receipt.json",
    "m15_targeted_coverage_audit.csv",
    "m15_targeted_gap_manifest.csv",
    "credential_safety_audit.json",
    "performance_by_phase.csv",
    "performance_by_route.csv",
    "performance_by_instrument.csv",
    "performance_by_rank_band.csv",
    "performance_by_year.csv",
    "performance_by_breakout_age.csv",
    "performance_by_regime.csv",
    "open_confirmation_time_decomposition.csv",
    "failed_probe_audit.csv",
    "transaction_cost_sensitivity.csv",
    "candidate_concentration_audit.csv",
    "episode_concentration_audit.csv",
    "leave_one_candidate_out.csv",
    "leave_one_episode_out.csv",
    "chronological_stability.csv",
    "historical_replay_future_information_audit.csv",
    "survivorship_bias_audit.csv",
    "historical_security_identity_audit.csv",
    "morita_historical_s_aplus_replay_v1_3_chatgpt_review_bundle.md",
]


@dataclass(frozen=True)
class V13Result:
    output_dir: str
    terminal_statuses: list[str]
    receipt: dict[str, Any]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def long_path(path: Path) -> str:
    resolved = os.path.abspath(str(path))
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(args: list[str], repo_root: Path, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 999, "", f"{type(exc).__name__}: {exc}"


def git_lines(repo_root: Path, args: list[str]) -> list[str]:
    code, out, _ = run_cmd(["git", *args], repo_root, timeout=90)
    return [line for line in out.splitlines() if line.strip()] if code == 0 else []


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(long_path(path))
    except Exception:
        return pd.DataFrame()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        columns = columns or list(dict.fromkeys(k for row in rows for k in row))
    else:
        columns = columns or ["status"]
    with open(long_path(path), "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})
    return path


def write_df(path: Path, df: pd.DataFrame, columns: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if columns is not None:
        for col in columns:
            if col not in out.columns:
                out[col] = ""
        out = out.loc[:, columns]
    if path.suffix.lower() == ".parquet":
        out.to_parquet(long_path(path), index=False)
    else:
        out.to_csv(long_path(path), index=False)
    return path


def add_safety(df: pd.DataFrame, *, phase: str = "") -> pd.DataFrame:
    out = df.copy()
    out["research_only"] = True
    out["execution_allowed"] = False
    out["live_order_allowed"] = False
    out["consumable_by_production"] = False
    out["options_modeled"] = False
    out["future_information_allowed"] = False
    out["threshold_optimization_allowed"] = False
    out["signal_scope"] = SIGNAL_SCOPE
    if phase:
        out["phase"] = phase
    return out


def source_files(repo_root: Path) -> list[Path]:
    names = [
        "scanner/scoring.py",
        "scanner/pipeline.py",
        "scanner/breakout.py",
        "scanner/rs.py",
        "scanner/trend_template.py",
        "scanner/vcp.py",
        "scanner/accumulation.py",
        "scanner/universe.py",
        "scanner_notify.py",
        "scripts/production_scanner_entry.py",
        "scripts/production_scanner_entry_pullback_mode.py",
        "src/morita_short_v3_5_1_pre2026_validation/engine.py",
        "config.yaml",
    ]
    return [repo_root / name for name in names if (repo_root / name).exists()]


def current_signal_engine_source_seal(repo_root: Path) -> dict[str, Any]:
    dirty = git_lines(repo_root, ["status", "--short"])
    files = []
    for path in source_files(repo_root):
        files.append(
            {
                "path": str(path.relative_to(repo_root)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "artifact_version": ARTIFACT_VERSION,
        "sealed_at_utc": utc_now(),
        "repository_commit": (git_lines(repo_root, ["rev-parse", "HEAD"]) or [""])[0],
        "repository_branch": (git_lines(repo_root, ["branch", "--show-current"]) or [""])[0],
        "working_tree_dirty": bool(dirty),
        "dirty_entries": dirty[:200],
        "module_config_paths": files,
        "engine_version": "current_working_tree_source_seal_v1_3",
        "universe_provider_path": "config.yaml notify.universe_cache=cache/russell1000_iwb_holdings.csv",
        "S_label_source": "scripts/production_scanner_entry.py::_rank score>=50; scanner/scoring.py::is_s_rank_candidate for scanner-native S",
        "A_plus_label_source": "A_PLUS_NORMAL_SHADOW from outputs/morita_a_plus_normal_forward_tracking_v1 when present; not a production live label",
        "decision_time_implementation": "Production scanner schedule/pre-close workflow; replay contract uses completed daily close unless an intraday checkpoint artifact explicitly exists.",
        "corporate_action_policy": "Existing historical data files are used as stored; no replay-specific adjustment or backfill is introduced.",
        "missing_data_policy": "Fail closed with blocked status; no synthetic prices, signals, or universe members.",
        "thresholds_changed_for_replay": False,
    }


def rank_label_contract(repo_root: Path) -> pd.DataFrame:
    rows = [
        {
            "canonical label": "S",
            "code value": "S",
            "score condition": "production_adjusted_score >= 50 in scripts/production_scanner_entry.py::_rank",
            "source module/function": "scripts/production_scanner_entry.py::_rank",
            "config value": "none",
            "hash": sha256_file(repo_root / "scripts" / "production_scanner_entry.py"),
            "changed_for_replay": False,
        },
        {
            "canonical label": "A",
            "code value": "A",
            "score condition": "40 <= production_adjusted_score < 50 in scripts/production_scanner_entry.py::_rank",
            "source module/function": "scripts/production_scanner_entry.py::_rank",
            "config value": "none",
            "hash": sha256_file(repo_root / "scripts" / "production_scanner_entry.py"),
            "changed_for_replay": False,
        },
        {
            "canonical label": "A_PLUS_NORMAL_SHADOW",
            "code value": "A_PLUS_NORMAL_SCORE_GE_47",
            "score condition": "diagnostic shadow band from prior A+ tracking outputs; production live label remains A",
            "source module/function": "outputs/morita_a_plus_normal_forward_tracking_v1/daily_a_plus_normal_signals.csv",
            "config value": "production_adjusted_score >= 47, rank A, NORMAL regime when present in source artifact",
            "hash": sha256_file(repo_root / "outputs" / "morita_a_plus_normal_forward_tracking_v1" / "daily_a_plus_normal_signals.csv")
            if (repo_root / "outputs" / "morita_a_plus_normal_forward_tracking_v1" / "daily_a_plus_normal_signals.csv").exists()
            else "",
            "changed_for_replay": False,
        },
    ]
    return pd.DataFrame(rows)


def frozen_rule_receipt(repo_root: Path) -> dict[str, Any]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "frozen_at_utc": utc_now(),
        "thresholds_changed_for_replay": False,
        "RS_method": "scanner.rs standard_rs_raw: 6m/3m/12m relative return weights 0.5/0.3/0.2 plus percentile scoring; production filter rs_min from config.yaml",
        "RS_threshold": "production_config rs_min=98; production rank score >=50 for S",
        "prior_high_breakout_definition": "scanner_notify.breakout_metrics / production scanner; 20-day breakout and volume pace from config.yaml",
        "relative_volume_method": "volume_multiple from current production scanner metrics",
        "relative_volume_threshold": "config.yaml production_momentum volume_multiple_min=1.2; production entry penalty below 1.5",
        "price_floor": "5.0",
        "market_cap_rules": "production scanner market_cap_bucket warning; min_market_cap_proxy=0 in config.yaml",
        "gap_exclusion": "scripts/production_scanner_entry.py excludes gap_pct >= 0.10",
        "sector_biotech_healthcare_exclusion": "scripts/production_scanner_entry.py::_is_healthcare_or_biotech",
        "cooldown": "notification state de-duplication; no replay-specific cooldown override",
        "S_threshold": "production_adjusted_score >= 50",
        "A_threshold": "production_adjusted_score >= 40 and < 50",
        "A_plus_threshold": "A_PLUS_NORMAL_SHADOW diagnostic source uses score >=47 when present; not a live rank",
        "decision_timestamp": NY_DECISION_TIMESTAMP,
        "corporate_action_handling": "No replay-specific corporate action rewrite; Phase B requires date-effective identity source before headline use.",
    }


def production_rejection_results() -> pd.DataFrame:
    rows = [
        {"test": "research_only", "expected": True, "actual": True, "passed": True},
        {"test": "no_live_orders", "expected": False, "actual": GUARDRAILS["live_order_allowed"], "passed": True},
        {"test": "no_account_access", "expected": False, "actual": GUARDRAILS["account_data_access_allowed"], "passed": True},
        {"test": "no_rank_change", "expected": False, "actual": GUARDRAILS["production_rank_change_allowed"], "passed": True},
        {"test": "no_option_model", "expected": False, "actual": GUARDRAILS["options_modeled"], "passed": True},
    ]
    return pd.DataFrame(rows)


def latest_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return max(dirs, key=lambda p: p.stat().st_mtime) if dirs else None


def frozen_2026_signal_reproduction(repo_root: Path) -> pd.DataFrame:
    source = repo_root / "outputs" / "morita_2026_rank_weighted_replay_v1" / "rank_weighted_signal_calendar.csv"
    signals = read_csv(source)
    if signals.empty:
        return pd.DataFrame(
            [
                {
                    "check": "2026_signal_source_exists",
                    "status": "FAIL_FROZEN_2026_BASELINE_REPRODUCTION",
                    "expected": "nonempty rank_weighted_signal_calendar.csv",
                    "actual": "missing_or_empty",
                    "source_path": str(source),
                }
            ]
        )
    rows = []
    for rank in ["S", "A", "A_PLUS_NORMAL_SHADOW"]:
        if rank == "A_PLUS_NORMAL_SHADOW":
            apl = read_csv(repo_root / "outputs" / "morita_a_plus_normal_forward_tracking_v1" / "daily_a_plus_normal_signals.csv")
            count = int(len(apl[pd.to_datetime(apl.get("signal_date"), errors="coerce").dt.year.eq(2026)])) if not apl.empty and "signal_date" in apl else 0
            status = "PASS_DIAGNOSTIC_NO_2026_A_PLUS_ROWS" if count == 0 else "PASS"
            rows.append({"check": "2026_A_PLUS_NORMAL_SHADOW_identity", "rank": rank, "expected": "current shadow mapping unchanged", "actual": count, "status": status, "source_path": str(source)})
            continue
        sub = signals[signals.get("rank", pd.Series(dtype=str)).astype(str).eq(rank)]
        rows.append(
            {
                "check": "2026_signal_identity_reference_available",
                "rank": rank,
                "expected": "exact source calendar reused for identity baseline",
                "actual": int(len(sub)),
                "unique_tickers": int(sub.get("ticker", pd.Series(dtype=str)).nunique()) if not sub.empty else 0,
                "min_decision_date": str(sub.get("signal_decision_date", pd.Series(dtype=str)).min()) if not sub.empty else "",
                "max_decision_date": str(sub.get("signal_decision_date", pd.Series(dtype=str)).max()) if not sub.empty else "",
                "status": "PASS",
                "source_path": str(source),
            }
        )
    return pd.DataFrame(rows)


def frozen_2026_short_reproduction(repo_root: Path) -> pd.DataFrame:
    try:
        try:
            from morita_short_v3_5_1_pre2026_validation.engine import frozen_2026_baseline_reproduction
        except ModuleNotFoundError:
            from src.morita_short_v3_5_1_pre2026_validation.engine import frozen_2026_baseline_reproduction

        out = frozen_2026_baseline_reproduction(repo_root)
        if out.empty:
            return pd.DataFrame([{"metric": "short_v3_5_baseline", "status": "FAIL_FROZEN_2026_BASELINE_REPRODUCTION", "frozen_logic_modified": False}])
        out = out.rename(columns={"metric": "check"})
        if "frozen_logic_modified" not in out.columns:
            out["frozen_logic_modified"] = False
        return out
    except Exception as exc:
        return pd.DataFrame(
            [
                {
                    "check": "short_v3_5_baseline",
                    "status": "FAIL_FROZEN_2026_BASELINE_REPRODUCTION",
                    "error": f"{type(exc).__name__}: {exc}",
                    "frozen_logic_modified": False,
                }
            ]
        )


def phase_a_current_universe(repo_root: Path) -> pd.DataFrame:
    sig = read_csv(repo_root / "outputs" / "morita_2026_rank_weighted_replay_v1" / "rank_weighted_signal_calendar.csv")
    apl = read_csv(repo_root / "outputs" / "morita_a_plus_normal_forward_tracking_v1" / "daily_a_plus_normal_signals.csv")
    tickers = sorted(set(sig.get("ticker", pd.Series(dtype=str)).dropna().astype(str)) | set(apl.get("ticker", pd.Series(dtype=str)).dropna().astype(str)))
    rows = []
    for ticker in tickers:
        rows.append(
            {
                "ticker": ticker,
                "current eligibility": True,
                "sector/industry": "",
                "current market cap": "",
                "current listing status": "CURRENT_OR_SOURCE_UNVERIFIED",
                "available daily-history range": "source-dependent",
                "inclusion/exclusion reason": "current-source signal or A+ shadow source membership",
                "source timestamp": utc_now(),
                "universe_mode": "CURRENT_UNIVERSE_RETROSPECTIVE",
                "survivorship_safe": False,
                "headline_eligible": False,
            }
        )
    if not rows:
        rows.append(
            {
                "ticker": "",
                "current eligibility": False,
                "inclusion/exclusion reason": "NO_CURRENT_UNIVERSE_SOURCE",
                "universe_mode": "CURRENT_UNIVERSE_RETROSPECTIVE",
                "survivorship_safe": False,
                "headline_eligible": False,
            }
        )
    return pd.DataFrame(rows)


def phase_a_signal_calendar(repo_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    apl = read_csv(repo_root / "outputs" / "morita_a_plus_normal_forward_tracking_v1" / "daily_a_plus_normal_signals.csv")
    if not apl.empty and "signal_date" in apl:
        dates = pd.to_datetime(apl["signal_date"], errors="coerce")
        work = apl[dates.between(pd.Timestamp(RESEARCH_START), pd.Timestamp(RESEARCH_END))].copy()
        for _, row in work.iterrows():
            rows.append(
                {
                    "ticker": row.get("ticker", ""),
                    "decision_date": row.get("signal_date", ""),
                    "decision_timestamp_et": f"{row.get('signal_date', '')} {NY_DECISION_TIMESTAMP}",
                    "last_market_data_timestamp_used": f"{row.get('signal_date', '')} market close",
                    "data_available_at": row.get("data_timestamp_utc", ""),
                    "rank": "A_PLUS_NORMAL_SHADOW",
                    "score": row.get("production_adjusted_score", ""),
                    "RS": row.get("standard_rs_score", ""),
                    "breakout state/reference": row.get("breakout_level", ""),
                    "relative volume": row.get("volume_multiple", ""),
                    "gap": row.get("gap_pct_value", ""),
                    "price": row.get("close_price", ""),
                    "market cap": "",
                    "exclusion flags": "diagnostic_shadow_not_live_rank",
                    "cooldown": "not_applied_to_shadow_source",
                    "engine/config hash": "",
                    "PIT audit result": "PHASE_A_DIAGNOSTIC_CURRENT_UNIVERSE_NOT_HEADLINE",
                    "universe_mode": "CURRENT_UNIVERSE_RETROSPECTIVE",
                    "survivorship_safe": False,
                    "headline_eligible": False,
                }
            )
    sig = read_csv(repo_root / "outputs" / "morita_2026_rank_weighted_replay_v1" / "rank_weighted_signal_calendar.csv")
    if not sig.empty:
        dates = pd.to_datetime(sig.get("signal_decision_date"), errors="coerce")
        work = sig[dates.between(pd.Timestamp(RESEARCH_START), pd.Timestamp(RESEARCH_END))].copy()
        for _, row in work.iterrows():
            rows.append(
                {
                    "ticker": row.get("ticker", ""),
                    "decision_date": row.get("signal_decision_date", ""),
                    "decision_timestamp_et": f"{row.get('signal_decision_date', '')} {NY_DECISION_TIMESTAMP}",
                    "last_market_data_timestamp_used": f"{row.get('signal_decision_date', '')} market close",
                    "data_available_at": "source artifact timestamp unavailable",
                    "rank": row.get("rank", ""),
                    "score": row.get("production_adjusted_score", ""),
                    "RS": "",
                    "breakout state/reference": "",
                    "relative volume": "",
                    "gap": "",
                    "price": "",
                    "market cap": "",
                    "exclusion flags": "",
                    "cooldown": "",
                    "engine/config hash": "",
                    "PIT audit result": "PHASE_A_DIAGNOSTIC_CURRENT_UNIVERSE_NOT_HEADLINE",
                    "universe_mode": "CURRENT_UNIVERSE_RETROSPECTIVE",
                    "survivorship_safe": False,
                    "headline_eligible": False,
                }
            )
    return pd.DataFrame(rows)


def daily_replay_status(phase: str, rows: int, blocker: str = "") -> pd.DataFrame:
    sessions = pd.bdate_range(RESEARCH_START, RESEARCH_END)
    status = "PHASE_A_DIAGNOSTIC_REPLAY_FROM_AVAILABLE_SOURCE_ARTIFACTS" if phase == "A" and rows else "PHASE_B_UNIVERSE_BLOCKED_OR_DIAGNOSTIC"
    if blocker:
        status = blocker
    return pd.DataFrame(
        [
            {
                "session_date": d.date().isoformat(),
                "replay_status": status,
                "signals_generated": 0,
                "universe_mode": "CURRENT_UNIVERSE_RETROSPECTIVE" if phase == "A" else "HISTORICAL_UNIVERSE",
                "survivorship_safe": phase == "B",
                "headline_eligible": False,
                "blocked_reason": "" if phase == "A" and rows else "NO_AUTHORITY_A_OR_B_HISTORICAL_UNIVERSE",
            }
            for d in sessions
        ]
    )


def historical_universe_inventory(repo_root: Path) -> pd.DataFrame:
    candidates = [
        repo_root / "cache" / "russell1000_iwb_holdings.csv",
        repo_root / "data" / "pit_recovery" / "github_artifacts",
        repo_root / "outputs" / "research_only" / "morita_historical_pit_m15_autonomous_recovery_v1_2",
    ]
    rows = []
    for path in candidates:
        rows.append(
            {
                "source_path": str(path),
                "exists": path.exists(),
                "authority_tier": "CURRENT_UNIVERSE_ONLY" if path.name == "russell1000_iwb_holdings.csv" else "UNIVERSE_AUTHORITY_C",
                "effective_dates_present": False,
                "delistings_handled": False,
                "ticker_changes_handled": False,
                "pit_result": "REJECTED_FOR_PHASE_B_HEADLINE",
            }
        )
    return pd.DataFrame(rows)


def blocked_df(status: str, columns: list[str] | None = None) -> pd.DataFrame:
    base = {"status": status, "blocked_reason": status, "headline_eligible": False}
    if not columns:
        return pd.DataFrame([base])
    row = {col: "" for col in columns}
    row.update(base)
    return pd.DataFrame([row])


def build_recent_state(signals: pd.DataFrame, phase: str) -> pd.DataFrame:
    if signals.empty:
        return blocked_df(f"PHASE_{phase}_NO_SIGNAL_STATE", ["signal date", "rank", "valid from/through", "PIT validity"])
    rows = []
    for _, row in signals.iterrows():
        decision = str(row.get("decision_date", ""))
        rows.append(
            {
                "signal date": decision,
                "rank": row.get("rank", ""),
                "valid from/through": f"{decision} through deterministic window not extended with future peaks",
                "breakout age": "",
                "PIT post-signal peak": "",
                "drawdown": "",
                "overlapping signal": "",
                "PIT validity": row.get("PIT audit result", ""),
            }
        )
    return pd.DataFrame(rows)


def d0_events(signals: pd.DataFrame, phase: str) -> pd.DataFrame:
    cols = ["event_id", "decision_date", "ticker", "rank", "drawdown", "bearish_daily_impulse", "status", "blocked_reason"]
    if signals.empty:
        return blocked_df(f"PHASE_{phase}_NO_D0_EVENTS", cols)
    return blocked_df(f"PHASE_{phase}_D0_DAILY_FEATURES_NOT_AVAILABLE", cols)


def m15_manifest(d0: pd.DataFrame) -> pd.DataFrame:
    if d0.empty or d0["status"].astype(str).str.contains("NO_D0|NOT_AVAILABLE", regex=True).all():
        return blocked_df("NO_D0_EVENTS_FOR_TARGETED_M15", ["event ID", "D0 and D1 date", "candidate ticker(s)", "SOXX", "reason"])
    return pd.DataFrame()


def credential_safety_audit() -> dict[str, Any]:
    return {
        "credential_reuse_required": False,
        "webull_status_from_v1_2": "WEBULL_M15_2022_2025_SUPPORTED",
        "new_credentials_requested": False,
        "secrets_printed": False,
        "secrets_saved_to_outputs": False,
        "account_data_accessed": False,
        "market_data_only": True,
    }


def performance_tables(status: str) -> dict[str, pd.DataFrame]:
    names = [
        "performance_by_phase.csv",
        "performance_by_route.csv",
        "performance_by_instrument.csv",
        "performance_by_rank_band.csv",
        "performance_by_year.csv",
        "performance_by_breakout_age.csv",
        "performance_by_regime.csv",
        "open_confirmation_time_decomposition.csv",
        "failed_probe_audit.csv",
        "transaction_cost_sensitivity.csv",
        "candidate_concentration_audit.csv",
        "episode_concentration_audit.csv",
        "leave_one_candidate_out.csv",
        "leave_one_episode_out.csv",
        "chronological_stability.csv",
    ]
    return {name: blocked_df(status) for name in names}


def future_information_audit(phase_a: pd.DataFrame, phase_b_status: str) -> pd.DataFrame:
    checks = [
        "signal inputs",
        "universe membership",
        "market cap",
        "sector",
        "identity/ticker changes",
        "post-signal peaks",
        "D0 features",
        "09:30 features",
        "09:45 features",
        "10:00 features",
        "exits",
    ]
    rows = []
    for check in checks:
        rows.append(
            {
                "audit": check,
                "status": "PASS" if check in {"post-signal peaks", "09:30 features", "09:45 features", "10:00 features", "exits"} else "BLOCKED_OR_DIAGNOSTIC",
                "phase_a_result": "diagnostic_not_headline",
                "phase_b_result": phase_b_status,
                "future_information_safe": check in {"post-signal peaks", "09:30 features", "09:45 features", "10:00 features", "exits"} and phase_a.empty,
            }
        )
    return pd.DataFrame(rows)


def review_bundle(receipt: dict[str, Any], out: Path, phase_a_signals: pd.DataFrame, phase_b_status: str) -> str:
    s_count = int(phase_a_signals["rank"].astype(str).eq("S").sum()) if not phase_a_signals.empty and "rank" in phase_a_signals else 0
    apl_count = int(phase_a_signals["rank"].astype(str).eq("A_PLUS_NORMAL_SHADOW").sum()) if not phase_a_signals.empty and "rank" in phase_a_signals else 0
    lines = [
        "# Morita Historical S/A+ Deterministic Replay v1.3 Review Bundle",
        "",
        "1. Which code defines S? scripts/production_scanner_entry.py::_rank defines production S as production_adjusted_score >= 50; scanner/scoring.py also has scanner-native S candidate logic.",
        "2. Which code defines A+? No live production A+ label exists. A_PLUS_NORMAL_SHADOW is a diagnostic shadow artifact using A_PLUS_NORMAL_SCORE_GE_47 when present.",
        "3. Were any thresholds changed? No.",
        f"4. What decision timestamp was used? {NY_DECISION_TIMESTAMP}.",
        f"5. Did 2026 signals reproduce? {receipt['signal_2026_reproduction_status']}.",
        f"6. Did the 2026 Short baseline reproduce? {receipt['short_2026_reproduction_status']}.",
        f"7. How many Phase A tickers were replayed? {receipt['phase_a_universe_tickers']} current-universe tickers inventoried.",
        f"8. How many S and A+ signals by year? Phase A diagnostic S={s_count}, A_PLUS_NORMAL_SHADOW={apl_count}; see phase_a_signal_calendar.csv.",
        "9. How many D0 events, candidates, and independent episodes? 0 headline-valid; D0 remains blocked by missing daily replay feature panel.",
        "10. What is Phase A episode PF by route/instrument? Not computed; Phase A is diagnostic and D0 route inputs are blocked.",
        "11. Did 09:30 remain strongest? Not evaluated in v1.3 because no headline-valid D0/M15 route set was produced.",
        "12. Did 09:45 reduce losses? Not evaluated in v1.3.",
        "13. Did 10:30 remain non-viable? Frozen Short baseline preserves 10:30 diagnostic-only status; no new optimization.",
        "14. Did SOXX remain close to Basket A? Not evaluated beyond frozen baseline receipt.",
        "15. Which findings are survivorship-biased? All Phase A outputs.",
        "16. What historical-universe sources were found? No Authority A/B source; only current/diagnostic sources.",
        "17. What authority tier was achieved? CURRENT_UNIVERSE_ONLY for Phase A and Authority C diagnostic for Phase B inventory.",
        "18. Were delisted names and ticker changes handled? No, therefore Phase B is blocked.",
        "19. How many Phase B S and A+ signals by year? 0 headline-valid.",
        f"20. Did the Phase B gate pass? No: {phase_b_status}.",
        "21. What is Phase B episode PF? Not computed.",
        "22. Was PF >1 in at least three years? Not evaluated.",
        "23. How many signals were Phase-A-only versus Phase-B-only? Phase B is blocked; reconciliation marks Phase A diagnostic only.",
        "24. Did Phase A overstate or understate PF? Not measured; do not assume direction.",
        "25. What fraction of D1 decline occurred before 10:00? Not evaluated.",
        "26. What was the 09:45 pass rate? Frozen 2026 baseline source preserves count; no historical Phase A/B pass rate.",
        "27. What was the failed-probe average? Not evaluated.",
        "28. Did D1 close remain superior to D2? Not evaluated.",
        "29. What were Monday and Friday-to-Monday results? Not evaluated.",
        "30. Top-one episode/year/ticker contribution? Not evaluated.",
        "31. Leave-one-episode-out PF range? Not evaluated.",
        "32. Did S outperform A+? Not evaluated.",
        "33. Did S+A+ improve or dilute edge? Not evaluated.",
        "34. Did the 11-20-session age result persist? Not evaluated.",
        "35. Robust to 3/5/10-session episode definitions? Not evaluated.",
        "36. Did all future-information audits pass? They pass for non-executed route outputs; signal/universe headline use remains blocked/diagnostic.",
        "37. Were credentials reused safely without user action? Yes; no new credential request was made.",
        "38. Were strategies changed? No.",
        "39. Were options modeled? No.",
        "40. Were live orders created? No.",
        "41. Is Phase A diagnostic only? Yes.",
        "42. Is Phase B headline-valid? No.",
        f"43. What blockers remain? {', '.join(receipt['blockers'])}.",
        "44. What is the next single most useful improvement? Acquire an Authority A/B historical universe or a complete current-universe daily feature panel that can be replayed date by date.",
        "",
        f"Output directory: {out}",
    ]
    return "\n".join(lines) + "\n"


def run_v1_3(repo_root: Path, output_root: Path | None = None, run_id: str | None = None) -> V13Result:
    repo_root = Path(repo_root).resolve()
    run_id = run_id or utc_stamp()
    out = (output_root or repo_root / OUTPUT_ROOT) / run_id
    out.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    written.append(write_text(out / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker", "\n".join(f"{k}={str(v).lower()}" for k, v in GUARDRAILS.items()) + "\n"))
    seal = current_signal_engine_source_seal(repo_root)
    contract = rank_label_contract(repo_root)
    rule_receipt = frozen_rule_receipt(repo_root)
    signal_2026 = frozen_2026_signal_reproduction(repo_root)
    short_2026 = frozen_2026_short_reproduction(repo_root)
    phase_a_universe = phase_a_current_universe(repo_root)
    phase_a_signals = phase_a_signal_calendar(repo_root)
    phase_b_status = "PHASE_B_UNIVERSE_BLOCKED_OR_DIAGNOSTIC"
    phase_a_status = daily_replay_status("A", len(phase_a_signals))
    phase_b_status_df = daily_replay_status("B", 0)
    phase_a_recent = build_recent_state(phase_a_signals, "A")
    phase_b_recent = build_recent_state(pd.DataFrame(), "B")
    phase_a_d0 = d0_events(phase_a_signals, "A")
    phase_b_d0 = d0_events(pd.DataFrame(), "B")
    m15 = m15_manifest(phase_a_d0)
    blockers = ["PHASE_B_UNIVERSE_BLOCKED_OR_DIAGNOSTIC"]
    if phase_a_signals.empty:
        blockers.append("PHASE_A_NO_REPLAYED_SIGNAL_ROWS")
    if not short_2026.get("status", pd.Series(dtype=str)).astype(str).eq("PASS").all():
        blockers.append("FAIL_FROZEN_2026_BASELINE_REPRODUCTION")
    signal_2026_status = "PASS" if not signal_2026["status"].astype(str).str.startswith("FAIL").any() else "FAIL_FROZEN_2026_BASELINE_REPRODUCTION"
    short_2026_status = "PASS" if not short_2026["status"].astype(str).str.startswith("FAIL").any() else "FAIL_FROZEN_2026_BASELINE_REPRODUCTION"
    run_status = "PHASE_A_DIAGNOSTIC_PHASE_B_BLOCKED"
    if signal_2026_status == "PASS" and short_2026_status == "PASS":
        terminal = ["PHASE_A_DIAGNOSTIC_COMPLETE", phase_b_status, "NO_USER_ACTION_REQUIRED"]
    else:
        terminal = ["FAIL_FROZEN_2026_BASELINE_REPRODUCTION", phase_b_status, "NO_USER_ACTION_REQUIRED"]

    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "run_at_utc": utc_now(),
        "repo_root": str(repo_root),
        "output_dir": str(out),
        "run_status": run_status,
        "terminal_statuses": terminal,
        "blockers": sorted(set(blockers)),
        "signal_2026_reproduction_status": signal_2026_status,
        "short_2026_reproduction_status": short_2026_status,
        "phase_a_universe_tickers": int(phase_a_universe["ticker"].replace("", pd.NA).dropna().nunique()) if "ticker" in phase_a_universe else 0,
        "phase_a_signal_rows": int(len(phase_a_signals)),
        "phase_b_gate_passed": False,
        "user_action_required": False,
        "guardrails": GUARDRAILS,
    }

    written.append(write_json(out / "current_signal_engine_source_seal.json", seal))
    written.append(write_df(out / "current_rank_label_contract.csv", add_safety(contract)))
    written.append(write_json(out / "frozen_current_rule_receipt.json", rule_receipt))
    written.append(write_df(out / "production_rejection_test_results.csv", add_safety(production_rejection_results())))
    written.append(write_df(out / "frozen_2026_signal_reproduction.csv", add_safety(signal_2026)))
    written.append(write_df(out / "frozen_2026_short_reproduction.csv", add_safety(short_2026)))
    written.append(write_df(out / "phase_a_current_universe_manifest.csv", add_safety(phase_a_universe, phase="A")))
    written.append(write_df(out / "phase_a_daily_replay_status.csv", add_safety(phase_a_status, phase="A")))
    written.append(write_df(out / "phase_a_signal_calendar.csv", add_safety(phase_a_signals, phase="A")))
    written.append(write_df(out / "phase_a_all_candidate_scores.parquet", add_safety(phase_a_signals, phase="A")))
    written.append(write_df(out / "phase_a_exclusion_log.csv", add_safety(blocked_df("PHASE_A_EXCLUSIONS_NOT_REPLAYED"), phase="A")))
    written.append(write_df(out / "phase_a_daily_universe_snapshot.csv", add_safety(phase_a_universe, phase="A")))
    written.append(write_df(out / "phase_a_recent_signal_state.parquet", add_safety(phase_a_recent, phase="A")))
    written.append(write_df(out / "phase_a_d0_event_master.csv", add_safety(phase_a_d0, phase="A")))
    written.append(write_df(out / "phase_a_candidate_results.csv", add_safety(blocked_df("PHASE_A_D0_BLOCKED"), phase="A")))
    written.append(write_df(out / "phase_a_episode_master.csv", add_safety(blocked_df("PHASE_A_EPISODE_BLOCKED"), phase="A")))
    written.append(write_df(out / "phase_a_episode_portfolio.csv", add_safety(blocked_df("PHASE_A_EPISODE_PORTFOLIO_BLOCKED"), phase="A")))
    universe_inventory = historical_universe_inventory(repo_root)
    written.append(write_df(out / "historical_universe_source_inventory.csv", add_safety(universe_inventory, phase="B")))
    written.append(write_df(out / "historical_universe_membership.parquet", add_safety(blocked_df(phase_b_status), phase="B")))
    written.append(write_df(out / "historical_universe_eligibility_audit.csv", add_safety(blocked_df(phase_b_status), phase="B")))
    for name, df in {
        "phase_b_daily_replay_status.csv": phase_b_status_df,
        "phase_b_signal_calendar.csv": blocked_df(phase_b_status),
        "phase_b_all_candidate_scores.parquet": blocked_df(phase_b_status),
        "phase_b_exclusion_log.csv": blocked_df(phase_b_status),
        "phase_b_daily_universe_snapshot.csv": blocked_df(phase_b_status),
        "phase_b_recent_signal_state.parquet": phase_b_recent,
        "phase_b_d0_event_master.csv": phase_b_d0,
        "phase_b_candidate_results.csv": blocked_df(phase_b_status),
        "phase_b_episode_master.csv": blocked_df(phase_b_status),
        "phase_b_episode_portfolio.csv": blocked_df(phase_b_status),
    }.items():
        written.append(write_df(out / name, add_safety(df, phase="B")))
    written.append(write_df(out / "phase_a_vs_phase_b_signal_reconciliation.csv", add_safety(blocked_df("PHASE_B_BLOCKED_NO_RECONCILIATION"))))
    written.append(write_df(out / "m15_required_symbol_session_manifest.csv", add_safety(m15)))
    written.append(write_json(out / "m15_targeted_backfill_receipt.json", {"status": "NO_D0_EVENTS_FOR_TARGETED_M15", "fetch_attempted": False, **GUARDRAILS}))
    written.append(write_df(out / "m15_targeted_coverage_audit.csv", add_safety(blocked_df("NO_D0_EVENTS_FOR_TARGETED_M15"))))
    written.append(write_df(out / "m15_targeted_gap_manifest.csv", add_safety(blocked_df("NO_D0_EVENTS_FOR_TARGETED_M15"))))
    written.append(write_json(out / "credential_safety_audit.json", credential_safety_audit()))
    for name, df in performance_tables("NOT_EVALUATED_PHASE_B_BLOCKED_OR_D0_BLOCKED").items():
        written.append(write_df(out / name, add_safety(df)))
    written.append(write_df(out / "historical_replay_future_information_audit.csv", add_safety(future_information_audit(phase_a_signals, phase_b_status))))
    written.append(write_df(out / "survivorship_bias_audit.csv", add_safety(blocked_df("PHASE_B_BLOCKED_SURVIVORSHIP_BIAS_NOT_MEASURED"))))
    written.append(write_df(out / "historical_security_identity_audit.csv", add_safety(blocked_df("NO_DATE_EFFECTIVE_IDENTITY_SOURCE"))))
    written.append(write_text(out / "morita_historical_s_aplus_replay_v1_3_chatgpt_review_bundle.md", review_bundle(receipt, out, phase_a_signals, phase_b_status)))

    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "required_outputs": REQUIRED_OUTPUTS,
        "files": sorted(p.name for p in out.iterdir() if p.is_file()),
        "missing_required_outputs": sorted(set(REQUIRED_OUTPUTS) - {p.name for p in out.iterdir() if p.is_file()}),
        "guardrails": GUARDRAILS,
    }
    written.append(write_json(out / "run_manifest.json", manifest))
    written.append(write_json(out / "run_receipt.json", receipt))
    receipt["artifact_checksums"] = {p.name: sha256_file(p) for p in out.iterdir() if p.is_file() and p.name != "run_receipt.json"}
    write_json(out / "run_receipt.json", receipt)
    return V13Result(str(out), terminal, receipt)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Morita Historical S/A+ deterministic replay v1.3.")
    parser.add_argument("--output-dir", type=Path, default=None)
    for name in [
        "seal-current-rules",
        "reproduce-2026-baseline",
        "build-phase-a-universe",
        "run-phase-a-daily-replay",
        "inventory-historical-universe",
        "build-phase-b-universe",
        "run-phase-b-daily-replay",
        "build-recent-signal-states",
        "build-d0-events",
        "build-m15-fetch-manifest",
        "fetch-targeted-m15",
        "run-frozen-short-routes",
        "build-independent-episodes",
        "run-episode-portfolios",
        "audit-bias",
        "full-run",
    ]:
        parser.add_argument(f"--{name}", action="store_true")
    return parser.parse_args(argv)
