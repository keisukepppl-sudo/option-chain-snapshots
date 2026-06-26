#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover - tests use local frames
    yf = None


ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
JST = ZoneInfo("Asia/Tokyo")
CALCULATION_VERSION = "market_bomb_phase3_2_cta_vol_proxy_v1_20260627"
CTA_METRIC_VERSION = "cta_proxy_rules_v1"
VOL_METRIC_VERSION = "vol_control_proxy_rules_v1"
METHODOLOGY_VERSION = "cta_vol_proxy_methodology_v1"
CTA_ASSETS = ["QQQ", "SPY", "SOXX", "TLT", "HYG"]
VOL_ASSETS = ["QQQ", "SPY", "SOXX"]
TARGET_VOLS = [0.10, 0.12, 0.15]
MAX_FEATURE_AGE_HOURS = 96


CTA_RULES = {
    "version": CTA_METRIC_VERSION,
    "long_bias": {"close_gt_ema_20": True, "close_gt_sma_50": True, "return_20d_gt": 0.0},
    "short_bias": {"close_lt_ema_20": True, "close_lt_sma_50": True, "return_20d_lt": 0.0},
    "exposure_mapping": {"long_bias": 1.0, "neutral": 0.0, "short_bias": -1.0},
    "deleveraging_if": {"cta_exposure_change_1d_lt": 0.0, "cta_exposure_change_5d_lt": 0.0},
}

VOL_RULES = {
    "version": VOL_METRIC_VERSION,
    "target_vols": TARGET_VOLS,
    "max_exposure": 1.0,
    "deleveraging_threshold_1d": -0.025,
    "deleveraging_threshold_5d": -0.05,
    "re_risking_threshold_1d": 0.025,
    "re_risking_threshold_5d": 0.05,
}


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value) or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def parse_ts(value: Any) -> pd.Timestamp | None:
    if value in [None, ""]:
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts


def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass


def markdown_table(df: pd.DataFrame, max_rows: int = 40) -> str:
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


def next_us_session_open_after_eod(feature_date: pd.Timestamp) -> pd.Timestamp:
    et_date = pd.Timestamp(feature_date).tz_localize(None).date()
    candidate = pd.Timestamp.combine(et_date, time(9, 30)).tz_localize(ET) + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.tz_convert(UTC)


def eod_timestamp_utc(feature_date: pd.Timestamp) -> pd.Timestamp:
    et_date = pd.Timestamp(feature_date).tz_localize(None).date()
    return pd.Timestamp.combine(et_date, time(16, 0)).tz_localize(ET).tz_convert(UTC)


def available_timestamp_utc(feature_date: pd.Timestamp) -> pd.Timestamp:
    et_date = pd.Timestamp(feature_date).tz_localize(None).date()
    return pd.Timestamp.combine(et_date, time(16, 30)).tz_localize(ET).tz_convert(UTC)


def source_audit() -> pd.DataFrame:
    rows = []
    for instrument in sorted(set(CTA_ASSETS + VOL_ASSETS)):
        rows.append(
            {
                "source_name": "yfinance",
                "instrument": instrument,
                "adjusted_close_available": True,
                "historical_coverage": "depends_on_yfinance_history",
                "timezone_or_exchange_calendar": "America/New_York approximation",
                "timestamp_quality": "daily_bar_date_eod_inferred",
                "availability_time_quality": "EOD close available next US session only",
                "api_or_download_method": "yf.download auto_adjust=False",
                "github_actions_compatible": True,
                "license_or_terms_risk": "third_party_terms_review_required",
                "recommended_or_not": True,
                "notes": "Proxy research only; not actual CTA or Vol Control flow.",
            }
        )
    return pd.DataFrame(rows)


def load_price_history(root: Path, refresh_price_history: bool = True, period: str = "5y") -> dict[str, pd.DataFrame]:
    price_dir = root / "market_bomb_history" / "price_history"
    price_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, pd.DataFrame] = {}
    for asset in sorted(set(CTA_ASSETS + VOL_ASSETS)):
        path = price_dir / f"{asset}_daily_price_history.csv"
        df = pd.DataFrame()
        if refresh_price_history and yf is not None:
            try:
                raw = yf.download(asset, period=period, auto_adjust=False, progress=False, threads=False)
                if isinstance(raw, pd.DataFrame) and not raw.empty:
                    if isinstance(raw.columns, pd.MultiIndex):
                        raw.columns = [str(c[0]) for c in raw.columns]
                    df = raw.reset_index()
                    df.to_csv(path, index=False)
            except Exception:
                df = pd.DataFrame()
        if df.empty and path.exists():
            try:
                df = pd.read_csv(path)
            except Exception:
                df = pd.DataFrame()
        out[asset] = normalize_price_frame(df)
    return out


def normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "close", "adjusted_close"])
    cols = {str(c).lower(): c for c in df.columns}
    date_col = cols.get("date") or cols.get("datetime") or cols.get("timestamp")
    close_col = cols.get("close")
    adj_col = cols.get("adj close") or cols.get("adj_close") or close_col
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col], errors="coerce").dt.tz_localize(None) if date_col else pd.NaT,
            "close": pd.to_numeric(df[close_col], errors="coerce") if close_col else np.nan,
            "adjusted_close": pd.to_numeric(df[adj_col], errors="coerce") if adj_col else np.nan,
        }
    )
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    return out.reset_index(drop=True)


def add_common_price_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    px = out["adjusted_close"].replace(0, np.nan)
    out["return_1d_pct"] = px.pct_change(1)
    out["return_5d_pct"] = px.pct_change(5)
    out["return_20d_pct"] = px.pct_change(20)
    out["return_60d_pct"] = px.pct_change(60)
    out["ema_20"] = px.ewm(span=20, adjust=False, min_periods=20).mean()
    out["sma_50"] = px.rolling(50, min_periods=50).mean()
    out["sma_200"] = px.rolling(200, min_periods=200).mean()
    out["close_vs_20ema_pct"] = px / out["ema_20"] - 1
    out["close_vs_50dma_pct"] = px / out["sma_50"] - 1
    out["close_vs_200dma_pct"] = px / out["sma_200"] - 1
    out["realized_vol_20d"] = out["return_1d_pct"].rolling(20, min_periods=20).std() * math.sqrt(252)
    out["realized_vol_60d"] = out["return_1d_pct"].rolling(60, min_periods=60).std() * math.sqrt(252)
    return out


def cta_state(row: pd.Series) -> tuple[str, float]:
    close = safe_float(row.get("adjusted_close"))
    ema_20 = safe_float(row.get("ema_20"))
    sma_50 = safe_float(row.get("sma_50"))
    ret_20 = safe_float(row.get("return_20d_pct"))
    if pd.notna(close) and pd.notna(ema_20) and pd.notna(sma_50) and pd.notna(ret_20):
        if close > ema_20 and close > sma_50 and ret_20 > 0:
            return "long_bias", 1.0
        if close < ema_20 and close < sma_50 and ret_20 < 0:
            return "short_bias", -1.0
    return "neutral", 0.0


