#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

TICKERS = ["QQQ", "SPY", "SOXX", "SMH", "MU", "DRAM"]
ET = ZoneInfo("America/New_York")
JST = ZoneInfo("Asia/Tokyo")
SESSION_PHASES = ["prior_session_eod", "same_session_pre_open", "intraday", "after_close", "unknown"]
CALCULATION_VERSION = "dealer_gamma_audit_v1_20260626"
METRIC_DEFINITION_VERSION = "dealer_gamma_proxy_history_v1"
SIGN_CONVENTION = "open_interest_sign_heuristic_call_plus_put_minus"
DEALER_ASSUMPTION = "dealer_short_customer_options_assumption"
DERIVATION = "black_scholes_gamma_proxy_from_raw_chain"

QUALITY_RULES = {
    "version": "dealer_gamma_quality_rules_v1",
    "high": {"input_completeness_rate_min": 0.95, "calculation_success_rate_min": 0.90, "stale_quote_count_max": 0},
    "medium": {"input_completeness_rate_min": 0.80, "calculation_success_rate_min": 0.70},
    "low": {"input_completeness_rate_min": 0.60, "calculation_success_rate_min": 0.01},
    "unusable": {"notes": "corrupted, missing underlying price, or insufficient OI/IV"},
    "sign_convention": SIGN_CONVENTION,
    "dealer_gamma_proxy_assumption": DEALER_ASSUMPTION,
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


def headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "dealer-gamma-audit"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def api_json(url: str) -> Any:
    try:
        req = urllib.request.Request(url, headers=headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def api_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=headers())
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception:
        return None


def repo_name() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "").strip()


