#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import numpy as np
import pandas as pd


ARTIFACT_VERSION = "flow_pressure_research_v0_0_1"
RELEASE_CONTENT_MANIFEST_VERSION = "flow_pressure_release_content_manifest_v0_0_1"
RELEASE_CORE_METADATA_VERSION = "flow_pressure_release_core_metadata_v0_0_1"
BACKTEST_CONTENT_MANIFEST_VERSION = "flow_pressure_backtest_content_manifest_v0_0_1"
METHODOLOGY_VERSION = "flow_pressure_methodology_v0_0_1"
ACTIONIZATION_ALLOWED = False
SUPPORTED_MODULES = {"leveraged_etf_rebalance", "vol_control_deleveraging", "cta_trend_flow", "dealer_gamma_regime"}
IMPLEMENTED_MODULES = {"leveraged_etf_rebalance", "vol_control_deleveraging"}
REQUIRED_SOURCE_FIELDS = [
    "source_id",
    "source_name",
    "source_file",
    "source_as_of_timestamp",
    "available_at_timestamp",
    "market_timestamp",
    "instrument",
    "asset_class",
    "relative_path",
    "coverage_start_date",
    "coverage_end_date",
    "dataset_version",
]


def utc_now() -> pd.Timestamp:
    fixed = os.environ.get("FLOW_PRESSURE_NOW_UTC")
    if fixed:
        return parse_utc_ts(fixed, "FLOW_PRESSURE_NOW_UTC")
    return pd.Timestamp.now(tz="UTC")


def parse_utc_ts(value: Any, label: str) -> pd.Timestamp:
    if value in [None, ""]:
        raise SystemExit(f"{label} is required")
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise SystemExit(f"{label} must be timezone-aware")
    return ts.tz_convert("UTC")


def iso_utc(ts: Any) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")


