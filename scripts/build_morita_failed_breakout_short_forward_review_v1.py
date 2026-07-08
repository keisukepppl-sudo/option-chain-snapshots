from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_INPUT_DIR = Path("outputs/morita_failed_breakout_short_forward_v1")
DEFAULT_OUTPUT_PATH = DEFAULT_INPUT_DIR / "failed_breakout_forward_review_v1.csv"

REVIEW_COLUMNS = [
    "period",
    "RS_bucket",
    "regime_state",
    "breakout_candidate_count",
    "failed_breakout_entry_count",
    "failure_rate",
    "completed_outcome_count",
    "reached_minus_5pct_10d_rate",
    "reached_minus_8pct_10d_rate",
    "reached_minus_10pct_10d_rate",
    "reached_minus_15pct_20d_rate",
    "recovered_breakout_high_10d_rate",
    "recovered_breakout_high_20d_rate",
    "median_MFE_10d",
    "median_MAE_10d",
    "p75_MAE_10d",
    "p90_MAE_10d",
    "unique_ticker_count",
    "largest_single_ticker_share",
    "top_five_ticker_share",
    "modeled_put_PF",
    "modeled_put_spread_PF",
    "modeled_win_rate",
    "modeled_mean_win_pct",
    "modeled_mean_loss_pct",
    "research_candidate_threshold_met",
]


def _rate(series: pd.Series) -> float:
    if series.empty:
        return math.nan
    return float(series.astype(bool).mean())


def _share_counts(series: pd.Series, top_n: int) -> float:
    if series.empty:
        return math.nan
    counts = series.astype(str).value_counts()
    return float(counts.head(top_n).sum() / counts.sum())


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def build_review(input_dir: Path = DEFAULT_INPUT_DIR, output_path: Path = DEFAULT_OUTPUT_PATH) -> list[dict[str, Any]]:
    candidates = _read(input_dir / "failed_breakout_candidate_watchlist.csv")
    entries = _read(input_dir / "failed_breakout_entry_log.csv")
    outcomes = _read(input_dir / "failed_breakout_forward_outcomes.csv")
    completed = outcomes[outcomes.get("outcome_status", pd.Series(dtype=str)).astype(str).eq("complete")].copy() if not outcomes.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    periods = ["5D", "10D", "20D"]
    groups = completed.groupby(["RS_bucket", "regime_state"], dropna=False) if not completed.empty else []
    for (bucket, regime), group in groups:
        cand_count = 0 if candidates.empty else len(candidates[(candidates["RS_bucket"].astype(str) == str(bucket)) & (candidates["regime_state"].astype(str) == str(regime))])
        entry_count = 0 if entries.empty else len(entries[(entries["RS_bucket"].astype(str) == str(bucket)) & (entries["regime_state"].astype(str) == str(regime))])
        failure_rate = entry_count / cand_count if cand_count else math.nan
        threshold_met = bool(
            len(group) >= 20
            and _rate(group["reached_minus_8pct_within_10d"]) >= 0.25
            and _rate(group["recovered_breakout_high_within_10d"]) <= 0.35
            and _share_counts(group["ticker"], 1) <= 0.35
        )
        for period in periods:
            rows.append(
                {
                    "period": period,
                    "RS_bucket": bucket,
                    "regime_state": regime,
                    "breakout_candidate_count": cand_count,
                    "failed_breakout_entry_count": entry_count,
                    "failure_rate": failure_rate,
                    "completed_outcome_count": len(group),
                    "reached_minus_5pct_10d_rate": _rate(group["reached_minus_5pct_within_10d"]),
                    "reached_minus_8pct_10d_rate": _rate(group["reached_minus_8pct_within_10d"]),
                    "reached_minus_10pct_10d_rate": _rate(group["reached_minus_10pct_within_10d"]),
                    "reached_minus_15pct_20d_rate": _rate(group["reached_minus_15pct_within_20d"]),
                    "recovered_breakout_high_10d_rate": _rate(group["recovered_breakout_high_within_10d"]),
                    "recovered_breakout_high_20d_rate": _rate(group["recovered_breakout_high_within_20d"]),
                    "median_MFE_10d": float(group["max_favorable_excursion_10d"].median()),
                    "median_MAE_10d": float(group["max_adverse_excursion_10d"].median()),
                    "p75_MAE_10d": float(group["max_adverse_excursion_10d"].quantile(0.75)),
                    "p90_MAE_10d": float(group["max_adverse_excursion_10d"].quantile(0.90)),
                    "unique_ticker_count": int(group["ticker"].nunique()),
                    "largest_single_ticker_share": _share_counts(group["ticker"], 1),
                    "top_five_ticker_share": _share_counts(group["ticker"], 5),
                    "modeled_put_PF": "",
                    "modeled_put_spread_PF": "",
                    "modeled_win_rate": "",
                    "modeled_mean_win_pct": "",
                    "modeled_mean_loss_pct": "",
                    "research_candidate_threshold_met": threshold_met,
                }
            )
    _write_csv(output_path, rows)
    summary_path = output_path.with_suffix(".md")
    summary_path.write_text(
        "# Failed Breakout Forward Review v1\n\n"
        f"Completed grouped review rows: `{len(rows)}`.\n\n"
        "No rule is auto-promoted. Manual review milestones remain 20 and 50 completed RS90_95 high-dispersion or narrow-leadership outcomes.\n",
        encoding="utf-8",
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()
    rows = build_review(Path(args.input_dir), Path(args.output_path))
    print(json.dumps({"review_rows": len(rows), "output_path": args.output_path}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
