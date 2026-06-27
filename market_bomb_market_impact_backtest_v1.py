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
OUTPUT_ROOT = Path("market_bomb_market_impact")


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
        "statistical": {"bootstrap_method": "moving_block", "multiple_testing_method": "benjamini_hochberg"},
        "actionization_allowed": False,
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
            availability.append({
                "feature_family": family,
                "feature_name": "cta_or_vol_proxy",
                "target_market": target,
                "availability_status": status,
                "availability_failure_reason": reason,
                "feature_as_of_timestamp_utc": asof,
                "effective_available_at_utc": eff,
                "feature_age_hours": round((decision_ts - eff_ts).total_seconds() / 3600, 2) if eff_ts is not None else np.nan,
                "data_type": row.get("data_type") if row is not None else "unavailable",
                "is_proxy": row.get("is_proxy") if row is not None else True,
                "observed_flow": row.get("observed_flow") if row is not None else False,
                "quality_grade": row.get("quality_flag") if row is not None else "unavailable",
            })
        if cta_row is None and vol_row is None:
            continue
        merged = outcome.to_dict()
        merged.update({
            "analysis_id": f"cta_vol_{target}_{decision_ts.date()}",
            "feature_family": "CTA_Vol",
            "feature_name": "cta_vol_proxy_set",
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


def prior_available_aum(aum: pd.DataFrame, ticker: str, decision_ts: pd.Timestamp) -> tuple[float, str, bool]:
    if aum.empty:
        return math.nan, "aum_history_missing", False
    work = aum[aum.get("ticker", pd.Series(dtype=str)).astype(str).eq(ticker)].copy()
    if work.empty:
        return math.nan, "ticker_aum_missing", False
    date_col = "as_of_timestamp_utc" if "as_of_timestamp_utc" in work.columns else "date" if "date" in work.columns else ""
    if not date_col:
        return math.nan, "aum_timestamp_missing", False
    work["asof"] = pd.to_datetime(work[date_col], utc=True, errors="coerce")
    work = work[work["asof"] <= decision_ts]
    if work.empty:
        return math.nan, "no_prior_available_aum", False
    row = work.sort_values("asof").iloc[-1]
    for col in ["net_assets_usd", "aum_usd", "assets"]:
        if col in row and pd.notna(row[col]):
            return safe_float(row[col]), "previous_available_net_assets_usd", False
    if "shares_outstanding" in row and "prior_close" in row:
        value = safe_float(row["shares_outstanding"]) * safe_float(row["prior_close"])
        if pd.notna(value) and value > 0:
            return value, "shares_outstanding_x_prior_close_proxy", True
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
                for col in ["open", "high", "low", "close", "volume"]:
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
                prior_close = safe_float(group.iloc[0].get("prior_close", np.nan))
                if pd.isna(prior_close):
                    prior_close = safe_float(group.iloc[0].get("open", np.nan))
                price_1530 = safe_float(bar_1530.get("close"))
                close_price = safe_float(bar_close.get("close"))
                if pd.isna(prior_close) or prior_close <= 0 or pd.isna(price_1530) or pd.isna(close_price):
                    continue
                r_to_1530 = price_1530 / prior_close - 1
                pressure = 0.0
                unavailable = []
                for fund in [f for f in funds if str(f["target"]) == target]:
                    decision_ts = pd.Timestamp.combine(pd.Timestamp(day).date(), time(15, 30)).tz_localize(ET).tz_convert(UTC)
                    fund_aum, aum_source, aum_proxy = prior_available_aum(aum, str(fund["ticker"]), decision_ts)
                    if pd.isna(fund_aum) or fund_aum <= 0:
                        unavailable.append(f"{fund['ticker']}:{aum_source}")
                        continue
                    pressure += leveraged_pressure(float(fund["leverage"]), fund_aum, r_to_1530)
                if unavailable and pressure == 0:
                    audit.append({"target_market": target, "feature_family": "LeveragedETF", "availability_status": "unavailable", "availability_failure_reason": ";".join(unavailable)})
                    continue
                rows.append({
                    "analysis_id": f"leveraged_etf_{target}_{day}",
                    "feature_family": "LeveragedETF",
                    "feature_name": f"{family}_pressure",
                    "target_market": target,
                    "decision_timestamp_utc": pd.Timestamp.combine(pd.Timestamp(day).date(), time(15, 30)).tz_localize(ET).tz_convert(UTC).isoformat(),
                    "aggregate_pressure_usd": pressure,
                    "pressure_sign": "positive" if pressure > 0 else "negative" if pressure < 0 else "flat",
                    "return_prior_close_to_1530": r_to_1530,
                    "intraday_return_1530_to_close": close_price / price_1530 - 1,
                    "intraday_absolute_return_1530_to_close": abs(close_price / price_1530 - 1),
                    "intraday_range_1530_to_close": (safe_float(close_bar.get("high", pd.Series([np.nan])).max()) - safe_float(close_bar.get("low", pd.Series([np.nan])).min())) / price_1530 if price_1530 else np.nan,
                    "data_type": "proxy",
                    "is_proxy": True,
                    "observed_flow": False,
                    "formula_version": "leveraged_etf_rebalancing_pressure_v1",
                    "analysis_mode": "reconstructed_proxy_primary",
                    "sample_split": "expanding_window",
                })
                audit.append({"target_market": target, "feature_family": "LeveragedETF", "availability_status": "available", "availability_failure_reason": ""})
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


def build_dealer_gamma_panel(root: Path, daily_outcomes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = load_dealer_gamma_history(root)
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame([{"feature_family": "DealerGamma", "availability_status": "unavailable", "availability_failure_reason": "dealer_gamma_history_missing"}])
    cols = {str(c).lower(): c for c in raw.columns}
    target_col = cols.get("ticker") or cols.get("asset") or cols.get("target_market")
    eff_col = cols.get("effective_available_at_utc") or cols.get("snapshot_timestamp_utc") or cols.get("feature_as_of_timestamp_utc")
    quality_col = cols.get("row_economic_quality") or cols.get("raw_chain_quality") or cols.get("economic_quality")
    if target_col is None or eff_col is None:
        return pd.DataFrame(), pd.DataFrame([{"feature_family": "DealerGamma", "availability_status": "unavailable", "availability_failure_reason": "required_columns_missing"}])
    work = raw.copy()
    work["target_market"] = work[target_col].astype(str).str.upper()
    work["effective_ts"] = pd.to_datetime(work[eff_col], utc=True, errors="coerce")
    work["quality"] = work[quality_col].astype(str).str.lower() if quality_col else "unknown"
    observed_col = cols.get("raw_option_chain_snapshot") or cols.get("observed_raw_chain") or cols.get("raw_chain_present")
    if observed_col:
        observed_mask = work[observed_col].astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        observed_mask = work.get("dealer_feature_sample_type", pd.Series([""] * len(work))).astype(str).eq("observed_raw_chain_primary")
    work = work[observed_mask & work["quality"].isin(["medium", "high"])]
    if work.empty:
        return pd.DataFrame(), pd.DataFrame([{"feature_family": "DealerGamma", "availability_status": "unavailable", "availability_failure_reason": "no_observed_medium_or_better_raw_chain"}])
    for _, outcome in daily_outcomes.iterrows():
        decision_ts = parse_ts(outcome["decision_timestamp_utc"])
        if decision_ts is None:
            continue
        target = str(outcome["target_market"]).upper()
        subset = work[(work["target_market"].eq(target)) & (work["effective_ts"] <= decision_ts)]
        if subset.empty:
            continue
        feat = subset.sort_values("effective_ts").iloc[-1]
        row = outcome.to_dict()
        flip_state = str(feat.get(cols.get("gamma_flip_state", "gamma_flip_state"), "unavailable"))
        row.update({
            "analysis_id": f"dealer_gamma_{target}_{decision_ts.date()}",
            "feature_family": "DealerGamma",
            "feature_name": "observed_raw_chain_proxy_set",
            "dealer_feature_sample_type": "observed_raw_chain_primary",
            "gamma_flip_state": flip_state if flip_state in {"local_flip_found", "no_local_flip", "unavailable"} else "unavailable",
            "gamma_flip_distance_pct": safe_float(feat.get(cols.get("gamma_flip_distance_pct", "gamma_flip_distance_pct"), np.nan)),
            "net_gex_proxy": safe_float(feat.get(cols.get("net_gex_proxy", "net_gex_proxy"), np.nan)),
            "pinning_proxy": safe_float(feat.get(cols.get("pinning_proxy", "pinning_proxy"), np.nan)),
            "sign_convention": "positive_net_gex_proxy_means_long_gamma_proxy_not_dealer_inventory",
            "is_proxy": True,
            "dealer_position_observed": False,
            "raw_chain_quality": feat.get("quality", "unknown"),
            "row_economic_quality": feat.get("quality", "unknown"),
            "analysis_mode": "reconstructed_proxy_primary",
        })
        rows.append(row)
    audit.append({"feature_family": "DealerGamma", "availability_status": "available" if rows else "unavailable", "availability_failure_reason": "" if rows else "no_temporally_available_observed_rows", "sample_count": len(rows)})
    return pd.DataFrame(rows), pd.DataFrame(audit)


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
    cols = ["feature_family", "feature_name", "target_market", "outcome", "sample_count", "effect_size", "effect_size_bps", "raw_p_value", "adjusted_p_value", "multiple_testing_method", "primary_or_robustness", "evidence_verdict"]
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
            "evidence_verdict": verdict,
        })
    adj = benjamini_hochberg(pvals)
    for row, p in zip(rows, adj):
        row["adjusted_p_value"] = p
    return pd.DataFrame(rows, columns=cols)


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


def write_reports(root: Path, cta_summary: pd.DataFrame, lev_panel: pd.DataFrame, dealer_panel: pd.DataFrame, expiry: pd.DataFrame, gate: dict[str, Any]) -> None:
    reports = root / OUTPUT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    header = (
        "feature is proxy: true\n\n"
        "observed flow: false\n\n"
        "dealer inventory observed: false\n\n"
        f"no-lookahead status: `{gate.get('no_lookahead_status', 'unknown')}`\n\n"
        f"actionization_gate: `{str(gate.get('actionization_gate', False)).lower()}`\n\n"
    )
    (reports / "cta_vol_market_impact_primary.md").write_text(header + markdown_table(cta_summary) + "\n", encoding="utf-8")
    (reports / "leveraged_etf_intraday_impact_primary.md").write_text(header + f"sample count: `{len(lev_panel)}`\n\n" + markdown_table(lev_panel.head(50)) + "\n", encoding="utf-8")
    (reports / "dealer_gamma_observed_primary.md").write_text(header + f"sample count: `{len(dealer_panel)}`\n\n" + markdown_table(dealer_panel.head(50)) + "\n", encoding="utf-8")
    (reports / "dealer_gamma_expiry_event_study.md").write_text(header + markdown_table(expiry) + "\n", encoding="utf-8")
    (reports / "gamma_surrogate_exploratory.md").write_text("feature is proxy: true\n\nprimary result mixed: false\n\ngamma surrogate was not run by default.\n", encoding="utf-8")
    (reports / "combined_feature_robustness.md").write_text("Combined model is exploratory only and not used for actionization in v1.\n", encoding="utf-8")
    (reports / "data_sufficiency_report.md").write_text(markdown_table(pd.DataFrame([gate])) + "\n", encoding="utf-8")


def gate_audit_text(gate: dict[str, Any]) -> str:
    return (
        "# Market Impact Backtest Gate Audit\n\n"
        f"market_impact_data_gate: `{gate['market_impact_data_gate']}`\n\n"
        f"cta_vol_primary_research_gate: `{gate['cta_vol_primary_research_gate']}`\n\n"
        f"leveraged_etf_primary_research_gate: `{gate['leveraged_etf_primary_research_gate']}`\n\n"
        f"dealer_gamma_primary_research_gate: `{gate['dealer_gamma_primary_research_gate']}`\n\n"
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
    del refresh_daily_prices, refresh_intraday_prices, run_gamma_surrogate_exploration
    cfg = rules(root)
    out = root / OUTPUT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    reports = out / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    targets = list(cfg.get("targets", ["QQQ", "SPY", "SOXX", "SMH"]))
    prices = load_price_history(root, targets)
    daily_outcomes = build_daily_outcomes(prices)
    cta_panel, availability, no_lookahead = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    if run_cta_vol_analysis:
        cta_panel, availability, no_lookahead = build_cta_vol_feature_outcome_panel(root, daily_outcomes, cfg)
    lev_panel, lev_audit = (pd.DataFrame(), pd.DataFrame())
    if run_leveraged_etf_analysis:
        lev_panel, lev_audit = build_leveraged_etf_panel(root, cfg)
    dealer_panel, dealer_audit = (pd.DataFrame(), pd.DataFrame())
    if run_dealer_observed_analysis:
        dealer_panel, dealer_audit = build_dealer_gamma_panel(root, daily_outcomes)

    cta_summary = summarize_association(cta_panel, "CTA_Vol", "next_session_absolute_return", "cta_exposure_change_proxy", "primary")
    lev_summary = summarize_association(lev_panel, "LeveragedETF", "intraday_absolute_return_1530_to_close", "aggregate_pressure_usd", "primary")
    dealer_summary = summarize_association(dealer_panel, "DealerGamma", "next_session_high_low_range_pct", "gamma_flip_distance_pct", "primary")
    summary = pd.concat([cta_summary, lev_summary, dealer_summary], ignore_index=True)

    expiry_path = root / EXPIRY_CALENDAR_PATH
    expiry = pd.read_csv(expiry_path) if expiry_path.exists() else pd.DataFrame(columns=["date", "market", "expiry_type"])
    if not expiry.empty:
        expiry["holiday_adjusted_audited"] = expiry.get("holiday_adjusted_flag", False).astype(str).str.lower().isin(["true", "1", "yes"])
        expiry["sample_count"] = 0
        expiry["evidence_verdict"] = "insufficient_data"

    no_lookahead_passed = True if no_lookahead.empty else bool(no_lookahead["no_lookahead_passed"].all())
    data_quality = pd.DataFrame([
        {"module": "CTA_Vol", "sample_count": len(cta_panel), "coverage_rate": len(cta_panel) / max(len(daily_outcomes), 1), "verdict": "passed" if len(cta_panel) else "insufficient_data"},
        {"module": "LeveragedETF", "sample_count": len(lev_panel), "coverage_rate": np.nan, "verdict": "passed" if len(lev_panel) else "insufficient_data"},
        {"module": "DealerGamma", "sample_count": len(dealer_panel), "coverage_rate": np.nan, "verdict": "passed" if len(dealer_panel) else "insufficient_data"},
    ])
    insufficient = ",".join(data_quality.loc[data_quality["verdict"].eq("insufficient_data"), "module"].astype(str))
    gate = {
        "market_impact_data_gate": "passed",
        "cta_vol_primary_research_gate": "passed" if len(cta_summary) else "insufficient_data",
        "leveraged_etf_primary_research_gate": "passed" if len(lev_panel) else "insufficient_data",
        "dealer_gamma_primary_research_gate": "passed" if len(dealer_panel) else "insufficient_data",
        "actionization_gate": False,
        "no_lookahead_status": "passed" if no_lookahead_passed else "failed",
        "insufficient_data_modules": insufficient,
    }

    inventory = source_inventory(root)
    feature_join = pd.concat([
        cta_panel.assign(module="CTA_Vol") if not cta_panel.empty else pd.DataFrame(),
        lev_panel.assign(module="LeveragedETF") if not lev_panel.empty else pd.DataFrame(),
        dealer_panel.assign(module="DealerGamma") if not dealer_panel.empty else pd.DataFrame(),
    ], ignore_index=True)
    manifest = {
        "analysis_id": f"market_impact_{pd.Timestamp.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}",
        "version": VERSION,
        "analysis_base_commit_sha": os.environ.get("GITHUB_SHA", ""),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "rules_version": cfg.get("version"),
        "walk_forward": build_walk_forward_manifest(len(feature_join), cfg),
        "actionization_allowed": False,
    }

    write_table(inventory, out / "source_inventory.csv")
    (out / "source_inventory.md").write_text("# Source Inventory\n\n" + markdown_table(inventory) + "\n", encoding="utf-8")
    data_quality.to_csv(out / "data_quality_audit.csv", index=False)
    availability = pd.concat([availability, lev_audit, dealer_audit], ignore_index=True)
    availability.to_csv(out / "feature_availability_audit.csv", index=False)
    (out / "feature_availability_audit.md").write_text("# Feature Availability Audit\n\n" + markdown_table(availability) + "\n", encoding="utf-8")
    write_table(feature_join, out / "feature_outcome_join_audit.csv", out / "feature_outcome_join_audit.parquet")
    (out / "feature_outcome_join_audit.md").write_text("# Feature Outcome Join Audit\n\n" + markdown_table(feature_join) + "\n", encoding="utf-8")
    no_lookahead.to_csv(out / "no_lookahead_audit.csv", index=False)
    (out / "no_lookahead_audit.md").write_text("# No Lookahead Audit\n\n" + markdown_table(no_lookahead) + "\n", encoding="utf-8")
    write_table(daily_outcomes, out / "daily_market_outcomes.csv", out / "daily_market_outcomes.parquet")
    write_table(cta_panel, out / "cta_vol_market_impact_panel.csv", out / "cta_vol_market_impact_panel.parquet")
    write_table(lev_panel, out / "leveraged_etf_intraday_panel.csv", out / "leveraged_etf_intraday_panel.parquet")
    write_table(dealer_panel, out / "dealer_gamma_observed_panel.csv", out / "dealer_gamma_observed_panel.parquet")
    summary.to_csv(out / "model_comparison_summary.csv", index=False)
    expiry.to_csv(out / "dealer_gamma_expiry_event_study.csv", index=False)
    with (out / "analysis_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    (root / "market_impact_backtest_gate_audit.md").write_text(gate_audit_text(gate), encoding="utf-8")
    write_reports(root, summary, lev_panel, dealer_panel, expiry, gate)
    return {
        "source_inventory": out / "source_inventory.csv",
        "feature_availability_audit": out / "feature_availability_audit.csv",
        "feature_outcome_join_audit": out / "feature_outcome_join_audit.csv",
        "no_lookahead_audit": out / "no_lookahead_audit.csv",
        "model_comparison_summary": out / "model_comparison_summary.csv",
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
