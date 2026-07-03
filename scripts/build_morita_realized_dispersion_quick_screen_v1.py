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
SPEC_PATH = REPO_ROOT / "config" / "morita_realized_dispersion_v1" / "realized_dispersion_quick_screen_spec.json"
BASKET_PATH = REPO_ROOT / "config" / "morita_theme_breadth_v1" / "static_research_baskets_v1.json"
CHATGPT_BUNDLE = REPO_ROOT / "morita_realized_dispersion_quick_screen_chatgpt_bundle.md"
MANIFEST_NAME = "realized_dispersion_content_manifest.json"
BASKET_STATUS = "static_research_basket_proxy"
REQUIRED_OUTPUTS = [
    "realized_dispersion_daily_panel.csv",
    "realized_dispersion_signal_context_panel.csv",
    "realized_dispersion_state_cutoffs.csv",
    "realized_dispersion_outcome_summary.csv",
    "realized_dispersion_rank_summary.csv",
    "realized_dispersion_scope_coverage.csv",
    "realized_dispersion_concentration_diagnostics.csv",
    "realized_dispersion_receipt.json",
    "realized_dispersion_summary.md",
]
BASKET_PREFIX = {
    "broad_russell1000_local_proxy": "broad_russell1000",
    "semiconductor_core": "semiconductor",
    "ai_infrastructure_extended": "ai_infrastructure",
}
BASE_METRICS = [
    "cross_sectional_dispersion_20d",
    "pct_positive_return_20d",
    "eqw_realized_vol_20d",
    "realized_average_correlation_proxy_20d",
    "qqq_minus_eqw_return_20d",
]


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
    manifest = {"artifact_version": "morita_realized_dispersion_quick_screen_v1", "created_at_utc": iso_now(), "files": files, "content_set_hash": text_hash(json_dumps(files))}
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


def read_static_baskets() -> dict[str, list[str]]:
    config = load_json(BASKET_PATH)
    baskets = {}
    for name in ["semiconductor_core", "ai_infrastructure_extended"]:
        seen = set()
        members = []
        for item in config["baskets"][name]:
            ticker = str(item).strip().upper()
            if ticker and ticker not in seen:
                seen.add(ticker)
                members.append(ticker)
        baskets[name] = members
    return baskets


def verify_baseline_and_input_root(baseline_run_dir: Path) -> Path:
    verify_manifest(baseline_run_dir, "source_content_manifest.json")
    lineage = load_json(baseline_run_dir / "source_input_lineage.json")
    entries = [entry for entry in lineage.get("inputs", []) if entry.get("required_for_signal_or_outcome")]
    if len(entries) != 1:
        raise SystemExit("baseline_lineage_invalid")
    input_root = REPO_ROOT / entries[0]["repository_relative_path_or_local_alias"]
    manifest = input_root / "source_manifest.json"
    if manifest.exists() and entries[0].get("sha256") and file_sha256(manifest) != entries[0]["sha256"]:
        raise SystemExit("baseline_input_manifest_hash_mismatch")
    return input_root


