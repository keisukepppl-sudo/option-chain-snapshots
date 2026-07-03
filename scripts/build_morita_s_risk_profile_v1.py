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
SPEC_PATH = REPO_ROOT / "config" / "morita_s_risk_profile_v1" / "s_adverse_excursion_stop_gap_spec.json"
CHATGPT_BUNDLE = REPO_ROOT / "morita_s_risk_profile_chatgpt_bundle.md"
MANIFEST_NAME = "s_risk_content_manifest.json"
REQUIRED_OUTPUTS = [
    "s_risk_cohort_coverage.csv",
    "s_mae_distribution_summary.csv",
    "s_initial_stop_distance_summary.csv",
    "s_stop_overshoot_summary.csv",
    "s_gap_through_summary.csv",
    "s_post_breach_recovery_summary.csv",
    "s_risk_tail_episodes.csv",
    "s_risk_signal_context_panel.csv",
    "s_risk_receipt.json",
    "s_risk_summary.md",
]
BASELINE_REQUIRED_COLUMNS = {
    "signal_id",
    "signal_decision_date",
    "entry_session",
    "underlying_symbol",
    "signal_rank",
    "theme",
    "entry_price",
    "breakout_day_low",
    "outcome_status",
    "breakout_day_low_breach_before_timeout",
    "timeout_10_sessions_under_threshold",
    "reached_plus_5pct_within_10_sessions",
    "holding_sessions_at_exit_or_timeout",
    "exit_event_category",
    "outcome_observed_through_session",
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
    manifest = {"artifact_version": "morita_s_risk_profile_v1", "created_at_utc": iso_now(), "files": files, "content_set_hash": text_hash(json_dumps(files))}
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


def verify_baseline_and_input_root(baseline_run_dir: Path, spec: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    verify_manifest(baseline_run_dir, "source_content_manifest.json")
    receipt = load_json(baseline_run_dir / "baseline_receipt.json")
    if receipt.get("run_id") != spec["baseline_run_id"]:
        raise SystemExit("baseline_run_id_mismatch")
    lineage = load_json(baseline_run_dir / "source_input_lineage.json")
    entries = [entry for entry in lineage.get("inputs", []) if entry.get("required_for_signal_or_outcome")]
    if len(entries) != 1:
        raise SystemExit("baseline_lineage_invalid")
    input_root = REPO_ROOT / entries[0]["repository_relative_path_or_local_alias"]
    manifest = input_root / "source_manifest.json"
    if not manifest.exists():
        raise SystemExit("baseline_input_manifest_missing")
    if entries[0].get("sha256") and file_sha256(manifest) != entries[0]["sha256"]:
        raise SystemExit("baseline_input_manifest_hash_mismatch")
    return input_root, {"lineage_entry": entries[0], "source_input_lineage_sha256": file_sha256(baseline_run_dir / "source_input_lineage.json")}


def load_baseline(baseline_run_dir: Path) -> pd.DataFrame:
    panel = pd.read_csv(baseline_run_dir / "morita_bot_baseline_panel.csv")
    missing = sorted(BASELINE_REQUIRED_COLUMNS - set(panel.columns))
    if missing:
        raise SystemExit(f"baseline_schema_missing:{missing[0]}")
    panel["entry_session"] = pd.to_datetime(panel["entry_session"])
    panel["signal_decision_date"] = pd.to_datetime(panel["signal_decision_date"])
    panel["outcome_observed_through_session"] = pd.to_datetime(panel["outcome_observed_through_session"], errors="coerce")
    for col in ["entry_price", "breakout_day_low"]:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
    if panel[["entry_price", "breakout_day_low"]].isna().any().any():
        raise SystemExit("baseline_entry_or_stop_reference_missing")
    return panel


def load_ohlcv(input_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    ohlcv_path = input_root / "sources" / "daily_ohlcv_merged.csv"
    ohlcv = pd.read_csv(ohlcv_path, usecols=["date", "ticker", "open", "high", "low", "close"])
    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    ohlcv["ticker"] = ohlcv["ticker"].astype(str).str.upper()
    for col in ["open", "high", "low", "close"]:
        ohlcv[col] = pd.to_numeric(ohlcv[col], errors="coerce")
    ohlcv = ohlcv.dropna(subset=["date", "ticker", "high", "low", "close"]).sort_values(["ticker", "date"])
    return ohlcv, {"ohlcv_path": repo_relative(ohlcv_path), "ohlcv_sha256": file_sha256(ohlcv_path)}


def distribution(values: pd.Series, prefix: str, thresholds: list[float] | None = None) -> dict[str, Any]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    row: dict[str, Any] = {f"{prefix}_available_count": int(len(clean))}
    if clean.empty:
        for col in ["median", "mean", "p01", "p05", "p10", "p25", "p75", "p90", "p95", "minimum"]:
            row[f"{prefix}_{col}"] = None
    else:
        row.update(
            {
                f"{prefix}_median": float(clean.median()),
                f"{prefix}_mean": float(clean.mean()),
                f"{prefix}_p01": float(clean.quantile(0.01)),
                f"{prefix}_p05": float(clean.quantile(0.05)),
                f"{prefix}_p10": float(clean.quantile(0.10)),
                f"{prefix}_p25": float(clean.quantile(0.25)),
                f"{prefix}_p75": float(clean.quantile(0.75)),
                f"{prefix}_p90": float(clean.quantile(0.90)),
                f"{prefix}_p95": float(clean.quantile(0.95)),
                f"{prefix}_minimum": float(clean.min()),
            }
        )
    for threshold in thresholds or []:
        label = str(abs(int(round(threshold * 100)))).replace("-", "")
        row[f"{prefix}_share_lte_minus_{label}pct"] = float((clean <= threshold).mean()) if len(clean) else None
    return row


def window_rows(data: pd.DataFrame, start: pd.Timestamp, sessions: int) -> pd.DataFrame:
    return data[data["date"] >= start].head(sessions)


def build_signal_context(panel: pd.DataFrame, ohlcv: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    by_ticker = {ticker: group.reset_index(drop=True) for ticker, group in ohlcv.groupby("ticker", sort=False)}
    rows = []
    for _, sig in panel[panel["signal_rank"] == spec["primary_rank"]].iterrows():
        ticker = str(sig["underlying_symbol"]).upper()
        data = by_ticker.get(ticker, pd.DataFrame(columns=ohlcv.columns))
        post = data[data["date"] >= sig["entry_session"]].reset_index(drop=True)
        row: dict[str, Any] = {
            "signal_id": sig["signal_id"],
            "ticker": ticker,
            "signal_decision_date": sig["signal_decision_date"].strftime("%Y-%m-%d"),
            "baseline_entry_date": sig["entry_session"].strftime("%Y-%m-%d"),
            "entry_price": float(sig["entry_price"]),
            "stop_reference": float(sig["breakout_day_low"]),
            "rank": sig["signal_rank"],
            "theme": sig.get("theme", ""),
            "outcome_status": sig["outcome_status"],
            "baseline_terminal_class": sig["exit_event_category"],
            "reached_plus_5pct_within_10_sessions": boolish(sig["reached_plus_5pct_within_10_sessions"]),
            "breakout_day_low_breach_before_timeout": boolish(sig["breakout_day_low_breach_before_timeout"]),
            "timeout_10_sessions_under_threshold": boolish(sig["timeout_10_sessions_under_threshold"]),
            "initial_stop_distance": float(sig["breakout_day_low"]) / float(sig["entry_price"]) - 1.0,
            "ohlcv_available_from_entry": bool(len(post)),
        }
        for horizon in spec["fixed_horizon_sessions"]:
            win = post.head(int(horizon))
            if len(win) == int(horizon):
                row[f"fixed_horizon_min_low_{horizon}d"] = float(win["low"].min())
                row[f"fixed_horizon_mae_{horizon}d"] = float(win["low"].min()) / float(sig["entry_price"]) - 1.0
                row[f"fixed_horizon_{horizon}d_status"] = "descriptive_complete"
            else:
                row[f"fixed_horizon_min_low_{horizon}d"] = None
                row[f"fixed_horizon_mae_{horizon}d"] = None
                row[f"fixed_horizon_{horizon}d_status"] = "insufficient_horizon_coverage"
        terminal = sig["outcome_observed_through_session"]
        if pd.notna(terminal) and len(post) and terminal >= sig["entry_session"]:
            terminal_win = post[post["date"] <= terminal]
            if len(terminal_win):
                row["mae_until_baseline_terminal"] = float(terminal_win["low"].min()) / float(sig["entry_price"]) - 1.0
                row["mae_until_baseline_terminal_status"] = "descriptive_complete"
            else:
                row["mae_until_baseline_terminal"] = None
                row["mae_until_baseline_terminal_status"] = "unavailable_from_baseline_schema"
        else:
            row["mae_until_baseline_terminal"] = None
            row["mae_until_baseline_terminal_status"] = "unavailable_from_baseline_schema"
        breach = post[post["low"] <= float(sig["breakout_day_low"])].head(1)
        if boolish(sig["breakout_day_low_breach_before_timeout"]) and len(breach):
            b = breach.iloc[0]
            b_index = int(breach.index[0])
            row.update(
                {
                    "first_breach_status": "descriptive_complete",
                    "first_breach_date": b["date"].strftime("%Y-%m-%d"),
                    "first_breach_open": safe_float(b["open"]),
                    "first_breach_low": float(b["low"]),
                    "first_breach_close": float(b["close"]),
                    "first_breach_low_undershoot": float(b["low"]) / float(sig["breakout_day_low"]) - 1.0,
                    "first_breach_close_vs_stop": float(b["close"]) / float(sig["breakout_day_low"]) - 1.0,
                }
            )
            open_px = safe_float(b["open"])
            if open_px is None:
                row["gap_classification"] = "unknown_open_missing"
                row["gap_through_stop"] = None
                row["intraday_breach_without_open_gap"] = None
                row["gap_through_amount"] = None
                row["daily_open_fill_proxy_loss_from_entry"] = None
                row["stop_reference_fill_proxy_loss_from_entry"] = float(sig["breakout_day_low"]) / float(sig["entry_price"]) - 1.0
            elif open_px < float(sig["breakout_day_low"]):
                row["gap_classification"] = "gap_through_stop"
                row["gap_through_stop"] = True
                row["intraday_breach_without_open_gap"] = False
                row["gap_through_amount"] = open_px / float(sig["breakout_day_low"]) - 1.0
                row["daily_open_fill_proxy_loss_from_entry"] = open_px / float(sig["entry_price"]) - 1.0
                row["stop_reference_fill_proxy_loss_from_entry"] = float(sig["breakout_day_low"]) / float(sig["entry_price"]) - 1.0
            else:
                row["gap_classification"] = "intraday_breach_without_open_gap"
                row["gap_through_stop"] = False
                row["intraday_breach_without_open_gap"] = True
                row["gap_through_amount"] = None
                row["daily_open_fill_proxy_loss_from_entry"] = open_px / float(sig["entry_price"]) - 1.0
                row["stop_reference_fill_proxy_loss_from_entry"] = float(sig["breakout_day_low"]) / float(sig["entry_price"]) - 1.0
            for horizon in spec["post_breach_horizons"]:
                fwd = post.iloc[b_index : b_index + int(horizon)]
                col = f"post_breach_min_low_{horizon}d"
                if len(fwd) == int(horizon):
                    row[col] = float(fwd["low"].min()) / float(sig["breakout_day_low"]) - 1.0
                    row[f"{col}_status"] = "descriptive_complete"
                else:
                    row[col] = None
                    row[f"{col}_status"] = "insufficient_horizon_coverage"
            for horizon in spec["recovery_horizons"]:
                fwd = post.iloc[b_index + 1 : b_index + 1 + int(horizon)]
                complete = len(fwd) == int(horizon)
                suffix = f"{horizon}d"
                row[f"reclaim_stop_on_close_within_{suffix}"] = bool((fwd["close"] >= float(sig["breakout_day_low"])).any()) if complete else None
                row[f"reclaim_entry_on_close_within_{suffix}"] = bool((fwd["close"] >= float(sig["entry_price"])).any()) if complete else None
                row[f"reach_plus_5pct_from_entry_on_high_within_{suffix}_after_breach"] = bool((fwd["high"] >= float(sig["entry_price"]) * 1.05).any()) if complete else None
                row[f"recovery_{suffix}_status"] = "descriptive_complete" if complete else "insufficient_horizon_coverage"
        else:
            row["first_breach_status"] = "schema_unavailable" if boolish(sig["breakout_day_low_breach_before_timeout"]) else "not_stopped"
            for col in ["first_breach_date", "first_breach_open", "first_breach_low", "first_breach_close", "first_breach_low_undershoot", "first_breach_close_vs_stop", "gap_through_stop", "intraday_breach_without_open_gap", "gap_through_amount", "daily_open_fill_proxy_loss_from_entry", "stop_reference_fill_proxy_loss_from_entry"]:
                row[col] = None
            row["gap_classification"] = "not_stopped"
            for horizon in spec["post_breach_horizons"]:
                row[f"post_breach_min_low_{horizon}d"] = None
                row[f"post_breach_min_low_{horizon}d_status"] = "schema_unavailable"
            for horizon in spec["recovery_horizons"]:
                suffix = f"{horizon}d"
                row[f"reclaim_stop_on_close_within_{suffix}"] = None
                row[f"reclaim_entry_on_close_within_{suffix}"] = None
                row[f"reach_plus_5pct_from_entry_on_high_within_{suffix}_after_breach"] = None
                row[f"recovery_{suffix}_status"] = "schema_unavailable"
        rows.append(row)
    return pd.DataFrame(rows)


def cohort_mask(context: pd.DataFrame, cohort: str, spec: dict[str, Any]) -> pd.Series:
    complete = context["outcome_status"] == spec["complete_status"]
    if cohort == "primary_complete_S":
        return complete
    if cohort == "S_target":
        return complete & context["reached_plus_5pct_within_10_sessions"]
    if cohort == "S_stop":
        return complete & context["breakout_day_low_breach_before_timeout"]
    if cohort == "S_timeout":
        return complete & context["timeout_10_sessions_under_threshold"]
    if cohort == "diagnostic_collision_S":
        return context["outcome_status"] == spec["collision_status"]
    if cohort == "diagnostic_incomplete_S":
        return context["outcome_status"] == spec["incomplete_status"]
    raise ValueError(cohort)


def build_coverage(context: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for cohort in ["all_S", "primary_complete_S", "S_target", "S_stop", "S_timeout", "diagnostic_collision_S", "diagnostic_incomplete_S"]:
        mask = pd.Series([True] * len(context)) if cohort == "all_S" else cohort_mask(context, cohort, spec)
        sub = context[mask]
        row = {"cohort": cohort, "signal_count": int(len(sub)), "unique_ticker_count": int(sub["ticker"].nunique()) if len(sub) else 0}
        for horizon in spec["fixed_horizon_sessions"]:
            row[f"mae_{horizon}d_available_count"] = int(sub[f"fixed_horizon_mae_{horizon}d"].notna().sum())
        for horizon in spec["post_breach_horizons"]:
            row[f"post_breach_{horizon}d_available_count"] = int(sub[f"post_breach_min_low_{horizon}d"].notna().sum())
        for horizon in spec["recovery_horizons"]:
            row[f"recovery_{horizon}d_available_count"] = int((sub[f"recovery_{horizon}d_status"] == "descriptive_complete").sum())
        row["daily_open_gap_known_count"] = int(sub["gap_classification"].isin(["gap_through_stop", "intraday_breach_without_open_gap"]).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def build_mae_summary(context: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for cohort in ["primary_complete_S", "S_target", "S_stop", "S_timeout"]:
        sub = context[cohort_mask(context, cohort, spec)]
        for horizon in spec["fixed_horizon_sessions"]:
            row = {"cohort": cohort, "horizon_sessions": int(horizon), "metric": f"fixed_horizon_mae_{horizon}d", "risk_description_label": "descriptive_complete"}
            row.update(distribution(sub[f"fixed_horizon_mae_{horizon}d"], "mae", spec["mae_thresholds"]))
            rows.append(row)
    return pd.DataFrame(rows)


def build_stop_distance_summary(context: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    sub = context[cohort_mask(context, "primary_complete_S", spec)]
    row = {"cohort": "primary_complete_S", "metric": "initial_stop_distance", "risk_description_label": "descriptive_complete"}
    row.update(distribution(sub["initial_stop_distance"], "initial_stop_distance", spec["stop_distance_thresholds"]))
    return pd.DataFrame([row])


def build_stop_overshoot_summary(context: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    sub = context[cohort_mask(context, "S_stop", spec)]
    rows = []
    for metric in ["first_breach_low_undershoot", "post_breach_min_low_5d", "post_breach_min_low_10d"]:
        row = {"cohort": "S_stop", "metric": metric, "interpretation": "additional decline below the existing stop reference", "risk_description_label": "descriptive_complete"}
        row.update(distribution(sub[metric], "additional_decline_below_stop", spec["stop_overshoot_thresholds"]))
        rows.append(row)
    return pd.DataFrame(rows)


def build_gap_summary(context: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    sub = context[cohort_mask(context, "S_stop", spec)]
    known = sub[sub["gap_classification"].isin(["gap_through_stop", "intraday_breach_without_open_gap"])]
    gap = sub[sub["gap_classification"] == "gap_through_stop"]
    base = {
        "cohort": "S_stop",
        "valid_stopped_signal_count": int(len(sub)),
        "known_open_classification_count": int(len(known)),
        "gap_through_count": int(len(gap)),
        "intraday_without_open_gap_count": int((sub["gap_classification"] == "intraday_breach_without_open_gap").sum()),
        "unknown_open_missing_count": int((sub["gap_classification"] == "unknown_open_missing").sum()),
        "gap_through_rate": float(len(gap) / len(known)) if len(known) else None,
        "intraday_without_open_gap_rate": float((sub["gap_classification"] == "intraday_breach_without_open_gap").sum() / len(known)) if len(known) else None,
        "execution_label": spec["execution_label"],
    }
    for metric in ["gap_through_amount", "daily_open_fill_proxy_loss_from_entry", "stop_reference_fill_proxy_loss_from_entry"]:
        dist = distribution(gap[metric] if metric != "stop_reference_fill_proxy_loss_from_entry" else sub[metric], metric, [])
        base.update({k: v for k, v in dist.items() if k.endswith(("available_count", "median", "p75", "p90", "p95", "minimum"))})
    return pd.DataFrame([base])


def build_recovery_summary(context: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    sub = context[cohort_mask(context, "S_stop", spec)]
    rows = []
    for horizon in spec["recovery_horizons"]:
        suffix = f"{horizon}d"
        available = sub[sub[f"recovery_{suffix}_status"] == "descriptive_complete"]
        for metric in [f"reclaim_stop_on_close_within_{suffix}", f"reclaim_entry_on_close_within_{suffix}", f"reach_plus_5pct_from_entry_on_high_within_{suffix}_after_breach"]:
            vals = available[metric].dropna()
            rows.append({"cohort": "S_stop", "horizon_sessions_after_breach": int(horizon), "metric": metric, "available_count": int(len(vals)), "true_count": int(vals.sum()) if len(vals) else 0, "rate": float(vals.mean()) if len(vals) else None, "risk_description_label": "descriptive_complete" if len(vals) else "insufficient_horizon_coverage"})
    return pd.DataFrame(rows)


def build_tail_episodes(context: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("fixed_horizon_mae_10d", True),
        ("fixed_horizon_mae_20d", True),
        ("gap_through_amount", True),
        ("post_breach_min_low_10d", True),
    ]
    rows = []
    fields = ["ticker", "signal_decision_date", "baseline_entry_date", "entry_price", "stop_reference", "rank", "baseline_terminal_class", "first_breach_date", "gap_through_stop"]
    for metric, asc in specs:
        sub = context.dropna(subset=[metric]).sort_values([metric, "ticker", "signal_decision_date"], ascending=[asc, True, True]).head(20)
        for _, row in sub.iterrows():
            out = {field: row.get(field) for field in fields}
            out["tail_episode_type"] = metric
            out["relevant_risk_metric"] = metric
            out["relevant_risk_value"] = row[metric]
            rows.append(out)
    return pd.DataFrame(rows)


def frequency_word(rate: float | None) -> str:
    if rate is None:
        return "not estimable from this sample"
    if rate >= 0.25:
        return "common within this sample"
    if rate >= 0.05:
        return "uncommon within this sample"
    return "rare within this sample"


def build_summary_md(receipt: dict[str, Any], coverage: pd.DataFrame, mae: pd.DataFrame, stop_distance: pd.DataFrame, overshoot: pd.DataFrame, gap: pd.DataFrame, recovery: pd.DataFrame, tails: pd.DataFrame) -> str:
    lines = ["# Morita S Risk Profile v1", "", f"Status: `{receipt['status']}`", f"Baseline run: `{receipt['baseline_run_id']}`", f"Baseline source input lineage SHA: `{receipt['source_input_lineage_sha256']}`", "", "Daily OHLCV proxy only. Actual stop execution can differ materially because intraday order type, liquidity, spread, and sequence are unavailable.", "", "## Cohort Coverage"]
    lines.append(md_table(coverage))
    lines.extend(["", "## MAE Summary"])
    lines.append(md_table(mae))
    lines.extend(["", "## Initial Stop Distance"])
    lines.append(md_table(stop_distance))
    lines.extend(["", "## Stop Overshoot"])
    lines.append(md_table(overshoot))
    lines.extend(["", "## Gap Through"])
    lines.append(md_table(gap))
    lines.extend(["", "## Recovery After Breach"])
    lines.append(md_table(recovery))
    tail_names = ", ".join(tails["ticker"].dropna().astype(str).head(10).tolist()) if len(tails) else ""
    lines.extend(["", "## Tail Episode Sample", "", f"Representative tickers from derived tail table: `{tail_names}`", "", "No new data, no Bot rerun/rule change, no stop optimization, no option-P&L inference, no actionization."])
    return "\n".join(lines) + "\n"


def write_bundle(output_dir: Path, summary_md: str, receipt: dict[str, Any], tails: pd.DataFrame) -> None:
    sample = tails.head(10)
    lines = ["# ChatGPT Handoff: Morita S Risk Profile v1", "", "## Objective", "", "Characterize S-rank stock path adverse excursion, breakout-day-low stop overshoot, daily-open gap-through proxy risk, and post-breach recovery using only the verified formal baseline and its local OHLCV lineage.", "", "## Status", "", f"- Status: `{receipt['status']}`", f"- Baseline run: `{receipt['baseline_run_id']}`", f"- Output directory: `{repo_relative(output_dir)}`", "", "## Representative Tail Episodes", ""]
    lines.append(md_table(sample) if len(sample) else "No representative tail rows.")
    lines.extend(["", "## Limitations", "", "- Daily OHLCV execution proxies only.", "- No raw OHLCV included.", "- No Bot rerun or rule change.", "- No stop optimization.", "- No option-P&L inference.", "- No actionization.", "", "## Embedded Summary", "", summary_md])
    CHATGPT_BUNDLE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_run(baseline_run_dir: Path, output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    input_root, lineage_meta = verify_baseline_and_input_root(baseline_run_dir, spec)
    panel = load_baseline(baseline_run_dir)
    ohlcv, ohlcv_meta = load_ohlcv(input_root)
    context = build_signal_context(panel, ohlcv, spec)
    coverage = build_coverage(context, spec)
    mae = build_mae_summary(context, spec)
    stop_distance = build_stop_distance_summary(context, spec)
    overshoot = build_stop_overshoot_summary(context, spec)
    gap = build_gap_summary(context, spec)
    recovery = build_recovery_summary(context, spec)
    tails = build_tail_episodes(context)
    complete_s = context[cohort_mask(context, "primary_complete_S", spec)]
    minus20 = pd.to_numeric(complete_s["fixed_horizon_mae_20d"], errors="coerce").dropna()
    minus20_rate = float((minus20 <= -0.20).mean()) if len(minus20) else None
    receipt = {
        "status": "morita_s_risk_profile_completed",
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "baseline_run_id": spec["baseline_run_id"],
        "baseline_run_dir": repo_relative(baseline_run_dir),
        "source_input_lineage_sha256": lineage_meta["source_input_lineage_sha256"],
        "ohlcv_sha256": ohlcv_meta["ohlcv_sha256"],
        "entry_price_field_identity": spec["baseline_entry_price_field"],
        "stop_reference_field_identity": spec["baseline_stop_reference_field"],
        "baseline_total_rows": int(len(panel)),
        "s_total_rows": int(len(context)),
        "s_complete_rows": int((context["outcome_status"] == spec["complete_status"]).sum()),
        "s_collision_rows": int((context["outcome_status"] == spec["collision_status"]).sum()),
        "s_incomplete_rows": int((context["outcome_status"] == spec["incomplete_status"]).sum()),
        "stock_level_minus20_from_entry_20d_n": int(len(minus20)),
        "stock_level_minus20_from_entry_20d_rate": minus20_rate,
        "stock_level_minus20_from_entry_20d_frequency": frequency_word(minus20_rate),
        "percentile_method": spec["percentile_method"],
        "daily_bar_execution_proxy_only": True,
        "new_data_downloaded": False,
        "bot_rerun_or_rule_change": False,
        "stop_optimization_performed": False,
        "option_pnl_inference_performed": False,
        "actionization_allowed": False,
    }
    safe_clean_output_dir(output_dir)
    write_dataframe(output_dir / "s_risk_cohort_coverage.csv", coverage)
    write_dataframe(output_dir / "s_mae_distribution_summary.csv", mae)
    write_dataframe(output_dir / "s_initial_stop_distance_summary.csv", stop_distance)
    write_dataframe(output_dir / "s_stop_overshoot_summary.csv", overshoot)
    write_dataframe(output_dir / "s_gap_through_summary.csv", gap)
    write_dataframe(output_dir / "s_post_breach_recovery_summary.csv", recovery)
    write_dataframe(output_dir / "s_risk_tail_episodes.csv", tails)
    write_dataframe(output_dir / "s_risk_signal_context_panel.csv", context)
    write_json(output_dir / "s_risk_receipt.json", receipt)
    summary_md = build_summary_md(receipt, coverage, mae, stop_distance, overshoot, gap, recovery, tails)
    (output_dir / "s_risk_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir)
    write_bundle(output_dir, summary_md, receipt, tails)
    return {"status": receipt["status"], "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "chatgpt_bundle": repo_relative(CHATGPT_BUNDLE)}


def verify_run(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifest(output_dir, MANIFEST_NAME)
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    missing = sorted(set(REQUIRED_OUTPUTS) - files)
    if missing:
        raise SystemExit(f"s_risk_manifest_missing_required_output:{missing[0]}")
    return {"status": "morita_s_risk_profile_verified", "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "file_count": len(files)}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline-run-dir")
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
    if not args.baseline_run_dir:
        raise SystemExit("--baseline-run-dir is required with --run")
    baseline_run_dir = Path(args.baseline_run_dir)
    if not baseline_run_dir.is_absolute():
        baseline_run_dir = REPO_ROOT / baseline_run_dir
    print(json_dumps(build_run(baseline_run_dir, output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
