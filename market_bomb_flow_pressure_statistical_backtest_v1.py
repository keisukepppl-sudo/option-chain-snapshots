from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import market_bomb_flow_pressure_research_v0 as flow


ARTIFACT_VERSION = "flow_pressure_statistical_backtest_v1"
SPEC_VERSION = "flow_pressure_statistical_backtest_v1_spec"
MANIFEST_VERSION = "flow_pressure_statistical_backtest_content_manifest_v1"
RECEIPT_VERSION = "flow_pressure_statistical_backtest_receipt_v1"
DECISION_RULE_VERSION = "flow_pressure_evidence_classifier_v1"
ACTIONIZATION_ALLOWED = False

REQUIRED_OUTPUTS = [
    "analysis_registry.csv",
    "feature_outcome_panel.csv",
    "chronological_split_manifest.json",
    "derived_threshold_registry.json",
    "partition_boundary_registry.json",
    "statistical_summary.csv",
    "effect_size_summary.csv",
    "bootstrap_summary.csv",
    "bootstrap_replicate_metadata.json",
    "interaction_results.csv",
    "interaction_difference_in_differences.csv",
    "sample_stability_report.csv",
    "outcome_coverage_report.csv",
    "exclusion_reason_report.csv",
    "evidence_classification.csv",
    "holdout_results.csv",
    "research_conclusion.md",
]

CONCLUSION_OPENING = (
    "This is a timing-valid, research-only analysis of model-implied pressure proxies.  \n"
    "It does not observe actual institutional or dealer orders, does not authorize trading, and does not modify Fragility Score."
)


def load_json(path: Path) -> dict[str, Any]:
    with open(io_path(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_for_write(path) as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True, default=str))


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(io_path(path), index=False)


def io_path(path: Path | str) -> str:
    if isinstance(path, str):
        resolved = path
    else:
        resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


def open_for_write(path: Path):
    return open(io_path(path), "w", encoding="utf-8", newline="")


