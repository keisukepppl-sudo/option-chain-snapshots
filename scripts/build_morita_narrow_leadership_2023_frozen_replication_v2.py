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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.build_morita_realized_dispersion_quick_screen_v1 as dispersion


SPEC_PATH = REPO_ROOT / "config" / "morita_narrow_leadership_2023_frozen_replication_v2" / "replication_spec.json"
OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_narrow_leadership_2023_frozen_replication_v2"
CHATGPT_BUNDLE = REPO_ROOT / "morita_narrow_leadership_2023_frozen_replication_v2_chatgpt_bundle.md"
MANIFEST_NAME = "replication_content_manifest.json"
CELLS = {
    "A": "NARROW_LEADERSHIP_ON",
    "B": "D_high_AND_L_not_high",
    "C": "D_not_high_AND_L_high",
    "D": "D_not_high_AND_L_not_high",
}
REQUIRED_OUTPUTS = [
    "input_verification.csv",
    "source_artifact_lineage.json",
    "state_cutoff_inheritance.json",
    "2023_state_coverage.csv",
    "2023_signal_reconciliation.csv",
    "2023_s_2x2_cell_coverage.csv",
    "2023_s_2x2_outcome_summary.csv",
    "2023_s_2x2_required_comparisons.csv",
    "2023_s_2x2_ticker_concentration.csv",
    "2023_primary_replication_label.json",
    "2023_vs_2024_2026_comparison.csv",
    "replication_receipt.json",
    "replication_summary.md",
]
def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        vals = []
        for col in cols:
            value = row[col]
            if pd.isna(value):
                vals.append("")
            elif isinstance(value, float):
                vals.append(f"{value:.6f}")
            else:
                vals.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def verify_manifest(path: Path, manifest_name: str, strict: bool = True) -> dict[str, Any]:
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
    if strict:
        extras = sorted(set(actual) - set(expected))
        if extras:
            raise SystemExit(f"manifest_extra_file:{extras[0]}")
    return manifest