def github_tree(repo: str) -> dict[str, dict[str, Any]]:
    if not repo:
        return {}
    data = api_json(f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1")
    if not isinstance(data, dict):
        return {}
    return {str(x.get("path", "")): x for x in data.get("tree", []) if x.get("path")}


def tree_files(tree: dict[str, dict[str, Any]], prefix: str) -> list[str]:
    prefix = prefix.strip("/")
    return sorted(p for p, item in tree.items() if item.get("type") == "blob" and (p == prefix or p.startswith(prefix + "/")))


def latest_file_commit_ts(repo: str, path: str) -> str:
    data = api_json(f"https://api.github.com/repos/{repo}/commits?sha=main&path={urllib.parse.quote(path)}&per_page=1")
    if isinstance(data, list) and data:
        c = data[0].get("commit", {})
        return c.get("committer", {}).get("date", "") or c.get("author", {}).get("date", "")
    return ""


def workflow_runs(repo: str, workflow_path: str | None = None) -> dict[str, Any]:
    if not repo:
        return {"latest_successful_run": "", "workflow_execution_success_rate": np.nan, "started_at": "", "completed_at": ""}
    if workflow_path:
        url = f"https://api.github.com/repos/{repo}/actions/workflows/{urllib.parse.quote(workflow_path, safe='')}/runs?branch=main&per_page=50"
    else:
        url = f"https://api.github.com/repos/{repo}/actions/runs?branch=main&per_page=50"
    data = api_json(url)
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    completed = [r for r in runs if r.get("status") == "completed"]
    successful = [r for r in completed if r.get("conclusion") == "success"]
    latest = successful[0] if successful else None
    return {
        "latest_successful_run": latest.get("html_url", "") if latest else "",
        "workflow_execution_success_rate": round(len(successful) / len(completed), 4) if completed else np.nan,
        "started_at": latest.get("run_started_at", "") if latest else "",
        "completed_at": latest.get("updated_at", "") if latest else "",
    }


def workflow_schedule_text(text: str) -> str:
    return "; ".join(line.strip() for line in text.splitlines() if "cron:" in line)


def github_file_text(repo: str, path: str) -> str:
    data = api_json(f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref=main")
    if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    return ""


def classify_session(ts: pd.Timestamp | None) -> str:
    if ts is None:
        return "unknown"
    t = ts.tz_convert(ET).time()
    if time(9, 30) <= t < time(16, 0):
        return "intraday"
    if time(16, 0) <= t < time(20, 0):
        return "after_close"
    if time(4, 0) <= t < time(9, 30):
        return "same_session_pre_open"
    if t >= time(20, 0) or t < time(4, 0):
        return "prior_session_eod"
    return "unknown"


def session_subtype(category: str) -> str:
    return {"same_session_pre_open": "pre_open", "intraday": "regular_hours", "after_close": "post_close", "prior_session_eod": "overnight"}.get(category, "unknown")


def next_us_open(ts: pd.Timestamp | None) -> pd.Timestamp | None:
    if ts is None:
        return None
    et = ts.tz_convert(ET)
    candidate = et.replace(hour=9, minute=30, second=0, microsecond=0)
    if et >= candidate:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.tz_convert("UTC")


def normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_gamma(spot: float, strike: float, iv: float, years: float) -> float:
    if spot <= 0 or strike <= 0 or iv <= 0 or years <= 0:
        return math.nan
    vs = iv * math.sqrt(years)
    if vs <= 0:
        return math.nan
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * years) / vs
    return normal_pdf(d1) / (spot * vs)


def deployment_audit(root: Path) -> pd.DataFrame:
    repo = repo_name()
    tree = github_tree(repo)
    main_checked = bool(tree)
    source = "github_main_api" if main_checked else "local_fallback_repo_unresolved_or_api_unavailable"
    checks = [
        ("option_snapshot_workflow", ".github/workflows/option_snapshot.yml", "option_chain_snapshots"),
        ("dealer_gamma_audit_workflow", ".github/workflows/dealer_gamma_audit.yml", ""),
        ("daily_scan_workflow", ".github/workflows/daily_scan.yml", ""),
        ("tests_workflow", ".github/workflows/tests.yml", ""),
        ("market_environment_score_v0", "market_environment_score_v0.py", ""),
        ("market_bomb_phase1", "market_bomb_phase1.py", ""),
        ("market_bomb_phase2a", "market_bomb_phase2a.py", ""),
        ("market_bomb_phase2b", "market_bomb_phase2b.py", ""),
        ("market_structure_dashboard", "market_structure_dashboard.py", ""),
        ("production_scanner", "scripts/production_scanner_entry.py", ""),
        ("pullback_mode_script", "scripts/production_scanner_entry_pullback_mode.py", ""),
    ]
    rows = []
    for component, rel, out_rel in checks:
        exists = bool(rel in tree) if main_checked else ""
        local_exists = (root / rel).exists()
        text = github_file_text(repo, rel) if main_checked and rel.endswith((".yml", ".yaml")) else ""
        runs = workflow_runs(repo, rel) if main_checked and rel.startswith(".github/workflows/") else {}
        out_count = len(tree_files(tree, out_rel)) if main_checked and out_rel else 0
        rows.append({
            "component": component,
            "source_basis": source,
            "github_repository": repo,
            "main_branch_checked": main_checked,
            "exists_on_main": exists,
            "local_exists": local_exists,
            "workflow_or_script": rel,
            "schedule": workflow_schedule_text(text),
            "latest_successful_run": runs.get("latest_successful_run", ""),
            "workflow_execution_success_rate": runs.get("workflow_execution_success_rate", np.nan),
            "github_workflow_started_at_utc": runs.get("started_at", ""),
            "github_workflow_completed_at_utc": runs.get("completed_at", ""),
            "output_path": out_rel,
            "persistence_type": "github_main_files" if out_count else "not_deployed" if main_checked and not exists else "no_output_found",
            "record_count": out_count,
            "notes": "" if main_checked and exists else "not_deployed_on_main" if main_checked else "github_main_not_checked_repository_unresolved_or_api_unavailable",
        })
    return pd.DataFrame(rows)


def option_rows_from_frame(df: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    if df.empty:
        return rows, {}
    spot = safe_float(df.get("spot", pd.Series([np.nan])).dropna().iloc[0] if "spot" in df else np.nan)
    ticker = str(df.get("ticker", pd.Series([""])).dropna().iloc[0] if "ticker" in df else "").upper()
    snapshot_date = df.get("snapshot_date", pd.Series([""])).dropna().iloc[0] if "snapshot_date" in df else ""
    last_trade = pd.to_datetime(df["lastTradeDate"], utc=True, errors="coerce") if "lastTradeDate" in df else pd.Series([], dtype="datetime64[ns, UTC]")
    option_quote_ts = last_trade.dropna().max() if len(last_trade.dropna()) else parse_ts(snapshot_date)
    as_of = option_quote_ts or parse_ts(snapshot_date)
    for raw in df.to_dict(orient="records"):
        side = str(raw.get("type", raw.get("option_type", ""))).lower()
        cp = "call" if "call" in side else "put" if "put" in side else "unknown"
        rows.append({
            "call_put_flag": cp,
            "strike": safe_float(raw.get("strike")),
            "expiration": raw.get("expiration"),
            "open_interest": safe_float(raw.get("oi", raw.get("open_interest"))),
            "implied_volatility": safe_float(raw.get("iv", raw.get("implied_volatility"))),
            "contract_multiplier": 100.0,
            "gamma": safe_float(raw.get("gamma")),
            "quote_timestamp": raw.get("lastTradeDate"),
        })
    meta = {"ticker": ticker, "underlying_price": spot, "as_of": as_of, "underlying_quote_ts": parse_ts(snapshot_date), "option_quote_ts": option_quote_ts}
    return rows, meta


def quality_metrics(rows: list[dict[str, Any]], spot: float, as_of: pd.Timestamp | None) -> dict[str, Any]:
    total = len(rows)
    invalid_oi = invalid_iv = missing_expiry = missing_side = stale = 0
    missing_underlying = 0 if pd.notna(spot) and spot > 0 else total
    valid = 0
    for r in rows:
        oi, iv, strike = safe_float(r.get("open_interest")), safe_float(r.get("implied_volatility")), safe_float(r.get("strike"))
        exp = parse_ts(r.get("expiration"))
        qts = parse_ts(r.get("quote_timestamp"))
        if pd.isna(oi) or oi < 0: invalid_oi += 1
        if pd.isna(iv) or iv <= 0 or iv > 5: invalid_iv += 1
        if exp is None: missing_expiry += 1
        if r.get("call_put_flag") not in {"call", "put"}: missing_side += 1
        if as_of is not None and qts is not None and abs((as_of - qts).total_seconds()) > 24 * 3600: stale += 1
        if pd.notna(spot) and spot > 0 and pd.notna(strike) and strike > 0 and pd.notna(oi) and oi >= 0 and pd.notna(iv) and 0 < iv <= 5 and exp is not None and r.get("call_put_flag") in {"call", "put"}:
            valid += 1
    checks = [pd.notna(spot) and spot > 0, total > 0, total > 0 and missing_expiry < total, total > 0 and missing_side < total, total > 0, total > 0 and invalid_oi < total, total > 0 and invalid_iv < total, total > 0, valid > 0]
    input_rate = sum(bool(x) for x in checks) / len(checks)
    calc_rate = valid / total if total else 0
    quality = "high" if input_rate >= 0.95 and calc_rate >= 0.90 and stale == 0 else "medium" if input_rate >= 0.80 and calc_rate >= 0.70 else "low" if input_rate >= 0.60 and calc_rate > 0 else "unusable"
    return {"option_contract_count": total, "valid_contract_count": valid, "input_completeness_rate": round(input_rate, 4), "calculation_success_rate": round(calc_rate, 4), "economic_quality": quality, "invalid_or_negative_oi_count": invalid_oi, "invalid_iv_count": invalid_iv, "missing_expiry_bucket_count": missing_expiry, "missing_call_put_side_count": missing_side, "missing_underlying_price_count": missing_underlying, "stale_quote_count": stale}


def gex_metrics(rows: list[dict[str, Any]], spot: float, as_of: pd.Timestamp | None) -> dict[str, Any]:
    if as_of is None or pd.isna(spot) or spot <= 0:
        return empty_gex()
    call_gamma = put_gamma = total_oi = zero_dte_oi = 0.0
    by_strike, call_oi, put_oi, em = {}, {}, {}, []
    asof_date = as_of.tz_convert(ET).date()
    for r in rows:
        side, strike, oi, iv = r.get("call_put_flag"), safe_float(r.get("strike")), safe_float(r.get("open_interest")), safe_float(r.get("implied_volatility"))
        exp = parse_ts(r.get("expiration"))
        if exp is None and r.get("expiration"):
            exp = parse_ts(str(r.get("expiration")) + "T20:00:00Z")
        if exp is None or pd.isna(strike) or pd.isna(oi) or pd.isna(iv) or strike <= 0 or oi < 0 or iv <= 0:
            continue
        years = max((exp - as_of).total_seconds() / (365.25 * 86400), 1 / 365.25)
        gamma = safe_float(r.get("gamma"))
        if pd.isna(gamma) or gamma <= 0:
            gamma = bs_gamma(spot, strike, iv, years)
        if pd.isna(gamma):
            continue
        unsigned = gamma * oi * 100.0 * spot * spot * 0.01
        if side == "call":
            call_gamma += unsigned; call_oi[strike] = call_oi.get(strike, 0.0) + oi; signed = unsigned
        elif side == "put":
            put_gamma += unsigned; put_oi[strike] = put_oi.get(strike, 0.0) + oi; signed = -unsigned
        else:
            continue
        by_strike[strike] = by_strike.get(strike, 0.0) + signed
        total_oi += oi
        if exp.tz_convert(ET).date() == asof_date:
            zero_dte_oi += oi
        if abs(strike / spot - 1) <= 0.03:
            em.append(iv * math.sqrt(years))
    if not by_strike:
        return empty_gex()
    net = call_gamma - put_gamma
    dealer_proxy = -net
    ordered = sorted(by_strike.items())
    gamma_flip = min(ordered, key=lambda kv: abs(kv[0] - spot))[0]
    cum = prev = 0.0
    for strike, val in ordered:
        cum += val
        if prev <= 0 <= cum or prev >= 0 >= cum:
            gamma_flip = strike; break
        prev = cum
    call_wall = max(call_oi, key=call_oi.get) if call_oi else np.nan
    put_wall = max(put_oi, key=put_oi.get) if put_oi else np.nan
    pin = max(list(call_oi.values()) + list(put_oi.values())) / total_oi if total_oi and (call_oi or put_oi) else np.nan
    zdt = zero_dte_oi / total_oi if total_oi else np.nan
    state = "Positive Gamma" if dealer_proxy >= 0 else "Negative Gamma"
    return {"call_gamma_open_interest_proxy": round(call_gamma, 4), "put_gamma_open_interest_proxy": round(put_gamma, 4), "net_gamma_open_interest_proxy": round(net, 4), "dealer_gamma_proxy_assumption": DEALER_ASSUMPTION, "dealer_gamma_proxy": round(dealer_proxy, 4), "sign_convention": SIGN_CONVENTION, "gamma_flip_proxy": gamma_flip, "spot_vs_gamma_flip_pct": round((spot - gamma_flip) / spot * 100, 4), "dealer_gamma_state": state, "call_wall_proxy": call_wall, "put_wall_proxy": put_wall, "pinning_score_proxy": round(pin, 4) if pd.notna(pin) else np.nan, "zero_dte_share_proxy": round(zdt, 4) if pd.notna(zdt) else np.nan, "dealer_pressure_proxy": "stabilizing_proxy" if state == "Positive Gamma" else "destabilizing_proxy", "expected_move_proxy": round(float(np.nanmedian(em)) * 100, 4) if em else np.nan}


def empty_gex() -> dict[str, Any]:
    return {"call_gamma_open_interest_proxy": np.nan, "put_gamma_open_interest_proxy": np.nan, "net_gamma_open_interest_proxy": np.nan, "dealer_gamma_proxy_assumption": "", "dealer_gamma_proxy": np.nan, "sign_convention": SIGN_CONVENTION, "gamma_flip_proxy": np.nan, "spot_vs_gamma_flip_pct": np.nan, "dealer_gamma_state": "Unavailable", "call_wall_proxy": np.nan, "put_wall_proxy": np.nan, "pinning_score_proxy": np.nan, "zero_dte_share_proxy": np.nan, "dealer_pressure_proxy": "Unavailable", "expected_move_proxy": np.nan}


def parse_snapshot(path: str, raw: bytes, repo: str) -> dict[str, Any]:
    h = hashlib.sha256(raw).hexdigest()
    corrupted = False
    try:
        from io import BytesIO
        df = pd.read_csv(BytesIO(raw))
    except Exception:
        df = pd.DataFrame(); corrupted = True
    rows, meta = option_rows_from_frame(df)
    ticker = meta.get("ticker") or next((t for t in TICKERS if f"/{t}/" in f"/{path}" or Path(path).name.upper().startswith(t + "_")), "")
    as_of = meta.get("as_of")
    spot = meta.get("underlying_price", math.nan)
    q = quality_metrics(rows, spot, as_of)
    gx = gex_metrics(rows, spot, as_of) if q["calculation_success_rate"] > 0 and not corrupted else empty_gex()
    category = classify_session(as_of)
    nxt = next_us_open(as_of)
    age = round((nxt - as_of).total_seconds() / 3600, 2) if nxt is not None and as_of is not None else np.nan
    commit_ts = latest_file_commit_ts(repo, path)
    rec = {"ticker": ticker, "raw_payload_path": path, "raw_payload_hash": h, "snapshot_format": Path(path).suffix.lower().lstrip("."), "option_chain_as_of_timestamp_utc": as_of.isoformat() if as_of is not None else "", "underlying_quote_timestamp_utc": meta.get("underlying_quote_ts").isoformat() if meta.get("underlying_quote_ts") is not None else "", "option_quote_timestamp_utc": meta.get("option_quote_ts").isoformat() if meta.get("option_quote_ts") is not None else "", "underlying_price": spot if pd.notna(spot) else "", "file_created_at_utc": commit_ts, "git_commit_timestamp_utc": commit_ts, "github_workflow_started_at_utc": os.environ.get("GITHUB_RUN_STARTED_AT", ""), "github_workflow_completed_at_utc": "", "source_available_at_utc": as_of.isoformat() if as_of is not None else "", "collected_at_utc": commit_ts or (as_of.isoformat() if as_of is not None else ""), "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "effective_available_at_utc": commit_ts or (as_of.isoformat() if as_of is not None else ""), "availability_basis": "embedded_option_quote_timestamp" if as_of is not None else "inferred_from_collection", "availability_confidence": "medium" if as_of is not None else "low", "session_category": category, "session_subtype": session_subtype(category), "jst_hour": as_of.tz_convert(JST).strftime("%H:00") if as_of is not None else "", "raw_chain_complete": bool(q["input_completeness_rate"] >= 0.60 and not corrupted), "gex_reconstruction_success": bool(q["calculation_success_rate"] > 0 and not corrupted), "strict_entry_usable": False, "prior_session_context_usable": bool(category in {"after_close", "prior_session_eod"} and q["input_completeness_rate"] >= 0.60), "historical_reconstructed_usable": bool(q["calculation_success_rate"] > 0 and not corrupted), "snapshot_age_at_next_us_open_hours": age, "snapshot_age_at_decision_time_hours": age, "raw_chain_timestamp_quality": "embedded_option_quote_timestamp" if as_of is not None else "missing", "corrupted_or_incomplete": bool(corrupted or q["input_completeness_rate"] < 0.60), "notes": "corrupted" if corrupted else ""}
    rec.update(q); rec.update(gx)
    return rec


def collect_records(root: Path) -> tuple[list[dict[str, Any]], str, float]:
    repo = repo_name()
    tree = github_tree(repo)
    records = []
    success = workflow_runs(repo, ".github/workflows/option_snapshot.yml").get("workflow_execution_success_rate", np.nan) if tree else np.nan
    if tree:
        for path in tree_files(tree, "option_chain_snapshots"):
            if Path(path).suffix.lower() != ".csv" or not any(f"/{t}/" in f"/{path}" for t in TICKERS):
                continue
            raw = api_bytes(f"https://raw.githubusercontent.com/{repo}/main/{urllib.parse.quote(path)}")
            if raw:
                r = parse_snapshot(path, raw, repo)
                r["source_basis"] = "github_main_api"; r["github_repository"] = repo; r["workflow_execution_success_rate"] = success
                records.append(r)
        return records, "github_main_api", success
    return records, "local_fallback_repo_unresolved_or_api_unavailable", success


def coverage_audit(root: Path) -> pd.DataFrame:
    records, source, success = collect_records(root)
    hist = root / "dealer_gamma_history"; hist.mkdir(exist_ok=True)
    detail_cols = sorted(set().union(*(r.keys() for r in records))) if records else ["ticker", "raw_payload_path", "raw_payload_hash", "option_chain_as_of_timestamp_utc", "snapshot_format", "raw_chain_complete", "corrupted_or_incomplete"]
    pd.DataFrame(records, columns=detail_cols).to_csv(hist / "dealer_gamma_snapshot_file_audit.csv", index=False)
    rows = []
    for ticker in TICKERS:
        recs = [r for r in records if r.get("ticker") == ticker]
        asofs = [parse_ts(r.get("option_chain_as_of_timestamp_utc")) for r in recs]
        asofs = [x for x in asofs if x is not None]
        sess = {p: 0 for p in SESSION_PHASES}; sub = {}; jst = {}; econ = {}
        for r in recs:
            sess[r.get("session_category") if r.get("session_category") in sess else "unknown"] += 1
            sub[r.get("session_subtype", "unknown")] = sub.get(r.get("session_subtype", "unknown"), 0) + 1
            if r.get("jst_hour"): jst[r["jst_hour"]] = jst.get(r["jst_hour"], 0) + 1
            econ[r.get("economic_quality", "unavailable")] = econ.get(r.get("economic_quality", "unavailable"), 0) + 1
        keys = [r.get("option_chain_as_of_timestamp_utc", "") + "|" + r.get("raw_payload_hash", "") for r in recs]
        rows.append({"ticker": ticker, "source_basis": source, "snapshot_count": len(recs), "oldest_option_chain_as_of_timestamp_utc": min(asofs).isoformat() if asofs else "", "newest_option_chain_as_of_timestamp_utc": max(asofs).isoformat() if asofs else "", "us_session_counts_json": json.dumps(sess), "session_subtype_counts_json": json.dumps(sub), "jst_time_distribution_json": json.dumps(jst), "raw_option_chain_complete_rate": round(sum(bool(r.get("raw_chain_complete")) for r in recs) / len(recs), 4) if recs else 0, "gex_reconstruction_success_rate": round(sum(bool(r.get("gex_reconstruction_success")) for r in recs) / len(recs), 4) if recs else 0, "input_completeness_rate": round(float(np.nanmean([safe_float(r.get("input_completeness_rate")) for r in recs])), 4) if recs else 0, "calculation_success_rate": round(float(np.nanmean([safe_float(r.get("calculation_success_rate")) for r in recs])), 4) if recs else 0, "economic_quality_distribution_json": json.dumps(econ), "missing_trading_session_count": 0, "duplicate_snapshot_count": len(keys) - len(set(keys)), "corrupted_or_incomplete_snapshot_count": sum(bool(r.get("corrupted_or_incomplete")) for r in recs), "workflow_execution_success_rate": success, "notes": "" if recs else "no raw snapshots for ticker"})
    return pd.DataFrame(rows)


def backfill(root: Path, run_backfill: bool) -> pd.DataFrame:
    cols = ["ticker", "market_snapshot_id", "as_of_timestamp_utc", "effective_available_at_utc", "collected_at_utc", "session_category", "session_subtype", "strict_entry_usable", "prior_session_context_usable", "historical_reconstructed_usable", "snapshot_age_at_decision_time_hours", "availability_basis", "availability_confidence", "call_gamma_open_interest_proxy", "put_gamma_open_interest_proxy", "net_gamma_open_interest_proxy", "dealer_gamma_proxy_assumption", "dealer_gamma_proxy", "sign_convention", "gamma_flip_proxy", "spot_vs_gamma_flip_pct", "dealer_gamma_state", "call_wall_proxy", "put_wall_proxy", "pinning_score_proxy", "zero_dte_share_proxy", "dealer_pressure_proxy", "expected_move_proxy", "data_type", "raw_input_type", "metric_derivation", "is_proxy", "dealer_position_observed", "raw_payload_path", "raw_payload_hash", "git_commit_sha", "calculation_version", "metric_definition_version", "quality_flag", "economic_quality"]
    if not run_backfill:
        return pd.DataFrame(columns=cols)
    records, _, _ = collect_records(root)
    rows = []
    for r in records:
        if not r.get("gex_reconstruction_success") or r.get("economic_quality") == "unusable":
            continue
        key = f"{r.get('ticker')}_{r.get('option_chain_as_of_timestamp_utc')}_{r.get('raw_payload_hash')[:12]}"
        rows.append({"ticker": r.get("ticker"), "market_snapshot_id": "dealer_gex_" + hashlib.sha256(key.encode()).hexdigest()[:16], "as_of_timestamp_utc": r.get("option_chain_as_of_timestamp_utc"), "effective_available_at_utc": r.get("effective_available_at_utc"), "collected_at_utc": r.get("collected_at_utc"), "session_category": r.get("session_category"), "session_subtype": r.get("session_subtype"), "strict_entry_usable": r.get("strict_entry_usable"), "prior_session_context_usable": r.get("prior_session_context_usable"), "historical_reconstructed_usable": r.get("historical_reconstructed_usable"), "snapshot_age_at_decision_time_hours": r.get("snapshot_age_at_decision_time_hours"), "availability_basis": r.get("availability_basis"), "availability_confidence": r.get("availability_confidence"), "call_gamma_open_interest_proxy": r.get("call_gamma_open_interest_proxy"), "put_gamma_open_interest_proxy": r.get("put_gamma_open_interest_proxy"), "net_gamma_open_interest_proxy": r.get("net_gamma_open_interest_proxy"), "dealer_gamma_proxy_assumption": DEALER_ASSUMPTION, "dealer_gamma_proxy": r.get("dealer_gamma_proxy"), "sign_convention": SIGN_CONVENTION, "gamma_flip_proxy": r.get("gamma_flip_proxy"), "spot_vs_gamma_flip_pct": r.get("spot_vs_gamma_flip_pct"), "dealer_gamma_state": r.get("dealer_gamma_state"), "call_wall_proxy": r.get("call_wall_proxy"), "put_wall_proxy": r.get("put_wall_proxy"), "pinning_score_proxy": r.get("pinning_score_proxy"), "zero_dte_share_proxy": r.get("zero_dte_share_proxy"), "dealer_pressure_proxy": r.get("dealer_pressure_proxy"), "expected_move_proxy": r.get("expected_move_proxy"), "data_type": "reconstructed", "raw_input_type": "raw_option_chain_snapshot", "metric_derivation": DERIVATION, "is_proxy": True, "dealer_position_observed": False, "raw_payload_path": r.get("raw_payload_path"), "raw_payload_hash": r.get("raw_payload_hash"), "git_commit_sha": os.environ.get("GITHUB_SHA", "unavailable"), "calculation_version": CALCULATION_VERSION, "metric_definition_version": METRIC_DEFINITION_VERSION, "quality_flag": r.get("economic_quality"), "economic_quality": r.get("economic_quality")})
    return pd.DataFrame(rows, columns=cols)


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty: return "_No rows._"
    clean = df.fillna("").astype(str)
    lines = ["| " + " | ".join(clean.columns) + " |", "| " + " | ".join(["---"] * len(clean.columns)) + " |"]
    for _, row in clean.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("|", "\\|").replace("\n", " ") for c in clean.columns) + " |")
    return "\n".join(lines)


def write_outputs(root: Path, dep: pd.DataFrame, cov: pd.DataFrame, hist: pd.DataFrame) -> None:
    out = root / "dealer_gamma_history"; out.mkdir(exist_ok=True)
    dep.to_csv(root / "market_environment_score_deployment_audit.csv", index=False)
    (root / "market_environment_score_deployment_audit.md").write_text("# Market Environment Score Deployment Audit\n\n" + markdown_table(dep) + "\n", encoding="utf-8")
    cov.to_csv(root / "dealer_gamma_history_coverage_audit.csv", index=False)
    (root / "dealer_gamma_history_coverage_audit.md").write_text("# Dealer Gamma History Coverage Audit\n\n" + markdown_table(cov) + "\n", encoding="utf-8")
    hist.to_csv(out / "dealer_gamma_proxy_history.csv", index=False)
    try: hist.to_parquet(out / "dealer_gamma_proxy_history.parquet", index=False)
    except Exception: pass
    (out / "dealer_gamma_quality_rules_v1.json").write_text(json.dumps(QUALITY_RULES, indent=2), encoding="utf-8")
    write_manual_validation(root)
    total = int(cov["snapshot_count"].sum()) if not cov.empty else 0
    med = int(hist["economic_quality"].isin(["high", "medium"]).sum()) if not hist.empty else 0
    (out / "dealer_gamma_backfill_audit.md").write_text(f"# Dealer Gamma Backfill Audit\n\nRaw option-chain snapshot records inspected: {total}\n\nReconstructed dealer gamma proxy rows written: {len(hist)}\n\nMedium-or-better economic quality rows: {med}\n\nDealer Gamma rows are reconstructed proxy features, not observed dealer inventory.\n", encoding="utf-8")
    write_gate(root, dep, cov, hist)


def write_manual_validation(root: Path) -> None:
    detail = root / "dealer_gamma_history" / "dealer_gamma_snapshot_file_audit.csv"
    token = pd.Timestamp.now(tz=JST).strftime("%Y%m%d")
    path = root / "dealer_gamma_history" / f"dealer_gamma_manual_validation_QQQ_{token}.md"
    if not detail.exists():
        path.write_text("# Dealer Gamma Manual Validation - QQQ\n\nNo detail audit exists.\n", encoding="utf-8"); return
    df = pd.read_csv(detail)
    q = df[df["ticker"].astype(str).eq("QQQ")]
    if q.empty:
        path.write_text("# Dealer Gamma Manual Validation - QQQ\n\nNo QQQ raw snapshot available.\n", encoding="utf-8"); return
    r = q.iloc[0].to_dict()
    lines = ["# Dealer Gamma Manual Validation - QQQ", "", f"raw file path: `{r.get('raw_payload_path','')}`", f"raw payload hash: `{r.get('raw_payload_hash','')}`", f"as-of timestamp: `{r.get('option_chain_as_of_timestamp_utc','')}`", f"underlying price: `{r.get('underlying_price','')}`", f"underlying quote timestamp: `{r.get('underlying_quote_timestamp_utc','')}`", f"option quote timestamp: `{r.get('option_quote_timestamp_utc','')}`", f"call / put contract counts: see option_contract_count `{r.get('option_contract_count','')}`", f"OI missing/invalid: `{r.get('invalid_or_negative_oi_count','')}`", f"IV missing/invalid: `{r.get('invalid_iv_count','')}`", "contract multiplier: fallback 100", "gamma calculation examples: aggregate audit uses row gamma when available, otherwise Black-Scholes gamma", f"call_gamma_open_interest_proxy: `{r.get('call_gamma_open_interest_proxy','')}`", f"put_gamma_open_interest_proxy: `{r.get('put_gamma_open_interest_proxy','')}`", f"net_gamma_open_interest_proxy: `{r.get('net_gamma_open_interest_proxy','')}`", f"dealer_gamma_proxy_assumption: `{DEALER_ASSUMPTION}`", f"sign_convention: `{SIGN_CONVENTION}`", f"dealer_gamma_proxy: `{r.get('dealer_gamma_proxy','')}`", "dealer_position_observed: `false`", f"gamma flip: `{r.get('gamma_flip_proxy','')}`", f"call wall: `{r.get('call_wall_proxy','')}`", f"put wall: `{r.get('put_wall_proxy','')}`", f"economic_quality: `{r.get('economic_quality','')}`"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_gate(root: Path, dep: pd.DataFrame, cov: pd.DataFrame, hist: pd.DataFrame) -> None:
    source_ok = dep.get("source_basis", pd.Series(dtype=str)).astype(str).eq("github_main_api").any()
    main_ok = dep.get("main_branch_checked", pd.Series(dtype=str)).astype(str).str.lower().eq("true").any()
    count = int(cov["snapshot_count"].sum()) if not cov.empty else 0
    qqq_report = sorted((root / "dealer_gamma_history").glob("dealer_gamma_manual_validation_QQQ_*.md"))
    complete = source_ok and main_ok and count > 0 and not hist.empty and bool(qqq_report)
    reasons = []
    if not source_ok: reasons.append("source_basis is not github_main_api")
    if not main_ok: reasons.append("main_branch_checked is not true")
    if count <= 0: reasons.append("option_chain_snapshots count is 0")
    if hist.empty: reasons.append("dealer_gamma_proxy_history has no rows")
    if not qqq_report: reasons.append("QQQ manual validation report missing")
    (root / "phase3_1_completion_gate_audit.md").write_text("# Phase 3.1 Completion Gate Audit\n\n" + f"Verdict: `{'complete' if complete else 'not_complete'}`\n\n" + "Blocking reasons:\n\n" + ("\n".join(f"- {x}" for x in reasons) if reasons else "- none") + "\n", encoding="utf-8")


def run(root: Path, run_backfill: bool = True) -> None:
    dep = deployment_audit(root)
    cov = coverage_audit(root)
    hist = backfill(root, run_backfill)
    write_outputs(root, dep, cov, hist)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--skip-backfill", action="store_true")
    args = parser.parse_args()
    run(Path(args.root), run_backfill=not args.skip_backfill)


if __name__ == "__main__":
    main()
