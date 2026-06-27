#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import uuid
from datetime import time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import market_bomb_phase3_2_cta_vol_proxy as p32
except Exception:  # pragma: no cover
    p32 = None


ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
JST = ZoneInfo("Asia/Tokyo")
PARSER_VERSION = "morita_history_reconstruction_parser_v1"
RECONSTRUCTION_VERSION = "market_bomb_phase3_2b_morita_history_reconstruction_v1_20260627"
MAX_FEATURE_AGE_HOURS = 96

SIGNAL_COLUMNS = [
    "signal_event_id", "setup_id", "source_id", "source_hash", "source_row_number", "source_record_key",
    "ticker", "event_timestamp_utc", "event_timestamp_original", "event_timezone_original",
    "event_timestamp_quality", "event_effective_at_utc", "event_session_context",
    "original_rank", "strategy_bucket", "setup_type", "scanner_name", "scanner_version",
    "signal_reason_raw", "signal_reason_normalized", "breakout_reference", "pullback_reference",
    "relative_strength", "volume_multiple", "source_evidence_level", "reconstruction_status",
    "reconstruction_notes", "data_type", "analysis_mode", "is_reconstructed", "raw_payload_reference",
]

DECISION_COLUMNS = [
    "decision_id", "signal_event_id", "setup_id", "source_id", "source_hash", "source_row_number",
    "ticker", "decision_timestamp_utc", "decision_timestamp_original", "decision_timezone_original",
    "decision_timestamp_quality", "decision_session_context", "decision_action", "decision_status",
    "decision_reason_raw", "decision_reason_normalized", "intended_instrument_type",
    "intended_option_expiration", "intended_option_strike", "intended_option_delta", "intended_option_dte",
    "intended_position_size_pct", "source_evidence_level", "reconstruction_status", "reconstruction_notes",
    "analysis_mode", "is_reconstructed", "raw_payload_reference",
]

FILL_COLUMNS = [
    "trade_id", "decision_id", "signal_event_id", "setup_id", "broker", "account_type", "ticker",
    "instrument_type", "contract_symbol", "option_expiration", "option_strike", "option_type",
    "multiplier", "fill_timestamp_utc", "fill_timestamp_original", "fill_timezone_original",
    "fill_timestamp_quality", "side", "quantity", "fill_price", "fees", "currency", "source_id",
    "source_hash", "source_row_number", "source_evidence_level", "reconstruction_status",
    "reconstruction_notes", "data_type", "analysis_mode", "is_reconstructed", "raw_payload_reference",
]

EXIT_COLUMNS = [
    "trade_exit_id", "trade_id", "exit_timestamp_utc", "exit_timestamp_original", "exit_timezone_original",
    "exit_timestamp_quality", "exit_reason", "exit_price", "exit_quantity", "fees", "realized_pnl_currency",
    "realized_pnl_pct", "source_id", "source_hash", "source_row_number", "source_evidence_level",
    "reconstruction_status", "reconstruction_notes", "data_type", "analysis_mode", "is_reconstructed",
    "raw_payload_reference",
]


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value) or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def deterministic_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, raw).hex[:20]}"


def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass


def markdown_table(df: pd.DataFrame, max_rows: int = 60) -> str:
    if df.empty:
        return "_No rows._"
    clean = df.head(max_rows).fillna("").astype(str)
    cols = list(clean.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in clean.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("|", "\\|").replace("\n", " ") for c in cols) + " |")
    if len(df) > max_rows:
        lines.append(f"\n_Only first {max_rows} of {len(df)} rows shown._")
    return "\n".join(lines)


def parse_timestamp(value: Any) -> tuple[pd.Timestamp | None, str, str]:
    if value in [None, ""] or (isinstance(value, float) and pd.isna(value)):
        return None, "unknown", ""
    raw = str(value).strip()
    ts = pd.to_datetime(raw, utc=False, errors="coerce")
    if pd.isna(ts):
        return None, "unknown", ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) or re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", raw):
        local = pd.Timestamp(ts).tz_localize(ET).replace(hour=16, minute=0, second=0)
        return local.tz_convert(UTC), "date_only", "America/New_York"
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is not None:
        return stamp.tz_convert(UTC), "exact_with_timezone", str(stamp.tzinfo)
    return stamp.tz_localize(ET).tz_convert(UTC), "exact_local_timezone_inferred", "America/New_York"


def session_context(ts: pd.Timestamp | None, quality: str = "") -> str:
    if quality == "date_only":
        return "date_only"
    if ts is None:
        return "unknown"
    t = ts.tz_convert(ET).time()
    if time(4, 0) <= t < time(9, 30):
        return "pre_open"
    if time(9, 30) <= t < time(16, 0):
        return "regular_hours"
    if time(16, 0) <= t < time(20, 0):
        return "after_close"
    return "overnight"


