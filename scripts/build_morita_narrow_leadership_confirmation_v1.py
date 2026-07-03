from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "config" / "morita_narrow_leadership_v1" / "narrow_leadership_confirmation_spec.json"
CHATGPT_BUNDLE = REPO_ROOT / "morita_narrow_leadership_confirmation_chatgpt_bundle.md"
MANIFEST_NAME = "narrow_leadership_content_manifest.json"
DISPERSION_MANIFEST_NAME = "realized_dispersion_content_manifest.json"
REQUIRED_OUTPUTS = [
    "input_verification.csv",
    "s_2x2_cell_coverage.csv",
    "s_2x2_outcome_summary.csv",
    "s_2x2_required_comparisons.csv",
    "s_2x2_chronological_stability.csv",
    "s_2x2_ticker_concentration.csv",
    "s_2x2_reconciliation.csv",
    "narrow_leadership_receipt.json",
    "narrow_leadership_summary.md",
]
REQUIRED_CONTEXT_COLUMNS = {
    "signal_id",
    "signal_decision_date",
    "underlying_symbol",
    "signal_rank",
    "outcome_status",
    "reached_plus_5pct_within_10_sessions",
    "breakout_day_low_breach_before_timeout",
    "timeout_10_sessions_under_threshold",
    "scope",
    "metric",
    "metric_value",
    "metric_state",
}
CELLS = {
    "A": "D_high_and_L_high",
    "B": "D_high_and_L_not_high",
    "C": "D_not_high_and_L_high",
    "D": "D_not_high_and_L_not_high",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def safe_float(value: Any) -> float | None:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception:
        return None


def fmt(value: Any, digits: int = 2) -> str:
    value = safe_float(value)
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def md_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    work = df.head(max_rows).copy() if max_rows else df.copy()
    if work.empty:
        return "_No rows._"
    cols = [str(col) for col in work.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in work.iterrows():
        vals = []
        for col in work.columns:
            value = row[col]
            if pd.isna(value):
                vals.append("")
            elif isinstance(value, float):
                vals.append(fmt(value, 6))
            else:
                vals.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def verify_manifest(path: Path, manifest_name: str) -> dict[str, Any]:
    manifest_path = path / manifest_name
    if not manifest_path.exists():
        raise SystemExit(f"manifest_missing:{repo_relative(manifest_path)}")
    manifest = load_json(manifest_path)
    expected = {entry["relative_path"]: entry["sha256"] for entry in manifest.get("files", [])}
    actual = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file() and p.name != manifest_name}
    for rel, expected_hash in expected.items():
        target = path / rel
        if not target.exists():
            raise SystemExit(f"manifest_missing_file:{rel}")
        if file_sha256(target) != expected_hash:
            raise SystemExit(f"manifest_sha_mismatch:{rel}")
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise SystemExit(f"manifest_extra_file:{extras[0]}")
    return manifest


def build_manifest(path: Path) -> dict[str, Any]:
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and child.name != MANIFEST_NAME:
            files.append({"relative_path": child.relative_to(path).as_posix(), "sha256": file_sha256(child), "bytes": child.stat().st_size})
    manifest = {"artifact_version": "morita_narrow_leadership_confirmation_v1", "created_at_utc": iso_now(), "files": files, "content_set_hash": text_hash(json_dumps(files))}
    write_json(path / MANIFEST_NAME, manifest)
    return manifest


def safe_clean_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        resolved = output_dir.resolve()
        if REPO_ROOT.resolve() not in resolved.parents and resolved != REPO_ROOT.resolve():
            raise SystemExit(f"refusing_to_clean_outside_repo:{resolved}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def verify_inputs(baseline_run_dir: Path, dispersion_output_dir: Path, spec: dict[str, Any]) -> pd.DataFrame:
    verify_manifest(baseline_run_dir, "source_content_manifest.json")
    verify_manifest(dispersion_output_dir, DISPERSION_MANIFEST_NAME)
    base_receipt = load_json(baseline_run_dir / "baseline_receipt.json")
    disp_receipt = load_json(dispersion_output_dir / "realized_dispersion_receipt.json")
    checks = []
    checks.append({"check": "baseline_manifest", "status": "passed", "value": file_sha256(baseline_run_dir / "source_content_manifest.json")})
    checks.append({"check": "dispersion_manifest", "status": "passed", "value": file_sha256(dispersion_output_dir / DISPERSION_MANIFEST_NAME)})
    if base_receipt.get("run_id") != spec["baseline_run_id"]:
        raise SystemExit("baseline_run_id_mismatch")
    if disp_receipt.get("baseline_run_id") != spec["baseline_run_id"]:
        raise SystemExit("dispersion_baseline_run_id_mismatch")
    checks.append({"check": "input_run_identity_match", "status": "passed", "value": spec["baseline_run_id"]})
    cutoffs = pd.read_csv(dispersion_output_dir / "realized_dispersion_state_cutoffs.csv")
    if "state_construction" not in cutoffs.columns or not (cutoffs["state_construction"] == "unique_complete_signal_date_ex_post_terciles").any():
        raise SystemExit("state_cutoff_provenance_missing")
    checks.append({"check": "state_cutoff_provenance", "status": "passed", "value": "unique_complete_signal_date_ex_post_terciles"})
    context = pd.read_csv(dispersion_output_dir / "realized_dispersion_signal_context_panel.csv")
    missing = sorted(REQUIRED_CONTEXT_COLUMNS - set(context.columns))
    if missing:
        raise SystemExit(f"dispersion_context_schema_missing:{missing[0]}")
    for metric in [spec["dispersion_metric"], spec["leadership_metric"]]:
        if metric not in set(context["metric"]):
            raise SystemExit(f"required_metric_missing:{metric}")
        if not (context[context["metric"] == metric]["metric_state"].isin(["low", "middle", "high"]).any()):
            raise SystemExit(f"required_metric_state_missing:{metric}")
    checks.append({"check": "required_metrics_and_states", "status": "passed", "value": f"{spec['dispersion_metric']}|{spec['leadership_metric']}"})
    return pd.DataFrame(checks)


def build_wide_context(dispersion_output_dir: Path, spec: dict[str, Any]) -> pd.DataFrame:
    context = pd.read_csv(dispersion_output_dir / "realized_dispersion_signal_context_panel.csv")
    context = context[(context["scope"] == "broad_market_context") & (context["metric"].isin([spec["dispersion_metric"], spec["leadership_metric"]]))].copy()
    id_cols = ["signal_id", "signal_decision_date", "underlying_symbol", "signal_rank", "outcome_status", "reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"]
    dupes = context.duplicated(id_cols + ["metric"]).sum()
    if dupes:
        raise SystemExit("duplicate_signal_metric_identity")
    values = context.pivot(index=id_cols, columns="metric", values="metric_value").reset_index()
    states = context.pivot(index=id_cols, columns="metric", values="metric_state").reset_index()
    states = states.rename(columns={spec["dispersion_metric"]: "D_state", spec["leadership_metric"]: "L_state"})
    values = values.rename(columns={spec["dispersion_metric"]: "D_value", spec["leadership_metric"]: "L_value"})
    wide = values.merge(states[id_cols + ["D_state", "L_state"]], on=id_cols, how="left", validate="one_to_one")
    wide["signal_decision_date"] = pd.to_datetime(wide["signal_decision_date"])
    wide["D_high"] = wide["D_state"] == "high"
    wide["L_high"] = wide["L_state"] == "high"
    wide["eligible_2x2"] = wide["signal_rank"].eq(spec["rank"]) & wide["outcome_status"].eq(spec["complete_status"]) & wide["D_state"].isin(["low", "middle", "high"]) & wide["L_state"].isin(["low", "middle", "high"])
    wide["cell"] = None
    wide.loc[wide["eligible_2x2"] & wide["D_high"] & wide["L_high"], "cell"] = "A"
    wide.loc[wide["eligible_2x2"] & wide["D_high"] & ~wide["L_high"], "cell"] = "B"
    wide.loc[wide["eligible_2x2"] & ~wide["D_high"] & wide["L_high"], "cell"] = "C"
    wide.loc[wide["eligible_2x2"] & ~wide["D_high"] & ~wide["L_high"], "cell"] = "D"
    return wide


def concentration(sub: pd.DataFrame) -> dict[str, Any]:
    if len(sub) == 0:
        return {"largest_single_ticker_share": None, "top_five_ticker_share": None, "unique_ticker_count": 0}
    counts = sub["underlying_symbol"].value_counts()
    return {
        "largest_single_ticker_share": float(counts.iloc[0] / len(sub)),
        "top_five_ticker_share": float(counts.head(5).sum() / len(sub)),
        "unique_ticker_count": int(counts.size),
    }


def outcome_rates(sub: pd.DataFrame) -> dict[str, Any]:
    n = int(len(sub))
    if n == 0:
        return {"complete_signal_count": 0, "plus5_success_rate": None, "breakout_low_breach_rate": None, "timeout_rate": None}
    return {
        "complete_signal_count": n,
        "plus5_success_rate": float(sub["reached_plus_5pct_within_10_sessions"].map(boolish).mean()),
        "breakout_low_breach_rate": float(sub["breakout_day_low_breach_before_timeout"].map(boolish).mean()),
        "timeout_rate": float(sub["timeout_10_sessions_under_threshold"].map(boolish).mean()),
    }


def cell_summary(wide: pd.DataFrame) -> pd.DataFrame:
    eligible = wide[wide["eligible_2x2"]].copy()
    rows = []
    for cell, desc in CELLS.items():
        sub = eligible[eligible["cell"] == cell]
        row = {"cell": cell, "cell_description": desc}
        row.update(outcome_rates(sub))
        row.update(concentration(sub))
        rows.append(row)
    return pd.DataFrame(rows)


def side(wide: pd.DataFrame, side_name: str) -> pd.DataFrame:
    eligible = wide[wide["eligible_2x2"]]
    if side_name in CELLS:
        return eligible[eligible["cell"] == side_name]
    if side_name == "pooled_BCD":
        return eligible[eligible["cell"].isin(["B", "C", "D"])]
    raise ValueError(side_name)


def compare(wide: pd.DataFrame, left: str, right: str, scope: str, min_side: int, concentration_limit: float) -> dict[str, Any]:
    a = side(wide, left)
    b = side(wide, right)
    ar = outcome_rates(a)
    br = outcome_rates(b)
    ac = concentration(a)
    bc = concentration(b)
    eligible = ar["complete_signal_count"] >= min_side and br["complete_signal_count"] >= min_side
    concentration_flag = bool((ac["largest_single_ticker_share"] or 0) > concentration_limit or (bc["largest_single_ticker_share"] or 0) > concentration_limit)
    plus = None if ar["plus5_success_rate"] is None or br["plus5_success_rate"] is None else (ar["plus5_success_rate"] - br["plus5_success_rate"]) * 100
    breach = None if ar["breakout_low_breach_rate"] is None or br["breakout_low_breach_rate"] is None else (ar["breakout_low_breach_rate"] - br["breakout_low_breach_rate"]) * 100
    timeout = None if ar["timeout_rate"] is None or br["timeout_rate"] is None else (ar["timeout_rate"] - br["timeout_rate"]) * 100
    return {
        "scope": scope,
        "comparison": f"{left}_vs_{right}",
        "left_side": left,
        "right_side": right,
        "left_complete_signal_count": ar["complete_signal_count"],
        "right_complete_signal_count": br["complete_signal_count"],
        "plus5_difference_pp": plus,
        "breach_difference_pp": breach,
        "timeout_difference_pp": timeout,
        "directionally_adverse": bool(plus is not None and breach is not None and plus < 0 and breach > 0),
        "comparison_status": "eligible" if eligible else "insufficient_sample",
        "left_largest_single_ticker_share": ac["largest_single_ticker_share"],
        "right_largest_single_ticker_share": bc["largest_single_ticker_share"],
        "left_top_five_ticker_share": ac["top_five_ticker_share"],
        "right_top_five_ticker_share": bc["top_five_ticker_share"],
        "ticker_concentration_flag": concentration_flag if eligible else False,
    }


def build_comparisons(wide: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    fixed = [("A", "B"), ("A", "C"), ("A", "D"), ("A", "pooled_BCD"), ("C", "D"), ("B", "D")]
    rows = [compare(wide, left, right, "full_sample", int(spec["full_sample_min_per_side"]), float(spec["concentration_largest_single_ticker_share_max"])) for left, right in fixed]
    return pd.DataFrame(rows)


def split_halves(wide: pd.DataFrame) -> pd.Series:
    eligible_dates = sorted(wide.loc[wide["eligible_2x2"], "signal_decision_date"].dropna().unique())
    cut = len(eligible_dates) // 2
    early = set(eligible_dates[:cut])
    return wide["signal_decision_date"].map(lambda x: "early_half" if x in early else "late_half")


def build_chronological(wide: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    work = wide.copy()
    work["chronological_half"] = split_halves(work)
    rows = []
    for half in ["early_half", "late_half"]:
        sub = work[work["chronological_half"] == half]
        for left, right in [("A", "pooled_BCD"), ("A", "B"), ("A", "C"), ("A", "D")]:
            rows.append(compare(sub, left, right, half, int(spec["chronological_half_min_per_side"]), float(spec["concentration_largest_single_ticker_share_max"])))
    return pd.DataFrame(rows)


def reconciliation(wide: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"bucket": "all_context_rows_after_wide_join", "count": int(len(wide))},
        {"bucket": "eligible_S_complete_2x2", "count": int(wide["eligible_2x2"].sum())},
        {"bucket": "excluded_non_S", "count": int((wide["signal_rank"] != spec["rank"]).sum())},
        {"bucket": "excluded_collision", "count": int((wide["outcome_status"] == "ambiguous_intraday_order").sum())},
        {"bucket": "excluded_incomplete", "count": int((wide["outcome_status"] == "incomplete_horizon").sum())},
        {"bucket": "excluded_unavailable_state", "count": int((wide["signal_rank"].eq(spec["rank"]) & wide["outcome_status"].eq(spec["complete_status"]) & ~wide["eligible_2x2"]).sum())},
    ]
    return pd.DataFrame(rows)


def ticker_concentration(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    eligible = wide[wide["eligible_2x2"]]
    for cell in ["A", "B", "C", "D"]:
        sub = eligible[eligible["cell"] == cell]
        counts = sub["underlying_symbol"].value_counts().head(10)
        for ticker, count in counts.items():
            rows.append({"cell": cell, "ticker": ticker, "signal_count": int(count), "share": float(count / len(sub)) if len(sub) else None})
    return pd.DataFrame(rows)


def confirmation_label(comparisons: pd.DataFrame, chrono: pd.DataFrame, spec: dict[str, Any]) -> tuple[str, str]:
    main = comparisons[comparisons["comparison"] == "A_vs_pooled_BCD"].iloc[0]
    if main["comparison_status"] != "eligible":
        return "insufficient_sample_for_confirmation", "freeze_all_market_environment_research"
    main_adverse = bool(main["plus5_difference_pp"] <= spec["main_plus5_adverse_threshold_pp"] and main["breach_difference_pp"] >= spec["main_breach_adverse_threshold_pp"])
    if main_adverse and bool(main["ticker_concentration_flag"]):
        return "concentration_limited", "freeze_all_market_environment_research"
    component_rows = comparisons[comparisons["comparison"].isin(["A_vs_B", "A_vs_C", "A_vs_D"])]
    component_pass = component_rows[(component_rows["comparison_status"] == "eligible") & (~component_rows["ticker_concentration_flag"]) & (component_rows["plus5_difference_pp"] <= -float(spec["component_threshold_pp"])) & (component_rows["breach_difference_pp"] >= float(spec["component_threshold_pp"]))]
    conditional = component_pass[component_pass["comparison"].isin(["A_vs_B", "A_vs_C"])]
    chrono_main = chrono[chrono["comparison"] == "A_vs_pooled_BCD"]
    chrono_pass = len(chrono_main) == 2 and all((chrono_main["comparison_status"] == "eligible") & (~chrono_main["ticker_concentration_flag"]) & (chrono_main["plus5_difference_pp"] < 0) & (chrono_main["breach_difference_pp"] > 0))
    if main_adverse and not bool(main["ticker_concentration_flag"]) and len(component_pass) >= 2 and len(conditional) >= 1 and chrono_pass:
        return "confirmed_descriptive_narrow_leadership_pattern", "separate_later_non_blocking_label_proposal_only"
    return "inconsistent_or_non_incremental", "freeze_all_market_environment_research"


def build_summary_md(receipt: dict[str, Any], cells: pd.DataFrame, comparisons: pd.DataFrame, chrono: pd.DataFrame, recon: pd.DataFrame) -> str:
    lines = ["# Morita Narrow Leadership Confirmation v1", "", f"Status: `{receipt['status']}`", f"Baseline run: `{receipt['baseline_run_id']}`", f"Dispersion output: `{receipt['dispersion_output_dir']}`", f"Overall label: `{receipt['overall_confirmation_label']}`", f"Research decision: `{receipt['research_decision']}`", "", "## Reconciliation", md_table(recon), "", "## 2x2 Cells", md_table(cells), "", "## Required Comparisons", md_table(comparisons), "", "## Chronological Stability", md_table(chrono), "", "Inherited metrics/states only. No new data, no Bot rerun/rule change, no threshold search, no live filter or sizing change, no actionization."]
    return "\n".join(lines) + "\n"


def write_bundle(output_dir: Path, summary_md: str, receipt: dict[str, Any], comparisons: pd.DataFrame) -> None:
    lines = ["# ChatGPT Handoff: Morita Narrow Leadership Confirmation v1", "", "## Objective", "", "Confirm the fixed S-only narrow-leadership 2x2 hypothesis using inherited realized-dispersion states only.", "", "## Status", "", f"- Status: `{receipt['status']}`", f"- Overall label: `{receipt['overall_confirmation_label']}`", f"- Research decision: `{receipt['research_decision']}`", f"- Output directory: `{repo_relative(output_dir)}`", "", "## Required Comparisons", md_table(comparisons), "", "## Limitations", "", "- No raw signal rows included.", "- No new data.", "- No metric recalculation.", "- No threshold search.", "- No live filter, sizing change, alert, or actionization.", "", "## Embedded Summary", "", summary_md]
    CHATGPT_BUNDLE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_run(baseline_run_dir: Path, dispersion_output_dir: Path, output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    input_checks = verify_inputs(baseline_run_dir, dispersion_output_dir, spec)
    wide = build_wide_context(dispersion_output_dir, spec)
    cells = cell_summary(wide)
    comparisons = build_comparisons(wide, spec)
    chrono = build_chronological(wide, spec)
    recon = reconciliation(wide, spec)
    tickers = ticker_concentration(wide)
    label, decision = confirmation_label(comparisons, chrono, spec)
    receipt = {
        "status": "morita_narrow_leadership_confirmation_completed",
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "baseline_run_id": spec["baseline_run_id"],
        "baseline_run_dir": repo_relative(baseline_run_dir),
        "dispersion_output_dir": repo_relative(dispersion_output_dir),
        "dispersion_manifest_sha256": file_sha256(dispersion_output_dir / DISPERSION_MANIFEST_NAME),
        "eligible_s_complete_signal_count": int(wide["eligible_2x2"].sum()),
        "overall_confirmation_label": label,
        "research_decision": decision,
        "state_source": spec["state_source"],
        "state_definition": spec["state_definition"],
        "not_live_thresholds": True,
        "not_predictive_thresholds": True,
        "new_data_downloaded": False,
        "inherited_metrics_states_only": True,
        "bot_rerun_or_rule_change": False,
        "threshold_search_performed": False,
        "live_filter_or_sizing_change": False,
        "actionization_allowed": False,
    }
    safe_clean_output_dir(output_dir)
    write_dataframe(output_dir / "input_verification.csv", input_checks)
    write_dataframe(output_dir / "s_2x2_cell_coverage.csv", cells[["cell", "cell_description", "complete_signal_count", "largest_single_ticker_share", "top_five_ticker_share", "unique_ticker_count"]])
    write_dataframe(output_dir / "s_2x2_outcome_summary.csv", cells)
    write_dataframe(output_dir / "s_2x2_required_comparisons.csv", comparisons)
    write_dataframe(output_dir / "s_2x2_chronological_stability.csv", chrono)
    write_dataframe(output_dir / "s_2x2_ticker_concentration.csv", tickers)
    write_dataframe(output_dir / "s_2x2_reconciliation.csv", recon)
    write_json(output_dir / "narrow_leadership_receipt.json", receipt)
    summary_md = build_summary_md(receipt, cells, comparisons, chrono, recon)
    (output_dir / "narrow_leadership_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir)
    write_bundle(output_dir, summary_md, receipt, comparisons)
    return {"status": receipt["status"], "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "chatgpt_bundle": repo_relative(CHATGPT_BUNDLE), "overall_confirmation_label": label}


def verify_run(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifest(output_dir, MANIFEST_NAME)
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    missing = sorted(set(REQUIRED_OUTPUTS) - files)
    if missing:
        raise SystemExit(f"narrow_leadership_manifest_missing_required_output:{missing[0]}")
    return {"status": "morita_narrow_leadership_confirmation_verified", "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "file_count": len(files)}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline-run-dir")
    parser.add_argument("--dispersion-output-dir")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    if args.verify:
        print(json_dumps(verify_run(output_dir)))
        return 0
    if not args.baseline_run_dir or not args.dispersion_output_dir:
        raise SystemExit("--baseline-run-dir and --dispersion-output-dir are required with --run")
    baseline_run_dir = Path(args.baseline_run_dir)
    dispersion_output_dir = Path(args.dispersion_output_dir)
    if not baseline_run_dir.is_absolute():
        baseline_run_dir = REPO_ROOT / baseline_run_dir
    if not dispersion_output_dir.is_absolute():
        dispersion_output_dir = REPO_ROOT / dispersion_output_dir
    print(json_dumps(build_run(baseline_run_dir, dispersion_output_dir, output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
