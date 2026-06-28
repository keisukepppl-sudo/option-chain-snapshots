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


ARTIFACT_VERSION = "market_fragility_score_v0_1"
SCORE_POLICY_REVISION = "predeclared_fragility_rubric_v0_1"
SCORE_DECISION_TIME_POLICY = "nyse_regular_session_close_plus_15_minutes_v0_1"
INPUT_MODE = "local_timestamped_csv_only_default"
OOS_MODE = "predeclared_walk_forward_descriptive_evaluation_v0_1"
ACTIONIZATION_ALLOWED = False
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
    "valid_row_count",
    "selected_invalid_row_count",
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
    "max_input_effective_available_at_utc",
    "no_lookahead_status",
    "no_lookahead_reason",
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
    if value is None or value == "":
        return None
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is None:
            return value
        return value.tz_convert("UTC")
    return _parse_ts_cached(str(value))


def is_tz_aware(value: Any) -> bool:
    if value is None or value == "":
        return False
    text = str(value)
    if text.endswith("Z") or text.endswith("+00:00"):
        return True
    if "T" in text and len(text) >= 6 and (text[-6] in ["+", "-"]) and text[-3] == ":":
        return True
    ts = parse_ts(text)
    return ts is not None and ts.tzinfo is not None


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

    for ticker in ALL_TICKERS:
        path = expected_source_path(input_root, ticker)
        content_hash = file_sha256(path)
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
            if eff_raw not in [None, ""] and not is_tz_aware(eff_raw):
                reasons.append("timezone_naive_supplied_effective_timestamp")
            source_as_of = parse_ts(source_as_of_raw) if source_as_of_raw not in [None, ""] and is_tz_aware(source_as_of_raw) else None
            if eff_raw not in [None, ""] and is_tz_aware(eff_raw):
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

        candidates = [x for x in canonical_candidates if x["ticker"] == ticker]
        valid_rows = len(candidates)
        selected_invalid = len([x for x in audit_rows if x["ticker"] == ticker and x["raw_input_status"] == "selected_invalid"])
        inventory.append(
            {
                "ticker": ticker,
                "source_path_or_provider": str(path),
                "file_exists": path.exists(),
                "raw_row_count": raw_count,
                "valid_row_count": valid_rows,
                "selected_invalid_row_count": selected_invalid,
                "first_session_date": min([x["session_date"] for x in candidates], default=""),
                "last_session_date": max([x["session_date"] for x in candidates], default=""),
                "source_content_hash": content_hash,
                "availability_basis_summary": ",".join(sorted(set(x["availability_basis"] for x in candidates))),
                "availability_confidence_summary": ",".join(sorted(set(x["availability_confidence"] for x in candidates))),
            }
        )

    canonical = pd.DataFrame(canonical_candidates, columns=CANONICAL_PANEL_COLUMNS)
    audit = pd.DataFrame(audit_rows, columns=RAW_INPUT_AUDIT_COLUMNS)
    availability = pd.DataFrame(availability_rows, columns=AVAILABILITY_AUDIT_COLUMNS)
    inventory_df = pd.DataFrame(inventory, columns=RAW_SOURCE_INVENTORY_COLUMNS)
    if canonical.empty:
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
                    ["raw_input_status", "raw_input_reason"],
                ] = ["selected_invalid", matched[0]]
            else:
                keep_mask.append(True)
        canonical = canonical[pd.Series(keep_mask).values].copy()
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


def compute_target_features(target: str, panel: pd.DataFrame) -> pd.DataFrame:
    ticker = target
    df = panel[panel["ticker"] == ticker].sort_values("session_date").copy()
    if df.empty:
        return df
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


def vix_features(panel: pd.DataFrame) -> pd.DataFrame:
    piv = panel[panel["ticker"].isin(VOL_TICKERS)].pivot(index="session_date", columns="ticker", values="close")
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


