from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "config" / "morita_s_tp_comparison_v1" / "s_tp100_tp125_staged_spec.json"
DEFAULT_BASELINE_DIR = (
    REPO_ROOT
    / "market_bomb_history"
    / "morita_bot_historical_baseline_v1"
    / "historical_runs"
    / "morita_baseline_20260703T123912Z_4994e3744ffa"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_s_tp_comparison"
CHATGPT_BUNDLE_PATH = REPO_ROOT / "morita_s_tp100_vs_tp125_comparison_chatgpt_bundle.md"

FAIL_CLOSED_STATUS = "canonical_single_call_model_not_reproducible_on_formal_S_baseline"
INSUFFICIENT_LABEL = "insufficient_canonical_coverage"
PORTFOLIO_UNAVAILABLE = "unavailable_no_existing_canonical_aggregation"

REQUIRED_OUTPUT_FILES = [
    "canonical_model_source_verification.csv",
    "s_tp_policy_trade_summary.csv",
    "s_tp_policy_portfolio_summary.csv",
    "s_tp100_to_tp125_path_classes.csv",
    "s_tp100_to_tp125_giveback_summary.csv",
    "s_tp100_to_tp125_chronological_summary.csv",
    "s_tp100_to_tp125_concentration_summary.csv",
    "s_tp100_to_tp125_representative_paths.csv",
    "s_tp_comparison_receipt.json",
    "s_tp_comparison_content_manifest.json",
    "s_tp_comparison_summary.md",
]

LIVE_ACTION_TOKENS = [
    "BUY_NOW",
    "SELL_NOW",
    "ORDER",
    "ALERT_CHANGE",
    "SIZE_UP",
    "SIZE_DOWN",
    "LIVE_TARGET_CHANGE",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_spec() -> dict[str, Any]:
    return read_json(SPEC_PATH)


def load_baseline_identity(baseline_run_dir: Path) -> dict[str, Any]:
    receipt_path = baseline_run_dir / "baseline_receipt.json"
    rule_path = baseline_run_dir / "source_rule_snapshot.json"
    panel_path = baseline_run_dir / "morita_bot_baseline_panel.csv"
    if not receipt_path.exists() or not rule_path.exists() or not panel_path.exists():
        return {
            "baseline_verified": False,
            "baseline_status": "missing_required_formal_baseline_files",
            "run_id": "",
            "repository_commit_sha": "",
            "signal_row_count": 0,
            "outcome_row_count": 0,
            "s_signal_count": 0,
            "s_complete_count": 0,
        }

    receipt = read_json(receipt_path)
    panel = pd.read_csv(panel_path)
    s_panel = panel[panel["signal_rank"].astype(str) == "S"] if "signal_rank" in panel else panel.iloc[0:0]
    complete = s_panel[s_panel["outcome_status"].astype(str) == "complete"] if "outcome_status" in s_panel else s_panel.iloc[0:0]
    required_run_id = "morita_baseline_20260703T123912Z_4994e3744ffa"
    verified = (
        receipt.get("formal_historical_baseline") is True
        and receipt.get("run_id") == required_run_id
        and receipt.get("actionization_allowed") is False
        and receipt.get("research_only") is True
    )
    return {
        "baseline_verified": bool(verified),
        "baseline_status": "verified" if verified else "formal_baseline_identity_mismatch",
        "run_id": receipt.get("run_id", ""),
        "repository_commit_sha": receipt.get("repository_commit_sha", ""),
        "signal_row_count": int(receipt.get("signal_row_count", len(panel))),
        "outcome_row_count": int(receipt.get("outcome_row_count", len(panel))),
        "s_signal_count": int((panel["signal_rank"].astype(str) == "S").sum()) if "signal_rank" in panel else 0,
        "s_complete_count": int(len(complete)),
    }


def discover_canonical_model_sources(baseline_run_dir: Path) -> list[dict[str, Any]]:
    legacy_dir = Path(r"C:\Users\keisu\Documents\Codex\2026-06-14\files-mentioned-by-the-user-codex\outputs\call_backtest")
    current_single_call_hits = [
        "scripts/production_scanner_entry.py",
        "scripts/trade_logger.py",
        "outputs/phase1_6c_morita_bot_mechanical_flow_context/morita_bot_canonical_signal_outcome_panel.csv",
    ]
    rows: list[dict[str, Any]] = []
    rows.append(
        {
            "source_component": "formal_S_baseline",
            "status": "implemented_underlying_only",
            "path": str(baseline_run_dir.relative_to(REPO_ROOT)) if baseline_run_dir.is_relative_to(REPO_ROOT) else str(baseline_run_dir),
            "sha256": sha256_file(baseline_run_dir / "baseline_receipt.json") if (baseline_run_dir / "baseline_receipt.json").exists() else "",
            "compatible_with_formal_S_baseline": True,
            "usable_for_tp_comparison": False,
            "notes": "Formal baseline is verified for S signal identity and underlying outcome fields, but it does not contain daily modeled single-call valuation paths.",
        }
    )
    rows.append(
        {
            "source_component": "repo_committed_single_call_tp_engine",
            "status": "not_implemented",
            "path": "",
            "sha256": "",
            "compatible_with_formal_S_baseline": False,
            "usable_for_tp_comparison": False,
            "notes": "No committed engine was found that replays canonical single-call daily net option returns on the formal S baseline with deterministic independent terminal semantics.",
        }
    )
    for rel_path in current_single_call_hits:
        path = REPO_ROOT / rel_path
        rows.append(
            {
                "source_component": "current_repo_reference_" + Path(rel_path).stem,
                "status": "reference_only" if path.exists() else "missing",
                "path": rel_path,
                "sha256": sha256_file(path) if path.exists() else "",
                "compatible_with_formal_S_baseline": path.exists(),
                "usable_for_tp_comparison": False,
                "notes": "Contains notification text or declared-exit summary fields, not a canonical single-call valuation path engine.",
            }
        )
    rows.append(
        {
            "source_component": "legacy_call_backtest_outputs_20260617",
            "status": "detected_in_accessible_workspace" if legacy_dir.exists() else "not_detected_in_accessible_workspace",
            "path": str(legacy_dir),
            "sha256": sha256_file(legacy_dir / "call_backtest_report.md") if (legacy_dir / "call_backtest_report.md").exists() else "",
            "compatible_with_formal_S_baseline": False,
            "usable_for_tp_comparison": False,
            "notes": "Legacy research used a limited 2023+ active sample and generated aggregate/trade CSVs; it is not the current formal S baseline and no committed compatible replay engine was found here.",
        }
    )
    return rows


def as_float(value: Any) -> float:
    if value is None or value == "":
        return math.nan
    return float(value)


def path_sorted(path: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(path, key=lambda row: (row.get("valuation_index", 0), str(row.get("valuation_time", ""))))


def validate_independent_terminal(path: list[dict[str, Any]]) -> dict[str, Any]:
    terminals = [row for row in path if bool(row.get("independent_terminal"))]
    if len(terminals) != 1:
        raise ValueError("independent_terminal_not_reproducible")
    return terminals[0]


def first_hit(path: list[dict[str, Any]], target_pct: float, start_index: int = 0) -> dict[str, Any] | None:
    for idx, row in enumerate(path_sorted(path)):
        if idx < start_index:
            continue
        ret = as_float(row.get("net_option_return_pct"))
        if not math.isnan(ret) and ret >= target_pct:
            out = dict(row)
            out["_path_index"] = idx
            return out
    return None


def policy_return_pct(path: list[dict[str, Any]], policy: str) -> float:
    ordered = path_sorted(path)
    terminal = validate_independent_terminal(ordered)
    terminal_return = as_float(terminal.get("net_option_return_pct"))
    if policy == "TP100":
        return 100.0 if first_hit(ordered, 100.0) is not None else terminal_return
    if policy == "TP125":
        return 125.0 if first_hit(ordered, 125.0) is not None else terminal_return
    if policy == "STAGED_100_125":
        hit100 = first_hit(ordered, 100.0)
        if hit100 is None:
            return terminal_return
        hit125 = first_hit(ordered, 125.0, int(hit100["_path_index"]))
        second_leg = 125.0 if hit125 is not None else terminal_return
        return 0.5 * 100.0 + 0.5 * second_leg
    raise ValueError(f"unknown_policy:{policy}")


def classify_path(path: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = path_sorted(path)
    terminal = validate_independent_terminal(ordered)
    hit100 = first_hit(ordered, 100.0)
    hit125 = first_hit(ordered, 125.0)
    if any(bool(row.get("target_path_ambiguous")) for row in ordered):
        return {"path_class": "CLASS_6_PATH_AMBIGUOUS", "broad_class": "ambiguous"}
    if hit100 is None:
        return {"path_class": "NO_100_HIT", "broad_class": "no_100_hit"}
    idx100 = int(hit100["_path_index"])
    post100 = ordered[idx100:]
    hit125_after = first_hit(ordered, 125.0, idx100)
    terminal_return = as_float(terminal.get("net_option_return_pct"))
    trough = min(as_float(row.get("net_option_return_pct")) for row in post100)
    peak = max(as_float(row.get("net_option_return_pct")) for row in post100)
    below100_before_125 = False
    if hit125_after is not None:
        idx125 = int(hit125_after["_path_index"])
        below100_before_125 = any(as_float(row.get("net_option_return_pct")) < 100.0 for row in ordered[idx100 + 1 : idx125])
        path_class = "CLASS_2_DIP_THEN_125" if below100_before_125 else "CLASS_1_DIRECT_100_TO_125"
        broad_class = "100_then_125"
    elif terminal_return >= 100.0:
        path_class = "CLASS_5_100_TO_TERMINAL_STILL_ABOVE_100"
        broad_class = "100_only_never_125"
    else:
        path_class = "CLASS_4_100_TO_TERMINAL_LOSS_OF_PROFIT"
        broad_class = "100_only_never_125"
    return {
        "path_class": path_class,
        "broad_class": broad_class,
        "first_hit_100_time": hit100.get("valuation_time", ""),
        "first_hit_125_time": hit125.get("valuation_time", "") if hit125 else "",
        "independent_terminal_time": terminal.get("valuation_time", ""),
        "independent_terminal_reason": terminal.get("terminal_reason", ""),
        "independent_terminal_return_pct": terminal_return,
        "post_100_peak_return_pct": peak,
        "post_100_trough_return_pct": trough,
        "post_100_drawdown_from_100_pct_points": trough - 100.0,
        "dipped_below_100_before_125": below100_before_125,
    }


def profit_factor(returns_pct: Iterable[float]) -> dict[str, float]:
    vals = [float(v) for v in returns_pct if not math.isnan(float(v))]
    gross_profit = sum(v for v in vals if v > 0)
    gross_loss = -sum(v for v in vals if v < 0)
    pf = math.inf if gross_profit > 0 and gross_loss == 0 else (gross_profit / gross_loss if gross_loss > 0 else 0.0)
    return {"gross_profit": gross_profit, "gross_loss": gross_loss, "profit_factor": pf}


def max_consecutive_losses(returns_pct: Iterable[float]) -> int:
    longest = 0
    current = 0
    for value in returns_pct:
        if float(value) < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def summarize_returns(returns_pct: list[float]) -> dict[str, Any]:
    if not returns_pct:
        return {
            "eligible_trade_count": 0,
            "trade_return_mean": "",
            "trade_return_median": "",
            "trade_return_p10": "",
            "trade_return_p25": "",
            "trade_return_p75": "",
            "trade_return_p90": "",
            "win_rate": "",
            "profit_factor": "",
            "gross_profit": "",
            "gross_loss": "",
            "max_single_trade_gain": "",
            "max_single_trade_loss": "",
            "largest_winner_share_of_gross_profit": "",
            "consecutive_loss_max": "",
        }
    series = pd.Series(returns_pct, dtype="float64")
    pf = profit_factor(returns_pct)
    gross_profit = pf["gross_profit"]
    largest_winner = max([v for v in returns_pct if v > 0], default=0.0)
    return {
        "eligible_trade_count": len(returns_pct),
        "trade_return_mean": float(series.mean()),
        "trade_return_median": float(series.median()),
        "trade_return_p10": float(series.quantile(0.10)),
        "trade_return_p25": float(series.quantile(0.25)),
        "trade_return_p75": float(series.quantile(0.75)),
        "trade_return_p90": float(series.quantile(0.90)),
        "win_rate": float((series > 0).mean()),
        "profit_factor": pf["profit_factor"],
        "gross_profit": gross_profit,
        "gross_loss": pf["gross_loss"],
        "max_single_trade_gain": float(series.max()),
        "max_single_trade_loss": float(series.min()),
        "largest_winner_share_of_gross_profit": (largest_winner / gross_profit if gross_profit else 0.0),
        "consecutive_loss_max": max_consecutive_losses(returns_pct),
    }


def policy_deltas(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy = {row["policy"]: row for row in summary_rows}
    pairs = [("TP125", "TP100"), ("STAGED_100_125", "TP100"), ("STAGED_100_125", "TP125")]
    rows: list[dict[str, Any]] = []
    for left, right in pairs:
        lrow = by_policy.get(left, {})
        rrow = by_policy.get(right, {})
        rows.append(
            {
                "comparison": f"{left}_minus_{right}",
                "mean_return_difference": numeric_delta(lrow.get("trade_return_mean"), rrow.get("trade_return_mean")),
                "median_return_difference": numeric_delta(lrow.get("trade_return_median"), rrow.get("trade_return_median")),
                "pf_difference": numeric_delta(lrow.get("profit_factor"), rrow.get("profit_factor")),
                "gross_profit_difference": numeric_delta(lrow.get("gross_profit"), rrow.get("gross_profit")),
                "gross_loss_difference": numeric_delta(lrow.get("gross_loss"), rrow.get("gross_loss")),
                "dd_difference": "",
            }
        )
    return rows


def numeric_delta(left: Any, right: Any) -> Any:
    if left == "" or right == "":
        return ""
    return float(left) - float(right)


def concentration_summary(rows: list[dict[str, Any]], group_key: str = "ticker") -> dict[str, Any]:
    if not rows:
        return {"unique_ticker_count": 0, "largest_single_ticker_share": "", "top_five_ticker_share": ""}
    counts = Counter(str(row.get(group_key, "")) for row in rows)
    total = sum(counts.values())
    shares = sorted((count / total for count in counts.values()), reverse=True)
    return {
        "unique_ticker_count": len(counts),
        "largest_single_ticker_share": shares[0] if shares else "",
        "top_five_ticker_share": sum(shares[:5]) if shares else "",
    }


def chronological_halves(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    unique_dates = sorted({str(row["entry_date"]) for row in rows})
    split = (len(unique_dates) + 1) // 2
    early_dates = set(unique_dates[:split])
    return {
        "early_half": [row for row in rows if str(row["entry_date"]) in early_dates],
        "late_half": [row for row in rows if str(row["entry_date"]) not in early_dates],
    }


def choose_overall_label(rows: list[dict[str, Any]], concentration_flag: bool, dd_available: bool = False) -> str:
    if not rows:
        return INSUFFICIENT_LABEL
    by_policy = {row["policy"]: row for row in rows}
    try:
        tp100_pf = float(by_policy["TP100"]["profit_factor"])
        tp125_pf = float(by_policy["TP125"]["profit_factor"])
        staged_pf = float(by_policy["STAGED_100_125"]["profit_factor"])
    except (KeyError, TypeError, ValueError):
        return INSUFFICIENT_LABEL
    if concentration_flag:
        return "no_clear_preference"
    if not dd_available:
        if tp100_pf - tp125_pf >= 0.15:
            return "tp100_preferred_descriptively"
        if tp125_pf - tp100_pf >= 0.15:
            return "tp125_preferred_descriptively"
        return "no_clear_preference"
    best_full = max(tp100_pf, tp125_pf)
    if staged_pf >= best_full - 0.10:
        return "staged_exit_preferred_descriptively"
    return "no_clear_preference"


def build_blocked_outputs(baseline_run_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = load_spec()
    identity = load_baseline_identity(baseline_run_dir)
    verification_rows = discover_canonical_model_sources(baseline_run_dir)
    status = FAIL_CLOSED_STATUS
    summary_counts = {
        "formal_s_signal_count": identity["s_signal_count"],
        "formal_s_complete_count": identity["s_complete_count"],
        "eligible_trade_count": 0,
        "excluded_trade_count": identity["s_complete_count"],
        "excluded_reason": status,
    }

    write_csv(
        output_dir / "canonical_model_source_verification.csv",
        verification_rows,
        [
            "source_component",
            "status",
            "path",
            "sha256",
            "compatible_with_formal_S_baseline",
            "usable_for_tp_comparison",
            "notes",
        ],
    )
    policy_rows = [
        {
            "policy": policy,
            "status": status,
            "eligible_trade_count": 0,
            "excluded_trade_count": identity["s_complete_count"],
            "excluded_reason": status,
            "trade_return_mean": "",
            "trade_return_median": "",
            "trade_return_p10": "",
            "trade_return_p25": "",
            "trade_return_p75": "",
            "trade_return_p90": "",
            "win_rate": "",
            "profit_factor": "",
            "gross_profit": "",
            "gross_loss": "",
            "max_single_trade_gain": "",
            "max_single_trade_loss": "",
            "largest_winner_share_of_gross_profit": "",
            "consecutive_loss_max": "",
        }
        for policy in ["TP100", "TP125", "STAGED_100_125"]
    ]
    write_csv(
        output_dir / "s_tp_policy_trade_summary.csv",
        policy_rows,
        [
            "policy",
            "status",
            "eligible_trade_count",
            "excluded_trade_count",
            "excluded_reason",
            "trade_return_mean",
            "trade_return_median",
            "trade_return_p10",
            "trade_return_p25",
            "trade_return_p75",
            "trade_return_p90",
            "win_rate",
            "profit_factor",
            "gross_profit",
            "gross_loss",
            "max_single_trade_gain",
            "max_single_trade_loss",
            "largest_winner_share_of_gross_profit",
            "consecutive_loss_max",
        ],
    )
    write_csv(
        output_dir / "s_tp_policy_portfolio_summary.csv",
        [
            {
                "policy": policy,
                "portfolio_metrics_status": PORTFOLIO_UNAVAILABLE,
                "portfolio_max_drawdown": "",
                "dd_20pct_or_worse_rate": "",
                "dd_30pct_or_worse_rate": "",
                "dd_50pct_or_worse_rate": "",
                "notes": "No existing canonical portfolio aggregation for this TP comparison was available.",
            }
            for policy in ["TP100", "TP125", "STAGED_100_125"]
        ],
        ["policy", "portfolio_metrics_status", "portfolio_max_drawdown", "dd_20pct_or_worse_rate", "dd_30pct_or_worse_rate", "dd_50pct_or_worse_rate", "notes"],
    )
    write_csv(
        output_dir / "s_tp100_to_tp125_path_classes.csv",
        [
            {
                "path_class": "insufficient_canonical_coverage",
                "count": 0,
                "rate": "",
                "median_independent_terminal_return": "",
                "median_post_100_trough_return": "",
                "median_post_100_peak_return": "",
                "median_days_from_100_to_125": "",
                "notes": status,
            }
        ],
        [
            "path_class",
            "count",
            "rate",
            "median_independent_terminal_return",
            "median_post_100_trough_return",
            "median_post_100_peak_return",
            "median_days_from_100_to_125",
            "notes",
        ],
    )
    write_csv(
        output_dir / "s_tp100_to_tp125_giveback_summary.csv",
        [
            {
                "metric": metric,
                "value": "",
                "denominator": 0,
                "status": status,
            }
            for metric in [
                "all_eligible_S_trades",
                "reached_plus_100",
                "reached_plus_125",
                "reached_plus_100_but_not_125",
                "reached_plus_100_then_later_125",
                "share_never_reached_plus_125",
                "share_gave_back_25pct_points_from_100",
                "share_gave_back_50pct_points_from_100",
                "share_gave_back_100pct_points_from_100",
                "share_ending_below_100_without_touching_125",
                "share_ending_below_0_without_touching_125",
            ]
        ],
        ["metric", "value", "denominator", "status"],
    )
    write_csv(
        output_dir / "s_tp100_to_tp125_chronological_summary.csv",
        [
            {
                "half": half,
                "TP100_profit_factor": "",
                "TP125_profit_factor": "",
                "STAGED_profit_factor": "",
                "reached_plus_100_count": "",
                "hundred_only_never_125_rate": "",
                "status": status,
            }
            for half in ["early_half", "late_half"]
        ],
        ["half", "TP100_profit_factor", "TP125_profit_factor", "STAGED_profit_factor", "reached_plus_100_count", "hundred_only_never_125_rate", "status"],
    )
    write_csv(
        output_dir / "s_tp100_to_tp125_concentration_summary.csv",
        [
            {
                "scope": scope,
                "unique_ticker_count": "",
                "largest_single_ticker_share": "",
                "top_five_ticker_share": "",
                "concentration_flag": "",
                "status": status,
            }
            for scope in ["TP100", "TP125", "STAGED_100_125", "CLASS_1_DIRECT_100_TO_125", "CLASS_2_DIP_THEN_125", "CLASS_3_100_ONLY_NEVER_125"]
        ],
        ["scope", "unique_ticker_count", "largest_single_ticker_share", "top_five_ticker_share", "concentration_flag", "status"],
    )
    write_csv(
        output_dir / "s_tp100_to_tp125_representative_paths.csv",
        [],
        [
            "ticker",
            "signal_date",
            "entry_date",
            "first_plus_100_time",
            "first_plus_125_time",
            "independent_terminal_time",
            "independent_terminal_reason",
            "TP100_modeled_return",
            "TP125_modeled_return",
            "staged_modeled_return",
            "post_100_trough",
            "post_100_peak",
            "path_class",
        ],
    )

    receipt = {
        "run_id": "morita_s_tp_comparison_v1_" + utc_now().replace("-", "").replace(":", ""),
        "created_at_utc": utc_now(),
        "status": status,
        "overall_comparison_label": INSUFFICIENT_LABEL,
        "research_only": True,
        "actionization_allowed": False,
        "new_data_downloaded": False,
        "canonical_model_reused": False,
        "canonical_model_reuse_status": status,
        "no_target_stop_optimization": True,
        "no_live_alert_change": True,
        "baseline_identity": identity,
        "summary_counts": summary_counts,
        "spec_sha256": sha256_file(SPEC_PATH),
        "source_verification_rows": len(verification_rows),
    }
    (output_dir / "s_tp_comparison_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    summary_md = render_summary_md(receipt, verification_rows)
    (output_dir / "s_tp_comparison_summary.md").write_text(summary_md, encoding="utf-8")
    write_manifest(output_dir)
    CHATGPT_BUNDLE_PATH.write_text(render_chatgpt_bundle(receipt, verification_rows, summary_md), encoding="utf-8")
    return receipt


def render_summary_md(receipt: dict[str, Any], verification_rows: list[dict[str, Any]]) -> str:
    identity = receipt["baseline_identity"]
    lines = [
        "# Morita S TP100 vs TP125 Comparison v1",
        "",
        f"Status: `{receipt['status']}`",
        f"Overall label: `{receipt['overall_comparison_label']}`",
        "",
        "## Source Identity",
        "",
        f"- Formal baseline run: `{identity.get('run_id', '')}`",
        f"- Baseline verified: `{identity.get('baseline_verified', False)}`",
        f"- Baseline commit: `{identity.get('repository_commit_sha', '')}`",
        f"- S signals: `{identity.get('s_signal_count', 0)}`",
        f"- S complete underlying outcomes: `{identity.get('s_complete_count', 0)}`",
        "",
        "## Decision",
        "",
        "No TP100/TP125/staged profit-factor comparison was produced because a committed canonical single-call valuation path engine compatible with the formal S baseline was not reproducible.",
        "",
        "This is a fail-closed result, not a negative result for TP100 or TP125.",
        "",
        "## Source Discovery",
        "",
        "| Component | Status | Usable | Notes |",
        "|---|---:|---:|---|",
    ]
    for row in verification_rows:
        lines.append(f"| {row['source_component']} | {row['status']} | {row['usable_for_tp_comparison']} | {row['notes']} |")
    lines.extend(
        [
            "",
            "## Confirmations",
            "",
            "- No new market data was downloaded.",
            "- No underlying-only returns were substituted for option returns.",
            "- No target, stop, DTE, delta, IV, cost, or hold-period optimization was run.",
            "- No live alert, sizing, order, or trading behavior was changed.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_chatgpt_bundle(receipt: dict[str, Any], verification_rows: list[dict[str, Any]], summary_md: str) -> str:
    lines = [
        "# ChatGPT Handoff: Morita S TP100 vs TP125 Comparison v1",
        "",
        "## Objective",
        "",
        "Compare S-rank single-call exits TP100, TP125, and fixed 50/50 staged exit only if the canonical single-call model can be replayed on the formal S baseline.",
        "",
        "## Current Result",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Overall label: `{receipt['overall_comparison_label']}`",
        f"- Formal S signals: `{receipt['baseline_identity'].get('s_signal_count', 0)}`",
        f"- Formal S complete underlying outcomes: `{receipt['baseline_identity'].get('s_complete_count', 0)}`",
        "- Eligible canonical single-call trades: `0`",
        "",
        "## Missing Artifact",
        "",
        "A committed canonical single-call daily valuation path engine compatible with the formal S baseline was not found. The available formal baseline is signal/outcome lineage with underlying outcome fields, not a single-call path replay.",
        "",
        "## Source Verification Rows",
        "",
        "| Component | Status | Compatible | Usable |",
        "|---|---:|---:|---:|",
    ]
    for row in verification_rows:
        lines.append(f"| {row['source_component']} | {row['status']} | {row['compatible_with_formal_S_baseline']} | {row['usable_for_tp_comparison']} |")
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `outputs/morita_s_tp_comparison/canonical_model_source_verification.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp_policy_trade_summary.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp_policy_portfolio_summary.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp100_to_tp125_path_classes.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp100_to_tp125_giveback_summary.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp100_to_tp125_chronological_summary.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp100_to_tp125_concentration_summary.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp100_to_tp125_representative_paths.csv`",
            "- `outputs/morita_s_tp_comparison/s_tp_comparison_receipt.json`",
            "- `outputs/morita_s_tp_comparison/s_tp_comparison_content_manifest.json`",
            "- `outputs/morita_s_tp_comparison/s_tp_comparison_summary.md`",
            "",
            "## Next GPT Instruction",
            "",
            "Do not infer TP100 vs TP125 performance from the legacy call_backtest outputs. First implement or locate a committed canonical single-call path replay engine that takes the formal baseline signal set and emits per-trade daily net option returns through an independent terminal condition. Only then rerun the fixed TP100/TP125/staged comparison.",
            "",
            "## Embedded Summary",
            "",
            summary_md,
        ]
    )
    return "\n".join(lines)


def write_manifest(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "s_tp_comparison_content_manifest.json"
    rows = []
    for name in REQUIRED_OUTPUT_FILES:
        if name == manifest_path.name:
            continue
        path = output_dir / name
        if not path.exists():
            continue
        rows.append({"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {
        "manifest_version": "s_tp_comparison_content_manifest_v1",
        "created_at_utc": utc_now(),
        "required_files": REQUIRED_OUTPUT_FILES,
        "files": rows,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def verify_output_dir(output_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_OUTPUT_FILES if not (output_dir / name).exists()]
    actual = sorted(path.name for path in output_dir.iterdir() if path.is_file()) if output_dir.exists() else []
    extra = [name for name in actual if name not in REQUIRED_OUTPUT_FILES]
    manifest_path = output_dir / "s_tp_comparison_content_manifest.json"
    changed: list[str] = []
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        for row in manifest.get("files", []):
            path = output_dir / row["path"]
            if not path.exists() or sha256_file(path) != row["sha256"]:
                changed.append(row["path"])
    clean = not missing and not extra and not changed
    return {"verified": clean, "missing": missing, "extra": extra, "changed": changed}


def assert_no_live_actionization(output_dir: Path) -> None:
    for path in output_dir.glob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in LIVE_ACTION_TOKENS:
                if token in text:
                    raise AssertionError(f"live_action_token_detected:{token}:{path}")


def run(args: argparse.Namespace) -> int:
    if args.run:
        receipt = build_blocked_outputs(Path(args.baseline_run_dir), Path(args.output_dir))
        print(json.dumps({"status": receipt["status"], "overall_comparison_label": receipt["overall_comparison_label"]}, sort_keys=True))
    if args.verify:
        result = verify_output_dir(Path(args.output_dir))
        assert_no_live_actionization(Path(args.output_dir))
        print(json.dumps(result, sort_keys=True))
        if not result["verified"]:
            return 1
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify Morita S TP100/TP125 fail-closed comparison artifacts.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline-run-dir", default=str(DEFAULT_BASELINE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    forbidden = ["--dte", "--delta", "--strike", "--iv", "--cost", "--target", "--split", "--hold", "--rank"]
    if any(arg.split("=")[0] in forbidden for arg in argv):
        raise SystemExit("fixed_spec_rejects_parameter_override")
    args = parser.parse_args(argv)
    if not args.run and not args.verify:
        parser.error("one of --run or --verify is required")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
