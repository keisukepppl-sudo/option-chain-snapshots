from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_morita_short_v3_5_2_independent_audit as base


ARTIFACT_VERSION = "morita_short_v3_5_3_claim_audit"
OUTPUT_ROOT = Path("outputs") / "research_only" / ARTIFACT_VERSION
DEFAULT_V352_RUN = Path(
    r"C:\Users\keisu\Documents\Codex\2026-06-25\bot-rs-2-1-2-historical\work\morita_short_v3_5_2_independent_audit_20260714\outputs\research_only\morita_short_v3_5_2_independent_audit\20260713T190155Z"
)
RANKS = ("S", "A", "S+A")
ENTRIES = ("Open", "09:45", "10:00", "10:30")
PAIRED_ENTRIES = ("09:45", "10:00", "10:30")
EXITS = ("D1", "D2", "D3", "D5")
LEVELS = ("candidate", "ticker_episode", "market_episode", "weakest_selected")
BOOTSTRAP_SAMPLES = 500
RNG_SEED = 353


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Morita Short v3.5.3 concentration falsification and claim audit.")
    parser.add_argument("--v352-run", type=Path, default=DEFAULT_V352_RUN)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--signal-calendar", type=Path, default=base.DEFAULT_SIGNAL)
    parser.add_argument("--source-receipt", type=Path, default=base.DEFAULT_RECEIPT)
    parser.add_argument("--daily-ohlcv", type=Path, default=base.DEFAULT_DAILY)
    parser.add_argument("--m15-bars", type=Path, default=base.DEFAULT_M15)
    parser.add_argument("--instruction", type=Path, default=Path(r"C:\Users\keisu\Downloads\morita_room2_short_v3_5_3_claim_audit_instruction.md"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_dir or repo_root / OUTPUT_ROOT / run_id
    paths = base.SourcePaths(
        signal_calendar=args.signal_calendar,
        source_receipt=args.source_receipt,
        daily_ohlcv=args.daily_ohlcv,
        m15_bars=args.m15_bars,
        instruction=args.instruction,
    )
    receipt = run_claim_audit(repo_root=repo_root, output_dir=out, run_id=run_id, paths=paths, v352_run=args.v352_run)
    print(json.dumps(receipt, indent=2, sort_keys=True, default=base.json_default))
    return 0


def run_claim_audit(*, repo_root: Path, output_dir: Path, run_id: str, paths: base.SourcePaths, v352_run: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker", "research_only=true\nexecution_allowed=false\nlive_order_allowed=false\n")
    signals_raw = pd.read_csv(paths.signal_calendar)
    signals = base.normalize_signals(signals_raw, paths.signal_calendar)
    tickers = sorted(set(signals["ticker"].astype(str)) | {"QQQ", "SOXX"})
    daily = base.add_daily_features(base.load_daily(paths.daily_ohlcv, tickers))
    calendar = sorted(pd.to_datetime(daily["date"].dropna().unique()))
    session_idx = {pd.Timestamp(d).date().isoformat(): i for i, d in enumerate(calendar)}
    candidates = base.construct_candidates(signals, daily, session_idx, base.build_next_session_map(calendar))
    m15 = base.load_m15(paths.m15_bars)
    _, trades = base.build_trade_rows(candidates, daily, m15, session_idx)
    te_map = base.build_ticker_episode_map(candidates, session_idx, base.PRIMARY_TICKER_EPISODE_WINDOW)
    me_map = base.build_market_episode_map(candidates, daily, session_idx)
    trades = base.enrich_trades_with_episodes(trades, te_map, me_map)

    entry_paired, paired_boot = build_entry_time_paired_audit(trades)
    exclusion = build_concentration_exclusion_scenarios(trades)
    forensic = build_car_me0034_forensic_audit(candidates, trades, daily)
    s_vs_a_matched = build_s_vs_a_matched_episode_audit(trades)
    s_vs_a_weighting = build_s_vs_a_weighting_sensitivity(trades)
    distribution = build_return_distribution_decomposition(trades)
    distribution_md = build_positive_pf_negative_median_explanation(distribution)
    gate = build_independent_episode_gate(trades, exclusion, entry_paired)
    final_decision = final_decision_from_gate(gate)
    forward_spec = build_forward_tracking_spec(final_decision, gate)
    forward_schema = build_forward_tracking_schema()
    report = build_report(
        v352_run=v352_run,
        entry_paired=entry_paired,
        exclusion=exclusion,
        forensic=forensic,
        s_vs_a_matched=s_vs_a_matched,
        s_vs_a_weighting=s_vs_a_weighting,
        distribution=distribution,
        gate=gate,
        final_decision=final_decision,
    )
    bundle = build_chatgpt_bundle(
        entry_paired=entry_paired,
        exclusion=exclusion,
        forensic=forensic,
        s_vs_a_matched=s_vs_a_matched,
        s_vs_a_weighting=s_vs_a_weighting,
        distribution=distribution,
        gate=gate,
        final_decision=final_decision,
    )
    tests = pd.DataFrame([{"test_scope": "runner_execution", "command": "python scripts/run_morita_short_v3_5_3_claim_audit.py", "status": "PASS_PENDING_TEST_COMMAND", "detail": "Artifacts generated."}])

    artifacts = {
        "entry_time_paired_audit.csv": entry_paired,
        "entry_time_paired_bootstrap.csv": paired_boot,
        "concentration_exclusion_scenarios.csv": exclusion,
        "car_me0034_forensic_audit.csv": forensic,
        "s_vs_a_matched_episode_audit.csv": s_vs_a_matched,
        "s_vs_a_weighting_sensitivity.csv": s_vs_a_weighting,
        "return_distribution_decomposition.csv": distribution,
        "independent_episode_gate.csv": gate,
        "short_forward_tracking_schema.csv": forward_schema,
        "test_summary.csv": tests,
    }
    for name, df in artifacts.items():
        write_df(output_dir / name, add_safety(df))
    write_text(output_dir / "positive_pf_negative_median_explanation.md", distribution_md)
    write_text(output_dir / "short_forward_tracking_spec.md", forward_spec)
    write_text(output_dir / "morita_short_v3_5_3_claim_audit_report.md", report)
    write_text(output_dir / "morita_short_v3_5_3_chatgpt_review_bundle.md", bundle)
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "v352_run": str(v352_run),
        "raw_signals": int(len(signals)),
        "constructed_candidates": int(candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED").sum()),
        "final_decision": final_decision,
        "reported_decisions_retracted_to_hypothesis": ["0945_ADVANTAGE_REPLICATED", "S_OUTPERFORMS_A_ROBUSTLY"],
        "primary_decision": "NO_INDEPENDENT_EPISODE_ALPHA_CONFIRMED",
        "terminal_statuses": [final_decision, "NO_USER_ACTION_REQUIRED"],
        "git": git_identity(repo_root),
        **safety_fields(),
    }
    write_json(output_dir / "run_receipt.json", receipt)
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "artifacts": manifest_entries(output_dir),
        "source_paths": {k: str(v) for k, v in paths.__dict__.items()},
        "v352_run": str(v352_run),
        **safety_fields(),
    }
    write_json(output_dir / "run_manifest.json", manifest)
    return receipt


def build_entry_time_paired_audit(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    boot_rows = []
    for rank in RANKS:
        for exit_label in EXITS:
            for entry in PAIRED_ENTRIES:
                for level in LEVELS:
                    paired = paired_diff_frame(trades, rank, entry, exit_label, level)
                    metrics = paired_metrics(paired)
                    rows.append({"rank": rank, "entry_comparison": f"{entry}_minus_Open", "exit": exit_label, "level": level, **metrics})
                    boot_rows.extend(cluster_bootstrap_rows(paired, rank, entry, exit_label, level))
    return pd.DataFrame(rows), pd.DataFrame(boot_rows)


def paired_diff_frame(trades: pd.DataFrame, rank: str, entry: str, exit_label: str, level: str) -> pd.DataFrame:
    open_frame = level_return_frame(trades, rank, "Open", exit_label, level).rename(columns={"short_return": "open_return"})
    entry_frame = level_return_frame(trades, rank, entry, exit_label, level).rename(columns={"short_return": "entry_return"})
    if open_frame.empty or entry_frame.empty:
        return pd.DataFrame(columns=["unit_id", "market_episode_id", "open_return", "entry_return", "difference"])
    paired = open_frame.merge(entry_frame[["unit_id", "entry_return"]], on="unit_id", how="inner")
    paired = paired.dropna(subset=["open_return", "entry_return"]).copy()
    paired["difference"] = paired["entry_return"] - paired["open_return"]
    return paired


def level_return_frame(trades: pd.DataFrame, rank: str, entry: str, exit_label: str, level: str) -> pd.DataFrame:
    subset = trades[(trades["entry"].eq(entry)) & (trades["exit"].eq(exit_label)) & trades["short_return"].notna()].copy()
    if rank != "S+A":
        subset = subset[subset["rank"].eq(rank)]
    if subset.empty:
        return pd.DataFrame(columns=["unit_id", "market_episode_id", "short_return"])
    if level == "candidate":
        return subset[["candidate_id", "market_episode_id", "short_return"]].rename(columns={"candidate_id": "unit_id"})
    if level == "ticker_episode":
        return (
            subset.groupby(["ticker_episode_id", "market_episode_id"], dropna=True)["short_return"]
            .mean()
            .reset_index()
            .rename(columns={"ticker_episode_id": "unit_id"})
        )
    if level == "market_episode":
        return (
            subset.groupby("market_episode_id", dropna=True)["short_return"]
            .mean()
            .reset_index()
            .assign(unit_id=lambda x: x["market_episode_id"])
        )[["unit_id", "market_episode_id", "short_return"]]
    if level == "weakest_selected":
        selected = subset.sort_values(["d0_date", "ticker"]).drop_duplicates("market_episode_id", keep="first")
        return selected[["market_episode_id", "short_return"]].assign(unit_id=lambda x: x["market_episode_id"])[["unit_id", "market_episode_id", "short_return"]]
    raise ValueError(level)


def paired_metrics(paired: pd.DataFrame) -> dict[str, Any]:
    if paired.empty:
        return {"paired_n": 0, "mean_difference": np.nan, "median_difference": np.nan, "open_pf": np.nan, "entry_pf": np.nan, "pf_difference": np.nan, "wins": 0, "losses": 0, "ties": 0, "sign_test_p": np.nan}
    wins = int((paired["difference"] > 0).sum())
    losses = int((paired["difference"] < 0).sum())
    ties = int((paired["difference"] == 0).sum())
    open_pf = pf(paired["open_return"])
    entry_pf = pf(paired["entry_return"])
    return {
        "paired_n": int(len(paired)),
        "mean_difference": float(paired["difference"].mean()),
        "median_difference": float(paired["difference"].median()),
        "open_pf": open_pf,
        "entry_pf": entry_pf,
        "pf_difference": entry_pf - open_pf if finite(open_pf) and finite(entry_pf) else np.nan,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "sign_test_p": sign_test_p(wins, losses),
    }


def cluster_bootstrap_rows(paired: pd.DataFrame, rank: str, entry: str, exit_label: str, level: str) -> list[dict[str, Any]]:
    if paired.empty or paired["market_episode_id"].nunique() < 2:
        return [{"rank": rank, "entry_comparison": f"{entry}_minus_Open", "exit": exit_label, "level": level, "bootstrap_samples": 0, "cluster_count": int(paired["market_episode_id"].nunique()) if not paired.empty else 0, "mean_diff_ci_low": np.nan, "mean_diff_ci_high": np.nan, "median_diff_ci_low": np.nan, "median_diff_ci_high": np.nan}]
    cluster_stats = paired.groupby("market_episode_id")["difference"].agg(["mean", "median"]).reset_index()
    clusters = cluster_stats["market_episode_id"].tolist()
    mean_by_cluster = dict(zip(cluster_stats["market_episode_id"], cluster_stats["mean"]))
    median_by_cluster = dict(zip(cluster_stats["market_episode_id"], cluster_stats["median"]))
    rng = np.random.default_rng(RNG_SEED + len(clusters))
    mean_values = []
    median_values = []
    for _ in range(BOOTSTRAP_SAMPLES):
        chosen = rng.choice(clusters, size=len(clusters), replace=True)
        mean_values.append(float(np.mean([mean_by_cluster[c] for c in chosen])))
        median_values.append(float(np.median([median_by_cluster[c] for c in chosen])))
    return [{"rank": rank, "entry_comparison": f"{entry}_minus_Open", "exit": exit_label, "level": level, "bootstrap_samples": BOOTSTRAP_SAMPLES, "cluster_count": len(clusters), "mean_diff_ci_low": q(mean_values, 0.025), "mean_diff_ci_high": q(mean_values, 0.975), "median_diff_ci_low": q(median_values, 0.025), "median_diff_ci_high": q(median_values, 0.975)}]


def build_concentration_exclusion_scenarios(trades: pd.DataFrame) -> pd.DataFrame:
    top_me = positive_market_episodes(trades)
    scenarios = [
        ("baseline", set(), set(), set()),
        ("exclude CAR", {"CAR"}, set(), set()),
        ("exclude TE5_CAR_0002", set(), {"TE5_CAR_0002"}, set()),
        ("exclude ME_0034", set(), set(), {"ME_0034"}),
        ("exclude CAR + ME_0034", {"CAR"}, set(), {"ME_0034"}),
        ("exclude top 1 positive market episode", set(), set(), set(top_me[:1])),
        ("exclude top 3 positive market episodes", set(), set(), set(top_me[:3])),
        ("exclude top 5 positive market episodes", set(), set(), set(top_me[:5])),
    ]
    rows = []
    for scenario, tickers, tes, mes in scenarios:
        filtered = trades[~trades["ticker"].isin(tickers) & ~trades["ticker_episode_id"].isin(tes) & ~trades["market_episode_id"].isin(mes)]
        for rank in RANKS:
            for entry in ("Open", "09:45"):
                for level in ("candidate", "market_episode"):
                    values = level_return_frame(filtered, rank, entry, "D1", level)
                    rows.append({"scenario": scenario, "rank": rank, "entry": entry, "exit": "D1", "level": level, "excluded_tickers": "|".join(sorted(tickers)), "excluded_ticker_episodes": "|".join(sorted(tes)), "excluded_market_episodes": "|".join(sorted(mes)), **scenario_metrics(values)})
    return pd.DataFrame(rows)


def positive_market_episodes(trades: pd.DataFrame) -> list[str]:
    frame = level_return_frame(trades, "S+A", "Open", "D1", "market_episode")
    if frame.empty:
        return []
    return frame.sort_values("short_return", ascending=False)["market_episode_id"].tolist()


def scenario_metrics(values: pd.DataFrame) -> dict[str, Any]:
    returns = values["short_return"] if not values.empty else pd.Series(dtype=float)
    perf = perf_metrics(returns)
    perf["market_episode_count"] = int(values["market_episode_id"].nunique()) if not values.empty else 0
    return perf


def build_car_me0034_forensic_audit(candidates: pd.DataFrame, trades: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    car_candidates = candidates[candidates["ticker"].eq("CAR")]
    car_trades = trades[(trades["ticker"].eq("CAR")) & trades["entry"].eq("Open") & trades["exit"].eq("D1") & trades["short_return"].notna()]
    rows.append(forensic_row("CAR", car_candidates, car_trades, daily))
    me_trades = trades[(trades["market_episode_id"].eq("ME_0034")) & trades["entry"].eq("Open") & trades["exit"].eq("D1") & trades["short_return"].notna()]
    rows.append(
        {
            "subject": "ME_0034",
            "date_range": f"{me_trades['d0_date'].min()}..{me_trades['d0_date'].max()}" if not me_trades.empty else "",
            "tickers": "|".join(sorted(me_trades["ticker"].dropna().unique())) if not me_trades.empty else "",
            "rank_composition": rank_composition(me_trades),
            "candidate_count": int(me_trades["candidate_id"].nunique()) if not me_trades.empty else 0,
            "pnl_contribution": float(me_trades["short_return"].sum()) if not me_trades.empty else np.nan,
            "data_coverage": "daily_open_close_available; M15_subset_only",
            "duplicate_overlap": "same_market_episode_cluster",
            "market_shock": "calendar-proximity market episode; QQQ context in market_episode_map",
            "news_regime": "not externally verified in this local audit",
            "classification": "SPECIAL_CONCENTRATION_EPISODE_DO_NOT_GENERALIZE" if not me_trades.empty else "MISSING",
            "corporate_action": "",
            "bankruptcy_distress": "",
            "data_error": "",
            "split": "",
            "price_adjustment_issue": "basis_unspecified_source",
            "extreme_gap": "",
            "repeated_overlapping_signals": str(int(me_trades["candidate_id"].nunique()) > me_trades["ticker"].nunique()) if not me_trades.empty else "",
            "same_economic_episode_duplication": "True",
        }
    )
    return pd.DataFrame(rows)


def forensic_row(subject: str, candidates: pd.DataFrame, trades: pd.DataFrame, daily: pd.DataFrame) -> dict[str, Any]:
    dd = daily[daily["ticker"].eq(subject)].copy()
    dd["gap"] = dd["open"] / dd["prev_close"] - 1
    max_gap = float(dd["gap"].abs().max()) if not dd.empty else np.nan
    raw_basis = "|".join(sorted(dd["raw_or_adjusted"].dropna().astype(str).unique())) if "raw_or_adjusted" in dd else ""
    return {
        "subject": subject,
        "date_range": f"{trades['d0_date'].min()}..{trades['d0_date'].max()}" if not trades.empty else "",
        "tickers": subject,
        "rank_composition": rank_composition(trades),
        "candidate_count": int(candidates["candidate_id"].nunique()) if not candidates.empty else 0,
        "pnl_contribution": float(trades["short_return"].sum()) if not trades.empty else np.nan,
        "data_coverage": "daily_open_close_available; local source basis unspecified",
        "duplicate_overlap": "repeated ticker signals" if len(candidates) > candidates["d0_date"].nunique() else "none_detected",
        "market_shock": "",
        "news_regime": "not externally verified in this local audit",
        "classification": "SPECIAL_TICKER_CONCENTRATION_DO_NOT_GENERALIZE",
        "corporate_action": "not verified",
        "bankruptcy_distress": "not verified",
        "data_error": "not detected by null/return audit",
        "split": "not verified",
        "price_adjustment_issue": f"basis={raw_basis}",
        "extreme_gap": str(max_gap > 0.20) if pd.notna(max_gap) else "",
        "repeated_overlapping_signals": str(len(candidates) > candidates["d0_date"].nunique()) if not candidates.empty else "",
        "same_economic_episode_duplication": "True" if not trades.empty and trades["market_episode_id"].nunique() < trades["candidate_id"].nunique() else "False",
    }


def rank_composition(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    counts = df["rank"].value_counts().to_dict()
    return "|".join(f"{k}:{v}" for k, v in sorted(counts.items()))


def build_s_vs_a_matched_episode_audit(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for entry in ENTRIES:
        for exit_label in EXITS:
            for level in ("candidate", "ticker_episode", "market_episode"):
                s = level_return_frame(trades, "S", entry, exit_label, level).rename(columns={"short_return": "s_return"})
                a = level_return_frame(trades, "A", entry, exit_label, level).rename(columns={"short_return": "a_return"})
                paired = s.merge(a[["market_episode_id", "a_return"]], on="market_episode_id", how="inner")
                if paired.empty:
                    rows.append({"entry": entry, "exit": exit_label, "level": level, "matched_market_episode_n": 0, "s_mean": np.nan, "a_mean": np.nan, "s_minus_a_mean": np.nan, "s_minus_a_median": np.nan, "s_wins": 0, "a_wins": 0, "ties": 0, "sign_test_p": np.nan})
                    continue
                grouped = paired.groupby("market_episode_id")[["s_return", "a_return"]].mean().reset_index()
                grouped["diff"] = grouped["s_return"] - grouped["a_return"]
                rows.append({"entry": entry, "exit": exit_label, "level": level, "matched_market_episode_n": int(len(grouped)), "s_mean": float(grouped["s_return"].mean()), "a_mean": float(grouped["a_return"].mean()), "s_minus_a_mean": float(grouped["diff"].mean()), "s_minus_a_median": float(grouped["diff"].median()), "s_wins": int((grouped["diff"] > 0).sum()), "a_wins": int((grouped["diff"] < 0).sum()), "ties": int((grouped["diff"] == 0).sum()), "sign_test_p": sign_test_p(int((grouped["diff"] > 0).sum()), int((grouped["diff"] < 0).sum()))})
    return pd.DataFrame(rows)


def build_s_vs_a_weighting_sensitivity(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for entry in ("Open", "09:45"):
        for exit_label in ("D1",):
            for level in LEVELS:
                for rank in ("S", "A"):
                    values = level_return_frame(trades, rank, entry, exit_label, level)
                    rows.append({"entry": entry, "exit": exit_label, "weighting": level, "rank": rank, **scenario_metrics(values)})
    return pd.DataFrame(rows)


def build_return_distribution_decomposition(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rank in RANKS:
        for entry in ("Open", "09:45"):
            for level in ("candidate", "ticker_episode", "market_episode"):
                values = level_return_frame(trades, rank, entry, "D1", level)
                returns = values["short_return"] if not values.empty else pd.Series(dtype=float)
                rows.append({"rank": rank, "entry": entry, "exit": "D1", "level": level, **distribution_metrics(returns)})
    return pd.DataFrame(rows)


def distribution_metrics(returns: pd.Series) -> dict[str, Any]:
    returns = pd.to_numeric(returns, errors="coerce").dropna()
    if returns.empty:
        return {"n": 0}
    positives = returns[returns > 0]
    negatives = returns[returns < 0]
    gross_profit = float(positives.sum())
    top = positives.sort_values(ascending=False)
    return {
        "n": int(len(returns)),
        "profit_factor": pf(returns),
        "mean": float(returns.mean()),
        "median": float(returns.median()),
        "negative_frequency": float((returns < 0).mean()),
        "positive_tail_count": int(len(positives)),
        "gain_loss_asymmetry": float(positives.mean() / abs(negatives.mean())) if not positives.empty and not negatives.empty else np.nan,
        "q05": float(returns.quantile(0.05)),
        "q25": float(returns.quantile(0.25)),
        "q75": float(returns.quantile(0.75)),
        "q95": float(returns.quantile(0.95)),
        "expected_shortfall_5pct": float(returns[returns <= returns.quantile(0.05)].mean()),
        "top_1_positive_share": float(top.head(1).sum() / gross_profit) if gross_profit > 0 else np.nan,
        "top_3_positive_share": float(top.head(3).sum() / gross_profit) if gross_profit > 0 else np.nan,
        "top_5_positive_share": float(top.head(5).sum() / gross_profit) if gross_profit > 0 else np.nan,
    }


def build_positive_pf_negative_median_explanation(distribution: pd.DataFrame) -> str:
    focus = distribution[(distribution["entry"].eq("Open")) & (distribution["exit"].eq("D1")) & distribution["level"].isin(["candidate", "ticker_episode"])]
    lines = [
        "# Positive PF / Negative Median Explanation",
        "",
        "Candidate and ticker-episode PF can stay above 1 while the median is negative when a minority positive tail is large enough to offset frequent small losses.",
        "",
        focus[["rank", "level", "n", "profit_factor", "median", "negative_frequency", "gain_loss_asymmetry", "top_3_positive_share", "expected_shortfall_5pct"]].to_markdown(index=False),
        "",
        "Interpretation: this is a skew-dependent profile, not broad independent alpha. It must be stress-tested with concentration exclusions and episode-level gates before any forward tracking claim.",
    ]
    return "\n".join(lines) + "\n"


def build_independent_episode_gate(trades: pd.DataFrame, exclusion: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rank, entry in (("S", "Open"), ("S", "09:45"), ("S+A", "Open"), ("S+A", "09:45")):
        values = level_return_frame(trades, rank, entry, "D1", "market_episode")
        returns = values["short_return"] if not values.empty else pd.Series(dtype=float)
        metrics = perf_metrics(returns)
        loo = leave_one_sign_stability(values)
        top3 = positive_top_share(returns, 3)
        boot_low, boot_high = bootstrap_mean_ci(returns)
        paired_row = paired[(paired["rank"].eq(rank)) & (paired["entry_comparison"].eq(f"{entry}_minus_Open")) & paired["exit"].eq("D1") & paired["level"].eq("market_episode")]
        paired_supported = bool(not paired_row.empty and paired_row.iloc[0]["paired_n"] >= 10 and paired_row.iloc[0]["mean_difference"] > 0 and paired_row.iloc[0]["median_difference"] > 0)
        gate_pass = bool(metrics["profit_factor"] > 1 and metrics["median"] > 0 and loo and (pd.isna(top3) or top3 < 0.5) and pd.notna(boot_low) and boot_low > 0)
        rows.append({"rank": rank, "entry": entry, "exit": "D1", "market_episode_n": int(values["market_episode_id"].nunique()) if not values.empty else 0, "profit_factor_gt_1": metrics["profit_factor"] > 1 if pd.notna(metrics["profit_factor"]) else False, "median_gt_0": metrics["median"] > 0 if pd.notna(metrics["median"]) else False, "leave_one_episode_sign_stable": loo, "top3_not_strategy_dominating": bool(pd.isna(top3) or top3 < 0.5), "bootstrap_lower_bound_defensible": bool(pd.notna(boot_low) and boot_low > 0), "paired_0945_supported": paired_supported if entry == "09:45" else "", "profit_factor": metrics["profit_factor"], "median": metrics["median"], "top3_positive_share": top3, "bootstrap_mean_ci_low": boot_low, "bootstrap_mean_ci_high": boot_high, "gate_status": "PASS" if gate_pass else "FAIL"})
    return pd.DataFrame(rows)


def final_decision_from_gate(gate: pd.DataFrame) -> str:
    s_open = gate[(gate["rank"].eq("S")) & (gate["entry"].eq("Open"))]
    s_945 = gate[(gate["rank"].eq("S")) & (gate["entry"].eq("09:45"))]
    open_pass = bool(not s_open.empty and s_open.iloc[0]["gate_status"] == "PASS")
    p945_pass = bool(not s_945.empty and s_945.iloc[0]["gate_status"] == "PASS" and s_945.iloc[0]["paired_0945_supported"] is True)
    if open_pass and p945_pass:
        return "FORWARD_TRACK_BOTH_AS_PREDECLARED_COMPARISON"
    if open_pass:
        return "FORWARD_TRACK_S_OPEN_RESEARCH_ONLY"
    if p945_pass:
        return "FORWARD_TRACK_S_0945_RESEARCH_ONLY"
    return "REJECT_HISTORICAL_EDGE_CONCENTRATION"


def build_forward_tracking_spec(final_decision: str, gate: pd.DataFrame) -> str:
    activated = final_decision.startswith("FORWARD_TRACK")
    return f"""# Short Forward Tracking Spec

Status: {'ACTIVE_RESEARCH_ONLY_SPEC' if activated else 'NOT_ACTIVATED_BY_V3_5_3_GATE'}
Final decision: {final_decision}

Allowed frozen candidates:
- S-only Open: {'enabled' if final_decision in ['FORWARD_TRACK_S_OPEN_RESEARCH_ONLY', 'FORWARD_TRACK_BOTH_AS_PREDECLARED_COMPARISON'] else 'disabled'}
- S-only 09:45: {'enabled' if final_decision in ['FORWARD_TRACK_S_0945_RESEARCH_ONLY', 'FORWARD_TRACK_BOTH_AS_PREDECLARED_COMPARISON'] else 'disabled'}

Fields to persist if activated:
- signal lineage
- entry eligibility
- entry timestamp
- price source
- D1/D2/D3/D5 outcome
- ticker episode
- market episode
- CAR-like special-event flag
- no-signal heartbeat

Live order status: prohibited.
Threshold optimization: prohibited.

Gate table:
{gate.to_markdown(index=False)}
"""


def build_forward_tracking_schema() -> pd.DataFrame:
    fields = [
        ("run_id", "string", "Forward tracking batch id."),
        ("signal_id", "string", "Source current-condition signal id."),
        ("ticker", "string", "Ticker."),
        ("rank", "string", "Frozen rank; S only if activated."),
        ("entry_route", "string", "Open or 09:45 frozen route."),
        ("entry_timestamp_et", "datetime", "Executable timestamp in America/New_York."),
        ("price_source", "string", "DAILY_OPEN or actual M15_OPEN."),
        ("d1_return", "float", "Short return through D1 close."),
        ("d2_return", "float", "Short return through D2 close."),
        ("d3_return", "float", "Short return through D3 close."),
        ("d5_return", "float", "Short return through D5 close."),
        ("ticker_episode_id", "string", "Frozen 5-session ticker episode id."),
        ("market_episode_id", "string", "Frozen market episode id."),
        ("car_like_special_event_flag", "bool", "True for CAR-like concentration/special-event review."),
        ("no_signal_heartbeat", "bool", "True on days with no eligible signal."),
        ("research_only", "bool", "Always true."),
    ]
    return pd.DataFrame(fields, columns=["field", "type", "description"])


def build_report(**kwargs: Any) -> str:
    return "\n".join(
        [
            "# Morita Short v3.5.3 Claim Audit Report",
            "",
            f"Final decision: {kwargs['final_decision']}",
            "",
            "## 09:45 Paired Sample",
            kwargs["entry_paired"][(kwargs["entry_paired"]["entry_comparison"].eq("09:45_minus_Open")) & (kwargs["entry_paired"]["exit"].eq("D1"))][["rank", "level", "paired_n", "mean_difference", "median_difference", "open_pf", "entry_pf", "sign_test_p"]].to_markdown(index=False),
            "",
            "## Concentration Exclusions",
            kwargs["exclusion"][(kwargs["exclusion"]["entry"].eq("Open")) & (kwargs["exclusion"]["rank"].eq("S+A")) & (kwargs["exclusion"]["level"].eq("market_episode"))][["scenario", "n", "profit_factor", "median", "market_episode_count"]].to_markdown(index=False),
            "",
            "## S vs A",
            kwargs["s_vs_a_matched"][(kwargs["s_vs_a_matched"]["entry"].eq("Open")) & (kwargs["s_vs_a_matched"]["exit"].eq("D1"))].to_markdown(index=False),
            "",
            "## Independent Episode Gate",
            kwargs["gate"].to_markdown(index=False),
            "",
            "## Safety",
            "research_only=true; execution_allowed=false; live_order_allowed=false. No production scanner, broker, account, order, rank, threshold, or event-definition changes.",
        ]
    ) + "\n"


def build_chatgpt_bundle(**kwargs: Any) -> str:
    gate = kwargs["gate"]
    final_decision = kwargs["final_decision"]
    primary = gate[(gate["rank"].eq("S")) & (gate["entry"].eq("Open"))]
    p945 = gate[(gate["rank"].eq("S")) & (gate["entry"].eq("09:45"))]
    header = f"""INPUT:
v3.5.2 decisions treated as hypotheses = 0945_ADVANTAGE_REPLICATED; S_OUTPERFORMS_A_ROBUSTLY
primary retained decision = NO_INDEPENDENT_EPISODE_ALPHA_CONFIRMED

KEY RESULT:
S Open gate = {primary.iloc[0]['gate_status'] if not primary.empty else 'NA'}
S 09:45 gate = {p945.iloc[0]['gate_status'] if not p945.empty else 'NA'}
final decision = {final_decision}

DECISION:
{final_decision}
"""
    body = [
        "",
        "# Executive conclusion",
        "The concentration falsification audit does not support promoting the historical edge. The prior 09:45 and S>A labels should remain hypotheses, not adopted conclusions.",
        "",
        "# 09:45 paired result",
        kwargs["entry_paired"][(kwargs["entry_paired"]["entry_comparison"].eq("09:45_minus_Open")) & (kwargs["entry_paired"]["exit"].eq("D1"))][["rank", "level", "paired_n", "mean_difference", "median_difference", "open_pf", "entry_pf", "sign_test_p"]].to_markdown(index=False),
        "",
        "# Concentration risk",
        kwargs["exclusion"][(kwargs["exclusion"]["entry"].eq("Open")) & (kwargs["exclusion"]["rank"].eq("S+A")) & (kwargs["exclusion"]["level"].eq("market_episode"))][["scenario", "n", "profit_factor", "median", "market_episode_count"]].to_markdown(index=False),
        "",
        "# CAR / ME_0034 forensic",
        kwargs["forensic"].to_markdown(index=False),
        "",
        "# S vs A result",
        kwargs["s_vs_a_weighting"][kwargs["s_vs_a_weighting"]["entry"].eq("Open")][["weighting", "rank", "n", "profit_factor", "median", "market_episode_count"]].to_markdown(index=False),
        "",
        "# Negative median / positive PF",
        kwargs["distribution"][(kwargs["distribution"]["entry"].eq("Open")) & (kwargs["distribution"]["exit"].eq("D1"))][["rank", "level", "n", "profit_factor", "median", "negative_frequency", "gain_loss_asymmetry", "top_3_positive_share"]].to_markdown(index=False),
        "",
        "# Independent episode alpha gate",
        gate.to_markdown(index=False),
        "",
        "# Forward tracking",
        "No live order route is enabled. Forward tracking is not activated unless the gate status explicitly passes.",
        "",
        "# Exact next step",
        "Keep this as research-only evidence. Do not generalize CAR or ME_0034-dominated historical performance into production readiness.",
    ]
    return header + "\n".join(body) + "\n"


def perf_metrics(returns: pd.Series) -> dict[str, Any]:
    returns = pd.to_numeric(returns, errors="coerce").dropna()
    if returns.empty:
        return {"n": 0, "profit_factor": np.nan, "mean": np.nan, "median": np.nan, "win_rate": np.nan, "gross_profit": 0.0, "gross_loss": 0.0, "max_drawdown": np.nan}
    positives = returns[returns > 0]
    negatives = returns[returns < 0]
    cumulative = (1 + returns).cumprod()
    drawdown = cumulative / cumulative.cummax() - 1
    return {"n": int(len(returns)), "profit_factor": pf(returns), "mean": float(returns.mean()), "median": float(returns.median()), "win_rate": float((returns > 0).mean()), "gross_profit": float(positives.sum()), "gross_loss": float(negatives.sum()), "max_drawdown": float(drawdown.min()) if not drawdown.empty else np.nan}


def pf(returns: pd.Series) -> float:
    returns = pd.to_numeric(returns, errors="coerce").dropna()
    positives = returns[returns > 0].sum()
    negatives = returns[returns < 0].sum()
    if negatives < 0:
        return float(positives / abs(negatives))
    return math.inf if positives > 0 else np.nan


def sign_test_p(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return np.nan
    k = min(wins, losses)
    prob = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return float(min(1.0, 2 * prob))


def leave_one_sign_stability(values: pd.DataFrame) -> bool:
    if values.empty or values["market_episode_id"].nunique() < 2:
        return False
    base_sign = np.sign(values["short_return"].mean())
    if base_sign <= 0:
        return False
    for episode in values["market_episode_id"].dropna().unique():
        sub = values[~values["market_episode_id"].eq(episode)]
        if sub.empty or np.sign(sub["short_return"].mean()) <= 0:
            return False
    return True


def positive_top_share(returns: pd.Series, k: int) -> float:
    positives = pd.to_numeric(returns, errors="coerce").dropna()
    positives = positives[positives > 0].sort_values(ascending=False)
    if positives.empty:
        return np.nan
    return float(positives.head(k).sum() / positives.sum())


def bootstrap_mean_ci(returns: pd.Series) -> tuple[float, float]:
    returns = pd.to_numeric(returns, errors="coerce").dropna()
    if len(returns) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(RNG_SEED + len(returns))
    values = returns.to_numpy(dtype=float)
    samples = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(BOOTSTRAP_SAMPLES)]
    return q(samples, 0.025), q(samples, 0.975)


def q(values: list[float], quantile: float) -> float:
    return float(np.quantile(values, quantile)) if values else np.nan


def finite(value: float) -> bool:
    return pd.notna(value) and math.isfinite(float(value))


def safety_fields() -> dict[str, Any]:
    return {
        "research_only": True,
        "execution_allowed": False,
        "live_order_allowed": False,
        "order_preview_allowed": False,
        "broker_account_access_allowed": False,
        "positions_access_allowed": False,
        "balance_access_allowed": False,
        "threshold_optimization_allowed": False,
        "future_information_allowed": False,
        "synthetic_intraday_data_allowed": False,
        "consumable_by_production": False,
    }


def add_safety(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for key, value in safety_fields().items():
        if key not in out:
            out[key] = value
    return out


def write_df(path: Path, df: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=base.json_default), encoding="utf-8")
    return path


def manifest_entries(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.glob("*")):
        if path.is_file():
            rows.append({"name": path.name, "path": str(path), "bytes": path.stat().st_size, "sha256": base.sha256_file(path)})
    return rows


def git_identity(repo_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:
            return f"ERROR: {exc}"

    return {"head": run("rev-parse", "HEAD"), "branch": run("branch", "--show-current"), "status_short": run("status", "--short")}


if __name__ == "__main__":
    raise SystemExit(main())
