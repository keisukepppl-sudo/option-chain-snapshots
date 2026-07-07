from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_regime_sizing_overlay_v1"
CONTEXT_PATH = REPO_ROOT / "outputs" / "morita_realized_dispersion_quick_screen" / "realized_dispersion_signal_context_panel.csv"
D_METRIC = "broad_russell1000_cross_sectional_dispersion_20d"
L_METRIC = "broad_russell1000_qqq_minus_eqw_return_20d"
POLICY_VERSION = "morita_regime_sizing_overlay_v1"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def classify_from_states(D_state: str, L_state: str) -> str:
    D_high = str(D_state).lower() == "high"
    L_high = str(L_state).lower() == "high"
    if D_high and L_high:
        return "NARROW_LEADERSHIP"
    if D_high and not L_high:
        return "HIGH_DISPERSION"
    return "NORMAL"


def safe_rate(series: pd.Series) -> float:
    if series.empty:
        return math.nan
    return float(series.astype(bool).mean())


def build_signal_regime_panel(context_path: Path = CONTEXT_PATH) -> pd.DataFrame:
    if not context_path.exists():
        raise FileNotFoundError(f"context_missing:{repo_relative(context_path)}")
    ctx = pd.read_csv(context_path)
    needed = ctx[(ctx["scope"] == "broad_market_context") & (ctx["metric"].isin([D_METRIC, L_METRIC]))].copy()
    pivot = needed.pivot_table(
        index=[
            "signal_id",
            "signal_decision_date",
            "entry_session",
            "underlying_symbol",
            "signal_rank",
            "theme",
            "outcome_status",
            "outcome_complete_status",
            "reached_plus_5pct_within_10_sessions",
            "breakout_day_low_breach_before_timeout",
            "timeout_10_sessions_under_threshold",
        ],
        columns="metric",
        values=["metric_value", "metric_state"],
        aggfunc="first",
    ).reset_index()
    pivot.columns = [
        "_".join([str(part) for part in col if str(part)])
        if isinstance(col, tuple)
        else str(col)
        for col in pivot.columns
    ]
    pivot = pivot.rename(
        columns={
            f"metric_value_{D_METRIC}": "D_value",
            f"metric_value_{L_METRIC}": "L_value",
            f"metric_state_{D_METRIC}": "D_state",
            f"metric_state_{L_METRIC}": "L_state",
        }
    )
    pivot["regime_state"] = [classify_from_states(d, l) for d, l in zip(pivot["D_state"], pivot["L_state"])]
    return pivot


def concentration_share(values: pd.Series, n: int) -> float:
    if values.empty:
        return math.nan
    counts = values.value_counts()
    return float(counts.head(n).sum() / counts.sum())


def build_forward_review() -> pd.DataFrame:
    panel = build_signal_regime_panel()
    s_complete = panel[
        (panel["signal_rank"].astype(str) == "S")
        & (panel["outcome_complete_status"].astype(str) == "complete")
    ].copy()
    rows: list[dict[str, Any]] = []
    for regime in ["NORMAL", "HIGH_DISPERSION", "NARROW_LEADERSHIP", "REGIME_UNAVAILABLE_CONSERVATIVE"]:
        sub = s_complete[s_complete["regime_state"] == regime].copy()
        rows.append(
            {
                "policy_version": POLICY_VERSION,
                "regime_state": regime,
                "complete_signal_count": int(len(sub)),
                "plus5_success_rate": safe_rate(sub["reached_plus_5pct_within_10_sessions"]) if not sub.empty else math.nan,
                "breakout_low_breach_rate": safe_rate(sub["breakout_day_low_breach_before_timeout"]) if not sub.empty else math.nan,
                "timeout_rate": safe_rate(sub["timeout_10_sessions_under_threshold"]) if not sub.empty else math.nan,
                "median_10_session_MAE": math.nan,
                "p75_10_session_MAE": math.nan,
                "p90_10_session_MAE": math.nan,
                "unique_ticker_count": int(sub["underlying_symbol"].nunique()) if not sub.empty else 0,
                "largest_single_ticker_share": concentration_share(sub["underlying_symbol"], 1),
                "top_five_ticker_share": concentration_share(sub["underlying_symbol"], 5),
                "actual_confirmed_trade_count": 0,
                "allocation_weighted_realized_return": math.nan,
                "realized_PF_if_defined": math.nan,
                "actual_portfolio_drawdown_if_defined": math.nan,
                "actual_execution_section_status": "not_available_no_fabricated_fills",
                "milestone_1_25_complete_narrow_leadership_met": bool(regime == "NARROW_LEADERSHIP" and len(sub) >= 25),
                "milestone_2_50_complete_high_dispersion_met": bool(regime == "HIGH_DISPERSION" and len(sub) >= 50),
                "source_context": repo_relative(CONTEXT_PATH),
            }
        )
    return pd.DataFrame(rows)


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    review = build_forward_review()
    write_dataframe(output_dir / "regime_overlay_forward_review.csv", review)
    print(json.dumps({"status": "completed", "output": repo_relative(output_dir / "regime_overlay_forward_review.csv")}, sort_keys=True))


if __name__ == "__main__":
    main()
