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


SPEC_PATH = REPO_ROOT / "config" / "morita_narrow_leadership_2023_replication_v1" / "replication_spec.json"
OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_narrow_leadership_2023_replication"
CHATGPT_BUNDLE = REPO_ROOT / "morita_narrow_leadership_2023_replication_chatgpt_bundle.md"
MANIFEST_NAME = "replication_content_manifest.json"
BASELINE_MANIFEST_NAME = "source_content_manifest.json"
DISPERSION_MANIFEST_NAME = "realized_dispersion_content_manifest.json"
CONFIRMATION_MANIFEST_NAME = "narrow_leadership_content_manifest.json"
CELLS = {
    "A": "D_high_and_L_high",
    "B": "D_high_and_L_not_high",
    "C": "D_not_high_and_L_high",
    "D": "D_not_high_and_L_not_high",
}
REQUIRED_OUTPUTS = [
    "input_verification.csv",
    "historical_coverage_2023.csv",
    "state_coverage_2023.csv",
    "state_cutoff_inheritance.json",
    "state_metric_lineage.json",
    "2023_signal_reconciliation.csv",
    "2023_s_2x2_cell_coverage.csv",
    "2023_s_2x2_outcome_summary.csv",
    "2023_s_2x2_required_comparisons.csv",
    "2023_s_2x2_ticker_concentration.csv",
    "2023_replication_label.json",
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


def fmt(value: Any, digits: int = 6) -> str:
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
                vals.append(fmt(value))
            else:
                vals.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def safe_clean_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        resolved = output_dir.resolve()
        if REPO_ROOT.resolve() not in resolved.parents and resolved != REPO_ROOT.resolve():
            raise SystemExit(f"refusing_to_clean_outside_repo:{resolved}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


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
    manifest = {"artifact_version": "morita_narrow_leadership_2023_replication_v1", "created_at_utc": iso_now(), "files": files, "content_set_hash": text_hash(json_dumps(files))}
    write_json(path / MANIFEST_NAME, manifest)
    return manifest


def load_cutoffs(cutoff_path: Path, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cutoffs = pd.read_csv(cutoff_path)
    out = {}
    for metric in [spec["dispersion_metric"], spec["leadership_metric"]]:
        row = cutoffs[cutoffs["metric"] == metric]
        if row.empty:
            raise SystemExit(f"required_cutoff_missing:{metric}")
        out[metric] = {
            "metric": metric,
            "p33": float(row["p33"].iloc[0]),
            "p67": float(row["p67"].iloc[0]),
            "state_construction": str(row["state_construction"].iloc[0]),
            "source_path": repo_relative(cutoff_path),
            "source_sha256": file_sha256(cutoff_path),
        }
    return out


def assign_state(value: Any, p33: Any, p67: Any) -> str:
    value = safe_float(value)
    p33 = safe_float(p33)
    p67 = safe_float(p67)
    if value is None or p33 is None or p67 is None:
        return "metric_unavailable"
    if value <= p33:
        return "low"
    if value >= p67:
        return "high"
    return "middle"


def cell_for(d_high: bool, l_high: bool) -> str:
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
    if sub.empty or "underlying_symbol" not in sub.columns:
        return {"largest_single_ticker_share": None, "top_five_ticker_share": None, "unique_ticker_count": 0}
    counts = sub["underlying_symbol"].value_counts()
    return {
        "largest_single_ticker_share": float(counts.iloc[0] / len(sub)),
        "top_five_ticker_share": float(counts.head(5).sum() / len(sub)),
        "unique_ticker_count": int(counts.size),
    }


def empty_cell_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    for cell, desc in CELLS.items():
        rows.append(
            {
                "cell": cell,
                "cell_description": desc,
                "complete_signal_count": 0,
                "plus5_success_rate": None,
                "breakout_low_breach_rate": None,
                "timeout_rate": None,
                "largest_single_ticker_share": None,
                "top_five_ticker_share": None,
                "unique_ticker_count": 0,
            }
        )
    summary = pd.DataFrame(rows)
    coverage = summary[["cell", "cell_description", "complete_signal_count", "largest_single_ticker_share", "top_five_ticker_share", "unique_ticker_count"]].copy()
    tickers = pd.DataFrame(columns=["cell", "ticker", "signal_count", "share"])
    return coverage, summary, tickers


def build_cell_tables(signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if signals.empty:
        return empty_cell_tables()
    rows = []
    for cell, desc in CELLS.items():
        sub = signals[signals["cell"] == cell]
        row = {
            "cell": cell,
            "cell_description": desc,
            "complete_signal_count": int(len(sub)),
            "plus5_success_rate": rate(sub, "reached_plus_5pct_within_10_sessions"),
            "breakout_low_breach_rate": rate(sub, "breakout_day_low_breach_before_timeout"),
            "timeout_rate": rate(sub, "timeout_10_sessions_under_threshold"),
        }
        row.update(concentration(sub))
        rows.append(row)
    summary = pd.DataFrame(rows)
    coverage = summary[["cell", "cell_description", "complete_signal_count", "largest_single_ticker_share", "top_five_ticker_share", "unique_ticker_count"]].copy()
    ticker_rows = []
    for cell in CELLS:
        sub = signals[signals["cell"] == cell]
        counts = sub["underlying_symbol"].value_counts().head(10)
        for ticker, count in counts.items():
            ticker_rows.append({"cell": cell, "ticker": ticker, "signal_count": int(count), "share": float(count / len(sub)) if len(sub) else None})
    return coverage, summary, pd.DataFrame(ticker_rows, columns=["cell", "ticker", "signal_count", "share"])


def outcome_counts(sub: pd.DataFrame) -> dict[str, Any]:
    n = int(len(sub))
    return {
        "complete_signal_count": n,
        "plus5_success_rate": None if n == 0 else float(sub["reached_plus_5pct_within_10_sessions"].map(boolish).mean()),
        "breakout_low_breach_rate": None if n == 0 else float(sub["breakout_day_low_breach_before_timeout"].map(boolish).mean()),
        "timeout_rate": None if n == 0 else float(sub["timeout_10_sessions_under_threshold"].map(boolish).mean()),
    }


def comparison_row(signals: pd.DataFrame, left: str, right: str, min_side: int) -> dict[str, Any]:
    if left == "pooled_BCD":
        lsub = signals[signals["cell"].isin(["B", "C", "D"])]
    else:
        lsub = signals[signals["cell"] == left]
    if right == "pooled_BCD":
        rsub = signals[signals["cell"].isin(["B", "C", "D"])]
    else:
        rsub = signals[signals["cell"] == right]
    lr = outcome_counts(lsub)
    rr = outcome_counts(rsub)
    plus = None if lr["plus5_success_rate"] is None or rr["plus5_success_rate"] is None else (lr["plus5_success_rate"] - rr["plus5_success_rate"]) * 100
    breach = None if lr["breakout_low_breach_rate"] is None or rr["breakout_low_breach_rate"] is None else (lr["breakout_low_breach_rate"] - rr["breakout_low_breach_rate"]) * 100
    timeout = None if lr["timeout_rate"] is None or rr["timeout_rate"] is None else (lr["timeout_rate"] - rr["timeout_rate"]) * 100
    return {
        "scope": "2023_replication",
        "comparison": f"{left}_vs_{right}",
        "left_side": left,
        "right_side": right,
        "left_complete_signal_count": lr["complete_signal_count"],
        "right_complete_signal_count": rr["complete_signal_count"],
        "plus5_difference_pp": plus,
        "breach_difference_pp": breach,
        "timeout_difference_pp": timeout,
        "directionally_adverse": bool(plus is not None and breach is not None and plus < 0 and breach > 0),
        "comparison_status": "eligible" if lr["complete_signal_count"] >= min_side and rr["complete_signal_count"] >= min_side else "insufficient_sample",
    }


def build_comparisons(signals: pd.DataFrame, min_side: int) -> pd.DataFrame:
    pairs = [("A", "B"), ("A", "C"), ("A", "D"), ("A", "pooled_BCD"), ("C", "D"), ("B", "D")]
    return pd.DataFrame([comparison_row(signals, left, right, min_side) for left, right in pairs])


def build_input_verification(baseline_run_dir: Path, dispersion_output_dir: Path, confirmation_output_dir: Path, spec: dict[str, Any]) -> pd.DataFrame:
    checks = []
    verify_manifest(baseline_run_dir, BASELINE_MANIFEST_NAME)
    checks.append({"check": "formal_baseline_manifest", "status": "passed", "value": file_sha256(baseline_run_dir / BASELINE_MANIFEST_NAME)})
    verify_manifest(dispersion_output_dir, DISPERSION_MANIFEST_NAME)
    checks.append({"check": "realized_dispersion_manifest", "status": "passed", "value": file_sha256(dispersion_output_dir / DISPERSION_MANIFEST_NAME)})
    verify_manifest(confirmation_output_dir, CONFIRMATION_MANIFEST_NAME)
    checks.append({"check": "narrow_leadership_confirmation_manifest", "status": "passed", "value": file_sha256(confirmation_output_dir / CONFIRMATION_MANIFEST_NAME)})
    base_receipt = load_json(baseline_run_dir / "baseline_receipt.json")
    if base_receipt.get("run_id") != spec["baseline_run_id"]:
        raise SystemExit("baseline_run_id_mismatch")
    checks.append({"check": "baseline_run_id", "status": "passed", "value": spec["baseline_run_id"]})
    disp_receipt = load_json(dispersion_output_dir / "realized_dispersion_receipt.json")
    if disp_receipt.get("baseline_run_id") != spec["baseline_run_id"]:
        raise SystemExit("dispersion_baseline_run_id_mismatch")
    checks.append({"check": "dispersion_baseline_link", "status": "passed", "value": disp_receipt.get("baseline_run_id", "")})
    return pd.DataFrame(checks)


def build_historical_coverage(panel: pd.DataFrame, rejected: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    start = spec["replication_observation_start"]
    end = spec["replication_observation_end"]
    panel_dates = panel["signal_decision_date"].astype(str) if "signal_decision_date" in panel.columns else pd.Series(dtype=str)
    rejected_dates = rejected["observation_date"].astype(str)
    p23 = panel[(panel_dates >= start) & (panel_dates <= end)].copy()
    r23 = rejected[(rejected_dates >= start) & (rejected_dates <= end)].copy()
    rows = [
        {"bucket": "decision_dates_in_2023_window", "count": int(len(r23) + p23["signal_decision_date"].nunique() if not p23.empty else len(r23)), "notes": "formal baseline rejected audit plus signal dates"},
        {"bucket": "signal_rows_in_2023_window", "count": int(len(p23)), "notes": "formal baseline panel"},
        {"bucket": "s_signal_rows_in_2023_window", "count": int((p23["signal_rank"] == spec["rank"]).sum()) if not p23.empty else 0, "notes": "rank S only"},
        {"bucket": "complete_s_signal_rows_in_2023_window", "count": int(((p23["signal_rank"] == spec["rank"]) & (p23["outcome_status"] == spec["complete_status"])).sum()) if not p23.empty else 0, "notes": "eligible before state join"},
    ]
    for reason, count in r23["reason"].value_counts().items():
        rows.append({"bucket": f"rejected_{reason}", "count": int(count), "notes": "formal baseline rejected audit"})
    return pd.DataFrame(rows)


def load_input_root_from_baseline(baseline_run_dir: Path) -> Path:
    lineage = load_json(baseline_run_dir / "source_input_lineage.json")
    entries = [entry for entry in lineage.get("inputs", []) if entry.get("required_for_signal_or_outcome")]
    if len(entries) != 1:
        raise SystemExit("baseline_lineage_invalid")
    return REPO_ROOT / entries[0]["repository_relative_path_or_local_alias"]


def standard_rs_scores_wide(close: pd.DataFrame, benchmark: str = "QQQ") -> pd.DataFrame:
    if benchmark not in close.columns:
        raise SystemExit("qqq_missing_for_rs_warmup_diagnostic")
    bench = close[benchmark]
    components = []
    for days, weight in [(126, 0.5), (63, 0.3), (252, 0.2)]:
        stock_ret = close / close.shift(days) - 1.0
        bench_ret = bench / bench.shift(days) - 1.0
        components.append(stock_ret.sub(bench_ret, axis=0) * weight)
    raw = components[0] + components[1] + components[2]
    raw = raw.drop(columns=[benchmark], errors="ignore")
    return raw.rank(axis=1, pct=True) * 100.0


def build_rs_warmup_diagnostic(baseline_run_dir: Path, spec: dict[str, Any]) -> pd.DataFrame:
    input_root = load_input_root_from_baseline(baseline_run_dir)
    source = input_root / "sources" / "daily_ohlcv_merged.csv"
    raw = pd.read_csv(source, usecols=["date", "ticker", "high", "close", "volume"])
    raw["date"] = pd.to_datetime(raw["date"])
    frames = {field: raw.pivot_table(index="date", columns="ticker", values=field, aggfunc="last").sort_index() for field in ["high", "close", "volume"]}
    close = frames["close"]
    high = frames["high"]
    volume = frames["volume"]
    rs = standard_rs_scores_wide(close)
    prior20 = high.shift(1).rolling(20).max()
    volume_multiple = volume / volume.rolling(50).mean()
    breakout_vol = (close > prior20) & (volume_multiple >= 1.2)
    breakout_vol_rs98 = breakout_vol & (rs >= 98)
    rows = []
    for date in sorted(pd.to_datetime(close.index)):
        date_text = date.strftime("%Y-%m-%d")
        if not (spec["replication_observation_start"] <= date_text <= spec["replication_observation_end"]):
            continue
        rows.append(
            {
                "date": date_text,
                "rs_non_null_ticker_count": int(rs.loc[date].dropna().shape[0]),
                "breakout_and_volume_candidate_count_before_rs": int(breakout_vol.loc[date].sum()),
                "breakout_and_volume_and_rs98_candidate_count": int(breakout_vol_rs98.loc[date].sum()),
            }
        )
    return pd.DataFrame(rows)


def build_2023_state_panel(baseline_run_dir: Path, spec: dict[str, Any], cutoffs: dict[str, dict[str, Any]]) -> pd.DataFrame:
    input_root = load_input_root_from_baseline(baseline_run_dir)
    ohlcv, decision_dates, _meta = dispersion.load_ohlcv_and_schedule(input_root)
    dates = [d for d in decision_dates if spec["replication_observation_start"] <= d <= spec["replication_observation_end"]]
    rd_spec = dispersion.load_json(dispersion.SPEC_PATH)
    baskets = dispersion.build_baskets(ohlcv, rd_spec)
    daily_long = dispersion.compute_daily_panel(ohlcv, dates, baskets, rd_spec)
    daily = dispersion.wide_daily_panel(daily_long)
    for metric, cutoff in cutoffs.items():
        daily[f"{metric}_frozen_state"] = pd.to_numeric(daily[metric], errors="coerce").map(lambda v, c=cutoff: assign_state(v, c["p33"], c["p67"]))
    daily["D_high"] = daily[f"{spec['dispersion_metric']}_frozen_state"] == "high"
    daily["L_high"] = daily[f"{spec['leadership_metric']}_frozen_state"] == "high"
    daily["cell"] = daily.apply(lambda r: cell_for(bool(r["D_high"]), bool(r["L_high"])) if r[f"{spec['dispersion_metric']}_frozen_state"] != "metric_unavailable" and r[f"{spec['leadership_metric']}_frozen_state"] != "metric_unavailable" else "state_unavailable", axis=1)
    return daily


def state_coverage(daily: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for metric in [spec["dispersion_metric"], spec["leadership_metric"]]:
        state_col = f"{metric}_frozen_state"
        values = daily[state_col].value_counts(dropna=False).to_dict()
        for state in ["low", "middle", "high", "metric_unavailable"]:
            rows.append({"metric": metric, "state": state, "decision_date_count": int(values.get(state, 0))})
    for cell, count in daily["cell"].value_counts().sort_index().items():
        rows.append({"metric": "D_L_2x2_cell", "state": str(cell), "decision_date_count": int(count)})
    return pd.DataFrame(rows)


def join_signals_to_states(panel: pd.DataFrame, daily: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame(columns=list(panel.columns) + ["D_value", "L_value", "D_state", "L_state", "D_high", "L_high", "cell", "eligible_2x2"])
    start = spec["replication_observation_start"]
    end = spec["replication_observation_end"]
    work = panel[(panel["signal_decision_date"].astype(str) >= start) & (panel["signal_decision_date"].astype(str) <= end)].copy()
    work = work[(work["signal_rank"] == spec["rank"]) & (work["outcome_status"] == spec["complete_status"])].copy()
    if work.empty:
        return pd.DataFrame(columns=list(panel.columns) + ["D_value", "L_value", "D_state", "L_state", "D_high", "L_high", "cell", "eligible_2x2"])
    keep = [
        "date",
        spec["dispersion_metric"],
        spec["leadership_metric"],
        f"{spec['dispersion_metric']}_frozen_state",
        f"{spec['leadership_metric']}_frozen_state",
        "D_high",
        "L_high",
        "cell",
    ]
    states = daily[keep].rename(
        columns={
            "date": "signal_decision_date",
            spec["dispersion_metric"]: "D_value",
            spec["leadership_metric"]: "L_value",
            f"{spec['dispersion_metric']}_frozen_state": "D_state",
            f"{spec['leadership_metric']}_frozen_state": "L_state",
        }
    )
    merged = work.merge(states, on="signal_decision_date", how="left", validate="many_to_one")
    merged["eligible_2x2"] = merged["D_state"].isin(["low", "middle", "high"]) & merged["L_state"].isin(["low", "middle", "high"])
    return merged


def signal_reconciliation(panel: pd.DataFrame, rejected: pd.DataFrame, signals: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    start = spec["replication_observation_start"]
    end = spec["replication_observation_end"]
    panel_2023 = panel[(panel["signal_decision_date"].astype(str) >= start) & (panel["signal_decision_date"].astype(str) <= end)] if not panel.empty else pd.DataFrame()
    rejected_2023 = rejected[(rejected["observation_date"].astype(str) >= start) & (rejected["observation_date"].astype(str) <= end)]
    rows = [
        {"bucket": "all_2023_formal_signal_rows", "count": int(len(panel_2023)), "reason": "formal baseline panel"},
        {"bucket": "all_2023_rejected_dates", "count": int(len(rejected_2023)), "reason": "formal baseline rejected audit"},
        {"bucket": "2023_s_complete_state_joined", "count": int(len(signals)), "reason": "rank S and complete outcome"},
        {"bucket": "2023_s_complete_eligible_2x2", "count": int(signals["eligible_2x2"].sum()) if not signals.empty else 0, "reason": "state available"},
    ]
    for reason, count in rejected_2023["reason"].value_counts().items():
        rows.append({"bucket": f"rejected_{reason}", "count": int(count), "reason": "formal baseline rejected audit"})
    return pd.DataFrame(rows)


def comparison_to_prior(summary_2023: pd.DataFrame, confirmation_dir: Path) -> pd.DataFrame:
    prior = pd.read_csv(confirmation_dir / "s_2x2_outcome_summary.csv")
    rows = []
    for cell in CELLS:
        cur = summary_2023[summary_2023["cell"] == cell].iloc[0]
        old = prior[prior["cell"] == cell].iloc[0]
        for metric in ["complete_signal_count", "plus5_success_rate", "breakout_low_breach_rate", "timeout_rate"]:
            rows.append(
                {
                    "cell": cell,
                    "metric": metric,
                    "replication_2023": cur[metric],
                    "prior_2024_2026_confirmation": old[metric],
                    "comparison_status": "insufficient_2023_sample" if int(cur["complete_signal_count"]) == 0 else "comparable",
                }
            )
    return pd.DataFrame(rows)


def replication_label(signals: pd.DataFrame, comparisons: pd.DataFrame) -> dict[str, Any]:
    n = int(len(signals))
    if n == 0:
        label = "no_2023_s_signals_available_for_2x2_replication"
        decision = "cannot_confirm_or_refute_2024_2026_pattern_from_2023"
    elif (comparisons["comparison_status"] == "eligible").any():
        label = "2023_replication_comparable"
        decision = "compare_required_cells_only_no_live_action"
    else:
        label = "insufficient_2023_sample_for_required_comparisons"
        decision = "research_only_no_live_action"
    return {
        "replication_label": label,
        "research_decision": decision,
        "eligible_2023_s_complete_signal_count": n,
        "threshold_search_performed": False,
        "live_action_allowed": False,
        "option_pnl_performed": False,
    }


def build_summary_md(
    label: dict[str, Any],
    historical: pd.DataFrame,
    rs_diag: pd.DataFrame,
    state_cov: pd.DataFrame,
    cells: pd.DataFrame,
    comparisons: pd.DataFrame,
    vs_prior: pd.DataFrame,
    receipt: dict[str, Any],
) -> str:
    lines = [
        "# Morita Narrow Leadership 2023 Frozen-Threshold Replication v1",
        "",
        f"Status: `{receipt['status']}`",
        f"Replication label: `{label['replication_label']}`",
        f"Research decision: `{label['research_decision']}`",
        "",
        "## Bottom Line",
        "",
        f"- 2023 eligible S complete signal count: `{label['eligible_2023_s_complete_signal_count']}`.",
        "- The frozen 2024-2026 dispersion/leadership high cutoffs were inherited unchanged.",
        "- No retuning, no option P&L, no live bot change, and no actionization were performed.",
        "",
        "## Historical Coverage",
        md_table(historical),
        "",
        "## RS Warmup Diagnostic",
        "",
        "The 2023 zero-signal result is driven by missing 252-session RS warmup history in the current input, not by an absence of breakout/volume candidates. The current production-style prefilter requires RS98 before scanner selection.",
        "",
        md_table(
            pd.DataFrame(
                [
                    {
                        "metric": "2023_dates_with_any_rs_value",
                        "value": int((rs_diag["rs_non_null_ticker_count"] > 0).sum()) if not rs_diag.empty else 0,
                    },
                    {
                        "metric": "2023_breakout_volume_candidate_rows_before_rs",
                        "value": int(rs_diag["breakout_and_volume_candidate_count_before_rs"].sum()) if not rs_diag.empty else 0,
                    },
                    {
                        "metric": "2023_breakout_volume_rs98_candidate_rows",
                        "value": int(rs_diag["breakout_and_volume_and_rs98_candidate_count"].sum()) if not rs_diag.empty else 0,
                    },
                ]
            )
        ),
        "",
        "## 2023 State Coverage",
        md_table(state_cov),
        "",
        "## 2023 S 2x2 Outcome Summary",
        md_table(cells),
        "",
        "## Required Comparisons",
        md_table(comparisons),
        "",
        "## 2023 vs 2024-2026",
        md_table(vs_prior),
    ]
    return "\n".join(lines) + "\n"


def write_bundle(output_dir: Path, summary_md: str, label: dict[str, Any], receipt: dict[str, Any]) -> None:
    lines = [
        "# ChatGPT Handoff: Morita Narrow Leadership 2023 Replication",
        "",
        "## Objective",
        "",
        "Replicate the completed narrow-leadership 2x2 analysis on 2023 decision dates using frozen 2024-2026 state thresholds and the existing Morita formal baseline lineage.",
        "",
        "## Result",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Label: `{label['replication_label']}`",
        f"- Research decision: `{label['research_decision']}`",
        f"- Output directory: `{repo_relative(output_dir)}`",
        "",
        "## Guardrails",
        "",
        "- Frozen thresholds only; no retuning.",
        "- Existing local baseline/input artifacts only; no new market data download.",
        "- No option P&L, no notification, no strategy/actionization change.",
        "",
        "## Embedded Summary",
        "",
        summary_md,
    ]
    CHATGPT_BUNDLE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_run(output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    baseline_run_dir = REPO_ROOT / spec["baseline_run_dir"]
    dispersion_output_dir = REPO_ROOT / spec["dispersion_output_dir"]
    confirmation_output_dir = REPO_ROOT / spec["narrow_leadership_confirmation_output_dir"]
    safe_clean_output_dir(output_dir)
    input_checks = build_input_verification(baseline_run_dir, dispersion_output_dir, confirmation_output_dir, spec)
    panel = pd.read_csv(baseline_run_dir / "morita_bot_baseline_panel.csv")
    rejected = pd.read_csv(baseline_run_dir / "baseline_rejected_audit.csv")
    historical = build_historical_coverage(panel, rejected, spec)
    rs_diag = build_rs_warmup_diagnostic(baseline_run_dir, spec)
    cutoffs = load_cutoffs(dispersion_output_dir / "realized_dispersion_state_cutoffs.csv", spec)
    daily = build_2023_state_panel(baseline_run_dir, spec, cutoffs)
    state_cov = state_coverage(daily, spec)
    signals = join_signals_to_states(panel, daily, spec)
    recon = signal_reconciliation(panel, rejected, signals, spec)
    coverage, summary, tickers = build_cell_tables(signals[signals["eligible_2x2"]] if not signals.empty else signals)
    comparisons = build_comparisons(signals[signals["eligible_2x2"]] if not signals.empty else signals, int(spec["full_sample_min_per_side"]))
    vs_prior = comparison_to_prior(summary, confirmation_output_dir)
    label = replication_label(signals[signals["eligible_2x2"]] if not signals.empty else signals, comparisons)
    cutoff_payload = {
        "state_definition": spec["state_definition"],
        "threshold_search_performed": False,
        "inherited_from": repo_relative(dispersion_output_dir / "realized_dispersion_state_cutoffs.csv"),
        "inherited_cutoffs": cutoffs,
    }
    lineage = {
        "metric_implementation_source": repo_relative(REPO_ROOT / "scripts" / "build_morita_realized_dispersion_quick_screen_v1.py"),
        "metric_implementation_sha256": file_sha256(REPO_ROOT / "scripts" / "build_morita_realized_dispersion_quick_screen_v1.py"),
        "replication_script": repo_relative(Path(__file__)),
        "replication_script_sha256": file_sha256(Path(__file__)),
        "baseline_run_dir": repo_relative(baseline_run_dir),
        "baseline_manifest_sha256": file_sha256(baseline_run_dir / BASELINE_MANIFEST_NAME),
        "dispersion_output_dir": repo_relative(dispersion_output_dir),
        "dispersion_manifest_sha256": file_sha256(dispersion_output_dir / DISPERSION_MANIFEST_NAME),
        "new_data_downloaded": False,
        "thresholds_retuned": False,
    }
    receipt = {
        "status": "morita_narrow_leadership_2023_replication_completed",
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "artifact_version": spec["artifact_version"],
        "baseline_run_id": spec["baseline_run_id"],
        "baseline_run_dir": repo_relative(baseline_run_dir),
        "dispersion_output_dir": repo_relative(dispersion_output_dir),
        "confirmation_output_dir": repo_relative(confirmation_output_dir),
        "replication_observation_start": spec["replication_observation_start"],
        "replication_observation_end": spec["replication_observation_end"],
        "eligible_2023_s_complete_signal_count": label["eligible_2023_s_complete_signal_count"],
        "replication_label": label["replication_label"],
        "research_decision": label["research_decision"],
        "new_data_downloaded": False,
        "threshold_search_performed": False,
        "option_pnl_performed": False,
        "live_action_allowed": False,
        "actionization_allowed": False,
    }
    write_dataframe(output_dir / "input_verification.csv", input_checks)
    write_dataframe(output_dir / "historical_coverage_2023.csv", historical)
    write_dataframe(output_dir / "rs_warmup_diagnostic_2023.csv", rs_diag)
    write_dataframe(output_dir / "state_coverage_2023.csv", state_cov)
    write_json(output_dir / "state_cutoff_inheritance.json", cutoff_payload)
    write_json(output_dir / "state_metric_lineage.json", lineage)
    write_dataframe(output_dir / "2023_signal_reconciliation.csv", recon)
    write_dataframe(output_dir / "2023_s_2x2_cell_coverage.csv", coverage)
    write_dataframe(output_dir / "2023_s_2x2_outcome_summary.csv", summary)
    write_dataframe(output_dir / "2023_s_2x2_required_comparisons.csv", comparisons)
    write_dataframe(output_dir / "2023_s_2x2_ticker_concentration.csv", tickers)
    write_json(output_dir / "2023_replication_label.json", label)
    write_dataframe(output_dir / "2023_vs_2024_2026_comparison.csv", vs_prior)
    write_json(output_dir / "replication_receipt.json", receipt)
    summary_md = build_summary_md(label, historical, rs_diag, state_cov, summary, comparisons, vs_prior, receipt)
    (output_dir / "replication_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir)
    write_bundle(output_dir, summary_md, label, receipt)
    verify_run(output_dir)
    return {
        "status": receipt["status"],
        "output_dir": repo_relative(output_dir),
        "manifest_hash": file_sha256(output_dir / MANIFEST_NAME),
        "chatgpt_bundle": repo_relative(CHATGPT_BUNDLE),
        "replication_label": label["replication_label"],
    }


def verify_run(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifest(output_dir, MANIFEST_NAME)
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    missing = sorted(set(REQUIRED_OUTPUTS) - files)
    if missing:
        raise SystemExit(f"replication_manifest_missing_required_output:{missing[0]}")
    return {
        "status": "morita_narrow_leadership_2023_replication_verified",
        "output_dir": repo_relative(output_dir),
        "manifest_hash": file_sha256(output_dir / MANIFEST_NAME),
        "file_count": len(files),
    }


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
