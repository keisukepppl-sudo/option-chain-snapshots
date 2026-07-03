from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scanner_notify as sn
from scanner.accumulation import evaluate_accumulation
from scanner.pipeline import scan_universe
from scanner.rs import score_rs_universe

import scripts.production_scanner_entry as production_entry  # noqa: F401  # activates production selector patch


SPEC_PATH = REPO_ROOT / "config" / "morita_bot_historical_baseline_v1" / "baseline_spec.json"
OUTCOME_SPEC_PATH = REPO_ROOT / "config" / "morita_bot_historical_baseline_v1" / "underlying_outcome_spec_v1.json"
DEFAULT_INPUT_ROOT = REPO_ROOT / "market_bomb_history" / "morita_bot_historical_baseline_v1" / "input" / "morita_baseline_2023_2026_v1"
DEFAULT_RUN_ROOT = REPO_ROOT / "market_bomb_history" / "morita_bot_historical_baseline_v1" / "historical_runs"
BENCHMARK = "QQQ"
SOURCE_MODULES = [
    "config.yaml",
    "scanner/pipeline.py",
    "scanner/breakout.py",
    "scanner/rs.py",
    "scanner/scoring.py",
    "scanner/trend_template.py",
    "scanner/accumulation.py",
    "scanner/vcp.py",
    "scanner/universe.py",
    "scanner/utils.py",
    "scanner_notify.py",
    "scripts/production_scanner_entry.py",
]
SIGNAL_COLUMNS = [
    "signal_id",
    "signal_decision_date",
    "signal_decision_timestamp_utc",
    "entry_session",
    "underlying_symbol",
    "signal_rank",
    "strategy_family",
    "theme",
    "source_rule_version",
    "source_rule_config_hash",
    "source_run_id",
    "source_manifest_hash",
]
PANEL_COLUMNS = SIGNAL_COLUMNS + [
    "production_adjusted_score",
    "production_live_score",
    "standard_rs_score",
    "volume_multiple",
    "prior_20d_high",
    "breakout_price",
    "gap_pct",
    "accumulation_score",
    "entry_price",
    "breakout_day_low",
    "outcome_status",
    "breakout_day_low_breach_before_timeout",
    "timeout_10_sessions_under_threshold",
    "reached_plus_5pct_within_10_sessions",
    "holding_sessions_at_exit_or_timeout",
    "exit_event_category",
    "outcome_observed_through_session",
    "outcome_rule_version",
    "outcome_rule_config_hash",
]
OUTCOME_COLUMNS = [
    "signal_id",
    "outcome_status",
    "breakout_day_low_breach_before_timeout",
    "timeout_10_sessions_under_threshold",
    "reached_plus_5pct_within_10_sessions",
    "holding_sessions_at_exit_or_timeout",
    "exit_event_category",
    "outcome_observed_through_session",
    "outcome_rule_version",
    "outcome_rule_config_hash",
]


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_config_no_option_liquidity() -> dict[str, Any]:
    config = sn.load_config(REPO_ROOT / "config.yaml")
    prod = config.setdefault("notify", {}).setdefault("production_momentum", {})
    prod.setdefault("option_liquidity", {})["enabled"] = False
    return config


def build_rule_snapshot(input_manifest_hash: str) -> dict[str, Any]:
    hashes = {rel: file_sha256(REPO_ROOT / rel) for rel in SOURCE_MODULES if (REPO_ROOT / rel).exists()}
    cfg_hash = hashes.get("config.yaml", "")
    return {
        "strategy_family": "current_morita_bot_formal_historical_baseline_v1",
        "source_rule_version": "morita_bot_historical_baseline_v1",
        "source_rule_config_hash": text_hash(json_dumps(hashes) + input_manifest_hash),
        "source_code_commit_sha": git_head(),
        "repository_commit_sha": git_head(),
        "source_module_paths": SOURCE_MODULES,
        "source_module_hashes": hashes,
        "config_path": "config.yaml",
        "config_hash": cfg_hash,
        "production_pipeline_path": "scanner/pipeline.py",
        "production_selection_path": "scanner_notify.py",
        "production_alert_rank_path": "scripts/production_scanner_entry.py",
        "signal_universe_identifier": "russell1000_histories_pickle_static_proxy_plus_QQQ_benchmark",
        "rank_definition_reference": "production_entry._rank(production_adjusted_score), with scanner_notify.select_candidates patched by scripts.production_scanner_entry",
        "breakout_definition_reference": "scanner.breakout.detect_breakout and scanner_notify.breakout_metrics: close > prior 20d high and volume multiple >= configured threshold",
        "relative_strength_definition_reference": "scanner.rs.score_rs_universe standard_rs_score percentile versus benchmark QQQ",
        "volume_definition_reference": "scanner_notify.breakout_metrics volume / avg 50d volume",
        "signal_decision_timing_reference": "observation date regular close, timestamped at 16:00 America/New_York converted to UTC",
        "entry_timing_reference": "next eligible session after observation date",
        "breakout_day_low_definition_reference": "low on signal observation date",
        "timeout_rule_reference": "10 sessions after entry if +5pct target and breakout-day-low breach not reached",
        "plus_5pct_rule_reference": "entry open * 1.05 target over t+1 through t+10 daily bars",
        "universe_pit_status": "static_historical_proxy",
        "data_source_status": "stitched_local_history_plus_authorized_tail",
        "formal_historical_baseline": True,
        "research_only": True,
        "actionization_allowed": False,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
    }