def build_feature_and_scores(canonical: pd.DataFrame, universe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    feature_rows: list[dict[str, Any]] = []
    feature_audit_rows: list[dict[str, Any]] = []
    no_lookahead_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    if canonical.empty or universe.empty:
        return (
            pd.DataFrame(feature_rows, columns=FEATURE_PANEL_COLUMNS),
            pd.DataFrame(feature_audit_rows, columns=FEATURE_PANEL_COLUMNS),
            pd.DataFrame(no_lookahead_rows, columns=NO_LOOKAHEAD_COLUMNS),
            pd.DataFrame(component_rows, columns=COMPONENT_SCORE_COLUMNS),
            pd.DataFrame(score_rows, columns=SCORE_PANEL_COLUMNS),
        )

    target_feature_frames = {t: compute_target_features(t, canonical) for t in PRICE_TICKERS}
    vix_frame = vix_features(canonical)
    vix_by_date = vix_frame.set_index("session_date").to_dict("index") if not vix_frame.empty else {}
    source_rows_by_key = {
        (row["ticker"], row["session_date"]): row for row in canonical.to_dict("records")
    }

    target_components: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for target, df in target_feature_frames.items():
        for row in df.to_dict("records"):
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
                        "max_input_effective_available_at_utc": max_eff,
                        "no_lookahead_status": "data_quality_blocked" if violation else "valid",
                        "no_lookahead_reason": "future_effective_available_at" if violation else "valid",
                    }
                )

            comps: dict[str, dict[str, Any]] = {}
            trend_inputs = [row.get("ma20"), row.get("ma50"), row.get("ma200"), row.get("dd63")]
            if any(pd.isna(x) for x in trend_inputs):
                trend = np.nan
                trend_status = "unavailable_coverage"
                trend_reason = "insufficient_history"
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
            }
            rv_inputs = [row.get("rv20"), row.get("rv60"), row.get("rv20_percentile_252"), row.get("rv_acceleration")]
            if any(pd.isna(x) for x in rv_inputs):
                rv_score = np.nan
                rv_status = "unavailable_coverage"
                rv_reason = "insufficient_history"
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
            }
            cta_inputs = [row.get("r20"), row.get("r60"), row.get("r120"), row.get("r252"), row.get("rv20"), row.get("cta_sell_impulse")]
            if any(pd.isna(x) for x in cta_inputs):
                cta = np.nan
                cta_status = "unavailable_coverage"
                cta_reason = "insufficient_history"
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
            }
            vc_inputs = [row.get("rv20"), row.get("vol_control_sell_impulse"), row.get("vol_control_stress_state")]
            if any(pd.isna(x) for x in vc_inputs):
                vc = np.nan
                vc_status = "unavailable_coverage"
                vc_reason = "insufficient_history"
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
            }
            vix = vix_by_date.get(session_date, {})
            if "backwardation" not in vix or pd.isna(vix.get("backwardation")) or pd.isna(vix.get("vix_percentile_252")):
                vix_score = np.nan
                vix_status = "unavailable_coverage"
                vix_reason = "missing_vix_or_vix3m"
            elif "near_term_stress" in vix and not pd.isna(vix.get("near_term_stress")):
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
            }
            target_components[(target, session_date)] = comps
            source_conf = row_source_confidence(canonical[(canonical["ticker"] == target) & (canonical["session_date"] == session_date)])
            for cname, comp in comps.items():
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
                        "source_confidence": source_conf if cname != "vix_term_structure_stress" else "High" if comp["status"] == "valid" else "Low",
                        "is_proxy": comp["is_proxy"],
                        "observed_flow": False,
                        "data_type": comp["data_type"],
                        "feature_as_of_timestamp_utc": decision_ts if comp["status"] == "valid" else "",
                        "effective_available_at_utc": max_eff,
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
            else:
                score = np.nan
                status = "unavailable_coverage"
                reason = "requires_spy_and_qqq_component"
            market_comps[cname] = {
                "score": score,
                "status": status,
                "reason": reason,
                "is_proxy": s.get("is_proxy", False),
                "data_type": s.get("data_type", ""),
            }
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
                    "source_confidence": "Medium",
                    "is_proxy": s.get("is_proxy", False),
                    "observed_flow": False,
                    "data_type": s.get("data_type", ""),
                    "feature_as_of_timestamp_utc": decision_ts if status == "valid" else "",
                    "effective_available_at_utc": decision_ts,
                }
            )
        target_components[("MARKET", session_date)] = market_comps

    component_df = pd.DataFrame(component_rows, columns=COMPONENT_SCORE_COLUMNS)
    for (target, session_date), comps in target_components.items():
        if target != "MARKET":
            src_rows = canonical[(canonical["ticker"] == target) & (canonical["session_date"] == session_date)]
            if src_rows.empty:
                continue
            decision_ts = src_rows["decision_timestamp_utc"].iloc[0]
            source_summary = row_source_confidence(src_rows)
            warning_count = int((src_rows["availability_confidence"].astype(str).str.lower() != "high").sum())
        else:
            match = canonical[canonical["session_date"] == session_date]
            if match.empty:
                continue
            decision_ts = match["decision_timestamp_utc"].iloc[0]
            source_summary = "Medium" if any(match["availability_confidence"].astype(str).str.lower() != "high") else "High"
            warning_count = int((match["availability_confidence"].astype(str).str.lower() != "high").sum())
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


