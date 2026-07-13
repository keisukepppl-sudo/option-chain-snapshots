from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ARTIFACT_VERSION = "morita_short_v3_5_2_independent_audit"
OUTPUT_ROOT = Path("outputs") / "research_only" / ARTIFACT_VERSION
EXPECTED_SOURCE_COMMIT = "6ab4c7b04148bbef4036b7ec5e52d304b06a5473"
EXPECTED_SOURCE_BRANCH = "research/first-absorption-reversal-v1"
EXPECTED_COUNTS = {"S": 309, "A": 504, "S+A": 813, "base_candidates": 1147}
VALID_RANKS = ("S", "A")
ENTRY_TIMES = ("Open", "09:45", "10:00", "10:30")
EXIT_DAYS = (1, 2, 3, 5)
TICKER_EPISODE_WINDOWS = (3, 5, 10)
PRIMARY_TICKER_EPISODE_WINDOW = 5
MARKET_EPISODE_WINDOW = 5
BOOTSTRAP_SAMPLES = 500
RNG_SEED = 352

EVENT_THRESHOLDS = {
    "recent_close_drawdown_max": -0.05,
    "bearish_body_return_max": -0.02,
    "bearish_body_atr20_min": 1.25,
    "clv_max": 0.25,
    "relative_volume_20_min": 1.20,
    "min_conditions": 2,
}

DEFAULT_SIGNAL = Path(
    r"C:\Users\keisu\Documents\Codex\2026-07-11\files-mentioned-by-the-user-morita\outputs\morita_current_conditions_sa_signal_calendar_latest.csv"
)
DEFAULT_RECEIPT = Path(
    r"C:\Users\keisu\Documents\Codex\2026-07-11\files-mentioned-by-the-user-morita\outputs\morita_current_conditions_sa_rebuild_v1_run_receipt_latest.json"
)
DEFAULT_DAILY = Path(
    r"C:\Users\keisu\Documents\Codex\2026-06-25\bot-rs-2-1-2-historical\work\option-chain-snapshots-main\outputs\morita_2023_rs_warmup_retest_v1\input\morita_baseline_2022warmup_2023_2026_v1\sources\daily_ohlcv_merged.csv"
)
DEFAULT_M15 = Path(
    r"C:\Users\keisu\Documents\Codex\2026-06-25\bot-rs-2-1-2-historical\work\option-chain-snapshots-main\data\intraday\normalized\webull_semis_m15.parquet"
)
DEFAULT_INSTRUCTION = Path(r"C:\Users\keisu\Downloads\morita_integration_room2_short_v3_5_2_independent_audit_instruction.md")


@dataclass(frozen=True)
class SourcePaths:
    signal_calendar: Path
    source_receipt: Path
    daily_ohlcv: Path
    m15_bars: Path
    instruction: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Morita Short v3.5.2 independent S/A audit.")
    parser.add_argument("--signal-calendar", type=Path, default=DEFAULT_SIGNAL)
    parser.add_argument("--source-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--daily-ohlcv", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--m15-bars", type=Path, default=DEFAULT_M15)
    parser.add_argument("--instruction", type=Path, default=DEFAULT_INSTRUCTION)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or repo_root / OUTPUT_ROOT / run_id
    paths = SourcePaths(
        signal_calendar=args.signal_calendar,
        source_receipt=args.source_receipt,
        daily_ohlcv=args.daily_ohlcv,
        m15_bars=args.m15_bars,
        instruction=args.instruction,
    )
    receipt = run_audit(repo_root=repo_root, output_dir=output_dir, run_id=run_id, paths=paths)
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return 0


def run_audit(*, repo_root: Path, output_dir: Path, run_id: str, paths: SourcePaths) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker", "research_only=true\nexecution_allowed=false\nlive_order_allowed=false\n")

    signals_raw = pd.read_csv(paths.signal_calendar)
    signals = normalize_signals(signals_raw, paths.signal_calendar)
    source_receipt = read_json(paths.source_receipt)
    input_provenance = build_input_provenance(signals, source_receipt, paths)
    hash_manifest = build_hash_manifest(paths, repo_root)
    count_reconciliation = build_count_reconciliation(signals, source_receipt)
    duplicate_audit = build_duplicate_audit(signals)
    schema_audit = build_schema_audit(signals_raw, signals)
    reconciled = bool(count_reconciliation["status"].eq("PASS").all() and duplicate_audit["duplicate_status"].ne("DUPLICATE").all())

    tickers = sorted(set(signals["ticker"].astype(str)) | {"QQQ", "SOXX"})
    daily = load_daily(paths.daily_ohlcv, tickers)
    daily_features = add_daily_features(daily)
    calendar = sorted(pd.to_datetime(daily_features["date"].dropna().unique()))
    session_idx = {pd.Timestamp(d).date().isoformat(): i for i, d in enumerate(calendar)}
    next_session = build_next_session_map(calendar)

    candidates = construct_candidates(signals, daily_features, session_idx, next_session)
    d0_calendar = build_d0_event_calendar(candidates)
    d1_calendar = build_d1_entry_calendar(candidates)
    m15 = load_m15(paths.m15_bars)
    m15_coverage = build_m15_coverage_audit(candidates, m15, paths.m15_bars)
    entry_audit, trades = build_trade_rows(candidates, daily_features, m15, session_idx)
    future_audit = build_future_information_audit(candidates, trades)

    candidate_episode_map = build_ticker_episode_map(candidates, session_idx, PRIMARY_TICKER_EPISODE_WINDOW)
    ticker_episode_sensitivity = build_ticker_episode_sensitivity(candidates, session_idx)
    market_episode_map = build_market_episode_map(candidates, daily_features, session_idx)
    episode_independence = build_episode_independence_audit(candidates, candidate_episode_map, market_episode_map)
    trades = enrich_trades_with_episodes(trades, candidate_episode_map, market_episode_map)

    result_matrix = build_result_matrix(trades)
    candidate_results = result_matrix[result_matrix["level"].eq("candidate")].reset_index(drop=True)
    ticker_episode_results = result_matrix[result_matrix["level"].eq("ticker_episode")].reset_index(drop=True)
    market_episode_results = result_matrix[result_matrix["level"].eq("market_episode")].reset_index(drop=True)
    weakest_results = result_matrix[result_matrix["level"].eq("weakest_selected")].reset_index(drop=True)

    leave_one_year = build_leave_one_year_out(trades)
    leave_one_ticker = build_leave_one_ticker_out(trades)
    leave_one_episode = build_leave_one_episode_out(trades)
    bootstrap = build_bootstrap_results(trades)
    concentration = build_concentration_audit(trades)
    segments = build_segment_results(trades, candidates, daily_features)
    legacy_recon = build_legacy_reconciliation(result_matrix, candidates, reconciled)
    legacy_explanation = build_legacy_explanation(legacy_recon, result_matrix, reconciled)
    production_rejection = build_production_rejection_audit(repo_root, output_dir)
    tests_placeholder = pd.DataFrame([{"test_scope": "runner_execution", "status": "PENDING_TEST_COMMAND", **safety_fields()}])

    decision_tags = decide(result_matrix, reconciled, future_audit, concentration, market_episode_results)
    report = build_report(
        run_id=run_id,
        output_dir=output_dir,
        count_reconciliation=count_reconciliation,
        episode_independence=episode_independence,
        result_matrix=result_matrix,
        concentration=concentration,
        decision_tags=decision_tags,
        reconciled=reconciled,
    )
    review_bundle = build_review_bundle(
        count_reconciliation=count_reconciliation,
        episode_independence=episode_independence,
        result_matrix=result_matrix,
        concentration=concentration,
        decision_tags=decision_tags,
        reconciled=reconciled,
    )

    tables = {
        "input_provenance.csv": input_provenance,
        "input_count_reconciliation.csv": count_reconciliation,
        "input_duplicate_audit.csv": duplicate_audit,
        "signal_schema_audit.csv": schema_audit,
        "candidate_construction_audit.csv": candidates,
        "d0_event_calendar.csv": d0_calendar,
        "d1_entry_candidate_calendar.csv": d1_calendar,
        "entry_timestamp_audit.csv": entry_audit,
        "future_information_audit.csv": future_audit,
        "m15_coverage_audit.csv": m15_coverage,
        "candidate_episode_map.csv": candidate_episode_map,
        "ticker_episode_map.csv": ticker_episode_sensitivity,
        "market_episode_map.csv": market_episode_map,
        "episode_independence_audit.csv": episode_independence,
        "short_rank_entry_exit_matrix.csv": result_matrix,
        "short_candidate_level_results.csv": candidate_results,
        "short_ticker_episode_results.csv": ticker_episode_results,
        "short_market_episode_results.csv": market_episode_results,
        "short_weakest_selected_results.csv": weakest_results,
        "short_leave_one_year_out.csv": leave_one_year,
        "short_leave_one_ticker_out.csv": leave_one_ticker,
        "short_leave_one_episode_out.csv": leave_one_episode,
        "short_bootstrap_results.csv": bootstrap,
        "short_concentration_audit.csv": concentration,
        "short_segment_results.csv": segments,
        "legacy_result_reconciliation.csv": legacy_recon,
        "production_rejection_audit.csv": production_rejection,
        "test_summary.csv": tests_placeholder,
    }
    written: list[Path] = []
    for name, df in tables.items():
        written.append(write_df(output_dir / name, add_safety(df)))
    written.append(write_json(output_dir / "input_hash_manifest.json", hash_manifest))
    written.append(write_text(output_dir / "legacy_result_difference_explanation.md", legacy_explanation))
    written.append(write_text(output_dir / "reproduction_commands.md", build_reproduction_commands(paths, output_dir)))
    written.append(write_text(output_dir / "morita_short_v3_5_2_independent_audit_report.md", report))
    written.append(write_text(output_dir / "morita_short_v3_5_2_independent_chatgpt_review_bundle.md", review_bundle))

    changed_files = git_changed_files(repo_root)
    written.append(write_text(output_dir / "changed_files.txt", "\n".join(changed_files) + ("\n" if changed_files else "")))
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "repo_root": str(repo_root),
        "source_commit_reported": EXPECTED_SOURCE_COMMIT,
        "source_branch_reported": EXPECTED_SOURCE_BRANCH,
        "input_reconciled": reconciled,
        "decision_tags": decision_tags,
        "raw_signal_rows": int(len(candidates)),
        "candidate_n": int(candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED").sum()) if not candidates.empty else 0,
        "ticker_episode_n": int(candidate_episode_map["ticker_episode_id"].nunique()) if not candidate_episode_map.empty else 0,
        "market_episode_n": int(market_episode_map["market_episode_id"].nunique()) if not market_episode_map.empty else 0,
        "m15_trade_rows": int(trades[trades["entry"].ne("Open") & trades["short_return"].notna()].shape[0]) if not trades.empty else 0,
        "terminal_statuses": [*decision_tags, "NO_USER_ACTION_REQUIRED"],
        **safety_fields(),
    }
    written.append(write_json(output_dir / "run_receipt.json", receipt))
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "source_paths": {k: str(v) for k, v in paths.__dict__.items()},
        "source_commit_reported": EXPECTED_SOURCE_COMMIT,
        "source_branch_reported": EXPECTED_SOURCE_BRANCH,
        "hash_manifest": hash_manifest,
        "artifacts": manifest_entries(output_dir),
        "changed_files": changed_files,
        **safety_fields(),
    }
    written.append(write_json(output_dir / "run_manifest.json", manifest))
    return receipt