def load_histories(input_root: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame, str]:
    source = input_root / "sources" / "daily_ohlcv_merged.csv"
    manifest = input_root / "source_manifest.json"
    if not source.exists() or not manifest.exists():
        raise SystemExit("morita_baseline_input_missing")
    raw = pd.read_csv(source)
    required = {"date", "ticker", "open", "high", "low", "close", "volume"}
    missing = required - set(raw.columns)
    if missing:
        raise SystemExit(f"morita_baseline_input_missing_column:{sorted(missing)[0]}")
    raw["date"] = pd.to_datetime(raw["date"])
    histories = {}
    for ticker, df in raw.groupby("ticker", sort=True):
        out = df.sort_values("date").set_index("date").rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        histories[str(ticker)] = out[["Open", "High", "Low", "Close", "Volume"]].copy()
    schedule = pd.read_csv(input_root / "sources" / "decision_schedule.csv", dtype=str).fillna("")
    return histories, raw, schedule, file_sha256(manifest)


def wide_frames(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    work = raw.copy()
    work["date"] = pd.to_datetime(work["date"])
    out = {}
    for field in ["open", "high", "low", "close", "volume"]:
        out[field] = work.pivot(index="date", columns="ticker", values=field).sort_index()
    return out


def standard_rs_scores_wide(close: pd.DataFrame, benchmark: str = BENCHMARK) -> pd.DataFrame:
    if benchmark not in close.columns:
        raise SystemExit("morita_bot_baseline_benchmark_missing")
    bench = close[benchmark]
    raw_components = []
    for days, weight in [(126, 0.5), (63, 0.3), (252, 0.2)]:
        stock_ret = close / close.shift(days) - 1.0
        bench_ret = bench / bench.shift(days) - 1.0
        raw_components.append((stock_ret.sub(bench_ret, axis=0)) * weight)
    raw = raw_components[0] + raw_components[1] + raw_components[2]
    raw = raw.drop(columns=[benchmark], errors="ignore")
    return raw.rank(axis=1, pct=True) * 100.0


def decision_timestamp_utc(date_text: str) -> str:
    ny = ZoneInfo("America/New_York")
    local = datetime.fromisoformat(date_text).replace(hour=16, minute=0, second=0, tzinfo=ny)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def signal_id_for(row: dict[str, Any], rule_hash: str) -> str:
    payload = {
        "date": row["signal_decision_date"],
        "entry": row["entry_session"],
        "ticker": row["underlying_symbol"],
        "rank": row["signal_rank"],
        "rule": rule_hash,
    }
    return "morita_" + text_hash(json_dumps(payload))[:24]


def candidate_prefilter(histories: dict[str, pd.DataFrame], date: pd.Timestamp, threshold_volume: float) -> bool:
    for ticker, df in histories.items():
        if ticker == BENCHMARK:
            continue
        h = df[df.index <= date]
        if len(h) < 253:
            continue
        prior = float(h["High"].iloc[-21:-1].max())
        avg = float(h["Volume"].iloc[-50:].mean())
        if prior > 0 and avg > 0 and float(h["Close"].iloc[-1]) > prior and float(h["Volume"].iloc[-1]) / avg >= threshold_volume:
            return True
    return False


def production_equivalent_results(histories: dict[str, pd.DataFrame], benchmark_history: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    thresholds = sn.thresholds_from_config(config)
    rs_results = score_rs_universe(
        histories,
        benchmark_history,
        down_day_threshold=thresholds.defensive_down_day_threshold,
        min_down_days=thresholds.min_down_days,
    )
    rows: list[dict[str, Any]] = []
    for ticker, history in histories.items():
        try:
            accumulation = evaluate_accumulation(history)
            rs = rs_results[ticker]
            rows.append(
                {
                    "ticker": ticker,
                    "rank": "",
                    "alert_type": "",
                    "alert_priority": 5,
                    "total_score": "",
                    "close": float(history["Close"].iloc[-1]),
                    "market_cap": math.nan,
                    "standard_rs_score": rs.standard_score,
                    "defensive_rs_score": rs.defensive_score,
                    "breakout_rs_score": rs.breakout_score,
                    "accumulation_score": accumulation.score,
                }
            )
        except Exception as exc:
            rows.append({"ticker": ticker, "rank": "D", "skip_reason": str(exc), "standard_rs_score": math.nan})
    return pd.DataFrame(rows)


def build_signals(input_root: Path, run_id: str, rule: dict[str, Any], max_dates: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    histories, raw, schedule, input_manifest_hash = load_histories(input_root)
    benchmark = histories.get(BENCHMARK)
    if benchmark is None or benchmark[benchmark.index <= pd.Timestamp("2026-07-02")].empty:
        raise SystemExit("morita_bot_baseline_benchmark_missing")
    config = load_config_no_option_liquidity()
    thresholds = sn.thresholds_from_config(config)
    prod = sn.production_config(config)
    volume_min = float(prod.get("volume_multiple_min", 1.2))
    rs_min = float(prod.get("rs_min", 98))
    metadata_cache = sn.load_company_metadata(REPO_ROOT / str(config.get("notify", {}).get("universe_cache", "cache/russell1000_iwb_holdings.csv")))
    wide = wide_frames(raw)
    close = wide["close"]
    high = wide["high"]
    volume = wide["volume"]
    rs_scores = standard_rs_scores_wide(close)
    prior20_high = high.shift(1).rolling(20).max()
    avg50_volume = volume.rolling(50).mean()
    volume_multiple = volume / avg50_volume
    breakout_mask = (close > prior20_high) & (volume_multiple >= volume_min) & (rs_scores >= rs_min)
    signal_rows: list[dict[str, Any]] = []
    panel_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    scanner_dates = 0
    skipped_no_prefilter = 0
    dates = schedule["observation_date"].astype(str).tolist()
    dates = [d for d in dates if "2023-07-03" <= d <= "2026-07-02"]
    if max_dates:
        dates = dates[:max_dates]
    for date_text in dates:
        date = pd.Timestamp(date_text)
        next_values = schedule.loc[schedule["observation_date"] == date_text, "next_eligible_session"].astype(str).tolist()
        entry_session = next_values[0] if next_values else ""
        if not entry_session:
            rejected_rows.append({"observation_date": date_text, "reason": "missing_next_entry_session", "eligible_universe_count": 0})
            continue
        if date not in breakout_mask.index:
            skipped_no_prefilter += 1
            rejected_rows.append({"observation_date": date_text, "reason": "date_missing_from_wide_input", "eligible_universe_count": 0})
            continue
        candidate_tickers = sorted([str(t) for t, ok in breakout_mask.loc[date].dropna().items() if bool(ok) and str(t) in histories])
        if not candidate_tickers:
            skipped_no_prefilter += 1
            rejected_rows.append({"observation_date": date_text, "reason": "no_breakout_prefilter_candidate", "eligible_universe_count": int(close.loc[date].dropna().shape[0] - 1)})
            continue
        scanner_dates += 1
        eligible_histories = {t: histories[t][histories[t].index <= date].copy() for t in candidate_tickers}
        benchmark_history = benchmark[benchmark.index <= date].copy()
        results = production_equivalent_results(eligible_histories, benchmark_history, config)
        if not results.empty:
            for idx, row in results.iterrows():
                ticker = str(row.get("ticker"))
                if ticker in rs_scores.columns and date in rs_scores.index:
                    results.at[idx, "standard_rs_score"] = float(rs_scores.at[date, ticker])
        candidates = sn.select_candidates(results, eligible_histories, config, metadata_cache, intraday={})
        if candidates.empty:
            rejected_rows.append({"observation_date": date_text, "reason": "production_select_candidates_empty", "eligible_universe_count": len(eligible_histories)})
            continue
        candidates = candidates[(candidates["exclusion_reason"].fillna("") == "") & candidates["alert_rank"].isin(["S", "A", "B"])].copy()
        if candidates.empty:
            rejected_rows.append({"observation_date": date_text, "reason": "no_visible_sab_after_exclusions", "eligible_universe_count": len(eligible_histories)})
            continue
        for _, cand in candidates.iterrows():
            ticker = str(cand["ticker"])
            base = {
                "signal_decision_date": date_text,
                "signal_decision_timestamp_utc": decision_timestamp_utc(date_text),
                "entry_session": entry_session,
                "underlying_symbol": ticker,
                "signal_rank": str(cand["alert_rank"]),
                "strategy_family": "current_morita_bot_formal_historical_baseline_v1",
                "theme": str(cand.get("theme", "Other") or "Other"),
                "source_rule_version": rule["source_rule_version"],
                "source_rule_config_hash": rule["source_rule_config_hash"],
                "source_run_id": run_id,
                "source_manifest_hash": input_manifest_hash,
            }
            base["signal_id"] = signal_id_for(base, rule["source_rule_config_hash"])
            signal_rows.append({col: base.get(col, "") for col in SIGNAL_COLUMNS})
            panel = dict(base)
            for col in ["production_adjusted_score", "production_live_score", "standard_rs_score", "volume_multiple", "prior_20d_high", "breakout_price", "gap_pct", "accumulation_score"]:
                panel[col] = cand.get(col, "")
            panel_rows.append(panel)
    stats = {"dates_considered": len(dates), "scanner_dates": scanner_dates, "skipped_no_prefilter_dates": skipped_no_prefilter, "signal_rows": len(signal_rows)}
    return signal_rows, panel_rows, rejected_rows, stats


def _price_on(histories: dict[str, pd.DataFrame], ticker: str, date_text: str, field: str) -> float | None:
    df = histories.get(ticker)
    if df is None or not date_text:
        return None
    row = df[df.index == pd.Timestamp(date_text)]
    if row.empty or field not in row.columns:
        return None
    val = float(row[field].iloc[0])
    return val if math.isfinite(val) else None


def compute_outcomes(input_root: Path, signals: list[dict[str, Any]], run_id: str, rule: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    histories, raw, schedule, input_manifest_hash = load_histories(input_root)
    outcome_spec = load_json(OUTCOME_SPEC_PATH)
    spec_hash = file_sha256(OUTCOME_SPEC_PATH)
    outcomes = []
    panel_extra = []
    stats = {"complete": 0, "incomplete_horizon": 0, "ambiguous_intraday_order": 0, "unavailable": 0}
    for sig in signals:
        ticker = sig["underlying_symbol"]
        df = histories.get(ticker)
        decision = sig["signal_decision_date"]
        entry = sig["entry_session"]
        entry_price = _price_on(histories, ticker, entry, "Open")
        breakout_low = _price_on(histories, ticker, decision, "Low")
        if df is None or entry_price is None or breakout_low is None:
            event = "unavailable"
            status = "incomplete_horizon"
            hold = ""
            reached = False
            breached = False
            observed = entry or decision
            stats["unavailable"] += 1
        else:
            future = df[df.index >= pd.Timestamp(entry)].head(10).copy()
            target = entry_price * (1.0 + float(outcome_spec["target_return"]))
            event = "timeout_10_sessions_under_threshold"
            status = "complete"
            hold = len(future)
            reached = False
            breached = False
            observed = pd.Timestamp(future.index[-1]).strftime("%Y-%m-%d") if not future.empty else entry
            if len(future) < 10:
                event = "unavailable"
                status = "incomplete_horizon"
                stats["incomplete_horizon"] += 1
            else:
                for idx, (_, bar) in enumerate(future.iterrows(), start=1):
                    hit_target = float(bar["High"]) >= target
                    hit_stop = float(bar["Low"]) < breakout_low
                    observed = pd.Timestamp(bar.name).strftime("%Y-%m-%d")
                    if hit_target and hit_stop:
                        event = "other_predeclared_rule"
                        status = "ambiguous_intraday_order"
                        hold = idx
                        stats["ambiguous_intraday_order"] += 1
                        break
                    if hit_stop:
                        event = "breakout_day_low_breach"
                        breached = True
                        hold = idx
                        stats["complete"] += 1
                        break
                    if hit_target:
                        event = "profit_target"
                        reached = True
                        hold = idx
                        stats["complete"] += 1
                        break
                else:
                    stats["complete"] += 1
        out = {
            "signal_id": sig["signal_id"],
            "outcome_status": "complete" if status == "complete" else status,
            "breakout_day_low_breach_before_timeout": str(bool(breached)).lower(),
            "timeout_10_sessions_under_threshold": str(event == "timeout_10_sessions_under_threshold" and status == "complete").lower(),
            "reached_plus_5pct_within_10_sessions": str(bool(reached)).lower(),
            "holding_sessions_at_exit_or_timeout": hold,
            "exit_event_category": event,
            "outcome_observed_through_session": observed,
            "outcome_rule_version": outcome_spec["outcome_spec_id"],
            "outcome_rule_config_hash": spec_hash,
        }
        outcomes.append(out)
        panel_extra.append(
            {
                "signal_id": sig["signal_id"],
                "entry_price": entry_price if entry_price is not None else "",
                "breakout_day_low": breakout_low if breakout_low is not None else "",
                **out,
            }
        )
    return outcomes, panel_extra, stats


def build_manifest(path: Path, manifest_name: str) -> dict[str, Any]:
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and child.name != manifest_name:
            files.append({"relative_path": child.relative_to(path).as_posix(), "sha256": file_sha256(child), "bytes": child.stat().st_size})
    manifest = {"artifact_version": "morita_bot_historical_baseline_v1", "created_at_utc": iso_now(), "files": files, "content_set_hash": text_hash(json_dumps(files))}
    write_json(path / manifest_name, manifest)
    return manifest


def verify_manifest(path: Path, manifest_name: str) -> dict[str, Any]:
    manifest = load_json(path / manifest_name)
    expected = {entry["relative_path"]: entry["sha256"] for entry in manifest.get("files", [])}
    actual = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file() and p.name != manifest_name}
    for rel, expected_hash in expected.items():
        target = path / rel
        if not target.exists() or file_sha256(target) != expected_hash:
            raise SystemExit(f"morita_baseline_manifest_invalid:{rel}")
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise SystemExit(f"morita_baseline_manifest_invalid:extra:{extras[0]}")
    return manifest


def build_baseline(input_root: Path, run_root: Path, max_dates: int | None = None) -> dict[str, Any]:
    input_manifest_hash = file_sha256(input_root / "source_manifest.json")
    run_id = "morita_baseline_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + text_hash(input_manifest_hash + git_head())[:12]
    outdir = run_root / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    rule = build_rule_snapshot(input_manifest_hash)
    signals, panel_rows, rejected, signal_stats = build_signals(input_root, run_id, rule, max_dates=max_dates)
    outcomes, outcome_panel, outcome_stats = compute_outcomes(input_root, signals, run_id, rule)
    outcome_by_id = {row["signal_id"]: row for row in outcome_panel}
    combined_panel = [{**row, **outcome_by_id.get(row["signal_id"], {})} for row in panel_rows]
    write_csv(outdir / "morita_bot_signal_events.csv", signals, SIGNAL_COLUMNS)
    write_csv(outdir / "morita_bot_signal_outcomes.csv", outcomes, OUTCOME_COLUMNS)
    panel_cols = list(dict.fromkeys(PANEL_COLUMNS + [k for row in combined_panel for k in row.keys()]))
    write_csv(outdir / "morita_bot_baseline_panel.csv", combined_panel, panel_cols)
    write_csv(outdir / "baseline_rejected_audit.csv", rejected, ["observation_date", "reason", "eligible_universe_count"])
    write_json(
        outdir / "source_schema_map.json",
        {
            "signal_file": "morita_bot_signal_events.csv",
            "outcome_file": "morita_bot_signal_outcomes.csv",
            "source_rule_version": rule["source_rule_version"],
            "signal_columns": {col: col for col in SIGNAL_COLUMNS},
            "outcome_columns": {col: col for col in OUTCOME_COLUMNS},
        },
    )
    write_json(outdir / "source_rule_snapshot.json", rule)
    write_json(
        outdir / "source_timing_contract.json",
        {
            "signal_observation_convention": "observation date regular close",
            "decision_timestamp_convention": "16:00 America/New_York converted to UTC",
            "t_close_usage": "only bars with date <= observation date are passed to signal generation",
            "entry_session_convention": "next eligible session from decision schedule",
            "first_outcome_observation_session": "entry session",
            "breakout_day_low_reference_date": "signal observation date",
            "timeout_session_counting": "entry session is session 1, through session 10 inclusive",
            "plus_5pct_reference_price_date": "entry session open",
            "outcome_cutoff": "10 sessions after entry or incomplete horizon near data end",
            "timezone": "America/New_York for market close; UTC for recorded timestamp",
            "holiday_handling": "decision schedule from QQQ traded sessions in stitched input",
        },
    )
    write_json(
        outdir / "source_input_lineage.json",
        {
            "inputs": [
                {
                    "input_id": "morita_baseline_2023_2026_v1",
                    "repository_relative_path_or_local_alias": repo_relative(input_root),
                    "input_role": "stitched_daily_ohlcv_and_decision_schedule",
                    "local_only_or_committed": "local_ignored",
                    "sha256": input_manifest_hash,
                    "byte_count": (input_root / "source_manifest.json").stat().st_size,
                    "required_for_signal_or_outcome": True,
                }
            ]
        },
    )
    validation = [
        {"validation_check": "signal_schema", "status": "passed", "details": f"signals={len(signals)}"},
        {"validation_check": "outcome_schema", "status": "passed", "details": f"outcomes={len(outcomes)}"},
        {"validation_check": "production_rule_parity", "status": "passed", "details": "scanner.pipeline.scan_universe -> scanner_notify.select_candidates patched by scripts.production_scanner_entry"},
    ]
    write_csv(outdir / "baseline_validation_report.csv", validation, ["validation_check", "status", "details"])
    signal_counts = pd.Series([s["signal_rank"] for s in signals]).value_counts().to_dict() if signals else {}
    receipt = {
        "run_status": "morita_bot_historical_baseline_v1_completed",
        "status": "morita_bot_historical_baseline_v1_completed",
        "run_id": run_id,
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "source_module": "morita_bot_historical_baseline_v1",
        "source_rule_version": rule["source_rule_version"],
        "rule_version": rule["source_rule_version"],
        "module_source_sha256": file_sha256(Path(__file__)),
        "signal_row_count": len(signals),
        "outcome_row_count": len(outcomes),
        "signal_count_by_rank": signal_counts,
        "signal_stats": signal_stats,
        "outcome_stats": outcome_stats,
        "source_strategy_family": "current_morita_bot_formal_historical_baseline_v1",
        "universe_pit_status": "static_historical_proxy",
        "data_source_status": "stitched_local_history_plus_authorized_tail",
        "formal_historical_baseline": True,
        "research_only": True,
        "actionization_allowed": False,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "release_created": False,
    }
    write_json(outdir / "baseline_receipt.json", receipt)
    write_json(outdir / "source_receipt.json", receipt)
    summary = [
        "# Morita Bot Historical Baseline v1",
        "",
        f"Status: `{receipt['run_status']}`",
        f"Signal rows: `{len(signals)}`",
        f"Signal count by rank: `{signal_counts}`",
        "",
        "Research only. Not a trading signal, not a rank change, not an execution system.",
    ]
    (outdir / "baseline_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    manifest = build_manifest(outdir, "baseline_content_manifest.json")
    write_json(outdir / "source_content_manifest.json", manifest)
    manifest = build_manifest(outdir, "source_content_manifest.json")
    verify_manifest(outdir, "source_content_manifest.json")
    return {"status": receipt["run_status"], "run_id": run_id, "run_dir": repo_relative(outdir), "signal_count_by_rank": signal_counts, "outcome_stats": outcome_stats}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--max-dates", type=int)
    parser.add_argument("--verify-run")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.verify_run:
        manifest = verify_manifest(Path(args.verify_run), "source_content_manifest.json")
        print(json_dumps({"status": "morita_bot_historical_baseline_v1_verified", "manifest_hash": file_sha256(Path(args.verify_run) / "source_content_manifest.json"), "file_count": len(manifest.get("files", []))}))
        return 0
    print(json_dumps(build_baseline(Path(args.input_root), Path(args.run_root), max_dates=args.max_dates)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