def add_oos(score_panel: pd.DataFrame, canonical: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    feature_frames = {t: compute_target_features(t, canonical) for t in PRICE_TICKERS}
    score_by_key = {
        (row["score_target"], row["session_date"]): row for row in score_panel.to_dict("records") if row["score_target"] in PRICE_TICKERS
    }
    for target, prices in feature_frames.items():
        prices = prices.sort_values("session_date").reset_index(drop=True)
        closes = prices["close"].astype(float)
        log_ret = np.log(closes / closes.shift(1))
        for idx, row in prices.iterrows():
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


def latest_score(score_panel: pd.DataFrame, as_of_date: str | None) -> pd.DataFrame:
    if score_panel.empty:
        return pd.DataFrame(columns=SCORE_PANEL_COLUMNS)
    df = score_panel.copy()
    if as_of_date:
        df = df[df["session_date"] <= as_of_date]
    if df.empty:
        return pd.DataFrame(columns=SCORE_PANEL_COLUMNS)
    idx = df.sort_values("session_date").groupby("score_target").tail(1).index
    return df.loc[idx].sort_values("score_target").reset_index(drop=True)


def build_latest_json(latest: pd.DataFrame, requested_as_of_date: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at_utc": iso_utc(pd.Timestamp.now(tz="UTC")),
        "requested_as_of_date": requested_as_of_date,
        "latest_available_session_date": "" if latest.empty else str(latest["session_date"].max()),
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
                "warnings": [] if int(r["availability_warning_count"]) == 0 else ["policy_assumed_or_non_high_confidence_source"],
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


def write_dashboard(out: Path, latest: pd.DataFrame, component_df: pd.DataFrame, oos_summary: pd.DataFrame) -> None:
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
        "- Caveat: rule-based proxies, no Gamma or Leveraged ETF component, no calibration, no trade action.",
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


def run(root: Path, input_root: Path, output_root: Path, as_of_date: str | None = None, strict: bool = False) -> dict[str, Any]:
    config_dir = root / "market_bomb_config"
    rules = load_json(config_dir / "fragility_score_v0_rules.json", {})
    sources = load_json(config_dir / "fragility_score_v0_sources.json", {})
    output_root.mkdir(parents=True, exist_ok=True)
    calendar = load_calendar(root)
    if as_of_date and as_of_date not in set(calendar["session_date"] if not calendar.empty else []):
        raise SystemExit(f"--as-of-date is not an ingested completed NYSE regular session: {as_of_date}")
    inventory, raw_audit, availability, canonical = ingest_raw_sources(root, input_root, calendar)
    if as_of_date and not canonical.empty:
        canonical = canonical[canonical["session_date"] <= as_of_date].copy()
        availability = availability[availability["session_date"] <= as_of_date].copy()
    universe = build_decision_universe(canonical, calendar if not as_of_date else calendar[calendar["session_date"] <= as_of_date])
    feature_panel, feature_audit, no_lookahead, component_scores, score_panel = build_feature_and_scores(canonical, universe)
    oos_panel, oos_fold, oos_band, oos_summary = add_oos(score_panel, canonical)
    latest = latest_score(score_panel, as_of_date)
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
    write_table(component_scores, output_root / "fragility_component_scores_v0.csv")
    write_table(score_panel, output_root / "fragility_score_panel_v0.csv", output_root / "fragility_score_panel_v0.parquet")
    write_table(latest, output_root / "fragility_score_latest_v0.csv")
    latest_payload = build_latest_json(latest, as_of_date)
    (output_root / "fragility_score_latest_v0.json").write_text(json.dumps(latest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_table(data_quality, output_root / "fragility_score_data_quality_audit_v0.csv")
    write_table(oos_panel, output_root / "fragility_score_oos_panel_v0.csv")
    write_table(oos_fold, output_root / "fragility_score_oos_fold_audit_v0.csv")
    write_table(oos_band, output_root / "fragility_score_oos_band_metrics_v0.csv")
    write_table(oos_summary, output_root / "fragility_score_oos_summary_v0.csv")
    write_dashboard(output_root, latest, component_scores, oos_summary)

    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "score_policy_revision": SCORE_POLICY_REVISION,
        "score_decision_time_policy": SCORE_DECISION_TIME_POLICY,
        "input_mode": INPUT_MODE,
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
        "rules_json": rules,
        "sources_json": sources,
    }
    (output_root / "fragility_score_manifest_v0.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
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
