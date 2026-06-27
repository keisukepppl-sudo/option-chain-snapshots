#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
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
VERSION = "market_bomb_market_impact_backtest_v1_20260627"
RULES_PATH = Path("market_bomb_config/market_impact_backtest_rules_v1.json")
LEVERAGED_UNIVERSE_PATH = Path("market_bomb_config/leveraged_etf_universe_v1.json")
DEALER_RULES_PATH = Path("market_bomb_config/dealer_gamma_observed_rules_v1.json")
EXPIRY_CALENDAR_PATH = Path("market_bomb_config/options_expiry_calendar_v1.csv")
DATA_SOURCES_PATH = Path("market_bomb_config/market_impact_data_sources_v1.json")
FEATURE_MAPPINGS_PATH = Path("market_bomb_config/market_impact_feature_mappings_v1.json")
BASELINE_PATH = Path("market_bomb_config/market_impact_baseline_v1.json")
OUTPUT_ROOT = Path("market_bomb_market_impact")

FEATURE_AUDIT_COLUMNS = [
    "feature_family",
    "feature_name",
    "target_market",
    "feature_value",
    "feature_unit",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
    "decision_timestamp_utc",
    "feature_age_hours",
    "availability_basis",
    "availability_confidence",
    "source_path_or_provider",
    "source_hash_or_request_id",
    "data_type",
    "is_proxy",
    "observed_flow",
    "quality_grade",
    "availability_status",
    "availability_failure_reason",
]

PANEL_COMMON_COLUMNS = [
    "analysis_id",
    "module",
    "feature_family",
    "feature_name",
    "target_market",
    "decision_date",
    "decision_timestamp_utc",
    "feature_value",
    "feature_unit",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
    "feature_age_hours",
    "availability_basis",
    "availability_confidence",
    "source_path_or_provider",
    "source_hash_or_request_id",
    "data_type",
    "is_proxy",
    "observed_flow",
    "quality_grade",
    "availability_status",
    "availability_failure_reason",
    "primary_or_robustness",
]


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value) or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def parse_ts(value: Any) -> pd.Timestamp | None:
    if value in [None, ""] or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(root: Path, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    full = root / path
    if not full.exists():
        return fallback
    try:
        return json.loads(full.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def rules(root: Path) -> dict[str, Any]:
    return load_json(root, RULES_PATH, {
        "version": "market_impact_backtest_rules_v1",
        "targets": ["QQQ", "SPY", "SOXX", "SMH"],
        "daily_horizons": [1, 5, 10],
        "intraday_primary_asof_et": "15:30",
        "intraday_robustness_asof_et": "15:00",
        "max_feature_age_hours": 96,
        "walk_forward": {"method": "expanding_window", "minimum_train_observations": 252, "test_block": "monthly"},
        "statistical": {
            "bootstrap_method": "moving_block",
            "multiple_testing_method": "benjamini_hochberg",
            "bootstrap_block_length": 5,
            "bootstrap_iterations": 1000,
            "random_seed": 42,
            "ridge_alpha": 1.0,
        },
        "minimum_samples": {
            "cta_vol_min_oos_rows_per_target": 252,
            "cta_vol_min_test_months": 6,
            "leveraged_etf_min_oos_rows": 126,
            "leveraged_etf_min_test_months": 6,
            "leveraged_etf_complete_universe_coverage_min": 0.80,
            "dealer_gamma_min_oos_rows": 100,
            "dealer_gamma_min_test_months": 6,
            "dealer_expiry_min_event_rows_per_comparison_group": 20,
        },
        "bar_timestamp_convention": "bar_end",
        "actionization_allowed": False,
    })


def baseline_config(root: Path) -> dict[str, Any]:
    return load_json(root, BASELINE_PATH, {
        "version": "market_impact_baseline_v1",
        "daily": [
            "prior_return_1d",
            "prior_return_5d",
            "prior_realized_vol_20d",
            "distance_from_20d_moving_average",
            "weekday",
            "month_end_flag",
            "monthly_expiry_flag",
            "quarterly_expiry_flag",
        ],
        "intraday": [
            "return_prior_regular_close_to_1530",
            "absolute_return_prior_regular_close_to_1530",
            "intraday_realized_vol_to_1530",
            "intraday_volume_share_to_1530",
            "prior_session_return",
            "prior_20d_realized_vol",
            "weekday",
            "monthly_expiry_flag",
            "quarterly_expiry_flag",
        ],
    })


def feature_mappings(root: Path) -> dict[str, Any]:
    return load_json(root, FEATURE_MAPPINGS_PATH, {
        "version": "market_impact_feature_mappings_v1",
        "cta_only": ["cta_exposure_change_proxy", "cta_deleveraging_proxy"],
        "vol_only": ["vol_control_exposure_change_proxy"],
        "cta_plus_vol": ["cta_exposure_change_proxy", "cta_deleveraging_proxy", "vol_control_exposure_change_proxy"],
        "leveraged_etf": ["aggregate_pressure_usd"],
        "dealer_gamma": ["gamma_flip_distance_pct", "net_gex_proxy", "pinning_proxy", "local_flip_found_flag", "no_local_flip_flag"],
        "expiry_event": ["monthly_expiry_flag", "quarterly_expiry_flag", "triple_witching_flag"],
    })


def data_sources_config(root: Path) -> dict[str, Any]:
    return load_json(root, DATA_SOURCES_PATH, {
        "version": "market_impact_data_sources_v1",
        "refresh_adapters": {
            "refresh_daily_prices": "not_supported",
            "refresh_intraday_prices": "not_supported",
            "run_gamma_surrogate_exploration": "not_supported",
        },
    })


def leveraged_universe(root: Path) -> dict[str, Any]:
    return load_json(root, LEVERAGED_UNIVERSE_PATH, {
        "version": "leveraged_etf_universe_v1",
        "nasdaq_100": [
            {"ticker": "TQQQ", "target": "QQQ", "leverage": 3.0},
            {"ticker": "SQQQ", "target": "QQQ", "leverage": -3.0},
        ],
        "semiconductor": [
            {"ticker": "SOXL", "target": "SOXX", "leverage": 3.0},
            {"ticker": "SOXS", "target": "SOXX", "leverage": -3.0},
        ],
    })


def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass


def markdown_table(df: pd.DataFrame, max_rows: int = 50) -> str:
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


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan
    return out[columns + [c for c in out.columns if c not in columns]]


def feature_audit_row(
    *,
    feature_family: str,
    feature_name: str,
    target_market: str = "",
    decision_timestamp_utc: Any = "",
    feature_value: Any = np.nan,
    feature_unit: str = "",
    feature_as_of_timestamp_utc: Any = "",
    effective_available_at_utc: Any = "",
    availability_status: str = "unavailable",
    availability_failure_reason: str = "",
    availability_basis: str = "effective_available_at_utc",
    availability_confidence: str = "medium",
    source_path_or_provider: str = "",
    source_hash_or_request_id: str = "",
    data_type: str = "proxy",
    is_proxy: bool = True,
    observed_flow: bool = False,
    quality_grade: str = "unknown",
) -> dict[str, Any]:
    decision_ts = parse_ts(decision_timestamp_utc)
    eff_ts = parse_ts(effective_available_at_utc)
    age = (decision_ts - eff_ts).total_seconds() / 3600 if decision_ts is not None and eff_ts is not None else np.nan
    return {
        "feature_family": feature_family,
        "feature_name": feature_name,
        "target_market": target_market,
        "feature_value": feature_value,
        "feature_unit": feature_unit,
        "feature_as_of_timestamp_utc": feature_as_of_timestamp_utc,
        "effective_available_at_utc": effective_available_at_utc,
        "decision_timestamp_utc": decision_timestamp_utc,
        "feature_age_hours": round(age, 4) if pd.notna(age) else np.nan,
        "availability_basis": availability_basis,
        "availability_confidence": availability_confidence,
        "source_path_or_provider": source_path_or_provider,
        "source_hash_or_request_id": source_hash_or_request_id,
        "data_type": data_type,
        "is_proxy": is_proxy,
        "observed_flow": observed_flow,
        "quality_grade": quality_grade,
        "availability_status": availability_status,
        "availability_failure_reason": availability_failure_reason,
    }


def normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "adjusted_close", "volume"])
    cols = {str(c).lower().replace(" ", "_"): c for c in df.columns}
    date_col = cols.get("date") or cols.get("datetime") or cols.get("timestamp")
    close_col = cols.get("close")
    adj_col = cols.get("adjusted_close") or cols.get("adj_close") or close_col
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce").dt.tz_localize(None) if date_col else pd.NaT,
        "open": pd.to_numeric(df[cols["open"]], errors="coerce") if "open" in cols else np.nan,
        "high": pd.to_numeric(df[cols["high"]], errors="coerce") if "high" in cols else np.nan,
        "low": pd.to_numeric(df[cols["low"]], errors="coerce") if "low" in cols else np.nan,
        "close": pd.to_numeric(df[close_col], errors="coerce") if close_col else np.nan,
        "adjusted_close": pd.to_numeric(df[adj_col], errors="coerce") if adj_col else np.nan,
        "volume": pd.to_numeric(df[cols["volume"]], errors="coerce") if "volume" in cols else np.nan,
    })
    return out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def load_price_history(root: Path, targets: list[str]) -> dict[str, pd.DataFrame]:
    price_dir = root / "market_bomb_history" / "price_history"
    prices: dict[str, pd.DataFrame] = {}
    for target in targets:
        path = price_dir / f"{target}_daily_price_history.csv"
        if path.exists():
            try:
                prices[target] = normalize_price_frame(pd.read_csv(path))
            except Exception:
                prices[target] = pd.DataFrame()
        else:
            prices[target] = pd.DataFrame()
    return prices


