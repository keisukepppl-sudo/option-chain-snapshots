#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import market_bomb_phase2a as p2a
except Exception:
    class _P2AFallback:
        @staticmethod
        def parse_ts(value: Any) -> pd.Timestamp | None:
            if value in [None, ""]:
                return None
            ts = pd.to_datetime(value, utc=True, errors="coerce")
            return None if pd.isna(ts) else ts

        @staticmethod
        def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(csv_path, index=False)
            if parquet_path is not None:
                parquet_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    df.to_parquet(parquet_path, index=False)
                except Exception:
                    pass

    p2a = _P2AFallback()

try:
    import market_bomb_phase2b as p2b
except Exception:
    class _P2BFallback:
        @staticmethod
        def git_commit_sha() -> str:
            return os.environ.get("GITHUB_SHA", "unavailable")

    p2b = _P2BFallback()


MARKET_SCORE_VERSION = "market_environment_v0.1"
EXECUTION_SCORE_VERSION = "execution_v0.1"
COMPONENT_WEIGHT_VERSION = "market_environment_weights_v0.1"
CALCULATION_VERSION = "market_environment_score_v0_20260626"
METRIC_DEFINITION_VERSION = "market_environment_score_v0"
TICKERS_FOR_GEX_AUDIT = ["QQQ", "SPY", "SOXX", "SMH", "MU", "DRAM"]
ET = ZoneInfo("America/New_York")
JST = ZoneInfo("Asia/Tokyo")
SESSION_PHASES = ["prior_session_eod", "same_session_pre_open", "intraday", "after_close", "unknown"]
DEALER_GAMMA_SIGN_CONVENTION = "open_interest_sign_heuristic_call_plus_put_minus"
DEALER_GAMMA_PROXY_ASSUMPTION = "dealer_short_customer_options_assumption"
GEX_METRIC_DERIVATION = "black_scholes_gamma_proxy_from_raw_chain"
GEX_FRESHNESS_THRESHOLD_HOURS = 6.0
GAMMA_FLIP_SEARCH_LOW_PCT = 0.70
GAMMA_FLIP_SEARCH_HIGH_PCT = 1.30
GAMMA_FLIP_WARNING_DISTANCE_PCT = 0.30
GAMMA_FLIP_REJECT_DISTANCE_PCT = 0.50
GAMMA_FLIP_MINIMUM_GRID_SIZE = 101

DEALER_GAMMA_QUALITY_RULES = {
    "version": "dealer_gamma_quality_rules_v2",
    "local_gamma_flip_search_low_pct": GAMMA_FLIP_SEARCH_LOW_PCT,
    "local_gamma_flip_search_high_pct": GAMMA_FLIP_SEARCH_HIGH_PCT,
    "gamma_flip_warning_distance_pct": GAMMA_FLIP_WARNING_DISTANCE_PCT,
    "gamma_flip_reject_distance_pct": GAMMA_FLIP_REJECT_DISTANCE_PCT,
    "minimum_grid_size": GAMMA_FLIP_MINIMUM_GRID_SIZE,
    "high": {
        "input_completeness_rate_min": 0.95,
        "calculation_success_rate_min": 0.90,
        "stale_quote_count_max": 0,
        "notes": "Clear underlying price and quote timestamps, low OI/IV missingness, and fresh quotes.",
    },
    "medium": {
        "input_completeness_rate_min": 0.80,
        "calculation_success_rate_min": 0.70,
        "notes": "Usable for prior-session context with limited missing expiry or IV gaps.",
    },
    "low": {
        "input_completeness_rate_min": 0.60,
        "calculation_success_rate_min": 0.01,
        "notes": "Historical reconstruction only; quote timestamp may be inferred or stale.",
    },
    "unusable": {
        "notes": "Raw chain corrupted, missing underlying price, or insufficient OI/IV to calculate gamma proxy.",
    },
    "sign_convention": DEALER_GAMMA_SIGN_CONVENTION,
    "dealer_gamma_proxy_assumption": DEALER_GAMMA_PROXY_ASSUMPTION,
}

