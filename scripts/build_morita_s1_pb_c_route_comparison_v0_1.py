from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.morita_single_call_reference import s_single_call_reference_engine as ref

OUT = REPO_ROOT / "outputs" / "morita_s1_pb_c_route_comparison_v0_1"
BUNDLE = REPO_ROOT / "morita_s1_pb_c_route_comparison_v0_1_bundle.md"
SPEC_PATH = REPO_ROOT / "config" / "morita_s1_pb_c_route_comparison_v0_1" / "route_comparison_spec.json"
CANDIDATE_LAYER_DIR = REPO_ROOT / "outputs" / "morita_s1_ab_candidate_layer_v0_1"
BASELINE_DIR = (
    REPO_ROOT
    / "market_bomb_history"
    / "morita_bot_historical_baseline_v1"
    / "historical_runs"
    / "morita_baseline_20260703T123912Z_4994e3744ffa"
)

REQUIRED_FILES = [
    "source_verification.csv",
    "raw_signal_cluster_proxy.csv",
    "route_candidate_calendar.csv",
    "route_underlying_outcomes.csv",
    "route_underlying_summary.csv",
    "route_fixed_iv_reference_summary.csv",
    "route_subperiod_stability.csv",
    "route_bias_and_dependency_notes.md",
    "route_comparison_receipt.json",
    "route_comparison_content_manifest.json",
    "route_comparison_summary.md",
]

ELIGIBLE_ROUTE_STATES = {"S1_CLUSTER_FIRST", "PB_FIRST_PARENTED", "C_FIRST_CONTINUATION"}
FORBIDDEN_OUTPUT_TOKENS = [
    "BUY_NOW",
    "SELL_NOW",
    "WEBULL",
    "PUSHOVER",
    "PORTFOLIO_DD",
    "SIZE_UP",
    "SIZE_DOWN",
    "NLR_OVERLAY",
    "MECHANICAL_FLOW_GATE",
]


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
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def profit_factor(values: list[float]) -> float | str:
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return "not_estimable_zero_gross_loss" if gains > 0 else ""
    return gains / losses


def source_identity_rows() -> list[dict[str, Any]]:
    paths = {
        "candidate_layer_raw_s": CANDIDATE_LAYER_DIR / "raw_s_to_s1_state.csv",
        "candidate_layer_raw_ab": CANDIDATE_LAYER_DIR / "raw_ab_to_parented_ab_state.csv",
        "candidate_layer_s1_summary": CANDIDATE_LAYER_DIR / "s1_vs_extended_summary.csv",
        "formal_baseline_panel": BASELINE_DIR / "morita_bot_baseline_panel.csv",
        "formal_baseline_receipt": BASELINE_DIR / "baseline_receipt.json",
        "route_comparison_spec": SPEC_PATH,
    }
    rows = []
    for component, path in paths.items():
        rows.append(
            {
                "component": component,
                "path": repo_relative(path),
                "exists": path.exists(),
                "sha256": sha256_file(path) if path.exists() else "",
                "status": "verified" if path.exists() else "missing",
            }
        )
    return rows


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


def load_baseline_event_map() -> dict[str, dict[str, Any]]:
    panel = pd.read_csv(BASELINE_DIR / "morita_bot_baseline_panel.csv", dtype={"signal_id": str}).fillna("")
    panel["ticker"] = panel["underlying_symbol"].astype(str).str.upper()
    panel["signal_date"] = panel["signal_decision_date"].map(norm_date)
    panel["entry_date"] = panel["entry_session"].map(norm_date)
    return {str(row["signal_id"]): row.to_dict() for _, row in panel.iterrows()}


def load_candidate_layer() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_s_path = CANDIDATE_LAYER_DIR / "raw_s_to_s1_state.csv"
    raw_ab_path = CANDIDATE_LAYER_DIR / "raw_ab_to_parented_ab_state.csv"
    if not raw_s_path.exists():
        raise FileNotFoundError(f"missing_candidate_layer_raw_s:{raw_s_path}")
    if not raw_ab_path.exists():
        raise FileNotFoundError(f"missing_candidate_layer_raw_ab:{raw_ab_path}")
    raw_s = pd.read_csv(raw_s_path, dtype=str).fillna("")
    raw_ab = pd.read_csv(raw_ab_path, dtype=str).fillna("")
    return raw_s, raw_ab