def load_baseline(baseline_run_dir: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    panel = pd.read_csv(baseline_run_dir / "morita_bot_baseline_panel.csv")
    required = {"signal_id", "signal_decision_date", "entry_session", "underlying_symbol", "signal_rank", "theme", "outcome_status", "reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise SystemExit(f"baseline_missing_columns:{','.join(missing)}")
    panel["signal_decision_date"] = pd.to_datetime(panel["signal_decision_date"]).dt.strftime("%Y-%m-%d")
    panel["underlying_symbol"] = panel["underlying_symbol"].astype(str).str.upper()
    panel["signal_rank"] = panel["signal_rank"].astype(str)
    for col in ["reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"]:
        panel[col] = panel[col].map(lambda x: x if isinstance(x, bool) else str(x).lower() == "true")
    stats = {
        "total": int(len(panel)),
        "complete": int((panel["outcome_status"] == "complete").sum()),
        "collisions": int((panel["outcome_status"] == "ambiguous_intraday_order").sum()),
        "incomplete": int((panel["outcome_status"] == "incomplete_horizon").sum()),
    }
    return panel, stats


def load_ohlcv_and_schedule(input_root: Path) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    source_dir = input_root / "sources"
    ohlcv_path = source_dir / "daily_ohlcv_merged.csv"
    schedule_path = source_dir / "decision_schedule.csv"
    ohlcv = pd.read_csv(ohlcv_path, usecols=["date", "ticker", "close"])
    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    ohlcv["ticker"] = ohlcv["ticker"].astype(str).str.upper()
    ohlcv["close"] = pd.to_numeric(ohlcv["close"], errors="coerce")
    ohlcv = ohlcv.dropna(subset=["date", "ticker", "close"])
    schedule = pd.read_csv(schedule_path)
    decision_dates = pd.to_datetime(schedule["observation_date"]).dt.strftime("%Y-%m-%d").tolist()
    meta = {
        "input_root": repo_relative(input_root),
        "ohlcv_path": repo_relative(ohlcv_path),
        "decision_schedule_path": repo_relative(schedule_path),
        "ohlcv_sha256": file_sha256(ohlcv_path),
        "decision_schedule_sha256": file_sha256(schedule_path),
    }
    return ohlcv, decision_dates, meta


def build_baskets(ohlcv: pd.DataFrame, spec: dict[str, Any]) -> dict[str, list[str]]:
    static = read_static_baskets()
    all_tickers = sorted(set(ohlcv["ticker"].dropna()))
    excluded = set(spec["benchmark_exclusions"])
    broad = [ticker for ticker in all_tickers if ticker not in excluded]
    return {"broad_russell1000_local_proxy": broad, **static}


def annualized_std(series: pd.Series, window: int, annualization: int) -> pd.Series:
    return series.rolling(window, min_periods=window).std(ddof=0) * math.sqrt(annualization)


def corr_proxy(window_returns: pd.DataFrame) -> float | None:
    n = int(window_returns.shape[1])
    if n <= 1:
        return None
    eqw = window_returns.mean(axis=1)
    eqw_var = float(eqw.var(ddof=0))
    indiv_vars = window_returns.var(axis=0, ddof=0)
    mean_indiv_var = float(indiv_vars.mean())
    if mean_indiv_var <= 1e-12:
        return None
    value = (n * eqw_var - mean_indiv_var) / ((n - 1) * mean_indiv_var)
    if abs(value) <= 1e-12:
        value = 0.0
    return float(value)


def compute_basket_daily(close: pd.DataFrame, returns: pd.DataFrame, qqq_return_20d: pd.Series, basket: str, members: list[str], min_members: int, decision_dates: list[str], spec: dict[str, Any]) -> pd.DataFrame:
    window = int(spec["realized_window_sessions"])
    annualization = int(spec["annualization_sessions"])
    present = [member for member in members if member in close.columns]
    basket_returns = returns[present].copy() if present else pd.DataFrame(index=returns.index)
    basket_total_20d = close[present] / close[present].shift(window) - 1.0 if present else pd.DataFrame(index=close.index)
    eqw_return_1d = basket_returns.where(basket_returns.notna().sum(axis=1) >= min_members).mean(axis=1)
    eqw_vol = annualized_std(eqw_return_1d, window, annualization)
    rows = []
    for dt in pd.to_datetime(decision_dates):
        date_key = dt.strftime("%Y-%m-%d")
        if dt not in close.index:
            rows.append({"date": date_key, "basket": basket, "valid_member_count": 0, "coverage_status": "insufficient_basket_coverage"})
            continue
        total = basket_total_20d.loc[dt].dropna() if present else pd.Series(dtype=float)
        valid_count = int(len(total))
        coverage = valid_count >= min_members
        basket_eqw_return_20d = float(total.mean()) if coverage else None
        corr = None
        if coverage and dt in basket_returns.index:
            trailing = basket_returns.loc[:dt].tail(window).dropna(axis=1, how="any")
            trailing = trailing[[col for col in trailing.columns if col in total.index]]
            if len(trailing) == window and trailing.shape[1] >= min_members:
                corr = corr_proxy(trailing)
        qqq_20 = safe_float(qqq_return_20d.get(dt))
        qqq_minus = None if qqq_20 is None or basket_eqw_return_20d is None else qqq_20 - basket_eqw_return_20d
        rows.append(
            {
                "date": date_key,
                "basket": basket,
                "basket_membership_status": BASKET_STATUS,
                "static_or_local_member_count": len(members),
                "locally_available_member_count": len(present),
                "valid_member_count": valid_count,
                "minimum_valid_member_count": min_members,
                "coverage_status": "valid_basket_coverage" if coverage else "insufficient_basket_coverage",
                "cross_sectional_dispersion_20d": float(total.std(ddof=0)) if coverage else None,
                "pct_positive_return_20d": float((total > 0).mean()) if coverage else None,
                "eqw_realized_vol_20d": safe_float(eqw_vol.get(dt)) if coverage else None,
                "realized_average_correlation_proxy_20d": corr,
                "basket_eqw_return_20d": basket_eqw_return_20d,
                "qqq_return_20d": qqq_20,
                "qqq_minus_eqw_return_20d": qqq_minus,
                "correlation_proxy_status": "available" if corr is not None else "unavailable",
            }
        )
    return pd.DataFrame(rows)


def compute_daily_panel(ohlcv: pd.DataFrame, decision_dates: list[str], baskets: dict[str, list[str]], spec: dict[str, Any]) -> pd.DataFrame:
    close = ohlcv.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    if "QQQ" not in close.columns:
        raise SystemExit("qqq_missing_from_baseline_ohlcv")
    returns = close.pct_change()
    qqq_return_20d = close["QQQ"] / close["QQQ"].shift(int(spec["realized_window_sessions"])) - 1.0
    frames = []
    for basket, members in baskets.items():
        frames.append(compute_basket_daily(close, returns, qqq_return_20d, basket, members, int(spec["minimum_valid_members"][basket]), decision_dates, spec))
    return pd.concat(frames, ignore_index=True)


def metric_name(basket: str, base_metric: str) -> str:
    return f"{BASKET_PREFIX[basket]}_{base_metric}"


def wide_daily_panel(daily_long: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for _, row in daily_long.iterrows():
        date = row["date"]
        out = rows.setdefault(date, {"date": date})
        basket = row["basket"]
        for base in BASE_METRICS:
            out[metric_name(basket, base)] = row[base]
        out[f"{basket}_valid_member_count"] = row["valid_member_count"]
        out[f"{basket}_coverage_status"] = row["coverage_status"]
    return pd.DataFrame(rows.values()).sort_values("date")


def assign_states(daily_wide: pd.DataFrame, complete_dates: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = daily_wide.copy()
    cutoff_rows = []
    date_set = set(complete_dates)
    metrics = [col for col in daily.columns if any(col.endswith(base) for base in BASE_METRICS)]
    for metric in metrics:
        values = pd.to_numeric(daily.loc[daily["date"].isin(date_set), metric], errors="coerce").dropna()
        p33 = values.quantile(1 / 3) if not values.empty else pd.NA
        p67 = values.quantile(2 / 3) if not values.empty else pd.NA
        daily[f"{metric}_state"] = pd.to_numeric(daily[metric], errors="coerce").map(lambda v: assign_tercile(v, p33, p67))
        cutoff_rows.append({"metric": metric, "p33": p33, "p67": p67, "valid_complete_signal_date_count": int(len(values)), "state_construction": "unique_complete_signal_date_ex_post_terciles", "not_predictive_thresholds": True, "not_live_filters": True})
    return daily, pd.DataFrame(cutoff_rows)


def assign_tercile(value: Any, p33: Any, p67: Any) -> str:
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


def scope_specs(baskets: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [
        {"scope": "broad_market_context", "basket": "broad_russell1000_local_proxy", "symbols": None},
        {"scope": "semiconductor_context", "basket": "semiconductor_core", "symbols": set(baskets["semiconductor_core"])},
        {"scope": "ai_infrastructure_context", "basket": "ai_infrastructure_extended", "symbols": set(baskets["ai_infrastructure_extended"])},
    ]


def build_signal_context(baseline: pd.DataFrame, daily: pd.DataFrame, baskets: dict[str, list[str]]) -> pd.DataFrame:
    by_date = daily.set_index("date", drop=False)
    rows = []
    for spec in scope_specs(baskets):
        scoped = baseline.copy() if spec["symbols"] is None else baseline[baseline["underlying_symbol"].isin(spec["symbols"])].copy()
        basket = spec["basket"]
        metrics = [metric_name(basket, base) for base in BASE_METRICS]
        for _, sig in scoped.iterrows():
            date = sig["signal_decision_date"]
            if date not in by_date.index:
                continue
            day = by_date.loc[date]
            if isinstance(day, pd.DataFrame):
                day = day.iloc[0]
            for metric in metrics:
                rows.append(
                    {
                        "signal_id": sig["signal_id"],
                        "scope": spec["scope"],
                        "basket": basket,
                        "basket_membership_status": BASKET_STATUS,
                        "metric": metric,
                        "metric_value": day.get(metric, pd.NA),
                        "metric_state": day.get(f"{metric}_state", "metric_unavailable"),
                        "signal_decision_date": date,
                        "entry_session": sig["entry_session"],
                        "underlying_symbol": sig["underlying_symbol"],
                        "signal_rank": sig["signal_rank"],
                        "theme": sig.get("theme", ""),
                        "outcome_status": sig["outcome_status"],
                        "outcome_complete_status": "complete" if sig["outcome_status"] == "complete" else sig["outcome_status"],
                        "reached_plus_5pct_within_10_sessions": bool(sig["reached_plus_5pct_within_10_sessions"]),
                        "breakout_day_low_breach_before_timeout": bool(sig["breakout_day_low_breach_before_timeout"]),
                        "timeout_10_sessions_under_threshold": bool(sig["timeout_10_sessions_under_threshold"]),
                    }
                )
    return pd.DataFrame(rows)


def bool_rate(series: pd.Series) -> float | None:
    if len(series) == 0:
        return None
    return float(series.astype(bool).mean())


def largest_ticker_share(data: pd.DataFrame) -> tuple[float | None, str]:
    complete = data[data["outcome_status"] == "complete"]
    if complete.empty:
        return None, ""
    counts = complete["underlying_symbol"].value_counts()
    return float(counts.iloc[0] / len(complete)), str(counts.index[0])


def build_outcome_summary(context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in context.groupby(["scope", "basket", "metric", "metric_state"], dropna=False):
        scope, basket, metric, state = keys
        for rank in ["S", "A", "B", "ALL"]:
            data = group if rank == "ALL" else group[group["signal_rank"] == rank]
            complete = data[data["outcome_status"] == "complete"]
            share, ticker = largest_ticker_share(data)
            rows.append({"scope": scope, "basket": basket, "metric": metric, "metric_state": state, "rank": rank, "complete_signal_count": len(complete), "diagnostic_total_signal_count": len(data), "collision_signal_count": int((data["outcome_status"] == "ambiguous_intraday_order").sum()), "incomplete_signal_count": int((data["outcome_status"] == "incomplete_horizon").sum()), "plus5_success_rate": bool_rate(complete["reached_plus_5pct_within_10_sessions"]) if not complete.empty else None, "breakout_low_breach_rate": bool_rate(complete["breakout_day_low_breach_before_timeout"]) if not complete.empty else None, "timeout_rate": bool_rate(complete["timeout_10_sessions_under_threshold"]) if not complete.empty else None, "largest_single_ticker_share": share, "largest_single_ticker": ticker})
    return pd.DataFrame(rows)


def direction(row: pd.Series) -> str:
    plus5 = safe_float(row.get("plus5_success_rate_diff_pp"))
    breach = safe_float(row.get("breakout_low_breach_rate_diff_pp"))
    if plus5 is not None and plus5 >= 10:
        return "high_better"
    if breach is not None and breach <= -10:
        return "high_better"
    if plus5 is not None and plus5 <= -10:
        return "high_worse"
    if breach is not None and breach >= 10:
        return "high_worse"
    return "neutral"


def build_rank_summary(context: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    conc_rows = []
    min_n = int(spec["minimum_complete_signals_per_high_or_low_state"])
    conc_max = float(spec["concentration_guard_largest_ticker_share_max"])
    for keys, group in context.groupby(["scope", "basket", "metric"], dropna=False):
        scope, basket, metric = keys
        for rank in ["S", "A", "B", "ALL"]:
            data = group if rank == "ALL" else group[group["signal_rank"] == rank]
            high = data[data["metric_state"] == "high"]
            low = data[data["metric_state"] == "low"]
            high_c = high[high["outcome_status"] == "complete"]
            low_c = low[low["outcome_status"] == "complete"]
            hp = bool_rate(high_c["reached_plus_5pct_within_10_sessions"]) if not high_c.empty else None
            lp = bool_rate(low_c["reached_plus_5pct_within_10_sessions"]) if not low_c.empty else None
            hb = bool_rate(high_c["breakout_day_low_breach_before_timeout"]) if not high_c.empty else None
            lb = bool_rate(low_c["breakout_day_low_breach_before_timeout"]) if not low_c.empty else None
            ht = bool_rate(high_c["timeout_10_sessions_under_threshold"]) if not high_c.empty else None
            lt = bool_rate(low_c["timeout_10_sessions_under_threshold"]) if not low_c.empty else None
            plus_diff = None if hp is None or lp is None else (hp - lp) * 100
            breach_diff = None if hb is None or lb is None else (hb - lb) * 100
            timeout_diff = None if ht is None or lt is None else (ht - lt) * 100
            high_share, high_ticker = largest_ticker_share(high)
            low_share, low_ticker = largest_ticker_share(low)
            sample = "sufficient_sample" if len(high_c) >= min_n and len(low_c) >= min_n else "insufficient_sample"
            material = (plus_diff is not None and abs(plus_diff) >= 10) or (breach_diff is not None and abs(breach_diff) >= 10)
            conc_breach = any(s is not None and s > conc_max for s in [high_share, low_share])
            timeout_contradicts = timeout_diff is not None and abs(timeout_diff) >= 10 and material
            if sample == "insufficient_sample":
                label = "insufficient_sample"
            elif conc_breach or timeout_contradicts:
                label = "inconsistent_relationship"
            elif material:
                label = "potentially_material_relationship"
            else:
                label = "no_visible_relationship"
            row = {"scope": scope, "basket": basket, "metric": metric, "rank": rank, "high_complete_signal_count": len(high_c), "low_complete_signal_count": len(low_c), "plus5_success_rate_diff_pp": plus_diff, "breakout_low_breach_rate_diff_pp": breach_diff, "timeout_rate_diff_pp": timeout_diff, "largest_single_ticker_share_high": high_share, "largest_single_ticker_high": high_ticker, "largest_single_ticker_share_low": low_share, "largest_single_ticker_low": low_ticker, "comparison_status": sample, "relationship_direction": "", "relationship_label": label}
            row["relationship_direction"] = direction(pd.Series(row))
            rows.append(row)
            conc_rows.append({k: row[k] for k in ["scope", "basket", "metric", "rank", "high_complete_signal_count", "largest_single_ticker_share_high", "largest_single_ticker_high", "low_complete_signal_count", "largest_single_ticker_share_low", "largest_single_ticker_low"]})
    summary = apply_inconsistency(pd.DataFrame(rows))
    return summary, pd.DataFrame(conc_rows)


def apply_inconsistency(summary: pd.DataFrame) -> pd.DataFrame:
    summary = summary.copy()
    for (scope, rank), group in summary[(summary["rank"].isin(["S", "A", "B"])) & (summary["comparison_status"] == "sufficient_sample")].groupby(["scope", "rank"]):
        directions = set(group["relationship_direction"]) - {"neutral"}
        if "high_better" in directions and "high_worse" in directions:
            mask = (summary["scope"] == scope) & (summary["rank"] == rank) & (summary["comparison_status"] == "sufficient_sample")
            summary.loc[mask, "relationship_label"] = "inconsistent_relationship"
    return summary


def build_scope_coverage(context: pd.DataFrame) -> pd.DataFrame:
    base = context.drop_duplicates(["scope", "signal_id"])
    rows = []
    for keys, group in base.groupby(["scope", "basket"], dropna=False):
        scope, basket = keys
        for rank in ["S", "A", "B", "ALL"]:
            data = group if rank == "ALL" else group[group["signal_rank"] == rank]
            rows.append({"scope": scope, "basket": basket, "rank": rank, "total_signal_count": len(data), "complete_signal_count": int((data["outcome_status"] == "complete").sum()), "collision_signal_count": int((data["outcome_status"] == "ambiguous_intraday_order").sum()), "incomplete_signal_count": int((data["outcome_status"] == "incomplete_horizon").sum())})
    return pd.DataFrame(rows)


def basket_coverage(daily_long: pd.DataFrame, baskets: dict[str, list[str]]) -> dict[str, Any]:
    out = {}
    for basket, members in baskets.items():
        g = daily_long[daily_long["basket"] == basket]
        out[basket] = {"member_count": len(members), "median_valid_member_count": safe_float(g["valid_member_count"].median()) if not g.empty else None, "valid_coverage_days": int((g["coverage_status"] == "valid_basket_coverage").sum()) if not g.empty else 0, "total_days": int(len(g))}
    return out


def build_summary_md(receipt: dict[str, Any], rank_summary: pd.DataFrame, coverage: pd.DataFrame) -> str:
    lines = ["# Morita Realized Dispersion Quick Screen v1", "", f"Status: `{receipt['status']}`", f"Baseline run: `{receipt['baseline_run_id']}`", f"Baseline coverage: total `{receipt['baseline_total_rows']}`, complete `{receipt['baseline_complete_rows']}`, collisions `{receipt['baseline_collision_rows']}`, incomplete `{receipt['baseline_incomplete_rows']}`", "MAE status: `unavailable_from_baseline`", "", "## Basket Coverage"]
    for basket, info in receipt["basket_coverage"].items():
        lines.append(f"- `{basket}`: members `{info['member_count']}`, median valid `{fmt(info['median_valid_member_count'], 0)}`, valid days `{info['valid_coverage_days']}/{info['total_days']}`")
    lines.extend(["", "## Complete Signals by Scope/Rank"])
    for _, row in coverage[coverage["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank"]).iterrows():
        lines.append(f"- `{row['scope']}` rank `{row['rank']}`: complete `{row['complete_signal_count']}`, total `{row['total_signal_count']}`")
    lines.extend(["", "## High-vs-Low Labels"])
    for _, row in rank_summary[rank_summary["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank", "metric"]).iterrows():
        lines.append(f"- `{row['scope']}` rank `{row['rank']}` metric `{row['metric']}`: label `{row['relationship_label']}`, status `{row['comparison_status']}`, +5 diff `{fmt(row['plus5_success_rate_diff_pp'])}pp`, breach diff `{fmt(row['breakout_low_breach_rate_diff_pp'])}pp`, timeout diff `{fmt(row['timeout_rate_diff_pp'])}pp`")
    primary = rank_summary[rank_summary["rank"].isin(["S", "A", "B"])]
    material = primary[primary["relationship_label"] == "potentially_material_relationship"]
    inconsistent = primary[primary["relationship_label"] == "inconsistent_relationship"]
    decision = "freeze_dispersion_research_stop_adding_market_environment_layers" if material.empty or not inconsistent.empty else "candidate_for_deeper_implied_correlation_or_pit_phase"
    lines.extend(["", "## Triage Decision", "", f"`{decision}`", "", "Research only. No new data, no Bot change, no option/implied-correlation analysis, no optimization, no actionization."])
    return "\n".join(lines) + "\n"


def write_bundle(output_dir: Path, summary_md: str, receipt: dict[str, Any], rank_summary: pd.DataFrame, coverage: pd.DataFrame) -> None:
    lines = ["# ChatGPT Handoff: Morita Realized Dispersion Quick Screen v1", "", "## Objective", "", "Assess whether local realized dispersion, realized correlation proxy, participation, and QQQ-minus-equal-weight divergence have a large, directionally consistent descriptive relationship with Morita Bot outcomes.", "", "## Status", "", f"- Status: `{receipt['status']}`", f"- Baseline run: `{receipt['baseline_run_id']}`", f"- Baseline complete rows: `{receipt['baseline_complete_rows']}`", "", "## Scope Counts", "", "| Scope | Rank | Total | Complete | Collisions | Incomplete |", "|---|---:|---:|---:|---:|---:|"]
    for _, row in coverage[coverage["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank"]).iterrows():
        lines.append(f"| {row['scope']} | {row['rank']} | {row['total_signal_count']} | {row['complete_signal_count']} | {row['collision_signal_count']} | {row['incomplete_signal_count']} |")
    lines.extend(["", "## High-vs-Low Differences", "", "| Scope | Rank | Metric | High N | Low N | +5 Diff pp | Breach Diff pp | Timeout Diff pp | Label |", "|---|---:|---|---:|---:|---:|---:|---:|---|"])
    for _, row in rank_summary[rank_summary["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank", "metric"]).iterrows():
        lines.append(f"| {row['scope']} | {row['rank']} | {row['metric']} | {row['high_complete_signal_count']} | {row['low_complete_signal_count']} | {fmt(row['plus5_success_rate_diff_pp'])} | {fmt(row['breakout_low_breach_rate_diff_pp'])} | {fmt(row['timeout_rate_diff_pp'])} | {row['relationship_label']} |")
    lines.extend(["", "## Limitations", "", "- No raw OHLCV, signal rows, or return matrices included.", "- No new data.", "- No option/implied-correlation analysis.", "- No recommendation or live rule.", f"- Output directory: `{repo_relative(output_dir)}`", "", "## Embedded Summary", "", summary_md])
    CHATGPT_BUNDLE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_run(baseline_run_dir: Path, output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    input_root = verify_baseline_and_input_root(baseline_run_dir)
    baseline, stats = load_baseline(baseline_run_dir)
    ohlcv, decision_dates, input_meta = load_ohlcv_and_schedule(input_root)
    baskets = build_baskets(ohlcv, spec)
    daily_long = compute_daily_panel(ohlcv, decision_dates, baskets, spec)
    daily_wide = wide_daily_panel(daily_long)
    complete_dates = sorted(set(baseline.loc[baseline["outcome_status"] == "complete", "signal_decision_date"]))
    daily_wide, cutoffs = assign_states(daily_wide, complete_dates)
    context = build_signal_context(baseline, daily_wide, baskets)
    outcome = build_outcome_summary(context)
    rank_summary, concentration = build_rank_summary(context, spec)
    coverage = build_scope_coverage(context)
    safe_clean_output_dir(output_dir)
    write_dataframe(output_dir / "realized_dispersion_daily_panel.csv", daily_wide)
    write_dataframe(output_dir / "realized_dispersion_signal_context_panel.csv", context)
    write_dataframe(output_dir / "realized_dispersion_state_cutoffs.csv", cutoffs)
    write_dataframe(output_dir / "realized_dispersion_outcome_summary.csv", outcome)
    write_dataframe(output_dir / "realized_dispersion_rank_summary.csv", rank_summary)
    write_dataframe(output_dir / "realized_dispersion_scope_coverage.csv", coverage)
    write_dataframe(output_dir / "realized_dispersion_concentration_diagnostics.csv", concentration)
    receipt = {"artifact_version": "morita_realized_dispersion_quick_screen_v1", "status": "morita_realized_dispersion_quick_screen_completed", "created_at_utc": iso_now(), "repository_commit_sha": git_head(), "baseline_run_id": baseline_run_dir.name, "baseline_run_dir": repo_relative(baseline_run_dir), "baseline_source_content_manifest_sha256": file_sha256(baseline_run_dir / "source_content_manifest.json"), "baseline_total_rows": stats["total"], "baseline_complete_rows": stats["complete"], "baseline_collision_rows": stats["collisions"], "baseline_incomplete_rows": stats["incomplete"], "input_meta": input_meta, "basket_membership_status": BASKET_STATUS, "basket_coverage": basket_coverage(daily_long, baskets), "mae_status": "unavailable_from_baseline", "new_data_used": False, "bot_rerun_or_rule_change": False, "option_or_implied_correlation_analysis_performed": False, "parameter_optimization_performed": False, "actionization_allowed": False}
    write_json(output_dir / "realized_dispersion_receipt.json", receipt)
    summary_md = build_summary_md(receipt, rank_summary, coverage)
    (output_dir / "realized_dispersion_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir)
    verify_manifest(output_dir, MANIFEST_NAME)
    write_bundle(output_dir, summary_md, receipt, rank_summary, coverage)
    return {"status": receipt["status"], "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "chatgpt_bundle": repo_relative(CHATGPT_BUNDLE)}


def verify_run(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifest(output_dir, MANIFEST_NAME)
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    missing = sorted(set(REQUIRED_OUTPUTS) - files)
    if missing:
        raise SystemExit(f"realized_dispersion_manifest_missing_required_output:{missing[0]}")
    return {"status": "morita_realized_dispersion_quick_screen_verified", "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "file_count": len(files)}


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