def et_close_utc(day: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp.combine(pd.Timestamp(day).date(), time(16, 0)).tz_localize(ET).tz_convert(UTC)


def next_trading_index(df: pd.DataFrame, date_value: pd.Timestamp) -> int | None:
    dates = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    target = pd.Timestamp(date_value).tz_localize(None).normalize()
    idx = np.where(dates >= target)[0]
    return int(idx[0]) if len(idx) else None


def build_daily_outcomes(prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target, df in prices.items():
        if df.empty:
            continue
        work = df.copy().reset_index(drop=True)
        for i in range(len(work) - 11):
            cur = work.loc[i]
            nxt = work.loc[i + 1]
            close = safe_float(cur.get("adjusted_close"))
            next_close = safe_float(nxt.get("adjusted_close"))
            high = safe_float(nxt.get("high"))
            low = safe_float(nxt.get("low"))
            nclose = safe_float(nxt.get("close", next_close))
            if pd.isna(close) or close <= 0 or pd.isna(next_close):
                continue
            range_pct = (high - low) / close if pd.notna(high) and pd.notna(low) and close else np.nan
            close_loc = (nclose - low) / (high - low) if pd.notna(high) and pd.notna(low) and high > low else np.nan
            rets = work["adjusted_close"].iloc[i + 1:i + 11].astype(float) / close - 1
            rows.append({
                "target_market": target,
                "decision_date": pd.Timestamp(cur["date"]).date().isoformat(),
                "outcome_date": pd.Timestamp(nxt["date"]).date().isoformat(),
                "decision_timestamp_utc": et_close_utc(cur["date"]).isoformat(),
                "outcome_start_timestamp_utc": et_close_utc(nxt["date"]).isoformat(),
                "outcome_end_timestamp_utc": et_close_utc(nxt["date"]).isoformat(),
                "next_session_return": next_close / close - 1,
                "next_session_absolute_return": abs(next_close / close - 1),
                "next_session_high_low_range_pct": range_pct,
                "next_session_close_location_value": close_loc,
                "next_session_max_adverse_excursion": rets.min() if len(rets) else np.nan,
                "next_session_max_favorable_excursion": rets.max() if len(rets) else np.nan,
                "forward_return_5d": work.loc[i + 5, "adjusted_close"] / close - 1 if i + 5 < len(work) else np.nan,
                "forward_return_10d": work.loc[i + 10, "adjusted_close"] / close - 1 if i + 10 < len(work) else np.nan,
                "forward_realized_vol_5d": rets.head(5).std() * math.sqrt(252) if len(rets) >= 5 else np.nan,
                "forward_realized_vol_10d": rets.head(10).std() * math.sqrt(252) if len(rets) >= 10 else np.nan,
                "primary_or_robustness": "primary",
            })
    return pd.DataFrame(rows)


def load_expiry_calendar(root: Path) -> pd.DataFrame:
    expiry_path = root / EXPIRY_CALENDAR_PATH
    if not expiry_path.exists():
        return pd.DataFrame(columns=["date", "market", "expiry_type"])
    expiry = pd.read_csv(expiry_path)
    if "date" in expiry.columns:
        expiry["date"] = pd.to_datetime(expiry["date"], errors="coerce").dt.date.astype(str)
    return expiry


def expiry_flags_for_date(expiry: pd.DataFrame, date_value: Any) -> dict[str, int]:
    day = pd.Timestamp(date_value).date().isoformat()
    if expiry.empty or "date" not in expiry.columns:
        return {"monthly_expiry_flag": 0, "quarterly_expiry_flag": 0, "triple_witching_flag": 0}
    rows = expiry[expiry["date"].astype(str).eq(day)]
    expiry_type = " ".join(rows.get("expiry_type", pd.Series(dtype=str)).astype(str).str.lower().tolist())
    triple = rows.get("triple_witching_flag", pd.Series([False] * len(rows))).astype(str).str.lower().isin(["true", "1", "yes"]).any() if not rows.empty else False
    return {
        "monthly_expiry_flag": int((not rows.empty and "monthly" in expiry_type) or "quarterly" in expiry_type or triple),
        "quarterly_expiry_flag": int("quarterly" in expiry_type or triple),
        "triple_witching_flag": int(triple or "triple" in expiry_type),
    }


def month_end_flag(date_value: Any) -> int:
    day = pd.Timestamp(date_value)
    return int((day + pd.offsets.BDay(1)).month != day.month)


def build_daily_baseline(prices: dict[str, pd.DataFrame], expiry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target, df in prices.items():
        if df.empty:
            continue
        work = df.copy().reset_index(drop=True)
        close = pd.to_numeric(work["adjusted_close"], errors="coerce")
        returns = close.pct_change()
        ma20 = close.rolling(20).mean()
        vol20 = returns.rolling(20).std() * math.sqrt(252)
        for i, row in work.iterrows():
            if i < 20:
                continue
            day = pd.Timestamp(row["date"])
            flags = expiry_flags_for_date(expiry, day)
            rows.append({
                "target_market": target,
                "decision_date": day.date().isoformat(),
                "decision_timestamp_utc": et_close_utc(day).isoformat(),
                "prior_return_1d": returns.iloc[i],
                "prior_return_5d": close.iloc[i] / close.iloc[i - 5] - 1 if i >= 5 and close.iloc[i - 5] else np.nan,
                "prior_realized_vol_20d": vol20.iloc[i],
                "distance_from_20d_moving_average": close.iloc[i] / ma20.iloc[i] - 1 if pd.notna(ma20.iloc[i]) and ma20.iloc[i] else np.nan,
                "weekday": int(day.weekday()),
                "month_end_flag": month_end_flag(day),
                **flags,
            })
    return pd.DataFrame(rows)


def attach_daily_baseline(panel: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel
    if baseline.empty:
        return panel
    left = panel.copy()
    if "decision_date" not in left.columns:
        left["decision_date"] = pd.to_datetime(left["decision_timestamp_utc"], utc=True, errors="coerce").dt.tz_convert(ET).dt.date.astype(str)
    return left.merge(
        baseline.drop(columns=["decision_timestamp_utc"], errors="ignore"),
        on=["target_market", "decision_date"],
        how="left",
        suffixes=("", "_baseline"),
    )


def latest_available_feature(df: pd.DataFrame, asset: str, decision_ts: pd.Timestamp, max_age_hours: float = 96, target_vol: float | None = None) -> tuple[pd.Series | None, str, str]:
    if df.empty:
        return None, "unavailable", "feature_history_missing"
    work = df[df["asset"].astype(str).eq(asset)].copy()
    if target_vol is not None and "target_vol" in work.columns:
        work = work[np.isclose(pd.to_numeric(work["target_vol"], errors="coerce"), target_vol)]
    if work.empty:
        return None, "unavailable", "asset_missing"
    work["feature_asof"] = pd.to_datetime(work["feature_as_of_timestamp_utc"], utc=True, errors="coerce")
    work["effective"] = pd.to_datetime(work["effective_available_at_utc"], utc=True, errors="coerce")
    work = work[(work["feature_asof"] <= decision_ts) & (work["effective"] <= decision_ts)]
    if work.empty:
        return None, "unavailable", "no_temporally_available_feature"
    work["feature_age_hours"] = (decision_ts - work["effective"]).dt.total_seconds() / 3600
    work = work[work["feature_age_hours"] <= max_age_hours]
    if work.empty:
        return None, "unavailable", "feature_too_old"
    return work.sort_values("effective").iloc[-1], "available", ""


def load_feature_history(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    cta_path = root / "market_bomb_history" / "cta_proxy_history.csv"
    vol_path = root / "market_bomb_history" / "vol_control_proxy_history.csv"
    cta = pd.read_csv(cta_path) if cta_path.exists() else pd.DataFrame()
    vol = pd.read_csv(vol_path) if vol_path.exists() else pd.DataFrame()
    return cta, vol


def target_to_feature_asset(target: str) -> str:
    if target == "SMH":
        return "SOXX"
    return target


def build_cta_vol_feature_outcome_panel(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cta, vol = load_feature_history(root)
    rows: list[dict[str, Any]] = []
    availability: list[dict[str, Any]] = []
    no_lookahead: list[dict[str, Any]] = []
    max_age = safe_float(cfg.get("max_feature_age_hours", 96), 96)
    for _, outcome in daily_outcomes.iterrows():
        decision_ts = parse_ts(outcome["decision_timestamp_utc"])
        if decision_ts is None:
            continue
        target = str(outcome["target_market"])
        asset = target_to_feature_asset(target)
        cta_row, cta_status, cta_reason = latest_available_feature(cta, asset, decision_ts, max_age_hours=max_age)
        vol_row, vol_status, vol_reason = latest_available_feature(vol, asset if asset in {"QQQ", "SPY", "SOXX"} else "QQQ", decision_ts, max_age_hours=max_age, target_vol=0.12)
        for family, row, status, reason in [("CTA", cta_row, cta_status, cta_reason), ("VolControl", vol_row, vol_status, vol_reason)]:
            asof = row.get("feature_as_of_timestamp_utc") if row is not None else ""
            eff = row.get("effective_available_at_utc") if row is not None else ""
            asof_ts = parse_ts(asof) if asof else None
            eff_ts = parse_ts(eff) if eff else None
            violation = bool((asof_ts is not None and asof_ts > decision_ts) or (eff_ts is not None and eff_ts > decision_ts))
            no_lookahead.append({
                "feature_family": family,
                "target_market": target,
                "decision_timestamp_utc": decision_ts.isoformat(),
                "feature_as_of_timestamp_utc": asof,
                "effective_available_at_utc": eff,
                "no_lookahead_passed": not violation,
                "violation_reason": "feature_after_decision" if violation else "",
            })
            value_col = "cta_exposure_change_1d" if family == "CTA" else "vol_control_exposure_change_1d"
            availability.append(feature_audit_row(
                feature_family=family,
                feature_name=value_col,
                target_market=target,
                decision_timestamp_utc=decision_ts.isoformat(),
                feature_value=row.get(value_col, np.nan) if row is not None else np.nan,
                feature_unit="fraction",
                feature_as_of_timestamp_utc=asof,
                effective_available_at_utc=eff,
                availability_status=status,
                availability_failure_reason=reason,
                source_path_or_provider="market_bomb_history/cta_proxy_history.csv" if family == "CTA" else "market_bomb_history/vol_control_proxy_history.csv",
                data_type=row.get("data_type") if row is not None else "unavailable",
                is_proxy=row.get("is_proxy") if row is not None else True,
                observed_flow=row.get("observed_flow") if row is not None else False,
                quality_grade=row.get("quality_flag") if row is not None else "unavailable",
            ))
        if cta_row is None and vol_row is None:
            continue
        primary_feature_row = cta_row if cta_row is not None else vol_row
        primary_eff_ts = parse_ts(primary_feature_row.get("effective_available_at_utc")) if primary_feature_row is not None else None
        merged = outcome.to_dict()
        merged.update({
            "analysis_id": f"cta_vol_{target}_{decision_ts.date()}",
            "feature_family": "CTA_Vol",
            "feature_name": "cta_vol_proxy_set",
            "feature_value": safe_float(cta_row.get("cta_exposure_change_1d")) if cta_row is not None else np.nan,
            "feature_unit": "fraction",
            "feature_as_of_timestamp_utc": primary_feature_row.get("feature_as_of_timestamp_utc") if primary_feature_row is not None else "",
            "effective_available_at_utc": primary_feature_row.get("effective_available_at_utc") if primary_feature_row is not None else "",
            "feature_age_hours": round((decision_ts - primary_eff_ts).total_seconds() / 3600, 4) if primary_eff_ts is not None else np.nan,
            "availability_basis": "effective_available_at_utc",
            "availability_confidence": "medium",
            "source_path_or_provider": "market_bomb_history/cta_proxy_history.csv;market_bomb_history/vol_control_proxy_history.csv",
            "source_hash_or_request_id": "",
            "data_type": "reconstructed_proxy",
            "is_proxy": True,
            "observed_flow": False,
            "quality_grade": "medium",
            "availability_status": "available",
            "availability_failure_reason": "",
            "analysis_mode": "reconstructed_proxy_primary",
            "baseline_model_version": "trend_vol_baseline_v1",
            "feature_model_version": "cta_vol_proxy_features_v1",
            "sample_split": "expanding_window",
            "cta_trend_state": cta_row.get("cta_trend_state") if cta_row is not None else "unavailable",
            "cta_deleveraging_proxy": cta_row.get("cta_deleveraging_proxy") if cta_row is not None else np.nan,
            "cta_exposure_change_proxy": cta_row.get("cta_exposure_change_1d") if cta_row is not None else np.nan,
            "vol_control_state": vol_row.get("vol_control_state") if vol_row is not None else "unavailable",
            "vol_control_pressure_proxy": vol_row.get("vol_control_pressure_proxy") if vol_row is not None else "unavailable",
            "vol_control_exposure_change_proxy": vol_row.get("vol_control_exposure_change_1d") if vol_row is not None else np.nan,
        })
        rows.append(merged)
    return pd.DataFrame(rows), pd.DataFrame(availability), pd.DataFrame(no_lookahead)


def leveraged_pressure(leverage: float, aum_usd: float, target_return_to_time: float) -> float:
    return leverage * (leverage - 1.0) * aum_usd * target_return_to_time


def load_leveraged_aum(root: Path) -> pd.DataFrame:
    paths = [
        root / "market_bomb_history" / "leveraged_etf_aum_history.csv",
        root / "manual_etf_aum.csv",
    ]
    for path in paths:
        if path.exists():
            try:
                return pd.read_csv(path)
            except Exception:
                pass
    return pd.DataFrame()


def prior_available_aum(aum: pd.DataFrame, ticker: str, decision_ts: pd.Timestamp, prior_regular_close_ts: pd.Timestamp | None = None) -> tuple[float, str, bool]:
    if aum.empty:
        return math.nan, "aum_history_missing", False
    work = aum[aum.get("ticker", pd.Series(dtype=str)).astype(str).eq(ticker)].copy()
    if work.empty:
        return math.nan, "ticker_aum_missing", False
    prior_regular_close_ts = prior_regular_close_ts or decision_ts
    availability_status = work.get("aum_availability_status", pd.Series([""] * len(work))).astype(str)
    date_col = "effective_available_at_utc" if "effective_available_at_utc" in work.columns else "as_of_timestamp_utc" if "as_of_timestamp_utc" in work.columns else "date" if "date" in work.columns else ""
    if not date_col:
        return math.nan, "aum_timestamp_missing", False
    work["asof"] = pd.to_datetime(work[date_col], utc=True, errors="coerce")
    if date_col == "date" and not availability_status.eq("prior_business_day_confirmed_aum").any():
        return math.nan, "date_only_aum_not_primary", False
    work["prior_business_day_confirmed"] = availability_status.eq("prior_business_day_confirmed_aum")
    work = work[(work["asof"] <= prior_regular_close_ts) | ((work["asof"] <= decision_ts) & work["prior_business_day_confirmed"])]
    if work.empty:
        return math.nan, "no_prior_available_aum", False
    row = work.sort_values("asof").iloc[-1]
    for col in ["net_assets_usd", "aum_usd", "assets"]:
        if col in row and pd.notna(row[col]):
            return safe_float(row[col]), "previous_available_net_assets_usd", False
    if "shares_outstanding" in row and "prior_close" in row:
        value = safe_float(row["shares_outstanding"]) * safe_float(row["prior_close"])
        if pd.notna(value) and value > 0:
            return value, "imputed_surrogate_exploratory", True
    return math.nan, "aum_value_missing", False


def load_intraday_bars(root: Path, target: str) -> pd.DataFrame:
    for path in [
        root / "market_bomb_history" / "intraday_bars" / f"{target}_5m.csv",
        root / "market_bomb_history" / "intraday_bars" / f"{target}.csv",
    ]:
        if path.exists():
            try:
                df = pd.read_csv(path)
                cols = {str(c).lower(): c for c in df.columns}
                ts_col = cols.get("timestamp_utc") or cols.get("datetime") or cols.get("timestamp")
                if ts_col is None:
                    return pd.DataFrame()
                out = df.copy()
                out["timestamp_utc"] = pd.to_datetime(out[ts_col], utc=True, errors="coerce")
                for col in ["open", "high", "low", "close", "volume", "prior_regular_session_close", "prior_close", "prior_session_return", "prior_20d_realized_vol"]:
                    if col in out.columns:
                        out[col] = pd.to_numeric(out[col], errors="coerce")
                return out.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")
            except Exception:
                return pd.DataFrame()
    return pd.DataFrame()


def build_leveraged_etf_panel(root: Path, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = leveraged_universe(root)
    aum = load_leveraged_aum(root)
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for family, funds in universe.items():
        if not isinstance(funds, list):
            continue
        targets = sorted({str(f["target"]) for f in funds})
        for target in targets:
            bars = load_intraday_bars(root, target)
            if bars.empty:
                audit.append({"target_market": target, "feature_family": "LeveragedETF", "availability_status": "unavailable", "availability_failure_reason": "intraday_bars_missing"})
                continue
            bars["date_et"] = bars["timestamp_utc"].dt.tz_convert(ET).dt.date
            for day, group in bars.groupby("date_et"):
                group = group.sort_values("timestamp_utc")
                et_times = group["timestamp_utc"].dt.tz_convert(ET)
                at_1530 = group[et_times.dt.time <= time(15, 30)]
                close_bar = group[et_times.dt.time <= time(16, 0)]
                if at_1530.empty or close_bar.empty:
                    audit.append({"target_market": target, "feature_family": "LeveragedETF", "availability_status": "unavailable", "availability_failure_reason": "intraday_1530_or_close_missing"})
                    continue
                bar_1530 = at_1530.iloc[-1]
                bar_close = close_bar.iloc[-1]
                prior_close = safe_float(group.iloc[0].get("prior_regular_session_close", np.nan))
                price_1530 = safe_float(bar_1530.get("close"))
                close_price = safe_float(bar_close.get("close"))
                if pd.isna(prior_close) or prior_close <= 0 or pd.isna(price_1530) or pd.isna(close_price):
                    audit.append({"target_market": target, "feature_family": "LeveragedETF", "availability_status": "unavailable", "availability_failure_reason": "prior_regular_session_close_missing"})
                    continue
                r_to_1530 = price_1530 / prior_close - 1
                pressure = 0.0
                unavailable = []
                fund_rows = [f for f in funds if str(f["target"]) == target]
                decision_ts = pd.Timestamp.combine(pd.Timestamp(day).date(), time(15, 30)).tz_localize(ET).tz_convert(UTC)
                prior_regular_close_ts = (pd.Timestamp.combine(pd.Timestamp(day).date(), time(16, 0)).tz_localize(ET) - pd.offsets.BDay(1)).tz_convert(UTC)
                for fund in fund_rows:
                    fund_aum, aum_source, aum_proxy = prior_available_aum(aum, str(fund["ticker"]), decision_ts, prior_regular_close_ts)
                    if pd.isna(fund_aum) or fund_aum <= 0:
                        unavailable.append(f"{fund['ticker']}:{aum_source}")
                        continue
                    if aum_proxy:
                        unavailable.append(f"{fund['ticker']}:{aum_source}")
                        continue
                    pressure += leveraged_pressure(float(fund["leverage"]), fund_aum, r_to_1530)
                complete_coverage = (len(fund_rows) - len(unavailable)) / max(len(fund_rows), 1)
                if unavailable:
                    audit.append({
                        "target_market": target,
                        "feature_family": "LeveragedETF",
                        "decision_timestamp_utc": decision_ts.isoformat(),
                        "availability_status": "unavailable",
                        "availability_failure_reason": "partial_universe_not_primary:" + ";".join(unavailable),
                        "complete_universe_coverage": complete_coverage,
                    })
                    continue
                after_1530 = group[(et_times.dt.time > time(15, 30)) & (et_times.dt.time <= time(16, 0))]
                volume_total = safe_float(group["volume"].sum(), np.nan) if "volume" in group.columns else np.nan
                volume_to_1530 = safe_float(at_1530["volume"].sum(), np.nan) if "volume" in at_1530.columns else np.nan
                prior_session_return = safe_float(group.iloc[0].get("prior_session_return", np.nan))
                prior_20d_realized_vol = safe_float(group.iloc[0].get("prior_20d_realized_vol", np.nan))
                flags = expiry_flags_for_date(load_expiry_calendar(root), day)
                rows.append({
                    "analysis_id": f"leveraged_etf_{target}_{day}",
                    "feature_family": "LeveragedETF",
                    "feature_name": f"{family}_pressure",
                    "target_market": target,
                    "decision_date": pd.Timestamp(day).date().isoformat(),
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "feature_value": pressure,
                    "feature_unit": "usd_pressure_proxy",
                    "feature_as_of_timestamp_utc": decision_ts.isoformat(),
                    "effective_available_at_utc": decision_ts.isoformat(),
                    "feature_age_hours": 0.0,
                    "availability_basis": "last_bar_completed_by_1530_et",
                    "availability_confidence": "medium",
                    "source_path_or_provider": f"market_bomb_history/intraday_bars/{target}_5m.csv;market_bomb_history/leveraged_etf_aum_history.csv",
                    "source_hash_or_request_id": "",
                    "aggregate_pressure_usd": pressure,
                    "pressure_sign": "positive" if pressure > 0 else "negative" if pressure < 0 else "flat",
                    "return_prior_regular_close_to_1530": r_to_1530,
                    "return_prior_close_to_1530": r_to_1530,
                    "absolute_return_prior_regular_close_to_1530": abs(r_to_1530),
                    "intraday_realized_vol_to_1530": pd.to_numeric(at_1530["close"], errors="coerce").pct_change().std() * math.sqrt(78) if len(at_1530) > 2 else np.nan,
                    "intraday_volume_share_to_1530": volume_to_1530 / volume_total if pd.notna(volume_to_1530) and pd.notna(volume_total) and volume_total else np.nan,
                    "prior_session_return": prior_session_return,
                    "prior_20d_realized_vol": prior_20d_realized_vol,
                    "weekday": pd.Timestamp(day).weekday(),
                    **flags,
                    "intraday_return_1530_to_close": close_price / price_1530 - 1,
                    "intraday_absolute_return_1530_to_close": abs(close_price / price_1530 - 1),
                    "intraday_range_1530_to_close": (safe_float(after_1530.get("high", pd.Series([np.nan])).max()) - safe_float(after_1530.get("low", pd.Series([np.nan])).min())) / price_1530 if price_1530 and not after_1530.empty else np.nan,
                    "data_type": "reconstructed_proxy",
                    "is_proxy": True,
                    "observed_flow": False,
                    "quality_grade": "medium",
                    "availability_status": "available",
                    "availability_failure_reason": "",
                    "formula_version": "leveraged_etf_rebalancing_pressure_v1",
                    "analysis_mode": "reconstructed_proxy_primary",
                    "sample_split": "expanding_window",
                    "bar_timestamp_convention": cfg.get("bar_timestamp_convention", "bar_end"),
                    "complete_universe_coverage": complete_coverage,
                })
                audit.append({
                    "target_market": target,
                    "feature_family": "LeveragedETF",
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "availability_status": "available",
                    "availability_failure_reason": "",
                    "complete_universe_coverage": complete_coverage,
                    "universe_fund_count": len(fund_rows),
                })
    return pd.DataFrame(rows), pd.DataFrame(audit)


def load_dealer_gamma_history(root: Path) -> pd.DataFrame:
    candidates = [
        root / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "dealer_gamma_observed_history.csv",
    ]
    for path in candidates:
        if path.exists():
            try:
                df = pd.read_csv(path)
                df["source_path_or_provider"] = str(path.relative_to(root)).replace("\\", "/")
                return df
            except Exception:
                pass
    return pd.DataFrame()


def build_dealer_gamma_panel(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = cfg or rules(root)
    raw = load_dealer_gamma_history(root)
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame([{"feature_family": "DealerGamma", "availability_status": "unavailable", "availability_failure_reason": "dealer_gamma_history_missing"}])
    cols = {str(c).lower(): c for c in raw.columns}
    target_col = cols.get("ticker") or cols.get("asset") or cols.get("target_market")
    eff_col = cols.get("effective_available_at_utc") or cols.get("snapshot_timestamp_utc") or cols.get("feature_as_of_timestamp_utc")
    asof_col = cols.get("feature_as_of_timestamp_utc") or cols.get("option_chain_as_of_timestamp_utc") or cols.get("snapshot_timestamp_utc") or eff_col
    quality_col = cols.get("row_economic_quality") or cols.get("raw_chain_quality") or cols.get("economic_quality")
    if target_col is None or eff_col is None:
        return pd.DataFrame(), pd.DataFrame([{"feature_family": "DealerGamma", "availability_status": "unavailable", "availability_failure_reason": "required_columns_missing"}])
    work = raw.copy()
    work["target_market"] = work[target_col].astype(str).str.upper()
    work["effective_ts"] = pd.to_datetime(work[eff_col], utc=True, errors="coerce")
    work["feature_asof_ts"] = pd.to_datetime(work[asof_col], utc=True, errors="coerce")
    work["quality"] = work[quality_col].astype(str).str.lower() if quality_col else "unknown"
    observed_col = cols.get("raw_option_chain_snapshot") or cols.get("observed_raw_chain") or cols.get("raw_chain_present")
    if observed_col:
        observed_mask = work[observed_col].astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        observed_mask = work.get("dealer_feature_sample_type", pd.Series([""] * len(work))).astype(str).eq("observed_raw_chain_primary")
    data_type_col = cols.get("data_type")
    if data_type_col:
        data_type_mask = work[data_type_col].astype(str).str.lower().str.contains("raw|reconstructed")
    else:
        data_type_mask = pd.Series([True] * len(work), index=work.index)
    dealer_observed_col = cols.get("dealer_position_observed")
    if dealer_observed_col:
        dealer_position_unobserved = ~work[dealer_observed_col].astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        dealer_position_unobserved = pd.Series([True] * len(work), index=work.index)
    work = work[observed_mask & data_type_mask & dealer_position_unobserved & work["quality"].isin(["medium", "high"])]
    if work.empty:
        return pd.DataFrame(), pd.DataFrame([{"feature_family": "DealerGamma", "availability_status": "unavailable", "availability_failure_reason": "no_observed_medium_or_better_raw_chain"}])
    for _, outcome in daily_outcomes.iterrows():
        decision_ts = parse_ts(outcome["decision_timestamp_utc"])
        if decision_ts is None:
            continue
        target = str(outcome["target_market"]).upper()
        max_age = safe_float(cfg.get("max_feature_age_hours", 96), 96)
        subset = work[
            (work["target_market"].eq(target))
            & (work["effective_ts"] <= decision_ts)
            & (work["feature_asof_ts"] <= decision_ts)
        ].copy()
        subset["feature_age_hours"] = (decision_ts - subset["effective_ts"]).dt.total_seconds() / 3600
        subset = subset[subset["feature_age_hours"] <= max_age]
        if subset.empty:
            continue
        feat = subset.sort_values("effective_ts").iloc[-1]
        row = outcome.to_dict()
        flip_state = str(feat.get(cols.get("gamma_flip_state", "gamma_flip_state"), "unavailable"))
        distance = safe_float(feat.get(cols.get("gamma_flip_distance_pct", "gamma_flip_distance_pct"), np.nan))
        if flip_state == "no_local_flip":
            distance = np.nan
        row.update({
            "analysis_id": f"dealer_gamma_{target}_{decision_ts.date()}",
            "feature_family": "DealerGamma",
            "feature_name": "observed_raw_chain_proxy_set",
            "feature_value": safe_float(feat.get(cols.get("net_gex_proxy", "net_gex_proxy"), np.nan)),
            "feature_unit": "proxy",
            "feature_as_of_timestamp_utc": feat.get(asof_col, ""),
            "effective_available_at_utc": feat.get(eff_col, ""),
            "feature_age_hours": safe_float(feat.get("feature_age_hours")),
            "availability_basis": "effective_available_at_utc",
            "availability_confidence": "medium",
            "source_path_or_provider": feat.get("source_path_or_provider", ""),
            "source_hash_or_request_id": "",
            "dealer_feature_sample_type": "observed_raw_chain_primary",
            "gamma_flip_state": flip_state if flip_state in {"local_flip_found", "no_local_flip", "unavailable"} else "unavailable",
            "gamma_flip_distance_pct": distance,
            "net_gex_proxy": safe_float(feat.get(cols.get("net_gex_proxy", "net_gex_proxy"), np.nan)),
            "pinning_proxy": safe_float(feat.get(cols.get("pinning_proxy", "pinning_proxy"), np.nan)),
            "local_flip_found_flag": int(flip_state == "local_flip_found"),
            "no_local_flip_flag": int(flip_state == "no_local_flip"),
            "sign_convention": "positive_net_gex_proxy_means_long_gamma_proxy_not_dealer_inventory",
            "is_proxy": True,
            "dealer_position_observed": False,
            "data_type": "reconstructed_from_raw_chain",
            "observed_flow": False,
            "raw_chain_quality": feat.get("quality", "unknown"),
            "row_economic_quality": feat.get("quality", "unknown"),
            "quality_grade": feat.get("quality", "unknown"),
            "availability_status": "available",
            "availability_failure_reason": "",
            "analysis_mode": "reconstructed_proxy_primary",
        })
        rows.append(row)
    audit.append(feature_audit_row(
        feature_family="DealerGamma",
        feature_name="observed_raw_chain_proxy_set",
        availability_status="available" if rows else "unavailable",
        availability_failure_reason="" if rows else "no_temporally_available_observed_rows",
        data_type="reconstructed_from_raw_chain",
        observed_flow=False,
        quality_grade="medium" if rows else "unavailable",
    ) | {"sample_count": len(rows)})
    return pd.DataFrame(rows), pd.DataFrame(audit)


def expiry_comparison_group(day: pd.Timestamp, expiry: pd.DataFrame) -> str:
    if day.weekday() != 4:
        return "non_friday"
    flags = expiry_flags_for_date(expiry, day)
    rows = expiry[expiry["date"].astype(str).eq(day.date().isoformat())] if not expiry.empty and "date" in expiry.columns else pd.DataFrame()
    expiry_type = " ".join(rows.get("expiry_type", pd.Series(dtype=str)).astype(str).str.lower().tolist())
    if flags["triple_witching_flag"]:
        return "triple_witching"
    if flags["quarterly_expiry_flag"]:
        return "quarterly_expiry_non_triple"
    if flags["monthly_expiry_flag"] or "monthly" in expiry_type:
        return "monthly_expiry_non_quarterly"
    return "non_expiry_friday"


def build_dealer_gamma_expiry_event_panel(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    expiry = load_expiry_calendar(root)
    if daily_outcomes.empty:
        return pd.DataFrame(), pd.DataFrame([{"module": "DealerGammaExpiry", "audit_status": "insufficient_data", "reason": "daily_outcomes_missing"}])
    raw = load_dealer_gamma_history(root)
    rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for _, outcome in daily_outcomes.iterrows():
        target = str(outcome["target_market"]).upper()
        day = pd.Timestamp(outcome.get("decision_date") or pd.to_datetime(outcome["decision_timestamp_utc"]).date())
        group = expiry_comparison_group(day, expiry)
        if group == "non_friday":
            continue
        decision_ts = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert(UTC)
        feature_available = False
        if not raw.empty:
            cols = {str(c).lower(): c for c in raw.columns}
            target_col = cols.get("ticker") or cols.get("asset") or cols.get("target_market")
            eff_col = cols.get("effective_available_at_utc") or cols.get("snapshot_timestamp_utc") or cols.get("feature_as_of_timestamp_utc")
            if target_col and eff_col:
                work = raw.copy()
                work["target_market"] = work[target_col].astype(str).str.upper()
                work["effective_ts"] = pd.to_datetime(work[eff_col], utc=True, errors="coerce")
                feature_available = not work[(work["target_market"].eq(target)) & (work["effective_ts"] <= decision_ts)].empty
        flags = expiry_flags_for_date(expiry, day)
        row = outcome.to_dict()
        row.update({
            "analysis_id": f"dealer_gamma_expiry_{target}_{day.date()}",
            "feature_family": "DealerGammaExpiry",
            "feature_name": group,
            "feature_value": flags["monthly_expiry_flag"] + flags["quarterly_expiry_flag"] + flags["triple_witching_flag"],
            "feature_unit": "event_flag",
            "feature_as_of_timestamp_utc": decision_ts.isoformat(),
            "effective_available_at_utc": decision_ts.isoformat(),
            "decision_timestamp_utc": decision_ts.isoformat(),
            "feature_age_hours": 0.0,
            "availability_basis": "expiry_calendar_prior_available_at_open",
            "availability_confidence": "high",
            "source_path_or_provider": str(EXPIRY_CALENDAR_PATH).replace("\\", "/"),
            "data_type": "calendar_event",
            "is_proxy": False,
            "observed_flow": False,
            "quality_grade": "high",
            "availability_status": "available",
            "availability_failure_reason": "",
            "comparison_group": group,
            "monthly_expiry_flag": flags["monthly_expiry_flag"],
            "quarterly_expiry_flag": flags["quarterly_expiry_flag"],
            "triple_witching_flag": flags["triple_witching_flag"],
            "prior_available_gamma_context": feature_available,
            "primary_or_robustness": "primary",
        })
        rows.append(row)
    if expiry.empty:
        audit_rows.append({"module": "DealerGammaExpiry", "audit_status": "insufficient_data", "reason": "expiry_calendar_missing"})
    else:
        audit_rows.append({"module": "DealerGammaExpiry", "audit_status": "available" if rows else "insufficient_data", "reason": "" if rows else "no_expiry_or_friday_rows", "event_rows": len(rows)})
    return pd.DataFrame(rows), pd.DataFrame(audit_rows)


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    n = len(p_values)
    if n == 0:
        return []
    order = np.argsort(p_values)
    adjusted = np.empty(n)
    prev = 1.0
    for rank, idx in enumerate(order[::-1], start=1):
        original_rank = n - rank + 1
        val = min(prev, p_values[idx] * n / original_rank)
        adjusted[idx] = val
        prev = val
    return adjusted.tolist()


def summarize_association(panel: pd.DataFrame, feature_family: str, outcome_col: str, feature_col: str, primary: str = "primary") -> pd.DataFrame:
    cols = ["feature_family", "feature_name", "target_market", "outcome", "sample_count", "effect_size", "effect_size_bps", "raw_p_value", "adjusted_p_value", "multiple_testing_method", "primary_or_robustness", "evidence_engine", "evidence_verdict"]
    if panel.empty or feature_col not in panel.columns or outcome_col not in panel.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    pvals = []
    for target, group in panel.groupby("target_market"):
        work = group[[feature_col, outcome_col]].copy()
        work[feature_col] = pd.to_numeric(work[feature_col], errors="coerce")
        work[outcome_col] = pd.to_numeric(work[outcome_col], errors="coerce")
        work = work.dropna()
        n = len(work)
        if n < 30 or work[feature_col].std() == 0:
            effect = np.nan
            p = 1.0
            verdict = "insufficient_data"
        else:
            corr = work[feature_col].corr(work[outcome_col])
            effect = corr
            p = max(0.0, min(1.0, 1.0 - abs(corr)))
            verdict = "exploratory_association" if abs(corr) > 0.05 else "no_incremental_value"
        pvals.append(p)
        rows.append({
            "feature_family": feature_family,
            "feature_name": feature_col,
            "target_market": target,
            "outcome": outcome_col,
            "sample_count": n,
            "effect_size": effect,
            "effect_size_bps": effect * 10000 if pd.notna(effect) else np.nan,
            "raw_p_value": p,
            "adjusted_p_value": np.nan,
            "multiple_testing_method": "benjamini_hochberg",
            "primary_or_robustness": primary,
            "evidence_engine": "descriptive_association_only",
            "evidence_verdict": verdict,
        })
    adj = benjamini_hochberg(pvals)
    for row, p in zip(rows, adj):
        row["adjusted_p_value"] = p
    return pd.DataFrame(rows, columns=cols)


def encode_model_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for col in columns:
        if col not in df.columns:
            pieces.append(pd.DataFrame({col: np.nan}, index=df.index))
            continue
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        numeric = pd.to_numeric(series, errors="coerce")
        non_null_ratio = numeric.notna().mean()
        if non_null_ratio >= 0.8 or series.dropna().empty:
            pieces.append(pd.DataFrame({col: numeric}, index=df.index))
        else:
            dummies = pd.get_dummies(series.astype(str), prefix=col, dummy_na=False)
            pieces.append(dummies.reindex(df.index))
    if not pieces:
        return pd.DataFrame(index=df.index)
    return pd.concat(pieces, axis=1)


def ridge_predict(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_test: pd.DataFrame,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    means = x_train.mean(axis=0)
    stds = x_train.std(axis=0).replace(0, 1).fillna(1)
    xtr = ((x_train - means) / stds).fillna(0).to_numpy(dtype=float)
    xte = ((x_test - means) / stds).fillna(0).to_numpy(dtype=float)
    xtr = np.column_stack([np.ones(len(xtr)), xtr])
    xte = np.column_stack([np.ones(len(xte)), xte])
    y = pd.to_numeric(y_train, errors="coerce").to_numpy(dtype=float)
    penalty = np.eye(xtr.shape[1]) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(xtr.T @ xtr + penalty) @ xtr.T @ y
    return xte @ beta, beta, stds.to_numpy(dtype=float)


def expanding_monthly_oos_predictions(
    frame: pd.DataFrame,
    outcome_col: str,
    baseline_cols: list[str],
    feature_cols: list[str],
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    stat = cfg.get("statistical", {})
    alpha = safe_float(stat.get("ridge_alpha", 1.0), 1.0)
    min_train = int(cfg.get("walk_forward", {}).get("minimum_train_observations", 252))
    work = frame.copy()
    work["decision_ts"] = pd.to_datetime(work["decision_timestamp_utc"], utc=True, errors="coerce")
    work["test_month"] = work["decision_ts"].dt.tz_convert(ET).dt.to_period("M").astype(str)
    y = pd.to_numeric(work[outcome_col], errors="coerce")
    baseline_cols = list(dict.fromkeys(baseline_cols))
    feature_cols = list(dict.fromkeys(feature_cols))
    augmented_cols = list(dict.fromkeys(baseline_cols + feature_cols))
    x_base = encode_model_frame(work, baseline_cols)
    x_aug = encode_model_frame(work, augmented_cols)
    keep = y.notna()
    for col in x_base.columns:
        keep &= x_base[col].notna()
    for col in x_aug.columns:
        keep &= x_aug[col].notna()
    work = work.loc[keep].reset_index(drop=True)
    y = y.loc[keep].reset_index(drop=True)
    x_base = x_base.loc[keep].reset_index(drop=True)
    x_aug = x_aug.loc[keep].reset_index(drop=True)
    months = sorted(work["test_month"].dropna().unique().tolist())
    pred_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    effect_coefs: list[float] = []
    for month in months:
        train_idx = work.index[work["test_month"] < month].to_numpy()
        test_idx = work.index[work["test_month"] == month].to_numpy()
        if len(train_idx) < min_train or len(test_idx) == 0:
            fold_rows.append({
                "test_month": month,
                "sample_count_train": len(train_idx),
                "sample_count_oos": len(test_idx),
                "fold_status": "insufficient_train",
            })
            continue
        base_pred, _, _ = ridge_predict(x_base.iloc[train_idx], y.iloc[train_idx], x_base.iloc[test_idx], alpha)
        aug_pred, aug_beta, _ = ridge_predict(x_aug.iloc[train_idx], y.iloc[train_idx], x_aug.iloc[test_idx], alpha)
        hist_mean = float(y.iloc[train_idx].mean())
        feature_dummy_cols = encode_model_frame(work, feature_cols).columns.tolist()
        aug_cols = x_aug.columns.tolist()
        coef_values = [aug_beta[aug_cols.index(c) + 1] for c in feature_dummy_cols if c in aug_cols]
        if coef_values:
            effect_coefs.append(float(np.nanmean(coef_values)))
        for idx, bp, ap in zip(test_idx, base_pred, aug_pred):
            pred_rows.append({
                "row_index": int(idx),
                "decision_timestamp_utc": work.loc[idx, "decision_timestamp_utc"],
                "test_month": month,
                "y_true": y.iloc[idx],
                "baseline_pred": bp,
                "augmented_pred": ap,
                "historical_mean_pred": hist_mean,
            })
        fold_rows.append({
            "test_month": month,
            "sample_count_train": len(train_idx),
            "sample_count_oos": len(test_idx),
            "fold_status": "tested",
        })
    return pd.DataFrame(pred_rows), pd.DataFrame(fold_rows), float(np.nanmean(effect_coefs)) if effect_coefs else np.nan


def moving_block_bootstrap_delta_ci(
    augmented_errors: np.ndarray,
    baseline_errors: np.ndarray,
    block_length: int,
    iterations: int,
    seed: int,
) -> tuple[float, float, float]:
    n = len(augmented_errors)
    if n == 0:
        return np.nan, np.nan, 1.0
    block_length = max(1, min(block_length, n))
    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    starts = np.arange(0, n)
    for _ in range(max(1, iterations)):
        picked: list[int] = []
        while len(picked) < n:
            start = int(rng.choice(starts))
            picked.extend([(start + j) % n for j in range(block_length)])
        idx = np.array(picked[:n])
        deltas.append(float(np.mean(augmented_errors[idx]) - np.mean(baseline_errors[idx])))
    observed = float(np.mean(augmented_errors) - np.mean(baseline_errors))
    raw_p = min(1.0, 2.0 * min(np.mean(np.array(deltas) <= 0), np.mean(np.array(deltas) >= 0)))
    return float(np.quantile(deltas, 0.025)), float(np.quantile(deltas, 0.975)), raw_p if pd.notna(raw_p) else 1.0


def run_oos_comparison(
    panel: pd.DataFrame,
    *,
    module: str,
    test_family: str,
    feature_sets: dict[str, list[str]],
    outcomes: list[str],
    baseline_cols: list[str],
    cfg: dict[str, Any],
    min_oos_rows: int,
    min_test_months: int,
    primary_or_robustness: str = "primary",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result_cols = [
        "module",
        "test_family",
        "feature_family",
        "feature_name",
        "target_market",
        "outcome",
        "primary_or_robustness",
        "sample_count_train",
        "sample_count_oos",
        "test_month_count",
        "oos_mse",
        "oos_mae",
        "oos_r2_vs_historical_mean",
        "oos_r2_vs_baseline",
        "delta_oos_mse_vs_baseline",
        "delta_oos_mae_vs_baseline",
        "effect_size_per_1sd_feature",
        "bootstrap_delta_mse_ci_low",
        "bootstrap_delta_mse_ci_high",
        "bootstrap_block_length",
        "bootstrap_iterations",
        "random_seed",
        "raw_p_value",
        "adjusted_p_value",
        "multiple_testing_method",
        "subperiod_pre_2023_delta_oos_mse",
        "subperiod_2023_onward_delta_oos_mse",
        "evidence_engine",
        "evidence_verdict",
    ]
    fold_rows: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return pd.DataFrame(columns=result_cols), pd.DataFrame(columns=["module", "target_market", "feature_name", "outcome", "test_month", "sample_count_train", "sample_count_oos", "fold_status"])
    stat = cfg.get("statistical", {})
    block_len = int(stat.get("bootstrap_block_length", 5))
    iterations = int(stat.get("bootstrap_iterations", 1000))
    seed = int(stat.get("random_seed", 42))
    for target, target_panel in panel.groupby("target_market"):
        for outcome_col in outcomes:
            if outcome_col not in target_panel.columns:
                continue
            for feature_name, feature_cols in feature_sets.items():
                required = list(dict.fromkeys(["decision_timestamp_utc", outcome_col] + baseline_cols + feature_cols))
                if not set(required).issubset(set(target_panel.columns)):
                    missing = sorted(set(required) - set(target_panel.columns))
                    rows.append({
                        "module": module,
                        "test_family": test_family,
                        "feature_family": module,
                        "feature_name": feature_name,
                        "target_market": target,
                        "outcome": outcome_col,
                        "primary_or_robustness": primary_or_robustness,
                        "sample_count_train": 0,
                        "sample_count_oos": 0,
                        "test_month_count": 0,
                        "evidence_engine": "expanding_window_oos_ridge",
                        "evidence_verdict": "insufficient_data",
                        "availability_failure_reason": "missing_columns:" + ",".join(missing),
                    })
                    continue
                preds, folds, effect = expanding_monthly_oos_predictions(target_panel[required].copy(), outcome_col, baseline_cols, feature_cols, cfg)
                if not folds.empty:
                    f = folds.copy()
                    f.insert(0, "outcome", outcome_col)
                    f.insert(0, "feature_name", feature_name)
                    f.insert(0, "target_market", target)
                    f.insert(0, "module", module)
                    fold_rows.append(f)
                tested = folds[folds.get("fold_status", pd.Series(dtype=str)).eq("tested")] if not folds.empty else pd.DataFrame()
                oos_n = len(preds)
                test_month_count = int(tested["test_month"].nunique()) if not tested.empty else 0
                train_n = int(tested["sample_count_train"].median()) if not tested.empty else 0
                if preds.empty:
                    mse = mae = r2_hist = r2_base = delta_mse = delta_mae = np.nan
                    ci_low = ci_high = np.nan
                    raw_p = 1.0
                else:
                    y = pd.to_numeric(preds["y_true"], errors="coerce").to_numpy(dtype=float)
                    aug = pd.to_numeric(preds["augmented_pred"], errors="coerce").to_numpy(dtype=float)
                    base = pd.to_numeric(preds["baseline_pred"], errors="coerce").to_numpy(dtype=float)
                    hist = pd.to_numeric(preds["historical_mean_pred"], errors="coerce").to_numpy(dtype=float)
                    aug_err = (y - aug) ** 2
                    base_err = (y - base) ** 2
                    hist_err = (y - hist) ** 2
                    mse = float(np.mean(aug_err))
                    mae = float(np.mean(np.abs(y - aug)))
                    base_mse = float(np.mean(base_err))
                    base_mae = float(np.mean(np.abs(y - base)))
                    hist_mse = float(np.mean(hist_err))
                    r2_hist = 1.0 - mse / hist_mse if hist_mse > 0 else np.nan
                    r2_base = 1.0 - mse / base_mse if base_mse > 0 else np.nan
                    delta_mse = mse - base_mse
                    delta_mae = mae - base_mae
                    ci_low, ci_high, raw_p = moving_block_bootstrap_delta_ci(aug_err, base_err, block_len, iterations, seed)
                pre_delta = np.nan
                post_delta = np.nan
                if not preds.empty:
                    pred_work = preds.copy()
                    pred_work["year"] = pd.to_datetime(pred_work["decision_timestamp_utc"], utc=True, errors="coerce").dt.year
                    for label, mask in [("pre", pred_work["year"] < 2023), ("post", pred_work["year"] >= 2023)]:
                        sub = pred_work[mask]
                        if not sub.empty:
                            sub_y = pd.to_numeric(sub["y_true"], errors="coerce")
                            sub_aug = pd.to_numeric(sub["augmented_pred"], errors="coerce")
                            sub_base = pd.to_numeric(sub["baseline_pred"], errors="coerce")
                            sub_delta = float(np.mean((sub_y - sub_aug) ** 2) - np.mean((sub_y - sub_base) ** 2))
                            if label == "pre":
                                pre_delta = sub_delta
                            else:
                                post_delta = sub_delta
                verdict = "passed" if oos_n >= min_oos_rows and test_month_count >= min_test_months else "insufficient_data"
                rows.append({
                    "module": module,
                    "test_family": test_family,
                    "feature_family": module,
                    "feature_name": feature_name,
                    "target_market": target,
                    "outcome": outcome_col,
                    "primary_or_robustness": primary_or_robustness,
                    "sample_count_train": train_n,
                    "sample_count_oos": oos_n,
                    "test_month_count": test_month_count,
                    "oos_mse": mse,
                    "oos_mae": mae,
                    "oos_r2_vs_historical_mean": r2_hist,
                    "oos_r2_vs_baseline": r2_base,
                    "delta_oos_mse_vs_baseline": delta_mse,
                    "delta_oos_mae_vs_baseline": delta_mae,
                    "effect_size_per_1sd_feature": effect,
                    "bootstrap_delta_mse_ci_low": ci_low,
                    "bootstrap_delta_mse_ci_high": ci_high,
                    "bootstrap_block_length": block_len,
                    "bootstrap_iterations": iterations,
                    "random_seed": seed,
                    "raw_p_value": raw_p,
                    "adjusted_p_value": np.nan,
                    "multiple_testing_method": "benjamini_hochberg",
                    "subperiod_pre_2023_delta_oos_mse": pre_delta,
                    "subperiod_2023_onward_delta_oos_mse": post_delta,
                    "evidence_engine": "expanding_window_oos_ridge",
                    "evidence_verdict": verdict,
                })
    result = pd.DataFrame(rows)
    if result.empty:
        result = pd.DataFrame(columns=result_cols)
    elif "raw_p_value" in result.columns:
        result["adjusted_p_value"] = benjamini_hochberg(pd.to_numeric(result["raw_p_value"], errors="coerce").fillna(1.0).tolist())
    result = ensure_columns(result, result_cols)
    fold_audit = pd.concat(fold_rows, ignore_index=True) if fold_rows else pd.DataFrame(columns=["module", "target_market", "feature_name", "outcome", "test_month", "sample_count_train", "sample_count_oos", "fold_status"])
    return result, fold_audit


def build_walk_forward_manifest(sample_count: int, cfg: dict[str, Any]) -> dict[str, Any]:
    wf = cfg.get("walk_forward", {})
    minimum = int(wf.get("minimum_train_observations", 252))
    return {
        "method": "expanding_window",
        "random_split_used": False,
        "minimum_train_observations": minimum,
        "sample_count": sample_count,
        "oos_available": sample_count > minimum,
        "test_block": wf.get("test_block", "monthly"),
    }


def build_no_lookahead_audit(feature_join: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    cols = [
        "module",
        "feature_family",
        "target_market",
        "decision_timestamp_utc",
        "feature_as_of_timestamp_utc",
        "effective_available_at_utc",
        "no_lookahead_passed",
        "violation_reason",
    ]
    if feature_join.empty:
        return pd.DataFrame(columns=cols), "not_run"
    rows: list[dict[str, Any]] = []
    for _, row in feature_join.iterrows():
        decision_ts = parse_ts(row.get("decision_timestamp_utc"))
        asof_ts = parse_ts(row.get("feature_as_of_timestamp_utc"))
        eff_ts = parse_ts(row.get("effective_available_at_utc"))
        reasons = []
        if decision_ts is None:
            reasons.append("decision_timestamp_missing")
        if decision_ts is not None and asof_ts is not None and asof_ts > decision_ts:
            reasons.append("feature_asof_after_decision")
        if decision_ts is not None and eff_ts is not None and eff_ts > decision_ts:
            reasons.append("effective_after_decision")
        rows.append({
            "module": row.get("module", ""),
            "feature_family": row.get("feature_family", ""),
            "target_market": row.get("target_market", ""),
            "decision_timestamp_utc": row.get("decision_timestamp_utc", ""),
            "feature_as_of_timestamp_utc": row.get("feature_as_of_timestamp_utc", ""),
            "effective_available_at_utc": row.get("effective_available_at_utc", ""),
            "no_lookahead_passed": len(reasons) == 0,
            "violation_reason": ";".join(reasons),
        })
    audit = pd.DataFrame(rows, columns=cols)
    return audit, "passed" if bool(audit["no_lookahead_passed"].all()) else "failed"


def research_gate_from_oos(results: pd.DataFrame, engine_requested: bool) -> str:
    if not engine_requested:
        return "not_run"
    if results.empty:
        return "insufficient_data"
    if results["evidence_verdict"].astype(str).eq("passed").any():
        return "passed"
    return "insufficient_data"


def market_data_gate(feature_join: pd.DataFrame, no_lookahead_status: str) -> str:
    if feature_join.empty:
        return "insufficient_data"
    if no_lookahead_status == "failed":
        return "failed"
    return "passed"


def refresh_status_rows(refresh_daily_prices: bool, refresh_intraday_prices: bool, run_gamma_surrogate_exploration: bool) -> list[dict[str, Any]]:
    rows = []
    for flag_name, enabled in [
        ("refresh_daily_prices", refresh_daily_prices),
        ("refresh_intraday_prices", refresh_intraday_prices),
        ("run_gamma_surrogate_exploration", run_gamma_surrogate_exploration),
    ]:
        if enabled:
            rows.append({
                "module": "RefreshAdapter",
                "operation": flag_name,
                "status": "not_supported",
                "reason": "refresh_adapter_not_implemented",
            })
    return rows


def source_inventory(root: Path) -> pd.DataFrame:
    paths = [
        root / "market_bomb_history" / "cta_proxy_history.csv",
        root / "market_bomb_history" / "vol_control_proxy_history.csv",
        root / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "leveraged_etf_aum_history.csv",
    ]
    rows = []
    for path in paths:
        rows.append({
            "source_path_or_provider": str(path.relative_to(root)).replace("\\", "/") if path.exists() else str(path.relative_to(root)).replace("\\", "/"),
            "exists": path.exists(),
            "source_hash_or_request_id": hash_file(path) if path.exists() and path.is_file() else "",
            "file_size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
        })
    return pd.DataFrame(rows)


def write_reports(
    root: Path,
    cta_oos: pd.DataFrame,
    lev_oos: pd.DataFrame,
    dealer_oos: pd.DataFrame,
    expiry_oos: pd.DataFrame,
    gate: dict[str, Any],
    refresh_rows: list[dict[str, Any]] | None = None,
) -> None:
    reports = root / OUTPUT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    header = (
        "feature is proxy: true\n\n"
        "observed flow: false\n\n"
        "dealer inventory observed: false\n\n"
        f"no-lookahead status: `{gate.get('no_lookahead_status', 'unknown')}`\n\n"
        f"actionization_gate: `{str(gate.get('actionization_gate', False)).lower()}`\n\n"
    )
    (reports / "cta_vol_market_impact_primary.md").write_text(header + markdown_table(cta_oos) + "\n", encoding="utf-8")
    (reports / "leveraged_etf_intraday_impact_primary.md").write_text(header + markdown_table(lev_oos) + "\n", encoding="utf-8")
    (reports / "dealer_gamma_observed_primary.md").write_text(header + markdown_table(dealer_oos) + "\n", encoding="utf-8")
    (reports / "dealer_gamma_expiry_event_study.md").write_text(header + markdown_table(expiry_oos) + "\n", encoding="utf-8")
    gamma_status = "not_implemented" if refresh_rows and any(r.get("operation") == "run_gamma_surrogate_exploration" for r in refresh_rows) else "not_run"
    (reports / "gamma_surrogate_exploratory.md").write_text(
        f"status: `{gamma_status}`\n\nfeature is proxy: true\n\nprimary result mixed: false\n\ngamma surrogate is disabled by default and is not a silent no-op.\n",
        encoding="utf-8",
    )
    (reports / "combined_feature_robustness.md").write_text("Combined model is exploratory only and not used for actionization in v1.\n", encoding="utf-8")
    (reports / "data_sufficiency_report.md").write_text(markdown_table(pd.DataFrame([gate])) + "\n", encoding="utf-8")


def gate_audit_text(gate: dict[str, Any]) -> str:
    return (
        "# Market Impact Backtest Gate Audit\n\n"
        f"market_impact_data_gate: `{gate['market_impact_data_gate']}`\n\n"
        f"cta_vol_primary_research_gate: `{gate['cta_vol_primary_research_gate']}`\n\n"
        f"leveraged_etf_primary_research_gate: `{gate['leveraged_etf_primary_research_gate']}`\n\n"
        f"dealer_gamma_primary_research_gate: `{gate['dealer_gamma_primary_research_gate']}`\n\n"
        f"dealer_gamma_expiry_research_gate: `{gate.get('dealer_gamma_expiry_research_gate', 'not_run')}`\n\n"
        f"actionization_gate: `{str(gate['actionization_gate']).lower()}`\n\n"
        f"no_lookahead_status: `{gate['no_lookahead_status']}`\n\n"
        f"insufficient_data_modules: `{gate['insufficient_data_modules']}`\n\n"
    )


def run(
    root: Path = Path("."),
    refresh_daily_prices: bool = False,
    refresh_intraday_prices: bool = False,
    run_cta_vol_analysis: bool = True,
    run_leveraged_etf_analysis: bool = True,
    run_dealer_observed_analysis: bool = True,
    run_gamma_surrogate_exploration: bool = False,
) -> dict[str, Path]:
    cfg = rules(root)
    base_cfg = baseline_config(root)
    mappings = feature_mappings(root)
    _sources_cfg = data_sources_config(root)
    out = root / OUTPUT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    reports = out / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    targets = list(cfg.get("targets", ["QQQ", "SPY", "SOXX", "SMH"]))
    prices = load_price_history(root, targets)
    daily_outcomes = build_daily_outcomes(prices)
    expiry_calendar = load_expiry_calendar(root)
    daily_baseline = build_daily_baseline(prices, expiry_calendar)
    cta_panel, availability, no_lookahead = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    if run_cta_vol_analysis:
        cta_panel, availability, no_lookahead = build_cta_vol_feature_outcome_panel(root, daily_outcomes, cfg)
        cta_panel = attach_daily_baseline(cta_panel, daily_baseline)
    lev_panel, lev_audit = (pd.DataFrame(), pd.DataFrame())
    if run_leveraged_etf_analysis:
        lev_panel, lev_audit = build_leveraged_etf_panel(root, cfg)
    dealer_panel, dealer_audit = (pd.DataFrame(), pd.DataFrame())
    if run_dealer_observed_analysis:
        dealer_panel, dealer_audit = build_dealer_gamma_panel(root, daily_outcomes, cfg)
        dealer_panel = attach_daily_baseline(dealer_panel, daily_baseline)
    expiry_panel, expiry_audit = build_dealer_gamma_expiry_event_panel(root, daily_outcomes, cfg)
    expiry_panel = attach_daily_baseline(expiry_panel, daily_baseline)

    min_cfg = cfg.get("minimum_samples", {})
    cta_oos, cta_folds = run_oos_comparison(
        cta_panel,
        module="CTA_Vol",
        test_family="cta_vol_primary",
        feature_sets={
            "CTA_only": mappings.get("cta_only", []),
            "Vol_only": mappings.get("vol_only", []),
            "CTA_plus_Vol": mappings.get("cta_plus_vol", []),
        },
        outcomes=["next_session_absolute_return", "next_session_high_low_range_pct", "forward_realized_vol_5d"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("cta_vol_min_oos_rows_per_target", 252)),
        min_test_months=int(min_cfg.get("cta_vol_min_test_months", 6)),
    )
    lev_oos, lev_folds = run_oos_comparison(
        lev_panel,
        module="LeveragedETF",
        test_family="leveraged_etf_primary",
        feature_sets={"LeveragedETF_pressure": mappings.get("leveraged_etf", [])},
        outcomes=["intraday_absolute_return_1530_to_close", "intraday_range_1530_to_close"],
        baseline_cols=base_cfg.get("intraday", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("leveraged_etf_min_oos_rows", 126)),
        min_test_months=int(min_cfg.get("leveraged_etf_min_test_months", 6)),
    )
    dealer_oos, dealer_folds = run_oos_comparison(
        dealer_panel,
        module="DealerGamma",
        test_family="dealer_gamma_observed_primary",
        feature_sets={"DealerGamma_raw_chain_proxy": mappings.get("dealer_gamma", [])},
        outcomes=["next_session_high_low_range_pct", "next_session_absolute_return", "forward_realized_vol_5d"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("dealer_gamma_min_oos_rows", 100)),
        min_test_months=int(min_cfg.get("dealer_gamma_min_test_months", 6)),
    )
    expiry_oos, expiry_folds = run_oos_comparison(
        expiry_panel,
        module="DealerGammaExpiry",
        test_family="dealer_gamma_expiry_event",
        feature_sets={"expiry_event_flags": mappings.get("expiry_event", [])},
        outcomes=["next_session_absolute_return", "next_session_high_low_range_pct"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("dealer_expiry_min_event_rows_per_comparison_group", 20)),
        min_test_months=1,
    )
    summary = pd.concat([cta_oos, lev_oos, dealer_oos, expiry_oos], ignore_index=True)
    descriptive_summary = pd.concat([
        summarize_association(cta_panel, "CTA_Vol", "next_session_absolute_return", "cta_exposure_change_proxy", "descriptive"),
        summarize_association(lev_panel, "LeveragedETF", "intraday_absolute_return_1530_to_close", "aggregate_pressure_usd", "descriptive"),
        summarize_association(dealer_panel, "DealerGamma", "next_session_high_low_range_pct", "gamma_flip_distance_pct", "descriptive"),
    ], ignore_index=True)

    data_quality = pd.DataFrame([
        {"module": "CTA_Vol", "sample_count": len(cta_panel), "coverage_rate": len(cta_panel) / max(len(daily_outcomes), 1), "verdict": "passed" if len(cta_panel) else "insufficient_data"},
        {"module": "LeveragedETF", "sample_count": len(lev_panel), "coverage_rate": np.nan, "verdict": "passed" if len(lev_panel) else "insufficient_data"},
        {"module": "DealerGamma", "sample_count": len(dealer_panel), "coverage_rate": np.nan, "verdict": "passed" if len(dealer_panel) else "insufficient_data"},
        {"module": "DealerGammaExpiry", "sample_count": len(expiry_panel), "coverage_rate": np.nan, "verdict": "passed" if len(expiry_panel) else "insufficient_data"},
    ])
    inventory = source_inventory(root)
    cta_panel = ensure_columns(cta_panel, PANEL_COMMON_COLUMNS)
    lev_panel = ensure_columns(lev_panel, PANEL_COMMON_COLUMNS)
    dealer_panel = ensure_columns(dealer_panel, PANEL_COMMON_COLUMNS)
    expiry_panel = ensure_columns(expiry_panel, PANEL_COMMON_COLUMNS)
    feature_join = pd.concat([
        cta_panel.assign(module="CTA_Vol") if not cta_panel.empty else pd.DataFrame(),
        lev_panel.assign(module="LeveragedETF") if not lev_panel.empty else pd.DataFrame(),
        dealer_panel.assign(module="DealerGamma") if not dealer_panel.empty else pd.DataFrame(),
        expiry_panel.assign(module="DealerGammaExpiry") if not expiry_panel.empty else pd.DataFrame(),
    ], ignore_index=True)
    feature_join = ensure_columns(feature_join, PANEL_COMMON_COLUMNS)
    no_lookahead, no_lookahead_status = build_no_lookahead_audit(feature_join)
    refresh_rows = refresh_status_rows(refresh_daily_prices, refresh_intraday_prices, run_gamma_surrogate_exploration)
    if refresh_rows:
        data_quality = pd.concat([data_quality, pd.DataFrame(refresh_rows).rename(columns={"status": "verdict"})], ignore_index=True)
    insufficient = ",".join(data_quality.loc[data_quality["verdict"].astype(str).isin(["insufficient_data", "not_supported"]), "module"].astype(str))
    gate = {
        "market_impact_data_gate": market_data_gate(feature_join, no_lookahead_status),
        "cta_vol_primary_research_gate": research_gate_from_oos(cta_oos, run_cta_vol_analysis),
        "leveraged_etf_primary_research_gate": research_gate_from_oos(lev_oos, run_leveraged_etf_analysis),
        "dealer_gamma_primary_research_gate": research_gate_from_oos(dealer_oos, run_dealer_observed_analysis),
        "dealer_gamma_expiry_research_gate": research_gate_from_oos(expiry_oos, True),
        "actionization_gate": False,
        "no_lookahead_status": no_lookahead_status,
        "insufficient_data_modules": insufficient,
    }
    manifest = {
        "analysis_id": f"market_impact_{pd.Timestamp.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}",
        "version": VERSION,
        "analysis_base_commit_sha": os.environ.get("GITHUB_SHA", ""),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "rules_version": cfg.get("version"),
        "walk_forward": build_walk_forward_manifest(len(feature_join), cfg),
        "actionization_allowed": False,
        "gates": gate,
        "refresh_status": refresh_rows,
        "gamma_surrogate_status": "not_implemented" if run_gamma_surrogate_exploration else "not_run",
    }

    write_table(inventory, out / "source_inventory.csv")
    (out / "source_inventory.md").write_text("# Source Inventory\n\n" + markdown_table(inventory) + "\n", encoding="utf-8")
    data_quality.to_csv(out / "data_quality_audit.csv", index=False)
    availability = pd.concat([availability, lev_audit, dealer_audit], ignore_index=True)
    availability = ensure_columns(availability, FEATURE_AUDIT_COLUMNS)
    availability.to_csv(out / "feature_availability_audit.csv", index=False)
    (out / "feature_availability_audit.md").write_text("# Feature Availability Audit\n\n" + markdown_table(availability) + "\n", encoding="utf-8")
    write_table(feature_join, out / "feature_outcome_join_audit.csv", out / "feature_outcome_join_audit.parquet")
    (out / "feature_outcome_join_audit.md").write_text("# Feature Outcome Join Audit\n\n" + markdown_table(feature_join) + "\n", encoding="utf-8")
    no_lookahead.to_csv(out / "no_lookahead_audit.csv", index=False)
    (out / "no_lookahead_audit.md").write_text("# No Lookahead Audit\n\n" + markdown_table(no_lookahead) + "\n", encoding="utf-8")
    write_table(daily_outcomes, out / "daily_market_outcomes.csv", out / "daily_market_outcomes.parquet")
    write_table(cta_panel, out / "cta_vol_primary_panel.csv", out / "cta_vol_primary_panel.parquet")
    write_table(cta_oos, out / "cta_vol_primary_oos_results.csv")
    write_table(cta_folds, out / "cta_vol_primary_fold_audit.csv")
    write_table(lev_panel, out / "leveraged_etf_primary_panel.csv", out / "leveraged_etf_primary_panel.parquet")
    write_table(lev_oos, out / "leveraged_etf_primary_oos_results.csv")
    write_table(lev_audit, out / "leveraged_etf_intraday_data_audit.csv")
    write_table(lev_audit, out / "leveraged_etf_universe_completeness_audit.csv")
    write_table(dealer_panel, out / "dealer_gamma_observed_primary_panel.csv", out / "dealer_gamma_observed_primary_panel.parquet")
    write_table(dealer_oos, out / "dealer_gamma_observed_primary_oos_results.csv")
    write_table(dealer_audit, out / "dealer_gamma_observed_join_audit.csv")
    write_table(expiry_panel, out / "dealer_gamma_expiry_event_panel.csv")
    write_table(expiry_oos, out / "dealer_gamma_expiry_event_oos_results.csv")
    write_table(expiry_audit, out / "dealer_gamma_expiry_event_audit.csv")
    write_table(pd.concat([cta_folds, lev_folds, dealer_folds, expiry_folds], ignore_index=True), out / "feature_fold_audit.csv")
    write_table(descriptive_summary, out / "descriptive_association_summary.csv")
    write_table(cta_panel, out / "cta_vol_market_impact_panel.csv", out / "cta_vol_market_impact_panel.parquet")
    write_table(lev_panel, out / "leveraged_etf_intraday_panel.csv", out / "leveraged_etf_intraday_panel.parquet")
    write_table(dealer_panel, out / "dealer_gamma_observed_panel.csv", out / "dealer_gamma_observed_panel.parquet")
    summary.to_csv(out / "model_comparison_summary.csv", index=False)
    expiry_calendar_out = expiry_calendar.copy()
    if not expiry_calendar_out.empty:
        expiry_calendar_out["holiday_adjusted_audited"] = expiry_calendar_out.get("holiday_adjusted_flag", False).astype(str).str.lower().isin(["true", "1", "yes"])
    expiry_calendar_out.to_csv(out / "dealer_gamma_expiry_event_study.csv", index=False)
    with (out / "analysis_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    (root / "market_impact_backtest_gate_audit.md").write_text(gate_audit_text(gate), encoding="utf-8")
    write_reports(root, cta_oos, lev_oos, dealer_oos, expiry_oos, gate, refresh_rows)
    return {
        "source_inventory": out / "source_inventory.csv",
        "feature_availability_audit": out / "feature_availability_audit.csv",
        "feature_outcome_join_audit": out / "feature_outcome_join_audit.csv",
        "no_lookahead_audit": out / "no_lookahead_audit.csv",
        "model_comparison_summary": out / "model_comparison_summary.csv",
        "cta_vol_primary_oos_results": out / "cta_vol_primary_oos_results.csv",
        "leveraged_etf_primary_oos_results": out / "leveraged_etf_primary_oos_results.csv",
        "dealer_gamma_observed_primary_oos_results": out / "dealer_gamma_observed_primary_oos_results.csv",
        "dealer_gamma_expiry_event_oos_results": out / "dealer_gamma_expiry_event_oos_results.csv",
        "gate": root / "market_impact_backtest_gate_audit.md",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--refresh-daily-prices", action="store_true")
    parser.add_argument("--refresh-intraday-prices", action="store_true")
    parser.add_argument("--skip-cta-vol-analysis", action="store_true")
    parser.add_argument("--skip-leveraged-etf-analysis", action="store_true")
    parser.add_argument("--skip-dealer-observed-analysis", action="store_true")
    parser.add_argument("--run-gamma-surrogate-exploration", action="store_true")
    args = parser.parse_args()
    outputs = run(
        Path(args.root),
        refresh_daily_prices=args.refresh_daily_prices,
        refresh_intraday_prices=args.refresh_intraday_prices,
        run_cta_vol_analysis=not args.skip_cta_vol_analysis,
        run_leveraged_etf_analysis=not args.skip_leveraged_etf_analysis,
        run_dealer_observed_analysis=not args.skip_dealer_observed_analysis,
        run_gamma_surrogate_exploration=args.run_gamma_surrogate_exploration,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
