from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.morita_single_call_reference import s_single_call_reference_engine as ref

OUT = REPO_ROOT / "outputs" / "morita_current_s_notification_quality_audit_v0_1"
BUNDLE = REPO_ROOT / "morita_current_s_notification_quality_audit_v0_1_bundle.md"
SPEC_PATH = REPO_ROOT / "config" / "morita_current_s_notification_quality_audit_v0_1" / "audit_spec.json"
BASELINE_DIR = (
    REPO_ROOT
    / "market_bomb_history"
    / "morita_bot_historical_baseline_v1"
    / "historical_runs"
    / "morita_baseline_20260703T123912Z_4994e3744ffa"
)
FORMAL_PANEL = BASELINE_DIR / "morita_bot_baseline_panel.csv"

REQUIRED_OUTPUTS = [
    "source_verification.csv",
    "current_s_notification_quality_audit.csv",
    "source_trace_and_filter_map.md",
    "classification_rulebook.md",
    "classification_summary.csv",
    "native_only_performance_summary.csv",
    "native_plus_proxy_performance_summary.csv",
    "class_subperiod_stability.csv",
    "class_path_risk_summary.csv",
    "class_fixed_iv_reference_summary.csv",
    "representative_deterministic_rows.csv",
    "audit_receipt.json",
    "audit_content_manifest.json",
    "audit_summary.md",
]

CLASS_RULE_VERSION = "morita_current_s_notification_quality_audit_v0_1_proxy_first_s_and_20_session_extension"
CONFIDENCE_ORDER = ["NATIVE_CONFIRMED", "PROXY_CONFIRMED", "UNRESOLVED", "OUTSIDE_COVERAGE"]
FINAL_CLASSES = [
    "CURRENT_S_INITIAL_BREAKOUT",
    "CURRENT_S_REBREAKOUT",
    "CURRENT_S_EXTENDED_FOMO",
    "CURRENT_S_UNRESOLVED",
    "OUTSIDE_SOURCE_COVERAGE",
]
FORBIDDEN_OUTPUT_TOKENS = ["BUY_NOW", "SELL_NOW", "WEBULL_ORDER", "PORTFOLIO_EQUITY_CURVE", "POSITION_SIZE_RULE_CHANGE"]


def utc_now() -> str:
    return pd.Timestamp.now(tz="UTC").replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(ts) else str(ts.date())


def safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        value = float(value)
        if not math.isfinite(value):
            return None
        return value
    except Exception:
        return None


def profit_factor(values: list[float]) -> float | str:
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return "not_estimable_zero_gross_loss" if gains > 0 else ""
    return gains / losses


def baseline_receipt() -> dict[str, Any]:
    return json.loads((BASELINE_DIR / "baseline_receipt.json").read_text(encoding="utf-8"))


def baseline_input_root() -> Path:
    lineage = json.loads((BASELINE_DIR / "source_input_lineage.json").read_text(encoding="utf-8"))
    rel = lineage["inputs"][0]["repository_relative_path_or_local_alias"]
    return REPO_ROOT / rel


def load_sessions() -> list[str]:
    schedule = pd.read_csv(baseline_input_root() / "sources" / "decision_schedule.csv", dtype=str).fillna("")
    dates = sorted(set(schedule["observation_date"]) | set(schedule["next_eligible_session"]))
    return [d for d in dates if d]


def session_gap(session_pos: dict[str, int], start: str, end: str) -> int | None:
    if start not in session_pos or end not in session_pos:
        return None
    return session_pos[end] - session_pos[start]


def source_verification_rows() -> list[dict[str, Any]]:
    receipt = baseline_receipt()
    paths = {
        "formal_baseline_panel": FORMAL_PANEL,
        "formal_baseline_receipt": BASELINE_DIR / "baseline_receipt.json",
        "formal_source_lineage": BASELINE_DIR / "source_input_lineage.json",
        "audit_spec": SPEC_PATH,
        "scanner_breakout_code": REPO_ROOT / "scanner" / "breakout.py",
        "scanner_scoring_code": REPO_ROOT / "scanner" / "scoring.py",
        "production_pullback_mode_notification_code": REPO_ROOT / "scripts" / "production_scanner_entry_pullback_mode.py",
        "historical_baseline_builder": REPO_ROOT / "scripts" / "build_morita_bot_historical_baseline_v1.py",
    }
    rows = []
    for component, path in paths.items():
        rows.append(
            {
                "component": component,
                "path": repo_relative(path),
                "exists": path.exists(),
                "sha256": sha256_file(path) if path.exists() else "",
                "source_run_id": receipt.get("run_id", ""),
                "source_commit": receipt.get("repository_commit_sha", ""),
                "status": "verified" if path.exists() else "missing",
            }
        )
    return rows


