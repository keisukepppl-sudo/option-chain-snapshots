from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ARTIFACT_VERSION = "morita_current_conditions_sa_rebuild_v1"
OUTPUT_ROOT = Path("outputs") / "research_only" / ARTIFACT_VERSION
SIGNAL_SCOPE = "MORITA_CURRENT_CONDITIONS_S_A_REBUILD_V1"
DEFAULT_PRICE_SOURCE = (
    Path("outputs")
    / "morita_2023_rs_warmup_retest_v1"
    / "input"
    / "morita_baseline_2022warmup_2023_2026_v1"
    / "sources"
    / "daily_ohlcv_merged.csv"
)
FALLBACK_PRICE_SOURCE = (
    Path("market_bomb_history")
    / "morita_bot_historical_baseline_v1"
    / "input"
    / "morita_baseline_2023_2026_v1"
    / "sources"
    / "daily_ohlcv_merged.csv"
)

GUARDRAILS = {
    "research_only": True,
    "execution_allowed": False,
    "live_order_allowed": False,
    "order_preview_allowed": False,
    "account_data_access_allowed": False,
    "options_modeled": False,
    "performance_calculated": False,
    "future_information_allowed": False,
    "threshold_optimization_allowed": False,
    "production_code_changed": False,
    "signal_scope": SIGNAL_SCOPE,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def long_path(path: Path) -> str:
    resolved = os.path.abspath(str(path))
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def add_safety(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for key, value in GUARDRAILS.items():
        out[key] = value
    return out


def load_prices(repo_root: Path, source: Path | None) -> tuple[pd.DataFrame, Path]:
    path = source or (repo_root / DEFAULT_PRICE_SOURCE)
    if not path.exists():
        path = repo_root / FALLBACK_PRICE_SOURCE
    if not path.exists():
        raise FileNotFoundError(f"daily OHLCV source not found: {path}")
    df = pd.read_csv(long_path(path), usecols=["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["ticker"] = df["ticker"].astype(str).str.upper()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "ticker", "high", "close", "volume"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    return df, path


def compute_features(prices: pd.DataFrame, benchmark: str = "QQQ") -> pd.DataFrame:
    df = prices.copy()
    g = df.groupby("ticker", group_keys=False)
    df["prior_20d_high"] = g["high"].transform(lambda s: s.rolling(20, min_periods=20).max().shift(1))
    df["avg_volume_50d"] = g["volume"].transform(lambda s: s.rolling(50, min_periods=50).mean())
    df["prev_close"] = g["close"].shift(1)
    df["volume_multiple"] = df["volume"] / df["avg_volume_50d"]
    df["gap_pct"] = df["open"] / df["prev_close"] - 1.0
    df["breakout20"] = df["close"] > df["prior_20d_high"]
    df["breakout_excess_pct"] = df["close"] / df["prior_20d_high"] - 1.0
    for days in [63, 126, 252]:
        df[f"ret_{days}d"] = g["close"].transform(lambda s, d=days: s / s.shift(d) - 1.0)

    bench = df[df["ticker"].eq(benchmark)][["date", "ret_63d", "ret_126d", "ret_252d"]].rename(
        columns={"ret_63d": "bench_ret_63d", "ret_126d": "bench_ret_126d", "ret_252d": "bench_ret_252d"}
    )
    df = df.merge(bench, on="date", how="left")
    df["standard_rs_raw"] = (
        0.5 * (df["ret_126d"] - df["bench_ret_126d"])
        + 0.3 * (df["ret_63d"] - df["bench_ret_63d"])
        + 0.2 * (df["ret_252d"] - df["bench_ret_252d"])
    )
    df["standard_rs_score"] = df.groupby("date")["standard_rs_raw"].rank(pct=True, method="average") * 100.0
    return df


def production_live_score(row: pd.Series) -> float:
    rs = float(row.get("standard_rs_score", 0.0) or 0.0)
    volume = float(row.get("volume_multiple", 0.0) or 0.0)
    price = float(row.get("close", math.nan))
    prior_high = float(row.get("prior_20d_high", math.nan))
    score = 0.0
    if rs >= 99.5:
        score += 25
    elif rs >= 99:
        score += 22
    elif rs >= 98:
        score += 20
    else:
        score += max(0.0, min(20.0, (rs - 90.0) / 8.0 * 20.0))

    if volume >= 3.0:
        score += 15
    elif volume >= 2.0:
        score += 13
    elif volume >= 1.5:
        score += 10
    elif volume >= 1.2:
        score += 7

    if math.isfinite(price) and math.isfinite(prior_high) and prior_high > 0 and price > prior_high:
        excess = price / prior_high - 1.0
        if excess >= 0.10:
            score += 15
        elif excess >= 0.05:
            score += 12
        elif excess >= 0.02:
            score += 9
        else:
            score += 7

    score += 5
    score += 2
    return max(0.0, score)


def rank_from_score(score: float) -> str:
    if score >= 50:
        return "S"
    if score >= 40:
        return "A"
    if score >= 30:
        return "B"
    if score >= 25:
        return "C"
    return "D"


def rebuild_signals(features: pd.DataFrame, start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    window = features[features["date"].between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    window["base_candidate"] = (
        window["standard_rs_score"].ge(98)
        & window["breakout20"].fillna(False)
        & window["volume_multiple"].ge(1.2)
        & window["close"].ge(5.0)
        & window["avg_volume_50d"].ge(500_000)
    )
    candidates = window[window["base_candidate"]].copy()
    if candidates.empty:
        signals = pd.DataFrame()
    else:
        candidates["production_live_score"] = candidates.apply(production_live_score, axis=1)
        candidates["volume_penalty"] = candidates["volume_multiple"].apply(lambda v: -5.0 if pd.notna(v) and float(v) < 1.5 else 0.0)
        candidates["production_adjusted_score"] = (candidates["production_live_score"] + candidates["volume_penalty"]).clip(lower=0)
        candidates["alert_rank"] = candidates["production_adjusted_score"].apply(rank_from_score)
        candidates["exclusion_reason"] = ""
        candidates.loc[candidates["gap_pct"].ge(0.10), "exclusion_reason"] = "excluded_gap_ge_10"
        candidates.loc[candidates["close"].lt(5.0), "exclusion_reason"] = "excluded_price_lt_5"
        candidates.loc[candidates["production_adjusted_score"].lt(25), "exclusion_reason"] = "excluded_production_adjusted_score_lt_25"
        signals = candidates[candidates["alert_rank"].isin(["S", "A"]) & candidates["exclusion_reason"].eq("")].copy()
        signals["signal_id"] = signals.apply(lambda r: f"current_sa_{r['date'].date().isoformat()}_{r['ticker']}_{r['alert_rank']}", axis=1)
        signals["decision_date"] = signals["date"].dt.date.astype(str)
        signals["decision_timestamp_et"] = signals["decision_date"] + " 16:00:00 ET"
        signals["data_source"] = "daily_ohlcv_merged.csv"
        signals["method"] = "current production-style S/A rerun from underlying daily prices; no performance"
        signals["pit_note"] = "static/proxy universe and local OHLCV; not formal survivorship-safe Phase B"

    daily_counts = (
        signals.groupby(["decision_date", "alert_rank"]).size().reset_index(name="signal_count")
        if not signals.empty
        else pd.DataFrame(columns=["decision_date", "alert_rank", "signal_count"])
    )
    return signals, candidates, daily_counts


def build_review(signals: pd.DataFrame, candidates: pd.DataFrame, source: Path, out: Path) -> str:
    s_count = int(signals["alert_rank"].eq("S").sum()) if not signals.empty else 0
    a_count = int(signals["alert_rank"].eq("A").sum()) if not signals.empty else 0
    years = signals.assign(year=pd.to_datetime(signals["decision_date"]).dt.year).groupby(["year", "alert_rank"]).size().reset_index(name="n") if not signals.empty else pd.DataFrame()
    year_lines = ["none"] if years.empty else [f"- {int(r.year)} {r.alert_rank}: {int(r.n)}" for r in years.itertuples()]
    return "\n".join(
        [
            "# Morita Current Conditions S/A Rebuild v1",
            "",
            "Purpose: Rebuild S/A only by applying current production-style Morita conditions to existing daily underlying prices. No performance backtest.",
            "",
            f"Price source: `{source}`",
            f"Output directory: `{out}`",
            "",
            f"S signals: {s_count}",
            f"A signals: {a_count}",
            f"All base candidates before S/A filter: {len(candidates)}",
            "",
            "By year/rank:",
            *year_lines,
            "",
            "Important caveats:",
            "- This is not a performance backtest.",
            "- This does not model options.",
            "- This does not place or preview orders.",
            "- Universe is local/static/proxy where applicable, not formal Phase B survivorship-safe historical universe.",
            "- A literal A+ rank is not generated here; this run is S and A only.",
            "",
        ]
    )


def run(repo_root: Path, start: str, end: str, source: Path | None = None, output_root: Path | None = None, run_id: str | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    run_id = run_id or utc_stamp()
    out = (output_root or repo_root / OUTPUT_ROOT) / run_id
    out.mkdir(parents=True, exist_ok=True)
    prices, source_path = load_prices(repo_root, source)
    features = compute_features(prices)
    signals, candidates, daily_counts = rebuild_signals(features, start, end)

    signal_columns = [
        "signal_id",
        "decision_date",
        "decision_timestamp_et",
        "ticker",
        "alert_rank",
        "production_adjusted_score",
        "production_live_score",
        "volume_penalty",
        "standard_rs_score",
        "standard_rs_raw",
        "close",
        "prior_20d_high",
        "breakout_excess_pct",
        "volume",
        "avg_volume_50d",
        "volume_multiple",
        "gap_pct",
        "exclusion_reason",
        "data_source",
        "method",
        "pit_note",
    ]
    for col in signal_columns:
        if col not in signals.columns:
            signals[col] = ""
    add_safety(signals[signal_columns]).to_csv(long_path(out / "current_conditions_sa_signal_calendar.csv"), index=False)
    add_safety(candidates).to_parquet(long_path(out / "current_conditions_sa_all_base_candidates.parquet"), index=False)
    add_safety(daily_counts).to_csv(long_path(out / "current_conditions_sa_daily_counts.csv"), index=False)
    write_text(out / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker", "\n".join(f"{k}={str(v).lower()}" for k, v in GUARDRAILS.items()) + "\n")
    write_text(out / "morita_current_conditions_sa_rebuild_v1_chatgpt_review_bundle.md", build_review(signals, candidates, source_path, out))
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "output_dir": str(out),
        "price_source": str(source_path),
        "start": start,
        "end": end,
        "signal_rows": int(len(signals)),
        "s_count": int(signals["alert_rank"].eq("S").sum()) if not signals.empty else 0,
        "a_count": int(signals["alert_rank"].eq("A").sum()) if not signals.empty else 0,
        "base_candidate_rows": int(len(candidates)),
        "terminal_statuses": ["CURRENT_CONDITIONS_S_A_REBUILT", "NO_PERFORMANCE_CALCULATED", "NO_USER_ACTION_REQUIRED"],
        "guardrails": GUARDRAILS,
    }
    write_json(out / "run_receipt.json", receipt)
    write_json(out / "run_manifest.json", {"files": sorted(p.name for p in out.iterdir() if p.is_file()), **receipt})
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Morita S/A signals from current production-style conditions and daily underlying prices.")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2026-12-31")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    receipt = run(repo_root, args.start, args.end, source=args.source, output_root=args.output_root)
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
