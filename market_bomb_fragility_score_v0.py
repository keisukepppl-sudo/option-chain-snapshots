#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ARTIFACT_VERSION = "market_fragility_score_v0_1_1"
SCORE_POLICY_REVISION = "predeclared_fragility_rubric_v0_1"
SCORE_DECISION_TIME_POLICY = "nyse_regular_session_close_plus_15_minutes_v0_1"
INPUT_MODE = "local_timestamped_csv_only_default"
OOS_MODE = "predeclared_walk_forward_descriptive_evaluation_v0_1"
ACTIONIZATION_ALLOWED = False
AS_OF_SELECTION_POLICY = "exact_requested_session_only_no_stale_fallback_v0_1_1"
ROLLING_WINDOW_POLICY = "consecutive_nyse_calendar_sessions_required_v0_1_1"
FUTURE_OUTCOME_WINDOW_POLICY = "consecutive_nyse_calendar_sessions_required_v0_1_1"
VIX_COMPONENT_LINEAGE_POLICY = "required_vix_vix3m_min_confidence_max_effective_timestamp_v0_1_1"
DUPLICATE_FINAL_RECONCILIATION_POLICY = "duplicate_keys_selected_invalid_all_artifacts_v0_1_1"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TARGETS = ["SPY", "QQQ", "SOXX", "MARKET"]
PRICE_TICKERS = ["SPY", "QQQ", "SOXX"]
VOL_TICKERS = ["VIX", "VIX3M", "VIX9D"]
ALL_TICKERS = PRICE_TICKERS + VOL_TICKERS
COMPONENTS = [
    "trend_drawdown_stress",
    "realized_volatility_stress",
    "cta_deleveraging_proxy",
    "vol_control_deleveraging_proxy",
    "vix_term_structure_stress",
]
CORE_COMPONENTS = [
    "trend_drawdown_stress",
    "realized_volatility_stress",
    "cta_deleveraging_proxy",
    "vol_control_deleveraging_proxy",
]
COMPONENT_WEIGHTS = {
    "trend_drawdown_stress": 20.0,
    "realized_volatility_stress": 25.0,
    "cta_deleveraging_proxy": 25.0,
    "vol_control_deleveraging_proxy": 20.0,
    "vix_term_structure_stress": 10.0,
}
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
OOS_CAVEAT = (
    "Descriptive OOS association for a predeclared research rubric only. "
    "No score weights were fitted, and results do not authorize actionization."
)


RAW_SOURCE_INVENTORY_COLUMNS = [
    "ticker",
    "source_path_or_provider",
    "file_exists",
    "raw_row_count",
    "provisional_valid_row_count",
    "final_canonical_valid_row_count",
    "valid_row_count",
    "selected_invalid_row_count",
    "duplicate_selected_invalid_row_count",
    "first_session_date",
    "last_session_date",
    "source_content_hash",
    "availability_basis_summary",
    "availability_confidence_summary",
]
RAW_INPUT_AUDIT_COLUMNS = [
    "ticker",
    "raw_row_ordinal",
    "raw_session_date",
    "raw_close",
    "raw_effective_available_at_utc",
    "source_row_identifier",
    "raw_input_status",
    "raw_input_reason",
    "canonical_session_date",
    "canonical_decision_timestamp_utc",
    "canonical_effective_available_at_utc",
]
CALENDAR_AUDIT_COLUMNS = [
    "session_date",
    "is_regular_session",
    "regular_close_et",
    "decision_timestamp_utc",
    "calendar_status",
    "calendar_reason",
]
AVAILABILITY_AUDIT_COLUMNS = [
    "ticker",
    "session_date",
    "decision_timestamp_utc",
    "source_as_of_timestamp_utc",
    "effective_available_at_utc",
    "availability_basis",
    "availability_confidence",
    "availability_status",
    "availability_reason",
]
CANONICAL_PANEL_COLUMNS = [
    "ticker",
    "session_date",
    "decision_timestamp_utc",
    "close",
    "high",
    "low",
    "volume",
    "source_row_identifier",
    "source_as_of_timestamp_utc",
    "effective_available_at_utc",
    "source_url_or_path",
    "source_content_hash",
    "availability_basis",
    "availability_confidence",
    "raw_input_status",
    "raw_input_reason",
]
DECISION_UNIVERSE_COLUMNS = [
    "score_target",
    "session_date",
    "decision_timestamp_utc",
    "score_decision_time_policy",
    "universe_status",
    "universe_reason",
]
FEATURE_PANEL_COLUMNS = [
    "score_target",
    "session_date",
    "decision_timestamp_utc",
    "feature_name",
    "feature_value",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
    "source_path_or_provider",
    "source_content_hash",
    "availability_status",
    "availability_reason",
    "is_proxy",
    "observed_flow",
    "data_type",
]
NO_LOOKAHEAD_COLUMNS = [
    "score_target",
    "session_date",
    "decision_timestamp_utc",
    "feature_name",
    "component_name",
    "max_input_effective_available_at_utc",
    "no_lookahead_status",
    "no_lookahead_reason",
]
COMPONENT_INPUT_LINEAGE_COLUMNS = [
    "score_target",
    "session_date",
    "decision_timestamp_utc",
    "component_name",
    "input_family",
    "input_tickers",
    "input_session_count_required",
    "input_session_count_valid",
    "input_session_completeness_status",
    "input_session_completeness_reason",
    "max_input_effective_available_at_utc",
    "min_input_source_confidence",
    "input_source_path_or_provider_summary",
    "input_source_content_hash_summary",
    "lineage_status",
    "lineage_reason",
    "is_proxy",
    "observed_flow",
    "data_type",
]
LOOKBACK_COMPLETENESS_COLUMNS = [
    "ticker",
    "session_date",
    "decision_timestamp_utc",
    "lookback_name",
    "required_calendar_session_count",
    "valid_source_session_count",
    "missing_calendar_session_count",
    "missing_calendar_session_dates",
    "window_completeness_status",
    "window_completeness_reason",
    "max_input_effective_available_at_utc",
    "min_input_source_confidence",
]
AS_OF_REQUEST_AUDIT_COLUMNS = [
    "requested_as_of_date",
    "score_target",
    "requested_calendar_session_exists",
    "requested_session_date",
    "requested_decision_timestamp_utc",
    "required_source_input_status",
    "core_component_status",
    "score_row_exists",
    "score_status",
    "as_of_resolution_status",
    "as_of_resolution_reason",
    "resolved_session_date",
    "resolved_decision_timestamp_utc",
    "actionization_allowed",
]
RAW_RECONCILIATION_COLUMNS = [
    "ticker",
    "raw_row_count",
    "raw_valid_before_duplicate_resolution_count",
    "raw_selected_invalid_final_count",
    "availability_valid_final_count",
    "canonical_valid_final_count",
    "raw_valid_key_set_sha256",
    "availability_valid_key_set_sha256",
    "canonical_valid_key_set_sha256",
    "raw_availability_canonical_reconciliation_status",
    "raw_availability_canonical_reconciliation_reason",
]
COMPONENT_SCORE_COLUMNS = [
    "score_target",
    "session_date",
    "decision_timestamp_utc",
    "component_name",
    "component_score",
    "nominal_weight",
    "component_available",
    "component_status",
    "component_reason",
    "source_confidence",
    "is_proxy",
    "observed_flow",
    "data_type",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
]
SCORE_PANEL_COLUMNS = [
    "score_target",
    "session_date",
    "decision_timestamp_utc",
    "fragility_score",
    "score_status",
    "risk_state",
    "confidence",
    "data_coverage_pct",
    "available_nominal_weight",
    "missing_components",
    "component_source_confidence_summary",
    "availability_warning_count",
    "trend_drawdown_stress",
    "realized_volatility_stress",
    "cta_deleveraging_proxy",
    "vol_control_deleveraging_proxy",
    "vix_term_structure_stress",
    "actionization_allowed",
    "score_policy_revision",
]
OOS_PANEL_COLUMNS = [
    "score_target",
    "session_date",
    "decision_timestamp_utc",
    "fragility_score",
    "risk_state",
    "score_band",
    "oos_eligible",
    "oos_reason",
    "fold_month",
    "rv20_at_t",
    "forward_close_return_5d",
    "forward_close_return_10d",
    "forward_realized_vol_5d",
    "forward_realized_vol_10d",
    "forward_close_to_close_drawdown_5d",
    "forward_close_to_close_drawdown_10d",
    "forward_tail_flag_5d",
    "forward_tail_flag_10d",
    "actionization_allowed",
]
OOS_SUMMARY_COLUMNS = [
    "score_target",
    "valid_oos_observation_count",
    "non_empty_fold_count",
    "score_vs_forward_rv5_spearman",
    "score_vs_forward_rv10_spearman",
    "score_vs_drawdown5_spearman",
    "score_vs_drawdown10_spearman",
    "high_minus_low_forward_rv5",
    "high_minus_low_tail_rate_5d",
    "high_minus_low_drawdown5",
    "evidence_status",
    "interpretation_caveat",
]


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value is None or pd.isna(value):
        return np.nan
    return float(min(max(value, low), high))


@lru_cache(maxsize=20000)
def _parse_ts_cached(text: str) -> pd.Timestamp | None:
    if text == "":
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return pd.Timestamp(dt)
        return pd.Timestamp(dt).tz_convert("UTC")
    except ValueError:
        ts = pd.to_datetime(text, errors="coerce")
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            return pd.Timestamp(ts)
        return pd.Timestamp(ts).tz_convert("UTC")


def parse_ts(value: Any) -> pd.Timestamp | None:
    if is_blank_value(value):
        return None
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is None:
            return value
        return value.tz_convert("UTC")
    return _parse_ts_cached(str(value))


def is_tz_aware(value: Any) -> bool:
    if is_blank_value(value):
        return False
    text = str(value)
    if text.endswith("Z") or text.endswith("+00:00"):
        return True
    if "T" in text and len(text) >= 6 and (text[-6] in ["+", "-"]) and text[-3] == ":":
        return True
    ts = parse_ts(text)
    return ts is not None and ts.tzinfo is not None


def is_blank_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def iso_utc(ts: Any) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")


