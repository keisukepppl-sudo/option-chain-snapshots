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
CONFIG_DIR = REPO_ROOT / "config" / "morita_theme_breadth_v1"
BASKET_CONFIG = CONFIG_DIR / "static_research_baskets_v1.json"
SPEC_CONFIG = CONFIG_DIR / "breadth_quick_screen_spec.json"
CHATGPT_BUNDLE = REPO_ROOT / "morita_theme_breadth_quick_screen_chatgpt_bundle.md"
MANIFEST_NAME = "breadth_content_manifest.json"
BASKET_STATUS = "static_research_basket_proxy"
METRICS = [
    "pct_above_20d_ma",
    "pct_above_50d_ma",
    "pct_at_65d_high",
    "median_return_20d",
    "cross_sectional_dispersion_20d",
]
RATE_METRICS = {"pct_above_20d_ma", "pct_above_50d_ma", "pct_at_65d_high", "median_return_20d"}
DISPERSION_METRIC = "cross_sectional_dispersion_20d"
PRIMARY_SCOPES = {"semiconductor_signals", "ai_infrastructure_signals"}
SECONDARY_SCOPES = {"all_signals_semiconductor_core", "all_signals_ai_infrastructure_extended"}
REQUIRED_OUTPUTS = [
    "breadth_daily_panel.csv",
    "breadth_signal_context_panel.csv",
    "breadth_state_cutoffs.csv",
    "breadth_outcome_summary.csv",
    "breadth_rank_summary.csv",
    "breadth_scope_coverage.csv",
    "breadth_concentration_diagnostics.csv",
    "breadth_receipt.json",
    "breadth_summary.md",
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
        if value is None:
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception:
        return None


def fmt_number(value: Any, digits: int = 6) -> str:
    value = safe_float(value)
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def bool_rate(series: pd.Series) -> float | None:
    if len(series) == 0:
        return None
    return float(series.astype(bool).mean())


def read_baskets() -> dict[str, list[str]]:
    config = load_json(BASKET_CONFIG)
    baskets: dict[str, list[str]] = {}
    for name, members in config["baskets"].items():
        seen: set[str] = set()
        clean: list[str] = []
        for member in members:
            ticker = str(member).strip().upper()
            if ticker and ticker not in seen:
                seen.add(ticker)
                clean.append(ticker)
        baskets[name] = clean
    return baskets


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


def build_manifest(path: Path, manifest_name: str = MANIFEST_NAME) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and child.name != manifest_name:
            files.append(
                {
                    "relative_path": child.relative_to(path).as_posix(),
                    "sha256": file_sha256(child),
                    "bytes": child.stat().st_size,
                }
            )
    manifest = {
        "artifact_version": "morita_theme_breadth_quick_screen_v1",
        "created_at_utc": iso_now(),
        "files": files,
        "content_set_hash": text_hash(json_dumps(files)),
    }
    write_json(path / manifest_name, manifest)
    return manifest


def resolve_baseline_input_root(baseline_run_dir: Path) -> Path:
    verify_manifest(baseline_run_dir, "source_content_manifest.json")
    lineage = load_json(baseline_run_dir / "source_input_lineage.json")
    entries = [entry for entry in lineage.get("inputs", []) if entry.get("required_for_signal_or_outcome")]
    if len(entries) != 1:
        raise SystemExit("baseline_lineage_invalid:expected_one_required_input")
    rel = entries[0].get("repository_relative_path_or_local_alias")
    if not rel:
        raise SystemExit("baseline_lineage_invalid:missing_input_path")
    input_root = (REPO_ROOT / rel).resolve()
    if not input_root.exists():
        raise SystemExit(f"baseline_input_missing:{rel}")
    manifest = input_root / "source_manifest.json"
    if manifest.exists() and entries[0].get("sha256") and file_sha256(manifest) != entries[0]["sha256"]:
        raise SystemExit("baseline_input_manifest_hash_mismatch")
    return input_root


def load_baseline_panels(baseline_run_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    panel_path = baseline_run_dir / "morita_bot_baseline_panel.csv"
    if not panel_path.exists():
        raise SystemExit("baseline_panel_missing")
    panel = pd.read_csv(panel_path)
    required = {
        "signal_id",
        "signal_decision_date",
        "entry_session",
        "underlying_symbol",
        "signal_rank",
        "theme",
        "outcome_status",
        "breakout_day_low_breach_before_timeout",
        "timeout_10_sessions_under_threshold",
        "reached_plus_5pct_within_10_sessions",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise SystemExit(f"baseline_panel_missing_columns:{','.join(missing)}")
    panel["signal_decision_date"] = pd.to_datetime(panel["signal_decision_date"]).dt.strftime("%Y-%m-%d")
    panel["underlying_symbol"] = panel["underlying_symbol"].astype(str).str.upper()
    panel["signal_rank"] = panel["signal_rank"].astype(str)
    bool_cols = [
        "breakout_day_low_breach_before_timeout",
        "timeout_10_sessions_under_threshold",
        "reached_plus_5pct_within_10_sessions",
    ]
    for col in bool_cols:
        panel[col] = panel[col].map(lambda x: str(x).strip().lower() == "true" if not isinstance(x, bool) else x)
    stats = {
        "total_rows": int(len(panel)),
        "complete_rows": int((panel["outcome_status"] == "complete").sum()),
        "collision_rows": int((panel["outcome_status"] == "ambiguous_intraday_order").sum()),
        "incomplete_rows": int((panel["outcome_status"] == "incomplete_horizon").sum()),
        "mae_available": "maximum_adverse_excursion_10_sessions" in panel.columns,
    }
    if not stats["mae_available"]:
        panel["maximum_adverse_excursion_10_sessions"] = pd.NA
    return panel, stats


def load_input_data(input_root: Path) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    source_dir = input_root / "sources"
    ohlcv_path = source_dir / "daily_ohlcv_merged.csv"
    schedule_path = source_dir / "decision_schedule.csv"
    if not ohlcv_path.exists() or not schedule_path.exists():
        raise SystemExit("baseline_input_missing_required_sources")
    ohlcv = pd.read_csv(ohlcv_path)
    schedule = pd.read_csv(schedule_path)
    for col in ["date", "ticker", "close"]:
        if col not in ohlcv.columns:
            raise SystemExit(f"ohlcv_missing_column:{col}")
    if "observation_date" not in schedule.columns:
        raise SystemExit("decision_schedule_missing_observation_date")
    ohlcv = ohlcv[["date", "ticker", "close"]].copy()
    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    ohlcv["ticker"] = ohlcv["ticker"].astype(str).str.upper()
    ohlcv["close"] = pd.to_numeric(ohlcv["close"], errors="coerce")
    ohlcv = ohlcv.dropna(subset=["date", "ticker", "close"])
    decision_dates = pd.to_datetime(schedule["observation_date"]).dt.strftime("%Y-%m-%d").tolist()
    meta = {
        "ohlcv_path": repo_relative(ohlcv_path),
        "decision_schedule_path": repo_relative(schedule_path),
        "ohlcv_sha256": file_sha256(ohlcv_path),
        "decision_schedule_sha256": file_sha256(schedule_path),
        "decision_date_count": len(decision_dates),
    }
    return ohlcv, decision_dates, meta


def compute_daily_breadth(
    ohlcv: pd.DataFrame,
    decision_dates: list[str],
    baskets: dict[str, list[str]],
    min_valid_member_count: int,
) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    ohlcv["ticker"] = ohlcv["ticker"].astype(str).str.upper()
    ohlcv["close"] = pd.to_numeric(ohlcv["close"], errors="coerce")
    ohlcv = ohlcv.dropna(subset=["date", "ticker", "close"])
    rows: list[dict[str, Any]] = []
    for basket_name, members in baskets.items():
        sub = ohlcv[ohlcv["ticker"].isin(members)].copy()
        close = sub.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
        close = close.reindex(sorted(close.index.unique()))
        sma20 = close.rolling(20, min_periods=20).mean()
        sma50 = close.rolling(50, min_periods=50).mean()
        high65 = close.rolling(65, min_periods=65).max()
        ret20 = close / close.shift(20) - 1.0
        date_index = pd.to_datetime(decision_dates)
        for dt in date_index:
            date_key = dt.strftime("%Y-%m-%d")
            if dt not in close.index:
                rows.append(
                    {
                        "date": date_key,
                        "basket": basket_name,
                        "basket_membership_status": BASKET_STATUS,
                        "basket_static_member_count": len(members),
                        "valid_member_count": 0,
                        "breadth_status": "insufficient_basket_coverage",
                    }
                )
                continue
            close_row = close.loc[dt]
            sma20_row = sma20.loc[dt]
            sma50_row = sma50.loc[dt]
            high65_row = high65.loc[dt]
            ret20_row = ret20.loc[dt]
            valid20 = close_row.notna() & sma20_row.notna()
            valid50 = close_row.notna() & sma50_row.notna()
            valid65 = close_row.notna() & high65_row.notna()
            validret = ret20_row.notna()
            count20 = int(valid20.sum())
            count50 = int(valid50.sum())
            count65 = int(valid65.sum())
            countret = int(validret.sum())
            min_count = min(count20, count50, count65, countret)
            row = {
                "date": date_key,
                "basket": basket_name,
                "basket_membership_status": BASKET_STATUS,
                "basket_static_member_count": len(members),
                "valid_member_count": min_count,
                "pct_above_20d_ma_valid_member_count": count20,
                "pct_above_50d_ma_valid_member_count": count50,
                "pct_at_65d_high_valid_member_count": count65,
                "median_return_20d_valid_member_count": countret,
                "cross_sectional_dispersion_20d_valid_member_count": countret,
                "breadth_status": "valid_basket_coverage" if min_count >= min_valid_member_count else "insufficient_basket_coverage",
            }
            row["pct_above_20d_ma"] = float((close_row[valid20] > sma20_row[valid20]).mean()) if count20 else pd.NA
            row["pct_above_50d_ma"] = float((close_row[valid50] > sma50_row[valid50]).mean()) if count50 else pd.NA
            row["pct_at_65d_high"] = float((close_row[valid65] >= high65_row[valid65]).mean()) if count65 else pd.NA
            row["median_return_20d"] = float(ret20_row[validret].median()) if countret else pd.NA
            row["cross_sectional_dispersion_20d"] = float(ret20_row[validret].std(ddof=0)) if countret else pd.NA
            rows.append(row)
    return pd.DataFrame(rows)


def assign_states(daily: pd.DataFrame, min_valid_member_count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = daily.copy()
    cutoff_rows: list[dict[str, Any]] = []
    for basket in sorted(daily["basket"].unique()):
        mask_basket = daily["basket"] == basket
        for metric in METRICS:
            valid_count_col = f"{metric}_valid_member_count"
            mask = mask_basket & daily[metric].notna() & (pd.to_numeric(daily[valid_count_col], errors="coerce") >= min_valid_member_count)
            values = pd.to_numeric(daily.loc[mask, metric], errors="coerce").dropna()
            if values.empty:
                p25 = p75 = pd.NA
                valid_days = 0
            else:
                p25 = float(values.quantile(0.25))
                p75 = float(values.quantile(0.75))
                valid_days = int(len(values))
            state_col = f"{metric}_state"
            daily[state_col] = ""
            for idx in daily.loc[mask_basket].index:
                value = safe_float(daily.at[idx, metric])
                count = safe_float(daily.at[idx, valid_count_col])
                if value is None or count is None or count < min_valid_member_count or p25 is pd.NA:
                    daily.at[idx, state_col] = "insufficient_basket_coverage"
                elif metric == DISPERSION_METRIC:
                    if value <= float(p25):
                        daily.at[idx, state_col] = "low_dispersion"
                    elif value >= float(p75):
                        daily.at[idx, state_col] = "high_dispersion"
                    else:
                        daily.at[idx, state_col] = "middle_dispersion"
                else:
                    if value <= float(p25):
                        daily.at[idx, state_col] = "low"
                    elif value >= float(p75):
                        daily.at[idx, state_col] = "high"
                    else:
                        daily.at[idx, state_col] = "middle"
            cutoff_rows.append(
                {
                    "basket": basket,
                    "metric": metric,
                    "p25": p25,
                    "p75": p75,
                    "valid_decision_date_count": valid_days,
                    "state_policy": "low_middle_high_dispersion" if metric == DISPERSION_METRIC else "low_middle_high",
                    "label_status": "ex_post_descriptive_only;not_predictive_thresholds;not_live_filters",
                }
            )
    return daily, pd.DataFrame(cutoff_rows)


def scope_frames(panel: pd.DataFrame, baskets: dict[str, list[str]]) -> dict[tuple[str, str], pd.DataFrame]:
    semiconductor = set(baskets["semiconductor_core"])
    ai = set(baskets["ai_infrastructure_extended"])
    return {
        ("semiconductor_signals", "semiconductor_core"): panel[panel["underlying_symbol"].isin(semiconductor)].copy(),
        ("ai_infrastructure_signals", "ai_infrastructure_extended"): panel[panel["underlying_symbol"].isin(ai)].copy(),
        ("all_signals_semiconductor_core", "semiconductor_core"): panel.copy(),
        ("all_signals_ai_infrastructure_extended", "ai_infrastructure_extended"): panel.copy(),
    }


def build_signal_context(panel: pd.DataFrame, daily: pd.DataFrame, baskets: dict[str, list[str]]) -> pd.DataFrame:
    daily_by_key = daily.set_index(["basket", "date"], drop=False)
    rows: list[dict[str, Any]] = []
    for (scope, basket), scoped in scope_frames(panel, baskets).items():
        for _, signal in scoped.iterrows():
            key = (basket, signal["signal_decision_date"])
            if key not in daily_by_key.index:
                continue
            breadth = daily_by_key.loc[key]
            if isinstance(breadth, pd.DataFrame):
                breadth = breadth.iloc[0]
            for metric in METRICS:
                rows.append(
                    {
                        "signal_id": signal["signal_id"],
                        "scope": scope,
                        "scope_type": "primary" if scope in PRIMARY_SCOPES else "secondary",
                        "basket": basket,
                        "basket_membership_status": BASKET_STATUS,
                        "metric": metric,
                        "breadth_value": breadth.get(metric, pd.NA),
                        "breadth_state": breadth.get(f"{metric}_state", ""),
                        "breadth_status": breadth.get("breadth_status", ""),
                        "valid_member_count": breadth.get(f"{metric}_valid_member_count", breadth.get("valid_member_count", pd.NA)),
                        "signal_decision_date": signal["signal_decision_date"],
                        "entry_session": signal["entry_session"],
                        "underlying_symbol": signal["underlying_symbol"],
                        "signal_rank": signal["signal_rank"],
                        "theme": signal.get("theme", ""),
                        "outcome_status": signal["outcome_status"],
                        "outcome_complete_status": "complete" if signal["outcome_status"] == "complete" else signal["outcome_status"],
                        "reached_plus_5pct_within_10_sessions": bool(signal["reached_plus_5pct_within_10_sessions"]),
                        "breakout_day_low_breach_before_timeout": bool(signal["breakout_day_low_breach_before_timeout"]),
                        "timeout_10_sessions_under_threshold": bool(signal["timeout_10_sessions_under_threshold"]),
                        "maximum_adverse_excursion_10_sessions": signal.get("maximum_adverse_excursion_10_sessions", pd.NA),
                    }
                )
    return pd.DataFrame(rows)


def median_mae(group: pd.DataFrame) -> float | None:
    values = pd.to_numeric(group.get("maximum_adverse_excursion_10_sessions", pd.Series(dtype=float)), errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.median())


def state_summary(context: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rank_values = sorted([r for r in context["signal_rank"].dropna().unique() if r in {"S", "A", "B"}])
    rank_values.append("ALL")
    for keys, subset in context.groupby(["scope", "scope_type", "basket", "metric", "breadth_state"], dropna=False):
        scope, scope_type, basket, metric, state = keys
        for rank in rank_values:
            data = subset if rank == "ALL" else subset[subset["signal_rank"] == rank]
            complete = data[data["outcome_status"] == "complete"]
            rows.append(
                {
                    "scope": scope,
                    "scope_type": scope_type,
                    "basket": basket,
                    "metric": metric,
                    "breadth_state": state,
                    "rank": rank,
                    "total_signal_count": int(len(data)),
                    "complete_signal_count": int(len(complete)),
                    "collision_signal_count": int((data["outcome_status"] == "ambiguous_intraday_order").sum()),
                    "incomplete_signal_count": int((data["outcome_status"] == "incomplete_horizon").sum()),
                    "plus5_success_rate": bool_rate(complete["reached_plus_5pct_within_10_sessions"]) if not complete.empty else None,
                    "breakout_low_breach_rate": bool_rate(complete["breakout_day_low_breach_before_timeout"]) if not complete.empty else None,
                    "timeout_rate": bool_rate(complete["timeout_10_sessions_under_threshold"]) if not complete.empty else None,
                    "median_mae_10_sessions": median_mae(complete),
                    "mae_status": "available" if median_mae(complete) is not None else "mae_unavailable_from_baseline",
                }
            )
    return pd.DataFrame(rows)


def concentration_for_state(data: pd.DataFrame) -> tuple[float | None, str]:
    complete = data[data["outcome_status"] == "complete"]
    if complete.empty:
        return None, ""
    counts = complete["underlying_symbol"].value_counts()
    top_ticker = str(counts.index[0])
    share = float(counts.iloc[0] / len(complete))
    return share, top_ticker


def comparison_states(metric: str) -> tuple[str, str]:
    if metric == DISPERSION_METRIC:
        return "high_dispersion", "low_dispersion"
    return "high", "low"


def build_rank_summary(context: pd.DataFrame, min_complete: int, concentration_max: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    conc_rows: list[dict[str, Any]] = []
    ranks = ["S", "A", "B", "ALL"]
    group_cols = ["scope", "scope_type", "basket", "metric"]
    for keys, subset in context.groupby(group_cols, dropna=False):
        scope, scope_type, basket, metric = keys
        high_state, low_state = comparison_states(metric)
        for rank in ranks:
            data = subset if rank == "ALL" else subset[subset["signal_rank"] == rank]
            high = data[data["breadth_state"] == high_state]
            low = data[data["breadth_state"] == low_state]
            high_complete = high[high["outcome_status"] == "complete"]
            low_complete = low[low["outcome_status"] == "complete"]
            high_count = int(len(high_complete))
            low_count = int(len(low_complete))
            high_conc, high_ticker = concentration_for_state(high)
            low_conc, low_ticker = concentration_for_state(low)
            high_plus5 = bool_rate(high_complete["reached_plus_5pct_within_10_sessions"]) if high_count else None
            low_plus5 = bool_rate(low_complete["reached_plus_5pct_within_10_sessions"]) if low_count else None
            high_breach = bool_rate(high_complete["breakout_day_low_breach_before_timeout"]) if high_count else None
            low_breach = bool_rate(low_complete["breakout_day_low_breach_before_timeout"]) if low_count else None
            high_timeout = bool_rate(high_complete["timeout_10_sessions_under_threshold"]) if high_count else None
            low_timeout = bool_rate(low_complete["timeout_10_sessions_under_threshold"]) if low_count else None
            high_mae = median_mae(high_complete)
            low_mae = median_mae(low_complete)
            comparison_status = "sufficient_sample" if high_count >= min_complete and low_count >= min_complete else "insufficient_sample"
            concentration_breach = any(
                share is not None and share > concentration_max for share in [high_conc, low_conc]
            )
            plus5_diff_pp = None if high_plus5 is None or low_plus5 is None else (high_plus5 - low_plus5) * 100.0
            breach_diff_pp = None if high_breach is None or low_breach is None else (high_breach - low_breach) * 100.0
            timeout_diff_pp = None if high_timeout is None or low_timeout is None else (high_timeout - low_timeout) * 100.0
            mae_diff = None if high_mae is None or low_mae is None else high_mae - low_mae
            material_binary = False
            if plus5_diff_pp is not None and abs(plus5_diff_pp) >= 10.0:
                material_binary = True
            if breach_diff_pp is not None and abs(breach_diff_pp) >= 10.0:
                material_binary = True
            if comparison_status == "insufficient_sample":
                label = "insufficient_sample"
            elif concentration_breach:
                label = "inconsistent_relationship"
            elif material_binary:
                label = "potentially_material_relationship"
            else:
                label = "no_visible_relationship"
            row = {
                "scope": scope,
                "scope_type": scope_type,
                "basket": basket,
                "metric": metric,
                "rank": rank,
                "high_state": high_state,
                "low_state": low_state,
                "high_complete_signal_count": high_count,
                "low_complete_signal_count": low_count,
                "high_plus5_success_rate": high_plus5,
                "low_plus5_success_rate": low_plus5,
                "plus5_success_rate_diff_pp": plus5_diff_pp,
                "high_breakout_low_breach_rate": high_breach,
                "low_breakout_low_breach_rate": low_breach,
                "breakout_low_breach_rate_diff_pp": breach_diff_pp,
                "high_timeout_rate": high_timeout,
                "low_timeout_rate": low_timeout,
                "timeout_rate_diff_pp": timeout_diff_pp,
                "high_median_mae_10_sessions": high_mae,
                "low_median_mae_10_sessions": low_mae,
                "median_mae_10_sessions_diff": mae_diff,
                "mae_status": "available" if mae_diff is not None else "mae_unavailable_from_baseline",
                "largest_single_ticker_share_high": high_conc,
                "largest_single_ticker_high": high_ticker,
                "largest_single_ticker_share_low": low_conc,
                "largest_single_ticker_low": low_ticker,
                "concentration_guard_status": "concentration_breach" if concentration_breach else "passed",
                "comparison_status": comparison_status,
                "relationship_label": label,
            }
            rows.append(row)
            conc_rows.append(
                {
                    "scope": scope,
                    "scope_type": scope_type,
                    "basket": basket,
                    "metric": metric,
                    "rank": rank,
                    "high_state": high_state,
                    "high_complete_signal_count": high_count,
                    "largest_single_ticker_share_high": high_conc,
                    "largest_single_ticker_high": high_ticker,
                    "low_state": low_state,
                    "low_complete_signal_count": low_count,
                    "largest_single_ticker_share_low": low_conc,
                    "largest_single_ticker_low": low_ticker,
                    "concentration_guard_status": "concentration_breach" if concentration_breach else "passed",
                }
            )
    rank_summary = pd.DataFrame(rows)
    rank_summary = apply_primary_contradiction_labels(rank_summary)
    return rank_summary, pd.DataFrame(conc_rows)


def direction(row: pd.Series) -> str:
    plus5 = safe_float(row.get("plus5_success_rate_diff_pp"))
    breach = safe_float(row.get("breakout_low_breach_rate_diff_pp"))
    if plus5 is not None and plus5 >= 10.0:
        return "high_better"
    if breach is not None and breach <= -10.0:
        return "high_better"
    if plus5 is not None and plus5 <= -10.0:
        return "high_worse"
    if breach is not None and breach >= 10.0:
        return "high_worse"
    return "neutral"


def apply_primary_contradiction_labels(rank_summary: pd.DataFrame) -> pd.DataFrame:
    if rank_summary.empty:
        return rank_summary
    rank_summary = rank_summary.copy()
    rank_summary["directional_read"] = rank_summary.apply(direction, axis=1)
    primary = rank_summary[
        (rank_summary["scope"].isin(PRIMARY_SCOPES))
        & (rank_summary["comparison_status"] == "sufficient_sample")
        & (rank_summary["rank"].isin(["S", "A", "B"]))
    ]
    for (metric, rank), group in primary.groupby(["metric", "rank"]):
        directions = set(group["directional_read"]) - {"neutral"}
        if "high_better" in directions and "high_worse" in directions:
            mask = (
                rank_summary["scope"].isin(PRIMARY_SCOPES)
                & (rank_summary["metric"] == metric)
                & (rank_summary["rank"] == rank)
                & (rank_summary["comparison_status"] == "sufficient_sample")
            )
            rank_summary.loc[mask, "relationship_label"] = "inconsistent_relationship"
    for (scope, rank), group in primary.groupby(["scope", "rank"]):
        directions = set(group["directional_read"]) - {"neutral"}
        if "high_better" in directions and "high_worse" in directions:
            mask = (
                (rank_summary["scope"] == scope)
                & (rank_summary["rank"] == rank)
                & (rank_summary["comparison_status"] == "sufficient_sample")
                & (rank_summary["scope"].isin(PRIMARY_SCOPES))
            )
            rank_summary.loc[mask, "relationship_label"] = "inconsistent_relationship"
    return rank_summary


def build_scope_coverage(context: pd.DataFrame) -> pd.DataFrame:
    base = context.drop_duplicates(["scope", "basket", "signal_id"])
    rows: list[dict[str, Any]] = []
    for keys, subset in base.groupby(["scope", "scope_type", "basket"], dropna=False):
        scope, scope_type, basket = keys
        for rank in ["S", "A", "B", "ALL"]:
            data = subset if rank == "ALL" else subset[subset["signal_rank"] == rank]
            rows.append(
                {
                    "scope": scope,
                    "scope_type": scope_type,
                    "basket": basket,
                    "rank": rank,
                    "total_signal_count": int(len(data)),
                    "complete_signal_count": int((data["outcome_status"] == "complete").sum()),
                    "collision_signal_count": int((data["outcome_status"] == "ambiguous_intraday_order").sum()),
                    "incomplete_signal_count": int((data["outcome_status"] == "incomplete_horizon").sum()),
                }
            )
    return pd.DataFrame(rows)


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def safe_clean_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        resolved = output_dir.resolve()
        repo = REPO_ROOT.resolve()
        if repo not in resolved.parents and resolved != repo:
            raise SystemExit(f"refusing_to_clean_outside_repo:{resolved}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def build_summary_markdown(receipt: dict[str, Any], rank_summary: pd.DataFrame, coverage: pd.DataFrame) -> str:
    lines = [
        "# Morita Theme Breadth Quick Screen v1",
        "",
        f"Status: `{receipt['status']}`",
        f"Baseline run: `{receipt['baseline_run_id']}`",
        f"Baseline coverage: total `{receipt['baseline_total_rows']}`, complete `{receipt['baseline_complete_rows']}`, collisions `{receipt['baseline_collision_rows']}`, incomplete `{receipt['baseline_incomplete_rows']}`",
        f"MAE status: `{receipt['mae_status']}`",
        "",
        "Research only. No new data, no Bot rerun, no option analysis, no optimization, no actionization.",
        "",
        "## Basket Coverage",
    ]
    for basket, info in receipt["basket_coverage"].items():
        lines.append(f"- `{basket}`: static members `{info['static_member_count']}`, members with local OHLCV `{info['members_with_any_ohlcv']}`")
    lines.extend(["", "## Primary Scope Complete Signals"])
    primary_coverage = coverage[(coverage["scope_type"] == "primary") & (coverage["rank"].isin(["S", "A", "B"]))]
    for _, row in primary_coverage.sort_values(["scope", "rank"]).iterrows():
        lines.append(
            f"- `{row['scope']}` rank `{row['rank']}`: complete `{row['complete_signal_count']}`, total `{row['total_signal_count']}`"
        )
    lines.extend(["", "## Primary High-vs-Low Labels"])
    primary = rank_summary[(rank_summary["scope_type"] == "primary") & (rank_summary["rank"].isin(["S", "A", "B"]))]
    for _, row in primary.sort_values(["scope", "rank", "metric"]).iterrows():
        lines.append(
            "- "
            f"`{row['scope']}` rank `{row['rank']}` metric `{row['metric']}`: "
            f"label `{row['relationship_label']}`, status `{row['comparison_status']}`, "
            f"+5 diff `{fmt_number(row['plus5_success_rate_diff_pp'], 2)}pp`, "
            f"breach diff `{fmt_number(row['breakout_low_breach_rate_diff_pp'], 2)}pp`, "
            f"timeout diff `{fmt_number(row['timeout_rate_diff_pp'], 2)}pp`, "
            f"MAE diff `{fmt_number(row['median_mae_10_sessions_diff'], 4)}`"
        )
    material = primary[primary["relationship_label"] == "potentially_material_relationship"]
    inconsistent = primary[primary["relationship_label"] == "inconsistent_relationship"]
    if material.empty or not inconsistent.empty:
        recommendation = "freeze_breadth_move_to_vxn_vix"
    else:
        recommendation = "candidate_for_deeper_breadth_validation"
    lines.extend(
        [
            "",
            "## Triage Decision",
            "",
            f"`{recommendation}`",
            "",
            "This decision is descriptive research triage only and is not a trading recommendation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_chatgpt_bundle(output_dir: Path, summary_md: str, receipt: dict[str, Any], rank_summary: pd.DataFrame, coverage: pd.DataFrame) -> None:
    primary = rank_summary[(rank_summary["scope_type"] == "primary") & (rank_summary["rank"].isin(["S", "A", "B"]))]
    rows = []
    for _, row in primary.sort_values(["scope", "rank", "metric"]).iterrows():
        rows.append(
            "| {scope} | {rank} | {metric} | {high_n} | {low_n} | {plus5} | {breach} | {timeout} | {mae} | {label} |".format(
                scope=row["scope"],
                rank=row["rank"],
                metric=row["metric"],
                high_n=row["high_complete_signal_count"],
                low_n=row["low_complete_signal_count"],
                plus5=fmt_number(row["plus5_success_rate_diff_pp"], 2),
                breach=fmt_number(row["breakout_low_breach_rate_diff_pp"], 2),
                timeout=fmt_number(row["timeout_rate_diff_pp"], 2),
                mae=fmt_number(row["median_mae_10_sessions_diff"], 4),
                label=row["relationship_label"],
            )
        )
    bundle = [
        "# ChatGPT Handoff: Morita Theme Breadth Quick Screen v1",
        "",
        "## Objective",
        "",
        "Assess whether static semiconductor and AI-infrastructure breadth has a large, directionally consistent descriptive relationship with Morita Bot underlying outcomes.",
        "",
        "## Primary Status",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Baseline run: `{receipt['baseline_run_id']}`",
        f"- Coverage: total `{receipt['baseline_total_rows']}`, complete `{receipt['baseline_complete_rows']}`, collisions `{receipt['baseline_collision_rows']}`, incomplete `{receipt['baseline_incomplete_rows']}`",
        f"- MAE status: `{receipt['mae_status']}`",
        "",
        "## Basket Coverage",
        "",
    ]
    for basket, info in receipt["basket_coverage"].items():
        bundle.append(f"- `{basket}`: static `{info['static_member_count']}`, local OHLCV `{info['members_with_any_ohlcv']}`")
    bundle.extend(
        [
            "",
            "## Primary Scope Signal Counts",
            "",
            "| Scope | Rank | Total | Complete | Collisions | Incomplete |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    cov = coverage[(coverage["scope_type"] == "primary") & (coverage["rank"].isin(["S", "A", "B"]))]
    for _, row in cov.sort_values(["scope", "rank"]).iterrows():
        bundle.append(
            f"| {row['scope']} | {row['rank']} | {row['total_signal_count']} | {row['complete_signal_count']} | {row['collision_signal_count']} | {row['incomplete_signal_count']} |"
        )
    bundle.extend(
        [
            "",
            "## High-vs-Low Differences",
            "",
            "| Scope | Rank | Metric | High N | Low N | +5 Diff pp | Breach Diff pp | Timeout Diff pp | MAE Diff | Label |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
            *rows,
            "",
            "## Limitations",
            "",
            "- Static research baskets only; no PIT sector-membership claim.",
            "- Binary rates use complete outcomes only.",
            "- Collisions and incomplete horizons are diagnostics only.",
            "- No raw OHLCV or signal rows are included in this bundle.",
            "- No trading recommendation, live filter, Bot change, option analysis, or optimization.",
            f"- Full output directory: `{repo_relative(output_dir)}`",
            "",
            "## Next Question For ChatGPT",
            "",
            "Based on these labels and sample sizes, should breadth be frozen and research move to VXN/VIX, or is a narrow PIT taxonomy validation justified?",
            "",
            "## Embedded Summary",
            "",
            summary_md,
        ]
    )
    CHATGPT_BUNDLE.write_text("\n".join(bundle).rstrip() + "\n", encoding="utf-8")


def build_run(baseline_run_dir: Path, output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_CONFIG)
    min_valid = int(spec["minimum_valid_member_count"])
    min_complete = int(spec["minimum_complete_signals_per_state"])
    concentration_max = float(spec["concentration_guard_largest_ticker_share_max"])
    baskets = read_baskets()
    input_root = resolve_baseline_input_root(baseline_run_dir)
    panel, baseline_stats = load_baseline_panels(baseline_run_dir)
    ohlcv, decision_dates, input_meta = load_input_data(input_root)
    safe_clean_output_dir(output_dir)
    daily = compute_daily_breadth(ohlcv, decision_dates, baskets, min_valid)
    daily, cutoffs = assign_states(daily, min_valid)
    context = build_signal_context(panel, daily, baskets)
    outcome_summary = state_summary(context)
    rank_summary, concentration = build_rank_summary(context, min_complete, concentration_max)
    coverage = build_scope_coverage(context)
    local_tickers = set(ohlcv["ticker"].unique())
    basket_coverage = {
        name: {
            "static_member_count": len(members),
            "members_with_any_ohlcv": sum(1 for member in members if member in local_tickers),
            "missing_members": [member for member in members if member not in local_tickers],
        }
        for name, members in baskets.items()
    }
    receipt = {
        "artifact_version": "morita_theme_breadth_quick_screen_v1",
        "status": "morita_theme_breadth_quick_screen_completed",
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "baseline_run_dir": repo_relative(baseline_run_dir),
        "baseline_run_id": baseline_run_dir.name,
        "baseline_source_content_manifest_sha256": file_sha256(baseline_run_dir / "source_content_manifest.json"),
        "baseline_total_rows": baseline_stats["total_rows"],
        "baseline_complete_rows": baseline_stats["complete_rows"],
        "baseline_collision_rows": baseline_stats["collision_rows"],
        "baseline_incomplete_rows": baseline_stats["incomplete_rows"],
        "mae_status": "available" if baseline_stats["mae_available"] else "mae_unavailable_from_baseline",
        "input_root": repo_relative(input_root),
        "input_meta": input_meta,
        "basket_membership_status": BASKET_STATUS,
        "basket_coverage": basket_coverage,
        "daily_panel_rows": int(len(daily)),
        "signal_context_rows": int(len(context)),
        "rank_summary_rows": int(len(rank_summary)),
        "complete_denominator_policy": "outcome_status_equals_complete_only",
        "new_data_used": False,
        "bot_rerun_or_rule_change": False,
        "option_analysis_performed": False,
        "parameter_optimization_performed": False,
        "actionization_allowed": False,
    }
    write_dataframe(output_dir / "breadth_daily_panel.csv", daily)
    write_dataframe(output_dir / "breadth_signal_context_panel.csv", context)
    write_dataframe(output_dir / "breadth_state_cutoffs.csv", cutoffs)
    write_dataframe(output_dir / "breadth_outcome_summary.csv", outcome_summary)
    write_dataframe(output_dir / "breadth_rank_summary.csv", rank_summary)
    write_dataframe(output_dir / "breadth_scope_coverage.csv", coverage)
    write_dataframe(output_dir / "breadth_concentration_diagnostics.csv", concentration)
    write_json(output_dir / "breadth_receipt.json", receipt)
    summary_md = build_summary_markdown(receipt, rank_summary, coverage)
    (output_dir / "breadth_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir, MANIFEST_NAME)
    verify_manifest(output_dir, MANIFEST_NAME)
    write_chatgpt_bundle(output_dir, summary_md, receipt, rank_summary, coverage)
    return {
        "status": receipt["status"],
        "output_dir": repo_relative(output_dir),
        "manifest_hash": file_sha256(output_dir / MANIFEST_NAME),
        "chatgpt_bundle": repo_relative(CHATGPT_BUNDLE),
    }


def verify_run(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifest(output_dir, MANIFEST_NAME)
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    missing = sorted(set(REQUIRED_OUTPUTS) - files)
    if missing:
        raise SystemExit(f"breadth_manifest_missing_required_output:{missing[0]}")
    return {
        "status": "morita_theme_breadth_quick_screen_verified",
        "output_dir": repo_relative(output_dir),
        "manifest_hash": file_sha256(output_dir / MANIFEST_NAME),
        "file_count": len(files),
    }


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
    output_dir = (REPO_ROOT / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    if args.run:
        if not args.baseline_run_dir:
            raise SystemExit("--baseline-run-dir is required with --run")
        baseline_run_dir = (REPO_ROOT / args.baseline_run_dir).resolve() if not Path(args.baseline_run_dir).is_absolute() else Path(args.baseline_run_dir)
        print(json_dumps(build_run(baseline_run_dir, output_dir)))
        return 0
    print(json_dumps(verify_run(output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