def safe_clean_output_dir(path: Path) -> None:
    if path.exists():
        resolved = path.resolve()
        if REPO_ROOT.resolve() not in resolved.parents and resolved != REPO_ROOT.resolve():
            raise SystemExit(f"refusing_to_clean_outside_repo:{resolved}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def assign_state(value: Any, p33: float, p67: float) -> str:
    value = safe_float(value)
    if value is None:
        return "metric_unavailable"
    if value <= p33:
        return "low"
    if value >= p67:
        return "high"
    return "middle"


def classify_cell(d_state: str, l_state: str) -> str:
    if d_state not in {"low", "middle", "high"} or l_state not in {"low", "middle", "high"}:
        return "state_unavailable"
    d_high = d_state == "high"
    l_high = l_state == "high"
    if d_high and l_high:
        return "A"
    if d_high and not l_high:
        return "B"
    if not d_high and l_high:
        return "C"
    return "D"


def rate(sub: pd.DataFrame, column: str) -> float | None:
    if sub.empty:
        return None
    return float(sub[column].map(boolish).mean())


def concentration(sub: pd.DataFrame) -> dict[str, Any]:
    if sub.empty:
        return {"unique_ticker_count": 0, "largest_single_ticker": "", "largest_single_ticker_share": None, "top_five_ticker_share": None}
    counts = sub["underlying_symbol"].value_counts()
    return {
        "unique_ticker_count": int(counts.size),
        "largest_single_ticker": str(counts.index[0]),
        "largest_single_ticker_share": float(counts.iloc[0] / len(sub)),
        "top_five_ticker_share": float(counts.head(5).sum() / len(sub)),
    }


def outcome_rates(sub: pd.DataFrame) -> dict[str, Any]:
    return {
        "complete_signal_count": int(len(sub)),
        "plus5_success_rate": rate(sub, "reached_plus_5pct_within_10_sessions"),
        "breakout_low_breach_rate": rate(sub, "breakout_day_low_breach_before_timeout"),
        "timeout_rate": rate(sub, "timeout_10_sessions_under_threshold"),
    }


def load_cutoff_inheritance(spec: dict[str, Any], dispersion_dir: Path) -> dict[str, Any]:
    cutoff_path = dispersion_dir / "realized_dispersion_state_cutoffs.csv"
    cutoffs = pd.read_csv(cutoff_path)
    drow = cutoffs[cutoffs["metric"] == spec["D_metric_name"]]
    lrow = cutoffs[cutoffs["metric"] == spec["L_metric_name"]]
    if drow.empty or lrow.empty:
        raise SystemExit("required_inherited_cutoff_missing")
    return {
        "threshold_source_run": repo_relative(dispersion_dir),
        "threshold_source_manifest_hash": file_sha256(dispersion_dir / "realized_dispersion_content_manifest.json"),
        "D_metric_name": spec["D_metric_name"],
        "D_high_cutoff_numeric": float(drow["p67"].iloc[0]),
        "D_low_cutoff_numeric": float(drow["p33"].iloc[0]),
        "L_metric_name": spec["L_metric_name"],
        "L_high_cutoff_numeric": float(lrow["p67"].iloc[0]),
        "L_low_cutoff_numeric": float(lrow["p33"].iloc[0]),
        "original_definition": str(drow["state_construction"].iloc[0]),
        "2023_application_definition": "apply inherited p33/p67 numeric cutoffs to 2023 decision-date D/L values without recomputing thresholds",
        "verification_status": "passed",
    }


def build_2023_state_daily(rs_dir: Path, spec: dict[str, Any], inheritance: dict[str, Any]) -> pd.DataFrame:
    input_root = rs_dir / "input" / "morita_baseline_2022warmup_2023_2026_v1"
    if not input_root.exists():
        raise SystemExit("rs_warmup_extended_input_missing")
    ohlcv, decision_dates, _meta = dispersion.load_ohlcv_and_schedule(input_root)
    dates = [d for d in decision_dates if spec["decision_start"] <= d <= spec["decision_end"]]
    rd_spec = dispersion.load_json(dispersion.SPEC_PATH)
    baskets = dispersion.build_baskets(ohlcv, rd_spec)
    daily_long = dispersion.compute_daily_panel(ohlcv, dates, baskets, rd_spec)
    state = dispersion.wide_daily_panel(daily_long)
    out = state[["date", spec["D_metric_name"], spec["L_metric_name"]]].copy()
    out["D_state"] = out[spec["D_metric_name"]].map(lambda value: assign_state(value, inheritance["D_low_cutoff_numeric"], inheritance["D_high_cutoff_numeric"]))
    out["L_state"] = out[spec["L_metric_name"]].map(lambda value: assign_state(value, inheritance["L_low_cutoff_numeric"], inheritance["L_high_cutoff_numeric"]))
    out["cell"] = out.apply(lambda row: classify_cell(str(row["D_state"]), str(row["L_state"])), axis=1)
    return out


def build_2023_signal_context(rs_dir: Path, state_daily: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_csv(rs_dir / "morita_2023_signal_panel.csv")
    panel["signal_decision_date"] = panel["signal_decision_date"].astype(str)
    start = spec["decision_start"]
    end = spec["decision_end"]
    in_window = panel[(panel["signal_decision_date"] >= start) & (panel["signal_decision_date"] <= end)].copy()
    state = state_daily.rename(columns={"date": "signal_decision_date"})
    state["signal_decision_date"] = state["signal_decision_date"].astype(str)
    merged = in_window.merge(state, on="signal_decision_date", how="left", validate="many_to_one")
    merged["D_state_available"] = merged["D_state"].isin(["low", "middle", "high"])
    merged["L_state_available"] = merged["L_state"].isin(["low", "middle", "high"])
    merged["combined_state_available"] = merged["cell"].isin(CELLS)
    primary = merged[
        (merged["signal_rank"] == spec["primary_rank"])
        & (merged["outcome_status"] == spec["complete_status"])
        & merged["D_state_available"]
        & merged["L_state_available"]
        & merged["combined_state_available"]
    ].copy()
    return merged, primary


def signal_reconciliation(all_rows: pd.DataFrame, primary: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"bucket": "all_2023_rs_warmup_signal_rows", "count": int(len(all_rows)), "primary_denominator": False},
        {"bucket": "primary_S_complete_state_available", "count": int(len(primary)), "primary_denominator": True},
        {"bucket": "excluded_non_S", "count": int((all_rows["signal_rank"] != spec["primary_rank"]).sum()), "primary_denominator": False},
        {"bucket": "excluded_collision", "count": int((all_rows["outcome_status"] == "ambiguous_intraday_order").sum()), "primary_denominator": False},
        {"bucket": "excluded_incomplete", "count": int((all_rows["outcome_status"] == "incomplete_horizon").sum()), "primary_denominator": False},
        {"bucket": "excluded_non_complete_other", "count": int((~all_rows["outcome_status"].isin([spec["complete_status"], "ambiguous_intraday_order", "incomplete_horizon"])).sum()), "primary_denominator": False},
        {"bucket": "excluded_unavailable_D", "count": int(((all_rows["signal_rank"] == spec["primary_rank"]) & (all_rows["outcome_status"] == spec["complete_status"]) & ~all_rows["D_state_available"]).sum()), "primary_denominator": False},
        {"bucket": "excluded_unavailable_L", "count": int(((all_rows["signal_rank"] == spec["primary_rank"]) & (all_rows["outcome_status"] == spec["complete_status"]) & ~all_rows["L_state_available"]).sum()), "primary_denominator": False},
        {"bucket": "excluded_unavailable_combined_state", "count": int(((all_rows["signal_rank"] == spec["primary_rank"]) & (all_rows["outcome_status"] == spec["complete_status"]) & ~all_rows["combined_state_available"]).sum()), "primary_denominator": False},
    ]
    return pd.DataFrame(rows)


def state_coverage(state_daily: pd.DataFrame, primary: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for scope, df in [("decision_dates", state_daily), ("primary_S_signals", primary)]:
        for col in ["D_state", "L_state", "cell"]:
            for state, count in df[col].value_counts(dropna=False).sort_index().items():
                rows.append({"scope": scope, "state_dimension": col, "state": str(state), "count": int(count)})
    rows.append({"scope": "lineage", "state_dimension": "metric_implementation", "state": repo_relative(Path(dispersion.__file__)), "count": 1})
    return pd.DataFrame(rows)


def cell_summary(primary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cell, desc in CELLS.items():
        sub = primary[primary["cell"] == cell]
        row = {"cell": cell, "cell_description": desc}
        row.update(outcome_rates(sub))
        row.update(concentration(sub))
        row["decision_date_min"] = "" if sub.empty else str(sub["signal_decision_date"].min())
        row["decision_date_max"] = "" if sub.empty else str(sub["signal_decision_date"].max())
        rows.append(row)
    return pd.DataFrame(rows)


def pooled_non_a(primary: pd.DataFrame) -> pd.DataFrame:
    return primary[primary["cell"].isin(["B", "C", "D"])]


def compare_cells(primary: pd.DataFrame, left: str, right: str, spec: dict[str, Any], scope: str = "2023") -> dict[str, Any]:
    left_df = primary[primary["cell"] == left]
    if right == "pooled_BCD":
        right_df = pooled_non_a(primary)
    else:
        right_df = primary[primary["cell"] == right]
    lr = outcome_rates(left_df)
    rr = outcome_rates(right_df)
    lc = concentration(left_df)
    rc = concentration(right_df)
    plus = difference_pp(lr["plus5_success_rate"], rr["plus5_success_rate"])
    breach = difference_pp(lr["breakout_low_breach_rate"], rr["breakout_low_breach_rate"])
    timeout = difference_pp(lr["timeout_rate"], rr["timeout_rate"])
    if right == "pooled_BCD":
        sample_ok = lr["complete_signal_count"] >= int(spec["primary_sample_gate_cell_a_min"]) and rr["complete_signal_count"] >= int(spec["primary_sample_gate_pooled_non_a_min"])
    else:
        sample_ok = lr["complete_signal_count"] >= int(spec["component_sample_gate_min_per_side"]) and rr["complete_signal_count"] >= int(spec["component_sample_gate_min_per_side"])
    concentration_flag = bool((lc["largest_single_ticker_share"] or 0) > float(spec["ticker_concentration_largest_share_max"]) or (rc["largest_single_ticker_share"] or 0) > float(spec["ticker_concentration_largest_share_max"]))
    return {
        "scope": scope,
        "comparison": f"{left}_vs_{right}",
        "left_side": left,
        "right_side": right,
        "left_complete_signal_count": lr["complete_signal_count"],
        "right_complete_signal_count": rr["complete_signal_count"],
        "plus5_difference_pp": plus,
        "breach_difference_pp": breach,
        "timeout_difference_pp": timeout,
        "directionally_adverse": bool(plus is not None and breach is not None and plus < 0 and breach > 0),
        "comparison_status": "eligible" if sample_ok else "insufficient_sample",
        "ticker_concentration_flag": concentration_flag,
        "left_largest_single_ticker_share": lc["largest_single_ticker_share"],
        "right_largest_single_ticker_share": rc["largest_single_ticker_share"],
        "left_top_five_ticker_share": lc["top_five_ticker_share"],
        "right_top_five_ticker_share": rc["top_five_ticker_share"],
    }


def difference_pp(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return (a - b) * 100.0


def required_comparisons(primary: pd.DataFrame, spec: dict[str, Any], scope: str = "2023") -> pd.DataFrame:
    rows = [compare_cells(primary, "A", right, spec, scope) for right in ["B", "C", "D", "pooled_BCD"]]
    return pd.DataFrame(rows)


def primary_label(comparisons: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    main = comparisons[comparisons["comparison"] == "A_vs_pooled_BCD"].iloc[0]
    plus = safe_float(main["plus5_difference_pp"])
    breach = safe_float(main["breach_difference_pp"])
    sample_ok = main["comparison_status"] == "eligible"
    concentration_flag = bool(main["ticker_concentration_flag"])
    adverse = bool(plus is not None and breach is not None and plus < 0 and breach > 0)
    if not sample_ok:
        label = "insufficient_2023_sample"
    elif adverse and not concentration_flag and plus <= float(spec["replicated_plus5_gate_pp"]) and breach >= float(spec["replicated_breach_gate_pp"]):
        label = "replicated_directionally_2023"
    elif adverse:
        label = "directionally_adverse_but_limited"
    else:
        label = "not_replicated_or_inconsistent"
    return {
        "primary_label": label,
        "primary_comparison": "A_vs_pooled_BCD",
        "sample_gate_passed": sample_ok,
        "ticker_concentration_flag": concentration_flag,
        "directionally_adverse": adverse,
        "plus5_difference_pp": plus,
        "breach_difference_pp": breach,
        "validation_type": spec["validation_type"],
        "thresholds_estimated_on_later_2024_2026_reference": True,
        "no_threshold_retuning": True,
        "no_live_rule_change": True,
        "not_predictive_out_of_sample_proof": True,
        "research_only": True,
    }


def prior_signal_context(spec: dict[str, Any]) -> pd.DataFrame:
    ctx = pd.read_csv(REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_signal_context_panel.csv")
    ctx = ctx[(ctx["scope"] == "broad_market_context") & (ctx["metric"].isin([spec["D_metric_name"], spec["L_metric_name"]]))].copy()
    ids = ["signal_id", "signal_decision_date", "entry_session", "underlying_symbol", "signal_rank", "theme", "outcome_status", "reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"]
    values = ctx.pivot(index=ids, columns="metric", values="metric_value").reset_index()
    states = ctx.pivot(index=ids, columns="metric", values="metric_state").reset_index()
    states = states.rename(columns={spec["D_metric_name"]: "D_state", spec["L_metric_name"]: "L_state"})
    values = values.rename(columns={spec["D_metric_name"]: spec["D_metric_name"], spec["L_metric_name"]: spec["L_metric_name"]})
    wide = values.merge(states[ids + ["D_state", "L_state"]], on=ids, how="left", validate="one_to_one")
    wide["cell"] = wide.apply(lambda row: classify_cell(str(row["D_state"]), str(row["L_state"])), axis=1)
    return wide[(wide["signal_rank"] == spec["primary_rank"]) & (wide["outcome_status"] == spec["complete_status"]) & wide["cell"].isin(CELLS)].copy()


def compact_period_row(period: str, primary: pd.DataFrame, comparisons: pd.DataFrame, label: str, threshold_source: str, interpretation: str) -> dict[str, Any]:
    cells = cell_summary(primary)
    a = cells[cells["cell"] == "A"].iloc[0]
    pooled = pooled_non_a(primary)
    pr = outcome_rates(pooled)
    pc = concentration(pooled)
    main = comparisons[comparisons["comparison"] == "A_vs_pooled_BCD"].iloc[0]
    return {
        "period": period,
        "threshold_source": threshold_source,
        "eligible_complete_S_count": int(len(primary)),
        "Cell_A_count": int(a["complete_signal_count"]),
        "pooled_non_A_count": int(len(pooled)),
        "Cell_A_plus5_rate": a["plus5_success_rate"],
        "pooled_non_A_plus5_rate": pr["plus5_success_rate"],
        "plus5_difference_pp": main["plus5_difference_pp"],
        "Cell_A_breach_rate": a["breakout_low_breach_rate"],
        "pooled_non_A_breach_rate": pr["breakout_low_breach_rate"],
        "breach_difference_pp": main["breach_difference_pp"],
        "timeout_difference_pp": main["timeout_difference_pp"],
        "ticker_concentration_flag": bool(main["ticker_concentration_flag"]) or bool((pc["largest_single_ticker_share"] or 0) > 0.30),
        "primary_label": label,
        "interpretation": interpretation,
    }


def comparison_table(primary_2023: pd.DataFrame, prior_primary: pd.DataFrame, label_2023: str, spec: dict[str, Any]) -> pd.DataFrame:
    threshold_source = "2024_2026_realized_dispersion_state_cutoffs"
    prior_comps = required_comparisons(prior_primary, spec, scope="2024_2026")
    prior_label = "existing_confirmation_reference"
    combined = pd.concat([primary_2023.assign(period_part="2023"), prior_primary.assign(period_part="2024_2026")], ignore_index=True)
    combined_comps = required_comparisons(combined, spec, scope="combined_2023_2026")
    rows = [
        compact_period_row("2023_frozen_threshold_replication", primary_2023, required_comparisons(primary_2023, spec), label_2023, threshold_source, "pre_2024_frozen_threshold_historical_replication"),
        compact_period_row("2024_2026_existing_confirmation_reference", prior_primary, prior_comps, prior_label, threshold_source, "existing_reference_not_overwritten"),
        compact_period_row("combined_2023_2026_descriptive_only", combined, combined_comps, "descriptive_only", threshold_source, "descriptive_only_not_validation"),
    ]
    return pd.DataFrame(rows)


def ticker_concentration_table(primary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cell in CELLS:
        sub = primary[primary["cell"] == cell]
        counts = sub["underlying_symbol"].value_counts().head(10)
        for ticker, count in counts.items():
            rows.append({"cell": cell, "ticker": ticker, "signal_count": int(count), "share": float(count / len(sub)) if len(sub) else None})
    return pd.DataFrame(rows, columns=["cell", "ticker", "signal_count", "share"])


def build_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for child in sorted(output_dir.rglob("*")):
        if child.is_file() and child.name != MANIFEST_NAME:
            files.append({"relative_path": child.relative_to(output_dir).as_posix(), "sha256": file_sha256(child), "bytes": child.stat().st_size})
    manifest = {"artifact_version": "morita_narrow_leadership_2023_frozen_replication_v2", "created_at_utc": iso_now(), "files": files, "content_set_hash": text_hash(json_dumps(files))}
    write_json(output_dir / MANIFEST_NAME, manifest)
    return manifest


def verify_run(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifest(output_dir, MANIFEST_NAME, strict=True)
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    missing = sorted(set(REQUIRED_OUTPUTS) - files)
    if missing:
        raise SystemExit(f"replication_manifest_missing_required_output:{missing[0]}")
    return {"status": "morita_narrow_leadership_2023_frozen_replication_v2_verified", "file_count": len(files), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME)}


def verify_inputs(spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Path]]:
    rs_dir = REPO_ROOT / spec["source_2023_rs_warmup_retest_dir"]
    nl_dir = REPO_ROOT / spec["source_2024_2026_narrow_leadership_dir"]
    disp_dir = REPO_ROOT / spec["source_realized_dispersion_dir"]
    checks = []
    verify_manifest(rs_dir, "rs_warmup_retest_content_manifest.json", strict=True)
    checks.append({"check": "2023_rs_warmup_retest_manifest", "status": "passed", "value": file_sha256(rs_dir / "rs_warmup_retest_content_manifest.json")})
    verify_manifest(nl_dir, "narrow_leadership_content_manifest.json", strict=True)
    checks.append({"check": "2024_2026_narrow_leadership_manifest", "status": "passed", "value": file_sha256(nl_dir / "narrow_leadership_content_manifest.json")})
    verify_manifest(disp_dir, "realized_dispersion_content_manifest.json", strict=True)
    checks.append({"check": "realized_dispersion_manifest", "status": "passed", "value": file_sha256(disp_dir / "realized_dispersion_content_manifest.json")})
    receipt = load_json(rs_dir / "retest_receipt.json")
    if int(receipt.get("2023_s_signal_count", -1)) < 1:
        raise SystemExit("2023_rs_warmup_retest_no_s_signals")
    checks.append({"check": "2023_rs_warmup_retest_s_signals", "status": "passed", "value": str(receipt.get("2023_s_signal_count"))})
    checks.append({"check": "metric_implementation_reused", "status": "passed", "value": repo_relative(Path(dispersion.__file__))})
    return pd.DataFrame(checks), receipt, {"rs": rs_dir, "nl": nl_dir, "disp": disp_dir}


def build_summary(receipt: dict[str, Any], cells: pd.DataFrame, comparisons: pd.DataFrame, label: dict[str, Any], compact: pd.DataFrame, recon: pd.DataFrame, inheritance: dict[str, Any]) -> str:
    lines = [
        "# Morita 2023 Narrow-Leadership Frozen-Threshold Replication v2",
        "",
        f"Status: `{receipt['status']}`",
        f"validation_type: `{receipt['validation_type']}`",
        f"primary_label: `{label['primary_label']}`",
        "",
        "## Inherited Thresholds",
        "",
        f"- D high cutoff `{inheritance['D_metric_name']}`: `{inheritance['D_high_cutoff_numeric']}`",
        f"- L high cutoff `{inheritance['L_metric_name']}`: `{inheritance['L_high_cutoff_numeric']}`",
        "",
        "## Reconciliation",
        md_table(recon),
        "",
        "## 2023 Cells",
        md_table(cells),
        "",
        "## Required Comparisons",
        md_table(comparisons),
        "",
        "## 2023 vs 2024-2026",
        md_table(compact),
        "",
        "No threshold retuning. No Bot/rank/universe rule change. No options analysis. No live filter, sizing, notification, or broker action.",
    ]
    return "\n".join(lines) + "\n"


def write_bundle(summary: str, output_dir: Path, label: dict[str, Any], compact: pd.DataFrame) -> None:
    lines = [
        "# ChatGPT Handoff: Morita 2023 Narrow-Leadership Frozen-Threshold Replication v2",
        "",
        "## Result",
        "",
        f"- Output directory: `{repo_relative(output_dir)}`",
        f"- Primary label: `{label['primary_label']}`",
        "",
        "## Compact Comparison",
        md_table(compact),
        "",
        "## Embedded Summary",
        "",
        summary,
    ]
    CHATGPT_BUNDLE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_run(output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    input_checks, rs_receipt, paths = verify_inputs(spec)
    inheritance = load_cutoff_inheritance(spec, paths["disp"])
    safe_clean_output_dir(output_dir)
    state_daily = build_2023_state_daily(paths["rs"], spec, inheritance)
    all_2023, primary_2023 = build_2023_signal_context(paths["rs"], state_daily, spec)
    recon = signal_reconciliation(all_2023, primary_2023, spec)
    state_cov = state_coverage(state_daily, primary_2023, spec)
    cells = cell_summary(primary_2023)
    comps = required_comparisons(primary_2023, spec)
    label = primary_label(comps, spec)
    prior_primary = prior_signal_context(spec)
    compact = comparison_table(primary_2023, prior_primary, label["primary_label"], spec)
    ticker_conc = ticker_concentration_table(primary_2023)
    lineage = {
        "git_head_at_run": git_head(),
        "source_2023_rs_warmup_retest_dir": repo_relative(paths["rs"]),
        "source_2023_rs_warmup_manifest_hash": file_sha256(paths["rs"] / "rs_warmup_retest_content_manifest.json"),
        "source_2024_2026_narrow_leadership_dir": repo_relative(paths["nl"]),
        "source_2024_2026_narrow_leadership_manifest_hash": file_sha256(paths["nl"] / "narrow_leadership_content_manifest.json"),
        "source_realized_dispersion_dir": repo_relative(paths["disp"]),
        "source_realized_dispersion_manifest_hash": file_sha256(paths["disp"] / "realized_dispersion_content_manifest.json"),
        "metric_implementation_module": repo_relative(Path(dispersion.__file__)),
        "metric_implementation_sha256": file_sha256(Path(dispersion.__file__)),
        "rs_warmup_retest_receipt": repo_relative(paths["rs"] / "retest_receipt.json"),
        "rs_warmup_retest_receipt_sha256": file_sha256(paths["rs"] / "retest_receipt.json"),
    }
    receipt = {
        "status": "morita_narrow_leadership_2023_frozen_replication_v2_completed",
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "validation_type": spec["validation_type"],
        "thresholds_estimated_on_later_2024_2026_reference": True,
        "no_threshold_retuning": True,
        "no_live_rule_change": True,
        "not_predictive_out_of_sample_proof": True,
        "research_only": True,
        "actionization_allowed": False,
        "primary_label": label["primary_label"],
        "primary_denominator_count": int(len(primary_2023)),
        "cell_A_count": int((primary_2023["cell"] == "A").sum()),
    }
    write_dataframe(output_dir / "input_verification.csv", input_checks)
    write_json(output_dir / "source_artifact_lineage.json", lineage)
    write_json(output_dir / "state_cutoff_inheritance.json", inheritance)
    write_dataframe(output_dir / "2023_state_coverage.csv", state_cov)
    write_dataframe(output_dir / "2023_signal_reconciliation.csv", recon)
    write_dataframe(output_dir / "2023_s_2x2_cell_coverage.csv", cells[["cell", "cell_description", "complete_signal_count", "unique_ticker_count", "largest_single_ticker", "largest_single_ticker_share", "top_five_ticker_share", "decision_date_min", "decision_date_max"]])
    write_dataframe(output_dir / "2023_s_2x2_outcome_summary.csv", cells)
    write_dataframe(output_dir / "2023_s_2x2_required_comparisons.csv", comps)
    write_dataframe(output_dir / "2023_s_2x2_ticker_concentration.csv", ticker_conc)
    write_json(output_dir / "2023_primary_replication_label.json", label)
    write_dataframe(output_dir / "2023_vs_2024_2026_comparison.csv", compact)
    write_json(output_dir / "replication_receipt.json", receipt)
    summary = build_summary(receipt, cells, comps, label, compact, recon, inheritance)
    (output_dir / "replication_summary.md").write_text(summary, encoding="utf-8")
    build_manifest(output_dir)
    verify_run(output_dir)
    write_bundle(summary, output_dir, label, compact)
    return {"status": receipt["status"], "output_dir": repo_relative(output_dir), "chatgpt_bundle": repo_relative(CHATGPT_BUNDLE), "primary_label": label["primary_label"], "manifest_hash": file_sha256(output_dir / MANIFEST_NAME)}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    if args.verify:
        print(json_dumps(verify_run(output_dir)))
        return 0
    print(json_dumps(build_run(output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
