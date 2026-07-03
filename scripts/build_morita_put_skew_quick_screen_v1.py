from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "config" / "morita_put_skew_v1" / "put_skew_quick_screen_spec.json"
CHATGPT_BUNDLE = REPO_ROOT / "morita_put_skew_quick_screen_chatgpt_bundle.md"
MANIFEST_NAME = "skew_content_manifest.json"
ARCHIVE_ROOT = REPO_ROOT / "option_chain_snapshots"
REQUIRED_OPTION_COLUMNS = {"snapshot_date", "ticker", "expiration", "type", "strike", "iv", "spot"}
OPTION_KEYWORDS = ("option", "chain", "snapshot", "iv", "implied", "vol", "quote", "eod", "greeks")
INDEX_METRICS = ["qqq_put_skew_abs", "qqq_put_skew_normalized", "qqq_put_skew_abs_5d_change", "qqq_put_skew_normalized_5d_change"]
SINGLE_METRICS = ["single_name_put_skew_abs", "single_name_put_skew_normalized", "single_name_put_skew_abs_5d_change", "single_name_put_skew_normalized_5d_change"]
RELATIVE_METRICS = ["single_name_minus_qqq_normalized_skew", "single_name_minus_qqq_abs_skew"]
REQUIRED_OUTPUTS = [
    "skew_source_availability.csv",
    "skew_snapshot_coverage.csv",
    "skew_daily_index_panel.csv",
    "skew_signal_context_panel.csv",
    "skew_state_cutoffs.csv",
    "skew_outcome_summary.csv",
    "skew_rank_summary.csv",
    "skew_joint_index_single_name_summary.csv",
    "skew_quality_tier_summary.csv",
    "skew_receipt.json",
    "skew_summary.md",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def safe_float(value: Any) -> float | None:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception:
        return None


def fmt(value: Any, digits: int = 2) -> str:
    value = safe_float(value)
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def verify_manifest(path: Path, manifest_name: str) -> dict[str, Any]:
    manifest_path = path / manifest_name
    if not manifest_path.exists():
        raise SystemExit(f"manifest_missing:{repo_relative(manifest_path)}")
    manifest = load_json(manifest_path)
    expected = {entry["relative_path"]: entry["sha256"] for entry in manifest.get("files", [])}
    actual = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file() and p.name != manifest_name}
    for rel, expected_hash in expected.items():
        target = path / rel
        if not target.exists():
            raise SystemExit(f"manifest_missing_file:{rel}")
        if file_sha256(target) != expected_hash:
            raise SystemExit(f"manifest_sha_mismatch:{rel}")
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise SystemExit(f"manifest_extra_file:{extras[0]}")
    return manifest


def build_manifest(path: Path) -> dict[str, Any]:
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and child.name != MANIFEST_NAME:
            files.append({"relative_path": child.relative_to(path).as_posix(), "sha256": file_sha256(child), "bytes": child.stat().st_size})
    manifest = {"artifact_version": "morita_put_skew_quick_screen_v1", "created_at_utc": iso_now(), "files": files, "content_set_hash": text_hash(json_dumps(files))}
    write_json(path / MANIFEST_NAME, manifest)
    return manifest


