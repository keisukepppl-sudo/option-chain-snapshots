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
SPEC_PATH = REPO_ROOT / "config" / "morita_volatility_regime_v1" / "volatility_quick_screen_spec.json"
BASKET_PATH = REPO_ROOT / "config" / "morita_theme_breadth_v1" / "static_research_baskets_v1.json"
CHATGPT_BUNDLE = REPO_ROOT / "morita_volatility_regime_quick_screen_chatgpt_bundle.md"
MANIFEST_NAME = "volatility_content_manifest.json"
BASKET_STATUS = "static_research_basket_proxy"
VXN_METRICS = ["vxn_level", "vxn_change_5d"]
THEME_METRICS = [
    "semiconductor_core_theme_realized_vol_20d",
    "semiconductor_core_theme_to_qqq_realized_vol_ratio_20d",
    "ai_infrastructure_extended_theme_realized_vol_20d",
    "ai_infrastructure_extended_theme_to_qqq_realized_vol_ratio_20d",
]
ALL_METRICS = VXN_METRICS + THEME_METRICS
PRIMARY_SCOPES = {
    "nasdaq_volatility",
    "semiconductor_theme_volatility",
    "ai_infrastructure_theme_volatility",
}
REQUIRED_OUTPUTS = [
    "vxn_daily_panel.csv",
    "theme_volatility_daily_panel.csv",
    "volatility_signal_context_panel.csv",
    "volatility_state_cutoffs.csv",
    "volatility_outcome_summary.csv",
    "volatility_rank_summary.csv",
    "volatility_scope_coverage.csv",
    "volatility_concentration_diagnostics.csv",
    "volatility_receipt.json",
    "volatility_summary.md",
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


def fmt_number(value: Any, digits: int = 2) -> str:
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


def build_manifest(path: Path, manifest_name: str = MANIFEST_NAME) -> dict[str, Any]:
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and child.name != manifest_name:
            files.append({"relative_path": child.relative_to(path).as_posix(), "sha256": file_sha256(child), "bytes": child.stat().st_size})
    manifest = {
        "artifact_version": "morita_volatility_regime_quick_screen_v1",
        "created_at_utc": iso_now(),
        "files": files,
        "content_set_hash": text_hash(json_dumps(files)),
    }
    write_json(path / manifest_name, manifest)
    return manifest


def read_baskets() -> dict[str, list[str]]:
    config = load_json(BASKET_PATH)
    baskets = {}
    for name, members in config["baskets"].items():
        seen = set()
        cleaned = []
        for member in members:
            ticker = str(member).strip().upper()
            if ticker and ticker not in seen:
                seen.add(ticker)
                cleaned.append(ticker)
        baskets[name] = cleaned
    return baskets


def resolve_baseline_input_root(baseline_run_dir: Path) -> Path:
    verify_manifest(baseline_run_dir, "source_content_manifest.json")
    lineage = load_json(baseline_run_dir / "source_input_lineage.json")
    entries = [entry for entry in lineage.get("inputs", []) if entry.get("required_for_signal_or_outcome")]
    if len(entries) != 1:
        raise SystemExit("baseline_lineage_invalid")
    rel = entries[0].get("repository_relative_path_or_local_alias")
    input_root = (REPO_ROOT / rel).resolve()
    if not input_root.exists():
        raise SystemExit(f"baseline_input_missing:{rel}")
    manifest = input_root / "source_manifest.json"
    if manifest.exists() and entries[0].get("sha256") and file_sha256(manifest) != entries[0]["sha256"]:
        raise SystemExit("baseline_input_manifest_hash_mismatch")
    return input_root


def load_baseline_panel(baseline_run_dir: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    panel = pd.read_csv(baseline_run_dir / "morita_bot_baseline_panel.csv")
    required = {
        "signal_id",
        "signal_decision_date",
        "entry_session",
        "underlying_symbol",
        "signal_rank",
        "theme",
        "outcome_status",
        "reached_plus_5pct_within_10_sessions",
        "breakout_day_low_breach_before_timeout",
        "timeout_10_sessions_under_threshold",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise SystemExit(f"baseline_missing_columns:{','.join(missing)}")
    panel["signal_decision_date"] = pd.to_datetime(panel["signal_decision_date"]).dt.strftime("%Y-%m-%d")
    panel["underlying_symbol"] = panel["underlying_symbol"].astype(str).str.upper()
    panel["signal_rank"] = panel["signal_rank"].astype(str)
    for col in ["reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"]:
        panel[col] = panel[col].map(lambda value: value if isinstance(value, bool) else str(value).lower() == "true")
    stats = {
        "total": int(len(panel)),
        "complete": int((panel["outcome_status"] == "complete").sum()),
        "collisions": int((panel["outcome_status"] == "ambiguous_intraday_order").sum()),
        "incomplete": int((panel["outcome_status"] == "incomplete_horizon").sum()),
    }
    return panel, stats


def load_input_data(input_root: Path) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    source_dir = input_root / "sources"
    ohlcv_path = source_dir / "daily_ohlcv_merged.csv"
    schedule_path = source_dir / "decision_schedule.csv"
    if not ohlcv_path.exists() or not schedule_path.exists():
        raise SystemExit("baseline_input_missing_sources")
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


def load_vxn(vxn_input_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    normalized = vxn_input_dir / "vxn_history_normalized.csv"
    manifest = vxn_input_dir / "vxn_input_manifest.json"
    receipt_path = vxn_input_dir / "vxn_intake_receipt.json"
    if not normalized.exists():
        return pd.DataFrame(columns=["date", "vxn_level", "vxn_change_5d"]), {"vxn_status": "vxn_unavailable", "reason": "normalized_missing"}
    if manifest.exists():
        verify_manifest(vxn_input_dir, "vxn_input_manifest.json")
    df = pd.read_csv(normalized)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["vxn_level"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "vxn_level"]).sort_values("date")
    df["vxn_change_5d"] = df["vxn_level"] / df["vxn_level"].shift(5) - 1.0
    meta = {
        "vxn_status": "available",
        "normalized_path": repo_relative(normalized),
        "normalized_sha256": file_sha256(normalized),
        "row_count": int(len(df)),
        "min_date": str(df["date"].min()) if not df.empty else "",
        "max_date": str(df["date"].max()) if not df.empty else "",
    }
    if receipt_path.exists():
        meta["receipt_sha256"] = file_sha256(receipt_path)
    return df[["date", "vxn_level", "vxn_change_5d"]], meta


def annualized_vol(returns: pd.Series, window: int, annualization: int) -> pd.Series:
    return returns.rolling(window, min_periods=window).std(ddof=0) * math.sqrt(annualization)


def compute_theme_volatility(ohlcv: pd.DataFrame, decision_dates: list[str], baskets: dict[str, list[str]], spec: dict[str, Any]) -> pd.DataFrame:
    window = int(spec["realized_vol_window_sessions"])
    min_members = int(spec["minimum_valid_member_count"])
    annualization = int(spec["annualization_sessions"])
    close = ohlcv.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    returns = close.pct_change()
    if "QQQ" not in close.columns:
        raise SystemExit("qqq_missing_from_baseline_ohlcv")
    qqq_vol = annualized_vol(returns["QQQ"], window, annualization)
    rows = []
    decision_index = pd.to_datetime(decision_dates)
    theme_daily: dict[str, pd.DataFrame] = {}
    for basket, members in baskets.items():
        basket_returns = returns[[member for member in members if member in returns.columns]].copy()
        valid_count = basket_returns.notna().sum(axis=1)
        eqw_return = basket_returns.where(valid_count >= min_members).mean(axis=1)
        theme_vol = annualized_vol(eqw_return, window, annualization)
        theme_daily[basket] = pd.DataFrame({"theme_eqw_return": eqw_return, "theme_realized_vol_20d": theme_vol, "valid_member_count": valid_count})
    for dt in decision_index:
        date_key = dt.strftime("%Y-%m-%d")
        row = {"date": date_key, "qqq_realized_vol_20d": qqq_vol.get(dt, pd.NA), "basket_membership_status": BASKET_STATUS}
        for basket, data in theme_daily.items():
            valid_member_count = data["valid_member_count"].get(dt, 0)
            theme_vol = data["theme_realized_vol_20d"].get(dt, pd.NA)
            qqq_value = qqq_vol.get(dt, pd.NA)
            ratio = pd.NA
            qqq_float = safe_float(qqq_value)
            theme_float = safe_float(theme_vol)
            if qqq_float is not None and qqq_float > 0 and theme_float is not None:
                ratio = theme_float / qqq_float
            row[f"{basket}_valid_member_count"] = int(valid_member_count) if not pd.isna(valid_member_count) else 0
            row[f"{basket}_theme_realized_vol_20d"] = theme_vol
            row[f"{basket}_theme_to_qqq_realized_vol_ratio_20d"] = ratio
            row[f"{basket}_vol_status"] = "available" if safe_float(theme_vol) is not None else "unavailable"
        rows.append(row)
    return pd.DataFrame(rows)


def assign_states(metric_panel: pd.DataFrame, complete_signal_dates: list[str], metrics: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = metric_panel.copy()
    date_set = set(complete_signal_dates)
    cutoff_rows = []
    for metric in metrics:
        if metric not in panel.columns:
            panel[f"{metric}_state"] = "metric_unavailable"
            cutoff_rows.append({"metric": metric, "p33": pd.NA, "p67": pd.NA, "valid_complete_signal_date_count": 0, "state_policy": "metric_unavailable"})
            continue
        values = pd.to_numeric(panel[panel["date"].isin(date_set)][metric], errors="coerce").dropna()
        if values.empty:
            p33 = p67 = pd.NA
            count = 0
        else:
            p33 = float(values.quantile(1.0 / 3.0))
            p67 = float(values.quantile(2.0 / 3.0))
            count = int(len(values))
        states = []
        for value in pd.to_numeric(panel[metric], errors="coerce"):
            if pd.isna(value) or count == 0:
                states.append("metric_unavailable")
            elif metric == "vxn_change_5d":
                if value <= p33:
                    states.append("vxn_falling_or_low_change")
                elif value >= p67:
                    states.append("vxn_rising_or_high_change")
                else:
                    states.append("vxn_neutral_change")
            else:
                if value <= p33:
                    states.append("low")
                elif value >= p67:
                    states.append("high")
                else:
                    states.append("middle")
        panel[f"{metric}_state"] = states
        cutoff_rows.append(
            {
                "metric": metric,
                "p33": p33,
                "p67": p67,
                "valid_complete_signal_date_count": count,
                "state_policy": "unique_complete_signal_decision_dates_p33_p67",
                "label_status": "signal_date_conditioned;ex_post_descriptive;not_predictive;not_live_filters",
            }
        )
    return panel, pd.DataFrame(cutoff_rows)


def build_metric_panels(vxn: pd.DataFrame, theme: pd.DataFrame, complete_signal_dates: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    vxn_panel = vxn.copy()
    if vxn_panel.empty:
        vxn_panel = pd.DataFrame({"date": sorted(set(theme["date"])), "vxn_level": pd.NA, "vxn_change_5d": pd.NA})
    vxn_panel, vxn_cutoffs = assign_states(vxn_panel, complete_signal_dates, VXN_METRICS)
    theme_panel, theme_cutoffs = assign_states(theme, complete_signal_dates, THEME_METRICS)
    cutoffs = pd.concat([vxn_cutoffs, theme_cutoffs], ignore_index=True)
    return vxn_panel, theme_panel, cutoffs


def scope_rows(panel: pd.DataFrame, baskets: dict[str, list[str]]) -> dict[tuple[str, str], tuple[pd.DataFrame, list[str]]]:
    semiconductor = set(baskets["semiconductor_core"])
    ai = set(baskets["ai_infrastructure_extended"])
    return {
        ("nasdaq_volatility", "all"): (panel.copy(), VXN_METRICS),
        ("semiconductor_theme_volatility", "semiconductor_core"): (
            panel[panel["underlying_symbol"].isin(semiconductor)].copy(),
            ["semiconductor_core_theme_realized_vol_20d", "semiconductor_core_theme_to_qqq_realized_vol_ratio_20d"],
        ),
        ("ai_infrastructure_theme_volatility", "ai_infrastructure_extended"): (
            panel[panel["underlying_symbol"].isin(ai)].copy(),
            ["ai_infrastructure_extended_theme_realized_vol_20d", "ai_infrastructure_extended_theme_to_qqq_realized_vol_ratio_20d"],
        ),
    }


def build_signal_context(panel: pd.DataFrame, vxn_panel: pd.DataFrame, theme_panel: pd.DataFrame, baskets: dict[str, list[str]]) -> pd.DataFrame:
    vxn_by_date = vxn_panel.set_index("date", drop=False)
    theme_by_date = theme_panel.set_index("date", drop=False)
    rows = []
    for (scope, basket), (scoped, metrics) in scope_rows(panel, baskets).items():
        for _, signal in scoped.iterrows():
            date_key = signal["signal_decision_date"]
            source = vxn_by_date if scope == "nasdaq_volatility" else theme_by_date
            if date_key not in source.index:
                continue
            values = source.loc[date_key]
            if isinstance(values, pd.DataFrame):
                values = values.iloc[0]
            for metric in metrics:
                rows.append(
                    {
                        "signal_id": signal["signal_id"],
                        "scope": scope,
                        "scope_type": "primary",
                        "basket": basket,
                        "basket_membership_status": BASKET_STATUS if basket != "all" else "",
                        "metric": metric,
                        "metric_value": values.get(metric, pd.NA),
                        "metric_state": values.get(f"{metric}_state", "metric_unavailable"),
                        "signal_decision_date": date_key,
                        "entry_session": signal["entry_session"],
                        "underlying_symbol": signal["underlying_symbol"],
                        "signal_rank": signal["signal_rank"],
                        "theme": signal.get("theme", ""),
                        "outcome_status": signal["outcome_status"],
                        "outcome_complete_status": "complete" if signal["outcome_status"] == "complete" else signal["outcome_status"],
                        "reached_plus_5pct_within_10_sessions": bool(signal["reached_plus_5pct_within_10_sessions"]),
                        "breakout_day_low_breach_before_timeout": bool(signal["breakout_day_low_breach_before_timeout"]),
                        "timeout_10_sessions_under_threshold": bool(signal["timeout_10_sessions_under_threshold"]),
                    }
                )
    return pd.DataFrame(rows)


def bool_rate(series: pd.Series) -> float | None:
    if len(series) == 0:
        return None
    return float(series.astype(bool).mean())


def build_outcome_summary(context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, subset in context.groupby(["scope", "scope_type", "basket", "metric", "metric_state"], dropna=False):
        scope, scope_type, basket, metric, state = keys
        for rank in ["S", "A", "B", "ALL"]:
            data = subset if rank == "ALL" else subset[subset["signal_rank"] == rank]
            complete = data[data["outcome_status"] == "complete"]
            rows.append(
                {
                    "scope": scope,
                    "scope_type": scope_type,
                    "basket": basket,
                    "metric": metric,
                    "metric_state": state,
                    "rank": rank,
                    "total_signal_count": int(len(data)),
                    "complete_signal_count": int(len(complete)),
                    "collision_signal_count": int((data["outcome_status"] == "ambiguous_intraday_order").sum()),
                    "incomplete_signal_count": int((data["outcome_status"] == "incomplete_horizon").sum()),
                    "plus5_success_rate": bool_rate(complete["reached_plus_5pct_within_10_sessions"]) if not complete.empty else None,
                    "breakout_low_breach_rate": bool_rate(complete["breakout_day_low_breach_before_timeout"]) if not complete.empty else None,
                    "timeout_rate": bool_rate(complete["timeout_10_sessions_under_threshold"]) if not complete.empty else None,
                    "mae_status": "unavailable_from_baseline",
                }
            )
    return pd.DataFrame(rows)


def high_low_states(metric: str) -> tuple[str, str]:
    if metric == "vxn_change_5d":
        return "vxn_rising_or_high_change", "vxn_falling_or_low_change"
    return "high", "low"


def concentration(data: pd.DataFrame) -> tuple[float | None, str]:
    complete = data[data["outcome_status"] == "complete"]
    if complete.empty:
        return None, ""
    counts = complete["underlying_symbol"].value_counts()
    return float(counts.iloc[0] / len(complete)), str(counts.index[0])


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


def build_rank_summary(context: pd.DataFrame, min_n: int, concentration_max: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    concentration_rows = []
    for keys, subset in context.groupby(["scope", "scope_type", "basket", "metric"], dropna=False):
        scope, scope_type, basket, metric = keys
        high_state, low_state = high_low_states(metric)
        for rank in ["S", "A", "B", "ALL"]:
            data = subset if rank == "ALL" else subset[subset["signal_rank"] == rank]
            high = data[data["metric_state"] == high_state]
            low = data[data["metric_state"] == low_state]
            high_complete = high[high["outcome_status"] == "complete"]
            low_complete = low[low["outcome_status"] == "complete"]
            high_count = int(len(high_complete))
            low_count = int(len(low_complete))
            high_plus5 = bool_rate(high_complete["reached_plus_5pct_within_10_sessions"]) if high_count else None
            low_plus5 = bool_rate(low_complete["reached_plus_5pct_within_10_sessions"]) if low_count else None
            high_breach = bool_rate(high_complete["breakout_day_low_breach_before_timeout"]) if high_count else None
            low_breach = bool_rate(low_complete["breakout_day_low_breach_before_timeout"]) if low_count else None
            high_timeout = bool_rate(high_complete["timeout_10_sessions_under_threshold"]) if high_count else None
            low_timeout = bool_rate(low_complete["timeout_10_sessions_under_threshold"]) if low_count else None
            high_conc, high_ticker = concentration(high)
            low_conc, low_ticker = concentration(low)
            plus5_diff = None if high_plus5 is None or low_plus5 is None else (high_plus5 - low_plus5) * 100.0
            breach_diff = None if high_breach is None or low_breach is None else (high_breach - low_breach) * 100.0
            timeout_diff = None if high_timeout is None or low_timeout is None else (high_timeout - low_timeout) * 100.0
            comparison_status = "sufficient_sample" if high_count >= min_n and low_count >= min_n else "insufficient_sample"
            concentration_breach = any(share is not None and share > concentration_max for share in [high_conc, low_conc])
            material = (plus5_diff is not None and abs(plus5_diff) >= 10.0) or (breach_diff is not None and abs(breach_diff) >= 10.0)
            timeout_contradicts = False
            if timeout_diff is not None:
                if direction({"plus5_success_rate_diff_pp": plus5_diff, "breakout_low_breach_rate_diff_pp": breach_diff}) == "high_better" and timeout_diff >= 10.0:
                    timeout_contradicts = True
                if direction({"plus5_success_rate_diff_pp": plus5_diff, "breakout_low_breach_rate_diff_pp": breach_diff}) == "high_worse" and timeout_diff <= -10.0:
                    timeout_contradicts = True
            if comparison_status == "insufficient_sample":
                label = "insufficient_sample"
            elif concentration_breach or timeout_contradicts:
                label = "inconsistent_relationship"
            elif material:
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
                "plus5_success_rate_diff_pp": plus5_diff,
                "high_breakout_low_breach_rate": high_breach,
                "low_breakout_low_breach_rate": low_breach,
                "breakout_low_breach_rate_diff_pp": breach_diff,
                "high_timeout_rate": high_timeout,
                "low_timeout_rate": low_timeout,
                "timeout_rate_diff_pp": timeout_diff,
                "largest_single_ticker_share_high": high_conc,
                "largest_single_ticker_high": high_ticker,
                "largest_single_ticker_share_low": low_conc,
                "largest_single_ticker_low": low_ticker,
                "concentration_guard_status": "concentration_breach" if concentration_breach else "passed",
                "comparison_status": comparison_status,
                "relationship_label": label,
                "directional_read": "",
                "mae_status": "unavailable_from_baseline",
            }
            row["directional_read"] = direction(pd.Series(row))
            rows.append(row)
            concentration_rows.append({k: row[k] for k in ["scope", "scope_type", "basket", "metric", "rank", "high_complete_signal_count", "largest_single_ticker_share_high", "largest_single_ticker_high", "low_complete_signal_count", "largest_single_ticker_share_low", "largest_single_ticker_low", "concentration_guard_status"]})
    summary = apply_related_metric_contradictions(pd.DataFrame(rows))
    return summary, pd.DataFrame(concentration_rows)


def apply_related_metric_contradictions(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary
    summary = summary.copy()
    related_groups = {
        "nasdaq_volatility": ["vxn_level", "vxn_change_5d"],
        "semiconductor_theme_volatility": ["semiconductor_core_theme_realized_vol_20d", "semiconductor_core_theme_to_qqq_realized_vol_ratio_20d"],
        "ai_infrastructure_theme_volatility": ["ai_infrastructure_extended_theme_realized_vol_20d", "ai_infrastructure_extended_theme_to_qqq_realized_vol_ratio_20d"],
    }
    for scope, metrics in related_groups.items():
        for rank in ["S", "A", "B"]:
            mask = (summary["scope"] == scope) & (summary["rank"] == rank) & (summary["comparison_status"] == "sufficient_sample") & (summary["metric"].isin(metrics))
            directions = set(summary.loc[mask, "directional_read"]) - {"neutral"}
            if "high_better" in directions and "high_worse" in directions:
                summary.loc[mask, "relationship_label"] = "inconsistent_relationship"
    return summary


def build_scope_coverage(context: pd.DataFrame) -> pd.DataFrame:
    base = context.drop_duplicates(["scope", "basket", "signal_id"])
    rows = []
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


def build_summary(receipt: dict[str, Any], coverage: pd.DataFrame, rank_summary: pd.DataFrame) -> str:
    lines = [
        "# Morita Volatility-Regime Quick Screen v1",
        "",
        f"Status: `{receipt['status']}`",
        f"Baseline run: `{receipt['baseline_run_id']}`",
        f"Baseline coverage: total `{receipt['baseline_total_rows']}`, complete `{receipt['baseline_complete_rows']}`, collisions `{receipt['baseline_collision_rows']}`, incomplete `{receipt['baseline_incomplete_rows']}`",
        f"VXN status: `{receipt['vxn_meta']['vxn_status']}`",
        "MAE status: `unavailable_from_baseline`",
        "",
        "Research only. No Bot rerun/rule change, no option-chain/skew analysis, no optimization, no actionization.",
        "",
        "## Theme Basket Coverage",
    ]
    for basket, info in receipt["basket_coverage"].items():
        lines.append(f"- `{basket}`: static members `{info['static_member_count']}`, local OHLCV `{info['members_with_any_ohlcv']}`")
    lines.extend(["", "## Complete Signals by Scope/Rank"])
    for _, row in coverage[coverage["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank"]).iterrows():
        lines.append(f"- `{row['scope']}` rank `{row['rank']}`: complete `{row['complete_signal_count']}`, total `{row['total_signal_count']}`")
    lines.extend(["", "## High-vs-Low Labels"])
    primary = rank_summary[rank_summary["rank"].isin(["S", "A", "B"])]
    for _, row in primary.sort_values(["scope", "rank", "metric"]).iterrows():
        lines.append(
            "- "
            f"`{row['scope']}` rank `{row['rank']}` metric `{row['metric']}`: "
            f"label `{row['relationship_label']}`, status `{row['comparison_status']}`, "
            f"+5 diff `{fmt_number(row['plus5_success_rate_diff_pp'])}pp`, "
            f"breach diff `{fmt_number(row['breakout_low_breach_rate_diff_pp'])}pp`, "
            f"timeout diff `{fmt_number(row['timeout_rate_diff_pp'])}pp`"
        )
    material = primary[primary["relationship_label"] == "potentially_material_relationship"]
    inconsistent = primary[primary["relationship_label"] == "inconsistent_relationship"]
    decision = "freeze_vol_regime_move_to_qqq_skew" if material.empty or not inconsistent.empty else "candidate_for_deeper_vol_regime_validation"
    lines.extend(["", "## Triage Decision", "", f"`{decision}`", "", "This is descriptive triage only, not a trading recommendation."])
    return "\n".join(lines) + "\n"


def write_bundle(output_dir: Path, summary_md: str, receipt: dict[str, Any], coverage: pd.DataFrame, rank_summary: pd.DataFrame) -> None:
    bundle = [
        "# ChatGPT Handoff: Morita Volatility-Regime Quick Screen v1",
        "",
        "## Objective",
        "",
        "Assess whether VXN and theme-specific realized volatility have a large, directionally consistent descriptive relationship with Morita Bot underlying outcomes.",
        "",
        "## Status",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Baseline run: `{receipt['baseline_run_id']}`",
        f"- VXN status: `{receipt['vxn_meta']['vxn_status']}`",
        f"- Baseline coverage: total `{receipt['baseline_total_rows']}`, complete `{receipt['baseline_complete_rows']}`, collisions `{receipt['baseline_collision_rows']}`, incomplete `{receipt['baseline_incomplete_rows']}`",
        "",
        "## Scope Counts",
        "",
        "| Scope | Rank | Total | Complete | Collisions | Incomplete |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in coverage[coverage["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank"]).iterrows():
        bundle.append(f"| {row['scope']} | {row['rank']} | {row['total_signal_count']} | {row['complete_signal_count']} | {row['collision_signal_count']} | {row['incomplete_signal_count']} |")
    bundle.extend(["", "## High-vs-Low Differences", "", "| Scope | Rank | Metric | High N | Low N | +5 Diff pp | Breach Diff pp | Timeout Diff pp | Label |", "|---|---:|---|---:|---:|---:|---:|---:|---|"])
    primary = rank_summary[rank_summary["rank"].isin(["S", "A", "B"])]
    for _, row in primary.sort_values(["scope", "rank", "metric"]).iterrows():
        bundle.append(
            f"| {row['scope']} | {row['rank']} | {row['metric']} | {row['high_complete_signal_count']} | {row['low_complete_signal_count']} | {fmt_number(row['plus5_success_rate_diff_pp'])} | {fmt_number(row['breakout_low_breach_rate_diff_pp'])} | {fmt_number(row['timeout_rate_diff_pp'])} | {row['relationship_label']} |"
        )
    bundle.extend(
        [
            "",
            "## Limitations",
            "",
            "- No raw VXN, OHLCV, or signal rows included.",
            "- Only authorized `^VXN` external data was used.",
            "- Theme baskets are static research proxies.",
            "- Complete outcomes only are binary denominators.",
            "- No option-chain/skew analysis, optimization, live filter, or actionization.",
            f"- Output directory: `{repo_relative(output_dir)}`",
            "",
            "## Embedded Summary",
            "",
            summary_md,
        ]
    )
    CHATGPT_BUNDLE.write_text("\n".join(bundle).rstrip() + "\n", encoding="utf-8")


def build_run(baseline_run_dir: Path, vxn_input_dir: Path, output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    input_root = resolve_baseline_input_root(baseline_run_dir)
    baseline, baseline_stats = load_baseline_panel(baseline_run_dir)
    ohlcv, decision_dates, input_meta = load_input_data(input_root)
    baskets = read_baskets()
    vxn, vxn_meta = load_vxn(vxn_input_dir)
    theme_panel = compute_theme_volatility(ohlcv, decision_dates, baskets, spec)
    complete_signal_dates = sorted(set(baseline.loc[baseline["outcome_status"] == "complete", "signal_decision_date"]))
    vxn_panel, theme_panel, cutoffs = build_metric_panels(vxn, theme_panel, complete_signal_dates)
    context = build_signal_context(baseline, vxn_panel, theme_panel, baskets)
    outcome_summary = build_outcome_summary(context)
    rank_summary, concentration_diag = build_rank_summary(context, int(spec["minimum_complete_signals_per_high_low_state"]), float(spec["concentration_guard_largest_ticker_share_max"]))
    coverage = build_scope_coverage(context)
    local_tickers = set(ohlcv["ticker"].unique())
    basket_coverage = {
        basket: {
            "static_member_count": len(members),
            "members_with_any_ohlcv": sum(1 for member in members if member in local_tickers),
            "missing_members": [member for member in members if member not in local_tickers],
        }
        for basket, members in baskets.items()
    }
    safe_clean_output_dir(output_dir)
    write_dataframe(output_dir / "vxn_daily_panel.csv", vxn_panel)
    write_dataframe(output_dir / "theme_volatility_daily_panel.csv", theme_panel)
    write_dataframe(output_dir / "volatility_signal_context_panel.csv", context)
    write_dataframe(output_dir / "volatility_state_cutoffs.csv", cutoffs)
    write_dataframe(output_dir / "volatility_outcome_summary.csv", outcome_summary)
    write_dataframe(output_dir / "volatility_rank_summary.csv", rank_summary)
    write_dataframe(output_dir / "volatility_scope_coverage.csv", coverage)
    write_dataframe(output_dir / "volatility_concentration_diagnostics.csv", concentration_diag)
    receipt = {
        "artifact_version": "morita_volatility_regime_quick_screen_v1",
        "status": "morita_volatility_regime_quick_screen_completed",
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "baseline_run_dir": repo_relative(baseline_run_dir),
        "baseline_run_id": baseline_run_dir.name,
        "baseline_source_content_manifest_sha256": file_sha256(baseline_run_dir / "source_content_manifest.json"),
        "baseline_total_rows": baseline_stats["total"],
        "baseline_complete_rows": baseline_stats["complete"],
        "baseline_collision_rows": baseline_stats["collisions"],
        "baseline_incomplete_rows": baseline_stats["incomplete"],
        "vxn_meta": vxn_meta,
        "input_meta": input_meta,
        "basket_membership_status": BASKET_STATUS,
        "basket_coverage": basket_coverage,
        "mae_status": "unavailable_from_baseline",
        "only_authorized_vxn_external_data_fetched": vxn_meta.get("vxn_status") == "available",
        "bot_rerun_or_rule_change": False,
        "option_chain_or_skew_analysis_performed": False,
        "parameter_optimization_performed": False,
        "actionization_allowed": False,
    }
    write_json(output_dir / "volatility_receipt.json", receipt)
    summary_md = build_summary(receipt, coverage, rank_summary)
    (output_dir / "volatility_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir, MANIFEST_NAME)
    verify_manifest(output_dir, MANIFEST_NAME)
    write_bundle(output_dir, summary_md, receipt, coverage, rank_summary)
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
        raise SystemExit(f"volatility_manifest_missing_required_output:{missing[0]}")
    return {
        "status": "morita_volatility_regime_quick_screen_verified",
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
    parser.add_argument("--vxn-input-dir")
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
    if not args.baseline_run_dir or not args.vxn_input_dir:
        raise SystemExit("--baseline-run-dir and --vxn-input-dir are required with --run")
    baseline_run_dir = Path(args.baseline_run_dir)
    vxn_input_dir = Path(args.vxn_input_dir)
    if not baseline_run_dir.is_absolute():
        baseline_run_dir = REPO_ROOT / baseline_run_dir
    if not vxn_input_dir.is_absolute():
        vxn_input_dir = REPO_ROOT / vxn_input_dir
    print(json_dumps(build_run(baseline_run_dir, vxn_input_dir, output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