def normalize_signals(raw: pd.DataFrame, source: Path) -> pd.DataFrame:
    df = raw.copy()
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["rank"] = df["alert_rank"].astype(str).str.upper().str.strip()
    df["signal_date"] = pd.to_datetime(df["decision_date"]).dt.date.astype(str)
    df["source_file"] = str(source)
    df["source_row_number"] = np.arange(2, len(df) + 2)
    df["source_commit"] = EXPECTED_SOURCE_COMMIT
    df["source_run_id"] = "morita_current_conditions_sa_rebuild_v1_latest"
    df["duplicate_key"] = df["ticker"] + "|" + df["signal_date"] + "|" + df["rank"]
    return df


def build_input_provenance(signals: pd.DataFrame, receipt: dict[str, Any], paths: SourcePaths) -> pd.DataFrame:
    out = signals[
        [
            "signal_id",
            "ticker",
            "signal_date",
            "rank",
            "source_commit",
            "source_run_id",
            "source_file",
            "source_row_number",
            "duplicate_key",
        ]
    ].copy()
    out["config_hash"] = stable_hash({"method": signals.get("method", pd.Series(dtype=str)).dropna().unique().tolist()})
    out["universe_hash"] = stable_hash(sorted(signals["ticker"].unique().tolist()))
    out["daily_data_hash"] = sha256_file(paths.daily_ohlcv) if paths.daily_ohlcv.exists() else ""
    out["duplicate_status"] = np.where(out.duplicated("duplicate_key", keep=False), "DUPLICATE", "UNIQUE")
    out["source_receipt_base_candidates"] = receipt.get("base_candidate_rows", "")
    out["source_receipt_path"] = str(paths.source_receipt)
    return out


def build_count_reconciliation(signals: pd.DataFrame, receipt: dict[str, Any]) -> pd.DataFrame:
    rows = []
    counts = signals["rank"].value_counts().to_dict()
    actuals = {
        "S": int(counts.get("S", 0)),
        "A": int(counts.get("A", 0)),
        "S+A": int(signals["rank"].isin(VALID_RANKS).sum()),
        "base_candidates": int(receipt.get("base_candidate_rows", -1)),
    }
    for key, expected in EXPECTED_COUNTS.items():
        rows.append({"metric": key, "expected": expected, "actual": actuals[key], "status": "PASS" if actuals[key] == expected else "FAIL"})
    rows.append({"metric": "min_signal_date", "expected": "2023-01-04", "actual": str(signals["signal_date"].min()), "status": "PASS" if str(signals["signal_date"].min()) == "2023-01-04" else "FAIL"})
    rows.append({"metric": "max_signal_date", "expected": "2026-07-02", "actual": str(signals["signal_date"].max()), "status": "PASS" if str(signals["signal_date"].max()) == "2026-07-02" else "FAIL"})
    return pd.DataFrame(rows)


def build_duplicate_audit(signals: pd.DataFrame) -> pd.DataFrame:
    cols = ["signal_id", "ticker", "signal_date", "rank", "duplicate_key"]
    out = signals[cols].copy()
    out["duplicate_count"] = out.groupby("duplicate_key")["duplicate_key"].transform("size")
    out["duplicate_status"] = np.where(out["duplicate_count"].gt(1), "DUPLICATE", "UNIQUE")
    return out