_OPTION_SNAPSHOT_RECORD_CACHE: dict[str, tuple[list[dict[str, Any]], str, float]] = {}


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value) or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def latest_file(root: Path, pattern: str) -> Path | None:
    files = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def hash_file(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    p2a.write_table(df, csv_path, parquet_path)


def metric_row(snapshot: pd.DataFrame, name: str) -> pd.Series | None:
    if snapshot.empty or "metric_name" not in snapshot:
        return None
    hit = snapshot[snapshot["metric_name"].astype(str).eq(name)]
    if hit.empty:
        return None
    return hit.iloc[0]


def metric_value(snapshot: pd.DataFrame, name: str) -> Any:
    row = metric_row(snapshot, name)
    return None if row is None else row.get("metric_value")


def metric_available(snapshot: pd.DataFrame, name: str) -> bool:
    row = metric_row(snapshot, name)
    if row is None:
        return False
    if str(row.get("metric_state", "")).lower() == "unavailable":
        return False
    if str(row.get("quality_flag", "")).lower() == "unavailable":
        return False
    return metric_value(snapshot, name) not in [None, ""]


def component_score(name: str, score: float, max_points: float, available: float, is_proxy: bool, notes: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    score = max(0.0, min(float(max_points), float(score)))
    available = max(0.0, min(float(max_points), float(available)))
    return {
        "component": name,
        "score": score,
        "max_points": float(max_points),
        "available_points": available,
        "coverage_pct": available / max_points if max_points else 0.0,
        "is_proxy": bool(is_proxy),
        "notes": notes,
        "details": details or {},
    }


def trend_component(snapshot: pd.DataFrame) -> dict[str, Any]:
    score = 0.0
    available = 0.0
    details: dict[str, Any] = {}
    for ticker in ["QQQ", "SOXX"]:
        for suffix, points in [
            ("close_vs_20ema_pct", 5.0),
            ("close_vs_50dma_pct", 5.0),
            ("20EMA_slope_5d_pct", 2.5),
            ("50DMA_slope_5d_pct", 2.5),
        ]:
            name = f"{ticker}.{suffix}"
            if metric_available(snapshot, name):
                available += points
                val = safe_float(metric_value(snapshot, name))
                details[name] = val
                if pd.notna(val) and val > 0:
                    score += points
    return component_score("Trend Regime", score, 30, available, False, "QQQ/SOXX trend inputs only.", details)


def volatility_component(snapshot: pd.DataFrame) -> dict[str, Any]:
    score = 0.0
    available = 0.0
    details: dict[str, Any] = {}
    if metric_available(snapshot, "VIX.20d_percentile"):
        available += 8
        val = safe_float(metric_value(snapshot, "VIX.20d_percentile"))
        details["VIX.20d_percentile"] = val
        score += 8 if val < 0.40 else 5 if val <= 0.70 else 1
    if metric_available(snapshot, "VIX.1d_change_pct"):
        available += 4
        val = safe_float(metric_value(snapshot, "VIX.1d_change_pct"))
        details["VIX.1d_change_pct"] = val
        score += 4 if val <= 0 else 2 if val <= 10 else 0
    for ticker in ["QQQ", "SOXX"]:
        name = f"{ticker}.20d_realized_vol"
        if metric_available(snapshot, name):
            available += 4
            val = safe_float(metric_value(snapshot, name))
            details[name] = val
            # v0 uses level as a conservative proxy for stable/falling until RV slope is captured.
            score += 4 if pd.notna(val) and val < (0.35 if ticker == "QQQ" else 0.60) else 0
    return component_score("Volatility Regime", score, 20, available, False, "VIX and realized-vol inputs. VIX futures curve remains unavailable.", details)


def dealer_component(snapshot: pd.DataFrame, scoring_ts: pd.Timestamp | None = None) -> dict[str, Any]:
    score = 0.0
    available = 0.0
    details: dict[str, Any] = {}
    stale = False
    if scoring_ts is not None and not snapshot.empty and "collected_at_utc" in snapshot:
        collected = pd.to_datetime(snapshot["collected_at_utc"], utc=True, errors="coerce").max()
        stale = bool(pd.notna(collected) and (scoring_ts - collected).total_seconds() > 24 * 3600)
    if stale:
        return component_score("Dealer Gamma Proxy", 0, 20, 0, True, "GEX snapshot is stale (>24h); excluded from score.", {"stale": True})
    for ticker in ["QQQ", "SOXX"]:
        state_name = f"{ticker}.dealer_gamma_state"
        flip_name = f"{ticker}.spot_vs_gamma_flip_pct"
        dte_name = f"{ticker}.0dte_share"
        pin_name = f"{ticker}.pinning_score"
        pressure_name = f"{ticker}.dealer_pressure_proxy"
        if metric_available(snapshot, state_name):
            available += 4
            val = str(metric_value(snapshot, state_name))
            details[state_name] = val
            if "Positive" in val:
                score += 4
        if metric_available(snapshot, flip_name):
            available += 3
            val = safe_float(metric_value(snapshot, flip_name))
            details[flip_name] = val
            # Current Phase 1 stores (gamma_flip - spot) / spot; <= 0 means spot is above flip.
            if pd.notna(val) and val <= 0:
                score += 3
        if metric_available(snapshot, dte_name):
            available += 1
            val = safe_float(metric_value(snapshot, dte_name))
            details[dte_name] = val
            if pd.notna(val) and val < 0.35:
                score += 1
        if metric_available(snapshot, pin_name):
            val = safe_float(metric_value(snapshot, pin_name))
            details[pin_name] = val
            if pd.notna(val) and val >= 0.80:
                score -= 1
        if metric_available(snapshot, pressure_name):
            details[pressure_name] = metric_value(snapshot, pressure_name)
    if any(str(v).lower().find("sell") >= 0 and str(v).lower().find("extreme") >= 0 for k, v in details.items() if "pressure" in k):
        score -= 4
    return component_score("Dealer Gamma Proxy", score, 20, available, True, "Dealer metrics are option-chain-derived proxies, not observed dealer positioning.", details)


def event_component(snapshot: pd.DataFrame, event_calendar: pd.DataFrame | None = None) -> dict[str, Any]:
    score = 0.0
    available = 0.0
    details: dict[str, Any] = {}
    # Major event timing is unavailable until manual/official calendar has timestamps.
    if event_calendar is not None and not event_calendar.empty and "event_timestamp_utc" in event_calendar:
        upcoming = pd.to_datetime(event_calendar["event_timestamp_utc"], utc=True, errors="coerce").dropna()
        if len(upcoming):
            available += 8
            now = pd.Timestamp.now(tz="UTC")
            hours = float(((upcoming[upcoming >= now].min() - now).total_seconds() / 3600.0)) if any(upcoming >= now) else math.nan
            details["hours_to_next_event"] = hours
            score += 0 if pd.notna(hours) and hours <= 24 else 4 if pd.notna(hours) and hours <= 48 else 8
    month = metric_value(snapshot, "is_month_end_window")
    quarter = metric_value(snapshot, "is_quarter_end_window")
    pension = metric_value(snapshot, "is_pension_rebalance_window")
    if month is not None or quarter is not None or pension is not None:
        available += 4
        month_flag = str(month).lower() in {"true", "1", "1.0"}
        quarter_flag = str(quarter).lower() in {"true", "1", "1.0"}
        pension_flag = str(pension).lower() in {"true", "1", "1.0"}
        details.update({"is_month_end_window": month_flag, "is_quarter_end_window": quarter_flag, "is_pension_rebalance_window": pension_flag})
        score += 0 if quarter_flag or pension_flag else 2 if month_flag else 4
    # Holiday proximity not implemented; normal-calendar points unavailable instead of granted.
    return component_score("Event / Rebalance Risk", score, 15, available, False, "Event calendar timestamps unavailable unless manual calendar is populated.", details)


def leverage_component(snapshot: pd.DataFrame) -> dict[str, Any]:
    values = []
    details: dict[str, Any] = {}
    for ticker in ["TQQQ", "SQQQ", "SOXL", "SOXS"]:
        name = f"{ticker}.estimated_rebalance_notional"
        if metric_available(snapshot, name):
            val = safe_float(metric_value(snapshot, name))
            values.append(val)
            details[name] = val
    if not values:
        return component_score("Leveraged ETF Pressure", 0, 5, 0, True, "Leveraged ETF pressure proxy unavailable.", details)
    net = float(np.nansum(values))
    score = 5 if net > 500_000_000 else 3 if net > -500_000_000 else 0
    details["net_rebalance_proxy"] = net
    return component_score("Leveraged ETF Pressure", score, 5, 5, True, "Mechanical leveraged ETF rebalance proxy; not actual ETF flow.", details)


def systemic_component(snapshot: pd.DataFrame) -> dict[str, Any]:
    score = 0.0
    available = 0.0
    details: dict[str, Any] = {}
    cta = metric_value(snapshot, "QQQ.estimated_cta_pressure") or metric_value(snapshot, "SPY.estimated_cta_pressure")
    if cta is not None:
        available += 3
        details["cta_proxy"] = cta
        if str(cta) in {"long_bias", "Buy", "Strong Buy", "Neutral"}:
            score += 3
    vc = metric_value(snapshot, "QQQ.target_vol_12pct.vol_control_pressure_proxy") or metric_value(snapshot, "SPY.target_vol_12pct.vol_control_pressure_proxy")
    if vc is not None:
        available += 3
        val = safe_float(vc)
        details["vol_control_proxy"] = val
        if pd.notna(val) and val >= 0:
            score += 3
    rp = metric_value(snapshot, "deleveraging_pressure_proxy")
    if rp is not None:
        available += 2
        val = safe_float(rp)
        details["risk_parity_deleveraging_pressure_proxy"] = val
        if pd.notna(val) and val <= 0:
            score += 2
    shock = metric_value(snapshot, "correlation_shock_flag")
    if shock is not None:
        available += 2
        flag = str(shock).lower() in {"true", "1", "1.0"}
        details["correlation_shock_flag"] = flag
        if not flag:
            score += 2
    return component_score("Systemic De-risking Proxy", score, 10, available, True, "CTA, Vol Control, and Risk Parity are proxies.", details)


def combine_scores(components: list[dict[str, Any]], include_proxy: bool) -> tuple[Any, float, str, list[str]]:
    selected = [c for c in components if include_proxy or not c["is_proxy"]]
    available = sum(c["available_points"] for c in selected)
    max_points = sum(c["max_points"] for c in selected)
    score = sum(c["score"] for c in selected)
    coverage = available / max_points if max_points else 0.0
    unavailable = [c["component"] for c in selected if c["available_points"] < c["max_points"]]
    if coverage < 0.60:
        return None, coverage, "low", unavailable
    confidence = "high" if coverage >= 0.85 and not any(c["is_proxy"] for c in selected) else "medium" if coverage >= 0.60 else "low"
    if any(c["is_proxy"] for c in selected):
        confidence = "medium" if confidence == "high" else confidence
    normalized = score / available * max_points if available else None
    return round(float(normalized), 2) if normalized is not None else None, coverage, confidence, unavailable


def calculate_market_environment_score(snapshot: pd.DataFrame, scoring_ts: pd.Timestamp | None = None, event_calendar: pd.DataFrame | None = None) -> dict[str, Any]:
    components = [
        trend_component(snapshot),
        volatility_component(snapshot),
        dealer_component(snapshot, scoring_ts),
        event_component(snapshot, event_calendar),
        leverage_component(snapshot),
        systemic_component(snapshot),
    ]
    observed_score, observed_cov, observed_conf, observed_unavail = combine_scores(components, include_proxy=False)
    proxy_score, proxy_cov, proxy_conf, proxy_unavail = combine_scores(components, include_proxy=True)
    standard_score = proxy_score if proxy_cov >= 0.60 else None
    snapshot_id = str(snapshot.get("market_snapshot_id", pd.Series([""])).iloc[0]) if not snapshot.empty and "market_snapshot_id" in snapshot else ""
    ts = str(snapshot.get("timestamp_utc", pd.Series([pd.Timestamp.now(tz="UTC").isoformat()])).iloc[0]) if not snapshot.empty else pd.Timestamp.now(tz="UTC").isoformat()
    return {
        "market_snapshot_id": snapshot_id,
        "score_timestamp_utc": ts,
        "market_environment_score_v0": standard_score,
        "market_environment_score_observed_v0": observed_score,
        "market_environment_score_proxy_augmented_v0": proxy_score,
        "market_score_coverage_pct": round(float(proxy_cov * 100), 2),
        "market_score_confidence": proxy_conf,
        "market_score_data_mode": "proxy_augmented" if proxy_score is not None else "unavailable",
        "market_score_version": MARKET_SCORE_VERSION,
        "component_weight_version": COMPONENT_WEIGHT_VERSION,
        "market_score_components_json": json.dumps(components, ensure_ascii=False),
        "market_score_unavailable_components": "; ".join(proxy_unavail),
        "market_score_observed_coverage_pct": round(float(observed_cov * 100), 2),
        "market_score_observed_confidence": observed_conf,
        "git_commit_sha": p2b.git_commit_sha(),
        "calculation_version": CALCULATION_VERSION,
        "metric_definition_version": METRIC_DEFINITION_VERSION,
        "input_snapshot_hash": "",
        "raw_payload_path": "",
        "raw_payload_hash": "",
    }


def calculate_execution_scores(option_context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if option_context.empty:
        return pd.DataFrame(columns=["option_snapshot_id", "decision_id", "trade_id", "execution_score_v0", "execution_score_coverage_pct", "execution_score_confidence", "execution_score_components_json", "execution_score_version"])
    for _, row in option_context.iterrows():
        score = 0.0
        available = 0.0
        comps: list[dict[str, Any]] = []

        def add(name: str, points: float, value: Any, awarded: float, notes: str) -> None:
            nonlocal score, available
            if value is None or pd.isna(value) or value == "":
                comps.append({"component": name, "score": 0, "max_points": points, "available": False, "value": None, "notes": "unavailable"})
                return
            available += points
            score += max(0.0, min(points, awarded))
            comps.append({"component": name, "score": max(0.0, min(points, awarded)), "max_points": points, "available": True, "value": value, "notes": notes})

        spread = safe_float(row.get("spread_pct_of_mid"))
        add("Spread quality", 40, spread if pd.notna(spread) else None, 40 if spread <= 0.10 else 25 if spread <= 0.15 else 0, "spread_pct_of_mid")
        collected = p2a.parse_ts(row.get("collected_at_utc"))
        snap = p2a.parse_ts(row.get("snapshot_timestamp_utc"))
        age_min = abs((collected - snap).total_seconds()) / 60 if collected is not None and snap is not None else math.nan
        add("Quote freshness", 15, age_min if pd.notna(age_min) else None, 15 if age_min <= 15 else 8 if age_min <= 60 else 0, "minutes between snapshot and collection")
        oi = safe_float(row.get("open_interest"))
        add("Open interest", 15, oi if pd.notna(oi) else None, 15 if oi >= 500 else 8 if oi >= 100 else 0, "open_interest")
        vol = safe_float(row.get("volume"))
        add("Volume", 10, vol if pd.notna(vol) else None, 10 if vol >= 100 else 5 if vol >= 20 else 0, "volume")
        dte = safe_float(row.get("dte"))
        add("DTE alignment", 10, dte if pd.notna(dte) else None, 10 if 75 <= dte <= 105 else 7 if 45 <= dte <= 120 else 0, "90DTE target")
        delta = safe_float(row.get("delta"))
        add("Delta alignment", 10, delta if pd.notna(delta) else None, 10 if 0.55 <= delta <= 0.65 else 5 if 0.45 <= delta <= 0.70 else 0, "Delta 0.6 target")
        coverage = available / 100.0
        exec_score = round(score / available * 100, 2) if available and coverage >= 0.60 else None
        rows.append(
            {
                "option_snapshot_id": row.get("option_snapshot_id"),
                "decision_id": row.get("decision_id"),
                "trade_id": row.get("trade_id", ""),
                "execution_score_v0": exec_score,
                "execution_score_coverage_pct": round(coverage * 100, 2),
                "execution_score_confidence": "high" if coverage >= 0.85 else "medium" if coverage >= 0.60 else "low",
                "execution_score_components_json": json.dumps(comps, ensure_ascii=False),
                "execution_score_version": EXECUTION_SCORE_VERSION,
                "git_commit_sha": p2b.git_commit_sha(),
                "calculation_version": CALCULATION_VERSION,
                "metric_definition_version": "execution_score_v0",
            }
        )
    return pd.DataFrame(rows)


def resolve_github_repository(root: Path) -> str:
    for key in ["GITHUB_REPOSITORY", "MARKET_ENV_GITHUB_REPOSITORY", "MORITA_GITHUB_REPOSITORY"]:
        value = os.environ.get(key, "").strip()
        if re.match(r"^[^/\s]+/[^/\s]+$", value):
            return value
    config = root / ".git" / "config"
    if config.exists():
        text = config.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"github\.com[:/](?P<repo>[^/\s]+/[^/\s.]+)(?:\.git)?", text)
        if match:
            return match.group("repo")
    return ""


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "morita-market-environment-audit"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_api_json(url: str) -> Any:
    try:
        req = urllib.request.Request(url, headers=github_headers())
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def github_api_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=github_headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def github_main_tree(repo: str) -> dict[str, dict[str, Any]]:
    if not repo:
        return {}
    url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
    data = github_api_json(url)
    if not isinstance(data, dict) or "tree" not in data:
        return {}
    return {str(item.get("path", "")).replace("\\", "/"): item for item in data.get("tree", []) if item.get("path")}


def github_file_text(repo: str, path: str) -> str:
    if not repo or not path:
        return ""
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref=main"
    data = github_api_json(url)
    if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        except Exception:
            return ""
    raw_url = f"https://raw.githubusercontent.com/{repo}/main/{urllib.parse.quote(path)}"
    raw = github_api_bytes(raw_url)
    return raw.decode("utf-8", errors="ignore") if raw else ""


def github_workflow_runs(repo: str, workflow_path: str | None = None) -> dict[str, Any]:
    if not repo:
        return {"runs": [], "latest_successful_run": "", "workflow_execution_success_rate": np.nan, "started_at": "", "completed_at": ""}
    encoded = urllib.parse.quote(workflow_path or "", safe="")
    if workflow_path:
        url = f"https://api.github.com/repos/{repo}/actions/workflows/{encoded}/runs?branch=main&per_page=50"
    else:
        url = f"https://api.github.com/repos/{repo}/actions/runs?branch=main&per_page=50"
    data = github_api_json(url)
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    completed = [r for r in runs if r.get("status") == "completed"]
    successful = [r for r in completed if r.get("conclusion") == "success"]
    latest = successful[0] if successful else None
    return {
        "runs": runs,
        "latest_successful_run": latest.get("html_url", "") if latest else "",
        "workflow_execution_success_rate": round(len(successful) / len(completed), 4) if completed else np.nan,
        "started_at": latest.get("run_started_at", "") if latest else "",
        "completed_at": latest.get("updated_at", "") if latest else "",
    }


def github_latest_file_commit_timestamp(repo: str, path: str) -> str:
    if not repo or not path:
        return ""
    url = f"https://api.github.com/repos/{repo}/commits?sha=main&path={urllib.parse.quote(path)}&per_page=1"
    data = github_api_json(url)
    if isinstance(data, list) and data:
        commit = data[0].get("commit", {})
        return commit.get("committer", {}).get("date", "") or commit.get("author", {}).get("date", "")
    return ""


def tree_files_under(tree: dict[str, dict[str, Any]], prefix: str) -> list[str]:
    prefix = prefix.strip("/").replace("\\", "/")
    return sorted(path for path, item in tree.items() if item.get("type") == "blob" and (path == prefix or path.startswith(prefix + "/")))


def deployment_audit(root: Path) -> pd.DataFrame:
    repo = resolve_github_repository(root)
    tree = github_main_tree(repo)
    source_basis = "github_main_api" if tree else "local_fallback_repo_unresolved_or_api_unavailable"
    components = [
        ("option_snapshot_workflow", ".github/workflows/option_snapshot.yml", "option_chain_snapshots"),
        ("daily_scan_workflow", ".github/workflows/daily_scan.yml", "scanner_alerts"),
        ("tests_workflow", ".github/workflows/tests.yml", ""),
        ("market_bomb_phase1", "market_bomb_phase1.py", "market_bomb_snapshots"),
        ("market_bomb_phase2a", "market_bomb_phase2a.py", "morita_decision_context"),
        ("market_bomb_phase2b", "market_bomb_phase2b.py", "morita_signal_market_context"),
        ("market_environment_score_v0", "market_environment_score_v0.py", "market_environment_scores"),
        ("market_structure_dashboard", "market_structure_dashboard.py", "output"),
        ("production_scanner", "scripts/production_scanner_entry.py", "scanner_alerts"),
        ("pullback_mode_script", "scripts/production_scanner_entry_pullback_mode.py", ""),
    ]
    rows = []
    for component, rel_path, out_rel in components:
        local_path = root / rel_path
        main_branch_checked = bool(tree)
        local_exists = local_path.exists()
        exists_on_main: Any = bool(rel_path in tree) if main_branch_checked else ""
        text = github_file_text(repo, rel_path) if tree and rel_path.endswith((".yml", ".yaml")) else ""
        if not text and rel_path.endswith((".yml", ".yaml")) and local_path.exists():
            text = local_path.read_text(encoding="utf-8", errors="ignore")
        out_files = tree_files_under(tree, out_rel) if tree and out_rel else []
        local_out = root / out_rel if out_rel else None
        local_files = [p for p in local_out.rglob("*") if p.is_file()] if local_out and local_out.exists() else []
        record_count = len(out_files) if tree and out_rel else len(local_files)
        mtimes = [pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC") for p in local_files]
        runs = github_workflow_runs(repo, rel_path) if tree and rel_path.startswith(".github/workflows/") else {"latest_successful_run": "", "workflow_execution_success_rate": np.nan, "started_at": "", "completed_at": ""}
        has_raw_snapshot = bool(out_rel == "option_chain_snapshots" and record_count)
        has_market_bomb = bool(component.startswith("market_bomb") and record_count)
        rows.append(
            {
                "component": component,
                "source_basis": source_basis,
                "github_repository": repo,
                "main_branch_checked": main_branch_checked,
                "exists_on_main": exists_on_main,
                "local_exists": bool(local_exists),
                "workflow_or_script": rel_path,
                "schedule": workflow_schedule_text(text),
                "latest_successful_run": runs.get("latest_successful_run", ""),
                "workflow_execution_success_rate": runs.get("workflow_execution_success_rate", np.nan),
                "github_workflow_started_at_utc": runs.get("started_at", ""),
                "github_workflow_completed_at_utc": runs.get("completed_at", ""),
                "output_path": out_rel,
                "persistence_type": "github_main_files" if tree and record_count else "local_filesystem" if local_files else "not_deployed" if main_branch_checked and not exists_on_main else "no_output_found",
                "oldest_file_timestamp_utc": min(mtimes).isoformat() if mtimes else "",
                "newest_file_timestamp_utc": max(mtimes).isoformat() if mtimes else "",
                "record_count": record_count,
                "strict_entry_usable": bool(has_market_bomb and component in {"market_bomb_phase1", "market_bomb_phase2a", "market_bomb_phase2b"}),
                "prior_session_context_usable": bool(has_raw_snapshot or has_market_bomb),
                "historical_reconstructed_usable": bool(record_count),
                "notes": "" if main_branch_checked and exists_on_main else "not_deployed_on_main" if main_branch_checked else "github_main_not_checked_repository_unresolved_or_api_unavailable",
            }
        )
    return pd.DataFrame(rows)


def workflow_schedule(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return workflow_schedule_text(text)


def workflow_schedule_text(text: str) -> str:
    return "; ".join(line.strip() for line in text.splitlines() if "cron:" in line)


def parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value in [None, ""]:
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts


def first_nested_value(obj: Any, keys: set[str]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in keys and v not in [None, ""]:
                return v
        for v in obj.values():
            found = first_nested_value(v, keys)
            if found not in [None, ""]:
                return found
    elif isinstance(obj, list):
        for item in obj[:50]:
            found = first_nested_value(item, keys)
            if found not in [None, ""]:
                return found
    return None


def collect_nested_keys(obj: Any, limit: int = 5000) -> set[str]:
    keys: set[str] = set()
    stack = [obj]
    seen = 0
    while stack and seen < limit:
        item = stack.pop()
        seen += 1
        if isinstance(item, dict):
            keys.update(str(k).lower() for k in item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item[:100])
    return keys


def infer_timestamp_from_filename(path: str) -> pd.Timestamp | None:
    match = re.search(r"(20\d{6})[_-]?(\d{4,6})?", path)
    if not match:
        return None
    date_part = match.group(1)
    time_part = (match.group(2) or "000000").ljust(6, "0")[:6]
    return parse_timestamp(f"{date_part}{time_part}")


def classify_us_session(ts_utc: pd.Timestamp | None) -> str:
    if ts_utc is None or pd.isna(ts_utc):
        return "unknown"
    et = ts_utc.tz_convert(ET)
    t = et.time()
    if time(9, 30) <= t < time(16, 0):
        return "intraday"
    if time(16, 0) <= t < time(20, 0):
        return "after_close"
    if time(4, 0) <= t < time(9, 30):
        return "same_session_pre_open"
    if t >= time(20, 0) or t < time(4, 0):
        return "prior_session_eod"
    return "unknown"


def session_subtype(session_category: str) -> str:
    return {
        "same_session_pre_open": "pre_open",
        "intraday": "regular_hours",
        "after_close": "post_close",
        "prior_session_eod": "overnight",
        "unknown": "unknown",
    }.get(session_category, "unknown")


def next_us_open(ts_utc: pd.Timestamp | None) -> pd.Timestamp | None:
    if ts_utc is None or pd.isna(ts_utc):
        return None
    et = ts_utc.tz_convert(ET)
    candidate = et.replace(hour=9, minute=30, second=0, microsecond=0)
    if et >= candidate:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.tz_convert("UTC")


def snapshot_usability(ts_utc: pd.Timestamp | None, raw_complete: bool, gex_success: bool) -> dict[str, Any]:
    phase = classify_us_session(ts_utc)
    next_open = next_us_open(ts_utc)
    age_next_open = ((next_open - ts_utc).total_seconds() / 3600.0) if next_open is not None and ts_utc is not None else math.nan
    strict_entry = bool(raw_complete and gex_success and phase in {"same_session_pre_open", "intraday"} and age_next_open <= 6)
    prior_context = bool(raw_complete and phase in {"after_close", "prior_session_eod"})
    historical = bool(raw_complete and gex_success)
    return {
        "us_session_phase": phase,
        "strict_entry_usable": strict_entry,
        "prior_session_context_usable": prior_context,
        "historical_reconstructed_usable": historical,
        "snapshot_age_at_next_us_open_hours": round(age_next_open, 2) if pd.notna(age_next_open) else np.nan,
    }


def strict_entry_usable_for_decision(
    effective_available_at_utc: Any,
    collected_at_utc: Any,
    as_of_timestamp_utc: Any,
    decision_timestamp_utc: Any,
    economic_quality: str,
    session_category: str,
    freshness_threshold_hours: float = GEX_FRESHNESS_THRESHOLD_HOURS,
) -> bool:
    effective = parse_timestamp(effective_available_at_utc)
    collected = parse_timestamp(collected_at_utc)
    as_of = parse_timestamp(as_of_timestamp_utc)
    decision = parse_timestamp(decision_timestamp_utc)
    if any(v is None for v in [effective, collected, as_of, decision]):
        return False
    age_hours = (decision - as_of).total_seconds() / 3600.0
    return bool(
        effective <= decision
        and collected <= decision
        and 0 <= age_hours <= freshness_threshold_hours
        and economic_quality in {"high", "medium"}
        and session_category in {"same_session_pre_open", "intraday"}
    )


def get_case_insensitive(row: dict[str, Any], names: list[str], default: Any = None) -> Any:
    lowered = {str(k).lower().replace("_", ""): v for k, v in row.items()}
    for name in names:
        key = name.lower().replace("_", "")
        if key in lowered and lowered[key] not in [None, ""]:
            return lowered[key]
    return default


def normalize_option_rows(payload: Any, frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if frame is not None and not frame.empty:
        for raw in frame.to_dict(orient="records"):
            side = str(get_case_insensitive(raw, ["option_type", "optionType", "contractType", "type", "side", "putCall"], "")).lower()
            if "call" in side:
                cp = "call"
            elif "put" in side:
                cp = "put"
            else:
                cp = "unknown"
            rows.append(
                {
                    "call_put_flag": cp,
                    "strike": safe_float(get_case_insensitive(raw, ["strike", "strikePrice"])),
                    "expiration": get_case_insensitive(raw, ["expiration", "expiry", "expirationDate"]),
                    "open_interest": safe_float(get_case_insensitive(raw, ["open_interest", "openInterest", "oi"])),
                    "implied_volatility": safe_float(get_case_insensitive(raw, ["implied_volatility", "impliedVolatility", "iv"])),
                    "bid": safe_float(get_case_insensitive(raw, ["bid"])),
                    "ask": safe_float(get_case_insensitive(raw, ["ask"])),
                    "last": safe_float(get_case_insensitive(raw, ["last", "lastPrice"])),
                    "contract_multiplier": safe_float(get_case_insensitive(raw, ["contract_multiplier", "multiplier"], 100), 100),
                    "quote_timestamp": get_case_insensitive(raw, ["option_quote_timestamp_utc", "quote_timestamp_utc", "quoteTime", "lastTradeDate"]),
                }
            )
        return rows
    if isinstance(payload, dict):
        for key, side in [("calls", "call"), ("puts", "put"), ("call", "call"), ("put", "put")]:
            values = payload.get(key)
            if isinstance(values, dict):
                values = values.get("options") or values.get("contracts") or values.get("data")
            if not isinstance(values, list):
                continue
            for raw in values:
                if not isinstance(raw, dict):
                    continue
                rows.append(
                    {
                        "call_put_flag": side,
                        "strike": safe_float(get_case_insensitive(raw, ["strike", "strikePrice"])),
                        "expiration": get_case_insensitive(raw, ["expiration", "expiry", "expirationDate"]),
                        "open_interest": safe_float(get_case_insensitive(raw, ["open_interest", "openInterest", "oi"])),
                        "implied_volatility": safe_float(get_case_insensitive(raw, ["implied_volatility", "impliedVolatility", "iv"])),
                        "bid": safe_float(get_case_insensitive(raw, ["bid"])),
                        "ask": safe_float(get_case_insensitive(raw, ["ask"])),
                        "last": safe_float(get_case_insensitive(raw, ["last", "lastPrice"])),
                        "contract_multiplier": safe_float(get_case_insensitive(raw, ["contract_multiplier", "multiplier"], 100), 100),
                        "quote_timestamp": get_case_insensitive(raw, ["option_quote_timestamp_utc", "quote_timestamp_utc", "quoteTime", "lastTradeDate"]),
                    }
                )
    return rows


def extract_underlying_price(payload: Any, frame: pd.DataFrame | None) -> float:
    if frame is not None and not frame.empty:
        raw = frame.iloc[0].to_dict()
        value = get_case_insensitive(raw, ["underlying_price", "underlyingPrice", "spot", "regularMarketPrice", "price"])
        val = safe_float(value)
        if pd.notna(val):
            return val
    value = first_nested_value(payload, {"underlying_price", "underlyingprice", "spot", "regularmarketprice", "price"})
    return safe_float(value)


def extract_first_timestamp(payload: Any, frame: pd.DataFrame | None, names: list[str]) -> pd.Timestamp | None:
    if frame is not None and not frame.empty:
        raw = frame.iloc[0].to_dict()
        value = get_case_insensitive(raw, names)
        ts = parse_timestamp(value)
        if ts is not None:
            return ts
    keys = {n.lower() for n in names} | {n.lower().replace("_", "") for n in names}
    return parse_timestamp(first_nested_value(payload, keys))


def option_quality_metrics(option_rows: list[dict[str, Any]], underlying_price: float, as_of: pd.Timestamp | None) -> dict[str, Any]:
    total = len(option_rows)
    invalid_or_negative_oi = 0
    invalid_iv = 0
    missing_expiry = 0
    missing_call_put = 0
    missing_underlying = 0 if pd.notna(underlying_price) and underlying_price > 0 else total
    stale_quote = 0
    valid_for_calc = 0
    expiry_cache: dict[str, pd.Timestamp | None] = {}
    for row in option_rows:
        oi = safe_float(row.get("open_interest"))
        iv = safe_float(row.get("implied_volatility"))
        strike = safe_float(row.get("strike"))
        expiry_key = str(row.get("expiration", ""))
        if expiry_key not in expiry_cache:
            expiry_cache[expiry_key] = parse_timestamp(row.get("expiration"))
        expiry_ts = expiry_cache[expiry_key]
        quote_ts = parse_timestamp(row.get("quote_timestamp"))
        if pd.isna(oi) or oi < 0:
            invalid_or_negative_oi += 1
        if pd.isna(iv) or iv <= 0 or iv > 5:
            invalid_iv += 1
        if expiry_ts is None:
            missing_expiry += 1
        if row.get("call_put_flag") not in {"call", "put"}:
            missing_call_put += 1
        if as_of is not None and quote_ts is not None and (as_of - quote_ts).total_seconds() > 24 * 3600:
            stale_quote += 1
        if (
            pd.notna(underlying_price)
            and underlying_price > 0
            and pd.notna(strike)
            and strike > 0
            and pd.notna(oi)
            and oi >= 0
            and pd.notna(iv)
            and 0 < iv <= 5
            and expiry_ts is not None
            and row.get("call_put_flag") in {"call", "put"}
        ):
            valid_for_calc += 1
    required_checks = 9
    present_checks = 0
    present_checks += int(pd.notna(underlying_price) and underlying_price > 0)
    present_checks += int(total > 0)
    present_checks += int(total > 0 and missing_expiry < total)
    present_checks += int(total > 0 and missing_call_put < total)
    present_checks += int(total > 0 and any(pd.notna(safe_float(r.get("strike"))) for r in option_rows))
    present_checks += int(total > 0 and invalid_or_negative_oi < total)
    present_checks += int(total > 0 and invalid_iv < total)
    present_checks += int(total > 0 and any(pd.notna(safe_float(r.get("contract_multiplier"))) for r in option_rows))
    present_checks += int(valid_for_calc > 0)
    input_rate = present_checks / required_checks
    calc_rate = valid_for_calc / total if total else 0
    if input_rate >= 0.95 and calc_rate >= 0.90 and stale_quote == 0:
        economic_quality = "high"
    elif input_rate >= 0.80 and calc_rate >= 0.70:
        economic_quality = "medium"
    elif input_rate >= 0.60 and calc_rate > 0:
        economic_quality = "low"
    else:
        economic_quality = "unusable"
    return {
        "option_contract_count": total,
        "valid_contract_count": valid_for_calc,
        "input_completeness_rate": round(input_rate, 4),
        "calculation_success_rate": round(calc_rate, 4),
        "economic_quality": economic_quality,
        "invalid_or_negative_oi_count": invalid_or_negative_oi,
        "invalid_iv_count": invalid_iv,
        "missing_expiry_bucket_count": missing_expiry,
        "missing_call_put_side_count": missing_call_put,
        "missing_underlying_price_count": missing_underlying,
        "stale_quote_count": stale_quote,
    }


def normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_gamma(spot: float, strike: float, iv: float, years: float) -> float:
    if spot <= 0 or strike <= 0 or iv <= 0 or years <= 0:
        return math.nan
    vol_sqrt = iv * math.sqrt(years)
    if vol_sqrt <= 0:
        return math.nan
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * years) / vol_sqrt
    return normal_pdf(d1) / (spot * vol_sqrt)


def dealer_gamma_proxy_from_net_gamma(net_gamma_open_interest_proxy: float, assumption: str | None) -> float:
    if not assumption:
        return math.nan
    if assumption != DEALER_GAMMA_PROXY_ASSUMPTION:
        return math.nan
    return -net_gamma_open_interest_proxy


def gamma_contribution_at_price(row: dict[str, Any], spot: float, as_of: pd.Timestamp) -> float:
    side = row.get("call_put_flag")
    strike = safe_float(row.get("strike"))
    oi = safe_float(row.get("open_interest"))
    iv = safe_float(row.get("implied_volatility"))
    mult = safe_float(row.get("contract_multiplier"), 100)
    expiry_ts = parse_timestamp(row.get("expiration"))
    if expiry_ts is None and row.get("expiration"):
        expiry_ts = parse_timestamp(str(row.get("expiration")) + "T20:00:00Z")
    if (
        expiry_ts is None
        or pd.isna(strike)
        or pd.isna(oi)
        or pd.isna(iv)
        or spot <= 0
        or strike <= 0
        or oi < 0
        or iv <= 0
        or side not in {"call", "put"}
    ):
        return math.nan
    years = max((expiry_ts - as_of).total_seconds() / (365.25 * 24 * 3600), 1 / 365.25)
    gamma = bs_gamma(spot, strike, iv, years)
    if pd.isna(gamma):
        return math.nan
    sign = 1.0 if side == "call" else -1.0
    return sign * gamma * oi * mult * spot * spot * 0.01


def aggregate_gamma_proxy_at_price(option_rows: list[dict[str, Any]], spot: float, as_of: pd.Timestamp) -> float:
    vals = [gamma_contribution_at_price(row, spot, as_of) for row in option_rows]
    vals = [v for v in vals if pd.notna(v)]
    return float(np.sum(vals)) if vals else math.nan


def gamma_grid_values(option_rows: list[dict[str, Any]], grid: np.ndarray, as_of: pd.Timestamp) -> np.ndarray:
    strikes = []
    open_interest = []
    ivs = []
    multipliers = []
    signs = []
    years = []
    expiry_cache: dict[str, pd.Timestamp | None] = {}
    for row in option_rows:
        side = row.get("call_put_flag")
        strike = safe_float(row.get("strike"))
        oi = safe_float(row.get("open_interest"))
        iv = safe_float(row.get("implied_volatility"))
        mult = safe_float(row.get("contract_multiplier"), 100)
        expiry_key = str(row.get("expiration", ""))
        if expiry_key not in expiry_cache:
            expiry_ts = parse_timestamp(row.get("expiration"))
            if expiry_ts is None and row.get("expiration"):
                expiry_ts = parse_timestamp(str(row.get("expiration")) + "T20:00:00Z")
            expiry_cache[expiry_key] = expiry_ts
        expiry_ts = expiry_cache[expiry_key]
        if (
            expiry_ts is None
            or side not in {"call", "put"}
            or pd.isna(strike)
            or pd.isna(oi)
            or pd.isna(iv)
            or strike <= 0
            or oi < 0
            or iv <= 0
        ):
            continue
        strikes.append(strike)
        open_interest.append(oi)
        ivs.append(iv)
        multipliers.append(mult)
        signs.append(1.0 if side == "call" else -1.0)
        years.append(max((expiry_ts - as_of).total_seconds() / (365.25 * 24 * 3600), 1 / 365.25))
    if not strikes:
        return np.full(len(grid), np.nan)
    grid_arr = np.asarray(grid, dtype=float)[:, None]
    strike_arr = np.asarray(strikes, dtype=float)[None, :]
    oi_arr = np.asarray(open_interest, dtype=float)[None, :]
    iv_arr = np.asarray(ivs, dtype=float)[None, :]
    mult_arr = np.asarray(multipliers, dtype=float)[None, :]
    sign_arr = np.asarray(signs, dtype=float)[None, :]
    years_arr = np.asarray(years, dtype=float)[None, :]
    vol_sqrt = iv_arr * np.sqrt(years_arr)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        d1 = (np.log(grid_arr / strike_arr) + 0.5 * iv_arr * iv_arr * years_arr) / vol_sqrt
        gamma = np.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (grid_arr * vol_sqrt)
        contribution = sign_arr * gamma * oi_arr * mult_arr * grid_arr * grid_arr * 0.01
    return np.nansum(contribution, axis=1)


def gamma_flip_quality(distance_pct: float) -> tuple[str, str, str]:
    if pd.isna(distance_pct):
        return "unavailable", "", ""
    abs_distance = abs(distance_pct)
    if abs_distance <= GAMMA_FLIP_WARNING_DISTANCE_PCT:
        return "usable", "", ""
    if abs_distance <= GAMMA_FLIP_REJECT_DISTANCE_PCT:
        return "low", "far_from_spot", ""
    return "unusable", "far_from_spot", "far_root_rejected"


def local_gamma_flip_search(option_rows: list[dict[str, Any]], underlying_price: float, as_of: pd.Timestamp | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if as_of is None or pd.isna(underlying_price) or underlying_price <= 0 or not option_rows:
        return {
            "gamma_flip_proxy": np.nan,
            "spot_vs_gamma_flip_pct": np.nan,
            "gamma_flip_search_low": np.nan,
            "gamma_flip_search_high": np.nan,
            "gamma_flip_search_range_pct": np.nan,
            "gamma_flip_grid_size": 0,
            "gamma_flip_root_count": 0,
            "gamma_flip_selected_root": np.nan,
            "gamma_flip_selection_reason": "",
            "gamma_flip_distance_pct": np.nan,
            "gamma_flip_status": "invalid_input_or_unit_check_failed",
            "gamma_flip_warning": "",
            "gamma_flip_failure_reason": "missing_input",
            "gamma_flip_proxy_quality": "unusable",
            "boundary_root_warning": "",
        }, []

    search_low = underlying_price * GAMMA_FLIP_SEARCH_LOW_PCT
    search_high = underlying_price * GAMMA_FLIP_SEARCH_HIGH_PCT
    grid = np.linspace(search_low, search_high, GAMMA_FLIP_MINIMUM_GRID_SIZE)
    diagnostics: list[dict[str, Any]] = []
    values = list(zip([float(x) for x in grid], [float(x) if pd.notna(x) else math.nan for x in gamma_grid_values(option_rows, grid, as_of)]))

    roots: list[float] = []
    for (p0, g0), (p1, g1) in zip(values, values[1:]):
        if pd.isna(g0) or pd.isna(g1):
            continue
        if g0 == 0:
            roots.append(p0)
            continue
        if (g0 < 0 < g1) or (g0 > 0 > g1):
            root = p0 + (p1 - p0) * (0 - g0) / (g1 - g0)
            roots.append(float(root))
    roots = sorted(set(round(r, 8) for r in roots))

    selected = math.nan
    selection_reason = ""
    status = "no_local_flip"
    warning = ""
    failure_reason = ""
    quality = "unavailable"
    boundary_warning = ""
    distance_pct = math.nan
    if roots:
        selected = min(roots, key=lambda r: abs(r - underlying_price))
        distance_pct = (selected - underlying_price) / underlying_price
        quality, warning, failure_reason = gamma_flip_quality(distance_pct)
        status = failure_reason or "local_flip_found"
        selection_reason = "nearest_to_spot"
        grid_step = (search_high - search_low) / max(GAMMA_FLIP_MINIMUM_GRID_SIZE - 1, 1)
        if selected <= search_low + grid_step or selected >= search_high - grid_step:
            boundary_warning = "boundary_root_warning"
            warning = ";".join([w for w in [warning, boundary_warning] if w])
    else:
        failure_reason = "no_sign_change_in_local_search_range"
        selection_reason = "no_local_flip"

    root_json = json.dumps(roots, ensure_ascii=False)
    for grid_price, agg in values:
        diagnostics.append(
            {
                "spot": underlying_price,
                "gamma_flip_search_low": round(search_low, 6),
                "gamma_flip_search_high": round(search_high, 6),
                "gamma_flip_grid_size": GAMMA_FLIP_MINIMUM_GRID_SIZE,
                "grid_price": round(grid_price, 6),
                "aggregate_gamma_proxy_at_grid": round(agg, 6) if pd.notna(agg) else np.nan,
                "grid_sign": "positive" if pd.notna(agg) and agg > 0 else "negative" if pd.notna(agg) and agg < 0 else "zero" if pd.notna(agg) else "unavailable",
                "sign_change_segment_count": len(roots),
                "root_candidate_count": len(roots),
                "root_candidate_values_json": root_json,
                "selected_root": round(selected, 6) if pd.notna(selected) else np.nan,
                "selected_root_distance_pct": round(distance_pct, 6) if pd.notna(distance_pct) else np.nan,
                "selected_root_validation_passed": quality in {"usable", "low"},
                "boundary_root_warning": boundary_warning,
                "gamma_flip_status": status,
                "gamma_flip_selection_reason": selection_reason,
                "gamma_flip_failure_reason": failure_reason,
            }
        )

    entry_flip = selected if quality in {"usable", "low"} else np.nan
    return {
        "gamma_flip_proxy": round(entry_flip, 4) if pd.notna(entry_flip) else np.nan,
        "spot_vs_gamma_flip_pct": round(distance_pct * 100, 4) if pd.notna(distance_pct) else np.nan,
        "gamma_flip_search_low": round(search_low, 4),
        "gamma_flip_search_high": round(search_high, 4),
        "gamma_flip_search_range_pct": round((GAMMA_FLIP_SEARCH_HIGH_PCT - GAMMA_FLIP_SEARCH_LOW_PCT) * 100, 4),
        "gamma_flip_grid_size": GAMMA_FLIP_MINIMUM_GRID_SIZE,
        "gamma_flip_root_count": len(roots),
        "gamma_flip_selected_root": round(selected, 4) if pd.notna(selected) else np.nan,
        "gamma_flip_selection_reason": selection_reason,
        "gamma_flip_distance_pct": round(distance_pct, 6) if pd.notna(distance_pct) else np.nan,
        "gamma_flip_status": status,
        "gamma_flip_warning": warning,
        "gamma_flip_failure_reason": failure_reason,
        "gamma_flip_proxy_quality": quality,
        "boundary_root_warning": boundary_warning,
    }, diagnostics


def combine_row_economic_quality(raw_chain_quality: str, net_gex_quality: str, gamma_flip_quality_value: str) -> str:
    if raw_chain_quality == "unusable" or net_gex_quality in {"unusable", "unavailable"}:
        return "unusable"
    if gamma_flip_quality_value == "unusable":
        return "low"
    if raw_chain_quality == "low" or net_gex_quality == "low" or gamma_flip_quality_value in {"low", "unavailable"}:
        return "low"
    return "high" if raw_chain_quality == "high" and net_gex_quality == "high" else "medium"


def contract_validation_examples(option_rows: list[dict[str, Any]], underlying_price: float, as_of: pd.Timestamp | None) -> list[dict[str, Any]]:
    if as_of is None or pd.isna(underlying_price) or underlying_price <= 0 or not option_rows:
        return []

    def prepared(row: dict[str, Any], label: str) -> dict[str, Any]:
        strike = safe_float(row.get("strike"))
        bid = safe_float(row.get("bid"))
        ask = safe_float(row.get("ask"))
        mid = safe_float(row.get("mid"))
        if pd.isna(mid) and pd.notna(bid) and pd.notna(ask):
            mid = (bid + ask) / 2
        iv = safe_float(row.get("implied_volatility"))
        oi = safe_float(row.get("open_interest"))
        mult = safe_float(row.get("contract_multiplier"), 100)
        expiry = row.get("expiration", "")
        expiry_ts = parse_timestamp(expiry)
        if expiry_ts is None and expiry:
            expiry_ts = parse_timestamp(str(expiry) + "T20:00:00Z")
        years = max((expiry_ts - as_of).total_seconds() / (365.25 * 24 * 3600), 1 / 365.25) if expiry_ts is not None else math.nan
        gamma = bs_gamma(underlying_price, strike, iv, years) if pd.notna(years) else math.nan
        gamma_notional = gamma * mult * underlying_price * underlying_price * 0.01 if pd.notna(gamma) else math.nan
        contribution = gamma_notional * oi if pd.notna(gamma_notional) and pd.notna(oi) else math.nan
        side = row.get("call_put_flag", "")
        signed = contribution if side == "call" else -contribution if side == "put" and pd.notna(contribution) else math.nan
        dte = (expiry_ts - as_of).total_seconds() / 86400 if expiry_ts is not None else math.nan
        return {
            "example_type": label,
            "expiration": expiry,
            "dte": round(dte, 4) if pd.notna(dte) else "",
            "option_type": side,
            "strike": strike if pd.notna(strike) else "",
            "bid": bid if pd.notna(bid) else "",
            "ask": ask if pd.notna(ask) else "",
            "mid": round(mid, 6) if pd.notna(mid) else "",
            "implied_volatility": iv if pd.notna(iv) else "",
            "open_interest": oi if pd.notna(oi) else "",
            "contract_multiplier": mult if pd.notna(mult) else "",
            "black_scholes_gamma": round(gamma, 10) if pd.notna(gamma) else "",
            "gamma_notional_per_contract": round(gamma_notional, 6) if pd.notna(gamma_notional) else "",
            "gamma_open_interest_contribution": round(contribution, 6) if pd.notna(contribution) else "",
            "signed_gamma_open_interest_contribution": round(signed, 6) if pd.notna(signed) else "",
            "sign_convention": DEALER_GAMMA_SIGN_CONVENTION,
            "dealer_gamma_proxy_assumption": DEALER_GAMMA_PROXY_ASSUMPTION,
        }

    valid = [
        r for r in option_rows
        if r.get("call_put_flag") in {"call", "put"}
        and pd.notna(safe_float(r.get("strike")))
        and pd.notna(safe_float(r.get("open_interest")))
        and pd.notna(safe_float(r.get("implied_volatility")))
    ]
    examples: list[tuple[str, dict[str, Any]]] = []
    for side in ["call", "put"]:
        side_rows = [r for r in valid if r.get("call_put_flag") == side]
        if not side_rows:
            continue
        atm = min(side_rows, key=lambda r: abs(safe_float(r.get("strike")) - underlying_price))
        examples.append((f"ATM {side}", atm))
        otm_rows = [r for r in side_rows if safe_float(r.get("strike")) > underlying_price] if side == "call" else [r for r in side_rows if safe_float(r.get("strike")) < underlying_price]
        if otm_rows:
            examples.append((f"OTM {side}", min(otm_rows, key=lambda r: abs(safe_float(r.get("strike")) - underlying_price))))
    if valid:
        max_oi = max(valid, key=lambda r: safe_float(r.get("open_interest"), 0))
        examples.append(("Max OI", max_oi))

    seen: set[tuple[str, str, str, str]] = set()
    output = []
    for label, row in examples:
        key = (label, str(row.get("call_put_flag")), str(row.get("strike")), str(row.get("expiration")))
        if key in seen:
            continue
        seen.add(key)
        output.append(prepared(row, label))
    return output[:5]


def calculate_gex_proxy_metrics(option_rows: list[dict[str, Any]], underlying_price: float, as_of: pd.Timestamp | None) -> dict[str, Any]:
    if as_of is None or pd.isna(underlying_price) or underlying_price <= 0 or not option_rows:
        return {
            "call_gamma_open_interest_proxy": np.nan,
            "put_gamma_open_interest_proxy": np.nan,
            "net_gamma_open_interest_proxy": np.nan,
            "dealer_gamma_proxy_assumption": "",
            "dealer_gamma_proxy": np.nan,
            "sign_convention": DEALER_GAMMA_SIGN_CONVENTION,
            "net_gex_proxy": np.nan,
            "gamma_flip_proxy": np.nan,
            "spot_vs_gamma_flip_pct": np.nan,
            "gamma_flip_search_low": np.nan,
            "gamma_flip_search_high": np.nan,
            "gamma_flip_search_range_pct": np.nan,
            "gamma_flip_grid_size": 0,
            "gamma_flip_root_count": 0,
            "gamma_flip_selected_root": np.nan,
            "gamma_flip_selection_reason": "",
            "gamma_flip_distance_pct": np.nan,
            "gamma_flip_status": "invalid_input_or_unit_check_failed",
            "gamma_flip_warning": "",
            "gamma_flip_failure_reason": "missing_input",
            "gamma_flip_proxy_quality": "unusable",
            "boundary_root_warning": "",
            "dealer_gamma_state": "Unavailable",
            "call_wall_proxy": np.nan,
            "put_wall_proxy": np.nan,
            "pinning_score_proxy": np.nan,
            "zero_dte_share_proxy": np.nan,
            "dealer_pressure_proxy": "Unavailable",
            "expected_move_proxy": np.nan,
        }
    gex_by_strike: dict[float, float] = {}
    call_oi_by_strike: dict[float, float] = {}
    put_oi_by_strike: dict[float, float] = {}
    call_gamma_oi_proxy = 0.0
    put_gamma_oi_proxy = 0.0
    total_oi = 0.0
    zero_dte_oi = 0.0
    expected_move_candidates: list[float] = []
    as_of_date = as_of.tz_convert(ET).date()
    expiry_cache: dict[str, pd.Timestamp | None] = {}
    for row in option_rows:
        side = row.get("call_put_flag")
        strike = safe_float(row.get("strike"))
        oi = safe_float(row.get("open_interest"))
        iv = safe_float(row.get("implied_volatility"))
        mult = safe_float(row.get("contract_multiplier"), 100)
        expiry_key = str(row.get("expiration", ""))
        if expiry_key not in expiry_cache:
            expiry_ts = parse_timestamp(row.get("expiration"))
            if expiry_ts is None and row.get("expiration"):
                expiry_ts = parse_timestamp(str(row.get("expiration")) + "T20:00:00Z")
            expiry_cache[expiry_key] = expiry_ts
        expiry_ts = expiry_cache[expiry_key]
        if expiry_ts is None or pd.isna(strike) or pd.isna(oi) or pd.isna(iv) or strike <= 0 or oi < 0 or iv <= 0:
            continue
        years = max((expiry_ts - as_of).total_seconds() / (365.25 * 24 * 3600), 1 / 365.25)
        gamma = bs_gamma(underlying_price, strike, iv, years)
        if pd.isna(gamma):
            continue
        unsigned_gex = gamma * oi * mult * underlying_price * underlying_price * 0.01
        if side == "call":
            call_gamma_oi_proxy += unsigned_gex
        elif side == "put":
            put_gamma_oi_proxy += unsigned_gex
        sign = 1.0 if side == "call" else -1.0 if side == "put" else 0.0
        gex = sign * unsigned_gex
        gex_by_strike[strike] = gex_by_strike.get(strike, 0.0) + gex
        if side == "call":
            call_oi_by_strike[strike] = call_oi_by_strike.get(strike, 0.0) + oi
        elif side == "put":
            put_oi_by_strike[strike] = put_oi_by_strike.get(strike, 0.0) + oi
        total_oi += oi
        if expiry_ts.tz_convert(ET).date() == as_of_date:
            zero_dte_oi += oi
        if abs(strike / underlying_price - 1.0) <= 0.03:
            expected_move_candidates.append(iv * math.sqrt(years))
    net_gamma_oi_proxy = call_gamma_oi_proxy - put_gamma_oi_proxy if gex_by_strike else np.nan
    dealer_gamma_proxy = dealer_gamma_proxy_from_net_gamma(net_gamma_oi_proxy, DEALER_GAMMA_PROXY_ASSUMPTION) if pd.notna(net_gamma_oi_proxy) else np.nan
    net_gex = float(net_gamma_oi_proxy) if pd.notna(net_gamma_oi_proxy) else np.nan
    flip_metrics, root_diagnostics = local_gamma_flip_search(option_rows, underlying_price, as_of)
    call_wall = max(call_oi_by_strike, key=call_oi_by_strike.get) if call_oi_by_strike else np.nan
    put_wall = max(put_oi_by_strike, key=put_oi_by_strike.get) if put_oi_by_strike else np.nan
    max_pin_oi = max(list(call_oi_by_strike.values()) + list(put_oi_by_strike.values())) if (call_oi_by_strike or put_oi_by_strike) else np.nan
    pinning = max_pin_oi / total_oi if total_oi and pd.notna(max_pin_oi) else np.nan
    zero_dte = zero_dte_oi / total_oi if total_oi else np.nan
    state_source = dealer_gamma_proxy if pd.notna(dealer_gamma_proxy) else net_gex
    state = "Positive Gamma" if pd.notna(state_source) and state_source >= 0 else "Negative Gamma" if pd.notna(state_source) else "Unavailable"
    pressure = "stabilizing_proxy" if state == "Positive Gamma" else "destabilizing_proxy" if state == "Negative Gamma" else "Unavailable"
    return {
        "call_gamma_open_interest_proxy": round(call_gamma_oi_proxy, 4) if gex_by_strike else np.nan,
        "put_gamma_open_interest_proxy": round(put_gamma_oi_proxy, 4) if gex_by_strike else np.nan,
        "net_gamma_open_interest_proxy": round(net_gamma_oi_proxy, 4) if pd.notna(net_gamma_oi_proxy) else np.nan,
        "dealer_gamma_proxy_assumption": DEALER_GAMMA_PROXY_ASSUMPTION,
        "dealer_gamma_proxy": round(dealer_gamma_proxy, 4) if pd.notna(dealer_gamma_proxy) else np.nan,
        "sign_convention": DEALER_GAMMA_SIGN_CONVENTION,
        "net_gex_proxy": round(net_gex, 4) if pd.notna(net_gex) else np.nan,
        "gamma_flip_proxy": flip_metrics["gamma_flip_proxy"],
        "spot_vs_gamma_flip_pct": flip_metrics["spot_vs_gamma_flip_pct"],
        "gamma_flip_search_low": flip_metrics["gamma_flip_search_low"],
        "gamma_flip_search_high": flip_metrics["gamma_flip_search_high"],
        "gamma_flip_search_range_pct": flip_metrics["gamma_flip_search_range_pct"],
        "gamma_flip_grid_size": flip_metrics["gamma_flip_grid_size"],
        "gamma_flip_root_count": flip_metrics["gamma_flip_root_count"],
        "gamma_flip_selected_root": flip_metrics["gamma_flip_selected_root"],
        "gamma_flip_selection_reason": flip_metrics["gamma_flip_selection_reason"],
        "gamma_flip_distance_pct": flip_metrics["gamma_flip_distance_pct"],
        "gamma_flip_status": flip_metrics["gamma_flip_status"],
        "gamma_flip_warning": flip_metrics["gamma_flip_warning"],
        "gamma_flip_failure_reason": flip_metrics["gamma_flip_failure_reason"],
        "gamma_flip_proxy_quality": flip_metrics["gamma_flip_proxy_quality"],
        "boundary_root_warning": flip_metrics["boundary_root_warning"],
        "_root_diagnostics_rows": root_diagnostics,
        "dealer_gamma_state": state,
        "call_wall_proxy": call_wall,
        "put_wall_proxy": put_wall,
        "pinning_score_proxy": round(pinning, 4) if pd.notna(pinning) else np.nan,
        "zero_dte_share_proxy": round(zero_dte, 4) if pd.notna(zero_dte) else np.nan,
        "dealer_pressure_proxy": pressure,
        "expected_move_proxy": round(float(np.nanmedian(expected_move_candidates)) * 100, 4) if expected_move_candidates else np.nan,
    }


def detect_raw_chain_quality(path: str, payload: Any, frame: pd.DataFrame | None) -> tuple[bool, bool, str]:
    if frame is not None:
        cols = {str(c).lower() for c in frame.columns}
        has_type = bool(cols & {"optiontype", "option_type", "contracttype", "type", "side", "putcall"})
        has_call_put = has_type or any("call" in c for c in cols) or any("put" in c for c in cols)
        has_core = bool(cols & {"strike", "strikeprice"}) and bool(cols & {"expiration", "expiry", "expirationdate", "dte"})
        has_quote = bool(cols & {"bid", "ask", "mid", "lastprice", "last"})
        has_oi = bool(cols & {"openinterest", "open_interest", "oi"})
        has_iv = bool(cols & {"impliedvolatility", "implied_volatility", "iv"})
        complete = bool(has_call_put and has_core and has_quote)
        return complete, bool(complete and has_oi and has_iv), "complete" if complete else "incomplete_columns"
    keys = collect_nested_keys(payload)
    has_calls = "calls" in keys or "call" in keys
    has_puts = "puts" in keys or "put" in keys
    has_core = bool(keys & {"strike", "strikeprice", "expiration", "expiry", "expirationdate", "dte"})
    has_quote = bool(keys & {"bid", "ask", "mid", "lastprice", "last"})
    has_oi = bool(keys & {"openinterest", "open_interest", "oi"})
    has_iv = bool(keys & {"impliedvolatility", "implied_volatility", "iv"})
    complete = bool(has_calls and has_puts and has_core and has_quote)
    return complete, bool(complete and has_oi and has_iv), "complete" if complete else "incomplete_payload"


def ticker_from_snapshot(path: str, payload: Any, frame: pd.DataFrame | None) -> str:
    if frame is not None and not frame.empty:
        for col in ["ticker", "underlying_ticker", "underlying", "symbol"]:
            if col in frame.columns and pd.notna(frame.iloc[0].get(col)):
                return str(frame.iloc[0].get(col)).upper()
    val = first_nested_value(payload, {"ticker", "underlying_ticker", "underlying", "symbol"})
    if val:
        val = str(val).upper().replace("$", "")
        for ticker in TICKERS_FOR_GEX_AUDIT:
            if ticker == val or val.startswith(ticker):
                return ticker
    lower = path.lower()
    for ticker in TICKERS_FOR_GEX_AUDIT:
        if re.search(rf"(^|[\\/_.-]){ticker.lower()}($|[\\/_.-])", lower):
            return ticker
    return ""


def parse_snapshot_file(path: str, raw: bytes | None, local_path: Path | None = None) -> dict[str, Any]:
    payload: Any = {}
    frame: pd.DataFrame | None = None
    corrupted = False
    if raw is None and local_path is not None:
        try:
            raw = local_path.read_bytes()
        except Exception:
            raw = None
    raw_payload_hash = hashlib.sha256(raw).hexdigest() if raw else ""
    try:
        suffix = Path(path).suffix.lower()
        if suffix == ".json" and raw is not None:
            payload = json.loads(raw.decode("utf-8"))
        elif suffix == ".csv" and local_path is not None and local_path.exists():
            frame = pd.read_csv(local_path)
        elif suffix == ".csv" and raw is not None:
            from io import BytesIO

            frame = pd.read_csv(BytesIO(raw))
        else:
            payload = {}
    except Exception:
        corrupted = True
    as_of = None
    timestamp_quality = "missing"
    if frame is not None and not frame.empty:
        for col in ["option_chain_as_of_timestamp_utc", "as_of_timestamp_utc", "snapshot_timestamp_utc", "timestamp_utc", "quote_timestamp_utc", "snapshot_date", "lastTradeDate"]:
            if col in frame.columns:
                as_of = parse_timestamp(frame.iloc[0].get(col))
                if as_of is not None:
                    timestamp_quality = f"embedded_column:{col}"
                    break
    if as_of is None and payload:
        val = first_nested_value(payload, {"option_chain_as_of_timestamp_utc", "as_of_timestamp_utc", "snapshot_timestamp_utc", "timestamp_utc", "quote_timestamp_utc", "snapshot_date", "lasttradedate", "quotetime", "regularmarkettime"})
        as_of = parse_timestamp(val)
        if as_of is not None:
            timestamp_quality = "embedded_payload"
    if as_of is None:
        as_of = infer_timestamp_from_filename(path)
        if as_of is not None:
            timestamp_quality = "filename_inferred_not_market_as_of"
    availability_basis = "as_of_timestamp_embedded" if timestamp_quality.startswith("embedded") else "inferred_from_collection"
    availability_confidence = "medium" if timestamp_quality.startswith("embedded") else "low"
    file_created = None
    git_commit_ts = None
    if local_path is not None and local_path.exists():
        file_created = pd.Timestamp(local_path.stat().st_ctime, unit="s", tz="UTC")
        if as_of is None:
            as_of = pd.Timestamp(local_path.stat().st_mtime, unit="s", tz="UTC")
            timestamp_quality = "local_mtime_not_market_as_of"
            availability_basis = "inferred_from_collection"
            availability_confidence = "low"
    option_rows = normalize_option_rows(payload, frame) if not corrupted else []
    underlying_price = extract_underlying_price(payload, frame) if not corrupted else math.nan
    underlying_quote_ts = extract_first_timestamp(payload, frame, ["underlying_quote_timestamp_utc", "underlyingQuoteTimestamp", "regularMarketTime", "snapshot_date"]) if not corrupted else None
    option_quote_ts = extract_first_timestamp(payload, frame, ["option_quote_timestamp_utc", "quote_timestamp_utc", "quoteTime", "lastTradeDate"]) if not corrupted else None
    quality_metrics = option_quality_metrics(option_rows, underlying_price, as_of)
    raw_complete, gex_success, completeness_note = detect_raw_chain_quality(path, payload, frame) if not corrupted else (False, False, "corrupted")
    raw_complete = bool(raw_complete and quality_metrics["input_completeness_rate"] >= 0.60)
    gex_success = bool(gex_success and quality_metrics["calculation_success_rate"] > 0)
    gex_metrics = calculate_gex_proxy_metrics(option_rows, underlying_price, as_of) if gex_success else calculate_gex_proxy_metrics([], math.nan, None)
    raw_chain_quality = str(quality_metrics.get("economic_quality", "unavailable"))
    net_gex_proxy_quality = raw_chain_quality if gex_success and pd.notna(safe_float(gex_metrics.get("net_gex_proxy"))) else "unavailable"
    gamma_flip_proxy_quality = str(gex_metrics.get("gamma_flip_proxy_quality", "unavailable"))
    row_economic_quality = combine_row_economic_quality(raw_chain_quality, net_gex_proxy_quality, gamma_flip_proxy_quality)
    quality_metrics["economic_quality"] = row_economic_quality
    contract_examples = contract_validation_examples(option_rows, underlying_price, as_of)
    ticker = ticker_from_snapshot(path, payload, frame)
    usability = snapshot_usability(as_of, raw_complete, gex_success)
    decision_age = usability["snapshot_age_at_next_us_open_hours"]
    session_category = usability["us_session_phase"]
    collected_at = file_created.isoformat() if file_created is not None else ""
    effective_available_at = collected_at or (as_of.isoformat() if as_of is not None else "")
    notes = completeness_note
    if gex_metrics.get("gamma_flip_warning"):
        notes = ";".join([n for n in [notes, str(gex_metrics.get("gamma_flip_warning"))] if n])
    if gex_metrics.get("gamma_flip_failure_reason") and gex_metrics.get("gamma_flip_status") != "no_local_flip":
        notes = ";".join([n for n in [notes, str(gex_metrics.get("gamma_flip_failure_reason"))] if n])
    record = {
        "ticker": ticker,
        "path": path,
        "raw_payload_path": path,
        "raw_payload_hash": raw_payload_hash,
        "snapshot_format": Path(path).suffix.lower().lstrip(".") or "unknown",
        "option_chain_as_of_timestamp_utc": as_of.isoformat() if as_of is not None else "",
        "underlying_quote_timestamp_utc": underlying_quote_ts.isoformat() if underlying_quote_ts is not None else "",
        "option_quote_timestamp_utc": option_quote_ts.isoformat() if option_quote_ts is not None else "",
        "underlying_price": underlying_price if pd.notna(underlying_price) else "",
        "source_available_at_utc": as_of.isoformat() if as_of is not None and timestamp_quality.startswith("embedded") else "",
        "collected_at_utc": collected_at,
        "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "effective_available_at_utc": effective_available_at,
        "availability_basis": availability_basis,
        "availability_confidence": availability_confidence,
        "file_created_at_utc": file_created.isoformat() if file_created is not None else "",
        "git_commit_timestamp_utc": git_commit_ts.isoformat() if git_commit_ts is not None else "",
        "github_workflow_started_at_utc": "",
        "github_workflow_completed_at_utc": "",
        "us_session_phase": session_category,
        "session_category": session_category,
        "session_subtype": session_subtype(session_category),
        "jst_hour": as_of.tz_convert(JST).strftime("%H:00") if as_of is not None else "",
        "raw_chain_complete": bool(raw_complete),
        "gex_reconstruction_success": bool(gex_success),
        "raw_chain_timestamp_quality": timestamp_quality,
        "strict_entry_usable": bool(usability["strict_entry_usable"]),
        "prior_session_context_usable": bool(usability["prior_session_context_usable"]),
        "historical_reconstructed_usable": bool(usability["historical_reconstructed_usable"]),
        "snapshot_age_at_next_us_open_hours": usability["snapshot_age_at_next_us_open_hours"],
        "snapshot_age_at_decision_time_hours": decision_age,
        "corrupted_or_incomplete": bool(corrupted or not raw_complete),
        "raw_chain_quality": raw_chain_quality,
        "net_gex_proxy_quality": net_gex_proxy_quality,
        "gamma_flip_proxy_quality": gamma_flip_proxy_quality,
        "call_wall_proxy_quality": raw_chain_quality if gex_success and pd.notna(safe_float(gex_metrics.get("call_wall_proxy"))) else "unavailable",
        "put_wall_proxy_quality": raw_chain_quality if gex_success and pd.notna(safe_float(gex_metrics.get("put_wall_proxy"))) else "unavailable",
        "pinning_proxy_quality": raw_chain_quality if gex_success and pd.notna(safe_float(gex_metrics.get("pinning_score_proxy"))) else "unavailable",
        "expected_move_proxy_quality": raw_chain_quality if gex_success and pd.notna(safe_float(gex_metrics.get("expected_move_proxy"))) else "unavailable",
        "row_economic_quality": row_economic_quality,
        "contract_examples_json": json.dumps(contract_examples, ensure_ascii=False),
        "notes": notes,
    }
    record.update(quality_metrics)
    record.update(gex_metrics)
    for diag in record.get("_root_diagnostics_rows", []) or []:
        diag.update(
            {
                "ticker": ticker,
                "market_snapshot_id": "dealer_gex_" + hashlib.sha256(f"{ticker}_{record.get('option_chain_as_of_timestamp_utc','')}_{raw_payload_hash[:12]}".encode("utf-8")).hexdigest()[:16],
                "as_of_timestamp_utc": record.get("option_chain_as_of_timestamp_utc", ""),
                "calculation_version": CALCULATION_VERSION,
                "metric_definition_version": "dealer_gamma_quality_rules_v2",
                "raw_payload_hash": raw_payload_hash,
            }
        )
    return record


def collect_option_snapshot_records(root: Path) -> tuple[list[dict[str, Any]], str, float]:
    cache_key = f"{root.resolve()}|{os.environ.get('GITHUB_ACTIONS', '')}|{os.environ.get('GITHUB_SHA', '')}"
    if cache_key in _OPTION_SNAPSHOT_RECORD_CACHE:
        return _OPTION_SNAPSHOT_RECORD_CACHE[cache_key]
    repo = resolve_github_repository(root)
    records: list[dict[str, Any]] = []
    success_rate = np.nan
    base = root / "option_chain_snapshots"
    if os.environ.get("GITHUB_ACTIONS") == "true" and base.exists():
        workflow_started = os.environ.get("GITHUB_WORKFLOW_STARTED_AT", "")
        workflow_completed = ""
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in {".json", ".csv", ".parquet"}:
                continue
            rec = parse_snapshot_file(str(p.relative_to(root)).replace("\\", "/"), None, p)
            rec["source_basis"] = "github_main_checkout"
            rec["github_repository"] = repo
            rec["workflow_execution_success_rate"] = success_rate
            rec["github_workflow_started_at_utc"] = workflow_started
            rec["github_workflow_completed_at_utc"] = workflow_completed
            records.append(rec)
        result = (records, "github_main_checkout", success_rate)
        _OPTION_SNAPSHOT_RECORD_CACHE[cache_key] = result
        return result
    tree = github_main_tree(repo)
    if tree:
        runs = github_workflow_runs(repo, ".github/workflows/option_snapshot.yml")
        success_rate = runs.get("workflow_execution_success_rate", np.nan)
        workflow_started = runs.get("started_at", "")
        workflow_completed = runs.get("completed_at", "")
        for path in tree_files_under(tree, "option_chain_snapshots"):
            if Path(path).suffix.lower() not in {".json", ".csv", ".parquet"}:
                continue
            raw = None
            if Path(path).suffix.lower() in {".json", ".csv"}:
                raw_url = f"https://raw.githubusercontent.com/{repo}/main/{urllib.parse.quote(path)}"
                raw = github_api_bytes(raw_url)
            rec = parse_snapshot_file(path, raw)
            commit_ts = github_latest_file_commit_timestamp(repo, path)
            rec["git_commit_timestamp_utc"] = commit_ts
            if not rec.get("file_created_at_utc"):
                rec["file_created_at_utc"] = commit_ts
            if not rec.get("collected_at_utc"):
                rec["collected_at_utc"] = commit_ts
            if not rec.get("effective_available_at_utc"):
                rec["effective_available_at_utc"] = commit_ts or rec.get("option_chain_as_of_timestamp_utc", "")
            rec["github_workflow_started_at_utc"] = workflow_started
            rec["github_workflow_completed_at_utc"] = workflow_completed
            rec["source_basis"] = "github_main_api"
            rec["github_repository"] = repo
            rec["workflow_execution_success_rate"] = success_rate
            records.append(rec)
        result = (records, "github_main_api", success_rate)
        _OPTION_SNAPSHOT_RECORD_CACHE[cache_key] = result
        return result
    if base.exists():
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".json", ".csv", ".parquet"}:
                rec = parse_snapshot_file(str(p.relative_to(root)).replace("\\", "/"), None, p)
                rec["source_basis"] = "local_fallback_repo_unresolved_or_api_unavailable"
                rec["github_repository"] = repo
                rec["workflow_execution_success_rate"] = np.nan
                records.append(rec)
    result = (records, "local_fallback_repo_unresolved_or_api_unavailable", success_rate)
    _OPTION_SNAPSHOT_RECORD_CACHE[cache_key] = result
    return result


def dealer_gamma_coverage_audit(root: Path) -> pd.DataFrame:
    records, source_basis, workflow_success = collect_option_snapshot_records(root)
    details_path = root / "dealer_gamma_history" / "dealer_gamma_snapshot_file_audit.csv"
    details_path.parent.mkdir(parents=True, exist_ok=True)
    root_diag_rows = []
    for rec in records:
        root_diag_rows.extend(rec.get("_root_diagnostics_rows", []) or [])
    root_diag_columns = [
        "ticker", "market_snapshot_id", "as_of_timestamp_utc", "spot",
        "gamma_flip_search_low", "gamma_flip_search_high", "gamma_flip_grid_size",
        "grid_price", "aggregate_gamma_proxy_at_grid", "grid_sign",
        "sign_change_segment_count", "root_candidate_count", "root_candidate_values_json",
        "selected_root", "selected_root_distance_pct", "selected_root_validation_passed",
        "boundary_root_warning", "gamma_flip_status", "gamma_flip_selection_reason",
        "gamma_flip_failure_reason", "calculation_version", "metric_definition_version",
        "raw_payload_hash",
    ]
    write_table(
        pd.DataFrame(root_diag_rows, columns=root_diag_columns),
        details_path.parent / "dealer_gamma_root_diagnostics.csv",
        details_path.parent / "dealer_gamma_root_diagnostics.parquet",
    )
    detail_columns = [
        "ticker", "raw_payload_path", "raw_payload_hash", "path", "source_basis", "github_repository", "option_chain_as_of_timestamp_utc",
        "underlying_quote_timestamp_utc", "option_quote_timestamp_utc", "underlying_price",
        "source_available_at_utc", "collected_at_utc", "retrieved_at_utc", "effective_available_at_utc",
        "availability_basis", "availability_confidence", "snapshot_format",
        "file_created_at_utc", "git_commit_timestamp_utc", "github_workflow_started_at_utc",
        "github_workflow_completed_at_utc", "us_session_phase", "session_category", "session_subtype", "jst_hour", "raw_chain_complete",
        "gex_reconstruction_success", "raw_chain_timestamp_quality", "strict_entry_usable",
        "prior_session_context_usable", "historical_reconstructed_usable",
        "snapshot_age_at_next_us_open_hours", "snapshot_age_at_decision_time_hours",
        "input_completeness_rate", "calculation_success_rate", "economic_quality",
        "raw_chain_quality", "net_gex_proxy_quality", "gamma_flip_proxy_quality",
        "call_wall_proxy_quality", "put_wall_proxy_quality", "pinning_proxy_quality",
        "expected_move_proxy_quality", "row_economic_quality",
        "option_contract_count", "valid_contract_count", "invalid_or_negative_oi_count",
        "invalid_iv_count", "missing_expiry_bucket_count", "missing_call_put_side_count",
        "missing_underlying_price_count", "stale_quote_count",
        "call_gamma_open_interest_proxy", "put_gamma_open_interest_proxy", "net_gamma_open_interest_proxy",
        "dealer_gamma_proxy_assumption", "dealer_gamma_proxy", "sign_convention",
        "net_gex_proxy", "gamma_flip_proxy", "spot_vs_gamma_flip_pct", "dealer_gamma_state",
        "gamma_flip_search_low", "gamma_flip_search_high", "gamma_flip_search_range_pct",
        "gamma_flip_grid_size", "gamma_flip_root_count", "gamma_flip_selected_root",
        "gamma_flip_selection_reason", "gamma_flip_distance_pct", "gamma_flip_status",
        "gamma_flip_warning", "gamma_flip_failure_reason", "boundary_root_warning",
        "call_wall_proxy", "put_wall_proxy", "pinning_score_proxy", "zero_dte_share_proxy",
        "dealer_pressure_proxy", "expected_move_proxy",
        "workflow_execution_success_rate", "corrupted_or_incomplete", "contract_examples_json", "notes",
    ]
    pd.DataFrame(records, columns=detail_columns).to_csv(details_path, index=False)
    rows = []
    for ticker in TICKERS_FOR_GEX_AUDIT:
        ticker_records = [r for r in records if r.get("ticker") == ticker or ticker.lower() in str(r.get("path", "")).lower()]
        as_of = [parse_timestamp(r.get("option_chain_as_of_timestamp_utc")) for r in ticker_records]
        as_of = [t for t in as_of if t is not None]
        session_counts = {phase: 0 for phase in SESSION_PHASES}
        for r in ticker_records:
            session_counts[r.get("us_session_phase") if r.get("us_session_phase") in session_counts else "unknown"] += 1
        subtype_counts: dict[str, int] = {}
        for r in ticker_records:
            subtype = str(r.get("session_subtype") or "unknown")
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
        jst_counts: dict[str, int] = {}
        for r in ticker_records:
            hour = r.get("jst_hour", "")
            if hour:
                jst_counts[hour] = jst_counts.get(hour, 0) + 1
        session_dates = sorted({t.tz_convert(ET).date() for t in as_of})
        missing_sessions = 0
        if session_dates:
            expected = pd.bdate_range(min(session_dates), max(session_dates)).date
            missing_sessions = max(0, len(set(expected) - set(session_dates)))
        duplicate_count = 0
        if ticker_records:
            keys = [f"{r.get('option_chain_as_of_timestamp_utc')}|{r.get('raw_chain_timestamp_quality')}" for r in ticker_records]
            duplicate_count = len(keys) - len(set(keys))
        complete_count = sum(bool(r.get("raw_chain_complete")) for r in ticker_records)
        gex_count = sum(bool(r.get("gex_reconstruction_success")) for r in ticker_records)
        input_rates = [safe_float(r.get("input_completeness_rate")) for r in ticker_records]
        calc_rates = [safe_float(r.get("calculation_success_rate")) for r in ticker_records]
        economic_counts: dict[str, int] = {}
        for r in ticker_records:
            eq = str(r.get("economic_quality") or "unavailable")
            economic_counts[eq] = economic_counts.get(eq, 0) + 1
        rows.append(
            {
                "ticker": ticker,
                "source_basis": source_basis,
                "snapshot_count": len(ticker_records),
                "oldest_option_chain_as_of_timestamp_utc": min(as_of).isoformat() if as_of else "",
                "newest_option_chain_as_of_timestamp_utc": max(as_of).isoformat() if as_of else "",
                "oldest_file_created_at_utc": min([r["file_created_at_utc"] for r in ticker_records if r.get("file_created_at_utc")] or [""]),
                "newest_file_created_at_utc": max([r["file_created_at_utc"] for r in ticker_records if r.get("file_created_at_utc")] or [""]),
                "oldest_git_commit_timestamp_utc": min([r["git_commit_timestamp_utc"] for r in ticker_records if r.get("git_commit_timestamp_utc")] or [""]),
                "newest_git_commit_timestamp_utc": max([r["git_commit_timestamp_utc"] for r in ticker_records if r.get("git_commit_timestamp_utc")] or [""]),
                "github_workflow_started_at_utc": max([r["github_workflow_started_at_utc"] for r in ticker_records if r.get("github_workflow_started_at_utc")] or [""]),
                "github_workflow_completed_at_utc": max([r["github_workflow_completed_at_utc"] for r in ticker_records if r.get("github_workflow_completed_at_utc")] or [""]),
                "us_session_counts_json": json.dumps(session_counts, ensure_ascii=False),
                "session_subtype_counts_json": json.dumps(dict(sorted(subtype_counts.items())), ensure_ascii=False),
                "prior_session_eod_count": session_counts["prior_session_eod"],
                "same_session_pre_open_count": session_counts["same_session_pre_open"],
                "intraday_count": session_counts["intraday"],
                "after_close_count": session_counts["after_close"],
                "unknown_count": session_counts["unknown"],
                "jst_time_distribution_json": json.dumps(dict(sorted(jst_counts.items())), ensure_ascii=False),
                "raw_option_chain_complete_rate": round(complete_count / len(ticker_records), 4) if ticker_records else 0,
                "gex_reconstruction_success_rate": round(gex_count / len(ticker_records), 4) if ticker_records else 0,
                "input_completeness_rate": round(float(np.nanmean(input_rates)), 4) if ticker_records else 0,
                "calculation_success_rate": round(float(np.nanmean(calc_rates)), 4) if ticker_records else 0,
                "economic_quality_distribution_json": json.dumps(dict(sorted(economic_counts.items())), ensure_ascii=False),
                "invalid_or_negative_oi_count": int(np.nansum([safe_float(r.get("invalid_or_negative_oi_count"), 0) for r in ticker_records])) if ticker_records else 0,
                "invalid_iv_count": int(np.nansum([safe_float(r.get("invalid_iv_count"), 0) for r in ticker_records])) if ticker_records else 0,
                "missing_expiry_bucket_count": int(np.nansum([safe_float(r.get("missing_expiry_bucket_count"), 0) for r in ticker_records])) if ticker_records else 0,
                "missing_call_put_side_count": int(np.nansum([safe_float(r.get("missing_call_put_side_count"), 0) for r in ticker_records])) if ticker_records else 0,
                "missing_underlying_price_count": int(np.nansum([safe_float(r.get("missing_underlying_price_count"), 0) for r in ticker_records])) if ticker_records else 0,
                "stale_quote_count": int(np.nansum([safe_float(r.get("stale_quote_count"), 0) for r in ticker_records])) if ticker_records else 0,
                "strict_entry_usable_count": sum(bool(r.get("strict_entry_usable")) for r in ticker_records),
                "prior_session_context_usable_count": sum(bool(r.get("prior_session_context_usable")) for r in ticker_records),
                "historical_reconstructed_usable_count": sum(bool(r.get("historical_reconstructed_usable")) for r in ticker_records),
                "median_snapshot_age_at_next_us_open_hours": round(float(np.nanmedian([safe_float(r.get("snapshot_age_at_next_us_open_hours")) for r in ticker_records])), 2) if ticker_records else np.nan,
                "median_snapshot_age_at_decision_time_hours": round(float(np.nanmedian([safe_float(r.get("snapshot_age_at_decision_time_hours")) for r in ticker_records])), 2) if ticker_records else np.nan,
                "raw_chain_timestamp_quality": "; ".join(sorted({str(r.get("raw_chain_timestamp_quality")) for r in ticker_records if r.get("raw_chain_timestamp_quality")})),
                "workflow_execution_success_rate": workflow_success,
                "missing_trading_session_count": missing_sessions,
                "duplicate_snapshot_count": duplicate_count,
                "corrupted_or_incomplete_snapshot_count": sum(bool(r.get("corrupted_or_incomplete")) for r in ticker_records),
                "notes": "" if ticker_records else "no option_chain_snapshots files found on GitHub main or local fallback",
            }
        )
    return pd.DataFrame(rows)


def dealer_gamma_backfill(root: Path) -> pd.DataFrame:
    columns = [
        "ticker", "market_snapshot_id", "as_of_timestamp_utc", "effective_available_at_utc", "collected_at_utc",
        "session_category", "session_subtype",
        "strict_entry_usable", "prior_session_context_usable", "historical_reconstructed_usable",
        "snapshot_age_at_decision_time_hours", "availability_basis", "availability_confidence",
        "call_gamma_open_interest_proxy", "put_gamma_open_interest_proxy", "net_gamma_open_interest_proxy",
        "dealer_gamma_proxy_assumption", "dealer_gamma_proxy", "sign_convention",
        "gamma_flip_proxy", "spot_vs_gamma_flip_pct", "dealer_gamma_state", "call_wall_proxy", "put_wall_proxy",
        "gamma_flip_search_low", "gamma_flip_search_high", "gamma_flip_search_range_pct",
        "gamma_flip_grid_size", "gamma_flip_root_count", "gamma_flip_selected_root",
        "gamma_flip_selection_reason", "gamma_flip_distance_pct", "gamma_flip_status",
        "gamma_flip_warning", "gamma_flip_failure_reason", "gamma_flip_proxy_quality",
        "pinning_score_proxy", "zero_dte_share_proxy", "dealer_pressure_proxy", "expected_move_proxy",
        "data_type", "raw_input_type", "metric_derivation", "is_proxy",
        "dealer_position_observed",
        "raw_payload_path", "raw_payload_hash", "git_commit_sha", "calculation_version", "metric_definition_version",
        "quality_flag", "economic_quality", "raw_chain_quality", "net_gex_proxy_quality",
        "call_wall_proxy_quality", "put_wall_proxy_quality", "pinning_proxy_quality",
        "expected_move_proxy_quality", "row_economic_quality",
    ]
    records, _, _ = collect_option_snapshot_records(root)
    rows = []
    quality_map = {"high": "high", "medium": "medium", "low": "low", "unusable": "unavailable"}
    for rec in records:
        if not rec.get("gex_reconstruction_success") or rec.get("economic_quality") == "unusable":
            continue
        as_of = rec.get("option_chain_as_of_timestamp_utc", "")
        collected = rec.get("collected_at_utc") or rec.get("file_created_at_utc") or rec.get("git_commit_timestamp_utc") or as_of
        effective = rec.get("effective_available_at_utc") or collected or as_of
        key = f"{rec.get('ticker','')}_{as_of}_{rec.get('raw_payload_hash','')[:12]}"
        rows.append(
            {
                "ticker": rec.get("ticker", ""),
                "market_snapshot_id": "dealer_gex_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
                "as_of_timestamp_utc": as_of,
                "effective_available_at_utc": effective,
                "collected_at_utc": collected,
                "session_category": rec.get("session_category", ""),
                "session_subtype": rec.get("session_subtype", ""),
                "strict_entry_usable": rec.get("strict_entry_usable"),
                "prior_session_context_usable": rec.get("prior_session_context_usable"),
                "historical_reconstructed_usable": rec.get("historical_reconstructed_usable"),
                "snapshot_age_at_decision_time_hours": rec.get("snapshot_age_at_decision_time_hours"),
                "availability_basis": rec.get("availability_basis", ""),
                "availability_confidence": rec.get("availability_confidence", ""),
                "call_gamma_open_interest_proxy": rec.get("call_gamma_open_interest_proxy"),
                "put_gamma_open_interest_proxy": rec.get("put_gamma_open_interest_proxy"),
                "net_gamma_open_interest_proxy": rec.get("net_gamma_open_interest_proxy"),
                "dealer_gamma_proxy_assumption": rec.get("dealer_gamma_proxy_assumption", DEALER_GAMMA_PROXY_ASSUMPTION),
                "dealer_gamma_proxy": rec.get("dealer_gamma_proxy"),
                "sign_convention": rec.get("sign_convention", DEALER_GAMMA_SIGN_CONVENTION),
                "gamma_flip_proxy": rec.get("gamma_flip_proxy"),
                "spot_vs_gamma_flip_pct": rec.get("spot_vs_gamma_flip_pct"),
                "dealer_gamma_state": rec.get("dealer_gamma_state"),
                "call_wall_proxy": rec.get("call_wall_proxy"),
                "put_wall_proxy": rec.get("put_wall_proxy"),
                "gamma_flip_search_low": rec.get("gamma_flip_search_low"),
                "gamma_flip_search_high": rec.get("gamma_flip_search_high"),
                "gamma_flip_search_range_pct": rec.get("gamma_flip_search_range_pct"),
                "gamma_flip_grid_size": rec.get("gamma_flip_grid_size"),
                "gamma_flip_root_count": rec.get("gamma_flip_root_count"),
                "gamma_flip_selected_root": rec.get("gamma_flip_selected_root"),
                "gamma_flip_selection_reason": rec.get("gamma_flip_selection_reason"),
                "gamma_flip_distance_pct": rec.get("gamma_flip_distance_pct"),
                "gamma_flip_status": rec.get("gamma_flip_status"),
                "gamma_flip_warning": rec.get("gamma_flip_warning"),
                "gamma_flip_failure_reason": rec.get("gamma_flip_failure_reason"),
                "gamma_flip_proxy_quality": rec.get("gamma_flip_proxy_quality"),
                "pinning_score_proxy": rec.get("pinning_score_proxy"),
                "zero_dte_share_proxy": rec.get("zero_dte_share_proxy"),
                "dealer_pressure_proxy": rec.get("dealer_pressure_proxy"),
                "expected_move_proxy": rec.get("expected_move_proxy"),
                "data_type": "reconstructed",
                "raw_input_type": "raw_option_chain_snapshot",
                "metric_derivation": GEX_METRIC_DERIVATION,
                "is_proxy": True,
                "dealer_position_observed": False,
                "raw_payload_path": rec.get("raw_payload_path", rec.get("path", "")),
                "raw_payload_hash": rec.get("raw_payload_hash", ""),
                "git_commit_sha": p2b.git_commit_sha(),
                "calculation_version": CALCULATION_VERSION,
                "metric_definition_version": "dealer_gamma_proxy_history_v0",
                "quality_flag": quality_map.get(str(rec.get("economic_quality")), "partial"),
                "economic_quality": rec.get("economic_quality", "unavailable"),
                "raw_chain_quality": rec.get("raw_chain_quality", "unavailable"),
                "net_gex_proxy_quality": rec.get("net_gex_proxy_quality", "unavailable"),
                "call_wall_proxy_quality": rec.get("call_wall_proxy_quality", "unavailable"),
                "put_wall_proxy_quality": rec.get("put_wall_proxy_quality", "unavailable"),
                "pinning_proxy_quality": rec.get("pinning_proxy_quality", "unavailable"),
                "expected_move_proxy_quality": rec.get("expected_move_proxy_quality", "unavailable"),
                "row_economic_quality": rec.get("row_economic_quality", rec.get("economic_quality", "unavailable")),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def market_score_snapshot(root: Path) -> pd.DataFrame:
    latest = latest_file(root / "market_bomb_snapshots", "**/market_bomb_snapshot_*.csv")
    snapshot = pd.read_csv(latest) if latest else pd.DataFrame()
    event_calendar = pd.read_csv(root / "market_event_calendar/event_calendar.csv") if (root / "market_event_calendar/event_calendar.csv").exists() else pd.DataFrame()
    score = calculate_market_environment_score(snapshot, pd.Timestamp.now(tz="UTC"), event_calendar)
    score["input_snapshot_hash"] = hash_file(latest)
    score["raw_payload_path"] = str(latest or "")
    score["raw_payload_hash"] = hash_file(latest)
    return pd.DataFrame([score])


def append_history(new_rows: pd.DataFrame, csv_path: Path, parquet_path: Path) -> None:
    if csv_path.exists():
        existing = pd.read_csv(csv_path)
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        combined = new_rows
    combined = combined.drop_duplicates(subset=[c for c in ["market_snapshot_id", "score_timestamp_utc"] if c in combined], keep="last")
    write_table(combined, csv_path, parquet_path)


def enrich_contexts(root: Path, score_df: pd.DataFrame, execution_df: pd.DataFrame) -> None:
    score_cols = [
        "market_environment_score_v0", "market_environment_score_observed_v0", "market_environment_score_proxy_augmented_v0",
        "market_score_coverage_pct", "market_score_confidence", "market_score_data_mode", "market_score_version",
        "market_score_components_json", "market_score_unavailable_components",
    ]
    for rel in ["morita_signal_market_context/signal_market_context.csv", "morita_entry_market_context/entry_market_context.csv"]:
        path = root / rel
        if not path.exists():
            continue
        ctx = pd.read_csv(path)
        if ctx.empty or score_df.empty or "market_snapshot_id" not in ctx:
            for col in score_cols:
                if col not in ctx:
                    ctx[col] = None
        else:
            ctx = ctx.copy()
            score_join = score_df[["market_snapshot_id"] + score_cols].copy()
            ctx["market_snapshot_id"] = ctx["market_snapshot_id"].fillna("").astype(str)
            score_join["market_snapshot_id"] = score_join["market_snapshot_id"].fillna("").astype(str)
            ctx = ctx.drop(columns=[c for c in score_cols if c in ctx], errors="ignore").merge(score_join, on="market_snapshot_id", how="left")
        write_table(ctx, path, path.with_suffix(".parquet"))
    panel_path = root / "morita_analysis_ready/signal_market_option_panel.csv"
    if panel_path.exists():
        panel = pd.read_csv(panel_path)
        if not score_df.empty:
            score = score_df.iloc[-1]
            panel["signal_market_environment_score_v0"] = score.get("market_environment_score_v0")
            panel["entry_market_environment_score_v0"] = score.get("market_environment_score_v0")
            panel["market_score_coverage_pct"] = score.get("market_score_coverage_pct")
        if not execution_df.empty:
            panel["entry_execution_score_v0"] = None
            panel["execution_score_coverage_pct"] = None
        write_table(panel, panel_path, panel_path.with_suffix(".parquet"))


def write_score_reports(root: Path, score_df: pd.DataFrame) -> dict[str, Path]:
    out = root / "market_environment_analysis"
    out.mkdir(parents=True, exist_ok=True)
    token = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d")
    bucket_report = out / f"market_score_bucket_report_{token}.md"
    html_report = out / f"market_score_bucket_report_{token}.html"
    comp_report = out / f"market_score_component_report_{token}.csv"
    suff_report = out / f"market_score_data_sufficiency_{token}.md"
    row = score_df.iloc[-1].to_dict() if not score_df.empty else {}
    components = json.loads(row.get("market_score_components_json", "[]")) if row else []
    pd.DataFrame(components).to_csv(comp_report, index=False)
    bucket = score_bucket(row.get("market_environment_score_v0"))
    md = [
        "# Market Environment Score v0 Bucket Report",
        "",
        f"Score: {row.get('market_environment_score_v0', 'unavailable')}",
        f"Bucket: {bucket}",
        f"Coverage: {row.get('market_score_coverage_pct', '')}%",
        f"Confidence: {row.get('market_score_confidence', '')}",
        "",
        "Score is display/storage only. It does not change notification, rank, sizing, or execution.",
        "",
    ]
    bucket_report.write_text("\n".join(md), encoding="utf-8")
    html_report.write_text(f"<!doctype html><meta charset='utf-8'><h1>Market Environment Score v0</h1><p>Score: {row.get('market_environment_score_v0', 'unavailable')}</p><p>Bucket: {bucket}</p>", encoding="utf-8")
    suff_report.write_text(
        f"""# Market Score Data Sufficiency

Coverage: {row.get('market_score_coverage_pct', '')}%
Confidence: {row.get('market_score_confidence', '')}
Unavailable components: {row.get('market_score_unavailable_components', '')}

Rules:
- coverage < 60%: standard Market Environment Score is unavailable.
- proxy confidence is capped at medium.
- score buckets are not hard filters.
""",
        encoding="utf-8",
    )
    return {"bucket_report": bucket_report, "html_report": html_report, "component_report": comp_report, "sufficiency": suff_report}


def score_bucket(value: Any) -> str:
    val = safe_float(value)
    if pd.isna(val):
        return "unavailable"
    if val < 40:
        return "0-39"
    if val < 60:
        return "40-59"
    if val < 80:
        return "60-79"
    return "80-100"


def write_dealer_gamma_quality_rules(root: Path) -> Path:
    path = root / "dealer_gamma_history" / "dealer_gamma_quality_rules_v2.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEALER_GAMMA_QUALITY_RULES, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_manual_validation_report(root: Path) -> Path:
    hist = root / "dealer_gamma_history"
    detail_path = hist / "dealer_gamma_snapshot_file_audit.csv"
    token = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d")
    report_path = hist / f"dealer_gamma_manual_validation_QQQ_{token}.md"
    if not detail_path.exists():
        report_path.write_text("# Dealer Gamma Manual Validation - QQQ\n\nNo snapshot file audit exists.\n", encoding="utf-8")
        return report_path
    details = pd.read_csv(detail_path)
    qqq = details[details.get("ticker", pd.Series(dtype=str)).astype(str).eq("QQQ")]
    if qqq.empty:
        report_path.write_text(
            "# Dealer Gamma Manual Validation - QQQ\n\n"
            "No QQQ raw option-chain snapshot was available in `option_chain_snapshots` for manual validation.\n\n"
            "Phase 3.1 completion gate remains blocked until GitHub Actions can inspect at least one QQQ raw snapshot on main.\n",
            encoding="utf-8",
        )
        return report_path
    row = qqq.iloc[0].to_dict()
    examples = []
    try:
        examples = json.loads(row.get("contract_examples_json", "[]") or "[]")
    except Exception:
        examples = []
    md = [
        "# Dealer Gamma Manual Validation - QQQ",
        "",
        f"Raw file path: `{row.get('raw_payload_path', '')}`",
        f"Raw hash: `{row.get('raw_payload_hash', '')}`",
        f"As-of timestamp: `{row.get('option_chain_as_of_timestamp_utc', '')}`",
        f"Underlying price: `{row.get('underlying_price', '')}`",
        f"Underlying quote timestamp: `{row.get('underlying_quote_timestamp_utc', '')}`",
        f"Option quote timestamp: `{row.get('option_quote_timestamp_utc', '')}`",
        "",
        "## Contract / Quality",
        "",
        f"Option contract count: `{row.get('option_contract_count', '')}`",
        f"Valid contract count: `{row.get('valid_contract_count', '')}`",
        f"OI invalid/missing count: `{row.get('invalid_or_negative_oi_count', '')}`",
        f"IV invalid/missing count: `{row.get('invalid_iv_count', '')}`",
        f"Missing expiry count: `{row.get('missing_expiry_bucket_count', '')}`",
        f"Missing call/put side count: `{row.get('missing_call_put_side_count', '')}`",
        f"Contract multiplier: assumed per contract row; fallback `100` when unavailable.",
        "",
        "## GEX Proxy",
        "",
        f"call_gamma_open_interest_proxy: `{row.get('call_gamma_open_interest_proxy', '')}`",
        f"put_gamma_open_interest_proxy: `{row.get('put_gamma_open_interest_proxy', '')}`",
        f"net_gamma_open_interest_proxy: `{row.get('net_gamma_open_interest_proxy', '')}`",
        f"dealer_gamma_proxy_assumption: `{row.get('dealer_gamma_proxy_assumption', '')}`",
        f"dealer_gamma_proxy: `{row.get('dealer_gamma_proxy', '')}`",
        f"sign_convention: `{row.get('sign_convention', '')}`",
        f"gamma_flip_proxy: `{row.get('gamma_flip_proxy', '')}`",
        f"gamma_flip_status: `{row.get('gamma_flip_status', '')}`",
        f"gamma_flip_search_range: `{row.get('gamma_flip_search_low', '')}` to `{row.get('gamma_flip_search_high', '')}`",
        f"gamma_flip_root_count: `{row.get('gamma_flip_root_count', '')}`",
        f"gamma_flip_selection_reason: `{row.get('gamma_flip_selection_reason', '')}`",
        f"gamma_flip_proxy_quality: `{row.get('gamma_flip_proxy_quality', '')}`",
        f"call_wall_proxy: `{row.get('call_wall_proxy', '')}`",
        f"put_wall_proxy: `{row.get('put_wall_proxy', '')}`",
        "",
        "## Quality Decision",
        "",
        f"input_completeness_rate: `{row.get('input_completeness_rate', '')}`",
        f"calculation_success_rate: `{row.get('calculation_success_rate', '')}`",
        f"raw_chain_quality: `{row.get('raw_chain_quality', '')}`",
        f"net_gex_proxy_quality: `{row.get('net_gex_proxy_quality', '')}`",
        f"gamma_flip_proxy_quality: `{row.get('gamma_flip_proxy_quality', '')}`",
        f"row_economic_quality: `{row.get('row_economic_quality', '')}`",
        f"economic_quality: `{row.get('economic_quality', '')}`",
        "",
    ]
    if examples:
        example_df = pd.DataFrame(examples)
        md.extend(
            [
                "## Contract-Level Gamma Examples",
                "",
                markdown_table(example_df),
                "",
            ]
        )
    else:
        md.extend(
            [
                "## Contract-Level Gamma Examples",
                "",
                "No contract-level examples were available from the retained raw rows.",
                "",
            ]
        )
    report_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return report_path


def write_phase3_completion_gate_audit(root: Path, deployment: pd.DataFrame, coverage: pd.DataFrame, backfill: pd.DataFrame) -> Path:
    path = root / "phase3_1_completion_gate_audit.md"
    source_basis_ok = bool(not deployment.empty and deployment.get("source_basis", pd.Series(dtype=str)).astype(str).eq("github_main_api").any())
    main_checked_ok = bool(not deployment.empty and deployment.get("main_branch_checked", pd.Series(dtype=bool)).astype(str).str.lower().eq("true").any())
    snapshot_count = int(coverage["snapshot_count"].sum()) if not coverage.empty and "snapshot_count" in coverage else 0
    tickers_present = sorted(coverage["ticker"].astype(str).tolist()) if not coverage.empty and "ticker" in coverage else []
    backfill_rows = len(backfill)
    medium_or_better = int(backfill["economic_quality"].isin(["high", "medium"]).sum()) if not backfill.empty and "economic_quality" in backfill else 0
    qqq_reports = sorted((root / "dealer_gamma_history").glob("dealer_gamma_manual_validation_QQQ_*.md"))
    root_diag_path = root / "dealer_gamma_history" / "dealer_gamma_root_diagnostics.csv"
    root_diag_exists = root_diag_path.exists() and root_diag_path.stat().st_size > 0
    qqq_manual_has_contract_examples = False
    if qqq_reports:
        try:
            qqq_manual_has_contract_examples = "Contract-Level Gamma Examples" in qqq_reports[-1].read_text(encoding="utf-8")
        except Exception:
            qqq_manual_has_contract_examples = False
    far_root_count = int(backfill["gamma_flip_status"].astype(str).eq("far_root_rejected").sum()) if not backfill.empty and "gamma_flip_status" in backfill else 0
    usable_or_normal_flip_count = int(backfill["gamma_flip_status"].astype(str).isin(["local_flip_found", "no_local_flip"]).sum()) if not backfill.empty and "gamma_flip_status" in backfill else 0
    deployment_gate = source_basis_ok and main_checked_ok
    raw_data_coverage_gate = snapshot_count > 0 and set(TICKERS_FOR_GEX_AUDIT).issubset(set(tickers_present))
    backfill_generation_gate = backfill_rows > 0
    dealer_feature_quality_gate = all([
        medium_or_better > 0,
        root_diag_exists,
        qqq_manual_has_contract_examples,
        usable_or_normal_flip_count > 0,
        far_root_count == 0,
    ])
    completed = all([deployment_gate, raw_data_coverage_gate, backfill_generation_gate, dealer_feature_quality_gate])
    verdict = "complete" if completed else "blocked"
    reasons = []
    if not deployment_gate:
        reasons.append("deployment_gate blocked")
    if not raw_data_coverage_gate:
        reasons.append("raw_data_coverage_gate blocked")
    if not backfill_generation_gate:
        reasons.append("backfill_generation_gate blocked")
    if not dealer_feature_quality_gate:
        reasons.append("dealer_feature_quality_gate blocked")
    if not source_basis_ok:
        reasons.append("source_basis is not github_main_api")
    if not main_checked_ok:
        reasons.append("main_branch_checked is not true")
    if snapshot_count <= 0:
        reasons.append("option_chain_snapshots count is 0")
    if not set(TICKERS_FOR_GEX_AUDIT).issubset(set(tickers_present)):
        reasons.append("not all target tickers have coverage rows")
    if backfill_rows <= 0:
        reasons.append("dealer_gamma_proxy_history has no reconstructed rows")
    if not qqq_reports:
        reasons.append("QQQ manual validation report is missing")
    if medium_or_better <= 0:
        reasons.append("no medium-or-better economic quality rows were produced")
    if not root_diag_exists:
        reasons.append("dealer_gamma_root_diagnostics.csv is missing or empty")
    if not qqq_manual_has_contract_examples:
        reasons.append("QQQ manual validation lacks contract-level gamma examples")
    if far_root_count > 0:
        reasons.append("far_root_rejected rows remain in dealer_gamma_proxy_history")
    if usable_or_normal_flip_count <= 0:
        reasons.append("no usable local flip or normal no_local_flip rows were produced")
    path.write_text(
        "# Phase 3.1 Completion Gate Audit\n\n"
        f"Verdict: `{verdict}`\n\n"
        f"deployment_gate: `{'passed' if deployment_gate else 'blocked'}`\n\n"
        f"raw_data_coverage_gate: `{'passed' if raw_data_coverage_gate else 'blocked'}`\n\n"
        f"backfill_generation_gate: `{'passed' if backfill_generation_gate else 'blocked'}`\n\n"
        f"dealer_feature_quality_gate: `{'passed' if dealer_feature_quality_gate else 'blocked'}`\n\n"
        f"phase3_1_overall_gate: `{'passed' if completed else 'blocked'}`\n\n"
        f"source_basis_github_main_api: `{source_basis_ok}`\n\n"
        f"main_branch_checked_true: `{main_checked_ok}`\n\n"
        f"option_chain_snapshot_count: `{snapshot_count}`\n\n"
        f"target_tickers: `{', '.join(tickers_present)}`\n\n"
        f"dealer_gamma_backfill_rows: `{backfill_rows}`\n\n"
        f"medium_or_better_rows: `{medium_or_better}`\n\n"
        f"far_root_rejected_rows: `{far_root_count}`\n\n"
        f"usable_or_normal_flip_rows: `{usable_or_normal_flip_count}`\n\n"
        f"root_diagnostics_file: `{root_diag_path.name if root_diag_exists else ''}`\n\n"
        f"qqq_manual_validation_report: `{qqq_reports[-1].name if qqq_reports else ''}`\n\n"
        "Blocking reasons:\n\n"
        + ("\n".join(f"- {r}" for r in reasons) if reasons else "- none")
        + "\n\nDealer Gamma is reconstructed proxy data only and is not observed dealer inventory.\n",
        encoding="utf-8",
    )
    return path


def write_audit_reports(root: Path, deployment: pd.DataFrame, coverage: pd.DataFrame, backfill: pd.DataFrame) -> None:
    deployment.to_csv(root / "market_environment_score_deployment_audit.csv", index=False)
    (root / "market_environment_score_deployment_audit.md").write_text("# Market Environment Score Deployment Audit\n\n" + markdown_table(deployment) + "\n", encoding="utf-8")
    coverage.to_csv(root / "dealer_gamma_history_coverage_audit.csv", index=False)
    (root / "dealer_gamma_history_coverage_audit.md").write_text("# Dealer Gamma History Coverage Audit\n\n" + markdown_table(coverage) + "\n", encoding="utf-8")
    hist = root / "dealer_gamma_history"
    hist.mkdir(parents=True, exist_ok=True)
    write_table(backfill, hist / "dealer_gamma_proxy_history.csv", hist / "dealer_gamma_proxy_history.parquet")
    write_dealer_gamma_quality_rules(root)
    manual_report = write_manual_validation_report(root)
    total_snapshots = int(coverage["snapshot_count"].sum()) if "snapshot_count" in coverage else 0
    backfill_rows = len(backfill)
    source_basis = "; ".join(sorted(set(str(v) for v in coverage.get("source_basis", pd.Series(dtype=str)).dropna()))) if not coverage.empty else "unknown"
    medium_or_better = 0
    if not backfill.empty and "economic_quality" in backfill:
        medium_or_better = int(backfill["economic_quality"].isin(["high", "medium"]).sum())
    if total_snapshots == 0:
        gate_note = "Blocked: no raw option-chain snapshots were available to inspect."
    elif medium_or_better == 0:
        gate_note = "Blocked: no reconstructed dealer gamma rows reached medium or high economic quality."
    else:
        gate_note = "Audit produced at least one medium-or-better reconstructed dealer gamma row."
    (hist / "dealer_gamma_backfill_audit.md").write_text(
        "# Dealer Gamma Backfill Audit\n\n"
        f"Raw option-chain snapshot records inspected: {total_snapshots}\n\n"
        f"Reconstructed dealer gamma proxy rows written: {backfill_rows}\n\n"
        f"Medium-or-better economic quality rows: {medium_or_better}\n\n"
        f"Audit source basis: {source_basis}\n\n"
        f"Manual validation report: `{manual_report.name}`\n\n"
        f"Gate note: {gate_note}\n\n"
        "Dealer gamma rows are reconstructed proxy features from raw option-chain snapshots. They are not observed dealer inventory.\n",
        encoding="utf-8",
    )
    write_phase3_completion_gate_audit(root, deployment, coverage, backfill)


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    clean = df.fillna("").astype(str)
    cols = list(clean.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in clean.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("|", "\\|").replace("\n", " ") for c in cols) + " |")
    return "\n".join(lines)


def write_readme(root: Path) -> Path:
    path = root / "README_market_environment_score_v0.md"
    path.write_text(
        """# Market Environment Score v0

Market Environment Score is a separate axis from Morita Bot S/A/B signal rank and Execution Score.

It is display/storage only. It does not implement GO/CAUTION/STOP, sizing, rank overrides, automatic trading, or hard filters.

Scores:

- `market_environment_score_observed_v0`: Trend, VIX, and calendar/event inputs only.
- `market_environment_score_proxy_augmented_v0`: observed score plus Dealer Gamma, leveraged ETF, CTA, Vol Control, and Risk Parity proxies.
- `market_environment_score_v0`: standard display score; unavailable when coverage is below 60%.

Execution Score is stored separately and measures option quote/liquidity fit, not market environment.
""",
        encoding="utf-8",
    )
    return path


def run(root: Path = Path("."), run_backfill: bool = True) -> dict[str, Path]:
    deployment = deployment_audit(root)
    coverage = dealer_gamma_coverage_audit(root)
    backfill = dealer_gamma_backfill(root) if run_backfill else pd.DataFrame()
    write_audit_reports(root, deployment, coverage, backfill)
    score_df = market_score_snapshot(root)
    out = root / "market_environment_scores"
    out.mkdir(parents=True, exist_ok=True)
    token = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d_%H%M")
    snap_csv = out / f"market_environment_score_snapshot_{token}.csv"
    snap_json = out / f"market_environment_score_snapshot_{token}.json"
    score_df.to_csv(snap_csv, index=False)
    snap_json.write_text(json.dumps(score_df.replace({np.nan: None}).to_dict("records"), indent=2, ensure_ascii=False), encoding="utf-8")
    append_history(score_df, out / "market_environment_score_history.csv", out / "market_environment_score_history.parquet")
    option_context = pd.read_csv(root / "morita_option_context/option_context.csv") if (root / "morita_option_context/option_context.csv").exists() else pd.DataFrame()
    execution_df = calculate_execution_scores(option_context)
    exe = root / "execution_scores"
    exe.mkdir(parents=True, exist_ok=True)
    write_table(execution_df, exe / "execution_score_history.csv", exe / "execution_score_history.parquet")
    enrich_contexts(root, score_df, execution_df)
    reports = write_score_reports(root, score_df)
    readme = write_readme(root)
    outputs = {
        "readme": readme,
        "deployment_audit_md": root / "market_environment_score_deployment_audit.md",
        "deployment_audit_csv": root / "market_environment_score_deployment_audit.csv",
        "dealer_coverage_md": root / "dealer_gamma_history_coverage_audit.md",
        "dealer_coverage_csv": root / "dealer_gamma_history_coverage_audit.csv",
        "dealer_history_csv": root / "dealer_gamma_history/dealer_gamma_proxy_history.csv",
        "dealer_history_parquet": root / "dealer_gamma_history/dealer_gamma_proxy_history.parquet",
        "dealer_backfill_audit": root / "dealer_gamma_history/dealer_gamma_backfill_audit.md",
        "dealer_quality_rules": root / "dealer_gamma_history/dealer_gamma_quality_rules_v2.json",
        "dealer_snapshot_file_audit": root / "dealer_gamma_history/dealer_gamma_snapshot_file_audit.csv",
        "dealer_root_diagnostics": root / "dealer_gamma_history/dealer_gamma_root_diagnostics.csv",
        "phase3_completion_gate_audit": root / "phase3_1_completion_gate_audit.md",
        "score_history_csv": out / "market_environment_score_history.csv",
        "score_history_parquet": out / "market_environment_score_history.parquet",
        "score_snapshot_csv": snap_csv,
        "score_snapshot_json": snap_json,
        "execution_history_csv": exe / "execution_score_history.csv",
        "execution_history_parquet": exe / "execution_score_history.parquet",
        **reports,
    }
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--skip-backfill", action="store_true")
    args = parser.parse_args()
    outputs = run(Path(args.root), run_backfill=not args.skip_backfill)
    for key, value in outputs.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