def build_cluster_proxy(raw_s: pd.DataFrame, session_pos: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker, group in raw_s.sort_values(["ticker", "entry_session", "raw_s_event_id"]).groupby("ticker"):
        cluster_idx = 0
        active_cluster_id = ""
        prior_entry = ""
        for _, row in group.iterrows():
            gap = session_gap(session_pos, prior_entry, row["entry_session"]) if prior_entry else None
            if not prior_entry or gap is None or gap > 20:
                cluster_idx += 1
                active_cluster_id = f"{ticker}_cluster_proxy_{cluster_idx:03d}"
                status = "NEW_CLUSTER_PROXY"
            else:
                status = "CONTINUATION_OF_ACTIVE_CLUSTER"
            rows.append(
                {
                    "cluster_proxy_id": active_cluster_id,
                    "ticker": ticker,
                    "raw_s_event_id": row["raw_s_event_id"],
                    "signal_date": row["signal_decision_date"],
                    "entry_date": row["entry_session"],
                    "prior_raw_s_gap_eligible_sessions": "" if gap is None else gap,
                    "cluster_proxy_status": status,
                }
            )
            prior_entry = row["entry_session"]
    return rows


def enrich_event(event_id: str, event_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return event_map.get(event_id, {})


def route_row(
    *,
    cluster: dict[str, Any],
    route: str,
    state: str,
    source_event_id: str,
    parent_s1_event_id: str,
    signal_date: str,
    entry_date: str,
    gap: Any,
    rank: str,
    score: Any,
    accum: Any,
    coverage: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "cluster_proxy_id": cluster["cluster_proxy_id"],
        "ticker": cluster["ticker"],
        "route": route,
        "route_state": state,
        "raw_source_event_id": source_event_id,
        "parent_s1_event_id": parent_s1_event_id,
        "signal_date": signal_date,
        "entry_date": entry_date,
        "eligible_sessions_since_s1": gap,
        "rank_or_raw_label": rank,
        "production_adjusted_score_if_available": score,
        "accumulation_score_if_available": accum,
        "source_data_coverage_status": coverage,
        "exclusion_reason": reason,
    }


def build_route_calendar(
    cluster_rows: list[dict[str, Any]],
    raw_ab: pd.DataFrame,
    event_map: dict[str, dict[str, Any]],
    session_pos: dict[str, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    clusters: dict[str, list[dict[str, Any]]] = {}
    for row in cluster_rows:
        clusters.setdefault(row["cluster_proxy_id"], []).append(row)
    ab_by_ticker = {ticker: group.sort_values(["entry_session", "raw_ab_event_id"]).reset_index(drop=True) for ticker, group in raw_ab.groupby("ticker")}

    for cluster_id in sorted(clusters):
        members = sorted(clusters[cluster_id], key=lambda r: (r["entry_date"], r["raw_s_event_id"]))
        s1 = members[0]
        s1_event = enrich_event(s1["raw_s_event_id"], event_map)
        rows.append(
            route_row(
                cluster=s1,
                route="S1",
                state="S1_CLUSTER_FIRST",
                source_event_id=s1["raw_s_event_id"],
                parent_s1_event_id=s1["raw_s_event_id"],
                signal_date=s1["signal_date"],
                entry_date=s1["entry_date"],
                gap=0,
                rank="S",
                score=s1_event.get("production_adjusted_score", ""),
                accum=s1_event.get("accumulation_score", ""),
                coverage="raw_s_verified_candidate_layer_v0_1",
                reason="",
            )
        )

        c_used = False
        for cont in members[1:]:
            event = enrich_event(cont["raw_s_event_id"], event_map)
            gap = session_gap(session_pos, s1["entry_date"], cont["entry_date"])
            state = "C_FIRST_CONTINUATION" if not c_used else "C_LATER_CONTINUATION_EXCLUDED"
            rows.append(
                route_row(
                    cluster=s1,
                    route="C",
                    state=state,
                    source_event_id=cont["raw_s_event_id"],
                    parent_s1_event_id=s1["raw_s_event_id"],
                    signal_date=cont["signal_date"],
                    entry_date=cont["entry_date"],
                    gap="" if gap is None else gap,
                    rank="S_CONTINUATION",
                    score=event.get("production_adjusted_score", ""),
                    accum=event.get("accumulation_score", ""),
                    coverage="raw_s_verified_candidate_layer_v0_1",
                    reason="" if not c_used else "later_same_cluster_continuation_excluded",
                )
            )
            c_used = True

        pb_used = False
        pb_seen = False
        for _, ab in ab_by_ticker.get(s1["ticker"], pd.DataFrame()).iterrows():
            gap = session_gap(session_pos, s1["entry_date"], ab["entry_session"])
            if gap is None or gap < 1 or gap > 20:
                continue
            pb_seen = True
            accum = safe_float(ab.get("accumulation_score"))
            event = enrich_event(ab["raw_ab_event_id"], event_map)
            if accum is None or accum < 50:
                state = "PB_ACCUMULATION_BELOW_50"
                reason = "accumulation_score_below_50"
            elif pb_used:
                state = "PB_LATER_CANDIDATE_EXCLUDED"
                reason = "first_qualifying_pb_already_selected_for_cluster"
            else:
                state = "PB_FIRST_PARENTED"
                reason = ""
                pb_used = True
            rows.append(
                route_row(
                    cluster=s1,
                    route="PB",
                    state=state,
                    source_event_id=ab["raw_ab_event_id"],
                    parent_s1_event_id=s1["raw_s_event_id"],
                    signal_date=ab["signal_decision_date"],
                    entry_date=ab["entry_session"],
                    gap=gap,
                    rank=ab.get("raw_rank", ""),
                    score=event.get("production_adjusted_score", ""),
                    accum=ab.get("accumulation_score", ""),
                    coverage="raw_ab_verified_candidate_layer_v0_1",
                    reason=reason,
                )
            )
        if not pb_seen or not pb_used:
            rows.append(
                route_row(
                    cluster=s1,
                    route="PB",
                    state="PB_NO_QUALIFYING_PARENTED_AB" if not pb_used else "PB_NO_ADDITIONAL_PARENTED_AB",
                    source_event_id="",
                    parent_s1_event_id=s1["raw_s_event_id"],
                    signal_date="",
                    entry_date="",
                    gap="",
                    rank="A_OR_B",
                    score="",
                    accum="",
                    coverage="raw_ab_verified_candidate_layer_v0_1",
                    reason="no_raw_ab_within_1_to_20_sessions_with_accumulation_ge50" if not pb_used else "",
                )
            )
    return rows


def load_ohlcv_subset(tickers: set[str]) -> dict[str, pd.DataFrame]:
    source = baseline_input_root() / "sources" / "daily_ohlcv_merged.csv"
    chunks = []
    usecols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    for chunk in pd.read_csv(source, usecols=usecols, chunksize=250_000):
        chunk["ticker"] = chunk["ticker"].astype(str).str.upper()
        chunk = chunk[chunk["ticker"].isin(tickers)].copy()
        if not chunk.empty:
            chunks.append(chunk)
    if not chunks:
        return {}
    raw = pd.concat(chunks, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["date"])
    return {ticker: group.sort_values("date").reset_index(drop=True) for ticker, group in raw.groupby("ticker")}


def outcome_for_route(row: dict[str, Any], event_map: dict[str, dict[str, Any]], histories: dict[str, pd.DataFrame]) -> dict[str, Any]:
    out = dict(row)
    out.update(
        {
            "underlying_return_5_sessions": "",
            "underlying_return_10_sessions": "",
            "underlying_return_20_sessions": "",
            "plus_5pct_within_10_sessions": "",
            "plus_10pct_within_20_sessions": "",
            "MAE_10_sessions": "",
            "MAE_20_sessions": "",
            "MFE_10_sessions": "",
            "MFE_20_sessions": "",
            "outcome_status": "excluded_non_primary_route_state",
        }
    )
    if row["route_state"] not in ELIGIBLE_ROUTE_STATES:
        return out
    hist = histories.get(row["ticker"])
    if hist is None or hist.empty or not row["entry_date"]:
        out["outcome_status"] = "missing_ohlcv"
        return out
    idxs = hist.index[hist["date"] == pd.Timestamp(row["entry_date"])].tolist()
    if not idxs:
        out["outcome_status"] = "missing_entry_session_ohlcv"
        return out
    idx = idxs[0]
    if idx + 20 >= len(hist):
        out["outcome_status"] = "insufficient_forward_20_sessions"
        return out
    entry_close = safe_float(hist.loc[idx, "close"])
    if entry_close is None or entry_close <= 0:
        out["outcome_status"] = "bad_entry_close"
        return out
    for horizon in [5, 10, 20]:
        close = safe_float(hist.loc[idx + horizon, "close"])
        if close is not None:
            out[f"underlying_return_{horizon}_sessions"] = (close / entry_close) - 1.0
    for horizon in [10, 20]:
        path = hist.iloc[idx : idx + horizon + 1]
        out[f"MAE_{horizon}_sessions"] = (float(path["low"].min()) / entry_close) - 1.0
        out[f"MFE_{horizon}_sessions"] = (float(path["high"].max()) / entry_close) - 1.0
    out["plus_5pct_within_10_sessions"] = bool(float(out["MFE_10_sessions"]) >= 0.05)
    out["plus_10pct_within_20_sessions"] = bool(float(out["MFE_20_sessions"]) >= 0.10)
    out["entry_price_used_for_option_reference"] = event_map.get(row["raw_source_event_id"], {}).get("entry_price", "")
    out["outcome_status"] = "complete"
    return out


def build_underlying_outcomes(route_rows: list[dict[str, Any]], event_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    tickers = {row["ticker"] for row in route_rows if row["route_state"] in ELIGIBLE_ROUTE_STATES}
    histories = load_ohlcv_subset(tickers)
    return [outcome_for_route(row, event_map, histories) for row in route_rows]


def subperiod(entry_date: str) -> str:
    date = pd.Timestamp(entry_date)
    if date.year == 2024:
        return "2024"
    if date.year == 2025:
        return "2025"
    if date.year == 2026 and date <= pd.Timestamp("2026-06-30"):
        return "2026_H1"
    return "other"


def summarize_underlying(outcomes: list[dict[str, Any]], include_full: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    complete = pd.DataFrame([r for r in outcomes if r["route_state"] in ELIGIBLE_ROUTE_STATES]).copy()
    if complete.empty:
        return [], []
    complete["subperiod"] = complete["entry_date"].map(subperiod)
    scopes = []
    for period in ["2024", "2025", "2026_H1"]:
        scopes.append((period, complete[complete["subperiod"] == period]))
    if include_full:
        scopes.append(("full_range", complete))
    rows = []
    stability = []
    for period, frame in scopes:
        for route in ["S1", "PB", "C"]:
            group = frame[frame["route"] == route]
            complete_group = group[group["outcome_status"] == "complete"]
            values = lambda col: pd.to_numeric(complete_group[col], errors="coerce").dropna()
            count = int(len(complete_group))
            row = {
                "subperiod": period,
                "route": route,
                "candidate_count": int(len(group)),
                "eligible_outcome_count": count,
                "unique_tickers": int(complete_group["ticker"].nunique()) if count else 0,
                "coverage": count / len(group) if len(group) else "",
                "mean_5d_return": values("underlying_return_5_sessions").mean() if count else "",
                "median_5d_return": values("underlying_return_5_sessions").median() if count else "",
                "mean_10d_return": values("underlying_return_10_sessions").mean() if count else "",
                "median_10d_return": values("underlying_return_10_sessions").median() if count else "",
                "mean_20d_return": values("underlying_return_20_sessions").mean() if count else "",
                "median_20d_return": values("underlying_return_20_sessions").median() if count else "",
                "plus_5pct_within_10_rate": pd.Series(complete_group["plus_5pct_within_10_sessions"]).astype(str).str.lower().eq("true").mean() if count else "",
                "plus_10pct_within_20_rate": pd.Series(complete_group["plus_10pct_within_20_sessions"]).astype(str).str.lower().eq("true").mean() if count else "",
                "MAE_10_median": values("MAE_10_sessions").median() if count else "",
                "MAE_10_p10": values("MAE_10_sessions").quantile(0.10) if count else "",
                "MAE_20_median": values("MAE_20_sessions").median() if count else "",
                "MAE_20_p10": values("MAE_20_sessions").quantile(0.10) if count else "",
                "MFE_10_median": values("MFE_10_sessions").median() if count else "",
                "MFE_10_p90": values("MFE_10_sessions").quantile(0.90) if count else "",
                "MFE_20_median": values("MFE_20_sessions").median() if count else "",
                "MFE_20_p90": values("MFE_20_sessions").quantile(0.90) if count else "",
                "sample_label": "SPARSE_SAMPLE" if count < 15 else "OK",
                "research_only": True,
            }
            rows.append(row)
            if period != "full_range":
                stability.append(row)
    return rows, stability


def fixed_iv_summary(outcomes: list[dict[str, Any]], event_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    eligible = [r for r in outcomes if r["route_state"] in ELIGIBLE_ROUTE_STATES and r["outcome_status"] == "complete"]
    histories = ref.load_ohlcv_subset(baseline_input_root(), {r["ticker"] for r in eligible})
    modeled: list[dict[str, Any]] = []
    coverage: dict[str, list[dict[str, Any]]] = {route: [] for route in ["S1", "PB", "C"]}
    for row in eligible:
        event = event_map.get(row["raw_source_event_id"], {})
        signal = {
            "signal_id": row["raw_source_event_id"],
            "underlying_symbol": row["ticker"],
            "signal_decision_date": row["signal_date"],
            "entry_session": row["entry_date"],
            "entry_price": event.get("entry_price", row.get("entry_price_used_for_option_reference", "")),
            "theme": event.get("theme", ""),
            "breakout_day_low": event.get("breakout_day_low", ""),
            "reached_plus_5pct_within_10_sessions": str(row["plus_5pct_within_10_sessions"]).lower(),
        }
        hist = histories.get(row["ticker"])
        result = {"status": "excluded", "excluded_reason": "missing_ticker_ohlcv"} if hist is None else ref.model_trade(signal, hist)
        coverage[row["route"]].append(result)
        if result["status"] == "eligible":
            ret = 125.0 if str(result.get("first_hit_125_date", "")).strip() else float(result["terminal_net_return_pct"])
            modeled.append({**row, **result, "route": row["route"], "fixed_iv_TP125_reference_return_pct": ret})
    rows = []
    for route in ["S1", "PB", "C"]:
        route_results = [r for r in modeled if r["route"] == route]
        vals = [float(r["fixed_iv_TP125_reference_return_pct"]) for r in route_results]
        rows.append(
            {
                "route": route,
                "fixed_iv_eligible_count": len(vals),
                "coverage": len(vals) / len(coverage[route]) if coverage[route] else "",
                "TP125_hit_rate": sum(bool(str(r.get("first_hit_125_date", "")).strip()) for r in route_results) / len(vals) if vals else "",
                "mean_return": pd.Series(vals).mean() if vals else "",
                "median_return": pd.Series(vals).median() if vals else "",
                "gross_profit": sum(v for v in vals if v > 0),
                "gross_loss": -sum(v for v in vals if v < 0),
                "PF": profit_factor(vals) if vals else "",
                "max_loss": min(vals) if vals else "",
                "uniform_reference_exit_for_comparison_only": True,
                "not_final_route_exit_policy": True,
            }
        )
    return rows, "complete"


def build_manifest() -> dict[str, Any]:
    files = []
    for name in REQUIRED_FILES:
        if name == "route_comparison_content_manifest.json":
            continue
        path = OUT / name
        if path.exists():
            files.append({"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {
        "manifest_version": "morita_s1_pb_c_route_comparison_v0_1",
        "created_at_utc": utc_now(),
        "required_files": REQUIRED_FILES,
        "files": files,
        "content_set_hash": hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    write_json(OUT / "route_comparison_content_manifest.json", manifest)
    return manifest


def verify_manifest() -> dict[str, Any]:
    missing = [name for name in REQUIRED_FILES if not (OUT / name).exists()]
    actual = sorted(path.name for path in OUT.iterdir() if path.is_file()) if OUT.exists() else []
    extra = [name for name in actual if name not in REQUIRED_FILES]
    changed = []
    manifest_path = OUT / "route_comparison_content_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("files", []):
            path = OUT / item["path"]
            if not path.exists() or sha256_file(path) != item["sha256"]:
                changed.append(item["path"])
    return {"verified": not missing and not extra and not changed, "missing": missing, "extra": extra, "changed": changed}


def assert_no_forbidden_outputs() -> None:
    for path in OUT.glob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in FORBIDDEN_OUTPUT_TOKENS:
                if token in text:
                    raise AssertionError(f"forbidden_output_token:{token}:{path.name}")


def write_notes() -> None:
    (OUT / "route_bias_and_dependency_notes.md").write_text(
        "\n".join(
            [
                "# Route Bias And Dependency Notes",
                "",
                "- Same-cluster S1, PB, and C observations are not independent observations.",
                "- C only exists after a later raw-S event occurs, so it has continuation-selection bias.",
                "- C does not justify buying every high update or FOMO breakout.",
                "- Route counts and ticker composition differ by construction.",
                "- Tables are not account-return, sizing, or drawdown estimates.",
                "- Real fills, real IV, option spreads, and route-specific exits remain unresolved.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def write_summary_and_bundle(receipt: dict[str, Any], underlying_summary: list[dict[str, Any]], fixed_rows: list[dict[str, Any]]) -> None:
    full = [r for r in underlying_summary if r["subperiod"] == "full_range"]
    stability = [r for r in underlying_summary if r["subperiod"] != "full_range"]
    lines = [
        "# Morita S1 vs PB vs C Route Comparison v0.1",
        "",
        "Research-only comparison. No live notification/order change, no new data, no parameter sweep, no PF targeting, no portfolio/DD/sizing study, and raw histories unchanged.",
        "",
        "## Receipt",
        "",
        "```json",
        json.dumps(receipt, indent=2, sort_keys=True),
        "```",
        "",
        "## Full-Range Underlying Comparison",
        "",
        md_table(full, ["route", "eligible_outcome_count", "unique_tickers", "mean_10d_return", "median_10d_return", "mean_20d_return", "median_20d_return", "plus_5pct_within_10_rate", "plus_10pct_within_20_rate", "sample_label"]),
        "",
        "## Subperiod Stability",
        "",
        md_table(stability, ["subperiod", "route", "eligible_outcome_count", "mean_10d_return", "median_20d_return", "sample_label"]),
        "",
        "## Uniform Fixed-IV Reference",
        "",
        md_table(fixed_rows, ["route", "fixed_iv_eligible_count", "coverage", "TP125_hit_rate", "mean_return", "median_return", "PF", "max_loss", "uniform_reference_exit_for_comparison_only", "not_final_route_exit_policy"]),
        "",
        "## Caveats",
        "",
        "- Same-cluster route observations are dependent.",
        "- C has continuation-selection bias and is not a buy-every-high-update rule.",
        "- PB still needs low-volume, base-validity, and rebound-confirmation refinement.",
        "- Fixed-IV is a common synthetic reference only, not final route exit policy.",
    ]
    summary = "\n".join(lines) + "\n"
    (OUT / "route_comparison_summary.md").write_text(summary, encoding="utf-8")
    BUNDLE.write_text(summary, encoding="utf-8")


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    source_rows = source_identity_rows()
    missing_sources = [r["component"] for r in source_rows if not r["exists"]]
    if missing_sources:
        write_csv(OUT / "source_verification.csv", source_rows)
        raise FileNotFoundError(f"missing_required_sources:{missing_sources}")
    sessions = load_sessions()
    session_pos = {date: idx for idx, date in enumerate(sessions)}
    raw_s, raw_ab = load_candidate_layer()
    event_map = load_baseline_event_map()
    cluster_rows = build_cluster_proxy(raw_s, session_pos)
    route_rows = build_route_calendar(cluster_rows, raw_ab, event_map, session_pos)
    outcome_rows = build_underlying_outcomes(route_rows, event_map)
    underlying_summary, stability_rows = summarize_underlying(outcome_rows)
    fixed_rows, fixed_status = fixed_iv_summary(outcome_rows, event_map)
    write_notes()
    receipt = {
        "status": "completed",
        "created_at_utc": utc_now(),
        "research_only": True,
        "no_new_data_downloaded": True,
        "no_web_or_provider_api": True,
        "no_broker_or_webull_access": True,
        "no_live_order_or_alert_action": True,
        "no_parameter_sweep": True,
        "no_pf_targeting": True,
        "no_future_data_in_route_assignment": True,
        "no_portfolio_simulation": True,
        "no_sizing_or_dd_research": True,
        "raw_s_count": int(len(raw_s)),
        "raw_ab_count": int(len(raw_ab)),
        "cluster_proxy_count": int(len({r["cluster_proxy_id"] for r in cluster_rows})),
        "route_s1_count": int(sum(r["route_state"] == "S1_CLUSTER_FIRST" for r in route_rows)),
        "route_pb_first_count": int(sum(r["route_state"] == "PB_FIRST_PARENTED" for r in route_rows)),
        "route_c_first_count": int(sum(r["route_state"] == "C_FIRST_CONTINUATION" for r in route_rows)),
        "fixed_iv_route_comparison_status": fixed_status,
    }
    write_csv(OUT / "source_verification.csv", source_rows)
    write_csv(OUT / "raw_signal_cluster_proxy.csv", cluster_rows)
    write_csv(OUT / "route_candidate_calendar.csv", route_rows)
    write_csv(OUT / "route_underlying_outcomes.csv", outcome_rows)
    write_csv(OUT / "route_underlying_summary.csv", underlying_summary)
    write_csv(OUT / "route_subperiod_stability.csv", stability_rows)
    write_csv(OUT / "route_fixed_iv_reference_summary.csv", fixed_rows)
    write_json(OUT / "route_comparison_receipt.json", receipt)
    write_summary_and_bundle(receipt, underlying_summary, fixed_rows)
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