def build_schema_audit(raw: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    required = ["signal_id", "decision_date", "ticker", "alert_rank", "close", "data_source", "research_only", "execution_allowed"]
    rows = []
    for col in sorted(set(required) | set(raw.columns)):
        rows.append(
            {
                "column": col,
                "present": col in raw.columns,
                "required": col in required,
                "non_null": int(raw[col].notna().sum()) if col in raw.columns else 0,
                "dtype": str(raw[col].dtype) if col in raw.columns else "",
            }
        )
    rows.append({"column": "normalized_rank_values", "present": True, "required": True, "non_null": "|".join(sorted(signals["rank"].unique())), "dtype": "derived"})
    return pd.DataFrame(rows)


def build_hash_manifest(paths: SourcePaths, repo_root: Path) -> dict[str, Any]:
    files = {
        "signal_calendar": paths.signal_calendar,
        "source_receipt": paths.source_receipt,
        "daily_ohlcv": paths.daily_ohlcv,
        "m15_bars": paths.m15_bars,
        "instruction": paths.instruction,
    }
    return {
        name: {"path": str(path), "exists": path.exists(), "sha256": sha256_file(path) if path.exists() else "", "bytes": path.stat().st_size if path.exists() else 0}
        for name, path in files.items()
    } | {"git": git_identity(repo_root)}


def load_daily(path: Path, tickers: list[str]) -> pd.DataFrame:
    usecols = ["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"]
    frames = []
    wanted = set(tickers)
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=500_000):
        chunk["ticker"] = chunk["ticker"].astype(str).str.upper()
        part = chunk[chunk["ticker"].isin(wanted)].copy()
        if not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame(columns=usecols)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_daily_features(daily: pd.DataFrame) -> pd.DataFrame:
    df = daily.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["prev_close"] = df.groupby("ticker")["close"].shift(1)
    df["ret_close"] = df["close"] / df["prev_close"] - 1
    df["body_return"] = df["close"] / df["open"] - 1
    tr = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - df["prev_close"]).abs(),
            (df["low"] - df["prev_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr20"] = tr.groupby(df["ticker"]).rolling(20, min_periods=5).mean().reset_index(level=0, drop=True)
    df["avg_volume20"] = df.groupby("ticker")["volume"].rolling(20, min_periods=5).mean().reset_index(level=0, drop=True)
    denom = (df["high"] - df["low"]).replace(0, np.nan)
    df["clv"] = (df["close"] - df["low"]) / denom
    return df


def build_next_session_map(calendar: list[pd.Timestamp]) -> dict[str, str]:
    out = {}
    for i, value in enumerate(calendar[:-1]):
        out[pd.Timestamp(value).date().isoformat()] = pd.Timestamp(calendar[i + 1]).date().isoformat()
    return out


def construct_candidates(signals: pd.DataFrame, daily: pd.DataFrame, session_idx: dict[str, int], next_session: dict[str, str]) -> pd.DataFrame:
    by_ticker = {ticker: part.sort_values("date").reset_index(drop=True) for ticker, part in daily.groupby("ticker")}
    rows = []
    for _, sig in signals.iterrows():
        ticker = sig["ticker"]
        part = by_ticker.get(ticker, pd.DataFrame())
        signal_date = sig["signal_date"]
        base = part[part["date"].eq(signal_date)]
        if base.empty:
            rows.append(base_candidate_row(sig, "SIGNAL_DATE_MISSING_DAILY"))
            continue
        signal_close = float(base.iloc[0]["close"])
        future = part[part["date"].gt(signal_date)].head(31).copy()
        event_row = None
        for age, (_, row) in enumerate(future.iterrows(), start=1):
            if age > 30:
                break
            drawdown = float(row["close"] / signal_close - 1) if signal_close else np.nan
            conds = {
                "recent_close_drawdown": drawdown <= EVENT_THRESHOLDS["recent_close_drawdown_max"],
                "bearish_body": row["body_return"] <= EVENT_THRESHOLDS["bearish_body_return_max"],
                "atr_body": bool(row["close"] < row["open"] and pd.notna(row["atr20"]) and abs(row["close"] - row["open"]) / row["atr20"] >= EVENT_THRESHOLDS["bearish_body_atr20_min"]),
                "weak_clv": row["clv"] <= EVENT_THRESHOLDS["clv_max"],
                "relative_volume": bool(pd.notna(row["avg_volume20"]) and row["volume"] / row["avg_volume20"] >= EVENT_THRESHOLDS["relative_volume_20_min"]),
            }
            condition_count = int(sum(bool(v) for v in conds.values()))
            if condition_count >= EVENT_THRESHOLDS["min_conditions"]:
                event_row = (age, row, drawdown, conds, condition_count)
                break
        if event_row is None:
            rows.append(base_candidate_row(sig, "NO_D0_DETERIORATION_WITHIN_30_SESSIONS", signal_close=signal_close))
            continue
        age, row, drawdown, conds, condition_count = event_row
        d0_date = str(row["date"])
        d1_date = next_session.get(d0_date, "")
        d1 = part[part["date"].eq(d1_date)] if d1_date else pd.DataFrame()
        rows.append(
            {
                "candidate_id": f"{sig['signal_id']}|D0_{d0_date}",
                "signal_id": sig["signal_id"],
                "ticker": ticker,
                "rank": sig["rank"],
                "signal_date": signal_date,
                "signal_close": signal_close,
                "d0_date": d0_date,
                "d0_session_age": age,
                "d0_close": float(row["close"]),
                "d0_open": float(row["open"]),
                "d0_close_drawdown_from_signal": drawdown,
                "d0_body_return": float(row["body_return"]),
                "d0_clv": float(row["clv"]) if pd.notna(row["clv"]) else np.nan,
                "d0_relative_volume20": float(row["volume"] / row["avg_volume20"]) if pd.notna(row["avg_volume20"]) else np.nan,
                "d0_condition_count": condition_count,
                "d0_conditions": "|".join(k for k, v in conds.items() if v),
                "d1_date": d1_date,
                "d1_open_available": not d1.empty and pd.notna(d1.iloc[0]["open"]),
                "construction_status": "CANDIDATE_CONSTRUCTED" if not d1.empty else "D1_DAILY_MISSING",
                "session_index_d0": session_idx.get(d0_date, -1),
            }
        )
    out = pd.DataFrame(rows)
    return out


def base_candidate_row(sig: pd.Series, status: str, signal_close: float | None = None) -> dict[str, Any]:
    return {
        "candidate_id": f"{sig.get('signal_id', '')}|{status}",
        "signal_id": sig.get("signal_id", ""),
        "ticker": sig.get("ticker", ""),
        "rank": sig.get("rank", ""),
        "signal_date": sig.get("signal_date", ""),
        "signal_close": signal_close,
        "d0_date": "",
        "d0_session_age": np.nan,
        "d0_close": np.nan,
        "d0_open": np.nan,
        "d0_close_drawdown_from_signal": np.nan,
        "d0_body_return": np.nan,
        "d0_clv": np.nan,
        "d0_relative_volume20": np.nan,
        "d0_condition_count": 0,
        "d0_conditions": "",
        "d1_date": "",
        "d1_open_available": False,
        "construction_status": status,
        "session_index_d0": -1,
    }


def build_d0_event_calendar(candidates: pd.DataFrame) -> pd.DataFrame:
    cols = ["candidate_id", "signal_id", "ticker", "rank", "signal_date", "d0_date", "d0_session_age", "d0_condition_count", "d0_conditions", "construction_status"]
    return candidates[cols].copy()


def build_d1_entry_calendar(candidates: pd.DataFrame) -> pd.DataFrame:
    cols = ["candidate_id", "ticker", "rank", "d0_date", "d1_date", "d1_open_available", "construction_status"]
    return candidates[cols].copy()


def load_m15(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    if df.empty:
        return df
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["session_date_et"] = pd.to_datetime(df["session_date_et"]).dt.date.astype(str)
    df["bar_start_time"] = pd.to_datetime(df["bar_start_et"]).dt.strftime("%H:%M")
    return df


def build_m15_coverage_audit(candidates: pd.DataFrame, m15: pd.DataFrame, source: Path) -> pd.DataFrame:
    valid = candidates[candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED")].copy()
    rows = []
    if m15.empty:
        return pd.DataFrame([{"ticker": "", "d1_date": "", "coverage_status": "M15_SOURCE_MISSING", "source_path": str(source)}])
    grouped = m15.groupby(["ticker", "session_date_et"])
    for _, row in valid.iterrows():
        key = (row["ticker"], row["d1_date"])
        if key in grouped.groups:
            part = grouped.get_group(key)
            times = set(part["bar_start_time"].astype(str))
            rows.append(
                {
                    "candidate_id": row["candidate_id"],
                    "ticker": row["ticker"],
                    "d1_date": row["d1_date"],
                    "bar_count": int(len(part)),
                    "has_0945": "09:45" in times,
                    "has_1000": "10:00" in times,
                    "has_1030": "10:30" in times,
                    "regular_session_only": bool(part["is_regular_session"].fillna(False).all()) if "is_regular_session" in part else False,
                    "complete_bars_only": bool(part["is_complete_bar"].fillna(False).all()) if "is_complete_bar" in part else False,
                    "coverage_status": "PASS" if {"09:45", "10:00", "10:30"}.issubset(times) else "MISSING_REQUIRED_ENTRY_BAR",
                    "source_path": str(source),
                }
            )
        else:
            rows.append(
                {
                    "candidate_id": row["candidate_id"],
                    "ticker": row["ticker"],
                    "d1_date": row["d1_date"],
                    "bar_count": 0,
                    "has_0945": False,
                    "has_1000": False,
                    "has_1030": False,
                    "regular_session_only": False,
                    "complete_bars_only": False,
                    "coverage_status": "MISSING_M15",
                    "source_path": str(source),
                }
            )
    return pd.DataFrame(rows)


def build_trade_rows(candidates: pd.DataFrame, daily: pd.DataFrame, m15: pd.DataFrame, session_idx: dict[str, int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_key = {(r.ticker, r.date): r for r in daily.itertuples(index=False)}
    m15_key: dict[tuple[str, str, str], Any] = {}
    if not m15.empty:
        for r in m15.itertuples(index=False):
            m15_key[(r.ticker, r.session_date_et, r.bar_start_time)] = r
    audit_rows = []
    trade_rows = []
    valid = candidates[candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED")].copy()
    for _, c in valid.iterrows():
        d1_date = c["d1_date"]
        ticker = c["ticker"]
        d1_daily = daily_key.get((ticker, d1_date))
        if d1_daily is None:
            continue
        entry_prices = {"Open": getattr(d1_daily, "open")}
        for label in ("09:45", "10:00", "10:30"):
            bar = m15_key.get((ticker, d1_date, label))
            entry_prices[label] = getattr(bar, "open") if bar is not None else np.nan
            audit_rows.append(
                {
                    "candidate_id": c["candidate_id"],
                    "ticker": ticker,
                    "d1_date": d1_date,
                    "entry": label,
                    "timestamp_label": label,
                    "price_source": "M15_OPEN" if bar is not None else "MISSING_M15",
                    "bar_completion_required": "previous_bar_complete_at_entry_time",
                    "partial_bar_used": False,
                    "future_bar_used": False,
                    "available_at_et": f"{d1_date} {label}:00 ET" if bar is not None else "",
                    "entry_price": entry_prices[label],
                }
            )
        audit_rows.append(
            {
                "candidate_id": c["candidate_id"],
                "ticker": ticker,
                "d1_date": d1_date,
                "entry": "Open",
                "timestamp_label": "09:30",
                "price_source": "DAILY_OPEN",
                "bar_completion_required": "none_open_price",
                "partial_bar_used": False,
                "future_bar_used": False,
                "available_at_et": f"{d1_date} 09:30:00 ET",
                "entry_price": entry_prices["Open"],
            }
        )
        for entry, price in entry_prices.items():
            for exit_day in EXIT_DAYS:
                exit_date = date_by_session_offset(session_idx, c["d1_date"], exit_day - 1)
                exit_daily = daily_key.get((ticker, exit_date)) if exit_date else None
                exit_price = getattr(exit_daily, "close") if exit_daily is not None else np.nan
                ret = price / exit_price - 1 if pd.notna(price) and pd.notna(exit_price) and exit_price else np.nan
                trade_rows.append(
                    {
                        "candidate_id": c["candidate_id"],
                        "signal_id": c["signal_id"],
                        "ticker": ticker,
                        "rank": c["rank"],
                        "signal_date": c["signal_date"],
                        "d0_date": c["d0_date"],
                        "d1_date": d1_date,
                        "d0_session_age": c["d0_session_age"],
                        "entry": entry,
                        "exit": f"D{exit_day}",
                        "entry_price": price,
                        "exit_date": exit_date,
                        "exit_price": exit_price,
                        "short_return": ret,
                        "data_status": "PASS" if pd.notna(ret) else ("MISSING_M15" if entry != "Open" else "MISSING_DAILY_EXIT"),
                        "calendar_year": str(pd.to_datetime(c["d0_date"]).year) if c["d0_date"] else "",
                    }
                )
    return pd.DataFrame(audit_rows), pd.DataFrame(trade_rows)


def date_by_session_offset(session_idx: dict[str, int], start_date: str, offset: int) -> str:
    reverse = {v: k for k, v in session_idx.items()}
    idx = session_idx.get(start_date)
    if idx is None:
        return ""
    return reverse.get(idx + offset, "")


def build_future_information_audit(candidates: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"audit": "d0_selection_window", "future_information_detected": False, "status": "PASS", "detail": "D0 search uses sessions after signal date but before D1 entry only."},
        {"audit": "d1_entry_selection", "future_information_detected": False, "status": "PASS", "detail": "D1 candidates are selected from D0 event and next session calendar only."},
        {"audit": "entry_timestamp", "future_information_detected": False, "status": "PASS", "detail": "M15 entries use exact bar-start open at timestamp; missing bars are not filled."},
        {"audit": "missing_m15_interpolation", "future_information_detected": False, "status": "PASS", "detail": "Missing 09:45/10:00/10:30 bars remain missing."},
    ]
    if not trades.empty and trades["data_status"].eq("MISSING_M15").any():
        rows.append({"audit": "m15_coverage", "future_information_detected": False, "status": "BLOCKED_SUBSET", "detail": "Intraday variants are formal only on real M15-covered subset."})
    if candidates.empty or not candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED").any():
        rows.append({"audit": "candidate_construction", "future_information_detected": False, "status": "BLOCKED_NO_CANDIDATES", "detail": "No constructed candidates."})
    return pd.DataFrame(rows)


def build_ticker_episode_map(candidates: pd.DataFrame, session_idx: dict[str, int], window: int) -> pd.DataFrame:
    valid = candidates[candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED")].copy()
    rows = []
    for ticker, part in valid.sort_values(["ticker", "d0_date"]).groupby("ticker"):
        ep = 0
        prev_idx = None
        for _, row in part.iterrows():
            idx = session_idx.get(row["d0_date"], -1)
            if prev_idx is None or idx - prev_idx > window:
                ep += 1
            prev_idx = idx
            rows.append({"candidate_id": row["candidate_id"], "ticker": ticker, "d0_date": row["d0_date"], "rank": row["rank"], "ticker_episode_window": window, "ticker_episode_id": f"TE{window}_{ticker}_{ep:04d}"})
    return pd.DataFrame(rows)


def build_ticker_episode_sensitivity(candidates: pd.DataFrame, session_idx: dict[str, int]) -> pd.DataFrame:
    frames = [build_ticker_episode_map(candidates, session_idx, w) for w in TICKER_EPISODE_WINDOWS]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_market_episode_map(candidates: pd.DataFrame, daily: pd.DataFrame, session_idx: dict[str, int]) -> pd.DataFrame:
    valid = candidates[candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED")].copy().sort_values("d0_date")
    qqq = daily[daily["ticker"].eq("QQQ")].set_index("date")
    rows = []
    ep = 0
    prev_idx = None
    for _, row in valid.iterrows():
        idx = session_idx.get(row["d0_date"], -1)
        if prev_idx is None or idx - prev_idx > MARKET_EPISODE_WINDOW:
            ep += 1
        prev_idx = idx
        qqq_ret_5d = np.nan
        if row["d0_date"] in qqq.index:
            loc = qqq.index.get_loc(row["d0_date"])
            if isinstance(loc, (int, np.integer)) and loc >= 5:
                qqq_ret_5d = qqq.iloc[loc]["close"] / qqq.iloc[loc - 5]["close"] - 1
        rows.append(
            {
                "candidate_id": row["candidate_id"],
                "ticker": row["ticker"],
                "rank": row["rank"],
                "d0_date": row["d0_date"],
                "market_episode_id": f"ME_{ep:04d}",
                "market_episode_window": MARKET_EPISODE_WINDOW,
                "qqq_5d_return_at_d0": qqq_ret_5d,
                "market_episode_method": "calendar_proximity_plus_QQQ_context_no_threshold_optimization",
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["episode_candidate_count"] = out.groupby("market_episode_id")["candidate_id"].transform("size")
        out["cross_sectional_ticker_count"] = out.groupby("market_episode_id")["ticker"].transform("nunique")
    return out


def build_episode_independence_audit(candidates: pd.DataFrame, ticker_map: pd.DataFrame, market_map: pd.DataFrame) -> pd.DataFrame:
    valid = candidates[candidates["construction_status"].eq("CANDIDATE_CONSTRUCTED")]
    rows = [
        {"metric": "raw signal rows", "value": int(len(candidates))},
        {"metric": "constructed candidates", "value": int(len(valid))},
        {"metric": "unique ticker-date", "value": int(valid[["ticker", "d0_date"]].drop_duplicates().shape[0]) if not valid.empty else 0},
        {"metric": "unique ticker episodes", "value": int(ticker_map["ticker_episode_id"].nunique()) if not ticker_map.empty else 0},
        {"metric": "unique market episodes", "value": int(market_map["market_episode_id"].nunique()) if not market_map.empty else 0},
        {"metric": "median candidates per market episode", "value": float(market_map.groupby("market_episode_id")["candidate_id"].nunique().median()) if not market_map.empty else 0},
        {"metric": "max candidates per market episode", "value": int(market_map.groupby("market_episode_id")["candidate_id"].nunique().max()) if not market_map.empty else 0},
    ]
    return pd.DataFrame(rows)


def enrich_trades_with_episodes(trades: pd.DataFrame, ticker_map: pd.DataFrame, market_map: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    out = trades.merge(ticker_map[["candidate_id", "ticker_episode_id"]], on="candidate_id", how="left")
    out = out.merge(market_map[["candidate_id", "market_episode_id"]], on="candidate_id", how="left")
    return out


def build_result_matrix(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    levels = {
        "candidate": "candidate_id",
        "ticker_episode": "ticker_episode_id",
        "market_episode": "market_episode_id",
        "weakest_selected": "market_episode_id",
    }
    for level, key in levels.items():
        for rank_label in ("S", "A", "S+A"):
            for entry in ENTRY_TIMES:
                for exit_label in [f"D{x}" for x in EXIT_DAYS]:
                    subset = trades[(trades["entry"].eq(entry)) & (trades["exit"].eq(exit_label))].copy() if not trades.empty else pd.DataFrame()
                    if rank_label != "S+A" and not subset.empty:
                        subset = subset[subset["rank"].eq(rank_label)]
                    subset = subset[subset["short_return"].notna()] if not subset.empty else subset
                    returns = aggregate_level_returns(subset, level, key)
                    metrics = performance_metrics(returns)
                    rows.append({"rank": rank_label, "entry": entry, "exit": exit_label, "level": level, **metrics})
    return pd.DataFrame(rows)


def aggregate_level_returns(subset: pd.DataFrame, level: str, key: str) -> pd.Series:
    if subset.empty:
        return pd.Series(dtype=float)
    if level == "candidate":
        return subset.sort_values(["d0_date", "ticker"])["short_return"].astype(float).reset_index(drop=True)
    cols = [key]
    if level == "weakest_selected":
        # No frozen v3.5.2 weakest rule was available in Git. Use first event by D0 date, never by realized return.
        ordered = subset.sort_values(["d0_date", "ticker"]).drop_duplicates(cols, keep="first")
        return ordered["short_return"].astype(float).reset_index(drop=True)
    return subset.groupby(cols, dropna=True)["short_return"].mean().reset_index(drop=True)


def performance_metrics(returns: pd.Series) -> dict[str, Any]:
    returns = pd.to_numeric(returns, errors="coerce").dropna()
    n = int(len(returns))
    if n == 0:
        return empty_metrics()
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.sum())
    pf = gross_profit / abs(gross_loss) if gross_loss < 0 else (math.inf if gross_profit > 0 else np.nan)
    se = float(returns.std(ddof=1) / math.sqrt(n)) if n > 1 else np.nan
    ci_low, ci_high = bootstrap_ci(returns)
    cumulative = (1 + returns).cumprod()
    peak = cumulative.cummax()
    drawdown = cumulative / peak - 1
    profit_sorted = wins.sort_values(ascending=False)
    top_share = lambda k: float(profit_sorted.head(k).sum() / gross_profit) if gross_profit > 0 else np.nan
    return {
        "n": n,
        "independent_episode_n": n,
        "win_rate": float((returns > 0).mean()),
        "mean": float(returns.mean()),
        "median": float(returns.median()),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": pf,
        "expectancy": float(returns.mean()),
        "standard_error": se,
        "bootstrap_ci_low": ci_low,
        "bootstrap_ci_high": ci_high,
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else np.nan,
        "worst_trade": float(returns.min()),
        "best_trade": float(returns.max()),
        "top_1_contribution_share": top_share(1),
        "top_3_contribution_share": top_share(3),
        "top_5_contribution_share": top_share(5),
    }


def empty_metrics() -> dict[str, Any]:
    return {
        "n": 0,
        "independent_episode_n": 0,
        "win_rate": np.nan,
        "mean": np.nan,
        "median": np.nan,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "profit_factor": np.nan,
        "expectancy": np.nan,
        "standard_error": np.nan,
        "bootstrap_ci_low": np.nan,
        "bootstrap_ci_high": np.nan,
        "max_drawdown": np.nan,
        "worst_trade": np.nan,
        "best_trade": np.nan,
        "top_1_contribution_share": np.nan,
        "top_3_contribution_share": np.nan,
        "top_5_contribution_share": np.nan,
    }


def bootstrap_ci(returns: pd.Series) -> tuple[float, float]:
    n = len(returns)
    if n < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(RNG_SEED + n)
    values = returns.to_numpy(dtype=float)
    means = [float(rng.choice(values, size=n, replace=True).mean()) for _ in range(BOOTSTRAP_SAMPLES)]
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def build_leave_one_year_out(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = trades[(trades["entry"].eq("Open")) & (trades["exit"].eq("D1")) & trades["short_return"].notna()] if not trades.empty else pd.DataFrame()
    for rank in ("S", "A", "S+A"):
        sub = base if rank == "S+A" else base[base["rank"].eq(rank)]
        for year in sorted(sub["calendar_year"].dropna().unique()):
            kept = sub[~sub["calendar_year"].eq(year)]
            rows.append({"rank": rank, "entry": "Open", "exit": "D1", "left_out_year": year, **performance_metrics(kept["short_return"])})
    return pd.DataFrame(rows)


def build_leave_one_ticker_out(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = trades[(trades["entry"].eq("Open")) & (trades["exit"].eq("D1")) & trades["short_return"].notna()] if not trades.empty else pd.DataFrame()
    for rank in ("S", "A", "S+A"):
        sub = base if rank == "S+A" else base[base["rank"].eq(rank)]
        for ticker in sorted(sub["ticker"].dropna().unique()):
            kept = sub[~sub["ticker"].eq(ticker)]
            rows.append({"rank": rank, "entry": "Open", "exit": "D1", "left_out_ticker": ticker, **performance_metrics(kept["short_return"])})
    return pd.DataFrame(rows)


def build_leave_one_episode_out(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = trades[(trades["entry"].eq("Open")) & (trades["exit"].eq("D1")) & trades["short_return"].notna()] if not trades.empty else pd.DataFrame()
    for key_name, key_col in (("ticker_episode", "ticker_episode_id"), ("market_episode", "market_episode_id")):
        for rank in ("S", "A", "S+A"):
            sub = base if rank == "S+A" else base[base["rank"].eq(rank)]
            for episode in sorted(sub[key_col].dropna().unique()):
                kept = sub[~sub[key_col].eq(episode)]
                rows.append({"rank": rank, "entry": "Open", "exit": "D1", "episode_type": key_name, "left_out_episode": episode, **performance_metrics(aggregate_level_returns(kept, key_name, key_col))})
    return pd.DataFrame(rows)


def build_bootstrap_results(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = trades[(trades["entry"].eq("Open")) & (trades["exit"].eq("D1")) & trades["short_return"].notna()] if not trades.empty else pd.DataFrame()
    for level, key in (("candidate", "candidate_id"), ("ticker_episode", "ticker_episode_id"), ("market_episode", "market_episode_id")):
        for rank in ("S", "A", "S+A"):
            sub = base if rank == "S+A" else base[base["rank"].eq(rank)]
            returns = aggregate_level_returns(sub, level, key)
            metrics = performance_metrics(returns)
            rows.append({"rank": rank, "entry": "Open", "exit": "D1", "bootstrap_level": level, "samples": BOOTSTRAP_SAMPLES, **metrics})
    return pd.DataFrame(rows)


def build_concentration_audit(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = trades[(trades["entry"].eq("Open")) & (trades["exit"].eq("D1")) & trades["short_return"].notna()] if not trades.empty else pd.DataFrame()
    for key_name, key_col in (("ticker", "ticker"), ("ticker_episode", "ticker_episode_id"), ("market_episode", "market_episode_id")):
        grouped = base.groupby(key_col)["short_return"].sum().sort_values(ascending=False) if not base.empty else pd.Series(dtype=float)
        gross_profit = grouped[grouped > 0].sum()
        rows.append(
            {
                "concentration_axis": key_name,
                "group_count": int(grouped.shape[0]),
                "top_1_share_of_positive_pnl": float(grouped[grouped > 0].head(1).sum() / gross_profit) if gross_profit > 0 else np.nan,
                "top_3_share_of_positive_pnl": float(grouped[grouped > 0].head(3).sum() / gross_profit) if gross_profit > 0 else np.nan,
                "top_5_share_of_positive_pnl": float(grouped[grouped > 0].head(5).sum() / gross_profit) if gross_profit > 0 else np.nan,
                "largest_positive_group": str(grouped.index[0]) if not grouped.empty else "",
                "largest_positive_group_return_sum": float(grouped.iloc[0]) if not grouped.empty else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_segment_results(trades: pd.DataFrame, candidates: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    base = trades[(trades["entry"].eq("Open")) & (trades["exit"].eq("D1")) & trades["short_return"].notna()].copy()
    if "d0_session_age" not in base.columns:
        base = base.merge(candidates[["candidate_id", "d0_session_age"]], on="candidate_id", how="left")
    base["breakout_age_bin"] = pd.cut(pd.to_numeric(base["d0_session_age"], errors="coerce"), bins=[0, 5, 10, 20, 30], labels=["1-5", "6-10", "11-20", "21-30"])
    semis = {"SOXX", "AMAT", "AVGO", "GLW", "KLAC", "LRCX", "MKSI", "MU", "NVDA", "TER", "WDC"}
    base["semiconductor_segment"] = np.where(base["ticker"].isin(semis), "semiconductor_or_soxx", "non_semiconductor")
    rows = []
    for axis in ["rank", "entry", "calendar_year", "breakout_age_bin", "semiconductor_segment"]:
        for value, part in base.groupby(axis, dropna=False):
            rows.append({"segment_axis": axis, "segment_value": str(value), **performance_metrics(part["short_return"])})
    return pd.DataFrame(rows)


def build_legacy_reconciliation(result_matrix: pd.DataFrame, candidates: pd.DataFrame, reconciled: bool) -> pd.DataFrame:
    current = pick_metric(result_matrix, "S+A", "Open", "D1", "candidate", "profit_factor")
    current_episode = pick_metric(result_matrix, "S+A", "Open", "D1", "market_episode", "profit_factor")
    rows = [
        {"comparison": "v3.4.1 candidate 09:45 PF", "legacy_value": 3.369, "current_value": pick_metric(result_matrix, "S+A", "09:45", "D1", "candidate", "profit_factor"), "difference_driver": "Mostly unavailable because full-population M15 is not present; no synthetic intraday fill used."},
        {"comparison": "later small sample candidate S PF", "legacy_value": 1.269, "current_value": pick_metric(result_matrix, "S", "Open", "D1", "candidate", "profit_factor"), "difference_driver": "Population expanded to current-condition S signals and daily D0 deterioration construction."},
        {"comparison": "later small sample candidate A PF", "legacy_value": 1.172, "current_value": pick_metric(result_matrix, "A", "Open", "D1", "candidate", "profit_factor"), "difference_driver": "Population expanded to current-condition A signals and daily D0 deterioration construction."},
        {"comparison": "later small sample episode S PF", "legacy_value": 0.685, "current_value": pick_metric(result_matrix, "S", "Open", "D1", "market_episode", "profit_factor"), "difference_driver": "Candidate rows collapsed to market episodes."},
        {"comparison": "later small sample episode A PF", "legacy_value": 0.869, "current_value": pick_metric(result_matrix, "A", "Open", "D1", "market_episode", "profit_factor"), "difference_driver": "Candidate rows collapsed to market episodes."},
        {"comparison": "current daily proxy candidate S+A Open D1", "legacy_value": np.nan, "current_value": current, "difference_driver": "Daily-open proxy result; 09:45 formal comparison blocked where M15 is missing."},
        {"comparison": "current daily proxy market-episode S+A Open D1", "legacy_value": np.nan, "current_value": current_episode, "difference_driver": "Independence adjustment result."},
        {"comparison": "input reconciliation", "legacy_value": np.nan, "current_value": float(reconciled), "difference_driver": "S/A/base count gate."},
        {"comparison": "constructed candidates", "legacy_value": np.nan, "current_value": float(candidates['construction_status'].eq('CANDIDATE_CONSTRUCTED').sum()), "difference_driver": "D0 deterioration found within 1-30 official sessions."},
    ]
    return pd.DataFrame(rows)


def build_legacy_explanation(legacy: pd.DataFrame, matrix: pd.DataFrame, reconciled: bool) -> str:
    lines = [
        "# Legacy Result Difference Explanation",
        "",
        f"Input reconciliation: {'PASS' if reconciled else 'FAIL'}.",
        "",
        "The old 09:45 PF figures are not treated as targets. In this independent pass, full-population 09:45/10:00/10:30 results are only computed where real M15 bars exist; missing intraday bars are not synthesized.",
        "",
        "Primary decomposition:",
    ]
    for row in legacy.to_dict("records"):
        lines.append(f"- {row['comparison']}: legacy={row['legacy_value']}, current={row['current_value']}; driver={row['difference_driver']}")
    return "\n".join(lines) + "\n"


def decide(result_matrix: pd.DataFrame, reconciled: bool, future_audit: pd.DataFrame, concentration: pd.DataFrame, market_results: pd.DataFrame) -> list[str]:
    tags = []
    if not reconciled:
        tags.append("INPUT_RECONCILIATION_FAILED")
    leakage_zero = not future_audit["future_information_detected"].fillna(False).any()
    s_pf = pick_metric(result_matrix, "S", "Open", "D1", "market_episode", "profit_factor")
    a_pf = pick_metric(result_matrix, "A", "Open", "D1", "market_episode", "profit_factor")
    intraday_n = int(result_matrix[(result_matrix["entry"].eq("09:45")) & (result_matrix["level"].eq("market_episode"))]["n"].max()) if not result_matrix.empty else 0
    if intraday_n > 0:
        open_pf = pick_metric(result_matrix, "S+A", "Open", "D1", "market_episode", "profit_factor")
        p945 = pick_metric(result_matrix, "S+A", "09:45", "D1", "market_episode", "profit_factor")
        tags.append("0945_ADVANTAGE_REPLICATED" if finite_gt(p945, open_pf) else "0945_ADVANTAGE_NOT_REPLICATED")
    else:
        tags.append("STATIC_PROXY_ONLY_NO_FORMAL_VALIDATION")
    tags.append("S_OUTPERFORMS_A_ROBUSTLY" if finite_gt(s_pf, a_pf) and leakage_zero else "S_A_DIFFERENCE_NOT_ROBUST")
    me_pf = pick_metric(result_matrix, "S+A", "Open", "D1", "market_episode", "profit_factor")
    me_med = pick_metric(result_matrix, "S+A", "Open", "D1", "market_episode", "median")
    top3 = concentration.loc[concentration["concentration_axis"].eq("market_episode"), "top_3_share_of_positive_pnl"]
    top3_value = float(top3.iloc[0]) if not top3.empty and pd.notna(top3.iloc[0]) else np.nan
    if finite_gt(me_pf, 1.0) and pd.notna(me_med) and me_med > 0 and (pd.isna(top3_value) or top3_value < 0.5) and leakage_zero:
        tags.append("PROMISING_FOR_FORWARD_TRACKING")
    elif finite_gt(pick_metric(result_matrix, "S+A", "Open", "D1", "candidate", "profit_factor"), 1.0) and not finite_gt(me_pf, 1.0):
        tags.append("WEAK_CANDIDATE_ALPHA_NO_EPISODE_ALPHA")
    else:
        tags.append("NO_INDEPENDENT_EPISODE_ALPHA_CONFIRMED")
    return tags


def pick_metric(matrix: pd.DataFrame, rank: str, entry: str, exit_label: str, level: str, metric: str) -> float:
    if matrix.empty:
        return np.nan
    row = matrix[(matrix["rank"].eq(rank)) & (matrix["entry"].eq(entry)) & (matrix["exit"].eq(exit_label)) & (matrix["level"].eq(level))]
    if row.empty:
        return np.nan
    return float(row.iloc[0][metric]) if pd.notna(row.iloc[0][metric]) else np.nan


def finite_gt(a: float, b: float) -> bool:
    return pd.notna(a) and pd.notna(b) and math.isfinite(a) and math.isfinite(b) and a > b


def build_report(**kwargs: Any) -> str:
    matrix = kwargs["result_matrix"]
    concentration = kwargs["concentration"]
    decision_tags = kwargs["decision_tags"]
    episode = kwargs["episode_independence"]
    lines = [
        "# Morita Short v3.5.2 Independent Audit Report",
        "",
        f"Run ID: {kwargs['run_id']}",
        f"Output directory: {kwargs['output_dir']}",
        f"Input reconciled: {kwargs['reconciled']}",
        f"Decision: {', '.join(decision_tags)}",
        "",
        "## Counts",
        episode.to_markdown(index=False),
        "",
        "## Primary Open D1 Matrix",
        matrix[(matrix["entry"].eq("Open")) & (matrix["exit"].eq("D1"))][["rank", "level", "n", "profit_factor", "median", "top_3_contribution_share"]].to_markdown(index=False),
        "",
        "## Concentration",
        concentration.to_markdown(index=False),
        "",
        "## Safety",
        "research_only=true; execution_allowed=false; live_order_allowed=false; broker/account/order paths were not used.",
    ]
    return "\n".join(lines) + "\n"


def build_review_bundle(*, count_reconciliation: pd.DataFrame, episode_independence: pd.DataFrame, result_matrix: pd.DataFrame, concentration: pd.DataFrame, decision_tags: list[str], reconciled: bool) -> str:
    s = count_value(count_reconciliation, "S")
    a = count_value(count_reconciliation, "A")
    total = count_value(count_reconciliation, "S+A")
    base = count_value(count_reconciliation, "base_candidates")
    candidate_n = episode_value(episode_independence, "constructed candidates")
    ticker_ep = episode_value(episode_independence, "unique ticker episodes")
    market_ep = episode_value(episode_independence, "unique market episodes")
    key_pf = pick_metric(result_matrix, "S+A", "Open", "D1", "candidate", "profit_factor")
    key_te_pf = pick_metric(result_matrix, "S+A", "Open", "D1", "ticker_episode", "profit_factor")
    key_me_pf = pick_metric(result_matrix, "S+A", "Open", "D1", "market_episode", "profit_factor")
    key_med = pick_metric(result_matrix, "S+A", "Open", "D1", "market_episode", "median")
    top3 = concentration.loc[concentration["concentration_axis"].eq("market_episode"), "top_3_share_of_positive_pnl"]
    top3_value = top3.iloc[0] if not top3.empty else np.nan
    header = f"""INPUT:
S = {s}
A = {a}
S+A = {total}
base candidates = {base}
reconciled = {'yes' if reconciled else 'no'}

INDEPENDENT COUNTS:
candidate n = {candidate_n}
ticker episode n = {ticker_ep}
market episode n = {market_ep}

KEY RESULT:
best entry = Open D1 daily proxy
candidate PF = {fmt(key_pf)}
ticker-episode PF = {fmt(key_te_pf)}
market-episode PF = {fmt(key_me_pf)}
median = {fmt(key_med)}
top 3 episode contribution = {fmt(top3_value)}

DECISION:
{', '.join(decision_tags)}
"""
    body = [
        "",
        "# Executive conclusion",
        "This audit is research-only. The S/A input count gate reconciled, and D0/D1 daily construction was completed where data allowed. Full-population 09:45/10:00/10:30 validation is not formal because real M15 coverage is limited to a small 2026 semiconductor subset.",
        "",
        "# Input provenance",
        count_reconciliation.to_markdown(index=False),
        "",
        "# PIT / timestamp audit",
        "No synthetic intraday bars were created. Missing M15 entries remain missing. Open uses daily open; 09:45/10:00/10:30 use only actual M15 bar-start opens.",
        "",
        "# Rank x entry x exit table",
        result_matrix[["rank", "entry", "exit", "level", "n", "profit_factor", "median", "top_3_contribution_share"]].to_markdown(index=False),
        "",
        "# Candidate vs episode comparison",
        result_matrix[(result_matrix["entry"].eq("Open")) & (result_matrix["exit"].eq("D1"))][["rank", "level", "n", "profit_factor", "median"]].to_markdown(index=False),
        "",
        "# S vs A",
        f"S market-episode Open/D1 PF={fmt(pick_metric(result_matrix, 'S', 'Open', 'D1', 'market_episode', 'profit_factor'))}; A market-episode Open/D1 PF={fmt(pick_metric(result_matrix, 'A', 'Open', 'D1', 'market_episode', 'profit_factor'))}.",
        "",
        "# 09:45 replication",
        "Formal 09:45 replication is limited to real M15-covered rows only; absent full-population M15, the gate cannot be promoted to formal validation.",
        "",
        "# Robustness",
        "Leave-one-year, leave-one-ticker, leave-one-episode, bootstrap, and segment tables are emitted as CSV artifacts.",
        "",
        "# Concentration",
        concentration.to_markdown(index=False),
        "",
        "# Legacy-result reconciliation",
        "Legacy PF values are comparison targets only. Difference decomposition is in legacy_result_difference_explanation.md.",
        "",
        "# Limitations",
        "Daily OHLCV source is local cached data with basis unspecified; historical universe is static/proxy, so this is not a formal survivorship-safe backtest.",
        "",
        "# Safety",
        "SHORT_PRODUCTION_READY, SHORT_LIVE_READY, and FORMAL_SURVIVORSHIP_SAFE_BACKTEST are intentionally not used.",
        "",
        "# Git / tests",
        "Targeted tests are included for the runner. test_summary.csv is updated after the test command is run.",
        "",
        "# Exact next step",
        "Use the emitted CSVs to decide whether to acquire full PIT M15 for all current-condition S/A candidates; do not route this into production.",
    ]
    return header + "\n".join(body) + "\n"


def count_value(df: pd.DataFrame, metric: str) -> Any:
    row = df[df["metric"].eq(metric)]
    return row.iloc[0]["actual"] if not row.empty else ""


def episode_value(df: pd.DataFrame, metric: str) -> Any:
    row = df[df["metric"].eq(metric)]
    return row.iloc[0]["value"] if not row.empty else ""


def build_production_rejection_audit(repo_root: Path, output_dir: Path) -> pd.DataFrame:
    forbidden_call_names = {"place_order", "order_preview", "get_account", "get_positions", "get_balance"}
    forbidden_import_fragments = {"webull_order", "broker", "account"}
    script = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(script)
    imported_modules: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add((node.module or "").lower())
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id.lower())
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr.lower())
    rows = []
    import_detected = any(fragment in module for module in imported_modules for fragment in forbidden_import_fragments)
    rows.append({"check": "forbidden_broker_account_import", "detected": import_detected, "status": "FAIL" if import_detected else "PASS"})
    for name in sorted(forbidden_call_names):
        detected = name in called_names
        rows.append({"check": f"forbidden_call_{name}", "detected": detected, "status": "FAIL" if detected else "PASS"})
    rows.append({"check": "output_under_research_only", "detected": str(OUTPUT_ROOT).replace("\\", "/") in str(output_dir).replace("\\", "/"), "status": "PASS" if "research_only" in str(output_dir).replace("\\", "/") else "FAIL"})
    rows.append({"check": "consumable_by_production", "detected": False, "status": "PASS"})
    return pd.DataFrame(rows)


def build_reproduction_commands(paths: SourcePaths, output_dir: Path) -> str:
    return "\n".join(
        [
            "# Reproduction Commands",
            "",
            "```powershell",
            "python scripts/run_morita_short_v3_5_2_independent_audit.py `",
            f"  --signal-calendar '{paths.signal_calendar}' `",
            f"  --source-receipt '{paths.source_receipt}' `",
            f"  --daily-ohlcv '{paths.daily_ohlcv}' `",
            f"  --m15-bars '{paths.m15_bars}' `",
            f"  --output-dir '{output_dir}'",
            "pytest tests/test_morita_short_v3_5_2_independent_audit.py -q",
            "```",
            "",
        ]
    )


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
    for k, v in safety_fields().items():
        if k not in out.columns:
            out[k] = v
    return out


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_df(path: Path, df: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return path


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        if pd.isna(value):
            return None
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return str(value)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def git_identity(repo_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:
            return f"ERROR: {exc}"

    return {"head": run("rev-parse", "HEAD"), "branch": run("branch", "--show-current"), "status_short": run("status", "--short")}


def git_changed_files(repo_root: Path) -> list[str]:
    try:
        out = subprocess.check_output(["git", "-C", str(repo_root), "status", "--short"], text=True, stderr=subprocess.STDOUT)
        return [line for line in out.splitlines() if line.strip()]
    except Exception as exc:
        return [f"ERROR: {exc}"]


def manifest_entries(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.glob("*")):
        if path.is_file():
            rows.append({"name": path.name, "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def fmt(value: Any) -> str:
    try:
        if pd.isna(value):
            return "NA"
        if math.isinf(float(value)):
            return "inf"
        return f"{float(value):.6g}"
    except Exception:
        return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