def build_cta_proxy_history(price_history: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for asset in CTA_ASSETS:
        df = add_common_price_features(price_history.get(asset, pd.DataFrame()))
        if df.empty:
            continue
        states = df.apply(cta_state, axis=1, result_type="expand")
        df["cta_trend_state"] = states[0]
        df["cta_trend_score"] = states[1]
        df["cta_normalized_exposure_proxy"] = states[1]
        df["cta_exposure_change_1d"] = df["cta_normalized_exposure_proxy"].diff(1)
        df["cta_exposure_change_5d"] = df["cta_normalized_exposure_proxy"].diff(5)
        df["cta_direction_proxy"] = np.where(df["cta_exposure_change_1d"] > 0, "increasing", np.where(df["cta_exposure_change_1d"] < 0, "decreasing", "flat"))
        df["cta_deleveraging_proxy"] = (df["cta_exposure_change_1d"] < 0) | (df["cta_exposure_change_5d"] < 0)
        for _, row in df.iterrows():
            feature_date = pd.Timestamp(row["date"])
            rows.append(
                {
                    "asset": asset,
                    "feature_as_of_timestamp_utc": eod_timestamp_utc(feature_date).isoformat(),
                    "effective_available_at_utc": next_us_session_open_after_eod(feature_date).isoformat(),
                    "source_available_at_utc": available_timestamp_utc(feature_date).isoformat(),
                    "collected_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
                    "retrieved_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
                    "availability_basis": "eod_feature_next_us_session_context_only",
                    "availability_confidence": "medium",
                    "close": row.get("close"),
                    "adjusted_close": row.get("adjusted_close"),
                    "return_1d_pct": row.get("return_1d_pct"),
                    "return_5d_pct": row.get("return_5d_pct"),
                    "return_20d_pct": row.get("return_20d_pct"),
                    "return_60d_pct": row.get("return_60d_pct"),
                    "ema_20": row.get("ema_20"),
                    "sma_50": row.get("sma_50"),
                    "sma_200": row.get("sma_200"),
                    "close_vs_20ema_pct": row.get("close_vs_20ema_pct"),
                    "close_vs_50dma_pct": row.get("close_vs_50dma_pct"),
                    "close_vs_200dma_pct": row.get("close_vs_200dma_pct"),
                    "realized_vol_20d": row.get("realized_vol_20d"),
                    "realized_vol_60d": row.get("realized_vol_60d"),
                    "cta_trend_state": row.get("cta_trend_state"),
                    "cta_trend_score": row.get("cta_trend_score"),
                    "cta_normalized_exposure_proxy": row.get("cta_normalized_exposure_proxy"),
                    "cta_exposure_change_1d": row.get("cta_exposure_change_1d"),
                    "cta_exposure_change_5d": row.get("cta_exposure_change_5d"),
                    "cta_direction_proxy": row.get("cta_direction_proxy"),
                    "cta_deleveraging_proxy": bool(row.get("cta_deleveraging_proxy")),
                    "data_type": "proxy",
                    "is_proxy": True,
                    "observed_flow": False,
                    "quality_flag": "medium" if pd.notna(row.get("realized_vol_20d")) else "low",
                    "calculation_version": CALCULATION_VERSION,
                    "metric_definition_version": CTA_METRIC_VERSION,
                }
            )
    return pd.DataFrame(rows)


def vol_state(change_1d: float, change_5d: float) -> str:
    if pd.isna(change_1d) and pd.isna(change_5d):
        return "unavailable"
    if (pd.notna(change_1d) and change_1d < VOL_RULES["deleveraging_threshold_1d"]) or (pd.notna(change_5d) and change_5d < VOL_RULES["deleveraging_threshold_5d"]):
        return "deleveraging"
    if (pd.notna(change_1d) and change_1d > VOL_RULES["re_risking_threshold_1d"]) or (pd.notna(change_5d) and change_5d > VOL_RULES["re_risking_threshold_5d"]):
        return "re_risking"
    return "stable"


def build_vol_control_proxy_history(price_history: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for asset in VOL_ASSETS:
        df = add_common_price_features(price_history.get(asset, pd.DataFrame()))
        if df.empty:
            continue
        for target_vol in TARGET_VOLS:
            tmp = df.copy()
            tmp["target_vol"] = target_vol
            tmp["target_exposure_raw"] = target_vol / tmp["realized_vol_20d"]
            tmp["target_exposure_capped"] = tmp["target_exposure_raw"].clip(lower=0.0, upper=VOL_RULES["max_exposure"])
            tmp["vol_control_exposure_change_1d"] = tmp["target_exposure_capped"].diff(1)
            tmp["vol_control_exposure_change_5d"] = tmp["target_exposure_capped"].diff(5)
            tmp["vol_control_state"] = tmp.apply(lambda r: vol_state(safe_float(r.get("vol_control_exposure_change_1d")), safe_float(r.get("vol_control_exposure_change_5d"))), axis=1)
            tmp["vol_control_direction_proxy"] = np.where(tmp["vol_control_exposure_change_1d"] > 0, "increasing", np.where(tmp["vol_control_exposure_change_1d"] < 0, "decreasing", "flat"))
            tmp["vol_control_pressure_proxy"] = tmp["vol_control_state"]
            for _, row in tmp.iterrows():
                feature_date = pd.Timestamp(row["date"])
                rows.append(
                    {
                        "asset": asset,
                        "feature_as_of_timestamp_utc": eod_timestamp_utc(feature_date).isoformat(),
                        "effective_available_at_utc": next_us_session_open_after_eod(feature_date).isoformat(),
                        "source_available_at_utc": available_timestamp_utc(feature_date).isoformat(),
                        "collected_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
                        "retrieved_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
                        "availability_basis": "eod_feature_next_us_session_context_only",
                        "availability_confidence": "medium",
                        "realized_vol_20d": row.get("realized_vol_20d"),
                        "realized_vol_60d": row.get("realized_vol_60d"),
                        "target_vol": target_vol,
                        "target_exposure_raw": row.get("target_exposure_raw"),
                        "target_exposure_capped": row.get("target_exposure_capped"),
                        "vol_control_exposure_change_1d": row.get("vol_control_exposure_change_1d"),
                        "vol_control_exposure_change_5d": row.get("vol_control_exposure_change_5d"),
                        "vol_control_state": row.get("vol_control_state"),
                        "vol_control_direction_proxy": row.get("vol_control_direction_proxy"),
                        "vol_control_pressure_proxy": row.get("vol_control_pressure_proxy"),
                        "data_type": "proxy",
                        "is_proxy": True,
                        "observed_flow": False,
                        "quality_flag": "medium" if pd.notna(row.get("realized_vol_20d")) else "low",
                        "calculation_version": CALCULATION_VERSION,
                        "metric_definition_version": VOL_METRIC_VERSION,
                    }
                )
    return pd.DataFrame(rows)


def strategy_bucket(rank: str) -> str:
    rank = str(rank).upper()
    if rank == "S":
        return "S_breakout_momentum"
    if rank in {"A", "B"}:
        return "AB_institutional_pullback"
    return "other"


def load_analysis_units(root: Path) -> pd.DataFrame:
    candidates: list[pd.DataFrame] = []
    patterns = [
        ("trade", "morita_trade_log/**/*.csv"),
        ("trade", "scanner_alerts/trade_log.csv"),
        ("decision", "morita_decision_history/**/*.csv"),
        ("signal_event", "morita_signal_history/**/*.csv"),
        ("signal_event", "scanner_alerts/**/*.csv"),
        ("setup", "morita_setup_history/**/*.csv"),
    ]
    for unit, pattern in patterns:
        for path in root.glob(pattern):
            try:
                df = pd.read_csv(path)
            except Exception:
                continue
            if df.empty:
                continue
            df = normalize_analysis_unit(df, unit, path)
            if not df.empty:
                candidates.append(df)
    if not candidates:
        return pd.DataFrame(columns=["analysis_unit", "decision_id", "signal_event_id", "setup_id", "trade_id", "ticker", "original_rank", "strategy_bucket", "decision_timestamp_utc"])
    out = pd.concat(candidates, ignore_index=True)
    out = out.drop_duplicates(["analysis_unit", "ticker", "decision_timestamp_utc", "original_rank"], keep="first")
    return out.reset_index(drop=True)


def first_present(row: pd.Series, names: list[str], default: Any = "") -> Any:
    for name in names:
        if name in row and pd.notna(row[name]) and row[name] != "":
            return row[name]
    return default


def normalize_analysis_unit(df: pd.DataFrame, unit: str, path: Path) -> pd.DataFrame:
    rows = []
    for i, row in df.iterrows():
        ticker = str(first_present(row, ["ticker", "symbol", "underlying"], "")).upper()
        rank = str(first_present(row, ["alert_rank", "rank", "production_rank", "original_rank"], "")).upper()
        ts_val = first_present(row, ["decision_timestamp_utc", "timestamp_utc", "alert_timestamp_utc", "alert_time_utc", "scan_time_utc", "date", "entry_date"], "")
        ts = parse_ts(ts_val)
        if ts is None and ts_val:
            ts = parse_ts(str(ts_val) + "T14:30:00Z")
        if not ticker or rank not in {"S", "A", "B"} or ts is None:
            continue
        rows.append(
            {
                "analysis_unit": unit,
                "decision_id": str(first_present(row, ["decision_id"], f"{unit}_{path.stem}_{i}")) if unit == "decision" else "",
                "signal_event_id": str(first_present(row, ["signal_event_id", "alert_id"], f"{unit}_{path.stem}_{i}")) if unit == "signal_event" else "",
                "setup_id": str(first_present(row, ["setup_id"], f"{unit}_{path.stem}_{i}")) if unit == "setup" else "",
                "trade_id": str(first_present(row, ["trade_id"], f"{unit}_{path.stem}_{i}")) if unit == "trade" else "",
                "ticker": ticker,
                "original_rank": rank,
                "strategy_bucket": strategy_bucket(rank),
                "decision_timestamp_utc": ts.isoformat(),
                "observed_option_pnl_pct": safe_float(first_present(row, ["observed_option_pnl_pct", "pnl_pct", "return_pct"], math.nan)),
                "modelled_option_pnl_pct": safe_float(first_present(row, ["modelled_option_pnl_pct", "modeled_option_pnl_pct"], math.nan)),
                "source_file": str(path).replace("\\", "/"),
            }
        )
    return pd.DataFrame(rows)


def market_proxy_asset_for_ticker(ticker: str) -> str:
    ticker = str(ticker).upper()
    if ticker in CTA_ASSETS:
        return ticker
    if ticker in {"NVDA", "AMD", "AVGO", "MU", "SMH", "SOXL", "SOXS"}:
        return "SOXX"
    return "QQQ"


def latest_feature(feature_df: pd.DataFrame, asset: str, decision_ts: pd.Timestamp, max_age_hours: int = MAX_FEATURE_AGE_HOURS, target_vol: float | None = None) -> tuple[pd.Series | None, str, str]:
    if feature_df.empty:
        return None, "no_feature_history", "no feature history"
    df = feature_df[feature_df["asset"].astype(str).eq(asset)].copy()
    if target_vol is not None and "target_vol" in df.columns:
        df = df[np.isclose(pd.to_numeric(df["target_vol"], errors="coerce"), target_vol)]
    if df.empty:
        return None, "no_asset_feature", f"no feature for {asset}"
    df["effective_ts"] = pd.to_datetime(df["effective_available_at_utc"], utc=True, errors="coerce")
    df["asof_ts"] = pd.to_datetime(df["feature_as_of_timestamp_utc"], utc=True, errors="coerce")
    eligible = df[(df["effective_ts"] <= decision_ts) & (df["asof_ts"] <= decision_ts)].copy()
    if eligible.empty:
        return None, "no_temporally_available_feature", "no feature available before decision"
    eligible["feature_age_hours"] = (decision_ts - eligible["effective_ts"]).dt.total_seconds() / 3600
    eligible = eligible[eligible["feature_age_hours"] <= max_age_hours]
    if eligible.empty:
        return None, "feature_too_old", f"no feature within {max_age_hours} hours"
    latest = eligible.sort_values("effective_ts").iloc[-1]
    return latest, "joined", ""


def build_join_audit(units: pd.DataFrame, cta: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, unit in units.iterrows():
        decision_ts = parse_ts(unit.get("decision_timestamp_utc"))
        if decision_ts is None:
            continue
        asset = market_proxy_asset_for_ticker(unit.get("ticker"))
        cta_row, cta_status, cta_reason = latest_feature(cta, asset, decision_ts)
        vol_row, vol_status, vol_reason = latest_feature(vol, asset if asset in VOL_ASSETS else "QQQ", decision_ts, target_vol=0.12)
        join_status = "joined" if cta_status == "joined" and vol_status == "joined" else "partial" if cta_status == "joined" or vol_status == "joined" else "failed"
        analysis_mode = "strict_live_replay" if unit.get("analysis_unit") in {"trade", "decision"} and join_status in {"joined", "partial"} else "historical_reconstructed" if join_status in {"joined", "partial"} else "unavailable"
        rows.append(
            {
                "decision_id": unit.get("decision_id", ""),
                "signal_event_id": unit.get("signal_event_id", ""),
                "setup_id": unit.get("setup_id", ""),
                "trade_id": unit.get("trade_id", ""),
                "analysis_unit": unit.get("analysis_unit"),
                "ticker": unit.get("ticker"),
                "strategy_bucket": unit.get("strategy_bucket"),
                "original_rank": unit.get("original_rank"),
                "decision_timestamp_utc": decision_ts.isoformat(),
                "feature_asset": asset,
                "feature_id": f"{asset}_{cta_row.get('feature_as_of_timestamp_utc') if cta_row is not None else ''}",
                "feature_as_of_timestamp_utc": cta_row.get("feature_as_of_timestamp_utc") if cta_row is not None else "",
                "effective_available_at_utc": cta_row.get("effective_available_at_utc") if cta_row is not None else "",
                "feature_age_hours": round(float((decision_ts - parse_ts(cta_row.get("effective_available_at_utc"))).total_seconds() / 3600), 2) if cta_row is not None and parse_ts(cta_row.get("effective_available_at_utc")) is not None else np.nan,
                "join_status": join_status,
                "join_failure_reason": "; ".join([x for x in [cta_reason, vol_reason] if x]),
                "analysis_mode": analysis_mode,
                "cta_trend_state": cta_row.get("cta_trend_state") if cta_row is not None else "unavailable",
                "cta_deleveraging_proxy": cta_row.get("cta_deleveraging_proxy") if cta_row is not None else "",
                "vol_control_state": vol_row.get("vol_control_state") if vol_row is not None else "unavailable",
                "vol_control_exposure_change_1d": vol_row.get("vol_control_exposure_change_1d") if vol_row is not None else np.nan,
                "dealer_feature_usage": "context_only",
                "dealer_data_type": "reconstructed",
                "dealer_is_proxy": True,
                "observed_option_pnl_pct": unit.get("observed_option_pnl_pct", np.nan),
                "modelled_option_pnl_pct": unit.get("modelled_option_pnl_pct", np.nan),
            }
        )
    return pd.DataFrame(rows)


def enrich_outcomes(joined: pd.DataFrame, price_history: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if joined.empty:
        return joined
    out = joined.copy()
    for idx, row in out.iterrows():
        ticker = str(row.get("ticker", "")).upper()
        asset = ticker if ticker in price_history and not price_history[ticker].empty else market_proxy_asset_for_ticker(ticker)
        px = price_history.get(asset, pd.DataFrame())
        if px.empty:
            continue
        decision_ts = parse_ts(row.get("decision_timestamp_utc"))
        if decision_ts is None:
            continue
        date = decision_ts.tz_convert(ET).tz_localize(None).normalize()
        px = add_common_price_features(px)
        px["date_norm"] = pd.to_datetime(px["date"]).dt.normalize()
        future = px[px["date_norm"] >= date].head(11).reset_index(drop=True)
        if len(future) < 2:
            continue
        entry = safe_float(future.loc[0, "adjusted_close"])
        if pd.isna(entry) or entry <= 0:
            continue
        for horizon in [1, 5, 10]:
            out.loc[idx, f"underlying_return_{horizon}d"] = future.loc[horizon, "adjusted_close"] / entry - 1 if len(future) > horizon else np.nan
        returns = future["adjusted_close"] / entry - 1
        out.loc[idx, "underlying_max_adverse_excursion"] = returns.min()
        out.loc[idx, "underlying_max_favorable_excursion"] = returns.max()
        pnl = safe_float(row.get("observed_option_pnl_pct"))
        if pd.isna(pnl):
            pnl = safe_float(row.get("modelled_option_pnl_pct"))
        out.loc[idx, "stop_minus_60_hit"] = bool(pd.notna(pnl) and pnl <= -0.60)
        out.loc[idx, "tp_plus_200_hit"] = bool(pd.notna(pnl) and pnl >= 2.00)
        out.loc[idx, "tp_plus_300_hit"] = bool(pd.notna(pnl) and pnl >= 3.00)
    return out


def profit_factor(vals: pd.Series) -> float:
    clean = pd.to_numeric(vals, errors="coerce").dropna()
    gains = clean[clean > 0].sum()
    losses = clean[clean < 0].sum()
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return float(gains / abs(losses))


def max_losing_streak(vals: pd.Series) -> int:
    streak = best = 0
    for val in pd.to_numeric(vals, errors="coerce").dropna():
        if val < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def summarize_groups(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if df.empty:
        return pd.DataFrame(columns=["group", "sample_count", "verdict"])
    group_cols = ["strategy_bucket", "cta_trend_state", "cta_deleveraging_proxy", "vol_control_state"]
    for keys, group in df.groupby(group_cols, dropna=False):
        pnl = pd.to_numeric(group["observed_option_pnl_pct"], errors="coerce") if "observed_option_pnl_pct" in group else pd.Series(index=group.index, dtype=float)
        if pnl.isna().all():
            pnl = pd.to_numeric(group["modelled_option_pnl_pct"], errors="coerce") if "modelled_option_pnl_pct" in group else pd.Series(index=group.index, dtype=float)
        n = len(group)
        rows.append(
            {
                "strategy_bucket": keys[0],
                "cta_trend_state": keys[1],
                "cta_deleveraging_proxy": keys[2],
                "vol_control_state": keys[3],
                "sample_count": n,
                "average_underlying_return_5d": pd.to_numeric(group.get("underlying_return_5d"), errors="coerce").mean(),
                "median_underlying_return_5d": pd.to_numeric(group.get("underlying_return_5d"), errors="coerce").median(),
                "stop_minus_60_hit_rate": group.get("stop_minus_60_hit", pd.Series(dtype=bool)).mean() if "stop_minus_60_hit" in group else np.nan,
                "tp_plus_200_hit_rate": group.get("tp_plus_200_hit", pd.Series(dtype=bool)).mean() if "tp_plus_200_hit" in group else np.nan,
                "tp_plus_300_hit_rate": group.get("tp_plus_300_hit", pd.Series(dtype=bool)).mean() if "tp_plus_300_hit" in group else np.nan,
                "profit_factor": profit_factor(pnl),
                "max_losing_streak": max_losing_streak(pnl),
                "evidence_verdict": "insufficient_data" if n < 20 else "exploratory" if n < 50 else "preliminary_evidence",
            }
        )
    return pd.DataFrame(rows)


def baseline_comparison(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if df.empty:
        return pd.DataFrame(columns=["baseline", "sample_count", "evidence_verdict"])
    definitions = {
        "A_trend_only_baseline": df["cta_trend_state"].isin(["long_bias", "neutral", "short_bias"]),
        "B_trend_plus_cta_proxy": df["cta_trend_state"].eq("long_bias") & df["cta_deleveraging_proxy"].astype(str).str.lower().eq("false"),
        "C_trend_plus_vol_control_proxy": df["vol_control_state"].isin(["stable", "re_risking"]),
        "D_trend_plus_cta_plus_vol_proxy": df["cta_trend_state"].eq("long_bias") & df["cta_deleveraging_proxy"].astype(str).str.lower().eq("false") & df["vol_control_state"].isin(["stable", "re_risking"]),
    }
    for name, mask in definitions.items():
        sample = df[mask]
        pnl = pd.to_numeric(sample["observed_option_pnl_pct"], errors="coerce") if "observed_option_pnl_pct" in sample else pd.Series(index=sample.index, dtype=float)
        if pnl.isna().all():
            pnl = pd.to_numeric(sample["modelled_option_pnl_pct"], errors="coerce") if "modelled_option_pnl_pct" in sample else pd.Series(index=sample.index, dtype=float)
        rows.append(
            {
                "baseline": name,
                "sample_count": len(sample),
                "average_underlying_return_5d": pd.to_numeric(sample.get("underlying_return_5d"), errors="coerce").mean() if not sample.empty else np.nan,
                "median_underlying_return_5d": pd.to_numeric(sample.get("underlying_return_5d"), errors="coerce").median() if not sample.empty else np.nan,
                "profit_factor": profit_factor(pnl),
                "max_losing_streak": max_losing_streak(pnl),
                "evidence_verdict": "insufficient_data" if len(sample) < 20 else "exploratory" if len(sample) < 50 else "preliminary_evidence",
            }
        )
    return pd.DataFrame(rows)


def write_configs(root: Path) -> None:
    cfg = root / "market_bomb_config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "cta_proxy_rules_v1.json").write_text(json.dumps(CTA_RULES, indent=2), encoding="utf-8")
    (cfg / "vol_control_proxy_rules_v1.json").write_text(json.dumps(VOL_RULES, indent=2), encoding="utf-8")


def write_reports(root: Path, cta: pd.DataFrame, vol: pd.DataFrame, source: pd.DataFrame, join: pd.DataFrame, enriched: pd.DataFrame, summary: pd.DataFrame, baseline: pd.DataFrame) -> dict[str, Path]:
    today = pd.Timestamp.now(tz=JST).strftime("%Y%m%d")
    analysis = root / "market_bomb_analysis"
    history = root / "market_bomb_history"
    analysis.mkdir(parents=True, exist_ok=True)
    history.mkdir(parents=True, exist_ok=True)
    source.to_csv(analysis / "cta_vol_price_source_audit.csv", index=False)
    (analysis / "cta_vol_price_source_audit.md").write_text("# CTA / Vol Control Price Source Audit\n\n" + markdown_table(source) + "\n", encoding="utf-8")
    write_table(cta, history / "cta_proxy_history.csv", history / "cta_proxy_history.parquet")
    write_table(vol, history / "vol_control_proxy_history.csv", history / "vol_control_proxy_history.parquet")
    quality = pd.DataFrame(
        [
            {"dataset": "cta_proxy_history", "rows": len(cta), "medium_or_better_rows": int(cta["quality_flag"].isin(["high", "medium"]).sum()) if not cta.empty else 0},
            {"dataset": "vol_control_proxy_history", "rows": len(vol), "medium_or_better_rows": int(vol["quality_flag"].isin(["high", "medium"]).sum()) if not vol.empty else 0},
            {"dataset": "join_audit", "rows": len(join), "joined_or_partial_rows": int(join["join_status"].isin(["joined", "partial"]).sum()) if not join.empty else 0},
        ]
    )
    quality.to_csv(history / "cta_vol_proxy_quality_audit.csv", index=False)
    (history / "cta_vol_proxy_quality_audit.md").write_text("# CTA / Vol Proxy Quality Audit\n\n" + markdown_table(quality) + "\n", encoding="utf-8")
    join.to_csv(analysis / f"cta_vol_join_audit_{today}.csv", index=False)
    summary.to_csv(analysis / f"cta_vol_indicator_summary_{today}.csv", index=False)
    baseline.to_csv(analysis / f"cta_vol_baseline_comparison_{today}.csv", index=False)
    methodology = (
        "# CTA / Vol Control Proxy Methodology v1\n\n"
        "These features are proxy research features only. They are not actual CTA flow, actual Vol Control selling, or observed institutional order flow.\n\n"
        "- `data_type = proxy`\n- `is_proxy = true`\n- `observed_flow = false`\n\n"
        "EOD features are only eligible after the next US regular-session open. Join rules require both `effective_available_at_utc <= decision_timestamp_utc` and `feature_as_of_timestamp_utc <= decision_timestamp_utc`.\n"
    )
    (analysis / "cta_vol_methodology_v1.md").write_text(methodology, encoding="utf-8")
    cta_report = "# CTA Proxy Report\n\n" + markdown_table(cta.tail(20)) + "\n"
    vol_report = "# Vol Control Proxy Report\n\n" + markdown_table(vol.tail(20)) + "\n"
    combined = (
        "# CTA / Vol Proxy Combined Report\n\n"
        "## Observed\n\n"
        f"- CTA rows: `{len(cta)}`\n- Vol Control rows: `{len(vol)}`\n- Join audit rows: `{len(join)}`\n\n"
        "## Proxy\n\n"
        "- CTA trend and deleveraging are rule-based proxies.\n- Vol Control exposure change is target-volatility math, not observed fund flow.\n\n"
        "## Not Established\n\n"
        "- No automatic market score, GO/STOP, sizing, or entry filter change is made by this phase.\n\n"
        "## Indicator Summary\n\n"
        + markdown_table(summary)
        + "\n\n## Baseline Comparison\n\n"
        + markdown_table(baseline)
        + "\n"
    )
    data_sufficiency = pd.DataFrame(
        [
            {"metric": "feature_history_coverage", "value": f"cta={len(cta)}, vol={len(vol)}"},
            {"metric": "signal_decision_trade_count", "value": len(join)},
            {"metric": "join_success_rate", "value": round(float(join["join_status"].eq("joined").mean()), 4) if not join.empty else 0},
            {"metric": "strict_live_replay_count", "value": int(join["analysis_mode"].eq("strict_live_replay").sum()) if not join.empty else 0},
            {"metric": "historical_reconstructed_count", "value": int(join["analysis_mode"].eq("historical_reconstructed").sum()) if not join.empty else 0},
            {"metric": "observed_option_pnl_count", "value": int(pd.to_numeric(enriched.get("observed_option_pnl_pct"), errors="coerce").notna().sum()) if not enriched.empty else 0},
            {"metric": "modelled_option_pnl_count", "value": int(pd.to_numeric(enriched.get("modelled_option_pnl_pct"), errors="coerce").notna().sum()) if not enriched.empty else 0},
            {"metric": "insufficient_data_verdict", "value": bool(len(join) < 20)},
        ]
    )
    (analysis / f"cta_proxy_report_{today}.md").write_text(cta_report, encoding="utf-8")
    (analysis / f"vol_control_proxy_report_{today}.md").write_text(vol_report, encoding="utf-8")
    (analysis / f"cta_vol_proxy_combined_report_{today}.md").write_text(combined, encoding="utf-8")
    (analysis / f"cta_vol_data_sufficiency_{today}.md").write_text("# CTA / Vol Proxy Data Sufficiency\n\n" + markdown_table(data_sufficiency) + "\n", encoding="utf-8")
    return {
        "cta_history_csv": history / "cta_proxy_history.csv",
        "vol_history_csv": history / "vol_control_proxy_history.csv",
        "quality_audit_csv": history / "cta_vol_proxy_quality_audit.csv",
        "source_audit_csv": analysis / "cta_vol_price_source_audit.csv",
        "join_audit_csv": analysis / f"cta_vol_join_audit_{today}.csv",
        "summary_csv": analysis / f"cta_vol_indicator_summary_{today}.csv",
        "combined_report_md": analysis / f"cta_vol_proxy_combined_report_{today}.md",
        "data_sufficiency_md": analysis / f"cta_vol_data_sufficiency_{today}.md",
        "methodology_md": analysis / "cta_vol_methodology_v1.md",
    }


def run(root: Path = Path("."), refresh_price_history: bool = True) -> dict[str, Path]:
    write_configs(root)
    prices = load_price_history(root, refresh_price_history=refresh_price_history)
    cta = build_cta_proxy_history(prices)
    vol = build_vol_control_proxy_history(prices)
    source = source_audit()
    units = load_analysis_units(root)
    join = build_join_audit(units, cta, vol)
    enriched = enrich_outcomes(join, prices)
    summary = summarize_groups(enriched)
    baseline = baseline_comparison(enriched)
    return write_reports(root, cta, vol, source, join, enriched, summary, baseline)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--skip-refresh-price-history", action="store_true")
    args = parser.parse_args()
    outputs = run(Path(args.root), refresh_price_history=not args.skip_refresh_price_history)
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