def file_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(io_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_run_files(run_dir: Path) -> list[tuple[str, str, int]]:
    base = io_path(run_dir)
    rows: list[tuple[str, str, int]] = []
    for dirpath, _, filenames in os.walk(base):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace("\\", "/")
            rows.append((rel, full, os.stat(full).st_size))
    return sorted(rows, key=lambda r: r[0])


def policy(root: Path) -> dict[str, Any]:
    path = root / "market_bomb_config" / "flow_pressure_statistical_backtest_v1_policy.json"
    return load_json(path)


def spec(root: Path, spec_path: str | None = None) -> dict[str, Any]:
    path = Path(spec_path) if spec_path else root / "market_bomb_config" / "flow_pressure_statistical_backtest_v1_spec.json"
    data = load_json(path)
    if data.get("actionization_allowed") is not False:
        raise SystemExit("statistical backtest spec actionization_allowed must be false")
    return data


def statistical_runs_dir(root: Path, release_id: str) -> Path:
    return flow.release_dir(root, release_id) / "stat_runs"


def statistical_run_dir(root: Path, release_id: str, run_id: str) -> Path:
    return statistical_runs_dir(root, release_id) / run_id


def safe_number(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out if np.isfinite(out) else np.nan


def timestamp_utc(value: Any) -> pd.Timestamp | pd.NaT:
    return pd.to_datetime(value, utc=True, errors="coerce")


def iso(value: pd.Timestamp | pd.NaT) -> str:
    if pd.isna(value):
        return ""
    return value.isoformat().replace("+00:00", "Z")


def release_paths(root: Path, release_id: str) -> tuple[Path, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    flow.verify_release(root, release_id)
    rel = flow.release_dir(root, release_id)
    features = pd.read_csv(rel / "features" / "flow_pressure_features.csv")
    canonical = pd.read_csv(rel / "canonical_input" / "flow_pressure_canonical_source_rows.csv")
    timing = pd.read_csv(rel / "timing_audit.csv")
    if "actionization_allowed" in features.columns and features["actionization_allowed"].fillna(False).astype(bool).any():
        raise SystemExit("feature release actionization_allowed must remain false")
    return rel, features, canonical, timing


def pressure_value(row: pd.Series) -> float:
    for col in ["pressure_normalized", "normalized_rebalance_pressure", "normalized_deleveraging_pressure", "pressure_value"]:
        value = safe_number(row.get(col))
        if np.isfinite(value):
            return value
    return np.nan


def feature_available_at(row: pd.Series) -> pd.Timestamp | pd.NaT:
    for col in ["available_at", "latest_return_available_at_timestamp", "underlying_return_available_at", "aum_available_at_timestamp"]:
        ts = timestamp_utc(row.get(col))
        if pd.notna(ts):
            return ts
    return pd.NaT


def feature_row_id(row: pd.Series, idx: int) -> str:
    raw = row.get("source_row_id")
    if isinstance(raw, str) and raw:
        return raw
    parts = [str(row.get(c, "")) for c in ["module", "feature_name", "instrument", "underlying", "as_of_date"]]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"feature_{idx:08d}_{digest}"


def prices_daily(canonical: pd.DataFrame) -> pd.DataFrame:
    rows = canonical[(canonical["dataset_type"] == "prices_daily") & (canonical["timing_status"] == "timing_eligible")].copy()
    rows["session_date"] = rows["session_date"].astype(str)
    for col in ["open", "high", "low", "close"]:
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    rows["market_ts"] = pd.to_datetime(rows["market_timestamp"], utc=True, errors="coerce")
    return rows.dropna(subset=["instrument", "session_date", "close", "market_ts"]).sort_values(["instrument", "session_date"]).reset_index(drop=True)


def outcome_value(px: pd.DataFrame, i: int, name: str) -> tuple[float, pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT]:
    if i + 1 >= len(px):
        return np.nan, pd.NaT, pd.NaT
    start_ts = px.loc[i + 1, "market_ts"]
    if name == "next_session_open_to_close_return":
        open_px = safe_number(px.loc[i + 1, "open"])
        close_px = safe_number(px.loc[i + 1, "close"])
        return (close_px / open_px - 1.0 if open_px else np.nan), start_ts, px.loc[i + 1, "market_ts"]
    if name == "next_session_close_to_close_return":
        base = safe_number(px.loc[i, "close"])
        close_px = safe_number(px.loc[i + 1, "close"])
        return (close_px / base - 1.0 if base else np.nan), start_ts, px.loc[i + 1, "market_ts"]
    if name == "next_session_daily_range":
        open_px = safe_number(px.loc[i + 1, "open"])
        hi = safe_number(px.loc[i + 1, "high"])
        lo = safe_number(px.loc[i + 1, "low"])
        return ((hi - lo) / open_px if open_px else np.nan), start_ts, px.loc[i + 1, "market_ts"]

    horizon = 3 if name.startswith("three_session") or name == "subsequent_realized_volatility" or name == "conditional_drawdown" else 5
    if i + horizon >= len(px):
        return np.nan, start_ts, pd.NaT
    end_ts = px.loc[i + horizon, "market_ts"]
    base = safe_number(px.loc[i, "close"])
    window = px.iloc[i + 1 : i + horizon + 1]
    if not base or window.empty:
        return np.nan, start_ts, end_ts
    if name in {"three_session_close_to_close_return", "five_session_close_to_close_return"}:
        return safe_number(px.loc[i + horizon, "close"]) / base - 1.0, start_ts, end_ts
    if name in {"three_session_mae", "five_session_mae", "conditional_drawdown"}:
        return safe_number(window["low"].min()) / base - 1.0, start_ts, end_ts
    if name in {"three_session_mfe", "five_session_mfe"}:
        return safe_number(window["high"].max()) / base - 1.0, start_ts, end_ts
    if name == "subsequent_realized_volatility":
        returns = window["close"].pct_change().dropna()
        return (float(returns.std() * math.sqrt(252)) if len(returns) >= 2 else np.nan), start_ts, end_ts
    return np.nan, start_ts, end_ts


def flow_regime(module: str, pressure: float, neutral_band: float) -> str:
    if not np.isfinite(pressure):
        return "unknown"
    if abs(pressure) <= neutral_band:
        return "non_adverse"
    if module in {"leveraged_etf_rebalance", "vol_control_deleveraging"}:
        return "adverse" if pressure < -neutral_band else "non_adverse"
    return "unknown"


def pressure_sign(pressure: float, neutral_band: float) -> str:
    if not np.isfinite(pressure):
        return "unknown"
    if abs(pressure) <= neutral_band:
        return "neutral_pressure"
    return "negative_pressure" if pressure < 0 else "positive_pressure"


def construct_feature_outcome_panel(root: Path, release_id: str, study_spec: dict[str, Any], p: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rel, features, canonical, _ = release_paths(root, release_id)
    meta = load_json(rel / "release_core_metadata.json")
    release_timing = str(meta.get("research_timing_class", ""))
    if release_timing not in p["allowed_timing_classes"]:
        raise SystemExit("unsupported statistical timing class")
    prices = prices_daily(canonical)
    outcomes = list(study_spec.get("outcomes", []))
    neutral_band = float(p.get("neutral_pressure_band", 0.0))
    panel_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    for idx, feat in features.iterrows():
        fid = feature_row_id(feat, idx)
        module = str(feat.get("module", ""))
        if module in {"cta_trend_flow", "dealer_gamma_regime"}:
            exclusion_rows.append({"feature_row_id": fid, "reason_code": "methodology_incomplete", "count": 1})
            continue
        if feat.get("feature_state") != "available" or feat.get("data_quality_state") != "valid":
            exclusion_rows.append({"feature_row_id": fid, "reason_code": "feature_not_available", "count": 1})
            continue
        if bool(feat.get("actionization_allowed", False)):
            raise SystemExit("statistical panel refuses actionization_allowed feature rows")
        available_ts = feature_available_at(feat)
        if pd.isna(available_ts):
            exclusion_rows.append({"feature_row_id": fid, "reason_code": "missing_feature_available_at", "count": 1})
            continue
        decision_ts = available_ts
        target_instrument = str(feat.get("underlying") or feat.get("underlying_instrument") or feat.get("instrument"))
        as_of_date = str(feat.get("as_of_date", ""))
        px = prices[prices["instrument"] == target_instrument].reset_index(drop=True)
        if px.empty:
            exclusion_rows.append({"feature_row_id": fid, "reason_code": "missing_price_series", "count": 1})
            continue
        matches = px.index[px["session_date"] == as_of_date]
        if len(matches) == 0:
            exclusion_rows.append({"feature_row_id": fid, "reason_code": "missing_as_of_price", "count": 1})
            continue
        i = int(matches[0])
        pressure = pressure_value(feat)
        for outcome_name in outcomes:
            value, target_start, target_end = outcome_value(px, i, outcome_name)
            if not np.isfinite(value):
                exclusion_rows.append({"feature_row_id": fid, "reason_code": f"missing_outcome_{outcome_name}", "count": 1})
                continue
            if not (available_ts <= decision_ts < target_start):
                exclusion_rows.append({"feature_row_id": fid, "reason_code": "point_in_time_rule_failed", "count": 1})
                continue
            panel_rows.append(
                {
                    "release_id": release_id,
                    "feature_row_id": fid,
                    "instrument": str(feat.get("instrument", "")),
                    "underlying_instrument": target_instrument,
                    "module_name": module,
                    "feature_name": str(feat.get("feature_name", "")),
                    "decision_time": iso(decision_ts),
                    "decision_date": str(decision_ts.date()),
                    "research_timing_class": release_timing,
                    "feature_available_at_timestamp": iso(available_ts),
                    "feature_state": feat.get("feature_state", ""),
                    "data_quality_state": feat.get("data_quality_state", ""),
                    "timing_eligible": True,
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                    "source_contract_version": meta.get("source_contract_version", ""),
                    "methodology_version": feat.get("methodology_version", meta.get("methodology_version", "")),
                    "parameter_registry_hash": flow.file_sha256(rel / "parameter_registry.json"),
                    "leveraged_etf_rebalance_pressure": safe_number(feat.get("theoretical_rebalance_pressure")),
                    "normalized_rebalance_pressure": safe_number(feat.get("normalized_rebalance_pressure")),
                    "vol_control_deleveraging_pressure": safe_number(feat.get("normalized_deleveraging_pressure")),
                    "vol_window_name": feat.get("vol_window_name", ""),
                    "selected_aum_source_row_id": feat.get("selected_aum_source_row_id", ""),
                    "aum_observation_age": safe_number(feat.get("aum_observation_age")),
                    "pressure_value": pressure,
                    "pressure_sign": pressure_sign(pressure, neutral_band),
                    "flow_regime": flow_regime(module, pressure, neutral_band),
                    "fragility_as_of_timestamp": "",
                    "fragility_available_at_timestamp": "",
                    "fragility_state": "unavailable",
                    "fragility_score_or_regime": "",
                    "fragility_regime": "not_high",
                    "target_name": outcome_name,
                    "target_start_timestamp": iso(target_start),
                    "target_end_timestamp": iso(target_end),
                    "target_value": value,
                    "outcome_available_at_timestamp": iso(target_end),
                    "outcome_validity_state": "valid",
                }
            )
    panel = pd.DataFrame(panel_rows)
    exclusions = pd.DataFrame(exclusion_rows)
    if not exclusions.empty:
        exclusions = exclusions.groupby("reason_code", dropna=False)["count"].sum().reset_index()
    else:
        exclusions = pd.DataFrame(columns=["reason_code", "count"])
    return panel, exclusions


def split_panel(panel: pd.DataFrame, study_spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    if panel.empty:
        manifest = {
            "artifact_version": ARTIFACT_VERSION,
            "split_method": "chronological_unique_decision_dates",
            "overlap_detected": False,
            "final_holdout_used_for_parameter_selection": False,
            "partitions": {},
            "actionization_allowed": ACTIONIZATION_ALLOWED,
        }
        return panel.copy(), manifest
    ratios = study_spec.get("chronological_split", {"train": 0.6, "validation": 0.2, "final_holdout": 0.2})
    dates = sorted(panel["decision_date"].dropna().astype(str).unique())
    n = len(dates)
    train_end = int(n * float(ratios.get("train", 0.6)))
    val_end = train_end + int(n * float(ratios.get("validation", 0.2)))
    mapping = {}
    for d in dates[:train_end]:
        mapping[d] = "train"
    for d in dates[train_end:val_end]:
        mapping[d] = "validation"
    for d in dates[val_end:]:
        mapping[d] = "final_holdout"
    out = panel.copy()
    out["split"] = out["decision_date"].map(mapping)
    partitions = {}
    for name in ["train", "validation", "final_holdout"]:
        part = out[out["split"] == name]
        partitions[name] = {
            "start_date": part["decision_date"].min() if not part.empty else "",
            "end_date": part["decision_date"].max() if not part.empty else "",
            "unique_decision_dates": int(part["decision_date"].nunique()) if not part.empty else 0,
            "row_count": int(len(part)),
            "module_counts": part["module_name"].value_counts().to_dict() if not part.empty else {},
            "instrument_counts": part["underlying_instrument"].value_counts().to_dict() if not part.empty else {},
        }
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "split_method": "chronological_unique_decision_dates",
        "overlap_detected": False,
        "final_holdout_used_for_parameter_selection": False,
        "partitions": partitions,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    return out, manifest


def derive_thresholds_and_boundaries(panel: pd.DataFrame, p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    train = panel[panel.get("split", "") == "train"].copy() if not panel.empty else pd.DataFrame()
    tail_pct = float(p.get("downside_tail_percentile", 0.2))
    thresholds: dict[str, Any] = {"artifact_version": ARTIFACT_VERSION, "downside_tail_percentile": tail_pct, "thresholds": [], "actionization_allowed": ACTIONIZATION_ALLOWED}
    boundaries: dict[str, Any] = {"artifact_version": ARTIFACT_VERSION, "boundaries": [], "actionization_allowed": ACTIONIZATION_ALLOWED}
    if train.empty:
        return thresholds, boundaries
    for (module, instrument, outcome), g in train.groupby(["module_name", "underlying_instrument", "target_name"], dropna=False):
        values = pd.to_numeric(g["target_value"], errors="coerce").dropna()
        thresholds["thresholds"].append(
            {
                "module_name": module,
                "underlying_instrument": instrument,
                "target_name": outcome,
                "threshold_name": "downside_tail_train_percentile",
                "threshold_value": float(values.quantile(tail_pct)) if not values.empty else None,
                "train_start": str(g["decision_date"].min()),
                "train_end": str(g["decision_date"].max()),
                "train_sample_count": int(len(values)),
            }
        )
    for (module, instrument, feature), g in train.groupby(["module_name", "underlying_instrument", "feature_name"], dropna=False):
        values = pd.to_numeric(g["pressure_value"], errors="coerce").abs().dropna()
        qs = values.quantile([0.2, 0.4, 0.6, 0.8]).to_dict() if len(values) else {}
        boundaries["boundaries"].append(
            {
                "module_name": module,
                "underlying_instrument": instrument,
                "feature_name": feature,
                "partition_name": "absolute_pressure_quintile",
                "q20": float(qs.get(0.2, np.nan)) if qs else None,
                "q40": float(qs.get(0.4, np.nan)) if qs else None,
                "q60": float(qs.get(0.6, np.nan)) if qs else None,
                "q80": float(qs.get(0.8, np.nan)) if qs else None,
                "train_sample_count": int(len(values)),
            }
        )
    return thresholds, boundaries


def apply_train_thresholds(panel: pd.DataFrame, thresholds: dict[str, Any], boundaries: dict[str, Any]) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    out = panel.copy()
    threshold_map = {
        (r["module_name"], r["underlying_instrument"], r["target_name"]): r.get("threshold_value")
        for r in thresholds.get("thresholds", [])
    }
    boundary_map = {
        (r["module_name"], r["underlying_instrument"], r["feature_name"]): [r.get("q20"), r.get("q40"), r.get("q60"), r.get("q80")]
        for r in boundaries.get("boundaries", [])
    }
    tail_values = []
    quintiles = []
    for _, row in out.iterrows():
        thr = threshold_map.get((row["module_name"], row["underlying_instrument"], row["target_name"]))
        value = safe_number(row["target_value"])
        tail_values.append(bool(np.isfinite(value) and thr is not None and value <= float(thr)))
        bounds = boundary_map.get((row["module_name"], row["underlying_instrument"], row["feature_name"]), [])
        abs_pressure = abs(safe_number(row["pressure_value"]))
        label = "absolute_pressure_unavailable"
        if np.isfinite(abs_pressure) and len(bounds) == 4 and all(b is not None for b in bounds):
            label = "abs_q1"
            for idx, b in enumerate(bounds, start=2):
                if abs_pressure > float(b):
                    label = f"abs_q{idx}"
        quintiles.append(label)
    out["downside_tail"] = tail_values
    out["absolute_pressure_quintile"] = quintiles
    return out


def descriptive_stats(values: pd.Series, tails: pd.Series, min_quantile_rows: int) -> dict[str, Any]:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    out: dict[str, Any] = {
        "sample_count": int(len(vals)),
        "mean": float(vals.mean()) if len(vals) else np.nan,
        "median": float(vals.median()) if len(vals) else np.nan,
        "std": float(vals.std()) if len(vals) > 1 else np.nan,
        "hit_rate": float((vals > 0).mean()) if len(vals) else np.nan,
        "downside_tail_rate": float(pd.Series(tails).astype(bool).mean()) if len(vals) else np.nan,
        "realized_volatility": float(vals.std() * math.sqrt(252)) if len(vals) > 1 else np.nan,
    }
    for q in [0.05, 0.10, 0.25, 0.75, 0.90, 0.95]:
        out[f"p{int(q*100):02d}"] = float(vals.quantile(q)) if len(vals) >= min_quantile_rows else np.nan
    return out


def build_statistical_summary(panel: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    rows = []
    min_q = int(p.get("minimum_quantile_rows", 30))
    group_cols = ["split", "module_name", "underlying_instrument", "feature_name", "target_name", "flow_regime"]
    if panel.empty:
        return pd.DataFrame(columns=group_cols + ["analysis_id", "sample_count"])
    for keys, g in panel.groupby(group_cols, dropna=False):
        stats = descriptive_stats(g["target_value"], g["downside_tail"], min_q)
        rows.append(
            {
                "analysis_id": analysis_id(keys),
                "partition_definition": "flow_adverse_vs_non_adverse",
                "unique_decision_dates": int(g["decision_date"].nunique()),
                "mean_mae": float(g.loc[g["target_name"].astype(str).str.contains("mae|drawdown"), "target_value"].mean()) if any(g["target_name"].astype(str).str.contains("mae|drawdown")) else np.nan,
                "median_mae": float(g.loc[g["target_name"].astype(str).str.contains("mae|drawdown"), "target_value"].median()) if any(g["target_name"].astype(str).str.contains("mae|drawdown")) else np.nan,
                "mean_mfe": float(g.loc[g["target_name"].astype(str).str.contains("mfe"), "target_value"].mean()) if any(g["target_name"].astype(str).str.contains("mfe")) else np.nan,
                "median_mfe": float(g.loc[g["target_name"].astype(str).str.contains("mfe"), "target_value"].median()) if any(g["target_name"].astype(str).str.contains("mfe")) else np.nan,
                **dict(zip(group_cols, keys)),
                **stats,
                "status": "ok" if stats["sample_count"] >= int(p.get("minimum_partition_rows", 50)) else "insufficient_sample",
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
        )
    return pd.DataFrame(rows)


def analysis_id(keys: Any) -> str:
    if not isinstance(keys, tuple):
        keys = tuple([keys])
    digest = hashlib.sha256("|".join(str(k) for k in keys).encode("utf-8")).hexdigest()[:16]
    return f"an_{digest}"


def not_estimable_ratio(num: float, den: float) -> tuple[Any, str]:
    if not np.isfinite(num) or not np.isfinite(den) or den == 0:
        return "not_estimable", "not_estimable"
    return float(num / den), "estimable"


def build_effect_sizes(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if summary.empty:
        return pd.DataFrame()
    baseline_cols = ["split", "module_name", "underlying_instrument", "feature_name", "target_name"]
    for keys, g in summary.groupby(baseline_cols, dropna=False):
        baseline = g.copy()
        base_mean = float(np.average(baseline["mean"], weights=baseline["sample_count"])) if baseline["sample_count"].sum() else np.nan
        base_median = float(np.average(baseline["median"], weights=baseline["sample_count"])) if baseline["sample_count"].sum() else np.nan
        base_tail = float(np.average(baseline["downside_tail_rate"], weights=baseline["sample_count"])) if baseline["sample_count"].sum() else np.nan
        base_std = safe_number(baseline["std"].mean())
        for _, row in g.iterrows():
            rr, rr_status = not_estimable_ratio(safe_number(row["downside_tail_rate"]), base_tail)
            odds_den = 1 - base_tail if np.isfinite(base_tail) else np.nan
            row_odds_den = 1 - safe_number(row["downside_tail_rate"])
            odds, odds_status = not_estimable_ratio(safe_number(row["downside_tail_rate"]) / row_odds_den if row_odds_den else np.nan, base_tail / odds_den if odds_den else np.nan)
            rows.append(
                {
                    "analysis_id": row["analysis_id"],
                    "split": row["split"],
                    "module_name": row["module_name"],
                    "underlying_instrument": row["underlying_instrument"],
                    "feature_name": row["feature_name"],
                    "target_name": row["target_name"],
                    "flow_regime": row["flow_regime"],
                    "mean_difference_vs_unconditional": safe_number(row["mean"]) - base_mean if np.isfinite(base_mean) else np.nan,
                    "median_difference_vs_unconditional": safe_number(row["median"]) - base_median if np.isfinite(base_median) else np.nan,
                    "tail_rate_difference_vs_unconditional": safe_number(row["downside_tail_rate"]) - base_tail if np.isfinite(base_tail) else np.nan,
                    "risk_ratio_vs_unconditional": rr,
                    "risk_ratio_status": rr_status,
                    "odds_ratio_vs_unconditional": odds,
                    "odds_ratio_status": odds_status,
                    "standardized_mean_difference": (safe_number(row["mean"]) - base_mean) / base_std if np.isfinite(base_std) and base_std else np.nan,
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
    return pd.DataFrame(rows)


def moving_block_dates(dates: list[str], rng: np.random.Generator, block_length: int) -> list[str]:
    if not dates:
        return []
    starts = np.arange(len(dates))
    sampled: list[str] = []
    while len(sampled) < len(dates):
        start = int(rng.choice(starts))
        sampled.extend(dates[start : min(start + block_length, len(dates))])
    return sampled[: len(dates)]


def bootstrap_metric(panel: pd.DataFrame, analysis: pd.Series, metric: str, block_length: int, replicates: int, seed: int) -> tuple[float, float, float, bool]:
    group = panel[
        (panel["split"] == analysis["split"])
        & (panel["module_name"] == analysis["module_name"])
        & (panel["underlying_instrument"] == analysis["underlying_instrument"])
        & (panel["feature_name"] == analysis["feature_name"])
        & (panel["target_name"] == analysis["target_name"])
    ].copy()
    sample = group[group["flow_regime"] == analysis["flow_regime"]]
    dates = sorted(group["decision_date"].unique())
    if len(dates) < block_length or sample.empty or group.empty:
        return np.nan, np.nan, np.nan, False
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(replicates):
        sampled_dates = moving_block_dates(dates, rng, block_length)
        base = group[group["decision_date"].isin(sampled_dates)]
        part = sample[sample["decision_date"].isin(sampled_dates)]
        if part.empty or base.empty:
            continue
        if metric == "mean_difference":
            estimates.append(part["target_value"].mean() - base["target_value"].mean())
        elif metric == "median_difference":
            estimates.append(part["target_value"].median() - base["target_value"].median())
        elif metric == "downside_tail_rate_difference":
            estimates.append(part["downside_tail"].astype(bool).mean() - base["downside_tail"].astype(bool).mean())
    if not estimates:
        return np.nan, np.nan, np.nan, False
    arr = np.array(estimates, dtype=float)
    return float(np.nanmean(arr)), float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5)), True


def build_bootstrap(panel: pd.DataFrame, summary: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    method = str(p.get("bootstrap_method", "moving_block_bootstrap"))
    block_lengths = [int(x) for x in p.get("bootstrap_block_lengths", [3, 5, 10])]
    replicates = int(p.get("minimum_bootstrap_replicates", 1000))
    seed = int(p.get("bootstrap_seed", 20260629))
    for _, analysis in summary.iterrows():
        for block_length in block_lengths:
            for metric in ["mean_difference", "median_difference", "downside_tail_rate_difference"]:
                point, low, high, estimable = bootstrap_metric(panel, analysis, metric, block_length, replicates, seed)
                rows.append(
                    {
                        "analysis_id": analysis["analysis_id"],
                        "metric_name": metric,
                        "bootstrap_method": method,
                        "block_length": block_length,
                        "replicate_count": replicates,
                        "seed": seed,
                        "point_estimate": point,
                        "ci_lower": low,
                        "ci_upper": high,
                        "estimable": bool(estimable),
                        "status": "ok" if estimable else "not_estimable",
                    }
                )
    metadata = {
        "artifact_version": ARTIFACT_VERSION,
        "bootstrap_method": method,
        "block_lengths": block_lengths,
        "replicate_count": replicates,
        "seed": seed,
        "resampling_unit": "decision_date",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    return pd.DataFrame(rows), metadata


def build_interactions(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if panel.empty:
        return pd.DataFrame(), pd.DataFrame()
    rows = []
    group_cols = ["split", "module_name", "underlying_instrument", "feature_name", "target_name", "fragility_regime", "flow_regime"]
    for keys, g in panel.groupby(group_cols, dropna=False):
        vals = pd.to_numeric(g["target_value"], errors="coerce")
        rows.append(
            {
                "analysis_id": analysis_id(keys),
                **dict(zip(group_cols, keys)),
                "outcome_name": keys[4],
                "sample_count": int(vals.count()),
                "unique_decision_dates": int(g["decision_date"].nunique()),
                "mean": float(vals.mean()) if vals.count() else np.nan,
                "median": float(vals.median()) if vals.count() else np.nan,
                "tail_rate": float(g["downside_tail"].astype(bool).mean()) if vals.count() else np.nan,
                "effect_vs_unconditional": np.nan,
                "status": "ok" if vals.count() else "insufficient_data",
            }
        )
    interactions = pd.DataFrame(rows)
    did_rows = []
    base_cols = ["split", "module_name", "underlying_instrument", "feature_name", "target_name"]
    for keys, g in interactions.groupby(base_cols, dropna=False):
        def mean_for(frag: str, flow_reg: str) -> float:
            x = g[(g["fragility_regime"] == frag) & (g["flow_regime"] == flow_reg)]["mean"]
            return safe_number(x.iloc[0]) if len(x) else np.nan

        high_adv = mean_for("high", "adverse")
        high_non = mean_for("high", "non_adverse")
        low_adv = mean_for("not_high", "adverse")
        low_non = mean_for("not_high", "non_adverse")
        estimable = all(np.isfinite(x) for x in [high_adv, high_non, low_adv, low_non])
        did_rows.append(
            {
                "analysis_id": analysis_id(keys),
                **dict(zip(base_cols, keys)),
                "interaction_difference_in_differences": (high_adv - high_non) - (low_adv - low_non) if estimable else np.nan,
                "estimable": bool(estimable),
                "status": "ok" if estimable else "not_estimable",
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
        )
    return interactions, pd.DataFrame(did_rows)


def build_stability(panel: pd.DataFrame, summary: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    rows = []
    max_share = float(p.get("concentration_max_date_share", 0.35))
    if panel.empty:
        return pd.DataFrame(columns=["analysis_id", "max_date_share", "stability_status"])
    for _, analysis in summary.iterrows():
        g = panel[
            (panel["split"] == analysis["split"])
            & (panel["module_name"] == analysis["module_name"])
            & (panel["underlying_instrument"] == analysis["underlying_instrument"])
            & (panel["feature_name"] == analysis["feature_name"])
            & (panel["target_name"] == analysis["target_name"])
            & (panel["flow_regime"] == analysis["flow_regime"])
        ]
        share = float(g["decision_date"].value_counts(normalize=True).max()) if not g.empty else np.nan
        rows.append(
            {
                "analysis_id": analysis["analysis_id"],
                "max_date_share": share,
                "stability_status": "concentrated_date_cluster" if np.isfinite(share) and share > max_share else "stable_enough_for_screening",
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
        )
    return pd.DataFrame(rows)


def build_analysis_registry(summary: pd.DataFrame, evidence: pd.DataFrame | None = None) -> pd.DataFrame:
    rows = []
    evidence_map = {} if evidence is None or evidence.empty else evidence.set_index("analysis_id")["evidence_label"].to_dict()
    for _, row in summary.iterrows():
        rows.append(
            {
                "analysis_id": row["analysis_id"],
                "module_name": row["module_name"],
                "instrument_or_underlying": row["underlying_instrument"],
                "research_timing_class": "",
                "feature_definition_version": row["feature_name"],
                "outcome_name": row["target_name"],
                "partition_definition": row.get("partition_definition", "flow_adverse_vs_non_adverse"),
                "fragility_interaction_definition": "fragility_high_x_flow_adverse_predefined",
                "split": row["split"],
                "status": row["status"],
                "sample_count": row["sample_count"],
                "unique_decision_dates": row["unique_decision_dates"],
                "evidence_label": evidence_map.get(row["analysis_id"], "pending_classification"),
                "reason_code": row["status"],
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
        )
    return pd.DataFrame(rows)


def classify_evidence(summary: pd.DataFrame, bootstrap: pd.DataFrame, stability: pd.DataFrame, p: dict[str, Any], timing_class: str) -> pd.DataFrame:
    rows = []
    if summary.empty:
        return pd.DataFrame(
            [
                {
                    "analysis_id": "no_panel",
                    "evidence_label": "insufficient_data",
                    "decision_rule_version": DECISION_RULE_VERSION,
                    "timing_valid": False,
                    "integrity_valid": True,
                    "sample_gate_passed": False,
                    "validation_alignment": False,
                    "holdout_alignment": False,
                    "bootstrap_stability": False,
                    "cross_section_or_regime_stability": False,
                    "primary_reason": "no_eligible_feature_outcome_panel",
                    "limitations": "No trading conclusion is permitted.",
                }
            ]
        )
    min_rows = int(p.get("minimum_partition_rows", 50))
    min_dates = int(p.get("minimum_partition_unique_dates", 40))
    min_holdout_rows = int(p.get("minimum_holdout_rows", 30))
    min_holdout_dates = int(p.get("minimum_holdout_unique_dates", 25))
    boot_ok = set(bootstrap[bootstrap["status"] == "ok"]["analysis_id"]) if not bootstrap.empty else set()
    stability_ok = set(stability[stability["stability_status"] == "stable_enough_for_screening"]["analysis_id"]) if not stability.empty else set()
    base_cols = ["module_name", "underlying_instrument", "feature_name", "target_name", "flow_regime"]
    for keys, g in summary.groupby(base_cols, dropna=False):
        validation = g[g["split"] == "validation"]
        holdout = g[g["split"] == "final_holdout"]
        representative = g.iloc[0]
        validation_effect = safe_number(validation["mean"].iloc[0]) if not validation.empty else np.nan
        holdout_effect = safe_number(holdout["mean"].iloc[0]) if not holdout.empty else np.nan
        sample_pass = bool(
            not validation.empty
            and not holdout.empty
            and int(validation["sample_count"].iloc[0]) >= min_rows
            and int(validation["unique_decision_dates"].iloc[0]) >= min_dates
            and int(holdout["sample_count"].iloc[0]) >= min_holdout_rows
            and int(holdout["unique_decision_dates"].iloc[0]) >= min_holdout_dates
        )
        aligned = bool(np.isfinite(validation_effect) and np.isfinite(holdout_effect) and np.sign(validation_effect) == np.sign(holdout_effect))
        ids = set(g["analysis_id"])
        bootstrap_stable = bool(ids & boot_ok)
        stable = bool(ids <= stability_ok) if ids else False
        if timing_class == "historical_descriptive_only":
            label, reason = "no_reliable_evidence", "historical_descriptive_only_no_predictive_label"
        elif not sample_pass:
            label, reason = "insufficient_sample", "sample_or_unique_date_gate_failed"
        elif not aligned:
            label, reason = "no_reliable_evidence", "validation_holdout_direction_not_aligned"
        elif not bootstrap_stable or not stable:
            label, reason = "no_reliable_evidence", "bootstrap_or_stability_gate_failed"
        else:
            label, reason = "exploratory_association", "timing_valid_aligned_but_requires_replication"
        rows.append(
            {
                "analysis_id": representative["analysis_id"],
                "evidence_label": label,
                "decision_rule_version": DECISION_RULE_VERSION,
                "timing_valid": True,
                "integrity_valid": True,
                "sample_gate_passed": sample_pass,
                "validation_alignment": aligned,
                "holdout_alignment": aligned,
                "bootstrap_stability": bootstrap_stable,
                "cross_section_or_regime_stability": stable,
                "primary_reason": reason,
                "limitations": "Model-implied proxy only; not causal and not trading authorization.",
            }
        )
    return pd.DataFrame(rows)


def outcome_coverage(panel: pd.DataFrame, exclusions: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame([{"target_name": "none", "eligible_rows": 0, "missing_or_excluded_rows": int(exclusions["count"].sum()) if not exclusions.empty else 0, "coverage_status": "insufficient_data"}])
    rows = []
    excluded = int(exclusions["count"].sum()) if not exclusions.empty else 0
    for target, g in panel.groupby("target_name"):
        rows.append({"target_name": target, "eligible_rows": len(g), "missing_or_excluded_rows": excluded, "coverage_status": "valid" if len(g) else "insufficient_data"})
    return pd.DataFrame(rows)


def research_conclusion(release_id: str, run_id: str, timing_class: str, meta: dict[str, Any], split_manifest: dict[str, Any], panel: pd.DataFrame, exclusions: pd.DataFrame, evidence: pd.DataFrame, bootstrap: pd.DataFrame) -> str:
    counts = evidence["evidence_label"].value_counts().to_dict() if not evidence.empty else {}
    split = split_manifest.get("partitions", {})
    lines = [
        CONCLUSION_OPENING,
        "",
        "# Flow Pressure Statistical Backtest v1",
        "",
        f"- release_id: `{release_id}`",
        f"- statistical_backtest_run_id: `{run_id}`",
        f"- timing_class: `{timing_class}`",
        f"- source_contract_version: `{meta.get('source_contract_version', '')}`",
        f"- methodology_version: `{meta.get('methodology_version', '')}`",
        f"- eligible_rows: `{len(panel)}`",
        f"- excluded_rows: `{int(exclusions['count'].sum()) if not exclusions.empty else 0}`",
        f"- evidence_label_counts: `{counts}`",
        "",
        "## Split Dates",
        json.dumps(split, indent=2, sort_keys=True),
        "",
        "## Main Evidence Table",
        evidence.to_csv(index=False).strip() if not evidence.empty else "No evidence rows.",
        "",
        "## Bootstrap Sensitivity",
        bootstrap.groupby(["block_length", "status"]).size().reset_index(name="count").to_csv(index=False).strip() if not bootstrap.empty else "No bootstrap rows.",
        "",
        "## Limitations",
        "- Negative and inconclusive analyses are retained in the registry.",
        "- CTA and Dealer remain blocked methodology placeholders.",
        "- This report is not investment advice and creates no trading, alerting, ranking, or execution permission.",
    ]
    return "\n".join(lines) + "\n"


def content_manifest(run_dir: Path, release_id: str, run_id: str) -> dict[str, Any]:
    entries = []
    for rel, full, size in iter_run_files(run_dir):
        if rel in {"statistical_backtest_content_manifest.json", "statistical_backtest_receipt.json"}:
            continue
        entries.append({"relative_path": rel, "sha256": file_sha256(full), "bytes": size})
    return {
        "artifact_version": MANIFEST_VERSION,
        "release_id": release_id,
        "statistical_backtest_run_id": run_id,
        "entries": entries,
        "content_set_sha256": flow.content_set_hash(entries),
    }


def run_flow_statistical_backtest(root: Path, release_id: str, spec_path: str | None = None) -> str:
    rel, _, _, timing = release_paths(root, release_id)
    meta = load_json(rel / "release_core_metadata.json")
    p = policy(root)
    study_spec = spec(root, spec_path)
    if p.get("actionization_allowed") is not False:
        raise SystemExit("statistical policy actionization_allowed must be false")
    if (timing["timing_status"] != "timing_eligible").any():
        raise SystemExit("statistical backtest blocked by timing audit")
    run_id = f"{flow.utc_now().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    run_dir = statistical_run_dir(root, release_id, run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    panel, exclusions = construct_feature_outcome_panel(root, release_id, study_spec, p)
    panel, split_manifest = split_panel(panel, study_spec)
    thresholds, boundaries = derive_thresholds_and_boundaries(panel, p)
    panel = apply_train_thresholds(panel, thresholds, boundaries)
    summary = build_statistical_summary(panel, p)
    effects = build_effect_sizes(summary)
    bootstrap, bootstrap_meta = build_bootstrap(panel, summary, p)
    interactions, did = build_interactions(panel)
    stability = build_stability(panel, summary, p)
    evidence = classify_evidence(summary, bootstrap, stability, p, str(meta.get("research_timing_class", "")))
    registry = build_analysis_registry(summary, evidence)
    holdout = summary[summary["split"] == "final_holdout"].copy() if not summary.empty else pd.DataFrame()
    coverage = outcome_coverage(panel, exclusions)

    write_csv(run_dir / "feature_outcome_panel.csv", panel)
    write_json(run_dir / "chronological_split_manifest.json", split_manifest)
    write_json(run_dir / "derived_threshold_registry.json", thresholds)
    write_json(run_dir / "partition_boundary_registry.json", boundaries)
    write_csv(run_dir / "statistical_summary.csv", summary)
    write_csv(run_dir / "effect_size_summary.csv", effects)
    write_csv(run_dir / "bootstrap_summary.csv", bootstrap)
    write_json(run_dir / "bootstrap_replicate_metadata.json", bootstrap_meta)
    write_csv(run_dir / "interaction_results.csv", interactions)
    write_csv(run_dir / "interaction_difference_in_differences.csv", did)
    write_csv(run_dir / "sample_stability_report.csv", stability)
    write_csv(run_dir / "outcome_coverage_report.csv", coverage)
    write_csv(run_dir / "exclusion_reason_report.csv", exclusions)
    write_csv(run_dir / "evidence_classification.csv", evidence)
    write_csv(run_dir / "analysis_registry.csv", registry)
    write_csv(run_dir / "holdout_results.csv", holdout)
    (run_dir / "research_conclusion.md").write_text(
        research_conclusion(release_id, run_id, str(meta.get("research_timing_class", "")), meta, split_manifest, panel, exclusions, evidence, bootstrap),
        encoding="utf-8",
    )
    shutil.copyfile(root / "market_bomb_config" / "flow_pressure_statistical_backtest_v1_spec.json", run_dir / "frozen_statistical_backtest_spec.json")
    manifest = content_manifest(run_dir, release_id, run_id)
    write_json(run_dir / "statistical_backtest_content_manifest.json", manifest)
    receipt = {
        "artifact_version": RECEIPT_VERSION,
        "release_id": release_id,
        "statistical_backtest_run_id": run_id,
        "statistical_backtest_spec_version": SPEC_VERSION,
        "run_at_utc": flow.iso_utc(flow.utc_now()),
        "release_content_manifest_sha256": flow.file_sha256(flow.content_manifest_path(rel)),
        "split_manifest_sha256": file_sha256(run_dir / "chronological_split_manifest.json"),
        "derived_threshold_registry_sha256": file_sha256(run_dir / "derived_threshold_registry.json"),
        "partition_boundary_registry_sha256": file_sha256(run_dir / "partition_boundary_registry.json"),
        "analysis_registry_sha256": file_sha256(run_dir / "analysis_registry.csv"),
        "statistical_backtest_content_manifest_sha256": file_sha256(run_dir / "statistical_backtest_content_manifest.json"),
        "bootstrap_seed": int(p.get("bootstrap_seed", 20260629)),
        "final_holdout_evaluation_started_at": flow.iso_utc(flow.utc_now()),
        "frozen_spec_sha256": file_sha256(run_dir / "frozen_statistical_backtest_spec.json"),
        "frozen_thresholds_sha256": file_sha256(run_dir / "derived_threshold_registry.json"),
        "final_holdout_run_count": 1,
        "observed_flow_statement": "No observed flow data; all flow measures are model-implied pressure proxies.",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    write_json(run_dir / "statistical_backtest_receipt.json", receipt)
    verify_flow_statistical_backtest(root, release_id, run_id)
    return run_id


def verify_flow_statistical_backtest(root: Path, release_id: str, run_id: str) -> dict[str, Any]:
    flow.verify_release(root, release_id)
    run_dir = statistical_run_dir(root, release_id, run_id)
    manifest = load_json(run_dir / "statistical_backtest_content_manifest.json")
    receipt = load_json(run_dir / "statistical_backtest_receipt.json")
    if manifest.get("artifact_version") != MANIFEST_VERSION:
        raise SystemExit("unsupported statistical backtest manifest version")
    if receipt.get("artifact_version") != RECEIPT_VERSION:
        raise SystemExit("unsupported statistical backtest receipt version")
    if manifest.get("release_id") != release_id or receipt.get("release_id") != release_id:
        raise SystemExit("statistical backtest release id mismatch")
    if receipt.get("statistical_backtest_run_id") != run_id:
        raise SystemExit("statistical backtest run id mismatch")
    if receipt.get("actionization_allowed") is not False:
        raise SystemExit("statistical backtest actionization_allowed must be false")
    for path_name, receipt_key in [
        ("chronological_split_manifest.json", "split_manifest_sha256"),
        ("derived_threshold_registry.json", "derived_threshold_registry_sha256"),
        ("partition_boundary_registry.json", "partition_boundary_registry_sha256"),
        ("analysis_registry.csv", "analysis_registry_sha256"),
    ]:
        if receipt.get(receipt_key) != file_sha256(run_dir / path_name):
            raise SystemExit(f"statistical backtest hash mismatch: {path_name}")
    if receipt.get("statistical_backtest_content_manifest_sha256") != file_sha256(run_dir / "statistical_backtest_content_manifest.json"):
        raise SystemExit("statistical backtest manifest hash mismatch")
    seen = set()
    recomputed = []
    for entry in manifest.get("entries", []):
        rel = str(entry.get("relative_path", ""))
        if not rel or ".." in Path(rel).parts:
            raise SystemExit(f"unsafe statistical output path: {rel}")
        seen.add(rel)
        path = run_dir / rel
        full = io_path(path)
        if os.path.islink(full) or not os.path.isfile(full):
            raise SystemExit(f"missing statistical output file: {rel}")
        sha = file_sha256(full)
        if sha != entry.get("sha256"):
            raise SystemExit(f"statistical output sha mismatch: {rel}")
        recomputed.append({"relative_path": rel, "sha256": sha, "bytes": os.stat(full).st_size})
    actual = {
        rel
        for rel, _, _ in iter_run_files(run_dir)
        if Path(rel).name not in {"statistical_backtest_content_manifest.json", "statistical_backtest_receipt.json"}
    }
    if actual != seen:
        raise SystemExit("statistical backtest file set mismatch")
    missing = set(REQUIRED_OUTPUTS) - actual
    if missing:
        raise SystemExit(f"statistical backtest missing required outputs: {sorted(missing)}")
    if manifest.get("content_set_sha256") != flow.content_set_hash(recomputed):
        raise SystemExit("statistical backtest content set hash mismatch")
    return {"release_id": release_id, "statistical_backtest_run_id": run_id, "status": "valid"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Flow Pressure Statistical Backtest v1")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run-flow-statistical-backtest")
    p.add_argument("--release-id", required=True)
    p.add_argument("--spec-path")
    p = sub.add_parser("verify-flow-statistical-backtest")
    p.add_argument("--release-id", required=True)
    p.add_argument("--statistical-backtest-run-id", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    if args.command == "run-flow-statistical-backtest":
        result = {"statistical_backtest_run_id": run_flow_statistical_backtest(root, args.release_id, args.spec_path)}
    elif args.command == "verify-flow-statistical-backtest":
        result = verify_flow_statistical_backtest(root, args.release_id, args.statistical_backtest_run_id)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