def parse_now_utc(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return parse_utc_ts(value, "--now-utc")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(df: pd.DataFrame, path: Path, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        df = pd.DataFrame(df, columns=columns)
    df.to_csv(path, index=False)


def platform_path(path: Path) -> Path:
    resolved = path.resolve()
    if os.name == "nt":
        text = str(resolved)
        if not text.startswith("\\\\?\\"):
            return Path("\\\\?\\" + text)
    return resolved


def history_root(root: Path) -> Path:
    return root / "market_bomb_history" / "flow_pressure_research_v0"


def staging_dir(root: Path, staging_id: str) -> Path:
    return history_root(root) / "staging" / staging_id


def releases_dir(root: Path) -> Path:
    return history_root(root) / "releases"


def release_dir(root: Path, release_id: str) -> Path:
    return releases_dir(root) / release_id


def receipt_path(rel: Path) -> Path:
    return rel / "release_receipt.json"


def content_manifest_path(rel: Path) -> Path:
    return rel / "release_content_manifest.json"


def safe_relative_path(base: Path, path: Path) -> str:
    resolved_text = str(path.resolve())
    base_text = str(base.resolve())
    if resolved_text.startswith("\\\\?\\"):
        resolved_text = resolved_text[4:]
    if base_text.startswith("\\\\?\\"):
        base_text = base_text[4:]
    rel = Path(resolved_text).relative_to(Path(base_text))
    text = rel.as_posix()
    if text.startswith("../") or text == ".." or Path(text).is_absolute():
        raise SystemExit(f"unsafe manifest path: {text}")
    return text


def validate_source_relative_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        raise SystemExit("empty staged source relative_path")
    if text.startswith("/") or text.startswith("\\"):
        raise SystemExit(f"absolute staged source path is not allowed: {text}")
    if PureWindowsPath(str(value)).drive or str(value).startswith("\\\\"):
        raise SystemExit(f"windows drive or UNC staged source path is not allowed: {value}")
    parts = PurePosixPath(text).parts
    if ".." in parts:
        raise SystemExit(f"path traversal staged source path is not allowed: {text}")
    return text


def staged_source_path(root: Path, staging_id: str, source: dict[str, Any]) -> Path:
    rel = validate_source_relative_path(source.get("relative_path"))
    base = staging_dir(root, staging_id)
    path = base / rel
    try:
        path.resolve().relative_to(base.resolve())
    except Exception as exc:
        raise SystemExit(f"staged source path escapes staging root: {rel}") from exc
    return path


def load_staging_manifest(root: Path, staging_id: str) -> dict[str, Any]:
    path = staging_dir(root, staging_id) / "source_bundle_manifest.json"
    if not path.exists():
        raise SystemExit(f"missing source bundle manifest: {staging_id}")
    manifest = load_json(path)
    if str(manifest.get("staging_id", staging_id)) != staging_id:
        raise SystemExit("staging manifest id mismatch")
    return manifest


def policy(root: Path) -> dict[str, Any]:
    path = root / "market_bomb_config" / "flow_pressure_research_v0_policy.json"
    if path.exists():
        return load_json(path)
    return {
        "artifact_version": ARTIFACT_VERSION,
        "implemented_modules": sorted(IMPLEMENTED_MODULES),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
        "min_rows_per_implemented_module": 5,
        "max_source_staleness_days": 7,
        "vol_control_windows": [5, 10, 20],
        "vol_control_target_vols": [0.10, 0.12],
        "vol_control_max_exposure": 1.0,
        "backtest_forward_days": [1, 3, 5],
    }


def validate_manifest_and_sources(root: Path, staging_id: str, now_utc: pd.Timestamp | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = load_staging_manifest(root, staging_id)
    sources = manifest.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise SystemExit("staging manifest must include non-empty sources")
    now = now_utc or utc_now()
    seen_paths: set[str] = set()
    seen_source_ids: set[str] = set()
    audit_rows: list[dict[str, Any]] = []
    for source in sources:
        for field in REQUIRED_SOURCE_FIELDS:
            if source.get(field) in [None, ""]:
                raise SystemExit(f"missing required source field: {field}")
        module = str(source.get("module", "") or source.get("feature_module", ""))
        if module and module not in SUPPORTED_MODULES:
            raise SystemExit(f"unsupported source module: {module}")
        source_id = str(source.get("source_id"))
        if source_id in seen_source_ids:
            raise SystemExit(f"duplicate source_id: {source_id}")
        seen_source_ids.add(source_id)
        rel = validate_source_relative_path(source.get("relative_path"))
        if rel in seen_paths:
            raise SystemExit(f"duplicate staged source path: {rel}")
        seen_paths.add(rel)
        source_path = staged_source_path(root, staging_id, source)
        if source_path.is_symlink():
            raise SystemExit(f"symlink staged source is not allowed: {rel}")
        exists = source_path.exists() and source_path.is_file()
        if not exists:
            raise SystemExit(f"missing staged source file: {rel}")
        source_as_of = parse_utc_ts(source.get("source_as_of_timestamp"), "source_as_of_timestamp")
        available_at = parse_utc_ts(source.get("available_at_timestamp"), "available_at_timestamp")
        market_ts = parse_utc_ts(source.get("market_timestamp"), "market_timestamp")
        if market_ts > available_at:
            raise SystemExit("market_timestamp cannot be after available_at_timestamp")
        if source_as_of > available_at:
            raise SystemExit("source_as_of_timestamp cannot be after available_at_timestamp")
        if available_at > now:
            raise SystemExit("available_at_timestamp cannot be in the future relative to decision time")
        audit_rows.append(
            {
                "source_id": source_id,
                "source_name": source.get("source_name", ""),
                "source_file": source.get("source_file", ""),
                "relative_path": rel,
                "instrument": str(source.get("instrument", "")).upper(),
                "asset_class": source.get("asset_class", ""),
                "module": module,
                "source_as_of": iso_utc(source_as_of),
                "available_at": iso_utc(available_at),
                "market_timestamp": iso_utc(market_ts),
                "dataset_version": source.get("dataset_version", ""),
                "source_file_sha256": file_sha256(source_path),
                "source_file_bytes": source_path.stat().st_size,
                "source_path_valid": True,
            }
        )
    return manifest, sources, audit_rows


def normalize_source_frame(path: Path, source: dict[str, Any]) -> pd.DataFrame:
    df = pd.read_csv(path)
    lower = {str(c).lower(): c for c in df.columns}
    date_col = lower.get("date") or lower.get("session_date") or lower.get("coverage_date")
    close_col = lower.get("close") or lower.get("adjusted_close") or lower.get("nav")
    aum_col = lower.get("aum") or lower.get("assets") or lower.get("net_assets")
    shares_col = lower.get("shares_outstanding")
    nav_col = lower.get("nav")
    if date_col is None:
        raise SystemExit(f"source missing date/session_date column: {source.get('source_id')}")
    out = pd.DataFrame()
    out["session_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    out["instrument"] = str(source.get("instrument", "")).upper()
    out["source_id"] = source.get("source_id", "")
    out["module"] = source.get("module", source.get("feature_module", ""))
    out["close"] = pd.to_numeric(df[close_col], errors="coerce") if close_col else np.nan
    out["aum"] = pd.to_numeric(df[aum_col], errors="coerce") if aum_col else np.nan
    out["shares_outstanding"] = pd.to_numeric(df[shares_col], errors="coerce") if shares_col else np.nan
    out["nav"] = pd.to_numeric(df[nav_col], errors="coerce") if nav_col else out["close"]
    if out["aum"].isna().all() and not out["shares_outstanding"].isna().all():
        out["aum"] = out["shares_outstanding"] * out["nav"]
    out["source_as_of"] = iso_utc(parse_utc_ts(source.get("source_as_of_timestamp"), "source_as_of_timestamp"))
    out["available_at"] = iso_utc(parse_utc_ts(source.get("available_at_timestamp"), "available_at_timestamp"))
    out["market_timestamp"] = iso_utc(parse_utc_ts(source.get("market_timestamp"), "market_timestamp"))
    out["dataset_version"] = source.get("dataset_version", "")
    out["row_hash"] = [
        bytes_sha256("|".join(str(v) for v in row).encode("utf-8"))
        for row in out[["session_date", "instrument", "close", "aum", "available_at"]].fillna("").to_numpy()
    ]
    return out.dropna(subset=["session_date"]).sort_values(["instrument", "session_date"]).reset_index(drop=True)


def source_inventory(root: Path, staging_id: str, sources: list[dict[str, Any]]) -> pd.DataFrame:
    frames = []
    for source in sources:
        path = staged_source_path(root, staging_id, source)
        df = normalize_source_frame(path, source)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_leveraged_universe(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("leveraged_etf_universe"):
        return list(manifest["leveraged_etf_universe"])
    cfg = root / "market_bomb_config" / "flow_pressure_research_v0_policy.json"
    p = policy(root)
    if p.get("leveraged_etf_universe"):
        return list(p["leveraged_etf_universe"])
    existing = root / "market_bomb_config" / "leveraged_etf_universe_v1.json"
    rows: list[dict[str, Any]] = []
    if existing.exists():
        data = load_json(existing)
        for items in data.values():
            if isinstance(items, list):
                rows.extend(items)
    return rows


def build_leveraged_etf_features(root: Path, manifest: dict[str, Any], canonical: pd.DataFrame) -> pd.DataFrame:
    rows = []
    universe = load_leveraged_universe(root, manifest)
    by_ticker = {ticker: g.sort_values("session_date").copy() for ticker, g in canonical.groupby("instrument")}
    for item in universe:
        etf = str(item.get("ticker", "")).upper()
        target = str(item.get("target") or item.get("underlying", "")).upper()
        leverage = float(item.get("leverage", np.nan))
        if etf not in by_ticker or target not in by_ticker or not np.isfinite(leverage):
            continue
        e = by_ticker[etf].copy()
        u = by_ticker[target].copy()
        e["etf_return_1d"] = pd.to_numeric(e["close"], errors="coerce").pct_change()
        e["prior_aum"] = pd.to_numeric(e["aum"], errors="coerce").shift(1)
        u["underlying_return_1d"] = pd.to_numeric(u["close"], errors="coerce").pct_change()
        merged = e.merge(u[["session_date", "close", "underlying_return_1d"]], on="session_date", how="left", suffixes=("", "_underlying"))
        for _, row in merged.iterrows():
            prior_aum = float(row.get("prior_aum", np.nan))
            uret = float(row.get("underlying_return_1d", np.nan))
            pressure = prior_aum * leverage * (leverage - 1.0) * uret if np.isfinite(prior_aum) and np.isfinite(uret) else np.nan
            exposure = prior_aum * leverage if np.isfinite(prior_aum) else np.nan
            normalized = pressure / abs(exposure) if np.isfinite(pressure) and np.isfinite(exposure) and exposure else np.nan
            rows.append(
                {
                    "module": "leveraged_etf_rebalance",
                    "feature_name": "theoretical_rebalance_pressure",
                    "instrument": etf,
                    "underlying": target,
                    "as_of_date": row["session_date"],
                    "source_as_of": row["source_as_of"],
                    "available_at": row["available_at"],
                    "feature_state": "available" if np.isfinite(pressure) else "insufficient_coverage",
                    "data_quality_state": "valid" if np.isfinite(pressure) else "insufficient_coverage",
                    "methodology_version": METHODOLOGY_VERSION,
                    "source_coverage": "prior_aum_and_underlying_return" if np.isfinite(pressure) else "missing_prior_aum_or_return",
                    "confidence": "medium" if np.isfinite(pressure) else "low",
                    "coverage_tier": "sufficient" if np.isfinite(pressure) else "insufficient",
                    "pressure_direction": "buy" if pressure > 0 else "sell" if pressure < 0 else "neutral",
                    "pressure_value": pressure,
                    "pressure_normalized": normalized,
                    "is_observed_flow": False,
                    "is_model_estimate": True,
                    "explicit_limitations": "theoretical rebalance pressure only; not observed ETF flow",
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
    return pd.DataFrame(rows)


def build_vol_control_features(root: Path, canonical: pd.DataFrame) -> pd.DataFrame:
    p = policy(root)
    windows = [int(x) for x in p.get("vol_control_windows", [5, 10, 20])]
    targets = [float(x) for x in p.get("vol_control_target_vols", [0.10, 0.12])]
    max_exp = float(p.get("vol_control_max_exposure", 1.0))
    rows = []
    for ticker, g in canonical.groupby("instrument"):
        df = g.sort_values("session_date").copy()
        if df["close"].isna().all():
            continue
        px = pd.to_numeric(df["close"], errors="coerce")
        df["return_1d"] = px.pct_change()
        for window in windows:
            vol = df["return_1d"].rolling(window, min_periods=window).std() * math.sqrt(252)
            for target in targets:
                exposure = (target / vol).clip(upper=max_exp)
                exposure = exposure.where(vol > 0)
                change = exposure.diff()
                for idx, row in df.iterrows():
                    exp_value = float(exposure.loc[idx]) if pd.notna(exposure.loc[idx]) else np.nan
                    change_value = float(change.loc[idx]) if pd.notna(change.loc[idx]) else np.nan
                    pressure = change_value
                    rows.append(
                        {
                            "module": "vol_control_deleveraging",
                            "feature_name": f"target_vol_{target:g}_window_{window}",
                            "instrument": ticker,
                            "underlying": ticker,
                            "as_of_date": row["session_date"],
                            "source_as_of": row["source_as_of"],
                            "available_at": row["available_at"],
                            "feature_state": "available" if np.isfinite(pressure) else "insufficient_coverage",
                            "data_quality_state": "valid" if np.isfinite(pressure) else "insufficient_coverage",
                            "methodology_version": METHODOLOGY_VERSION,
                            "source_coverage": f"{window}d_realized_vol" if np.isfinite(pressure) else "missing_return_window",
                            "confidence": "medium" if np.isfinite(pressure) else "low",
                            "coverage_tier": "sufficient" if np.isfinite(pressure) else "insufficient",
                            "pressure_direction": "buy" if pressure > 0 else "sell" if pressure < 0 else "neutral",
                            "pressure_value": pressure,
                            "pressure_normalized": pressure,
                            "vol_control_exposure": exp_value,
                            "is_observed_flow": False,
                            "is_model_estimate": True,
                            "explicit_limitations": "normalized target-vol pressure proxy; AUM not assumed",
                            "actionization_allowed": ACTIONIZATION_ALLOWED,
                        }
                    )
    return pd.DataFrame(rows)


def placeholder_module_rows() -> pd.DataFrame:
    rows = []
    for module in sorted(SUPPORTED_MODULES - IMPLEMENTED_MODULES):
        rows.append(
            {
                "module": module,
                "feature_name": "placeholder",
                "instrument": "",
                "underlying": "",
                "as_of_date": "",
                "source_as_of": "",
                "available_at": "",
                "feature_state": "methodology_incomplete",
                "data_quality_state": "methodology_incomplete",
                "methodology_version": METHODOLOGY_VERSION,
                "source_coverage": "not_implemented_in_phase_1_2",
                "confidence": "none",
                "coverage_tier": "unavailable",
                "pressure_direction": "unknown",
                "pressure_value": np.nan,
                "pressure_normalized": np.nan,
                "is_observed_flow": False,
                "is_model_estimate": True,
                "explicit_limitations": "placeholder only; no inference or actionization",
                "actionization_allowed": ACTIONIZATION_ALLOWED,
            }
        )
    return pd.DataFrame(rows)


def build_features(root: Path, manifest: dict[str, Any], canonical: pd.DataFrame) -> pd.DataFrame:
    frames = [
        build_leveraged_etf_features(root, manifest, canonical),
        build_vol_control_features(root, canonical),
        placeholder_module_rows(),
    ]
    return pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True)


def build_backtest_results(root: Path, features: pd.DataFrame, canonical: pd.DataFrame) -> pd.DataFrame:
    p = policy(root)
    forward_days = [int(x) for x in p.get("backtest_forward_days", [1, 3, 5])]
    prices = canonical[["instrument", "session_date", "close"]].dropna().copy()
    prices = prices.sort_values(["instrument", "session_date"])
    result_rows = []
    available = features[features["feature_state"] == "available"].copy()
    if available.empty:
        return pd.DataFrame(columns=["module", "feature_name", "forward_days", "sample_count", "hit_rate", "median_forward_return", "downside_p10", "effect_size", "interpretation"])
    for (module, feature_name), g in available.groupby(["module", "feature_name"]):
        for horizon in forward_days:
            sample_rows = []
            for _, feat in g.iterrows():
                target = str(feat.get("underlying") or feat.get("instrument"))
                px = prices[prices["instrument"] == target].reset_index(drop=True)
                idx = px.index[px["session_date"] == feat["as_of_date"]]
                if len(idx) == 0:
                    continue
                i = int(idx[0])
                if i + horizon >= len(px):
                    continue
                ret = float(px.loc[i + horizon, "close"] / px.loc[i, "close"] - 1.0)
                pressure = float(feat.get("pressure_normalized", np.nan))
                sample_rows.append({"forward_return": ret, "pressure": pressure})
            sample = pd.DataFrame(sample_rows).replace([np.inf, -np.inf], np.nan).dropna()
            if sample.empty:
                continue
            signed = sample["forward_return"] * np.sign(sample["pressure"])
            high = sample[sample["pressure"].abs() >= sample["pressure"].abs().median()]
            low = sample[sample["pressure"].abs() < sample["pressure"].abs().median()]
            effect = float(high["forward_return"].median() - low["forward_return"].median()) if not high.empty and not low.empty else np.nan
            result_rows.append(
                {
                    "module": module,
                    "feature_name": feature_name,
                    "forward_days": horizon,
                    "sample_count": len(sample),
                    "hit_rate": float((signed > 0).mean()),
                    "median_forward_return": float(sample["forward_return"].median()),
                    "downside_p10": float(sample["forward_return"].quantile(0.10)),
                    "effect_size": effect,
                    "interpretation": "exploratory_descriptive_only",
                    "actionization_allowed": ACTIONIZATION_ALLOWED,
                }
            )
    return pd.DataFrame(result_rows)


def source_coverage_audit(sources: list[dict[str, Any]], canonical: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for source in sources:
        instrument = str(source.get("instrument", "")).upper()
        df = canonical[canonical["instrument"] == instrument]
        rows.append(
            {
                "source_id": source.get("source_id", ""),
                "instrument": instrument,
                "module": source.get("module", source.get("feature_module", "")),
                "coverage_start_date": source.get("coverage_start_date", ""),
                "coverage_end_date": source.get("coverage_end_date", ""),
                "canonical_row_count": len(df),
                "coverage_status": "valid" if len(df) else "insufficient_coverage",
                "coverage_reason": "valid" if len(df) else "no_canonical_rows",
            }
        )
    return pd.DataFrame(rows)


def source_timeliness_audit(sources: list[dict[str, Any]], now_utc: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for source in sources:
        available_at = parse_utc_ts(source.get("available_at_timestamp"), "available_at_timestamp")
        rows.append(
            {
                "source_id": source.get("source_id", ""),
                "instrument": str(source.get("instrument", "")).upper(),
                "available_at": iso_utc(available_at),
                "decision_time_utc": iso_utc(now_utc),
                "age_hours": round((now_utc - available_at).total_seconds() / 3600, 6),
                "timeliness_status": "valid" if available_at <= now_utc else "data_quality_blocked",
                "timeliness_reason": "valid" if available_at <= now_utc else "available_at_after_decision_time",
            }
        )
    return pd.DataFrame(rows)


def feature_quality_gate(root: Path, features: pd.DataFrame, coverage: pd.DataFrame, timeliness: pd.DataFrame) -> pd.DataFrame:
    p = policy(root)
    min_rows = int(p.get("min_rows_per_implemented_module", 5))
    rows = []
    hard_block = False
    for module in sorted(SUPPORTED_MODULES):
        module_features = features[features["module"] == module]
        available_count = int((module_features["feature_state"] == "available").sum()) if not module_features.empty else 0
        if module in IMPLEMENTED_MODULES:
            ok = available_count >= min_rows
            status = "valid_research_candidate" if ok else "insufficient_coverage"
            reason = "valid" if ok else "implemented_module_insufficient_feature_rows"
            hard_block = hard_block or not ok
        else:
            status = "methodology_incomplete"
            reason = "placeholder_not_actionable"
        rows.append({"gate_scope": "module", "module": module, "quality_gate_status": status, "quality_gate_reason": reason, "available_feature_count": available_count, "actionization_allowed": ACTIONIZATION_ALLOWED})
    if (timeliness["timeliness_status"] == "data_quality_blocked").any():
        release_status = "data_quality_blocked"
        release_reason = "timeliness_blocked"
    elif hard_block:
        release_status = "insufficient_coverage"
        release_reason = "one_or_more_implemented_modules_insufficient"
    else:
        release_status = "valid_research_candidate"
        release_reason = "valid_for_research_only"
    rows.append({"gate_scope": "release", "module": "ALL", "quality_gate_status": release_status, "quality_gate_reason": release_reason, "available_feature_count": int((features["feature_state"] == "available").sum()), "actionization_allowed": ACTIONIZATION_ALLOWED})
    return pd.DataFrame(rows)


def release_core_files(rel: Path) -> list[Path]:
    files: list[Path] = []
    for base in [rel / "canonical_input", rel / "features"]:
        pbase = platform_path(base)
        if pbase.exists():
            files.extend([p for p in pbase.rglob("*") if p.is_file()])
    for name in [
        "release_core_metadata.json",
        "source_coverage_audit.csv",
        "source_timeliness_audit.csv",
        "feature_quality_gate.csv",
        "module_methodology.json",
        "parameter_registry.json",
        "backtest_spec.json",
        "backtest_results.csv",
        "backtest_summary.md",
        "explicit_limitations.md",
    ]:
        path = platform_path(rel / name)
        if path.exists():
            files.append(path)
    return sorted(files, key=lambda p: safe_relative_path(rel, p))


def content_set_hash(entries: list[dict[str, Any]]) -> str:
    parts = [f"{e['relative_path']}\0{e['sha256']}\0{e['bytes']}\n" for e in sorted(entries, key=lambda x: x["relative_path"])]
    return bytes_sha256("".join(parts).encode("utf-8"))


def write_content_manifest(rel: Path, release_id: str) -> dict[str, Any]:
    entries = []
    seen: set[str] = set()
    for path in release_core_files(rel):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"unsafe release core path: {path}")
        relative = safe_relative_path(rel, path)
        if relative in seen:
            raise SystemExit(f"duplicate release core path: {relative}")
        seen.add(relative)
        entries.append({"relative_path": relative, "sha256": file_sha256(path), "bytes": path.stat().st_size, "required": True})
    manifest = {
        "artifact_version": RELEASE_CONTENT_MANIFEST_VERSION,
        "release_id": release_id,
        "created_at_utc": iso_utc(utc_now()),
        "content_set_kind": "immutable_flow_pressure_research_release_core",
        "core_content_set_sha256": content_set_hash(entries),
        "entries": entries,
    }
    write_json(content_manifest_path(rel), manifest)
    return manifest


def release_core_metadata(root: Path, staging_id: str, release_id: str, manifest: dict[str, Any], gate: pd.DataFrame) -> dict[str, Any]:
    release_row = gate[gate["gate_scope"] == "release"].iloc[0].to_dict()
    return {
        "artifact_version": RELEASE_CORE_METADATA_VERSION,
        "release_id": release_id,
        "staging_id": staging_id,
        "built_at_utc": iso_utc(utc_now()),
        "source_bundle_sha256_at_build": compute_bundle_hash(root, staging_id, manifest),
        "release_quality_status": release_row.get("quality_gate_status", "data_quality_blocked"),
        "release_quality_reason": release_row.get("quality_gate_reason", ""),
        "implemented_modules": sorted(IMPLEMENTED_MODULES),
        "placeholder_modules": sorted(SUPPORTED_MODULES - IMPLEMENTED_MODULES),
        "methodology_version": METHODOLOGY_VERSION,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def release_receipt(rel: Path, release_id: str, content_manifest: dict[str, Any]) -> dict[str, Any]:
    metadata_path = rel / "release_core_metadata.json"
    return {
        "artifact_version": ARTIFACT_VERSION,
        "release_id": release_id,
        "release_content_manifest_sha256": file_sha256(content_manifest_path(rel)),
        "release_core_content_set_sha256": content_manifest.get("core_content_set_sha256", ""),
        "release_core_metadata_sha256": file_sha256(metadata_path),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def compute_bundle_hash(root: Path, staging_id: str, manifest: dict[str, Any]) -> str:
    sources = manifest.get("sources", [])
    pieces = [json.dumps({k: v for k, v in manifest.items() if k != "sources"}, sort_keys=True)]
    for source in sorted(sources, key=lambda s: str(s.get("source_id", ""))):
        path = staged_source_path(root, staging_id, source)
        pieces.append(json.dumps(source, sort_keys=True))
        pieces.append(file_sha256(path))
    return bytes_sha256("\n".join(pieces).encode("utf-8"))


def make_release_id(root: Path, staging_id: str, manifest: dict[str, Any]) -> str:
    digest = compute_bundle_hash(root, staging_id, manifest)[:12]
    return f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{digest}"


def backtest_summary_md(results: pd.DataFrame, gate: pd.DataFrame) -> str:
    def md_table(df: pd.DataFrame) -> str:
        if df.empty:
            return "_No rows._"
        clean = df.fillna("").astype(str)
        cols = list(clean.columns)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, row in clean.iterrows():
            lines.append("| " + " | ".join(str(row[c]).replace("|", "\\|").replace("\n", " ") for c in cols) + " |")
        return "\n".join(lines)

    lines = [
        "# Flow Pressure Research v0 Backtest Summary",
        "",
        "This release is exploratory research only. It does not authorize trading, notification, or automated execution.",
        "",
        "## Quality Gate",
        md_table(gate),
        "",
        "## Results",
        md_table(results),
        "",
        "## Interpretation",
        "Reported relationships are descriptive and exploratory. No fitted calibration, optimized thresholds, or actionization are included.",
    ]
    return "\n".join(lines) + "\n"


def build_release(root: Path, staging_id: str, now_utc: str | None = None) -> str:
    now = parse_now_utc(now_utc) or utc_now()
    manifest, sources, audit_rows = validate_manifest_and_sources(root, staging_id, now)
    release_id = make_release_id(root, staging_id, manifest)
    final_rel = release_dir(root, release_id)
    if final_rel.exists():
        raise SystemExit(f"release already exists: {release_id}")
    releases_dir(root).mkdir(parents=True, exist_ok=True)
    rel = releases_dir(root) / f".building_{release_id}_{uuid.uuid4().hex[:8]}"
    rel.mkdir(parents=True, exist_ok=False)
    try:
        canonical = source_inventory(root, staging_id, sources)
        features = build_features(root, manifest, canonical)
        coverage = source_coverage_audit(sources, canonical)
        timeliness = source_timeliness_audit(sources, now)
        gate = feature_quality_gate(root, features, coverage, timeliness)
        backtest = build_backtest_results(root, features, canonical)
        write_csv(canonical, rel / "canonical_input" / "flow_pressure_canonical_source_rows.csv")
        write_csv(features, rel / "features" / "flow_pressure_features.csv")
        write_csv(pd.DataFrame(audit_rows), rel / "source_file_inventory.csv")
        write_csv(coverage, rel / "source_coverage_audit.csv")
        write_csv(timeliness, rel / "source_timeliness_audit.csv")
        write_csv(gate, rel / "feature_quality_gate.csv")
        write_csv(backtest, rel / "backtest_results.csv")
        write_json(rel / "module_methodology.json", module_methodology())
        write_json(rel / "parameter_registry.json", parameter_registry(root))
        write_json(rel / "backtest_spec.json", backtest_spec(root))
        (rel / "backtest_summary.md").write_text(backtest_summary_md(backtest, gate), encoding="utf-8")
        (rel / "explicit_limitations.md").write_text(explicit_limitations_text(), encoding="utf-8")
        write_json(rel / "release_core_metadata.json", release_core_metadata(root, staging_id, release_id, manifest, gate))
        content_manifest = write_content_manifest(rel, release_id)
        write_json(receipt_path(rel), release_receipt(rel, release_id, content_manifest))
        rel.replace(final_rel)
        verify_release(root, release_id)
        return release_id
    except Exception:
        if rel.exists():
            shutil.rmtree(platform_path(rel), ignore_errors=True)
        raise


def module_methodology() -> dict[str, Any]:
    return {
        "artifact_version": METHODOLOGY_VERSION,
        "modules": {
            "leveraged_etf_rebalance": "Theoretical rebalance pressure from prior available AUM, target leverage, and underlying return.",
            "vol_control_deleveraging": "Normalized target-vol exposure change from realized volatility windows.",
            "cta_trend_flow": "Placeholder only in this release.",
            "dealer_gamma_regime": "Placeholder only in this release.",
        },
        "all_pressure_fields_are": "model-implied pressure proxies; not observed institutional flow",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def parameter_registry(root: Path) -> dict[str, Any]:
    p = policy(root)
    return {
        "artifact_version": ARTIFACT_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "vol_control_windows": p.get("vol_control_windows", [5, 10, 20]),
        "vol_control_target_vols": p.get("vol_control_target_vols", [0.10, 0.12]),
        "vol_control_max_exposure": p.get("vol_control_max_exposure", 1.0),
        "backtest_forward_days": p.get("backtest_forward_days", [1, 3, 5]),
        "leveraged_etf_universe": p.get("leveraged_etf_universe", []),
    }


def backtest_spec(root: Path) -> dict[str, Any]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "targets": ["forward close-to-close returns"],
        "forward_days": policy(root).get("backtest_forward_days", [1, 3, 5]),
        "metrics": ["hit_rate", "median_forward_return", "downside_p10", "effect_size", "sample_count"],
        "overfitting_guard": "descriptive only; no best-parameter adoption",
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def explicit_limitations_text() -> str:
    return (
        "# Explicit Limitations\n\n"
        "- All outputs are research-only model-implied pressure proxies.\n"
        "- No output is observed institutional flow, dealer positioning, or actual CTA/vol-control order flow.\n"
        "- `actionization_allowed=false`; do not connect this release to notifications, execution, or trading gates.\n"
        "- No network fetch, scraping, forward fill, fitted calibration, source coalescing, or calendar fallback is performed.\n"
        "- CTA and Dealer modules are placeholders until source contracts and methodology are complete.\n"
    )


def validate_content_manifest(rel: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("artifact_version") != RELEASE_CONTENT_MANIFEST_VERSION:
        raise SystemExit("unsupported flow release content manifest version")
    entries = manifest.get("entries", [])
    if not isinstance(entries, list) or not entries:
        raise SystemExit("empty flow release content manifest")
    seen: set[str] = set()
    recomputed = []
    for entry in entries:
        relative = str(entry.get("relative_path", ""))
        if not relative or relative.startswith("/") or relative.startswith("\\") or ".." in PurePosixPath(relative).parts:
            raise SystemExit(f"unsafe release content path: {relative}")
        if relative in seen:
            raise SystemExit(f"duplicate release content path: {relative}")
        seen.add(relative)
        path = rel / relative
        safe_relative_path(rel, path)
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"missing or unsafe release core file: {relative}")
        sha = file_sha256(path)
        size = path.stat().st_size
        if str(entry.get("sha256", "")) != sha:
            raise SystemExit(f"release core sha mismatch: {relative}")
        if int(entry.get("bytes", -1)) != size:
            raise SystemExit(f"release core size mismatch: {relative}")
        recomputed.append({"relative_path": relative, "sha256": sha, "bytes": size})
    actual = {safe_relative_path(rel, p) for p in release_core_files(rel)}
    if actual != seen:
        raise SystemExit("release core file set does not match content manifest")
    if manifest.get("core_content_set_sha256") != content_set_hash(recomputed):
        raise SystemExit("release core content set hash mismatch")


def verify_release(root: Path, release_id: str) -> dict[str, Any]:
    rel = release_dir(root, release_id)
    if not rel.exists() or rel.name != release_id:
        raise SystemExit(f"missing release: {release_id}")
    receipt = load_json(receipt_path(rel))
    manifest = load_json(content_manifest_path(rel))
    if receipt.get("release_id") != release_id or manifest.get("release_id") != release_id:
        raise SystemExit("flow release id mismatch")
    if receipt.get("release_content_manifest_sha256") != file_sha256(content_manifest_path(rel)):
        raise SystemExit("flow release manifest hash mismatch")
    validate_content_manifest(rel, manifest)
    metadata_path = rel / "release_core_metadata.json"
    metadata_sha = file_sha256(metadata_path)
    if receipt.get("release_core_metadata_sha256") != metadata_sha:
        raise SystemExit("flow release core metadata hash mismatch")
    metadata = load_json(metadata_path)
    gate = pd.read_csv(rel / "feature_quality_gate.csv")
    release_rows = gate[gate["gate_scope"] == "release"]
    if len(release_rows) != 1:
        raise SystemExit("flow release gate must have exactly one release row")
    release_status = str(release_rows.iloc[0]["quality_gate_status"])
    if release_status != str(metadata.get("release_quality_status")):
        raise SystemExit("flow release metadata status mismatch")
    features = pd.read_csv(rel / "features" / "flow_pressure_features.csv")
    required_cols = {"feature_state", "data_quality_state", "methodology_version", "source_coverage", "source_as_of", "available_at", "as_of_date", "is_observed_flow", "is_model_estimate"}
    if not required_cols.issubset(features.columns):
        raise SystemExit("flow feature output missing required fields")
    if bool(features["is_observed_flow"].fillna(False).astype(bool).any()):
        raise SystemExit("flow release cannot mark model proxies as observed flow")
    if bool(pd.Series(features["actionization_allowed"]).fillna(False).astype(bool).any()):
        raise SystemExit("flow release cannot allow actionization")
    return {
        **metadata,
        "release_content_manifest_sha256": file_sha256(content_manifest_path(rel)),
        "release_core_content_set_sha256": manifest.get("core_content_set_sha256", ""),
        "release_core_metadata_sha256": metadata_sha,
    }


def verify_staging(root: Path, staging_id: str, now_utc: str | None = None) -> dict[str, Any]:
    now = parse_now_utc(now_utc) or utc_now()
    manifest, sources, audit_rows = validate_manifest_and_sources(root, staging_id, now)
    before_releases = releases_dir(root).exists()
    with tempfile.TemporaryDirectory(prefix="flow_pressure_preflight_") as tmp:
        temp_root = Path(tmp) / "repo"
        temp_stage = staging_dir(temp_root, staging_id)
        temp_stage.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging_dir(root, staging_id), temp_stage)
        cfg_src = root / "market_bomb_config"
        cfg_dst = temp_root / "market_bomb_config"
        if cfg_src.exists():
            shutil.copytree(cfg_src, cfg_dst)
        release_id = build_release(temp_root, staging_id, now_utc=iso_utc(now))
        verified = verify_release(temp_root, release_id)
    if releases_dir(root).exists() != before_releases:
        raise SystemExit("verify-flow-staging attempted to mutate source release directory")
    return {
        "artifact_version": ARTIFACT_VERSION,
        "staging_id": staging_id,
        "candidate_quality_status": verified.get("release_quality_status", ""),
        "candidate_quality_reason": verified.get("release_quality_reason", ""),
        "source_count": len(sources),
        "source_bundle_sha256": compute_bundle_hash(root, staging_id, manifest),
        "validated_sources": audit_rows,
        "preflight_release_id_preview": release_id,
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def run_flow_backtest(root: Path, release_id: str) -> str:
    verify_release(root, release_id)
    rel = release_dir(root, release_id)
    run_id = f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    out = rel / "backtest_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    for name in ["backtest_results.csv", "backtest_summary.md", "backtest_spec.json"]:
        shutil.copyfile(rel / name, out / name)
    manifest = build_backtest_content_manifest(out, release_id, run_id)
    write_json(out / "backtest_content_manifest.json", manifest)
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "release_id": release_id,
        "backtest_run_id": run_id,
        "run_at_utc": iso_utc(utc_now()),
        "backtest_content_manifest_sha256": file_sha256(out / "backtest_content_manifest.json"),
        "release_content_manifest_sha256": file_sha256(content_manifest_path(rel)),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }
    write_json(out / "backtest_receipt.json", receipt)
    verify_backtest(root, release_id, run_id)
    return run_id


def build_backtest_content_manifest(run_dir: Path, release_id: str, run_id: str) -> dict[str, Any]:
    entries = []
    for path in sorted([p for p in platform_path(run_dir).rglob("*") if p.is_file()], key=lambda p: str(p)):
        relative = safe_relative_path(run_dir, path)
        if relative in {"backtest_content_manifest.json", "backtest_receipt.json"}:
            continue
        entries.append({"relative_path": relative, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {
        "artifact_version": BACKTEST_CONTENT_MANIFEST_VERSION,
        "release_id": release_id,
        "backtest_run_id": run_id,
        "entries": entries,
        "content_set_sha256": content_set_hash(entries),
    }


def verify_backtest(root: Path, release_id: str, run_id: str) -> dict[str, Any]:
    verify_release(root, release_id)
    run_dir = release_dir(root, release_id) / "backtest_runs" / run_id
    manifest = load_json(run_dir / "backtest_content_manifest.json")
    receipt = load_json(run_dir / "backtest_receipt.json")
    if manifest.get("artifact_version") != BACKTEST_CONTENT_MANIFEST_VERSION:
        raise SystemExit("unsupported flow backtest manifest version")
    if manifest.get("release_id") != release_id or receipt.get("release_id") != release_id:
        raise SystemExit("flow backtest release id mismatch")
    if receipt.get("backtest_content_manifest_sha256") != file_sha256(run_dir / "backtest_content_manifest.json"):
        raise SystemExit("flow backtest manifest hash mismatch")
    seen = set()
    recomputed = []
    for entry in manifest.get("entries", []):
        relative = str(entry.get("relative_path", ""))
        if not relative or ".." in PurePosixPath(relative).parts:
            raise SystemExit(f"unsafe flow backtest path: {relative}")
        seen.add(relative)
        path = run_dir / relative
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"missing flow backtest file: {relative}")
        sha = file_sha256(path)
        if sha != entry.get("sha256"):
            raise SystemExit(f"flow backtest sha mismatch: {relative}")
        recomputed.append({"relative_path": relative, "sha256": sha, "bytes": path.stat().st_size})
    actual = {safe_relative_path(run_dir, p) for p in platform_path(run_dir).rglob("*") if p.is_file() and safe_relative_path(run_dir, p) not in {"backtest_content_manifest.json", "backtest_receipt.json"}}
    if actual != seen:
        raise SystemExit("flow backtest file set mismatch")
    if manifest.get("content_set_sha256") != content_set_hash(recomputed):
        raise SystemExit("flow backtest content set hash mismatch")
    return {"release_id": release_id, "backtest_run_id": run_id, "status": "valid"}


def inspect_release(root: Path, release_id: str) -> dict[str, Any]:
    meta = verify_release(root, release_id)
    rel = release_dir(root, release_id)
    gate = pd.read_csv(rel / "feature_quality_gate.csv")
    features = pd.read_csv(rel / "features" / "flow_pressure_features.csv")
    return {
        "release_id": release_id,
        "release_quality_status": meta.get("release_quality_status"),
        "module_gate": gate.to_dict("records"),
        "feature_count": len(features),
        "available_feature_count": int((features["feature_state"] == "available").sum()),
        "actionization_allowed": ACTIONIZATION_ALLOWED,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Flow Pressure Research v0 release/backtest CLI")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify-flow-staging")
    p.add_argument("--staging-id", required=True)
    p.add_argument("--now-utc")
    p = sub.add_parser("build-flow-release")
    p.add_argument("--staging-id", required=True)
    p.add_argument("--now-utc")
    p = sub.add_parser("verify-flow-release")
    p.add_argument("--release-id", required=True)
    p = sub.add_parser("run-flow-backtest")
    p.add_argument("--release-id", required=True)
    p = sub.add_parser("verify-flow-backtest")
    p.add_argument("--release-id", required=True)
    p.add_argument("--backtest-run-id", required=True)
    p = sub.add_parser("inspect-flow-release")
    p.add_argument("--release-id", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    if args.command == "verify-flow-staging":
        result = verify_staging(root, args.staging_id, args.now_utc)
    elif args.command == "build-flow-release":
        result = {"release_id": build_release(root, args.staging_id, args.now_utc)}
    elif args.command == "verify-flow-release":
        result = verify_release(root, args.release_id)
    elif args.command == "run-flow-backtest":
        result = {"backtest_run_id": run_flow_backtest(root, args.release_id)}
    elif args.command == "verify-flow-backtest":
        result = verify_backtest(root, args.release_id, args.backtest_run_id)
    elif args.command == "inspect-flow-release":
        result = inspect_release(root, args.release_id)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