def safe_clean_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        resolved = output_dir.resolve()
        if REPO_ROOT.resolve() not in resolved.parents and resolved != REPO_ROOT.resolve():
            raise SystemExit(f"refusing_to_clean_outside_repo:{resolved}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def inspect_local_snapshot_archive() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    candidates: list[Path] = []
    if ARCHIVE_ROOT.exists():
        candidates.extend(sorted(ARCHIVE_ROOT.rglob("*.csv")))
    for child in sorted(REPO_ROOT.iterdir()):
        name = child.name.lower()
        if child.is_dir() and child != ARCHIVE_ROOT and any(k in name for k in OPTION_KEYWORDS):
            candidates.extend(sorted(child.rglob("*.csv")))
    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        try:
            header = pd.read_csv(path, nrows=0)
            columns = set(header.columns)
        except Exception as exc:
            rows.append({"source_root": repo_relative(path.parent), "file_count": 1, "status": "unreadable", "notes": str(exc), "schema_columns": ""})
            continue
        status = "usable_minimum_schema" if REQUIRED_OPTION_COLUMNS.issubset(columns) else "missing_minimum_schema"
        rows.append(
            {
                "source_root": repo_relative(path.parent),
                "sample_file": path.name,
                "file_count": 1,
                "status": status,
                "schema_columns": "|".join(header.columns),
                "has_bid_ask": {"bid", "ask"}.issubset(columns),
                "has_open_interest": bool({"oi", "open_interest", "openInterest"}.intersection(columns)),
                "has_volume": "volume" in columns,
                "notes": "",
            }
        )
    if not rows:
        return pd.DataFrame(columns=["source_root", "sample_file", "file_count", "status", "schema_columns", "has_bid_ask", "has_open_interest", "has_volume", "notes"])
    df = pd.DataFrame(rows)
    grouped = (
        df.groupby(["source_root", "status", "schema_columns", "has_bid_ask", "has_open_interest", "has_volume"], dropna=False)
        .agg(file_count=("file_count", "sum"), sample_file=("sample_file", "first"), notes=("notes", "first"))
        .reset_index()
    )
    return grouped


def select_archive_source(availability: pd.DataFrame) -> Path | None:
    if availability.empty:
        return None
    usable = availability[availability["status"] == "usable_minimum_schema"]
    if usable.empty:
        return None
    roots = [REPO_ROOT / str(root) for root in usable["source_root"].unique()]
    if any(root == ARCHIVE_ROOT or ARCHIVE_ROOT in root.parents for root in roots):
        return ARCHIVE_ROOT
    return roots[0]


def load_option_archive(source_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = []
    file_rows = []
    for path in sorted(source_root.rglob("*.csv")):
        try:
            header = pd.read_csv(path, nrows=0)
        except Exception:
            continue
        if not REQUIRED_OPTION_COLUMNS.issubset(set(header.columns)):
            continue
        df = pd.read_csv(path)
        df["source_file"] = repo_relative(path)
        frames.append(df)
        file_rows.append({"source_file": repo_relative(path), "rows": len(df)})
    if not frames:
        return pd.DataFrame(), pd.DataFrame(file_rows)
    raw = pd.concat(frames, ignore_index=True)
    raw["ticker"] = raw["ticker"].astype(str).str.upper()
    raw["snapshot_date"] = pd.to_datetime(raw["snapshot_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    raw["expiration"] = pd.to_datetime(raw["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")
    raw["type"] = raw["type"].astype(str).str.lower()
    for col in ["strike", "iv", "spot", "bid", "ask", "oi", "volume"]:
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw.dropna(subset=["ticker", "snapshot_date", "expiration", "type", "strike", "iv", "spot"])
    return raw, pd.DataFrame(file_rows)


def contract_quality_tier(contracts: pd.DataFrame) -> str:
    if contracts.empty:
        return "unavailable"
    has_bid_ask = {"bid", "ask"}.issubset(contracts.columns)
    oi_col = "oi" if "oi" in contracts.columns else None
    oi_ok = True if oi_col is None else bool((pd.to_numeric(contracts[oi_col], errors="coerce") > 0).all())
    if has_bid_ask:
        bid = pd.to_numeric(contracts["bid"], errors="coerce")
        ask = pd.to_numeric(contracts["ask"], errors="coerce")
        if bool(((bid >= 0) & (ask > bid)).all()) and oi_ok:
            return "tier_a"
    if oi_ok:
        return "tier_b"
    return "tier_c"


def nearest_option(candidates: pd.DataFrame, target_moneyness: float | None = None, spot: float | None = None) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    work = candidates.copy()
    if target_moneyness is not None and spot is not None:
        work["_distance"] = (work["strike"] / spot - target_moneyness).abs()
    elif spot is not None:
        work["_distance"] = (work["strike"] / spot - 1.0).abs()
    else:
        work["_distance"] = 0
    return work.sort_values(["_distance", "strike"]).head(1).drop(columns=["_distance"])


def construct_skew_for_snapshot(group: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    ticker = str(group["ticker"].iloc[0]).upper()
    snapshot_date = str(group["snapshot_date"].iloc[0])
    snap = pd.Timestamp(snapshot_date)
    group = group[(group["iv"] > 0) & (group["spot"] > 0) & (group["strike"] > 0)].copy()
    if group.empty:
        return {"ticker": ticker, "snapshot_date": snapshot_date, "skew_status": "unavailable_missing_direct_iv_or_spot"}
    group["expiration_dt"] = pd.to_datetime(group["expiration"], errors="coerce")
    group["dte"] = (group["expiration_dt"] - snap).dt.days
    eligible = group[(group["dte"] >= int(spec["eligible_dte_min_calendar_days"])) & (group["dte"] <= int(spec["eligible_dte_max_calendar_days"]))]
    if eligible.empty:
        return {"ticker": ticker, "snapshot_date": snapshot_date, "skew_status": "unavailable_no_21_to_45_dte_expiry"}
    expiries = eligible[["expiration", "dte"]].drop_duplicates().copy()
    expiries["_distance"] = (expiries["dte"] - int(spec["target_dte_calendar_days"])).abs()
    selected = expiries.sort_values(["_distance", "dte"]).iloc[0]
    selected_exp = selected["expiration"]
    selected_dte = int(selected["dte"])
    exp_group = eligible[eligible["expiration"] == selected_exp].copy()
    spot = float(exp_group["spot"].dropna().median())
    atm_band = float(spec["atm_moneyness_abs_max"])
    atm_candidates = exp_group[((exp_group["strike"] / spot - 1.0).abs() <= atm_band) & (exp_group["type"].isin(["call", "put"]))]
    atm_parts = []
    selected_contracts = []
    for opt_type in ["call", "put"]:
        part = nearest_option(atm_candidates[atm_candidates["type"] == opt_type], spot=spot)
        if not part.empty:
            atm_parts.append(float(part["iv"].iloc[0]))
            selected_contracts.append(part)
    if not atm_parts:
        return {"ticker": ticker, "snapshot_date": snapshot_date, "skew_status": "unavailable_no_atm_iv"}
    atm_iv = sum(atm_parts) / len(atm_parts)
    puts = exp_group[exp_group["type"] == "put"].copy()
    puts["moneyness"] = puts["strike"] / spot
    puts = puts[(puts["moneyness"] >= float(spec["otm_put_moneyness_min"])) & (puts["moneyness"] <= float(spec["otm_put_moneyness_max"]))]
    otm = nearest_option(puts, target_moneyness=float(spec["otm_put_target_moneyness"]), spot=spot)
    if otm.empty:
        return {"ticker": ticker, "snapshot_date": snapshot_date, "skew_status": "unavailable_no_085_095_otm_put"}
    selected_contracts.append(otm)
    otm_put_iv = float(otm["iv"].iloc[0])
    skew_abs = otm_put_iv - atm_iv
    selected_df = pd.concat(selected_contracts, ignore_index=True)
    return {
        "ticker": ticker,
        "snapshot_date": snapshot_date,
        "skew_status": "valid",
        "selected_expiration": selected_exp,
        "selected_dte": selected_dte,
        "spot": spot,
        "atm_iv": atm_iv,
        "otm_put_iv": otm_put_iv,
        "put_skew_abs": skew_abs,
        "put_skew_normalized": skew_abs / atm_iv if atm_iv > 0 else pd.NA,
        "quality_tier": contract_quality_tier(selected_df),
        "snapshot_timing_quality": "snapshot_date_end_of_day_proxy",
    }


def build_skew_panel(options: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    if options.empty:
        return pd.DataFrame()
    rows = [construct_skew_for_snapshot(group, spec) for _, group in options.groupby(["ticker", "snapshot_date"], dropna=False)]
    panel = pd.DataFrame(rows).sort_values(["ticker", "snapshot_date"])
    for metric in ["put_skew_abs", "put_skew_normalized"]:
        panel[metric] = pd.to_numeric(panel.get(metric), errors="coerce")
    valid = panel["skew_status"].eq("valid")
    panel["put_skew_abs_5d_change"] = pd.NA
    panel["put_skew_normalized_5d_change"] = pd.NA
    for ticker, idx in panel[valid].groupby("ticker").groups.items():
        sub = panel.loc[list(idx)].sort_values("snapshot_date")
        prior_abs = sub["put_skew_abs"].shift(5)
        prior_norm = sub["put_skew_normalized"].shift(5)
        panel.loc[sub.index, "put_skew_abs_5d_change"] = sub["put_skew_abs"] / prior_abs - 1.0
        panel.loc[sub.index, "put_skew_normalized_5d_change"] = sub["put_skew_normalized"] - prior_norm
    return panel


def load_baseline(baseline_run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    verify_manifest(baseline_run_dir, "source_content_manifest.json")
    panel = pd.read_csv(baseline_run_dir / "morita_bot_baseline_panel.csv")
    required = {"signal_id", "signal_decision_date", "signal_decision_timestamp_utc", "entry_session", "underlying_symbol", "signal_rank", "theme", "outcome_status", "reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise SystemExit(f"baseline_missing_columns:{','.join(missing)}")
    panel["signal_decision_date"] = pd.to_datetime(panel["signal_decision_date"]).dt.strftime("%Y-%m-%d")
    panel["underlying_symbol"] = panel["underlying_symbol"].astype(str).str.upper()
    panel["signal_rank"] = panel["signal_rank"].astype(str)
    for col in ["reached_plus_5pct_within_10_sessions", "breakout_day_low_breach_before_timeout", "timeout_10_sessions_under_threshold"]:
        panel[col] = panel[col].map(lambda x: x if isinstance(x, bool) else str(x).lower() == "true")
    lineage = load_json(baseline_run_dir / "source_input_lineage.json")
    entries = [entry for entry in lineage.get("inputs", []) if entry.get("required_for_signal_or_outcome")]
    if len(entries) != 1:
        raise SystemExit("baseline_lineage_invalid")
    input_root = REPO_ROOT / entries[0]["repository_relative_path_or_local_alias"]
    schedule = pd.read_csv(input_root / "sources" / "decision_schedule.csv")
    schedule["observation_date"] = pd.to_datetime(schedule["observation_date"]).dt.strftime("%Y-%m-%d")
    stats = {
        "total": int(len(panel)),
        "complete": int((panel["outcome_status"] == "complete").sum()),
        "collisions": int((panel["outcome_status"] == "ambiguous_intraday_order").sum()),
        "incomplete": int((panel["outcome_status"] == "incomplete_horizon").sum()),
    }
    return panel, schedule, stats


def session_index_map(schedule: pd.DataFrame) -> dict[str, int]:
    dates = sorted(schedule["observation_date"].dropna().unique())
    return {date: idx for idx, date in enumerate(dates)}


def map_date_to_session_index(date_str: str, session_map: dict[str, int]) -> int | None:
    eligible = [d for d in session_map if d <= date_str]
    if not eligible:
        return None
    return session_map[max(eligible)]


def select_prior_snapshot(skew_panel: pd.DataFrame, ticker: str, decision_date: str, decision_session_idx: int, session_map: dict[str, int], max_lag: int) -> dict[str, Any]:
    sub = skew_panel[(skew_panel["ticker"] == ticker) & (skew_panel["snapshot_date"] <= decision_date) & (skew_panel["skew_status"] == "valid")].sort_values("snapshot_date")
    if sub.empty:
        return {"skew_status": "unavailable_no_prior_snapshot"}
    for _, row in sub.iloc[::-1].iterrows():
        snap_idx = map_date_to_session_index(str(row["snapshot_date"]), session_map)
        if snap_idx is None:
            continue
        lag = decision_session_idx - snap_idx
        if lag < 0:
            continue
        if lag <= max_lag:
            out = row.to_dict()
            out["snapshot_lag_sessions"] = int(lag)
            return out
        return {"skew_status": "unavailable_snapshot_lag_exceeded", "snapshot_asof_date": row["snapshot_date"], "snapshot_lag_sessions": int(lag)}
    return {"skew_status": "unavailable_snapshot_lag_exceeded"}


def assign_tercile(value: Any, p33: Any, p67: Any) -> str:
    value = safe_float(value)
    p33 = safe_float(p33)
    p67 = safe_float(p67)
    if value is None or p33 is None or p67 is None:
        return "metric_unavailable"
    if value <= p33:
        return "low"
    if value >= p67:
        return "high"
    return "middle"


def build_context(baseline: pd.DataFrame, schedule: pd.DataFrame, skew_panel: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    session_map = session_index_map(schedule)
    max_lag = int(spec["maximum_snapshot_lag_sessions"])
    signal_rows = []
    index_rows = []
    for _, sig in baseline.iterrows():
        decision_date = sig["signal_decision_date"]
        dec_idx = map_date_to_session_index(decision_date, session_map)
        if dec_idx is None:
            continue
        qqq = select_prior_snapshot(skew_panel, "QQQ", decision_date, dec_idx, session_map, max_lag)
        single = select_prior_snapshot(skew_panel, sig["underlying_symbol"], decision_date, dec_idx, session_map, max_lag)
        base = {
            "signal_id": sig["signal_id"],
            "signal_decision_date": decision_date,
            "entry_session": sig["entry_session"],
            "underlying_symbol": sig["underlying_symbol"],
            "signal_rank": sig["signal_rank"],
            "theme": sig.get("theme", ""),
            "outcome_status": sig["outcome_status"],
            "outcome_complete_status": "complete" if sig["outcome_status"] == "complete" else sig["outcome_status"],
            "reached_plus_5pct_within_10_sessions": bool(sig["reached_plus_5pct_within_10_sessions"]),
            "breakout_day_low_breach_before_timeout": bool(sig["breakout_day_low_breach_before_timeout"]),
            "timeout_10_sessions_under_threshold": bool(sig["timeout_10_sessions_under_threshold"]),
        }
        qqq_valid = qqq.get("skew_status") == "valid"
        single_valid = single.get("skew_status") == "valid"
        for metric, source_col in {
            "qqq_put_skew_abs": "put_skew_abs",
            "qqq_put_skew_normalized": "put_skew_normalized",
            "qqq_put_skew_abs_5d_change": "put_skew_abs_5d_change",
            "qqq_put_skew_normalized_5d_change": "put_skew_normalized_5d_change",
        }.items():
            signal_rows.append({**base, "scope": "index", "metric": metric, "metric_value": qqq.get(source_col, pd.NA), "metric_state": "", "skew_status": qqq.get("skew_status"), "snapshot_asof_date": qqq.get("snapshot_date", qqq.get("snapshot_asof_date", "")), "snapshot_lag_sessions": qqq.get("snapshot_lag_sessions", ""), "snapshot_timing_quality": qqq.get("snapshot_timing_quality", ""), "quality_tier": qqq.get("quality_tier", "")})
        for metric, source_col in {
            "single_name_put_skew_abs": "put_skew_abs",
            "single_name_put_skew_normalized": "put_skew_normalized",
            "single_name_put_skew_abs_5d_change": "put_skew_abs_5d_change",
            "single_name_put_skew_normalized_5d_change": "put_skew_normalized_5d_change",
        }.items():
            signal_rows.append({**base, "scope": "single_name", "metric": metric, "metric_value": single.get(source_col, pd.NA), "metric_state": "", "skew_status": single.get("skew_status"), "snapshot_asof_date": single.get("snapshot_date", single.get("snapshot_asof_date", "")), "snapshot_lag_sessions": single.get("snapshot_lag_sessions", ""), "snapshot_timing_quality": single.get("snapshot_timing_quality", ""), "quality_tier": single.get("quality_tier", "")})
        same_date_pair = qqq_valid and single_valid and str(qqq.get("snapshot_date")) == str(single.get("snapshot_date"))
        rel_abs = rel_norm = pd.NA
        rel_status = "valid" if same_date_pair else "unavailable_no_same_date_pair"
        if same_date_pair:
            rel_norm = single.get("put_skew_normalized") - qqq.get("put_skew_normalized")
            rel_abs = single.get("put_skew_abs") - qqq.get("put_skew_abs")
        signal_rows.append({**base, "scope": "relative", "metric": "single_name_minus_qqq_normalized_skew", "metric_value": rel_norm, "metric_state": "", "skew_status": rel_status, "snapshot_asof_date": qqq.get("snapshot_date", ""), "snapshot_lag_sessions": qqq.get("snapshot_lag_sessions", ""), "snapshot_timing_quality": qqq.get("snapshot_timing_quality", ""), "quality_tier": "|".join(sorted({str(qqq.get("quality_tier", "")), str(single.get("quality_tier", ""))}))})
        signal_rows.append({**base, "scope": "relative", "metric": "single_name_minus_qqq_abs_skew", "metric_value": rel_abs, "metric_state": "", "skew_status": rel_status, "snapshot_asof_date": qqq.get("snapshot_date", ""), "snapshot_lag_sessions": qqq.get("snapshot_lag_sessions", ""), "snapshot_timing_quality": qqq.get("snapshot_timing_quality", ""), "quality_tier": "|".join(sorted({str(qqq.get("quality_tier", "")), str(single.get("quality_tier", ""))}))})
        if qqq_valid:
            index_rows.append({"signal_decision_date": decision_date, "snapshot_asof_date": qqq.get("snapshot_date"), **{m: qqq.get(m.replace("qqq_", "")) for m in []}})
    context = pd.DataFrame(signal_rows)
    cutoffs = assign_states(context, baseline)
    daily_index = build_daily_index_panel(context)
    return context, cutoffs, daily_index


def assign_states(context: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    rows = []
    context["metric_value"] = pd.to_numeric(context["metric_value"], errors="coerce")
    if "metric_state" not in context.columns:
        context["metric_state"] = ""
    context["metric_state"] = context["metric_state"].astype("object")
    complete_dates = set(baseline.loc[baseline["outcome_status"] == "complete", "signal_decision_date"])
    for metric in INDEX_METRICS:
        mask = (context["scope"] == "index") & (context["metric"] == metric) & (context["signal_decision_date"].isin(complete_dates))
        values = context.loc[mask].drop_duplicates("signal_decision_date")["metric_value"].dropna()
        p33 = values.quantile(1 / 3) if not values.empty else pd.NA
        p67 = values.quantile(2 / 3) if not values.empty else pd.NA
        context.loc[context["metric"] == metric, "metric_state"] = context.loc[context["metric"] == metric, "metric_value"].map(lambda v: assign_tercile(v, p33, p67))
        rows.append({"scope": "index", "metric": metric, "p33": p33, "p67": p67, "valid_cutoff_observation_count": int(len(values)), "state_construction": "unique_complete_signal_decision_dates_p33_p67"})
    for scope, metrics in [("single_name", SINGLE_METRICS), ("relative", RELATIVE_METRICS)]:
        for metric in metrics:
            mask = (context["scope"] == scope) & (context["metric"] == metric) & (context["outcome_status"] == "complete")
            values = context.loc[mask, "metric_value"].dropna()
            p33 = values.quantile(1 / 3) if not values.empty else pd.NA
            p67 = values.quantile(2 / 3) if not values.empty else pd.NA
            context.loc[(context["scope"] == scope) & (context["metric"] == metric), "metric_state"] = context.loc[(context["scope"] == scope) & (context["metric"] == metric), "metric_value"].map(lambda v: assign_tercile(v, p33, p67))
            rows.append({"scope": scope, "metric": metric, "p33": p33, "p67": p67, "valid_cutoff_observation_count": int(len(values)), "state_construction": "complete_signal_rows_p33_p67"})
    return pd.DataFrame(rows)


def build_daily_index_panel(context: pd.DataFrame) -> pd.DataFrame:
    qqq = context[context["scope"] == "index"].copy()
    if qqq.empty:
        return pd.DataFrame(columns=["signal_decision_date"])
    rows = []
    for date, group in qqq.groupby("signal_decision_date"):
        row = {"signal_decision_date": date}
        for _, rec in group.drop_duplicates("metric").iterrows():
            row[rec["metric"]] = rec["metric_value"]
            row[f"{rec['metric']}_state"] = rec["metric_state"]
            row["snapshot_asof_date"] = rec["snapshot_asof_date"]
            row["snapshot_lag_sessions"] = rec["snapshot_lag_sessions"]
            row["snapshot_timing_quality"] = rec["snapshot_timing_quality"]
            row["skew_status"] = rec["skew_status"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("signal_decision_date")


def bool_rate(series: pd.Series) -> float | None:
    if len(series) == 0:
        return None
    return float(series.astype(bool).mean())


def quality_mix(data: pd.DataFrame) -> str:
    if data.empty:
        return ""
    counts = data["quality_tier"].fillna("").replace("", "unknown").value_counts().to_dict()
    return "|".join(f"{k}:{v}" for k, v in sorted(counts.items()))


def largest_ticker_share(data: pd.DataFrame) -> tuple[float | None, str]:
    complete = data[data["outcome_status"] == "complete"]
    if complete.empty:
        return None, ""
    counts = complete["underlying_symbol"].value_counts()
    return float(counts.iloc[0] / len(complete)), str(counts.index[0])


def build_outcome_summary(context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in context.groupby(["scope", "metric", "metric_state"], dropna=False):
        scope, metric, state = keys
        for rank in ["S", "A", "B", "ALL"]:
            data = group if rank == "ALL" else group[group["signal_rank"] == rank]
            complete = data[data["outcome_status"] == "complete"]
            share, ticker = largest_ticker_share(data)
            rows.append(
                {
                    "scope": scope,
                    "metric": metric,
                    "metric_state": state,
                    "rank": rank,
                    "complete_signal_count": int(len(complete)),
                    "diagnostic_total_signal_count": int(len(data)),
                    "collision_signal_count": int((data["outcome_status"] == "ambiguous_intraday_order").sum()),
                    "incomplete_signal_count": int((data["outcome_status"] == "incomplete_horizon").sum()),
                    "plus5_success_rate": bool_rate(complete["reached_plus_5pct_within_10_sessions"]) if not complete.empty else None,
                    "breakout_low_breach_rate": bool_rate(complete["breakout_day_low_breach_before_timeout"]) if not complete.empty else None,
                    "timeout_rate": bool_rate(complete["timeout_10_sessions_under_threshold"]) if not complete.empty else None,
                    "largest_single_ticker_share": share,
                    "largest_single_ticker": ticker,
                    "quality_tier_mix": quality_mix(complete),
                }
            )
    return pd.DataFrame(rows)


def direction(row: pd.Series) -> str:
    plus5 = safe_float(row.get("plus5_success_rate_diff_pp"))
    breach = safe_float(row.get("breakout_low_breach_rate_diff_pp"))
    if plus5 is not None and plus5 >= 10:
        return "higher"
    if breach is not None and breach <= -10:
        return "higher"
    if plus5 is not None and plus5 <= -10:
        return "lower"
    if breach is not None and breach >= 10:
        return "lower"
    return "mixed"


def layer_statuses(context: pd.DataFrame, baseline: pd.DataFrame, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    complete = baseline[baseline["outcome_status"] == "complete"]
    unique_dates = set(complete["signal_decision_date"])
    qqq_valid_dates = set(context[(context["scope"] == "index") & (context["metric"] == "qqq_put_skew_normalized") & (context["outcome_status"] == "complete") & (context["metric_value"].notna())]["signal_decision_date"])
    qqq_ratio = len(qqq_valid_dates) / len(unique_dates) if unique_dates else 0
    single_rows = int(len(context[(context["scope"] == "single_name") & (context["metric"] == "single_name_put_skew_normalized") & (context["outcome_status"] == "complete") & (context["metric_value"].notna())]))
    rel_rows = int(len(context[(context["scope"] == "relative") & (context["metric"] == "single_name_minus_qqq_normalized_skew") & (context["outcome_status"] == "complete") & (context["metric_value"].notna())]))
    return {
        "index": {"status": "available" if qqq_ratio >= float(spec["index_coverage_min_unique_complete_signal_dates"]) else "insufficient_snapshot_coverage", "valid_unique_complete_signal_dates": len(qqq_valid_dates), "total_unique_complete_signal_dates": len(unique_dates), "coverage_ratio": qqq_ratio},
        "single_name": {"status": "available" if single_rows >= int(spec["single_name_min_complete_signal_rows"]) else "insufficient_snapshot_coverage", "valid_complete_signal_rows": single_rows, "required_complete_signal_rows": int(spec["single_name_min_complete_signal_rows"])},
        "relative": {"status": "available" if rel_rows >= int(spec["relative_min_complete_signal_rows"]) else "insufficient_snapshot_coverage", "valid_complete_signal_rows": rel_rows, "required_complete_signal_rows": int(spec["relative_min_complete_signal_rows"])},
    }


def build_rank_summary(context: pd.DataFrame, layer_status: dict[str, dict[str, Any]], spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    min_n = int(spec["minimum_complete_signals_per_state"])
    conc_max = float(spec["concentration_guard_largest_ticker_share_max"])
    for keys, group in context.groupby(["scope", "metric"], dropna=False):
        scope, metric = keys
        layer = scope
        for rank in ["S", "A", "B", "ALL"]:
            data = group if rank == "ALL" else group[group["signal_rank"] == rank]
            high = data[data["metric_state"] == "high"]
            low = data[data["metric_state"] == "low"]
            high_c = high[high["outcome_status"] == "complete"]
            low_c = low[low["outcome_status"] == "complete"]
            high_share, high_ticker = largest_ticker_share(high)
            low_share, low_ticker = largest_ticker_share(low)
            high_plus = bool_rate(high_c["reached_plus_5pct_within_10_sessions"]) if not high_c.empty else None
            low_plus = bool_rate(low_c["reached_plus_5pct_within_10_sessions"]) if not low_c.empty else None
            high_breach = bool_rate(high_c["breakout_day_low_breach_before_timeout"]) if not high_c.empty else None
            low_breach = bool_rate(low_c["breakout_day_low_breach_before_timeout"]) if not low_c.empty else None
            high_timeout = bool_rate(high_c["timeout_10_sessions_under_threshold"]) if not high_c.empty else None
            low_timeout = bool_rate(low_c["timeout_10_sessions_under_threshold"]) if not low_c.empty else None
            plus_diff = None if high_plus is None or low_plus is None else (high_plus - low_plus) * 100
            breach_diff = None if high_breach is None or low_breach is None else (high_breach - low_breach) * 100
            timeout_diff = None if high_timeout is None or low_timeout is None else (high_timeout - low_timeout) * 100
            comparison_status = "sufficient_sample" if len(high_c) >= min_n and len(low_c) >= min_n else "insufficient_sample"
            if layer_status.get(layer, {}).get("status") != "available":
                label = "insufficient_snapshot_coverage"
            else:
                conc_breach = any(s is not None and s > conc_max for s in [high_share, low_share])
                material = (plus_diff is not None and abs(plus_diff) >= 10) or (breach_diff is not None and abs(breach_diff) >= 10)
                timeout_contradicts = timeout_diff is not None and abs(timeout_diff) >= 10 and material
                if comparison_status == "insufficient_sample":
                    label = "insufficient_sample"
                elif conc_breach or timeout_contradicts:
                    label = "inconsistent_relationship"
                elif material:
                    label = "potentially_material_relationship"
                else:
                    label = "no_visible_relationship"
            row = {
                "scope": scope,
                "metric": metric,
                "rank": rank,
                "high_complete_signal_count": int(len(high_c)),
                "low_complete_signal_count": int(len(low_c)),
                "plus5_success_rate_diff_pp": plus_diff,
                "breakout_low_breach_rate_diff_pp": breach_diff,
                "timeout_rate_diff_pp": timeout_diff,
                "largest_single_ticker_share_high": high_share,
                "largest_single_ticker_high": high_ticker,
                "largest_single_ticker_share_low": low_share,
                "largest_single_ticker_low": low_ticker,
                "quality_tier_mix_high": quality_mix(high_c),
                "quality_tier_mix_low": quality_mix(low_c),
                "comparison_status": comparison_status,
                "layer_coverage_status": layer_status.get(layer, {}).get("status", "unknown"),
                "relationship_direction": "",
                "relationship_label": label,
            }
            row["relationship_direction"] = direction(pd.Series(row))
            rows.append(row)
    summary = pd.DataFrame(rows)
    return apply_cross_metric_inconsistency(summary)


def apply_cross_metric_inconsistency(summary: pd.DataFrame) -> pd.DataFrame:
    summary = summary.copy()
    for (scope, rank), group in summary[(summary["rank"].isin(["S", "A", "B"])) & (summary["layer_coverage_status"] == "available")].groupby(["scope", "rank"]):
        directions = set(group.loc[group["comparison_status"] == "sufficient_sample", "relationship_direction"]) - {"mixed"}
        if "higher" in directions and "lower" in directions:
            mask = (summary["scope"] == scope) & (summary["rank"] == rank) & (summary["comparison_status"] == "sufficient_sample")
            summary.loc[mask, "relationship_label"] = "inconsistent_relationship"
    return summary


def build_joint_summary(context: pd.DataFrame) -> pd.DataFrame:
    pivot = context.pivot_table(index="signal_id", columns="metric", values="metric_state", aggfunc="first").reset_index()
    base = context.drop_duplicates("signal_id")
    merged = base.merge(pivot, on="signal_id", how="left")
    rows = []
    q_metric = "qqq_put_skew_normalized"
    r_metric = "single_name_minus_qqq_normalized_skew"
    if q_metric not in merged or r_metric not in merged:
        return pd.DataFrame()
    merged["joint_state"] = merged.apply(lambda r: f"QQQ {'high' if r.get(q_metric) == 'high' else 'not_high'} x relative {'high' if r.get(r_metric) == 'high' else 'not_high'}", axis=1)
    for (rank, state), data in merged.groupby(["signal_rank", "joint_state"]):
        complete = data[data["outcome_status"] == "complete"]
        rows.append({"rank": rank, "joint_state": state, "complete_signal_count": len(complete), "cell_status": "sufficient_sample" if len(complete) >= 15 else "insufficient_sample", "plus5_success_rate": bool_rate(complete["reached_plus_5pct_within_10_sessions"]) if not complete.empty else None, "breakout_low_breach_rate": bool_rate(complete["breakout_day_low_breach_before_timeout"]) if not complete.empty else None, "timeout_rate": bool_rate(complete["timeout_10_sessions_under_threshold"]) if not complete.empty else None})
    return pd.DataFrame(rows)


def build_quality_summary(context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    valid = context[context["metric_value"].notna()]
    for keys, group in valid.groupby(["scope", "metric", "quality_tier"], dropna=False):
        scope, metric, tier = keys
        rows.append({"scope": scope, "metric": metric, "quality_tier": tier, "signal_context_rows": len(group), "complete_signal_rows": int((group["outcome_status"] == "complete").sum())})
    return pd.DataFrame(rows)


def index_vs_individual(rank_summary: pd.DataFrame, layer_status: dict[str, dict[str, Any]]) -> dict[str, str]:
    result = {}
    for rank in ["S", "A", "B"]:
        if layer_status["index"]["status"] != "available" or layer_status["single_name"]["status"] != "available":
            result[rank] = "insufficient_coverage"
            continue
        rank_rows = rank_summary[rank_summary["rank"] == rank]
        idx_material = (rank_rows[(rank_rows["scope"] == "index")]["relationship_label"] == "potentially_material_relationship").sum()
        single_material = (rank_rows[(rank_rows["scope"] == "single_name")]["relationship_label"] == "potentially_material_relationship").sum()
        if single_material > idx_material:
            result[rank] = "individual_skew_more_informative"
        elif idx_material > single_material:
            result[rank] = "index_skew_more_informative"
        else:
            result[rank] = "neither_clear"
    return result


def summarize_source(options: pd.DataFrame, source_root: Path | None, availability: pd.DataFrame) -> pd.DataFrame:
    if options.empty:
        return availability
    rows = []
    for ticker, group in options.groupby("ticker"):
        rows.append({"selected_source_root": repo_relative(source_root) if source_root else "", "ticker": ticker, "row_count": len(group), "min_snapshot_date": group["snapshot_date"].min(), "max_snapshot_date": group["snapshot_date"].max(), "expiration_count": group["expiration"].nunique(), "has_iv": True, "has_bid_ask": {"bid", "ask"}.issubset(group.columns), "has_open_interest": "oi" in group.columns, "has_spot": "spot" in group.columns})
    return pd.DataFrame(rows)


def build_summary_md(receipt: dict[str, Any], rank_summary: pd.DataFrame, coverage: pd.DataFrame, source_summary: pd.DataFrame) -> str:
    lines = [
        "# Morita Put-Skew Quick Screen v1",
        "",
        f"Status: `{receipt['status']}`",
        f"Baseline run: `{receipt['baseline_run_id']}`",
        f"Baseline coverage: total `{receipt['baseline_total_rows']}`, complete `{receipt['baseline_complete_rows']}`, collisions `{receipt['baseline_collision_rows']}`, incomplete `{receipt['baseline_incomplete_rows']}`",
        "",
        "## Local Snapshot Availability",
        "",
    ]
    if source_summary.empty:
        lines.append("No suitable local option snapshot source was found.")
    else:
        for _, row in source_summary.head(20).iterrows():
            lines.append(f"- `{row.get('ticker','')}`: `{row.get('min_snapshot_date','')}` to `{row.get('max_snapshot_date','')}`, rows `{row.get('row_count','')}`")
    lines.extend(["", "## Layer Coverage"])
    for layer, info in receipt["layer_status"].items():
        lines.append(f"- `{layer}`: `{info['status']}` {info}")
    lines.extend(["", "## Rank Labels"])
    for _, row in rank_summary[rank_summary["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank", "metric"]).iterrows():
        lines.append(f"- `{row['scope']}` rank `{row['rank']}` metric `{row['metric']}`: label `{row['relationship_label']}`, +5 diff `{fmt(row['plus5_success_rate_diff_pp'])}pp`, breach diff `{fmt(row['breakout_low_breach_rate_diff_pp'])}pp`, timeout diff `{fmt(row['timeout_rate_diff_pp'])}pp`")
    lines.extend(["", "## Index vs Individual", ""])
    for rank, value in receipt["index_vs_individual_comparison"].items():
        lines.append(f"- rank `{rank}`: `{value}`")
    decision = "freeze_skew_move_to_dispersion_implied_correlation"
    if any(v in {"individual_skew_more_informative", "index_skew_more_informative"} for v in receipt["index_vs_individual_comparison"].values()):
        decision = "candidate_for_deeper_put_skew_validation"
    lines.extend(["", "## Triage Decision", "", f"`{decision}`", "", "Research only. No external options data, no Bot change, no option PnL, no dealer model, no actionization."])
    return "\n".join(lines) + "\n"


def write_bundle(output_dir: Path, summary_md: str, receipt: dict[str, Any], rank_summary: pd.DataFrame) -> None:
    lines = [
        "# ChatGPT Handoff: Morita Put-Skew Quick Screen v1",
        "",
        "## Objective",
        "",
        "Compare whether local-archive put skew is more informative at QQQ index, individual underlying, or individual-minus-QQQ relative level.",
        "",
        "## Status",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Baseline run: `{receipt['baseline_run_id']}`",
        f"- Selected local archive: `{receipt.get('selected_source_root','')}`",
        "",
        "## Coverage",
        "",
    ]
    for layer, info in receipt["layer_status"].items():
        lines.append(f"- `{layer}`: `{info['status']}` {info}")
    lines.extend(["", "## High-vs-Low Differences", "", "| Scope | Rank | Metric | High N | Low N | +5 Diff pp | Breach Diff pp | Timeout Diff pp | Label |", "|---|---:|---|---:|---:|---:|---:|---:|---|"])
    for _, row in rank_summary[rank_summary["rank"].isin(["S", "A", "B"])].sort_values(["scope", "rank", "metric"]).iterrows():
        lines.append(f"| {row['scope']} | {row['rank']} | {row['metric']} | {row['high_complete_signal_count']} | {row['low_complete_signal_count']} | {fmt(row['plus5_success_rate_diff_pp'])} | {fmt(row['breakout_low_breach_rate_diff_pp'])} | {fmt(row['timeout_rate_diff_pp'])} | {row['relationship_label']} |")
    lines.extend(["", "## Index vs Individual", ""])
    for rank, value in receipt["index_vs_individual_comparison"].items():
        lines.append(f"- rank `{rank}`: `{value}`")
    lines.extend(["", "## Limitations", "", "- No raw option chain rows included.", "- No raw signal rows included.", "- No raw contract IV rows included.", "- No external options data.", "- No trade recommendation.", "", "## Embedded Summary", "", summary_md])
    CHATGPT_BUNDLE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_run(baseline_run_dir: Path, output_dir: Path) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    availability = inspect_local_snapshot_archive()
    source_root = select_archive_source(availability)
    baseline, schedule, stats = load_baseline(baseline_run_dir)
    options, file_inventory = (pd.DataFrame(), pd.DataFrame())
    if source_root is not None:
        options, file_inventory = load_option_archive(source_root)
    if source_root is None or options.empty:
        safe_clean_output_dir(output_dir)
        for name in REQUIRED_OUTPUTS:
            if name.endswith(".csv"):
                write_dataframe(output_dir / name, pd.DataFrame())
        receipt = {"status": "morita_put_skew_quick_screen_local_snapshot_archive_missing", "created_at_utc": iso_now(), "baseline_run_id": baseline_run_dir.name, "layer_status": {"index": {"status": "insufficient_snapshot_coverage"}, "single_name": {"status": "insufficient_snapshot_coverage"}, "relative": {"status": "insufficient_snapshot_coverage"}}, "index_vs_individual_comparison": {"S": "insufficient_coverage", "A": "insufficient_coverage", "B": "insufficient_coverage"}}
        write_json(output_dir / "skew_receipt.json", receipt)
        (output_dir / "skew_summary.md").write_text("# Morita Put-Skew Quick Screen v1\n\nNo suitable local option snapshot archive found.\n", encoding="utf-8")
        build_manifest(output_dir)
        return {"status": receipt["status"], "output_dir": repo_relative(output_dir)}
    skew_panel = build_skew_panel(options, spec)
    context, cutoffs, daily_index = build_context(baseline, schedule, skew_panel, spec)
    layer_status = layer_statuses(context, baseline, spec)
    outcome_summary = build_outcome_summary(context)
    rank_summary = build_rank_summary(context, layer_status, spec)
    joint_summary = build_joint_summary(context)
    quality_summary = build_quality_summary(context)
    source_summary = summarize_source(options, source_root, availability)
    coverage_rows = []
    for layer, info in layer_status.items():
        coverage_rows.append({"layer": layer, **info})
    coverage = pd.DataFrame(coverage_rows)
    comparison = index_vs_individual(rank_summary, layer_status)
    safe_clean_output_dir(output_dir)
    write_dataframe(output_dir / "skew_source_availability.csv", source_summary)
    write_dataframe(output_dir / "skew_snapshot_coverage.csv", coverage)
    write_dataframe(output_dir / "skew_daily_index_panel.csv", daily_index)
    write_dataframe(output_dir / "skew_signal_context_panel.csv", context)
    write_dataframe(output_dir / "skew_state_cutoffs.csv", cutoffs)
    write_dataframe(output_dir / "skew_outcome_summary.csv", outcome_summary)
    write_dataframe(output_dir / "skew_rank_summary.csv", rank_summary)
    write_dataframe(output_dir / "skew_joint_index_single_name_summary.csv", joint_summary)
    write_dataframe(output_dir / "skew_quality_tier_summary.csv", quality_summary)
    receipt = {
        "artifact_version": "morita_put_skew_quick_screen_v1",
        "status": "morita_put_skew_quick_screen_completed",
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "baseline_run_id": baseline_run_dir.name,
        "baseline_run_dir": repo_relative(baseline_run_dir),
        "baseline_source_content_manifest_sha256": file_sha256(baseline_run_dir / "source_content_manifest.json"),
        "baseline_total_rows": stats["total"],
        "baseline_complete_rows": stats["complete"],
        "baseline_collision_rows": stats["collisions"],
        "baseline_incomplete_rows": stats["incomplete"],
        "selected_source_root": repo_relative(source_root),
        "selected_source_file_count": int(len(file_inventory)),
        "selected_source_tickers": sorted(options["ticker"].dropna().unique().tolist()),
        "layer_status": layer_status,
        "index_vs_individual_comparison": comparison,
        "no_external_options_data": True,
        "bot_rerun_or_rule_change": False,
        "option_pnl_performed": False,
        "parameter_optimization_performed": False,
        "dealer_model_performed": False,
        "actionization_allowed": False,
    }
    write_json(output_dir / "skew_receipt.json", receipt)
    summary_md = build_summary_md(receipt, rank_summary, coverage, source_summary)
    (output_dir / "skew_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir)
    verify_manifest(output_dir, MANIFEST_NAME)
    write_bundle(output_dir, summary_md, receipt, rank_summary)
    return {"status": receipt["status"], "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "chatgpt_bundle": repo_relative(CHATGPT_BUNDLE)}


def verify_run(output_dir: Path) -> dict[str, Any]:
    manifest = verify_manifest(output_dir, MANIFEST_NAME)
    files = {entry["relative_path"] for entry in manifest.get("files", [])}
    missing = sorted(set(REQUIRED_OUTPUTS) - files)
    if missing:
        raise SystemExit(f"skew_manifest_missing_required_output:{missing[0]}")
    return {"status": "morita_put_skew_quick_screen_verified", "output_dir": repo_relative(output_dir), "manifest_hash": file_sha256(output_dir / MANIFEST_NAME), "file_count": len(files)}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect-local-snapshot-archive", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline-run-dir")
    parser.add_argument("--output-dir")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.inspect_local_snapshot_archive:
        print(inspect_local_snapshot_archive().to_json(orient="records", indent=2))
        return 0
    if not args.output_dir:
        raise SystemExit("--output-dir is required")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    if args.verify:
        print(json_dumps(verify_run(output_dir)))
        return 0
    if not args.baseline_run_dir:
        raise SystemExit("--baseline-run-dir is required with --run")
    baseline_run_dir = Path(args.baseline_run_dir)
    if not baseline_run_dir.is_absolute():
        baseline_run_dir = REPO_ROOT / baseline_run_dir
    print(json_dumps(build_run(baseline_run_dir, output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