def next_regular_open(ts: pd.Timestamp | None) -> pd.Timestamp | None:
    if ts is None:
        return None
    et = ts.tz_convert(ET)
    candidate = et.replace(hour=9, minute=30, second=0, microsecond=0)
    if et.time() >= time(9, 30):
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.tz_convert(UTC)


def strategy_bucket(rank: Any) -> str:
    rank = str(rank or "").upper().strip()
    if rank == "S":
        return "S_breakout_momentum"
    if rank in {"A", "B"}:
        return "AB_institutional_pullback"
    return "unclassified"


def analysis_mode(evidence: str, timestamp_quality: str, unit: str) -> str:
    if evidence == "raw_broker_execution" and timestamp_quality in {"exact_utc", "exact_with_timezone", "exact_local_timezone_inferred"}:
        return "strict_live_replay"
    if unit == "decision" and timestamp_quality in {"exact_utc", "exact_with_timezone", "exact_local_timezone_inferred"} and evidence in {"raw_action_artifact", "raw_scanner_output"}:
        return "strict_live_replay"
    if evidence in {"raw_scanner_output", "raw_notification_export", "raw_action_artifact"}:
        return "historical_reconstructed"
    if evidence == "structured_manual_entry":
        return "mixed_exploratory"
    return "unavailable"


def source_type_for(path: Path) -> str:
    p = str(path).lower().replace("\\", "/")
    name = path.name.lower()
    if "raw_sources" in p and "manual" in name:
        return "manual_reconstruction_csv"
    if "broker" in p or "execution" in name or "fill" in name:
        return "broker_execution_csv"
    if "order" in name:
        return "broker_order_csv"
    if "notification" in p or "pushover" in p or "discord" in p:
        return "notification_export_csv"
    if "notified_candidates" in p:
        return "notified_candidates_csv"
    if "daily_scan" in p or "scan_log" in p:
        return "daily_scan_log_csv"
    if "scanner_alert" in p or "scanner" in p or "candidate" in name:
        return "scanner_alert_csv"
    return "unknown"


def source_priority(source_type: str) -> int:
    return {
        "broker_execution_csv": 1,
        "broker_order_csv": 1,
        "scanner_alert_csv": 1,
        "notified_candidates_csv": 1,
        "daily_scan_log_csv": 1,
        "notification_export_csv": 2,
        "manual_reconstruction_csv": 2,
        "scanner_markdown_report": 2,
        "unknown": 3,
    }.get(source_type, 3)


def evidence_level(source_type: str) -> str:
    if source_type in {"broker_execution_csv", "broker_order_csv"}:
        return "raw_broker_execution"
    if source_type in {"scanner_alert_csv", "notified_candidates_csv", "daily_scan_log_csv"}:
        return "raw_scanner_output"
    if source_type == "notification_export_csv":
        return "raw_notification_export"
    if source_type == "manual_reconstruction_csv":
        return "structured_manual_entry"
    return "unknown"


def candidate_source_paths(root: Path) -> list[Path]:
    globs = [
        "scanner_alerts/**/*.csv",
        "scanner/**/*.csv",
        "notified_candidates/**/*.csv",
        "daily_scan_log/**/*.csv",
        "morita_signal_history/**/*.csv",
        "morita_decision_history/**/*.csv",
        "morita_trade_log/**/*.csv",
        "market_bomb_reconstruction/raw_sources/**/*.csv",
    ]
    paths: list[Path] = []
    for pattern in globs:
        paths.extend(root.glob(pattern))
    return sorted({p for p in paths if p.is_file() and "market_bomb_reconstruction/normalized" not in str(p).replace("\\", "/")})


def first_present(row: pd.Series, names: list[str], default: Any = "") -> Any:
    for name in names:
        if name in row and pd.notna(row[name]) and str(row[name]) != "":
            return row[name]
    return default