def load_formal_s() -> pd.DataFrame:
    df = pd.read_csv(FORMAL_PANEL, dtype={"signal_id": str}).fillna("")
    s = df[df["signal_rank"].astype(str).eq("S")].copy()
    s["ticker"] = s["underlying_symbol"].astype(str).str.upper()
    s["signal_date"] = s["signal_decision_date"].map(norm_date)
    s["entry_date"] = s["entry_session"].map(norm_date)
    return s.sort_values(["ticker", "entry_date", "signal_id"]).reset_index(drop=True)


def native_logic_status(panel_columns: list[str]) -> dict[str, Any]:
    native_fields = {
        "original_breakout_date": [c for c in panel_columns if c in {"original_breakout_date", "native_original_breakout_date"}],
        "breakout_id": [c for c in panel_columns if c in {"breakout_id", "base_breakout_id"}],
        "base_id": [c for c in panel_columns if c in {"base_id", "native_base_id"}],
        "extended_flag": [c for c in panel_columns if "extended" in c.lower()],
        "cooldown": [c for c in panel_columns if "cooldown" in c.lower()],
        "reset_or_rebase": [c for c in panel_columns if re.search(r"reset|rebase", c, re.I)],
    }
    found = {k: v for k, v in native_fields.items() if v}
    status = "NATIVE_CURRENT_S_LOGIC_PARTIAL" if found else "NATIVE_CURRENT_S_LOGIC_NOT_FOUND"
    return {"status": status, "found_fields": found, "missing_field_groups": [k for k, v in native_fields.items() if not v]}