def as_date(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return text[:10]
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return ""
    return str(pd.Timestamp(ts).date())


def file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            parquet_path.write_text(
                json.dumps(
                    {
                        "parquet_unavailable": True,
                        "csv_fallback_path": str(csv_path.name),
                        "reason": "No parquet engine available in this environment.",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )


def load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fallback


def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {"date": "session_date", "adj_close": "close", "adjusted_close": "close"}
    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower()
        renamed[col] = aliases.get(key, key)
    return df.rename(columns=renamed)


def load_calendar(root: Path) -> pd.DataFrame:
    path = root / "market_bomb_config" / "nyse_regular_sessions_v1.csv"
    if not path.exists():
        return pd.DataFrame(columns=CALENDAR_AUDIT_COLUMNS)
    cal = pd.read_csv(path)
    regular = cal[cal["is_regular_session"].astype(str).str.lower().eq("true")].copy()
    records: list[dict[str, Any]] = []
    for row in regular.to_dict("records"):
        session_date = as_date(row.get("session_date"))
        close_text = str(row.get("regular_close_et", "16:00"))
        hour, minute = [int(x) for x in close_text.split(":")[:2]]
        close_et = pd.Timestamp(session_date).replace(hour=hour, minute=minute, tzinfo=ET)
        decision_ts = close_et.tz_convert("UTC") + timedelta(minutes=15)
        records.append(
            {
                "session_date": session_date,
                "is_regular_session": True,
                "regular_close_et": close_text,
                "decision_timestamp_utc": iso_utc(decision_ts),
                "calendar_status": "valid",
                "calendar_reason": "regular_nyse_session",
            }
        )
    return pd.DataFrame(records, columns=CALENDAR_AUDIT_COLUMNS)


def expected_source_path(input_root: Path, ticker: str) -> Path:
    if ticker in PRICE_TICKERS:
        return input_root / "daily_prices" / f"{ticker}.csv"
    return input_root / "volatility_indices" / f"{ticker}.csv"


def ingest_raw_sources(root: Path, input_root: Path, calendar: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cal_map = calendar.set_index("session_date")["decision_timestamp_utc"].to_dict() if not calendar.empty else {}
    inventory: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    canonical_candidates: list[dict[str, Any]] = []
    availability_rows: list[dict[str, Any]] = []
    provisional_valid_counts: dict[str, int] = {ticker: 0 for ticker in ALL_TICKERS}
    raw_counts: dict[str, int] = {ticker: 0 for ticker in ALL_TICKERS}
    source_paths: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    file_exists: dict[str, bool] = {}

    for ticker in ALL_TICKERS:
        path = expected_source_path(input_root, ticker)
        content_hash = file_sha256(path)
        source_paths[ticker] = str(path)
        source_hashes[ticker] = content_hash
        file_exists[ticker] = path.exists()
        raw_count = 0
        if path.exists():
            try:
                raw = normalize_headers(pd.read_csv(path))
            except Exception:
                raw = pd.DataFrame()
                audit_rows.append(
                    {
                        "ticker": ticker,
                        "raw_row_ordinal": 0,
                        "raw_session_date": "",
                        "raw_close": "",
                        "raw_effective_available_at_utc": "",
                        "source_row_identifier": "",
                        "raw_input_status": "selected_invalid",
                        "raw_input_reason": "csv_parse_failure",
                        "canonical_session_date": "",
                        "canonical_decision_timestamp_utc": "",
                        "canonical_effective_available_at_utc": "",
                    }
                )
        else:
            raw = pd.DataFrame()
        raw_count = len(raw)
        raw_counts[ticker] = raw_count
        for ordinal, row in enumerate(raw.to_dict("records"), start=1):
            raw_session = row.get("session_date", "")
            session_date = as_date(raw_session)
            raw_close = row.get("close", "")
            close = pd.to_numeric(pd.Series([raw_close]), errors="coerce").iloc[0]
            eff_raw = row.get("effective_available_at_utc", "")
            source_as_of_raw = row.get("source_as_of_timestamp_utc", "")
            source_row_id = row.get("source_row_identifier", f"{ticker}:{ordinal}")
            high = pd.to_numeric(pd.Series([row.get("high", np.nan)]), errors="coerce").iloc[0]
            low = pd.to_numeric(pd.Series([row.get("low", np.nan)]), errors="coerce").iloc[0]
            volume = pd.to_numeric(pd.Series([row.get("volume", np.nan)]), errors="coerce").iloc[0]
            reasons: list[str] = []
            status = "valid"
            decision_ts = cal_map.get(session_date, "")
            if not session_date:
                reasons.append("blank_or_unparsable_session_date")
            elif session_date not in cal_map:
                reasons.append("session_date_absent_from_nyse_calendar")
            if pd.isna(close) or float(close) <= 0:
                reasons.append("invalid_nonpositive_close")
            if not is_blank_value(eff_raw) and not is_tz_aware(eff_raw):
                reasons.append("timezone_naive_supplied_effective_timestamp")
            source_as_of = parse_ts(source_as_of_raw) if not is_blank_value(source_as_of_raw) and is_tz_aware(source_as_of_raw) else None
            if not is_blank_value(eff_raw) and is_tz_aware(eff_raw):
                effective_ts = parse_ts(eff_raw)
                availability_basis = "observed_source_effective_timestamp"
                availability_confidence = str(row.get("availability_confidence", "high")).lower() or "high"
            elif decision_ts:
                effective_ts = parse_ts(decision_ts)
                availability_basis = "assumed_official_close_plus_15_minutes"
                availability_confidence = "medium"
            else:
                effective_ts = None
                availability_basis = "unavailable"
                availability_confidence = "low"
            if decision_ts and effective_ts is not None and pd.Timestamp(effective_ts).tz_convert("UTC") > parse_ts(decision_ts):
                status = "unavailable_coverage"
                reasons.append("future_availability_timestamp")
            if reasons and status != "unavailable_coverage":
                status = "selected_invalid"
            reason = ";".join(reasons) if reasons else "valid"
            audit_rows.append(
                {
                    "ticker": ticker,
                    "raw_row_ordinal": ordinal,
                    "raw_session_date": raw_session,
                    "raw_close": raw_close,
                    "raw_effective_available_at_utc": eff_raw,
                    "source_row_identifier": source_row_id,
                    "raw_input_status": status,
                    "raw_input_reason": reason,
                    "canonical_session_date": session_date if status == "valid" else "",
                    "canonical_decision_timestamp_utc": decision_ts if status == "valid" else "",
                    "canonical_effective_available_at_utc": iso_utc(effective_ts) if status == "valid" and effective_ts is not None else "",
                }
            )
            if status in ["valid", "unavailable_coverage"] and session_date and decision_ts:
                availability_rows.append(
                    {
                        "ticker": ticker,
                        "session_date": session_date,
                        "decision_timestamp_utc": decision_ts,
                        "source_as_of_timestamp_utc": iso_utc(source_as_of),
                        "effective_available_at_utc": iso_utc(effective_ts),
                        "availability_basis": availability_basis,
                        "availability_confidence": availability_confidence,
                        "availability_status": status,
                        "availability_reason": reason,
                    }
                )
            if status == "valid":
                provisional_valid_counts[ticker] += 1
                canonical_candidates.append(
                    {
                        "ticker": ticker,
                        "session_date": session_date,
                        "decision_timestamp_utc": decision_ts,
                        "close": float(close),
                        "high": float(high) if not pd.isna(high) else np.nan,
                        "low": float(low) if not pd.isna(low) else np.nan,
                        "volume": float(volume) if not pd.isna(volume) else np.nan,
                        "source_row_identifier": source_row_id,
                        "source_as_of_timestamp_utc": iso_utc(source_as_of),
                        "effective_available_at_utc": iso_utc(effective_ts),
                        "source_url_or_path": str(row.get("source_url_or_path", path)),
                        "source_content_hash": str(row.get("source_content_hash", content_hash or EMPTY_SHA256)),
                        "availability_basis": availability_basis,
                        "availability_confidence": availability_confidence,
                        "raw_input_status": status,
                        "raw_input_reason": reason,
                    }
                )

    canonical = pd.DataFrame(canonical_candidates, columns=CANONICAL_PANEL_COLUMNS)
    audit = pd.DataFrame(audit_rows, columns=RAW_INPUT_AUDIT_COLUMNS)
    availability = pd.DataFrame(availability_rows, columns=AVAILABILITY_AUDIT_COLUMNS)
    if canonical.empty:
        for ticker in ALL_TICKERS:
            selected_invalid = len(audit[(audit["ticker"] == ticker) & (audit["raw_input_status"] == "selected_invalid")]) if not audit.empty else 0
            inventory.append(
                {
                    "ticker": ticker,
                    "source_path_or_provider": source_paths.get(ticker, str(expected_source_path(input_root, ticker))),
                    "file_exists": file_exists.get(ticker, False),
                    "raw_row_count": raw_counts.get(ticker, 0),
                    "provisional_valid_row_count": provisional_valid_counts.get(ticker, 0),
                    "final_canonical_valid_row_count": 0,
                    "valid_row_count": 0,
                    "selected_invalid_row_count": selected_invalid,
                    "duplicate_selected_invalid_row_count": 0,
                    "first_session_date": "",
                    "last_session_date": "",
                    "source_content_hash": source_hashes.get(ticker, ""),
                    "availability_basis_summary": "",
                    "availability_confidence_summary": "",
                }
            )
        inventory_df = pd.DataFrame(inventory, columns=RAW_SOURCE_INVENTORY_COLUMNS)
        return inventory_df, audit, availability, canonical

    duplicate_keys = canonical.duplicated(["ticker", "session_date"], keep=False)
    if duplicate_keys.any():
        duplicate_df = canonical[duplicate_keys].copy()
        bad_keys = set()
        for key, group in duplicate_df.groupby(["ticker", "session_date"]):
            comparable = group[["close", "high", "low", "volume"]].astype(str).drop_duplicates()
            bad_keys.add((key[0], key[1], "duplicate_metadata_conflict" if len(comparable) > 1 else "duplicate_ticker_session"))
        keep_mask = []
        for row in canonical.to_dict("records"):
            matched = [reason for t, d, reason in bad_keys if t == row["ticker"] and d == row["session_date"]]
            if matched:
                keep_mask.append(False)
                audit.loc[
                    (audit["ticker"] == row["ticker"]) & (audit["canonical_session_date"] == row["session_date"]),
                    ["raw_input_status", "raw_input_reason", "canonical_session_date", "canonical_decision_timestamp_utc", "canonical_effective_available_at_utc"],
                ] = ["selected_invalid", matched[0], "", "", ""]
                availability.loc[
                    (availability["ticker"] == row["ticker"]) & (availability["session_date"] == row["session_date"]),
                    ["availability_status", "availability_reason"],
                ] = ["selected_invalid", matched[0]]
            else:
                keep_mask.append(True)
        canonical = canonical[pd.Series(keep_mask).values].copy()
    for ticker in ALL_TICKERS:
        candidates = canonical[canonical["ticker"] == ticker].to_dict("records") if not canonical.empty else []
        selected_invalid = len(audit[(audit["ticker"] == ticker) & (audit["raw_input_status"] == "selected_invalid")]) if not audit.empty else 0
        duplicate_invalid = len(audit[(audit["ticker"] == ticker) & (audit["raw_input_reason"].astype(str).str.contains("duplicate_", na=False))]) if not audit.empty else 0
        inventory.append(
            {
                "ticker": ticker,
                "source_path_or_provider": source_paths.get(ticker, str(expected_source_path(input_root, ticker))),
                "file_exists": file_exists.get(ticker, False),
                "raw_row_count": raw_counts.get(ticker, 0),
                "provisional_valid_row_count": provisional_valid_counts.get(ticker, 0),
                "final_canonical_valid_row_count": len(candidates),
                "valid_row_count": len(candidates),
                "selected_invalid_row_count": selected_invalid,
                "duplicate_selected_invalid_row_count": duplicate_invalid,
                "first_session_date": min([x["session_date"] for x in candidates], default=""),
                "last_session_date": max([x["session_date"] for x in candidates], default=""),
                "source_content_hash": source_hashes.get(ticker, ""),
                "availability_basis_summary": ",".join(sorted(set(x["availability_basis"] for x in candidates))),
                "availability_confidence_summary": ",".join(sorted(set(x["availability_confidence"] for x in candidates))),
            }
        )
    inventory_df = pd.DataFrame(inventory, columns=RAW_SOURCE_INVENTORY_COLUMNS)
    return inventory_df, audit, availability, canonical.sort_values(["ticker", "session_date"]).reset_index(drop=True)


def build_decision_universe(canonical: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if calendar.empty:
        return pd.DataFrame(rows, columns=DECISION_UNIVERSE_COLUMNS)
    valid = set(zip(canonical["ticker"], canonical["session_date"])) if not canonical.empty else set()
    for cal in calendar.to_dict("records"):
        session_date = cal["session_date"]
        decision_ts = cal["decision_timestamp_utc"]
        for target in TARGETS:
            if target == "MARKET":
                ok = ("SPY", session_date) in valid and ("QQQ", session_date) in valid
                reason = "requires_spy_and_qqq_same_session"
            else:
                ok = (target, session_date) in valid
                reason = f"requires_{target.lower()}_eligible_daily_bar"
            rows.append(
                {
                    "score_target": target,
                    "session_date": session_date,
                    "decision_timestamp_utc": decision_ts,
                    "score_decision_time_policy": SCORE_DECISION_TIME_POLICY,
                    "universe_status": "valid" if ok else "unavailable_coverage",
                    "universe_reason": "eligible" if ok else reason,
                }
            )
    return pd.DataFrame(rows, columns=DECISION_UNIVERSE_COLUMNS)


def percentile_rank(series: pd.Series, window: int = 252, min_periods: int = 126) -> pd.Series:
    def rank_last(values: np.ndarray) -> float:
        s = pd.Series(values).dropna()
        if len(s) < min_periods:
            return np.nan
        return float((s <= s.iloc[-1]).mean())

    return series.rolling(window, min_periods=min_periods).apply(rank_last, raw=True)


def spearman_corr(left: pd.Series, right: pd.Series) -> float:
    pairs = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(pairs) < 2:
        return np.nan
    return float(pairs["left"].rank(method="average").corr(pairs["right"].rank(method="average")))


def confidence_rank(value: str) -> int:
    return {"unavailable": 0, "low": 1, "medium": 2, "high": 3}.get(str(value).lower(), 0)


def confidence_min(values: list[str]) -> str:
    clean = [str(v).lower() for v in values if str(v).strip()]
    if not clean:
        return "Unavailable"
    lowest = min(clean, key=confidence_rank)
    return {"high": "High", "medium": "Medium", "low": "Low", "unavailable": "Unavailable"}.get(lowest, "Unavailable")


def key_set_sha256(keys: list[tuple[str, str]]) -> str:
    values = sorted({f"{ticker}|{session_date}" for ticker, session_date in keys})
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def timestamp_max(values: list[str]) -> str:
    parsed = [parse_ts(v) for v in values if str(v).strip()]
    parsed = [v for v in parsed if v is not None]
    if not parsed:
        return ""
    return iso_utc(max(parsed))


def timestamp_lte(left: str, right: str) -> bool:
    lts = parse_ts(left)
    rts = parse_ts(right)
    if lts is None or rts is None:
        return False
    return lts <= rts


def compute_target_features(target: str, panel: pd.DataFrame, calendar: pd.DataFrame | None = None) -> pd.DataFrame:
    ticker = target
    source = panel[panel["ticker"] == ticker].sort_values("session_date").copy()
    if source.empty:
        return source
    if calendar is not None and not calendar.empty:
        cal = calendar[["session_date", "decision_timestamp_utc"]].drop_duplicates().sort_values("session_date").copy()
        df = cal.merge(source.drop(columns=["decision_timestamp_utc"], errors="ignore"), on="session_date", how="left")
        df["ticker"] = ticker
    else:
        df = source.copy()
    df["has_canonical_source"] = df["close"].notna()
    close = df["close"].astype(float)
    log_ret = np.log(close / close.shift(1))
    df["ma20"] = close.rolling(20, min_periods=20).mean()
    df["ma50"] = close.rolling(50, min_periods=50).mean()
    df["ma200"] = close.rolling(200, min_periods=200).mean()
    df["dd63"] = 1 - close / close.rolling(63, min_periods=63).max()
    df["r20"] = close / close.shift(20) - 1
    df["r60"] = close / close.shift(60) - 1
    df["r120"] = close / close.shift(120) - 1
    df["r252"] = close / close.shift(252) - 1
    df["rv20"] = log_ret.rolling(20, min_periods=20).std(ddof=1) * math.sqrt(252)
    df["rv60"] = log_ret.rolling(60, min_periods=60).std(ddof=1) * math.sqrt(252)
    df["rv20_percentile_252"] = percentile_rank(df["rv20"])
    df["rv_acceleration"] = ((df["rv20"] / df["rv60"].clip(lower=1e-9) - 1.0) / 0.75).apply(clip)
    trend_direction = (
        0.40 * (df["r20"] > 0).astype(float)
        + 0.30 * (df["r60"] > 0).astype(float)
        + 0.20 * (df["r120"] > 0).astype(float)
        + 0.10 * (df["r252"] > 0).astype(float)
    )
    risk_scalar = (0.15 / df["rv20"].clip(lower=0.05)).apply(clip)
    df["cta_long_exposure"] = trend_direction * risk_scalar
    df["cta_sell_impulse"] = ((df["cta_long_exposure"].shift(1) - df["cta_long_exposure"]) / 0.25).apply(clip)
    df["cta_risk_off_state"] = 1 - df["cta_long_exposure"]
    df["vol_control_exposure"] = (0.12 / df["rv20"].clip(lower=0.05)).apply(clip)
    df["vol_control_sell_impulse"] = ((df["vol_control_exposure"].shift(1) - df["vol_control_exposure"]) / 0.25).apply(clip)
    df["vol_control_stress_state"] = ((df["rv20"] / 0.12 - 1.0) / 1.0).apply(clip)
    return df


def window_meta(df: pd.DataFrame, idx: int, count: int, value_col: str = "close") -> dict[str, Any]:
    if idx - count + 1 < 0:
        window = df.iloc[0 : idx + 1]
        missing_prefix = count - len(window)
    else:
        window = df.iloc[idx - count + 1 : idx + 1]
        missing_prefix = 0
    valid = int(window[value_col].notna().sum())
    missing_dates = list(window.loc[window[value_col].isna(), "session_date"].astype(str))
    if missing_prefix:
        missing_dates = [f"pre_calendar_start_{missing_prefix}"] + missing_dates
    effective = list(window.loc[window[value_col].notna(), "effective_available_at_utc"].dropna().astype(str))
    confidences = list(window.loc[window[value_col].notna(), "availability_confidence"].dropna().astype(str))
    complete = valid == count and missing_prefix == 0
    return {
        "required": count,
        "valid": valid,
        "missing": count - valid,
        "missing_dates": ",".join(missing_dates),
        "status": "valid" if complete else "unavailable_coverage",
        "max_effective": timestamp_max(effective),
        "min_confidence": confidence_min(confidences),
    }


def build_lookback_completeness_audit(target_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    specs = {
        "ma20": ("close", 20),
        "ma50": ("close", 50),
        "ma200": ("close", 200),
        "dd63": ("close", 63),
        "r20": ("close", 21),
        "r60": ("close", 61),
        "r120": ("close", 121),
        "r252": ("close", 253),
        "rv20": ("close", 21),
        "rv60": ("close", 61),
        "rv20_percentile_252": ("rv20", 126),
    }
    for ticker, df in target_frames.items():
        work = df.reset_index(drop=True)
        if work.empty:
            continue
        session_dates = work["session_date"].astype(str).tolist()
        decision_ts_values = work["decision_timestamp_utc"].astype(str).tolist()
        effective_values = work.get("effective_available_at_utc", pd.Series([""] * len(work))).fillna("").astype(str).tolist()
        confidence_values = work.get("availability_confidence", pd.Series([""] * len(work))).fillna("").astype(str).tolist()
        value_arrays = {
            "close": work["close"].notna().astype(int).to_numpy() if "close" in work else np.zeros(len(work), dtype=int),
            "rv20": work["rv20"].notna().astype(int).to_numpy() if "rv20" in work else np.zeros(len(work), dtype=int),
        }
        cumulative = {name: np.concatenate([[0], arr.cumsum()]) for name, arr in value_arrays.items()}
        for idx, row in work.iterrows():
            for name, (col, count) in specs.items():
                start = idx - count + 1
                actual_start = max(start, 0)
                missing_prefix = max(0, -start)
                valid = int(cumulative[col][idx + 1] - cumulative[col][actual_start])
                missing_count = count - valid
                if missing_count:
                    missing_dates = []
                    if missing_prefix:
                        missing_dates.append(f"pre_calendar_start_{missing_prefix}")
                    arr = value_arrays[col]
                    missing_dates.extend(session_dates[j] for j in range(actual_start, idx + 1) if arr[j] == 0)
                    status = "unavailable_coverage"
                    reason = f"incomplete_{name}_window"
                else:
                    missing_dates = []
                    status = "valid"
                    reason = "valid"
                valid_indices = [j for j in range(actual_start, idx + 1) if value_arrays[col][j] == 1]
                max_eff = timestamp_max([effective_values[j] for j in valid_indices])
                min_conf = confidence_min([confidence_values[j] for j in valid_indices])
                rows.append(
                    {
                        "ticker": ticker,
                        "session_date": row["session_date"],
                        "decision_timestamp_utc": row["decision_timestamp_utc"],
                        "lookback_name": name,
                        "required_calendar_session_count": count,
                        "valid_source_session_count": valid,
                        "missing_calendar_session_count": missing_count,
                        "missing_calendar_session_dates": ",".join(missing_dates),
                        "window_completeness_status": status,
                        "window_completeness_reason": reason,
                        "max_input_effective_available_at_utc": max_eff,
                        "min_input_source_confidence": min_conf,
                    }
                )
    return pd.DataFrame(rows, columns=LOOKBACK_COMPLETENESS_COLUMNS)


def vix_features(panel: pd.DataFrame, calendar: pd.DataFrame | None = None) -> pd.DataFrame:
    vol = panel[panel["ticker"].isin(VOL_TICKERS)].copy()
    piv = vol.pivot(index="session_date", columns="ticker", values="close") if not vol.empty else pd.DataFrame()
    if calendar is not None and not calendar.empty:
        base = calendar[["session_date", "decision_timestamp_utc"]].drop_duplicates().sort_values("session_date").set_index("session_date")
        piv = base.join(piv, how="left")
    elif "decision_timestamp_utc" not in piv.columns and not vol.empty:
        decision = vol.drop_duplicates("session_date").set_index("session_date")["decision_timestamp_utc"]
        piv = decision.to_frame().join(piv, how="right")
    if piv.empty:
        return pd.DataFrame()
    out = piv.copy()
    if "VIX" in out:
        out["vix_percentile_252"] = percentile_rank(out["VIX"])
    if "VIX" in out and "VIX3M" in out:
        out["backwardation"] = ((out["VIX"] / out["VIX3M"] - 1.0) / 0.15).apply(clip)
    if "VIX9D" in out and "VIX" in out:
        out["near_term_stress"] = ((out["VIX9D"] / out["VIX"] - 1.0) / 0.15).apply(clip)
    return out.reset_index()


def row_source_confidence(rows: pd.DataFrame) -> str:
    if rows.empty:
        return "Low"
    vals = set(rows["availability_confidence"].astype(str).str.lower())
    return "High" if vals == {"high"} else "Medium" if "medium" in vals or vals else "Low"


def build_feature_and_scores(
    canonical: pd.DataFrame,
    universe: pd.DataFrame,
    availability: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    feature_rows: list[dict[str, Any]] = []
    feature_audit_rows: list[dict[str, Any]] = []
    no_lookahead_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    if canonical.empty or universe.empty:
        return (
            pd.DataFrame(feature_rows, columns=FEATURE_PANEL_COLUMNS),
            pd.DataFrame(feature_audit_rows, columns=FEATURE_PANEL_COLUMNS),
            pd.DataFrame(no_lookahead_rows, columns=NO_LOOKAHEAD_COLUMNS),
            pd.DataFrame(lineage_rows, columns=COMPONENT_INPUT_LINEAGE_COLUMNS),
            pd.DataFrame(columns=LOOKBACK_COMPLETENESS_COLUMNS),
            pd.DataFrame(component_rows, columns=COMPONENT_SCORE_COLUMNS),
            pd.DataFrame(score_rows, columns=SCORE_PANEL_COLUMNS),
        )

    calendar = universe[["session_date", "decision_timestamp_utc"]].drop_duplicates().sort_values("session_date").reset_index(drop=True)
    target_feature_frames = {t: compute_target_features(t, canonical, calendar) for t in PRICE_TICKERS}
    lookback_audit = build_lookback_completeness_audit(target_feature_frames)
    lookback_by_key = {
        (row["ticker"], row["session_date"], row["lookback_name"]): row for row in lookback_audit.to_dict("records")
    }
    vix_frame = vix_features(canonical, calendar)
    vix_by_date = vix_frame.set_index("session_date").to_dict("index") if not vix_frame.empty else {}
    source_rows_by_key = {
        (row["ticker"], row["session_date"]): row for row in canonical.to_dict("records")
    }
    availability_by_key = {
        (row["ticker"], row["session_date"]): row for row in availability.to_dict("records")
    } if availability is not None and not availability.empty else {}

    def price_lineage(target: str, session_date: str, component_name: str, lookbacks: list[str], is_proxy: bool, data_type: str) -> dict[str, Any]:
        metas = [lookback_by_key.get((target, session_date, name), {}) for name in lookbacks]
        required = sum(int(m.get("required_calendar_session_count", 0) or 0) for m in metas)
        valid = min([int(m.get("valid_source_session_count", 0) or 0) for m in metas], default=0)
        bad = [m for m in metas if m.get("window_completeness_status") != "valid"]
        max_eff = timestamp_max([str(m.get("max_input_effective_available_at_utc", "")) for m in metas])
        min_conf = confidence_min([str(m.get("min_input_source_confidence", "")) for m in metas])
        status = "valid" if not bad else "unavailable_coverage"
        reason = "valid" if not bad else ";".join(sorted(set(str(m.get("window_completeness_reason", "")) for m in bad if m)))
        src = source_rows_by_key.get((target, session_date), {})
        row = {
            "score_target": target,
            "session_date": session_date,
            "decision_timestamp_utc": src.get("decision_timestamp_utc", ""),
            "component_name": component_name,
            "input_family": "PRICE_WINDOW",
            "input_tickers": target,
            "input_session_count_required": required,
            "input_session_count_valid": valid,
            "input_session_completeness_status": status,
            "input_session_completeness_reason": reason,
            "max_input_effective_available_at_utc": max_eff,
            "min_input_source_confidence": min_conf,
            "input_source_path_or_provider_summary": src.get("source_url_or_path", ""),
            "input_source_content_hash_summary": src.get("source_content_hash", ""),
            "lineage_status": status,
            "lineage_reason": reason,
            "is_proxy": is_proxy,
            "observed_flow": False,
            "data_type": data_type,
        }
        lineage_rows.append(row)
        return row

    def vix_input_rows(session_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        required = []
        optional = []
        for ticker in ["VIX", "VIX3M"]:
            src = source_rows_by_key.get((ticker, session_date))
            av = availability_by_key.get((ticker, session_date), {})
            required.append(src or av or {"ticker": ticker, "session_date": session_date})
        src9 = source_rows_by_key.get(("VIX9D", session_date))
        av9 = availability_by_key.get(("VIX9D", session_date), {})
        optional.append(src9 or av9 or {"ticker": "VIX9D", "session_date": session_date})
        used_optional = [src9] if src9 is not None else []
        return required, optional, used_optional

    def vix_lineage(target: str, session_date: str, decision_ts: str, use_vix9d: bool, is_market: bool = False) -> dict[str, Any]:
        required, optional, used_optional = vix_input_rows(session_date)
        required_valid = [r for r in required if r.get("ticker") in ["VIX", "VIX3M"] and r.get("availability_status", "valid") == "valid" and r.get("close", np.nan) == r.get("close", np.nan)]
        timely_required = [r for r in required_valid if timestamp_lte(str(r.get("effective_available_at_utc", "")), decision_ts)]
        required_ok = len(timely_required) == 2
        late_required = any(r.get("availability_status") == "unavailable_coverage" or (r.get("effective_available_at_utc") and not timestamp_lte(str(r.get("effective_available_at_utc")), decision_ts)) for r in required)
        reason = "valid" if required_ok else "late_or_missing_vix_or_vix3m" if late_required else "missing_vix_or_vix3m"
        required_effective = [str(r.get("effective_available_at_utc", "")) for r in timely_required]
        required_conf = [str(r.get("availability_confidence", "")) for r in timely_required]
        all_required_effective = [str(r.get("effective_available_at_utc", "")) for r in required if str(r.get("effective_available_at_utc", "")).strip()]
        required_paths = [str(r.get("source_url_or_path", "")) for r in timely_required if r.get("source_url_or_path")]
        required_hashes = [str(r.get("source_content_hash", "")) for r in timely_required if r.get("source_content_hash")]
        row = {
            "score_target": target,
            "session_date": session_date,
            "decision_timestamp_utc": decision_ts,
            "component_name": "vix_term_structure_stress",
            "input_family": "VIX_REQUIRED",
            "input_tickers": "VIX,VIX3M",
            "input_session_count_required": 2,
            "input_session_count_valid": len(timely_required),
            "input_session_completeness_status": "valid" if required_ok else "unavailable_coverage",
            "input_session_completeness_reason": reason,
            "max_input_effective_available_at_utc": timestamp_max(required_effective if required_ok else all_required_effective),
            "min_input_source_confidence": confidence_min(required_conf) if required_ok else "Unavailable",
            "input_source_path_or_provider_summary": ",".join(sorted(set(required_paths))),
            "input_source_content_hash_summary": ",".join(sorted(set(required_hashes))),
            "lineage_status": "valid" if required_ok else "unavailable_coverage",
            "lineage_reason": reason,
            "is_proxy": False,
            "observed_flow": False,
            "data_type": "observed_market_volatility_index",
        }
        lineage_rows.append(row)
        opt = optional[0] if optional else {}
        opt_valid = bool(use_vix9d and opt.get("ticker") == "VIX9D" and opt.get("availability_status", "valid") == "valid" and timestamp_lte(str(opt.get("effective_available_at_utc", "")), decision_ts))
        opt_row = {
            "score_target": target,
            "session_date": session_date,
            "decision_timestamp_utc": decision_ts,
            "component_name": "vix_term_structure_stress",
            "input_family": "VIX9D_OPTIONAL",
            "input_tickers": "VIX9D",
            "input_session_count_required": 1,
            "input_session_count_valid": 1 if opt_valid else 0,
            "input_session_completeness_status": "valid" if opt_valid else "unavailable_coverage",
            "input_session_completeness_reason": "valid" if opt_valid else "optional_vix9d_unavailable_or_late",
            "max_input_effective_available_at_utc": str(opt.get("effective_available_at_utc", "")) if opt_valid else "",
            "min_input_source_confidence": confidence_min([str(opt.get("availability_confidence", ""))]) if opt_valid else "Unavailable",
            "input_source_path_or_provider_summary": str(opt.get("source_url_or_path", "")) if opt_valid else "",
            "input_source_content_hash_summary": str(opt.get("source_content_hash", "")) if opt_valid else "",
            "lineage_status": "valid" if opt_valid else "unavailable_coverage",
            "lineage_reason": "valid" if opt_valid else "optional_vix9d_unavailable_or_late",
            "is_proxy": False,
            "observed_flow": False,
            "data_type": "observed_market_volatility_index",
        }
        lineage_rows.append(opt_row)
        used_conf = required_conf + ([str(opt.get("availability_confidence", ""))] if opt_valid else [])
        used_eff = (required_effective if required_ok else all_required_effective) + ([str(opt.get("effective_available_at_utc", ""))] if opt_valid else [])
        return {
            "status": "valid" if required_ok else "unavailable_coverage",
            "reason": reason,
            "source_confidence": confidence_min(used_conf) if required_ok else "Unavailable",
            "max_effective": timestamp_max(used_eff),
            "used_vix9d": opt_valid,
        }

    for session_date, vix in vix_by_date.items():
        decision_ts = str(vix.get("decision_timestamp_utc", ""))
        for name in ["VIX", "VIX3M", "VIX9D", "vix_percentile_252", "backwardation", "near_term_stress"]:
            if name not in vix or pd.isna(vix.get(name)):
                continue
            ticker = name if name in VOL_TICKERS else "VIX"
            src = source_rows_by_key.get((ticker, session_date), {})
            feature_rows.append(
                {
                    "score_target": "MARKET",
                    "session_date": session_date,
                    "decision_timestamp_utc": decision_ts,
                    "feature_name": name,
                    "feature_value": vix.get(name),
                    "feature_as_of_timestamp_utc": decision_ts,
                    "effective_available_at_utc": src.get("effective_available_at_utc", ""),
                    "source_path_or_provider": src.get("source_url_or_path", ""),
                    "source_content_hash": src.get("source_content_hash", ""),
                    "availability_status": "valid",
                    "availability_reason": "valid",
                    "is_proxy": False,
                    "observed_flow": False,
                    "data_type": "observed_market_volatility_index",
                }
            )
            feature_audit_rows.append(feature_rows[-1])

    target_components: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for target, df in target_feature_frames.items():
        for row in df.to_dict("records"):
            if not bool(row.get("has_canonical_source", False)):
                continue
            session_date = row["session_date"]
            decision_ts = row["decision_timestamp_utc"]
            src = source_rows_by_key.get((target, session_date), {})
            max_eff = src.get("effective_available_at_utc", "")
            features = {
                "ma20": row.get("ma20"),
                "ma50": row.get("ma50"),
                "ma200": row.get("ma200"),
                "dd63": row.get("dd63"),
                "rv20": row.get("rv20"),
                "rv60": row.get("rv60"),
                "rv20_percentile_252": row.get("rv20_percentile_252"),
                "rv_acceleration": row.get("rv_acceleration"),
                "cta_long_exposure": row.get("cta_long_exposure"),
                "cta_sell_impulse": row.get("cta_sell_impulse"),
                "cta_risk_off_state": row.get("cta_risk_off_state"),
                "vol_control_exposure": row.get("vol_control_exposure"),
                "vol_control_sell_impulse": row.get("vol_control_sell_impulse"),
                "vol_control_stress_state": row.get("vol_control_stress_state"),
            }
            for name, value in features.items():
                is_proxy = name.startswith("cta_") or name.startswith("vol_control_")
                frow = {
                    "score_target": target,
                    "session_date": session_date,
                    "decision_timestamp_utc": decision_ts,
                    "feature_name": name,
                    "feature_value": value,
                    "feature_as_of_timestamp_utc": decision_ts if not pd.isna(value) else "",
                    "effective_available_at_utc": max_eff,
                    "source_path_or_provider": src.get("source_url_or_path", ""),
                    "source_content_hash": src.get("source_content_hash", ""),
                    "availability_status": "valid" if not pd.isna(value) else "unavailable_coverage",
                    "availability_reason": "valid" if not pd.isna(value) else "insufficient_history",
                    "is_proxy": is_proxy,
                    "observed_flow": False,
                    "data_type": "rule_based_systematic_proxy" if is_proxy else "observed_market_daily_price",
                }
                feature_rows.append(frow)
                feature_audit_rows.append(frow)
                violation = bool(max_eff and parse_ts(max_eff) is not None and parse_ts(max_eff) > parse_ts(decision_ts))
                no_lookahead_rows.append(
                    {
                        "score_target": target,
                        "session_date": session_date,
                        "decision_timestamp_utc": decision_ts,
                        "feature_name": name,
                        "component_name": "",
                        "max_input_effective_available_at_utc": max_eff,
                        "no_lookahead_status": "data_quality_blocked" if violation else "valid",
                        "no_lookahead_reason": "future_effective_available_at" if violation else "valid",
                    }
                )

            comps: dict[str, dict[str, Any]] = {}
            trend_lineage = price_lineage(target, session_date, "trend_drawdown_stress", ["ma20", "ma50", "ma200", "dd63"], False, "observed_market_daily_price")
            trend_inputs = [row.get("ma20"), row.get("ma50"), row.get("ma200"), row.get("dd63")]
            if any(pd.isna(x) for x in trend_inputs) or trend_lineage["lineage_status"] != "valid":
                trend = np.nan
                trend_status = "unavailable_coverage"
                trend_reason = "insufficient_history" if trend_lineage["lineage_status"] == "valid" else trend_lineage["lineage_reason"]
            else:
                trend = 100 * (
                    0.20 * float(row["close"] < row["ma20"])
                    + 0.25 * float(row["close"] < row["ma50"])
                    + 0.20 * float(row["close"] < row["ma200"])
                    + 0.35 * clip(row["dd63"] / 0.10)
                )
                trend_status = "valid"
                trend_reason = "valid"
            comps["trend_drawdown_stress"] = {
                "score": trend,
                "status": trend_status,
                "reason": trend_reason,
                "is_proxy": False,
                "data_type": "observed_market_daily_price",
                "source_confidence": trend_lineage["min_input_source_confidence"],
                "max_effective": trend_lineage["max_input_effective_available_at_utc"],
            }
            rv_lineage = price_lineage(target, session_date, "realized_volatility_stress", ["rv20", "rv60", "rv20_percentile_252"], False, "observed_market_daily_price")
            rv_inputs = [row.get("rv20"), row.get("rv60"), row.get("rv20_percentile_252"), row.get("rv_acceleration")]
            if any(pd.isna(x) for x in rv_inputs) or rv_lineage["lineage_status"] != "valid":
                rv_score = np.nan
                rv_status = "unavailable_coverage"
                rv_reason = "insufficient_history" if rv_lineage["lineage_status"] == "valid" else rv_lineage["lineage_reason"]
            else:
                rv_score = 100 * (0.70 * row["rv20_percentile_252"] + 0.30 * row["rv_acceleration"])
                rv_status = "valid"
                rv_reason = "valid"
            comps["realized_volatility_stress"] = {
                "score": rv_score,
                "status": rv_status,
                "reason": rv_reason,
                "is_proxy": False,
                "data_type": "observed_market_daily_price",
                "source_confidence": rv_lineage["min_input_source_confidence"],
                "max_effective": rv_lineage["max_input_effective_available_at_utc"],
            }
            cta_lineage = price_lineage(target, session_date, "cta_deleveraging_proxy", ["r20", "r60", "r120", "r252", "rv20"], True, "rule_based_systematic_proxy")
            cta_inputs = [row.get("r20"), row.get("r60"), row.get("r120"), row.get("r252"), row.get("rv20"), row.get("cta_sell_impulse")]
            if any(pd.isna(x) for x in cta_inputs) or cta_lineage["lineage_status"] != "valid":
                cta = np.nan
                cta_status = "unavailable_coverage"
                cta_reason = "insufficient_history" if cta_lineage["lineage_status"] == "valid" else cta_lineage["lineage_reason"]
            else:
                cta = 100 * (0.70 * row["cta_sell_impulse"] + 0.30 * row["cta_risk_off_state"])
                cta_status = "valid"
                cta_reason = "valid"
            comps["cta_deleveraging_proxy"] = {
                "score": cta,
                "status": cta_status,
                "reason": cta_reason,
                "is_proxy": True,
                "data_type": "rule_based_systematic_proxy",
                "source_confidence": cta_lineage["min_input_source_confidence"],
                "max_effective": cta_lineage["max_input_effective_available_at_utc"],
            }
            vc_lineage = price_lineage(target, session_date, "vol_control_deleveraging_proxy", ["rv20"], True, "rule_based_systematic_proxy")
            vc_inputs = [row.get("rv20"), row.get("vol_control_sell_impulse"), row.get("vol_control_stress_state")]
            if any(pd.isna(x) for x in vc_inputs) or vc_lineage["lineage_status"] != "valid":
                vc = np.nan
                vc_status = "unavailable_coverage"
                vc_reason = "insufficient_history" if vc_lineage["lineage_status"] == "valid" else vc_lineage["lineage_reason"]
            else:
                vc = 100 * (0.65 * row["vol_control_sell_impulse"] + 0.35 * row["vol_control_stress_state"])
                vc_status = "valid"
                vc_reason = "valid"
            comps["vol_control_deleveraging_proxy"] = {
                "score": vc,
                "status": vc_status,
                "reason": vc_reason,
                "is_proxy": True,
                "data_type": "rule_based_systematic_proxy",
                "source_confidence": vc_lineage["min_input_source_confidence"],
                "max_effective": vc_lineage["max_input_effective_available_at_utc"],
            }
            vix = vix_by_date.get(session_date, {})
            vix_use_9d = "near_term_stress" in vix and not pd.isna(vix.get("near_term_stress"))
            vix_lin = vix_lineage(target, session_date, decision_ts, vix_use_9d)
            if vix_lin["status"] != "valid" or "backwardation" not in vix or pd.isna(vix.get("backwardation")) or pd.isna(vix.get("vix_percentile_252")):
                vix_score = np.nan
                vix_status = "unavailable_coverage"
                vix_reason = vix_lin["reason"] if vix_lin["status"] != "valid" else "missing_vix_or_vix3m"
            elif vix_use_9d and vix_lin["used_vix9d"]:
                vix_score = 100 * (0.55 * vix["backwardation"] + 0.25 * vix["vix_percentile_252"] + 0.20 * vix["near_term_stress"])
                vix_status = "valid"
                vix_reason = "valid_with_vix9d"
            else:
                vix_score = 100 * (0.70 * vix["backwardation"] + 0.30 * vix["vix_percentile_252"])
                vix_status = "valid"
                vix_reason = "valid_without_vix9d"
            comps["vix_term_structure_stress"] = {
                "score": vix_score,
                "status": vix_status,
                "reason": vix_reason,
                "is_proxy": False,
                "data_type": "observed_market_volatility_index",
                "source_confidence": vix_lin["source_confidence"],
                "max_effective": vix_lin["max_effective"],
            }
            target_components[(target, session_date)] = comps
            source_conf = row_source_confidence(canonical[(canonical["ticker"] == target) & (canonical["session_date"] == session_date)])
            for cname, comp in comps.items():
                max_input_eff = comp.get("max_effective", max_eff)
                nl_blocked = bool(max_input_eff and parse_ts(max_input_eff) is not None and parse_ts(max_input_eff) > parse_ts(decision_ts))
                no_lookahead_rows.append(
                    {
                        "score_target": target,
                        "session_date": session_date,
                        "decision_timestamp_utc": decision_ts,
                        "feature_name": "",
                        "component_name": cname,
                        "max_input_effective_available_at_utc": max_input_eff,
                        "no_lookahead_status": "data_quality_blocked" if nl_blocked else "valid",
                        "no_lookahead_reason": "future_effective_available_at" if nl_blocked else "valid",
                    }
                )
                component_rows.append(
                    {
                        "score_target": target,
                        "session_date": session_date,
                        "decision_timestamp_utc": decision_ts,
                        "component_name": cname,
                        "component_score": comp["score"],
                        "nominal_weight": COMPONENT_WEIGHTS[cname],
                        "component_available": comp["status"] == "valid",
                        "component_status": comp["status"],
                        "component_reason": comp["reason"],
                        "source_confidence": comp.get("source_confidence", source_conf) if comp["status"] == "valid" else "Unavailable",
                        "is_proxy": comp["is_proxy"],
                        "observed_flow": False,
                        "data_type": comp["data_type"],
                        "feature_as_of_timestamp_utc": decision_ts if comp["status"] == "valid" else "",
                        "effective_available_at_utc": max_input_eff,
                    }
                )

    # MARKET components are an explicit SPY/QQQ aggregation.
    for session_date in sorted(set(canonical["session_date"])):
        spy = target_components.get(("SPY", session_date), {})
        qqq = target_components.get(("QQQ", session_date), {})
        if not spy or not qqq:
            continue
        decision_ts = canonical[canonical["session_date"] == session_date]["decision_timestamp_utc"].iloc[0]
        market_comps: dict[str, dict[str, Any]] = {}
        for cname in COMPONENTS:
            s = spy.get(cname, {})
            q = qqq.get(cname, {})
            if s.get("status") == "valid" and q.get("status") == "valid":
                score = 0.55 * s["score"] + 0.45 * q["score"]
                status = "valid"
                reason = "spy_qqq_weighted_aggregation"
                source_confidence = confidence_min([str(s.get("source_confidence", "")), str(q.get("source_confidence", ""))])
                max_effective = timestamp_max([str(s.get("max_effective", "")), str(q.get("max_effective", ""))])
            else:
                score = np.nan
                status = "unavailable_coverage"
                reason = "requires_spy_and_qqq_component"
                source_confidence = "Unavailable"
                max_effective = ""
            market_comps[cname] = {
                "score": score,
                "status": status,
                "reason": reason,
                "is_proxy": s.get("is_proxy", False),
                "data_type": s.get("data_type", ""),
                "source_confidence": source_confidence,
                "max_effective": max_effective,
            }
            for family, ticker, comp in [("MARKET_SPY_COMPONENT", "SPY", s), ("MARKET_QQQ_COMPONENT", "QQQ", q)]:
                lineage_rows.append(
                    {
                        "score_target": "MARKET",
                        "session_date": session_date,
                        "decision_timestamp_utc": decision_ts,
                        "component_name": cname,
                        "input_family": family,
                        "input_tickers": ticker,
                        "input_session_count_required": 1,
                        "input_session_count_valid": 1 if comp.get("status") == "valid" else 0,
                        "input_session_completeness_status": "valid" if comp.get("status") == "valid" else "unavailable_coverage",
                        "input_session_completeness_reason": comp.get("reason", "missing_component"),
                        "max_input_effective_available_at_utc": comp.get("max_effective", ""),
                        "min_input_source_confidence": comp.get("source_confidence", "Unavailable") if comp.get("status") == "valid" else "Unavailable",
                        "input_source_path_or_provider_summary": "",
                        "input_source_content_hash_summary": "",
                        "lineage_status": "valid" if comp.get("status") == "valid" else "unavailable_coverage",
                        "lineage_reason": comp.get("reason", "missing_component"),
                        "is_proxy": comp.get("is_proxy", False),
                        "observed_flow": False,
                        "data_type": comp.get("data_type", ""),
                    }
                )
            nl_blocked = bool(max_effective and parse_ts(max_effective) is not None and parse_ts(max_effective) > parse_ts(decision_ts))
            no_lookahead_rows.append(
                {
                    "score_target": "MARKET",
                    "session_date": session_date,
                    "decision_timestamp_utc": decision_ts,
                    "feature_name": "",
                    "component_name": cname,
                    "max_input_effective_available_at_utc": max_effective,
                    "no_lookahead_status": "data_quality_blocked" if nl_blocked else "valid",
                    "no_lookahead_reason": "future_effective_available_at" if nl_blocked else "valid",
                }
            )
            component_rows.append(
                {
                    "score_target": "MARKET",
                    "session_date": session_date,
                    "decision_timestamp_utc": decision_ts,
                    "component_name": cname,
                    "component_score": score,
                    "nominal_weight": COMPONENT_WEIGHTS[cname],
                    "component_available": status == "valid",
                    "component_status": status,
                    "component_reason": reason,
                    "source_confidence": source_confidence,
                    "is_proxy": s.get("is_proxy", False),
                    "observed_flow": False,
                    "data_type": s.get("data_type", ""),
                    "feature_as_of_timestamp_utc": decision_ts if status == "valid" else "",
                    "effective_available_at_utc": max_effective,
                }
            )
        target_components[("MARKET", session_date)] = market_comps

    component_df = pd.DataFrame(component_rows, columns=COMPONENT_SCORE_COLUMNS)
    for (target, session_date), comps in target_components.items():
        comp_confidences = [str(c.get("source_confidence", "")) for c in comps.values() if c.get("status") == "valid"]
        source_summary = confidence_min(comp_confidences)
        warning_count = int(any(confidence_rank(c) < confidence_rank("high") for c in comp_confidences))
        if target != "MARKET":
            src_rows = canonical[(canonical["ticker"] == target) & (canonical["session_date"] == session_date)]
            if src_rows.empty:
                continue
            decision_ts = src_rows["decision_timestamp_utc"].iloc[0]
        else:
            match = canonical[canonical["session_date"] == session_date]
            if match.empty:
                continue
            decision_ts = match["decision_timestamp_utc"].iloc[0]
        missing = [c for c in COMPONENTS if comps.get(c, {}).get("status") != "valid"]
        core_missing = [c for c in CORE_COMPONENTS if comps.get(c, {}).get("status") != "valid"]
        if core_missing:
            score = np.nan
            status = "unavailable_core_component"
            risk_state = "Unavailable"
            available_weight = sum(COMPONENT_WEIGHTS[c] for c in COMPONENTS if comps.get(c, {}).get("status") == "valid")
            coverage = available_weight
            confidence = "Unavailable"
        else:
            available_weight = sum(COMPONENT_WEIGHTS[c] for c in COMPONENTS if comps.get(c, {}).get("status") == "valid")
            denom = available_weight
            score = sum(COMPONENT_WEIGHTS[c] * comps[c]["score"] for c in COMPONENTS if comps[c]["status"] == "valid") / denom
            coverage = available_weight
            status = "valid"
            risk_state = risk_state_for_score(score)
            if missing:
                confidence = "Medium"
            elif source_summary == "High" and warning_count == 0:
                confidence = "High"
            else:
                confidence = "Medium"
        score_rows.append(
            {
                "score_target": target,
                "session_date": session_date,
                "decision_timestamp_utc": decision_ts,
                "fragility_score": score,
                "score_status": status,
                "risk_state": risk_state,
                "confidence": confidence,
                "data_coverage_pct": coverage,
                "available_nominal_weight": available_weight,
                "missing_components": ",".join(missing),
                "component_source_confidence_summary": source_summary,
                "availability_warning_count": warning_count,
                "trend_drawdown_stress": comps.get("trend_drawdown_stress", {}).get("score", np.nan),
                "realized_volatility_stress": comps.get("realized_volatility_stress", {}).get("score", np.nan),
                "cta_deleveraging_proxy": comps.get("cta_deleveraging_proxy", {}).get("score", np.nan),
                "vol_control_deleveraging_proxy": comps.get("vol_control_deleveraging_proxy", {}).get("score", np.nan),
                "vix_term_structure_stress": comps.get("vix_term_structure_stress", {}).get("score", np.nan),
                "actionization_allowed": ACTIONIZATION_ALLOWED,
                "score_policy_revision": SCORE_POLICY_REVISION,
            }
        )

    return (
        pd.DataFrame(feature_rows, columns=FEATURE_PANEL_COLUMNS),
        pd.DataFrame(feature_audit_rows, columns=FEATURE_PANEL_COLUMNS),
        pd.DataFrame(no_lookahead_rows, columns=NO_LOOKAHEAD_COLUMNS),
        pd.DataFrame(lineage_rows, columns=COMPONENT_INPUT_LINEAGE_COLUMNS),
        lookback_audit,
        component_df,
        pd.DataFrame(score_rows, columns=SCORE_PANEL_COLUMNS).sort_values(["score_target", "session_date"]).reset_index(drop=True),
    )


def risk_state_for_score(score: float) -> str:
    if pd.isna(score):
        return "Unavailable"
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "Elevated"
    return "High"


def add_oos(score_panel: pd.DataFrame, canonical: pd.DataFrame, calendar: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    band_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    if score_panel.empty or canonical.empty:
        for target in PRICE_TICKERS:
            summary_rows.append(empty_oos_summary(target, "insufficient_data", "empty_score_or_price_panel"))
        return (
            pd.DataFrame(rows, columns=OOS_PANEL_COLUMNS),
            pd.DataFrame(fold_rows),
            pd.DataFrame(band_rows),
            pd.DataFrame(summary_rows, columns=OOS_SUMMARY_COLUMNS),
        )
    feature_frames = {t: compute_target_features(t, canonical, calendar) for t in PRICE_TICKERS}
    score_by_key = {
        (row["score_target"], row["session_date"]): row for row in score_panel.to_dict("records") if row["score_target"] in PRICE_TICKERS
    }
    for target, prices in feature_frames.items():
        prices = prices.sort_values("session_date").reset_index(drop=True)
        closes = prices["close"].astype(float)
        log_ret = np.log(closes / closes.shift(1))
        for idx, row in prices.iterrows():
            if not bool(row.get("has_canonical_source", False)):
                continue
            score = score_by_key.get((target, row["session_date"]))
            if not score:
                continue
            reasons: list[str] = []
            if score["score_status"] != "valid":
                reasons.append("score_status_not_available")
            if idx < 252:
                reasons.append("less_than_252_prior_sessions")
            if idx + 10 >= len(prices):
                reasons.append("future_outcome_window_missing")
            else:
                future10 = prices.iloc[idx + 1 : idx + 11]
                if future10["close"].isna().any():
                    reasons.append("future_outcome_calendar_session_missing")
            eligible = not reasons
            out: dict[str, Any] = {
                "score_target": target,
                "session_date": row["session_date"],
                "decision_timestamp_utc": row["decision_timestamp_utc"],
                "fragility_score": score["fragility_score"],
                "risk_state": score["risk_state"],
                "score_band": risk_state_for_score(score["fragility_score"]),
                "oos_eligible": eligible,
                "oos_reason": "valid" if eligible else ";".join(reasons),
                "fold_month": str(row["session_date"])[:7],
                "rv20_at_t": row.get("rv20"),
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
            for h in [5, 10]:
                if idx + h < len(prices):
                    future = closes.iloc[idx + 1 : idx + h + 1]
                    ret_slice = log_ret.iloc[idx + 1 : idx + h + 1]
                    if future.isna().any() or pd.isna(closes.iloc[idx]):
                        out[f"forward_close_return_{h}d"] = np.nan
                        out[f"forward_realized_vol_{h}d"] = np.nan
                        out[f"forward_close_to_close_drawdown_{h}d"] = np.nan
                        out[f"forward_tail_flag_{h}d"] = np.nan
                    else:
                        out[f"forward_close_return_{h}d"] = closes.iloc[idx + h] / closes.iloc[idx] - 1
                        out[f"forward_realized_vol_{h}d"] = ret_slice.std(ddof=1) * math.sqrt(252)
                        out[f"forward_close_to_close_drawdown_{h}d"] = float((future / closes.iloc[idx] - 1).min())
                        threshold = -1.5 * row.get("rv20", np.nan) * math.sqrt(h / 252)
                        out[f"forward_tail_flag_{h}d"] = int(out[f"forward_close_to_close_drawdown_{h}d"] <= threshold) if not pd.isna(threshold) else np.nan
                else:
                    out[f"forward_close_return_{h}d"] = np.nan
                    out[f"forward_realized_vol_{h}d"] = np.nan
                    out[f"forward_close_to_close_drawdown_{h}d"] = np.nan
                    out[f"forward_tail_flag_{h}d"] = np.nan
            rows.append(out)
    panel = pd.DataFrame(rows, columns=OOS_PANEL_COLUMNS)
    for target in PRICE_TICKERS:
        tdf = panel[(panel["score_target"] == target) & (panel["oos_eligible"] == True)].copy()
        folds = tdf.groupby("fold_month").size() if not tdf.empty else pd.Series(dtype=int)
        for month, count in folds.items():
            fold_rows.append({"score_target": target, "fold_month": month, "oos_observation_count": int(count), "fold_status": "valid"})
        for band in ["Low", "Moderate", "Elevated", "High"]:
            bdf = tdf[tdf["score_band"] == band]
            band_rows.append(
                {
                    "score_target": target,
                    "score_band": band,
                    "oos_observation_count": len(bdf),
                    "mean_forward_realized_vol_5d": bdf["forward_realized_vol_5d"].mean() if not bdf.empty else np.nan,
                    "median_forward_realized_vol_5d": bdf["forward_realized_vol_5d"].median() if not bdf.empty else np.nan,
                    "mean_forward_realized_vol_10d": bdf["forward_realized_vol_10d"].mean() if not bdf.empty else np.nan,
                    "median_forward_realized_vol_10d": bdf["forward_realized_vol_10d"].median() if not bdf.empty else np.nan,
                    "mean_forward_close_to_close_drawdown_5d": bdf["forward_close_to_close_drawdown_5d"].mean() if not bdf.empty else np.nan,
                    "median_forward_close_to_close_drawdown_5d": bdf["forward_close_to_close_drawdown_5d"].median() if not bdf.empty else np.nan,
                    "mean_forward_close_to_close_drawdown_10d": bdf["forward_close_to_close_drawdown_10d"].mean() if not bdf.empty else np.nan,
                    "median_forward_close_to_close_drawdown_10d": bdf["forward_close_to_close_drawdown_10d"].median() if not bdf.empty else np.nan,
                    "forward_tail_rate_5d": bdf["forward_tail_flag_5d"].mean() if not bdf.empty else np.nan,
                    "forward_tail_rate_10d": bdf["forward_tail_flag_10d"].mean() if not bdf.empty else np.nan,
                }
            )
        if len(tdf) < 100 or len(folds) < 3:
            summary_rows.append(empty_oos_summary(target, "insufficient_data", "minimum_observation_or_fold_threshold_not_met", len(tdf), len(folds)))
            continue
        low = tdf[tdf["score_band"] == "Low"]
        high = tdf[tdf["score_band"] == "High"]
        summary_rows.append(
            {
                "score_target": target,
                "valid_oos_observation_count": len(tdf),
                "non_empty_fold_count": len(folds),
                "score_vs_forward_rv5_spearman": spearman_corr(tdf["fragility_score"], tdf["forward_realized_vol_5d"]),
                "score_vs_forward_rv10_spearman": spearman_corr(tdf["fragility_score"], tdf["forward_realized_vol_10d"]),
                "score_vs_drawdown5_spearman": spearman_corr(tdf["fragility_score"], tdf["forward_close_to_close_drawdown_5d"]),
                "score_vs_drawdown10_spearman": spearman_corr(tdf["fragility_score"], tdf["forward_close_to_close_drawdown_10d"]),
                "high_minus_low_forward_rv5": high["forward_realized_vol_5d"].mean() - low["forward_realized_vol_5d"].mean() if not high.empty and not low.empty else np.nan,
                "high_minus_low_tail_rate_5d": high["forward_tail_flag_5d"].mean() - low["forward_tail_flag_5d"].mean() if not high.empty and not low.empty else np.nan,
                "high_minus_low_drawdown5": high["forward_close_to_close_drawdown_5d"].mean() - low["forward_close_to_close_drawdown_5d"].mean() if not high.empty and not low.empty else np.nan,
                "evidence_status": "descriptive_only",
                "interpretation_caveat": OOS_CAVEAT,
            }
        )
    return pd.DataFrame(rows, columns=OOS_PANEL_COLUMNS), pd.DataFrame(fold_rows), pd.DataFrame(band_rows), pd.DataFrame(summary_rows, columns=OOS_SUMMARY_COLUMNS)


def empty_oos_summary(target: str, status: str, reason: str, obs: int = 0, folds: int = 0) -> dict[str, Any]:
    return {
        "score_target": target,
        "valid_oos_observation_count": obs,
        "non_empty_fold_count": folds,
        "score_vs_forward_rv5_spearman": np.nan,
        "score_vs_forward_rv10_spearman": np.nan,
        "score_vs_drawdown5_spearman": np.nan,
        "score_vs_drawdown10_spearman": np.nan,
        "high_minus_low_forward_rv5": np.nan,
        "high_minus_low_tail_rate_5d": np.nan,
        "high_minus_low_drawdown5": np.nan,
        "evidence_status": status,
        "interpretation_caveat": f"{OOS_CAVEAT} Reason: {reason}",
    }


def unavailable_score_row(target: str, session_date: str, decision_ts: str, reason: str, coverage: float = 0.0) -> dict[str, Any]:
    return {
        "score_target": target,
        "session_date": session_date,
        "decision_timestamp_utc": decision_ts,
        "fragility_score": np.nan,
        "score_status": "requested_as_of_unavailable",
        "risk_state": "Unavailable",
        "confidence": "Unavailable",
        "data_coverage_pct": coverage,
        "available_nominal_weight": coverage,
        "missing_components": ",".join(COMPONENTS),
        "component_source_confidence_summary": "Unavailable",
        "availability_warning_count": 1,
        "trend_drawdown_stress": np.nan,
        "realized_volatility_stress": np.nan,
        "cta_deleveraging_proxy": np.nan,
        "vol_control_deleveraging_proxy": np.nan,
        "vix_term_structure_stress": np.nan,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "score_policy_revision": SCORE_POLICY_REVISION,
        "as_of_resolution_reason": reason,
    }


def latest_score(score_panel: pd.DataFrame, as_of_date: str | None, calendar: pd.DataFrame | None = None) -> pd.DataFrame:
    if score_panel.empty and not as_of_date:
        return pd.DataFrame(columns=SCORE_PANEL_COLUMNS)
    df = score_panel.copy()
    if as_of_date:
        rows: list[dict[str, Any]] = []
        cal_row = calendar[calendar["session_date"] == as_of_date] if calendar is not None and not calendar.empty else pd.DataFrame()
        decision_ts = "" if cal_row.empty else cal_row.iloc[0]["decision_timestamp_utc"]
        for target in TARGETS:
            exact = df[(df["score_target"] == target) & (df["session_date"] == as_of_date)] if not df.empty else pd.DataFrame()
            if exact.empty:
                rows.append(unavailable_score_row(target, as_of_date, decision_ts, "no_exact_score_row"))
            else:
                row = exact.iloc[-1].to_dict()
                if row.get("score_status") == "valid":
                    rows.append(row)
                else:
                    coverage = float(row.get("data_coverage_pct", 0) or 0)
                    rows.append(unavailable_score_row(target, as_of_date, decision_ts, str(row.get("score_status", "score_unavailable")), coverage))
        return pd.DataFrame(rows, columns=SCORE_PANEL_COLUMNS + ["as_of_resolution_reason"]).reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=SCORE_PANEL_COLUMNS)
    idx = df.sort_values("session_date").groupby("score_target").tail(1).index
    return df.loc[idx].sort_values("score_target").reset_index(drop=True)


def build_latest_json(latest: pd.DataFrame, requested_as_of_date: str | None, as_of_audit: pd.DataFrame | None = None) -> dict[str, Any]:
    asof_summary = {}
    if as_of_audit is not None and not as_of_audit.empty:
        asof_summary = {
            row["score_target"]: {
                "status": row["as_of_resolution_status"],
                "reason": row["as_of_resolution_reason"],
                "resolved_session_date": row["resolved_session_date"],
            }
            for row in as_of_audit.to_dict("records")
        }
    payload: dict[str, Any] = {
        "generated_at_utc": iso_utc(pd.Timestamp.now(tz="UTC")),
        "requested_as_of_date": requested_as_of_date,
        "latest_available_session_date": "" if latest.empty else str(latest["session_date"].max()),
        "latest_selection_policy": AS_OF_SELECTION_POLICY if requested_as_of_date else "latest_available_per_target_v0_1_1",
        "as_of_resolution_summary": asof_summary,
        "score_decision_time_policy": SCORE_DECISION_TIME_POLICY,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    for target in TARGETS:
        row = latest[latest["score_target"] == target]
        if row.empty:
            payload[target] = {
                "score": None,
                "risk_state": "Unavailable",
                "confidence": "Unavailable",
                "coverage": 0,
                "components": {},
                "missing_components": COMPONENTS,
                "warnings": ["no_latest_score"],
            }
        else:
            r = row.iloc[0].to_dict()
            payload[target] = {
                "score": None if pd.isna(r["fragility_score"]) else float(r["fragility_score"]),
                "risk_state": r["risk_state"],
                "confidence": r["confidence"],
                "coverage": float(r["data_coverage_pct"]),
                "components": {c: None if pd.isna(r[c]) else float(r[c]) for c in COMPONENTS},
                "missing_components": [x for x in str(r["missing_components"]).split(",") if x],
                "warnings": [str(r.get("as_of_resolution_reason", ""))] if requested_as_of_date and r.get("score_status") == "requested_as_of_unavailable" else ([] if int(r["availability_warning_count"]) == 0 else ["policy_assumed_or_non_high_confidence_source"]),
            }
    return payload


def markdown_table(df: pd.DataFrame, columns: list[str] | None = None, limit: int = 20) -> str:
    if columns:
        df = df[columns]
    if df.empty:
        return "_No rows._"
    d = df.head(limit).fillna("")
    lines = ["| " + " | ".join(d.columns) + " |", "| " + " | ".join(["---"] * len(d.columns)) + " |"]
    for row in d.astype(str).to_dict("records"):
        lines.append("| " + " | ".join(row[c] for c in d.columns) + " |")
    return "\n".join(lines)


def write_dashboard(out: Path, latest: pd.DataFrame, component_df: pd.DataFrame, oos_summary: pd.DataFrame, as_of_audit: pd.DataFrame | None = None) -> None:
    market = latest[latest["score_target"] == "MARKET"]
    market_text = "Unavailable"
    if not market.empty:
        r = market.iloc[0]
        score = "NaN" if pd.isna(r["fragility_score"]) else f"{r['fragility_score']:.2f}"
        market_text = f"{score} / {r['risk_state']} / {r['confidence']} / coverage {r['data_coverage_pct']:.0f}%"
    text = [
        "# Market Fragility Score v0.1 Dashboard",
        "",
        f"- Latest MARKET score: {market_text}",
        f"- Actionization allowed: {str(ACTIONIZATION_ALLOWED).lower()}",
        f"- Latest selection policy: {AS_OF_SELECTION_POLICY if as_of_audit is not None and not as_of_audit.empty and str(as_of_audit.iloc[0].get('requested_as_of_date', '')).strip() else 'latest_available_per_target_v0_1_1'}",
        "- Caveat: rule-based proxies, no Gamma or Leveraged ETF component, no calibration, no trade action.",
    ]
    if as_of_audit is not None and not as_of_audit.empty and str(as_of_audit.iloc[0].get("requested_as_of_date", "")).strip():
        status_summary = ",".join(sorted(set(as_of_audit["as_of_resolution_status"].astype(str))))
        text += [
            f"- Requested as-of: {as_of_audit.iloc[0]['requested_as_of_date']}",
            f"- Resolution: {status_summary}",
            "- No prior score was substituted.",
        ]
        if "requested_as_of_unavailable" in status_summary:
            text.append("- Requested session unavailable.")
    text += [
        "",
        "## Latest Scores",
        markdown_table(latest, ["score_target", "session_date", "fragility_score", "risk_state", "confidence", "data_coverage_pct", "missing_components"]),
        "",
        "## Latest Components",
        markdown_table(component_df.sort_values(["score_target", "session_date"]).groupby(["score_target", "component_name"]).tail(1), ["score_target", "component_name", "component_score", "component_status", "component_reason", "is_proxy", "observed_flow"]),
        "",
        "## OOS Descriptive Status",
        markdown_table(oos_summary),
        "",
        "## Caveats",
        "- CTA and VolControl are rule-based market proxies, not observed fund flow.",
        "- VIX term structure is observed market-volatility input, not dealer positioning.",
        "- Fragility Score is a predeclared research rubric, not a probability of loss.",
        "- OOS is descriptive only and does not authorize actionization.",
        "- VIX/VIX3M source lineage, confidence, and availability are separately audited.",
        "- Policy-assumed VIX availability cannot produce High confidence.",
        "- Requested as-of dates never silently resolve to prior scores.",
        "- Rolling features and future labels require consecutive NYSE calendar sessions.",
        "- Duplicate raw keys are invalidated and reconciled across artifacts.",
    ]
    (out / "fragility_score_dashboard_v0.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    (out / "fragility_score_report_v0.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def build_data_quality_audit(raw_audit: pd.DataFrame, availability: pd.DataFrame, no_lookahead: pd.DataFrame, score_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rows.append({"audit_name": "raw_input_selected_invalid", "status": "valid" if raw_audit.empty or not (raw_audit["raw_input_status"] == "selected_invalid").any() else "data_quality_warning", "count": int((raw_audit["raw_input_status"] == "selected_invalid").sum()) if not raw_audit.empty else 0})
    rows.append({"audit_name": "future_availability", "status": "valid" if availability.empty or not (availability["availability_status"] == "unavailable_coverage").any() else "data_quality_warning", "count": int((availability["availability_status"] == "unavailable_coverage").sum()) if not availability.empty else 0})
    rows.append({"audit_name": "no_lookahead", "status": "valid" if no_lookahead.empty or not (no_lookahead["no_lookahead_status"] == "data_quality_blocked").any() else "data_quality_blocked", "count": int((no_lookahead["no_lookahead_status"] == "data_quality_blocked").sum()) if not no_lookahead.empty else 0})
    rows.append({"audit_name": "unavailable_core_score", "status": "valid" if score_panel.empty or not (score_panel["score_status"] == "unavailable_core_component").any() else "unavailable_coverage", "count": int((score_panel["score_status"] == "unavailable_core_component").sum()) if not score_panel.empty else 0})
    return pd.DataFrame(rows)


def build_raw_reconciliation_audit(inventory: pd.DataFrame, raw_audit: pd.DataFrame, availability: pd.DataFrame, canonical: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in ALL_TICKERS:
        inv = inventory[inventory["ticker"] == ticker]
        raw_valid_keys = [
            (ticker, row["canonical_session_date"])
            for row in raw_audit[(raw_audit["ticker"] == ticker) & (raw_audit["raw_input_status"] == "valid")].to_dict("records")
            if str(row.get("canonical_session_date", "")).strip()
        ] if not raw_audit.empty else []
        availability_valid_keys = [
            (ticker, row["session_date"])
            for row in availability[(availability["ticker"] == ticker) & (availability["availability_status"] == "valid")].to_dict("records")
        ] if not availability.empty else []
        canonical_valid_keys = [
            (ticker, row["session_date"])
            for row in canonical[canonical["ticker"] == ticker].to_dict("records")
        ] if not canonical.empty else []
        clean = set(raw_valid_keys) == set(availability_valid_keys) == set(canonical_valid_keys)
        rows.append(
            {
                "ticker": ticker,
                "raw_row_count": int(inv.iloc[0]["raw_row_count"]) if not inv.empty else 0,
                "raw_valid_before_duplicate_resolution_count": int(inv.iloc[0]["provisional_valid_row_count"]) if not inv.empty else 0,
                "raw_selected_invalid_final_count": int(inv.iloc[0]["selected_invalid_row_count"]) if not inv.empty else 0,
                "availability_valid_final_count": len(set(availability_valid_keys)),
                "canonical_valid_final_count": len(set(canonical_valid_keys)),
                "raw_valid_key_set_sha256": key_set_sha256(raw_valid_keys),
                "availability_valid_key_set_sha256": key_set_sha256(availability_valid_keys),
                "canonical_valid_key_set_sha256": key_set_sha256(canonical_valid_keys),
                "raw_availability_canonical_reconciliation_status": "valid" if clean else "data_quality_blocked",
                "raw_availability_canonical_reconciliation_reason": "valid" if clean else "raw_availability_canonical_valid_key_set_mismatch",
            }
        )
    return pd.DataFrame(rows, columns=RAW_RECONCILIATION_COLUMNS)


def build_as_of_request_audit(as_of_date: str | None, calendar: pd.DataFrame, universe: pd.DataFrame, score_panel: pd.DataFrame, latest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not as_of_date:
        for target in TARGETS:
            rows.append(
                {
                    "requested_as_of_date": "",
                    "score_target": target,
                    "requested_calendar_session_exists": "",
                    "requested_session_date": "",
                    "requested_decision_timestamp_utc": "",
                    "required_source_input_status": "",
                    "core_component_status": "",
                    "score_row_exists": "",
                    "score_status": "",
                    "as_of_resolution_status": "no_as_of_requested",
                    "as_of_resolution_reason": "latest_available_per_target",
                    "resolved_session_date": "",
                    "resolved_decision_timestamp_utc": "",
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
        return pd.DataFrame(rows, columns=AS_OF_REQUEST_AUDIT_COLUMNS)
    cal_row = calendar[calendar["session_date"] == as_of_date] if not calendar.empty else pd.DataFrame()
    exists = not cal_row.empty
    decision_ts = "" if cal_row.empty else cal_row.iloc[0]["decision_timestamp_utc"]
    for target in TARGETS:
        u = universe[(universe["score_target"] == target) & (universe["session_date"] == as_of_date)] if not universe.empty else pd.DataFrame()
        s = score_panel[(score_panel["score_target"] == target) & (score_panel["session_date"] == as_of_date)] if not score_panel.empty else pd.DataFrame()
        l = latest[latest["score_target"] == target] if not latest.empty else pd.DataFrame()
        score_status = "" if s.empty else str(s.iloc[-1]["score_status"])
        row_exists = not s.empty
        exact_valid = row_exists and score_status == "valid"
        status = "exact_score_available" if exact_valid else "requested_as_of_unavailable"
        if not exists:
            status = "requested_as_of_invalid_calendar_date"
        reason = "valid" if exact_valid else ("invalid_calendar_date" if not exists else (score_status or ("no_exact_score_row" if s.empty else "score_unavailable")))
        rows.append(
            {
                "requested_as_of_date": as_of_date,
                "score_target": target,
                "requested_calendar_session_exists": exists,
                "requested_session_date": as_of_date if exists else "",
                "requested_decision_timestamp_utc": decision_ts,
                "required_source_input_status": "" if u.empty else str(u.iloc[-1]["universe_status"]),
                "core_component_status": "valid" if exact_valid else "unavailable",
                "score_row_exists": row_exists,
                "score_status": score_status,
                "as_of_resolution_status": status,
                "as_of_resolution_reason": reason,
                "resolved_session_date": str(l.iloc[0]["session_date"]) if exact_valid and not l.empty else "",
                "resolved_decision_timestamp_utc": str(l.iloc[0]["decision_timestamp_utc"]) if exact_valid and not l.empty else "",
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
        )
    return pd.DataFrame(rows, columns=AS_OF_REQUEST_AUDIT_COLUMNS)


def run(root: Path, input_root: Path, output_root: Path, as_of_date: str | None = None, strict: bool = False) -> dict[str, Any]:
    config_dir = root / "market_bomb_config"
    rules = load_json(config_dir / "fragility_score_v0_rules.json", {})
    sources = load_json(config_dir / "fragility_score_v0_sources.json", {})
    output_root.mkdir(parents=True, exist_ok=True)
    calendar = load_calendar(root)
    invalid_as_of = bool(as_of_date and as_of_date not in set(calendar["session_date"] if not calendar.empty else []))
    inventory, raw_audit, availability, canonical = ingest_raw_sources(root, input_root, calendar)
    if as_of_date and not canonical.empty:
        canonical = canonical[canonical["session_date"] <= as_of_date].copy()
        availability = availability[availability["session_date"] <= as_of_date].copy()
    if as_of_date:
        active_calendar = calendar[calendar["session_date"] <= as_of_date].copy()
    elif not canonical.empty:
        active_calendar = calendar[calendar["session_date"] <= str(canonical["session_date"].max())].copy()
    else:
        active_calendar = calendar.copy()
    universe = build_decision_universe(canonical, active_calendar)
    feature_panel, feature_audit, no_lookahead, component_lineage, lookback_audit, component_scores, score_panel = build_feature_and_scores(canonical, universe, availability)
    oos_panel, oos_fold, oos_band, oos_summary = add_oos(score_panel, canonical, active_calendar)
    latest = latest_score(score_panel, as_of_date, calendar)
    raw_reconciliation = build_raw_reconciliation_audit(inventory, raw_audit, availability, canonical)
    as_of_audit = build_as_of_request_audit(as_of_date, calendar, universe, score_panel, latest)
    data_quality = build_data_quality_audit(raw_audit, availability, no_lookahead, score_panel)

    write_table(inventory, output_root / "fragility_raw_source_inventory_v0.csv")
    write_table(raw_audit, output_root / "fragility_raw_input_audit_v0.csv")
    write_table(calendar, output_root / "fragility_daily_calendar_audit_v0.csv")
    write_table(availability, output_root / "fragility_daily_availability_audit_v0.csv")
    write_table(canonical, output_root / "fragility_daily_canonical_panel_v0.csv", output_root / "fragility_daily_canonical_panel_v0.parquet")
    write_table(universe, output_root / "fragility_score_decision_universe_v0.csv")
    write_table(feature_panel, output_root / "fragility_feature_panel_v0.csv", output_root / "fragility_feature_panel_v0.parquet")
    write_table(feature_audit, output_root / "fragility_feature_availability_audit_v0.csv")
    write_table(no_lookahead, output_root / "fragility_score_no_lookahead_audit_v0.csv")
    write_table(component_lineage, output_root / "fragility_component_input_lineage_v0.csv")
    write_table(lookback_audit, output_root / "fragility_lookback_completeness_audit_v0.csv")
    write_table(as_of_audit, output_root / "fragility_as_of_request_audit_v0.csv")
    write_table(raw_reconciliation, output_root / "fragility_raw_reconciliation_audit_v0.csv")
    write_table(component_scores, output_root / "fragility_component_scores_v0.csv")
    write_table(score_panel, output_root / "fragility_score_panel_v0.csv", output_root / "fragility_score_panel_v0.parquet")
    write_table(latest, output_root / "fragility_score_latest_v0.csv")
    latest_payload = build_latest_json(latest, as_of_date, as_of_audit)
    (output_root / "fragility_score_latest_v0.json").write_text(json.dumps(latest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_table(data_quality, output_root / "fragility_score_data_quality_audit_v0.csv")
    write_table(oos_panel, output_root / "fragility_score_oos_panel_v0.csv")
    write_table(oos_fold, output_root / "fragility_score_oos_fold_audit_v0.csv")
    write_table(oos_band, output_root / "fragility_score_oos_band_metrics_v0.csv")
    write_table(oos_summary, output_root / "fragility_score_oos_summary_v0.csv")
    write_dashboard(output_root, latest, component_scores, oos_summary, as_of_audit)

    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "score_policy_revision": SCORE_POLICY_REVISION,
        "score_decision_time_policy": SCORE_DECISION_TIME_POLICY,
        "input_mode": INPUT_MODE,
        "as_of_selection_policy": AS_OF_SELECTION_POLICY,
        "rolling_window_policy": ROLLING_WINDOW_POLICY,
        "future_outcome_window_policy": FUTURE_OUTCOME_WINDOW_POLICY,
        "vix_component_lineage_policy": VIX_COMPONENT_LINEAGE_POLICY,
        "duplicate_final_reconciliation_policy": DUPLICATE_FINAL_RECONCILIATION_POLICY,
        "network_download_default": False,
        "calendar_fallback_allowed": False,
        "forward_fill_allowed": False,
        "score_weight_fitting_allowed": False,
        "score_calibration_allowed": False,
        "gamma_component_included": False,
        "leveraged_etf_component_included": False,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "oos_mode": OOS_MODE,
        "requested_as_of_date": as_of_date,
        "latest_available_session_date": "" if latest.empty else str(latest["session_date"].max()),
        "raw_input_row_count": int(inventory["raw_row_count"].sum()) if not inventory.empty else 0,
        "valid_raw_input_row_count": int(len(canonical)),
        "selected_invalid_raw_input_row_count": int((raw_audit["raw_input_status"] == "selected_invalid").sum()) if not raw_audit.empty else 0,
        "eligible_score_row_count": int((score_panel["score_status"] == "valid").sum()) if not score_panel.empty else 0,
        "unavailable_score_row_count": int((score_panel["score_status"] != "valid").sum()) if not score_panel.empty else 0,
        "high_confidence_score_row_count": int((score_panel["confidence"] == "High").sum()) if not score_panel.empty else 0,
        "medium_confidence_score_row_count": int((score_panel["confidence"] == "Medium").sum()) if not score_panel.empty else 0,
        "low_confidence_score_row_count": int((score_panel["confidence"] == "Low").sum()) if not score_panel.empty else 0,
        "oos_eligible_row_count": int((oos_panel["oos_eligible"] == True).sum()) if not oos_panel.empty else 0,
        "requested_as_of_unavailable_target_count": int((as_of_audit["as_of_resolution_status"] == "requested_as_of_unavailable").sum()) if not as_of_audit.empty else 0,
        "vix_component_high_confidence_count": int(((component_scores["component_name"] == "vix_term_structure_stress") & (component_scores["source_confidence"] == "High")).sum()) if not component_scores.empty else 0,
        "vix_component_medium_confidence_count": int(((component_scores["component_name"] == "vix_term_structure_stress") & (component_scores["source_confidence"] == "Medium")).sum()) if not component_scores.empty else 0,
        "vix_component_unavailable_count": int(((component_scores["component_name"] == "vix_term_structure_stress") & (component_scores["component_status"] != "valid")).sum()) if not component_scores.empty else 0,
        "lookback_incomplete_window_count": int((lookback_audit["window_completeness_status"] != "valid").sum()) if not lookback_audit.empty else 0,
        "future_outcome_calendar_incomplete_count": int((oos_panel["oos_reason"].astype(str).str.contains("future_outcome_calendar_session_missing", na=False)).sum()) if not oos_panel.empty else 0,
        "duplicate_selected_invalid_raw_row_count": int(inventory["duplicate_selected_invalid_row_count"].sum()) if not inventory.empty else 0,
        "raw_availability_canonical_reconciliation_mismatch_count": int((raw_reconciliation["raw_availability_canonical_reconciliation_status"] != "valid").sum()) if not raw_reconciliation.empty else 0,
        "rules_json": rules,
        "sources_json": sources,
    }
    (output_root / "fragility_score_manifest_v0.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    if invalid_as_of:
        raise SystemExit(f"--as-of-date is not an ingested completed NYSE regular session: {as_of_date}")
    if strict and as_of_date:
        market = latest[latest["score_target"] == "MARKET"] if not latest.empty else pd.DataFrame()
        if market.empty or str(market.iloc[0].get("score_status", "")) != "valid":
            raise SystemExit("--strict requested but exact MARKET as-of score is unavailable.")
    if strict and canonical.empty:
        raise SystemExit("--strict requested but no usable local historical rows were found.")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--input-root", default="market_bomb_history/fragility_score_v0/raw")
    parser.add_argument("--output-root", default="market_bomb_fragility_v0")
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    input_root = Path(args.input_root)
    if not input_root.is_absolute():
        input_root = root / input_root
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = root / output_root
    run(root, input_root, output_root, args.as_of_date, args.strict)


if __name__ == "__main__":
    main()