def build_source_inventory(root: Path, include_repo_sources: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    paths = candidate_source_paths(root) if include_repo_sources else []
    rows = []
    manifest = []
    for i, path in enumerate(paths, start=1):
        rel = str(path.relative_to(root)).replace("\\", "/")
        stype = source_type_for(path)
        sha = hash_file(path)
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame()
        source_id = deterministic_id("src", rel, sha)
        rows.append(
            {
                "source_id": source_id,
                "source_path": rel,
                "source_filename": path.name,
                "source_type": stype,
                "source_priority": source_priority(stype),
                "source_hash": sha,
                "file_size_bytes": path.stat().st_size,
                "source_created_at_utc": pd.Timestamp(path.stat().st_ctime, unit="s", tz=UTC).isoformat(),
                "source_modified_at_utc": pd.Timestamp(path.stat().st_mtime, unit="s", tz=UTC).isoformat(),
                "discovered_on_main": True,
                "source_access_method": "repository_checkout",
                "parser_name": parser_for_type(stype),
                "parser_version": PARSER_VERSION,
                "row_count_raw": len(df),
                "row_count_parsed": 0,
                "timezone_found": "",
                "timestamp_quality": "unknown",
                "rank_availability": any(c in df.columns for c in ["alert_rank", "rank", "original_rank", "production_rank"]),
                "ticker_availability": any(c in df.columns for c in ["ticker", "symbol", "underlying"]),
                "trade_data_availability": any(c in df.columns for c in ["fill_price", "exit_price", "contract_symbol"]),
                "recommended_use": recommended_use(stype),
                "notes": "" if not df.empty else "empty_or_unreadable",
            }
        )
        manifest.append({"source_id": source_id, "source_path": rel, "source_hash": sha, "source_type": stype, "row_count_raw": len(df)})
    return pd.DataFrame(rows), pd.DataFrame(manifest)


def parser_for_type(source_type: str) -> str:
    if source_type in {"broker_execution_csv", "broker_order_csv"}:
        return "broker_execution_csv_parser"
    if source_type in {"scanner_alert_csv", "notified_candidates_csv", "daily_scan_log_csv"}:
        return "scanner_signal_csv_parser"
    if source_type == "manual_reconstruction_csv":
        return "manual_reconstruction_csv_parser"
    if source_type == "notification_export_csv":
        return "notification_export_csv_parser"
    return "generic_csv_parser"


def recommended_use(source_type: str) -> str:
    if source_type in {"broker_execution_csv", "broker_order_csv"}:
        return "trade_fill_exit_reconstruction"
    if source_type in {"scanner_alert_csv", "notified_candidates_csv", "daily_scan_log_csv"}:
        return "signal_reconstruction"
    if source_type == "manual_reconstruction_csv":
        return "manual_research_reconstruction_only"
    return "audit_only"


def normalize_signal_row(row: pd.Series, source: pd.Series, row_num: int) -> dict[str, Any] | None:
    ticker = str(first_present(row, ["ticker", "symbol", "underlying"], "")).upper().strip()
    if not ticker:
        return None
    raw_rank = str(first_present(row, ["alert_rank", "rank", "original_rank", "production_rank"], "")).upper().strip()
    ts_raw = first_present(row, ["event_timestamp_utc", "timestamp_utc", "alert_timestamp_utc", "scan_time_utc", "date", "breakout_date"], "")
    ts, tq, tz = parse_timestamp(ts_raw)
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    setup_type = str(first_present(row, ["setup_type", "entry_rule"], "unknown")).lower()
    if setup_type not in {"breakout", "first_pullback", "institutional_pullback"}:
        setup_type = "unknown"
    sid = deterministic_id("sig", source["source_hash"], row_num, ticker, ts.isoformat())
    setup_id = deterministic_id("setup", source["source_hash"], ticker, raw_rank, setup_type, ts.date())
    return {
        "signal_event_id": sid,
        "setup_id": setup_id,
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "source_record_key": f"{source['source_id']}:{row_num}",
        "ticker": ticker,
        "event_timestamp_utc": ts.isoformat(),
        "event_timestamp_original": ts_raw,
        "event_timezone_original": tz,
        "event_timestamp_quality": tq,
        "event_effective_at_utc": ts.isoformat(),
        "event_session_context": session_context(ts, tq),
        "original_rank": raw_rank,
        "strategy_bucket": strategy_bucket(raw_rank),
        "setup_type": setup_type,
        "scanner_name": str(first_present(row, ["scanner_name"], "morita_scanner")),
        "scanner_version": str(first_present(row, ["scanner_version"], "")),
        "signal_reason_raw": str(first_present(row, ["signal_reason", "reason", "exclusion_reason"], "")),
        "signal_reason_normalized": "",
        "breakout_reference": first_present(row, ["prior_20d_high", "breakout_price"], ""),
        "pullback_reference": first_present(row, ["pullback_reference", "pullback_price"], ""),
        "relative_strength": first_present(row, ["RS", "rs", "relative_strength"], ""),
        "volume_multiple": first_present(row, ["volume_multiple"], ""),
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "" if raw_rank in {"S", "A", "B"} else "rank_missing_or_unclassified",
        "data_type": "reconstructed",
        "analysis_mode": analysis_mode(evidence, tq, "signal"),
        "is_reconstructed": True,
        "raw_payload_reference": source["source_path"],
    }


def normalize_decision_row(row: pd.Series, source: pd.Series, row_num: int, signal_id: str = "", setup_id: str = "") -> dict[str, Any] | None:
    ticker = str(first_present(row, ["ticker", "symbol", "underlying"], "")).upper().strip()
    action = str(first_present(row, ["decision_action", "action"], "")).lower().strip()
    if action not in {"enter", "skip", "watch", "exit_plan_only", "unknown"}:
        if action:
            action = "unknown"
    if not ticker or not action:
        return None
    ts_raw = first_present(row, ["decision_timestamp_utc", "timestamp_utc", "decision_time", "date"], "")
    ts, tq, tz = parse_timestamp(ts_raw)
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    did = deterministic_id("dec", source["source_hash"], row_num, ticker, ts.isoformat(), action)
    return {
        "decision_id": did,
        "signal_event_id": signal_id,
        "setup_id": setup_id,
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "ticker": ticker,
        "decision_timestamp_utc": ts.isoformat(),
        "decision_timestamp_original": ts_raw,
        "decision_timezone_original": tz,
        "decision_timestamp_quality": tq,
        "decision_session_context": session_context(ts, tq),
        "decision_action": action,
        "decision_status": str(first_present(row, ["decision_status", "status"], "")),
        "decision_reason_raw": str(first_present(row, ["decision_reason", "reason"], "")),
        "decision_reason_normalized": "",
        "intended_instrument_type": first_present(row, ["intended_instrument_type", "instrument_type"], ""),
        "intended_option_expiration": first_present(row, ["intended_option_expiration", "option_expiration"], ""),
        "intended_option_strike": first_present(row, ["intended_option_strike", "option_strike"], ""),
        "intended_option_delta": first_present(row, ["intended_option_delta", "option_delta"], ""),
        "intended_option_dte": first_present(row, ["intended_option_dte", "option_dte"], ""),
        "intended_position_size_pct": first_present(row, ["intended_position_size_pct", "position_size_pct"], ""),
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "",
        "analysis_mode": analysis_mode(evidence, tq, "decision"),
        "is_reconstructed": True,
        "raw_payload_reference": source["source_path"],
    }


def normalize_fill_row(row: pd.Series, source: pd.Series, row_num: int) -> dict[str, Any] | None:
    ticker = str(first_present(row, ["ticker", "symbol", "underlying"], "")).upper().strip()
    price = safe_float(first_present(row, ["fill_price", "price"], math.nan))
    qty = safe_float(first_present(row, ["quantity", "qty"], math.nan))
    side = str(first_present(row, ["side", "action"], "")).lower()
    if not ticker or pd.isna(price) or pd.isna(qty):
        return None
    ts_raw = first_present(row, ["fill_timestamp_utc", "timestamp_utc", "fill_time", "date"], "")
    ts, tq, tz = parse_timestamp(ts_raw)
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    contract = str(first_present(row, ["contract_symbol"], ""))
    trade_id = deterministic_id("trd", source["source_hash"], row_num, ticker, contract, ts.isoformat(), side, qty, price)
    return {
        "trade_id": trade_id,
        "decision_id": str(first_present(row, ["decision_id"], "")),
        "signal_event_id": str(first_present(row, ["signal_event_id"], "")),
        "setup_id": str(first_present(row, ["setup_id"], "")),
        "broker": first_present(row, ["broker"], ""),
        "account_type": first_present(row, ["account_type"], ""),
        "ticker": ticker,
        "instrument_type": first_present(row, ["instrument_type"], "option" if contract else ""),
        "contract_symbol": contract,
        "option_expiration": first_present(row, ["option_expiration"], ""),
        "option_strike": first_present(row, ["option_strike"], ""),
        "option_type": first_present(row, ["option_type"], ""),
        "multiplier": first_present(row, ["multiplier"], 100 if contract else ""),
        "fill_timestamp_utc": ts.isoformat(),
        "fill_timestamp_original": ts_raw,
        "fill_timezone_original": tz,
        "fill_timestamp_quality": tq,
        "side": side,
        "quantity": qty,
        "fill_price": price,
        "fees": first_present(row, ["fees"], ""),
        "currency": first_present(row, ["currency"], "USD"),
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "",
        "data_type": "observed" if evidence == "raw_broker_execution" else "reconstructed",
        "analysis_mode": analysis_mode(evidence, tq, "fill"),
        "is_reconstructed": evidence != "raw_broker_execution",
        "raw_payload_reference": source["source_path"],
    }


def normalize_exit_row(row: pd.Series, source: pd.Series, row_num: int) -> dict[str, Any] | None:
    trade_id = str(first_present(row, ["trade_id"], ""))
    price = safe_float(first_present(row, ["exit_price"], math.nan))
    if not trade_id or pd.isna(price):
        return None
    ts_raw = first_present(row, ["exit_timestamp_utc", "timestamp_utc", "exit_time", "date"], "")
    ts, tq, tz = parse_timestamp(ts_raw)
    if ts is None:
        return None
    evidence = evidence_level(str(source["source_type"]))
    return {
        "trade_exit_id": deterministic_id("exit", source["source_hash"], row_num, trade_id, ts.isoformat(), price),
        "trade_id": trade_id,
        "exit_timestamp_utc": ts.isoformat(),
        "exit_timestamp_original": ts_raw,
        "exit_timezone_original": tz,
        "exit_timestamp_quality": tq,
        "exit_reason": first_present(row, ["exit_reason"], ""),
        "exit_price": price,
        "exit_quantity": first_present(row, ["exit_quantity", "quantity"], ""),
        "fees": first_present(row, ["fees"], ""),
        "realized_pnl_currency": first_present(row, ["realized_pnl_currency"], ""),
        "realized_pnl_pct": first_present(row, ["realized_pnl_pct", "pnl_pct"], ""),
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "source_row_number": row_num,
        "source_evidence_level": evidence,
        "reconstruction_status": "parsed",
        "reconstruction_notes": "",
        "data_type": "observed" if evidence == "raw_broker_execution" else "reconstructed",
        "analysis_mode": analysis_mode(evidence, tq, "exit"),
        "is_reconstructed": evidence != "raw_broker_execution",
        "raw_payload_reference": source["source_path"],
    }


def parse_sources(root: Path, inventory: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signals: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    for _, source in inventory.iterrows():
        path = root / str(source["source_path"])
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        for idx, row in df.iterrows():
            row_num = int(idx) + 2
            sig = normalize_signal_row(row, source, row_num)
            if sig is not None:
                signals.append(sig)
            dec = normalize_decision_row(row, source, row_num, sig["signal_event_id"] if sig else "", sig["setup_id"] if sig else "")
            if dec is not None:
                decisions.append(dec)
            fill = normalize_fill_row(row, source, row_num)
            if fill is not None:
                fills.append(fill)
            ex = normalize_exit_row(row, source, row_num)
            if ex is not None:
                exits.append(ex)
    return (
        pd.DataFrame(signals, columns=SIGNAL_COLUMNS),
        pd.DataFrame(decisions, columns=DECISION_COLUMNS),
        pd.DataFrame(fills, columns=FILL_COLUMNS),
        pd.DataFrame(exits, columns=EXIT_COLUMNS),
    )


def duplicate_audit(signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if signals.empty:
        return pd.DataFrame(), pd.DataFrame(), signals
    df = signals.copy()
    df["event_date"] = pd.to_datetime(df["event_timestamp_utc"], utc=True, errors="coerce").dt.date.astype(str)
    keys = ["ticker", "event_date", "original_rank", "scanner_name", "setup_type", "event_session_context"]
    df["duplicate_key"] = df[keys].astype(str).agg("|".join, axis=1)
    dupes = df[df.duplicated("duplicate_key", keep=False)].copy()
    canonical = df.sort_values(["duplicate_key", "source_evidence_level", "source_id"]).drop_duplicates("duplicate_key", keep="first")
    linkage_rows = []
    if not dupes.empty:
        for key, group in dupes.groupby("duplicate_key"):
            winner = canonical[canonical["duplicate_key"].eq(key)].iloc[0]
            for _, row in group.iterrows():
                if row["signal_event_id"] == winner["signal_event_id"]:
                    continue
                linkage_rows.append(
                    {
                        "canonical_signal_event_id": winner["signal_event_id"],
                        "duplicate_signal_event_id": row["signal_event_id"],
                        "duplicate_type": "probable_duplicate",
                        "duplicate_key": key,
                        "duplicate_source_id": row["source_id"],
                        "canonical_source_id": winner["source_id"],
                    }
                )
    canonical = canonical.drop(columns=["event_date", "duplicate_key"], errors="ignore")
    dupes = dupes.drop(columns=["event_date"], errors="ignore")
    return dupes, pd.DataFrame(linkage_rows), canonical


def load_price_history(root: Path) -> dict[str, pd.DataFrame]:
    if p32 is None:
        return {}
    return p32.load_price_history(root, refresh_price_history=False)


def build_outcome_panel(root: Path, signals: pd.DataFrame, decisions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame, build_underlying: bool) -> pd.DataFrame:
    rows = []
    prices = load_price_history(root) if build_underlying else {}
    for _, sig in signals.iterrows():
        event_ts = parse_timestamp(sig["event_timestamp_utc"])[0]
        entry_ts = next_regular_open(event_ts) if sig["event_session_context"] in {"after_close", "overnight", "date_only"} else event_ts
        method = "next_regular_open_proxy" if sig["event_session_context"] in {"after_close", "overnight"} else "same_day_close_proxy" if sig["event_session_context"] == "date_only" else "unavailable"
        row = {
            "analysis_unit": "signal_event",
            "signal_event_id": sig["signal_event_id"],
            "decision_id": "",
            "trade_id": "",
            "ticker": sig["ticker"],
            "strategy_bucket": sig["strategy_bucket"],
            "original_rank": sig["original_rank"],
            "setup_type": sig["setup_type"],
            "event_timestamp_utc": sig["event_timestamp_utc"],
            "entry_timestamp_utc": entry_ts.isoformat() if entry_ts is not None else "",
            "entry_price_method": method,
            "analysis_mode": sig["analysis_mode"],
            "observed_option_pnl_pct": np.nan,
            "modelled_option_pnl_pct": np.nan,
            "observed_option_pnl_available": False,
            "modelled_option_pnl_available": False,
            "underlying_entry_timestamp_utc": entry_ts.isoformat() if entry_ts is not None else "",
            "underlying_entry_price": np.nan,
            "outcome_price_source": "",
            "outcome_calculation_version": RECONSTRUCTION_VERSION,
        }
        rows.append(add_underlying_outcomes(row, prices))
    return pd.DataFrame(rows)


def add_underlying_outcomes(row: dict[str, Any], prices: dict[str, pd.DataFrame]) -> dict[str, Any]:
    for col in ["underlying_return_1d", "underlying_return_5d", "underlying_return_10d", "underlying_max_adverse_excursion", "underlying_max_favorable_excursion"]:
        row[col] = np.nan
    if not prices:
        return row
    ticker = row["ticker"] if row["ticker"] in prices and not prices[row["ticker"]].empty else "QQQ"
    df = prices.get(ticker, pd.DataFrame())
    ts = parse_timestamp(row.get("entry_timestamp_utc"))[0]
    if df.empty or ts is None:
        return row
    if "date" not in df.columns:
        return row
    work = df.copy()
    work["date_norm"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    date = ts.tz_convert(ET).tz_localize(None).normalize()
    future = work[work["date_norm"] >= date].head(11).reset_index(drop=True)
    if len(future) < 2:
        return row
    entry = safe_float(future.loc[0, "adjusted_close"])
    if pd.isna(entry) or entry <= 0:
        return row
    row["underlying_entry_price"] = entry
    row["outcome_price_source"] = f"price_history:{ticker}"
    returns = future["adjusted_close"] / entry - 1
    for horizon in [1, 5, 10]:
        row[f"underlying_return_{horizon}d"] = returns.iloc[horizon] if len(returns) > horizon else np.nan
    row["underlying_max_adverse_excursion"] = returns.min()
    row["underlying_max_favorable_excursion"] = returns.max()
    return row


def latest_feature(df: pd.DataFrame, asset: str, ts: pd.Timestamp, target_vol: float | None = None) -> tuple[pd.Series | None, str, str]:
    if df.empty:
        return None, "failed", "feature_history_missing"
    work = df[df["asset"].astype(str).eq(asset)].copy()
    if target_vol is not None and "target_vol" in work.columns:
        work = work[np.isclose(pd.to_numeric(work["target_vol"], errors="coerce"), target_vol)]
    if work.empty:
        return None, "failed", f"feature_asset_missing:{asset}"
    work["effective_ts"] = pd.to_datetime(work["effective_available_at_utc"], utc=True, errors="coerce")
    work["asof_ts"] = pd.to_datetime(work["feature_as_of_timestamp_utc"], utc=True, errors="coerce")
    work = work[(work["effective_ts"] <= ts) & (work["asof_ts"] <= ts)]
    if work.empty:
        return None, "failed", "no_temporally_available_feature"
    work["feature_age_hours"] = (ts - work["effective_ts"]).dt.total_seconds() / 3600
    work = work[work["feature_age_hours"] <= MAX_FEATURE_AGE_HOURS]
    if work.empty:
        return None, "failed", "feature_too_old"
    return work.sort_values("effective_ts").iloc[-1], "joined", ""


def feature_asset(ticker: str) -> str:
    if p32 is not None:
        return p32.market_proxy_asset_for_ticker(ticker)
    return "SOXX" if ticker in {"NVDA", "AMD", "AVGO", "MU", "SMH"} else "QQQ"


def build_cta_vol_join(root: Path, panel: pd.DataFrame) -> pd.DataFrame:
    cta_path = root / "market_bomb_history" / "cta_proxy_history.csv"
    vol_path = root / "market_bomb_history" / "vol_control_proxy_history.csv"
    cta = pd.read_csv(cta_path) if cta_path.exists() else pd.DataFrame()
    vol = pd.read_csv(vol_path) if vol_path.exists() else pd.DataFrame()
    rows = []
    for _, event in panel.iterrows():
        ts = parse_timestamp(event.get("event_timestamp_utc"))[0]
        if ts is None:
            continue
        asset = feature_asset(event["ticker"])
        vol_asset = asset if asset in {"QQQ", "SPY", "SOXX"} else "QQQ"
        cta_row, cta_status, cta_reason = latest_feature(cta, asset, ts)
        vol_row, vol_status, vol_reason = latest_feature(vol, vol_asset, ts, target_vol=0.12)
        status = "joined" if cta_status == "joined" and vol_status == "joined" else "partial" if cta_status == "joined" or vol_status == "joined" else "failed"
        eff = cta_row.get("effective_available_at_utc") if cta_row is not None else ""
        eff_ts = parse_timestamp(eff)[0] if eff else None
        rows.append(
            {
                "analysis_unit": event["analysis_unit"],
                "signal_event_id": event["signal_event_id"],
                "decision_id": event.get("decision_id", ""),
                "trade_id": event.get("trade_id", ""),
                "ticker": event["ticker"],
                "strategy_bucket": event["strategy_bucket"],
                "original_rank": event["original_rank"],
                "event_timestamp_utc": event["event_timestamp_utc"],
                "feature_id": f"{asset}_{cta_row.get('feature_as_of_timestamp_utc') if cta_row is not None else ''}",
                "feature_as_of_timestamp_utc": cta_row.get("feature_as_of_timestamp_utc") if cta_row is not None else "",
                "effective_available_at_utc": eff,
                "feature_age_hours": round((ts - eff_ts).total_seconds() / 3600, 2) if eff_ts is not None else np.nan,
                "join_status": status,
                "join_failure_reason": "; ".join([x for x in [cta_reason, vol_reason] if x]),
                "cta_trend_state": cta_row.get("cta_trend_state") if cta_row is not None else "unavailable",
                "cta_deleveraging_proxy": cta_row.get("cta_deleveraging_proxy") if cta_row is not None else "",
                "vol_control_state": vol_row.get("vol_control_state") if vol_row is not None else "unavailable",
                "vol_control_pressure_proxy": vol_row.get("vol_control_pressure_proxy") if vol_row is not None else "unavailable",
                "analysis_mode": event["analysis_mode"],
            }
        )
    return pd.DataFrame(rows)


def write_templates(root: Path) -> None:
    tdir = root / "market_bomb_reconstruction" / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=["ticker", "event_timestamp_utc", "original_rank", "setup_type", "signal_reason_raw"]).to_csv(tdir / "manual_signal_events_template.csv", index=False)
    pd.DataFrame(columns=["ticker", "decision_timestamp_utc", "decision_action", "decision_reason_raw", "intended_option_delta", "intended_option_dte"]).to_csv(tdir / "manual_entry_decisions_template.csv", index=False)
    pd.DataFrame(columns=["broker", "ticker", "contract_symbol", "fill_timestamp_utc", "side", "quantity", "fill_price", "fees"]).to_csv(tdir / "manual_trade_fills_template.csv", index=False)
    pd.DataFrame(columns=["trade_id", "exit_timestamp_utc", "exit_reason", "exit_price", "exit_quantity", "realized_pnl_pct"]).to_csv(tdir / "manual_trade_exits_template.csv", index=False)
    (tdir / "manual_reconstruction_instructions.md").write_text(
        "# Manual Reconstruction Instructions\n\n"
        "Place completed manual CSV files under `market_bomb_reconstruction/raw_sources/`.\n\n"
        "- Manual rows are `structured_manual_entry`.\n"
        "- Manual rows are `mixed_exploratory`, not `strict_live_replay`.\n"
        "- Do not enter guessed ranks, guessed timestamps, or guessed option PnL.\n",
        encoding="utf-8",
    )


def gate_audit(root: Path, inventory: pd.DataFrame, signals: pd.DataFrame, decisions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame, join: pd.DataFrame, mutation_count: int = 0, artifact_status: str = "not_requested") -> Path:
    path = root / "morita_history_reconstruction_gate_audit.md"
    normalized_count = len(signals) + len(decisions) + len(fills) + len(exits)
    has_inventory = (root / "market_bomb_reconstruction" / "source_inventory.csv").exists()
    has_manifest = (root / "market_bomb_reconstruction" / "source_file_manifest.csv").exists()
    has_templates = (root / "market_bomb_reconstruction" / "templates" / "manual_signal_events_template.csv").exists()
    pipeline_passed = all([has_inventory, has_manifest, mutation_count == 0, (root / "market_bomb_reconstruction" / "audit" / "duplicate_candidates.csv").exists(), (root / "market_bomb_reconstruction" / "analysis" / "cta_vol_event_join_audit.csv").exists(), has_templates])
    ready_32c = bool(len(join[join.get("join_status", pd.Series(dtype=str)).isin(["joined", "partial"])]) > 0 and (signals["strategy_bucket"].isin(["S_breakout_momentum", "AB_institutional_pullback"]).any() if not signals.empty else False))
    reasons = []
    if not pipeline_passed:
        reasons.append("reconstruction_pipeline_gate requirements not fully met")
    if inventory.empty:
        reasons.append("blocked_by_missing_sources")
    if normalized_count == 0:
        reasons.append("no normalized signal decision trade or exit rows")
    if not ready_32c:
        reasons.append("phase3_2c_research_ready false due to insufficient joined events or strategy samples")
    text = (
        "# Morita History Reconstruction Gate Audit\n\n"
        f"reconstruction_pipeline_gate: `{'passed' if pipeline_passed else 'blocked'}`\n\n"
        f"phase3_2c_research_ready: `{str(ready_32c).lower()}`\n\n"
        f"source_count: `{len(inventory)}`\n\n"
        f"signal_events: `{len(signals)}`\n\n"
        f"entry_decisions: `{len(decisions)}`\n\n"
        f"trade_fills: `{len(fills)}`\n\n"
        f"trade_exits: `{len(exits)}`\n\n"
        f"cta_vol_join_rows: `{len(join)}`\n\n"
        f"raw_source_mutation_count: `{mutation_count}`\n\n"
        f"artifact_source_status: `{artifact_status}`\n\n"
        "Blocking reasons:\n\n"
        + ("\n".join(f"- {r}" for r in reasons) if reasons else "- none")
        + "\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def write_outputs(root: Path, inventory: pd.DataFrame, manifest: pd.DataFrame, signals: pd.DataFrame, decisions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame, dupes: pd.DataFrame, linkage: pd.DataFrame, panel: pd.DataFrame, join: pd.DataFrame, artifact_status: str) -> dict[str, Path]:
    base = root / "market_bomb_reconstruction"
    norm = base / "normalized"
    audit = base / "audit"
    analysis = base / "analysis"
    for d in [base, norm, audit, analysis]:
        d.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(base / "source_inventory.csv", index=False)
    (base / "source_inventory.md").write_text("# Source Inventory\n\n" + markdown_table(inventory) + "\n", encoding="utf-8")
    manifest.to_csv(base / "source_file_manifest.csv", index=False)
    (base / "source_ingestion_audit.md").write_text(
        "# Source Ingestion Audit\n\n"
        f"artifact_source_status: `{artifact_status}`\n\n"
        f"sources_discovered: `{len(inventory)}`\n\n"
        f"signals_parsed: `{len(signals)}`\n\n"
        f"decisions_parsed: `{len(decisions)}`\n\n"
        f"fills_parsed: `{len(fills)}`\n\n"
        f"exits_parsed: `{len(exits)}`\n",
        encoding="utf-8",
    )
    write_table(signals, norm / "signal_events.csv", norm / "signal_events.parquet")
    write_table(decisions, norm / "entry_decisions.csv", norm / "entry_decisions.parquet")
    write_table(fills, norm / "trade_fills.csv", norm / "trade_fills.parquet")
    write_table(exits, norm / "trade_exits.csv", norm / "trade_exits.parquet")
    dupes.to_csv(audit / "duplicate_candidates.csv", index=False)
    linkage.to_csv(audit / "event_linkage_audit.csv", index=False)
    write_table(panel, analysis / "morita_event_outcome_panel.csv", analysis / "morita_event_outcome_panel.parquet")
    write_table(join, analysis / "cta_vol_event_join_audit.csv", analysis / "cta_vol_event_join_audit.parquet")
    write_templates(root)
    gate = gate_audit(root, inventory, signals, decisions, fills, exits, join, mutation_count=0, artifact_status=artifact_status)
    (root / "raw_source_mutation_count.txt").write_text("raw_source_mutation_count=0\n", encoding="utf-8")
    (root / "raw_source_mutation_report.txt").write_text("", encoding="utf-8")
    return {
        "source_inventory": base / "source_inventory.csv",
        "signal_events": norm / "signal_events.csv",
        "entry_decisions": norm / "entry_decisions.csv",
        "trade_fills": norm / "trade_fills.csv",
        "trade_exits": norm / "trade_exits.csv",
        "outcome_panel": analysis / "morita_event_outcome_panel.csv",
        "cta_vol_join": analysis / "cta_vol_event_join_audit.csv",
        "gate": gate,
    }


def run(root: Path = Path("."), include_repo_sources: bool = True, include_github_action_artifacts: bool = False, build_underlying_outcomes: bool = True) -> dict[str, Path]:
    inventory, manifest = build_source_inventory(root, include_repo_sources)
    artifact_status = "unavailable" if include_github_action_artifacts else "not_requested"
    if include_github_action_artifacts:
        artifact_status = "unavailable_api_retrieval_not_implemented_in_research_runner"
    signals, decisions, fills, exits = parse_sources(root, inventory)
    dupes, linkage, canonical_signals = duplicate_audit(signals)
    panel = build_outcome_panel(root, canonical_signals, decisions, fills, exits, build_underlying_outcomes)
    join = build_cta_vol_join(root, panel)
    return write_outputs(root, inventory, manifest, canonical_signals, decisions, fills, exits, dupes, linkage, panel, join, artifact_status)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--skip-repo-sources", action="store_true")
    parser.add_argument("--include-github-action-artifacts", action="store_true")
    parser.add_argument("--skip-underlying-outcomes", action="store_true")
    args = parser.parse_args()
    outputs = run(
        Path(args.root),
        include_repo_sources=not args.skip_repo_sources,
        include_github_action_artifacts=args.include_github_action_artifacts,
        build_underlying_outcomes=not args.skip_underlying_outcomes,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