def classify_notifications(s: pd.DataFrame, session_pos: dict[str, int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    receipt = baseline_receipt()
    native = native_logic_status(list(s.columns))
    rows: list[dict[str, Any]] = []
    for ticker, group in s.groupby("ticker"):
        prior_dates: list[str] = []
        for _, row in group.sort_values(["entry_date", "signal_id"]).iterrows():
            prior_count = len(prior_dates)
            prior_date = prior_dates[-1] if prior_dates else ""
            gap = session_gap(session_pos, prior_date, row["entry_date"]) if prior_date else None
            if not row["entry_date"] or not row["signal_date"]:
                classification = "OUTSIDE_SOURCE_COVERAGE"
                evidence = "OUTSIDE_SOURCE_COVERAGE"
                confidence = "OUTSIDE_COVERAGE"
                reason = "missing_signal_or_entry_date"
            elif prior_count == 0:
                classification = "CURRENT_S_INITIAL_BREAKOUT"
                evidence = "PROXY_INITIAL_BREAKOUT"
                confidence = "PROXY_CONFIRMED"
                reason = "first_same_ticker_raw_s_in_formal_current_s_stream"
            elif gap is not None and gap <= 20:
                classification = "CURRENT_S_EXTENDED_FOMO"
                evidence = "PROXY_EXTENDED_FOMO"
                confidence = "PROXY_CONFIRMED"
                reason = "same_ticker_prior_raw_s_within_20_eligible_sessions_no_native_reset_or_base_id"
            else:
                classification = "CURRENT_S_UNRESOLVED"
                evidence = "NO_NATIVE_REBREAKOUT_PROOF"
                confidence = "UNRESOLVED"
                reason = "prior_same_ticker_raw_s_exists_but_gap_alone_cannot_prove_rebreakout"
            rows.append(
                {
                    "raw_s_event_id": row["signal_id"],
                    "ticker": ticker,
                    "signal_decision_date": row["signal_date"],
                    "entry_session": row["entry_date"],
                    "signal_rank": row["signal_rank"],
                    "production_adjusted_score": row.get("production_adjusted_score", ""),
                    "source_run_id": row.get("source_run_id", receipt.get("run_id", "")),
                    "source_code_commit": receipt.get("repository_commit_sha", ""),
                    "source_config_identity": row.get("source_rule_config_hash", ""),
                    "prior_same_ticker_raw_s_count": prior_count,
                    "most_recent_prior_raw_s_date": prior_date,
                    "eligible_sessions_since_prior_raw_s": "" if gap is None else gap,
                    "native_breakout_id_if_available": "",
                    "native_original_breakout_date_if_available": "",
                    "native_base_id_if_available": "",
                    "native_extended_flag_if_available": "",
                    "native_reset_or_rebase_flag_if_available": "",
                    "classification": classification,
                    "classification_evidence": evidence,
                    "classification_confidence": confidence,
                    "classification_reason_code": reason,
                    "classification_rule_version": CLASS_RULE_VERSION,
                    "source_coverage_status": native["status"],
                }
            )
            prior_dates.append(row["entry_date"])
    return rows, native


def load_ohlcv_subset(tickers: set[str]) -> dict[str, pd.DataFrame]:
    source = baseline_input_root() / "sources" / "daily_ohlcv_merged.csv"
    chunks = []
    for chunk in pd.read_csv(source, usecols=["ticker", "date", "open", "high", "low", "close", "volume"], chunksize=250_000):
        chunk["ticker"] = chunk["ticker"].astype(str).str.upper()
        chunk = chunk[chunk["ticker"].isin(tickers)].copy()
        if not chunk.empty:
            chunks.append(chunk)
    if not chunks:
        return {}
    raw = pd.concat(chunks, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["date"])
    return {ticker: group.sort_values("date").reset_index(drop=True) for ticker, group in raw.groupby("ticker")}


def outcome_for_row(row: dict[str, Any], source_by_id: dict[str, dict[str, Any]], histories: dict[str, pd.DataFrame]) -> dict[str, Any]:
    out = dict(row)
    metric_defaults = {
        "underlying_return_5_sessions": "",
        "underlying_return_10_sessions": "",
        "underlying_return_20_sessions": "",
        "plus_5pct_within_10_sessions": "",
        "plus_10pct_within_20_sessions": "",
        "MAE_LOW_5": "",
        "MAE_LOW_10": "",
        "MAE_LOW_20": "",
        "CLOSE_DRAWDOWN_5": "",
        "CLOSE_DRAWDOWN_10": "",
        "CLOSE_DRAWDOWN_20": "",
        "MFE_HIGH_5": "",
        "MFE_HIGH_10": "",
        "MFE_HIGH_20": "",
        "outcome_coverage_status": "",
    }
    out.update(metric_defaults)
    source = source_by_id[row["raw_s_event_id"]]
    entry_price = safe_float(source.get("entry_price"))
    hist = histories.get(row["ticker"])
    if hist is None or hist.empty:
        out["outcome_coverage_status"] = "missing_ticker_ohlcv"
        return out
    if entry_price is None or entry_price <= 0:
        out["outcome_coverage_status"] = "missing_entry_price"
        return out
    idxs = hist.index[hist["date"] == pd.Timestamp(row["entry_session"])].tolist()
    if not idxs:
        out["outcome_coverage_status"] = "missing_entry_session_ohlcv"
        return out
    idx = idxs[0]
    if idx + 20 >= len(hist):
        out["outcome_coverage_status"] = "insufficient_forward_20_sessions"
        return out
    for horizon in [5, 10, 20]:
        window = hist.iloc[idx : idx + horizon + 1]
        close = safe_float(hist.loc[idx + horizon, "close"])
        if close is not None:
            out[f"underlying_return_{horizon}_sessions"] = close / entry_price - 1.0
        out[f"MAE_LOW_{horizon}"] = float(window["low"].min()) / entry_price - 1.0
        out[f"CLOSE_DRAWDOWN_{horizon}"] = float(window["close"].min()) / entry_price - 1.0
        out[f"MFE_HIGH_{horizon}"] = float(window["high"].max()) / entry_price - 1.0
    out["plus_5pct_within_10_sessions"] = bool(float(out["MFE_HIGH_10"]) >= 0.05)
    out["plus_10pct_within_20_sessions"] = bool(float(out["MFE_HIGH_20"]) >= 0.10)
    out["outcome_coverage_status"] = "complete"
    return out


def add_outcomes(audit_rows: list[dict[str, Any]], s: pd.DataFrame) -> list[dict[str, Any]]:
    source_by_id = {str(row["signal_id"]): row.to_dict() for _, row in s.iterrows()}
    histories = load_ohlcv_subset({row["ticker"] for row in audit_rows})
    return [outcome_for_row(row, source_by_id, histories) for row in audit_rows]


def subperiod(date_text: str) -> str:
    date = pd.Timestamp(date_text)
    if date.year == 2024:
        return "2024"
    if date.year == 2025:
        return "2025"
    if date.year == 2026 and date <= pd.Timestamp("2026-06-30"):
        return "2026_H1"
    return "other"


def confidence_filter(df: pd.DataFrame, universe: str) -> pd.DataFrame:
    if universe == "native_only":
        return df[df["classification_confidence"] == "NATIVE_CONFIRMED"].copy()
    if universe == "native_plus_proxy":
        return df[df["classification_confidence"].isin(["NATIVE_CONFIRMED", "PROXY_CONFIRMED"])].copy()
    raise ValueError(universe)


def bool_rate(series: pd.Series) -> float | str:
    if series.empty:
        return ""
    return float(series.astype(str).str.lower().eq("true").mean())


def performance_summary(outcomes: list[dict[str, Any]], universe: str, periods: list[str]) -> list[dict[str, Any]]:
    df = pd.DataFrame(outcomes)
    df = confidence_filter(df, universe)
    if df.empty:
        rows = []
        for period in periods:
            for klass in FINAL_CLASSES:
                rows.append(
                    {
                        "evidence_universe": universe,
                        "subperiod": period,
                        "classification": klass,
                        "notification_count": 0,
                        "eligible_observation_count": 0,
                        "unique_tickers": 0,
                        "outcome_coverage": "",
                        "mean_5d_return": "",
                        "median_5d_return": "",
                        "mean_10d_return": "",
                        "median_10d_return": "",
                        "mean_20d_return": "",
                        "median_20d_return": "",
                        "plus_5pct_within_10_rate": "",
                        "plus_10pct_within_20_rate": "",
                        "MAE_LOW_20_median": "",
                        "MAE_LOW_20_p10": "",
                        "MAE_LOW_20_p05": "",
                        "CLOSE_DRAWDOWN_20_median": "",
                        "CLOSE_DRAWDOWN_20_p10": "",
                        "MFE_HIGH_20_median": "",
                        "MFE_HIGH_20_p90": "",
                        "share_MAE_LOW_20_le_minus10": "",
                        "share_MAE_LOW_20_le_minus20": "",
                        "share_MAE_LOW_20_le_minus30": "",
                        "sample_label": "SPARSE_SAMPLE",
                    }
                )
        return rows
    df["subperiod"] = df["entry_session"].map(subperiod)
    rows = []
    for period in periods:
        scope = df if period == "full_range" else df[df["subperiod"] == period]
        for klass in FINAL_CLASSES:
            group = scope[scope["classification"] == klass]
            complete = group[group["outcome_coverage_status"] == "complete"]
            def nums(col: str) -> pd.Series:
                return pd.to_numeric(complete[col], errors="coerce").dropna()
            n = len(complete)
            row = {
                "evidence_universe": universe,
                "subperiod": period,
                "classification": klass,
                "notification_count": int(len(group)),
                "eligible_observation_count": int(n),
                "unique_tickers": int(complete["ticker"].nunique()) if n else 0,
                "outcome_coverage": n / len(group) if len(group) else "",
                "mean_5d_return": nums("underlying_return_5_sessions").mean() if n else "",
                "median_5d_return": nums("underlying_return_5_sessions").median() if n else "",
                "mean_10d_return": nums("underlying_return_10_sessions").mean() if n else "",
                "median_10d_return": nums("underlying_return_10_sessions").median() if n else "",
                "mean_20d_return": nums("underlying_return_20_sessions").mean() if n else "",
                "median_20d_return": nums("underlying_return_20_sessions").median() if n else "",
                "plus_5pct_within_10_rate": bool_rate(complete["plus_5pct_within_10_sessions"]) if n else "",
                "plus_10pct_within_20_rate": bool_rate(complete["plus_10pct_within_20_sessions"]) if n else "",
                "MAE_LOW_20_median": nums("MAE_LOW_20").median() if n else "",
                "MAE_LOW_20_p10": nums("MAE_LOW_20").quantile(0.10) if n else "",
                "MAE_LOW_20_p05": nums("MAE_LOW_20").quantile(0.05) if n else "",
                "CLOSE_DRAWDOWN_20_median": nums("CLOSE_DRAWDOWN_20").median() if n else "",
                "CLOSE_DRAWDOWN_20_p10": nums("CLOSE_DRAWDOWN_20").quantile(0.10) if n else "",
                "MFE_HIGH_20_median": nums("MFE_HIGH_20").median() if n else "",
                "MFE_HIGH_20_p90": nums("MFE_HIGH_20").quantile(0.90) if n else "",
                "share_MAE_LOW_20_le_minus10": float((nums("MAE_LOW_20") <= -0.10).mean()) if n else "",
                "share_MAE_LOW_20_le_minus20": float((nums("MAE_LOW_20") <= -0.20).mean()) if n else "",
                "share_MAE_LOW_20_le_minus30": float((nums("MAE_LOW_20") <= -0.30).mean()) if n else "",
                "sample_label": "SPARSE_SAMPLE" if n < 15 else "OK",
            }
            rows.append(row)
    return rows


def class_path_risk_summary(perf_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_universe": row["evidence_universe"],
            "subperiod": row["subperiod"],
            "classification": row["classification"],
            "eligible_observation_count": row["eligible_observation_count"],
            "MAE_LOW_20_median": row["MAE_LOW_20_median"],
            "MAE_LOW_20_p10": row["MAE_LOW_20_p10"],
            "MAE_LOW_20_p05": row["MAE_LOW_20_p05"],
            "CLOSE_DRAWDOWN_20_median": row["CLOSE_DRAWDOWN_20_median"],
            "CLOSE_DRAWDOWN_20_p10": row["CLOSE_DRAWDOWN_20_p10"],
            "share_MAE_LOW_20_le_minus10": row["share_MAE_LOW_20_le_minus10"],
            "share_MAE_LOW_20_le_minus20": row["share_MAE_LOW_20_le_minus20"],
            "share_MAE_LOW_20_le_minus30": row["share_MAE_LOW_20_le_minus30"],
            "per_entry_path_risk_not_portfolio_dd": True,
        }
        for row in perf_rows
        if row["subperiod"] == "full_range"
    ]


def classification_summary(audit_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(audit_rows)
    rows = []
    for klass in FINAL_CLASSES:
        sub = df[df["classification"] == klass]
        rows.append(
            {
                "classification": klass,
                "count": int(len(sub)),
                "unique_tickers": int(sub["ticker"].nunique()) if len(sub) else 0,
                "native_confirmed_count": int((sub["classification_confidence"] == "NATIVE_CONFIRMED").sum()) if len(sub) else 0,
                "proxy_confirmed_count": int((sub["classification_confidence"] == "PROXY_CONFIRMED").sum()) if len(sub) else 0,
                "unresolved_count": int((sub["classification_confidence"] == "UNRESOLVED").sum()) if len(sub) else 0,
                "outside_coverage_count": int((sub["classification_confidence"] == "OUTSIDE_COVERAGE").sum()) if len(sub) else 0,
            }
        )
    return rows


def fixed_iv_summary(outcomes: list[dict[str, Any]], source_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(outcomes)
    df = df[df["outcome_coverage_status"] == "complete"].copy()
    if df.empty:
        return []
    histories = ref.load_ohlcv_subset(baseline_input_root(), set(df["ticker"]))
    modeled: list[dict[str, Any]] = []
    coverage: dict[str, int] = {klass: 0 for klass in FINAL_CLASSES}
    for _, row in df.iterrows():
        klass = row["classification"]
        coverage[klass] += 1
        source = source_by_id[row["raw_s_event_id"]]
        signal = {
            "signal_id": row["raw_s_event_id"],
            "underlying_symbol": row["ticker"],
            "signal_decision_date": row["signal_decision_date"],
            "entry_session": row["entry_session"],
            "entry_price": source.get("entry_price", ""),
            "theme": source.get("theme", ""),
            "breakout_day_low": source.get("breakout_day_low", ""),
            "reached_plus_5pct_within_10_sessions": str(row["plus_5pct_within_10_sessions"]).lower(),
        }
        hist = histories.get(row["ticker"])
        result = {"status": "excluded", "excluded_reason": "missing_ticker_ohlcv"} if hist is None else ref.model_trade(signal, hist)
        if result["status"] == "eligible":
            ret = 125.0 if str(result.get("first_hit_125_date", "")).strip() else float(result["terminal_net_return_pct"])
            modeled.append({"classification": klass, **result, "fixed_iv_reference_return_pct": ret})
    rows = []
    for klass in FINAL_CLASSES:
        vals = [float(r["fixed_iv_reference_return_pct"]) for r in modeled if r["classification"] == klass]
        hits = [r for r in modeled if r["classification"] == klass and str(r.get("first_hit_125_date", "")).strip()]
        rows.append(
            {
                "classification": klass,
                "fixed_iv_eligible_count": len(vals),
                "coverage": len(vals) / coverage[klass] if coverage[klass] else "",
                "TP125_hit_rate": len(hits) / len(vals) if vals else "",
                "mean_return": pd.Series(vals).mean() if vals else "",
                "median_return": pd.Series(vals).median() if vals else "",
                "PF": profit_factor(vals) if vals else "",
                "max_loss": min(vals) if vals else "",
                "synthetic_fixed_iv_reference_only": True,
                "not_historical_option_fill_reconstruction": True,
                "not_final_live_exit_policy": True,
            }
        )
    return rows


def deterministic_representatives(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(outcomes)
    rows = []
    for klass in FINAL_CLASSES:
        sub = df[df["classification"] == klass].copy()
        if sub.empty:
            continue
        sub["score_num"] = pd.to_numeric(sub["production_adjusted_score"], errors="coerce")
        choices = [
            ("earliest_date", sub.sort_values(["entry_session", "raw_s_event_id"]).iloc[0]),
            ("latest_date", sub.sort_values(["entry_session", "raw_s_event_id"]).iloc[-1]),
        ]
        scored = sub.dropna(subset=["score_num"]).sort_values(["score_num", "entry_session", "raw_s_event_id"])
        if not scored.empty:
            choices.append(("median_score_row", scored.iloc[len(scored) // 2]))
        seen: set[str] = set()
        for sample_type, row in choices:
            sid = row["raw_s_event_id"]
            if sid in seen:
                continue
            seen.add(sid)
            rows.append(
                {
                    "sample_type": sample_type,
                    "classification": klass,
                    "raw_s_event_id": sid,
                    "ticker": row["ticker"],
                    "signal_decision_date": row["signal_decision_date"],
                    "entry_session": row["entry_session"],
                    "production_adjusted_score": row["production_adjusted_score"],
                    "classification_reason_code": row["classification_reason_code"],
                    "selection_not_return_based": True,
                }
            )
    return rows


def write_trace_and_rulebook(native: dict[str, Any]) -> None:
    trace = [
        "# Source Trace And Filter Map",
        "",
        "| Step | Source | Finding | Status |",
        "|---|---|---|---|",
        "| raw scanner breakout | `scanner/breakout.py::detect_breakout` | Computes pivot, breakout_today, near_breakout, failed_breakout. | present |",
        "| S rank assignment | `scanner/scoring.py::is_s_rank_candidate` | S requires trend, RS, breakout RS, accumulation, VCP, near_breakout, and distance_to_pivot. | present |",
        "| production notification selection | `scripts/production_scanner_entry_pullback_mode.py` | Visible candidates with `alert_rank == S` are formatted as S breakout momentum/wake candidates. | present |",
        "| anti-extended/base/cooldown filter | formal baseline fields and traced code | No persisted original_breakout_date, breakout_id, base_id, extended flag, reset/rebase flag, or cooldown field in formal S stream. | not reproducible from saved historical S rows |",
        "",
        "## Direct Answers",
        "",
        f"- Native logic status: `{native['status']}`.",
        "- A. Current production S has breakout/near-breakout requirements, but this audit did not find a native anti-extended base/cooldown condition in the formal historical S rows.",
        "- B. It is not active/reproducible in the historical formal S run as a saved field.",
        "- C. S rank is determined by `scanner/scoring.py`; notification formatting/selection is in `scripts/production_scanner_entry_pullback_mode.py`; no exact base/cooldown branch is carried into `morita_bot_baseline_panel.csv`.",
        "- D. Issue classification: not reproducible from saved data, and no active formal-stream base/cooldown field was found.",
    ]
    (OUT / "source_trace_and_filter_map.md").write_text("\n".join(trace) + "\n", encoding="utf-8")
    rulebook = [
        "# Classification Rulebook",
        "",
        f"Rule version: `{CLASS_RULE_VERSION}`",
        "",
        "Native-first rule: use persisted native base/breakout/extended/reset fields if present. In this formal S stream, those fields are not available.",
        "",
        "Frozen proxy fallback:",
        "",
        "- First same-ticker raw S in the formal current-S stream -> `CURRENT_S_INITIAL_BREAKOUT`, `PROXY_INITIAL_BREAKOUT`, `PROXY_CONFIRMED`.",
        "- Same-ticker raw S with most recent prior raw S within 20 eligible sessions -> `CURRENT_S_EXTENDED_FOMO`, `PROXY_EXTENDED_FOMO`, `PROXY_CONFIRMED`.",
        "- Same-ticker raw S after a gap greater than 20 eligible sessions -> `CURRENT_S_UNRESOLVED`; elapsed time alone is not native new-base proof.",
        "- Missing signal/entry coverage -> `OUTSIDE_SOURCE_COVERAGE`.",
        "",
        "Forbidden: no future returns, no later raw-S event, no manual chart labeling, no outcome-driven threshold selection, no PF targeting.",
    ]
    (OUT / "classification_rulebook.md").write_text("\n".join(rulebook) + "\n", encoding="utf-8")


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def write_summary_and_bundle(receipt: dict[str, Any], class_rows: list[dict[str, Any]], native_plus: list[dict[str, Any]], risk_rows: list[dict[str, Any]], fixed_rows: list[dict[str, Any]]) -> None:
    full_perf = [r for r in native_plus if r["subperiod"] == "full_range" and r["notification_count"]]
    full_risk = [r for r in risk_rows if r["evidence_universe"] == "native_plus_proxy" and r["subperiod"] == "full_range" and r["eligible_observation_count"]]
    lines = [
        "# Morita Current-S Notification Quality Audit v0.1",
        "",
        "Research-only audit of the current historical formal S notification stream. No live notification/order behavior, scanner rank, portfolio DD, or sizing changes were made.",
        "",
        "## Receipt",
        "",
        "```json",
        json.dumps(receipt, indent=2, sort_keys=True),
        "```",
        "",
        "## Classification Counts",
        "",
        md_table(class_rows, ["classification", "count", "unique_tickers", "native_confirmed_count", "proxy_confirmed_count", "unresolved_count"]),
        "",
        "## Full Range Underlying Performance",
        "",
        md_table(full_perf, ["classification", "eligible_observation_count", "unique_tickers", "mean_10d_return", "median_10d_return", "mean_20d_return", "median_20d_return", "plus_5pct_within_10_rate", "plus_10pct_within_20_rate", "sample_label"]),
        "",
        "## Full Range Adverse Path Risk",
        "",
        md_table(full_risk, ["classification", "eligible_observation_count", "MAE_LOW_20_median", "MAE_LOW_20_p10", "MAE_LOW_20_p05", "CLOSE_DRAWDOWN_20_median", "share_MAE_LOW_20_le_minus10", "share_MAE_LOW_20_le_minus20"]),
        "",
        "## Fixed-IV Reference",
        "",
        md_table(fixed_rows, ["classification", "fixed_iv_eligible_count", "coverage", "TP125_hit_rate", "mean_return", "median_return", "PF", "max_loss", "synthetic_fixed_iv_reference_only", "not_final_live_exit_policy"]),
        "",
        "## Interpretation Boundaries",
        "",
        "- This measures outcomes after current S notifications, not a clean independent portfolio strategy.",
        "- Same-ticker notifications can be dependent and overlap.",
        "- CURRENT_S_EXTENDED_FOMO means the current stream admits extended setups under the frozen audit proxy; it is not a live FOMO strategy.",
        "- CURRENT_S_UNRESOLVED remains visible and is not forced into breakout or FOMO.",
        "- MAE and close drawdown are per-entry path risk, not portfolio drawdown.",
        "- No live S rule, notification behavior, order behavior, or sizing change is authorized.",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "audit_summary.md").write_text(text, encoding="utf-8")
    BUNDLE.write_text(text, encoding="utf-8")


def build_manifest() -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUTS:
        if name == "audit_content_manifest.json":
            continue
        path = OUT / name
        if path.exists():
            files.append({"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {
        "manifest_version": "morita_current_s_notification_quality_audit_v0_1",
        "created_at_utc": utc_now(),
        "required_files": REQUIRED_OUTPUTS,
        "files": files,
        "content_set_hash": hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    write_json(OUT / "audit_content_manifest.json", manifest)
    return manifest


def verify_manifest() -> dict[str, Any]:
    missing = [name for name in REQUIRED_OUTPUTS if not (OUT / name).exists()]
    actual = sorted(path.name for path in OUT.iterdir() if path.is_file()) if OUT.exists() else []
    extra = [name for name in actual if name not in REQUIRED_OUTPUTS]
    changed = []
    manifest_path = OUT / "audit_content_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("files", []):
            path = OUT / item["path"]
            if not path.exists() or sha256_file(path) != item["sha256"]:
                changed.append(item["path"])
    return {"verified": not missing and not extra and not changed, "missing": missing, "extra": extra, "changed": changed}


def assert_no_forbidden_outputs() -> None:
    for path in OUT.glob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN_OUTPUT_TOKENS:
            if token in text:
                raise AssertionError(f"forbidden_output_token:{token}:{path.name}")


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    source_rows = source_verification_rows()
    missing = [r["component"] for r in source_rows if not r["exists"]]
    if missing:
        write_csv(OUT / "source_verification.csv", source_rows)
        raise FileNotFoundError(f"missing_required_sources:{missing}")
    sessions = load_sessions()
    session_pos = {date: idx for idx, date in enumerate(sessions)}
    s = load_formal_s()
    audit_rows, native = classify_notifications(s, session_pos)
    outcome_rows = add_outcomes(audit_rows, s)
    class_rows = classification_summary(audit_rows)
    periods = ["2024", "2025", "2026_H1", "full_range"]
    native_only = performance_summary(outcome_rows, "native_only", periods)
    native_plus = performance_summary(outcome_rows, "native_plus_proxy", periods)
    stability = [r for r in native_plus if r["subperiod"] != "full_range"]
    risk_rows = class_path_risk_summary(native_only + native_plus)
    source_by_id = {str(row["signal_id"]): row.to_dict() for _, row in s.iterrows()}
    fixed_rows = fixed_iv_summary(outcome_rows, source_by_id)
    reps = deterministic_representatives(outcome_rows)
    write_trace_and_rulebook(native)
    receipt = {
        "status": "completed",
        "created_at_utc": utc_now(),
        "research_only": True,
        "raw_current_s_stream_immutable": True,
        "no_new_data_downloaded": True,
        "no_web_or_provider_api": True,
        "no_broker_or_webull_access": True,
        "no_live_notification_or_order_change": True,
        "no_parameter_sweep": True,
        "no_pf_targeting": True,
        "no_future_data_in_classification": True,
        "no_portfolio_simulation": True,
        "no_portfolio_dd_study": True,
        "source_run_id": baseline_receipt().get("run_id", ""),
        "source_commit": baseline_receipt().get("repository_commit_sha", ""),
        "source_date_min": str(s["signal_date"].min()),
        "source_date_max": str(s["signal_date"].max()),
        "raw_s_event_count": int(len(s)),
        "native_current_s_logic_status": native["status"],
        "initial_breakout_count": int(sum(r["classification"] == "CURRENT_S_INITIAL_BREAKOUT" for r in audit_rows)),
        "rebreakout_count": int(sum(r["classification"] == "CURRENT_S_REBREAKOUT" for r in audit_rows)),
        "extended_fomo_count": int(sum(r["classification"] == "CURRENT_S_EXTENDED_FOMO" for r in audit_rows)),
        "unresolved_count": int(sum(r["classification"] == "CURRENT_S_UNRESOLVED" for r in audit_rows)),
        "outside_source_coverage_count": int(sum(r["classification"] == "OUTSIDE_SOURCE_COVERAGE" for r in audit_rows)),
        "native_confirmed_count": int(sum(r["classification_confidence"] == "NATIVE_CONFIRMED" for r in audit_rows)),
        "proxy_confirmed_count": int(sum(r["classification_confidence"] == "PROXY_CONFIRMED" for r in audit_rows)),
        "fixed_iv_class_comparison_status": "complete",
    }
    write_csv(OUT / "source_verification.csv", source_rows)
    write_csv(OUT / "current_s_notification_quality_audit.csv", outcome_rows)
    write_csv(OUT / "classification_summary.csv", class_rows)
    write_csv(OUT / "native_only_performance_summary.csv", native_only)
    write_csv(OUT / "native_plus_proxy_performance_summary.csv", native_plus)
    write_csv(OUT / "class_subperiod_stability.csv", stability)
    write_csv(OUT / "class_path_risk_summary.csv", risk_rows)
    write_csv(OUT / "class_fixed_iv_reference_summary.csv", fixed_rows)
    write_csv(OUT / "representative_deterministic_rows.csv", reps)
    write_json(OUT / "audit_receipt.json", receipt)
    write_summary_and_bundle(receipt, class_rows, native_plus, risk_rows, fixed_rows)
    build_manifest()
    assert_no_forbidden_outputs()
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.run and not args.verify:
        parser.error("one of --run or --verify is required")
    if args.run:
        print(json.dumps(run(), indent=2, sort_keys=True))
    if args.verify:
        result = verify_manifest()
        print(result)
        return 0 if result["verified"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
