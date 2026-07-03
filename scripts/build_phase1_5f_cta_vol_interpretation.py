from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "config" / "research_review_v1" / "phase1_5f_cta_vol_interpretation_spec.json"
CTA_RUN_MANIFEST = "cta_content_manifest.json"
CTA_RUN_RECEIPT = "cta_run_receipt.json"
CTA_DAILY = "cta_daily_exposure.csv"
CTA_ROBUSTNESS_MANIFEST = "cta_cot_robustness_content_manifest.json"
CTA_ROBUSTNESS_RECEIPT = "cta_cot_robustness_receipt.json"
CTA_ROBUSTNESS_SUMMARY = "cta_cot_robustness_summary.csv"
VOL_RUN_MANIFEST = "vol_control_content_manifest.json"
VOL_RUN_RECEIPT = "vol_control_run_receipt.json"
VOL_DAILY = "vol_control_daily_exposure.csv"
VOL_CHARACTERIZATION_MANIFEST = "vol_control_cross_spec_content_manifest.json"
VOL_CHARACTERIZATION_RECEIPT = "vol_control_cross_spec_receipt.json"
VOL_SUMMARY = "vol_control_cross_spec_summary.csv"
VOL_PAIRWISE = "vol_control_cross_spec_pairwise_dispersion.csv"
FORBIDDEN_OUTPUT_FIELDS = {
    "raw_close",
    "benchmark_return",
    "realized_volatility",
    "price",
    "return",
    "returns",
    "pnl",
    "future_outcome",
    "forward_return",
}


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    lower = {name.lower() for name in fieldnames}
    blocked = sorted(lower & FORBIDDEN_OUTPUT_FIELDS)
    if blocked:
        raise SystemExit(f"forbidden_output_field:{','.join(blocked)}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: str | Path) -> Path:
    return Path(path).resolve()


def verify_manifested_artifact(path: Path, manifest_name: str) -> None:
    manifest_path = path / manifest_name
    if not manifest_path.exists():
        raise SystemExit(f"missing_manifest:{path}")
    manifest = load_json(manifest_path)
    expected = {str(entry["relative_path"]): str(entry["sha256"]) for entry in manifest.get("files", [])}
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


def load_spec(spec_id: str, spec_path: Path = SPEC_PATH) -> dict[str, Any]:
    registry = load_json(spec_path)
    for spec in registry.get("specs", []):
        if spec.get("interpretation_spec_id") == spec_id:
            return spec
    raise SystemExit(f"unknown_interpretation_spec_id:{spec_id}")


def reject_output_dir(path: Path) -> None:
    resolved = path.resolve()
    parts = {part.lower() for part in resolved.parts}
    if "market_bomb_history" in parts:
        raise SystemExit("output_dir_inside_market_bomb_history_rejected")


def finite_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def state_from_exposure(value: Any) -> int | None:
    f = finite_float(value)
    if f is None:
        return None
    if f > 0:
        return 1
    if f < 0:
        return -1
    return 0


def state_label(state: int | None) -> str:
    if state is None:
        return "unavailable"
    if state > 0:
        return "long"
    if state < 0:
        return "short"
    return "neutral"


def window_bounds(window_id: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    bounds = {
        "full_covered_period": (None, None),
        "pre_2025": ("2023-07-03", "2024-12-31"),
        "from_2025": ("2025-01-01", None),
        "calendar_2024": ("2024-01-01", "2024-12-31"),
        "calendar_2025": ("2025-01-01", "2025-12-31"),
        "calendar_2023_h2": ("2023-07-03", "2023-12-31"),
        "calendar_2026_ytd": ("2026-01-01", None),
    }
    start, end = bounds[window_id]
    return (pd.Timestamp(start) if start else None, pd.Timestamp(end) if end else None)


def apply_window(df: pd.DataFrame, date_col: str, window_id: str) -> pd.DataFrame:
    work = df.copy()
    dates = pd.to_datetime(work[date_col], errors="coerce")
    start, end = window_bounds(window_id)
    if start is not None:
        work = work[dates.ge(start)]
        dates = pd.to_datetime(work[date_col], errors="coerce")
    if end is not None:
        work = work[dates.le(end)]
    return work.sort_values(date_col).copy()


def require_exact_models(receipts: list[dict[str, Any]], required: list[str], label: str) -> None:
    observed = [str(receipt.get("model_spec_id", "")) for receipt in receipts]
    if observed != required:
        if len(set(observed)) != len(observed):
            raise SystemExit(f"{label}_duplicate_model_spec")
        missing = [model for model in required if model not in observed]
        if missing:
            raise SystemExit(f"{label}_missing_model_spec:{missing[0]}")
        raise SystemExit(f"{label}_wrong_model_order_or_extra")


def require_consistent(receipts: list[dict[str, Any]], fields: list[str], label: str) -> None:
    for field in fields:
        values = [str(receipt.get(field, "")) for receipt in receipts]
        if not values or any(not value for value in values) or len(set(values)) != 1:
            raise SystemExit(f"{label}_{field}_mismatch")


def artifact_integrity_rows(paths: list[Path], receipts: list[dict[str, Any]], artifact_type: str) -> list[dict[str, Any]]:
    rows = []
    for path, receipt in zip(paths, receipts):
        rows.append(
            {
                "artifact_type": artifact_type,
                "artifact_path": path.as_posix(),
                "model_spec_id": receipt.get("model_spec_id", ""),
                "run_id": receipt.get("run_id", ""),
                "input_id": receipt.get("input_id", ""),
                "source_manifest_hash": receipt.get("source_manifest_hash", ""),
                "model_spec_registry_hash": receipt.get("model_spec_registry_hash", ""),
                "repository_commit_sha": receipt.get("repository_commit_sha", ""),
                "module_source_sha256": receipt.get("module_source_sha256", ""),
                "verification_status": "valid",
                "research_only": True,
                "actionization_allowed": False,
                "not_a_trading_signal": True,
                "predictive_pit_eligible": False,
                "phase2_eligible": False,
                "cross_module_metrics_computed": False,
                "cross_module_integration_performed": False,
            }
        )
    return rows


def require_receipt_matches_baseline(receipt: dict[str, Any], baseline: dict[str, Any], fields: list[str], label: str) -> None:
    for field in fields:
        if str(receipt.get(field, "")) != str(baseline.get(field, "")):
            raise SystemExit(f"{label}_{field}_mismatch")


def load_cta_runs(paths: list[Path], required: list[str]) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    receipts: list[dict[str, Any]] = []
    daily: dict[str, pd.DataFrame] = {}
    for path in paths:
        verify_manifested_artifact(path, CTA_RUN_MANIFEST)
        receipt = load_json(path / CTA_RUN_RECEIPT)
        receipts.append(receipt)
        model = str(receipt.get("model_spec_id"))
        df = read_csv(path / CTA_DAILY)
        df["state"] = [state_from_exposure(value) for value in df["target_exposure"]]
        daily[model] = df
    require_exact_models(receipts, required, "cta")
    require_consistent(receipts, ["input_id", "market_id", "source_manifest_hash", "model_spec_registry_hash", "repository_commit_sha", "module_source_sha256"], "cta")
    return receipts, daily


def load_vol_runs(paths: list[Path], required: list[str]) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    receipts: list[dict[str, Any]] = []
    daily: dict[str, pd.DataFrame] = {}
    for path in paths:
        verify_manifested_artifact(path, VOL_RUN_MANIFEST)
        receipt = load_json(path / VOL_RUN_RECEIPT)
        receipts.append(receipt)
        model = str(receipt.get("model_spec_id"))
        daily[model] = read_csv(path / VOL_DAILY)
    require_exact_models(receipts, required, "vol")
    require_consistent(receipts, ["input_id", "benchmark_mode", "source_manifest_hash", "model_spec_registry_hash", "repository_commit_sha", "module_source_sha256"], "vol")
    return receipts, daily


def load_cta_robustness(path: Path, required_models: list[str], windows: list[str]) -> tuple[dict[str, Any], pd.DataFrame]:
    verify_manifested_artifact(path, CTA_ROBUSTNESS_MANIFEST)
    receipt = load_json(path / CTA_ROBUSTNESS_RECEIPT)
    df = read_csv(path / CTA_ROBUSTNESS_SUMMARY)
    if list(df["analysis_window_id"].drop_duplicates()) != windows:
        raise SystemExit("cta_robustness_window_set_mismatch")
    if sorted(df["model_spec_id"].drop_duplicates().tolist(), key=required_models.index) != required_models:
        raise SystemExit("cta_robustness_model_set_mismatch")
    return receipt, df


def load_vol_characterization(path: Path, required_models: list[str], windows: list[str]) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    verify_manifested_artifact(path, VOL_CHARACTERIZATION_MANIFEST)
    receipt = load_json(path / VOL_CHARACTERIZATION_RECEIPT)
    summary = read_csv(path / VOL_SUMMARY)
    pairwise = read_csv(path / VOL_PAIRWISE)
    if list(summary["analysis_window_id"].drop_duplicates()) != windows:
        raise SystemExit("vol_characterization_window_set_mismatch")
    if sorted(summary["model_spec_id"].drop_duplicates().tolist(), key=required_models.index) != required_models:
        raise SystemExit("vol_characterization_model_set_mismatch")
    return receipt, summary, pairwise


def order_map(values: list[str]) -> dict[str, int]:
    return {value: index for index, value in enumerate(values)}


def cta_metric_atlas(robustness: pd.DataFrame, models: list[str], windows: list[str]) -> list[dict[str, Any]]:
    alignment_order = order_map([str(value) for value in robustness["alignment_mode"].drop_duplicates().tolist()])
    rows = robustness.copy()
    rows["_model_order"] = rows["model_spec_id"].map(order_map(models))
    rows["_alignment_order"] = rows["alignment_mode"].map(alignment_order)
    rows["_window_order"] = rows["analysis_window_id"].map(order_map(windows))
    rows = rows.sort_values(["_model_order", "_alignment_order", "_window_order"], kind="stable").drop(columns=["_model_order", "_alignment_order", "_window_order"])
    rows["ranking_allowed"] = False
    rows["model_selection_allowed"] = False
    return rows.to_dict("records")


def cta_state_transition_atlas(daily: dict[str, pd.DataFrame], models: list[str], windows: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for window in windows:
            group = apply_window(daily[model], "observation_date", window)
            states = group["state"].tolist()
            labels = group["exposure_change_label"].astype(str)
            transitions = long_to_short = short_to_long = 0
            prev: int | None = None
            for state in states:
                if state is None or pd.isna(state):
                    prev = None
                    continue
                state = int(state)
                if prev is not None and state != prev:
                    transitions += 1
                    if prev == 1 and state == -1:
                        long_to_short += 1
                    if prev == -1 and state == 1:
                        short_to_long += 1
                prev = state
            rows.append(
                {
                    "model_spec_id": model,
                    "analysis_window_id": window,
                    "observation_count": int(len(group)),
                    "valid_target_exposure_count": int(sum(state is not None and not pd.isna(state) for state in states)),
                    "input_unavailable_count": int(sum(state is None or pd.isna(state) for state in states)),
                    "long_state_count": int(sum(state == 1 for state in states)),
                    "short_state_count": int(sum(state == -1 for state in states)),
                    "neutral_state_count": int(sum(state == 0 for state in states)),
                    "state_transition_count": transitions,
                    "long_to_short_transition_count": long_to_short,
                    "short_to_long_transition_count": short_to_long,
                    "increase_risk_count": int(labels.eq("increase_risk").sum()),
                    "reduce_risk_count": int(labels.eq("reduce_risk").sum()),
                    "unchanged_count": int(labels.eq("unchanged").sum()),
                    "ranking_allowed": False,
                    "model_selection_allowed": False,
                }
            )
    return rows


def align_cta_states(daily: dict[str, pd.DataFrame], models: list[str]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for model in models:
        frame = daily[model][["observation_date", "state"]].rename(columns={"state": model})
        merged = frame if merged is None else merged.merge(frame, on="observation_date", how="outer")
    return merged.sort_values("observation_date").reset_index(drop=True)


def cta_pairwise_agreement(aligned: pd.DataFrame, models: list[str], windows: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for left_i, left in enumerate(models):
        for right in models[left_i + 1 :]:
            for window in windows:
                group = apply_window(aligned, "observation_date", window)
                pair = group[[left, right]].dropna()
                same = pair[left].eq(pair[right])
                rows.append(
                    {
                        "left_model_spec_id": left,
                        "right_model_spec_id": right,
                        "analysis_window_id": window,
                        "overlapping_valid_state_count": int(len(pair)),
                        "same_state_count": int(same.sum()),
                        "same_state_fraction": "" if len(pair) == 0 else float(same.sum() / len(pair)),
                        "both_long_count": int(((pair[left] == 1) & (pair[right] == 1)).sum()),
                        "both_short_count": int(((pair[left] == -1) & (pair[right] == -1)).sum()),
                        "left_long_right_short_count": int(((pair[left] == 1) & (pair[right] == -1)).sum()),
                        "left_short_right_long_count": int(((pair[left] == -1) & (pair[right] == 1)).sum()),
                        "one_or_both_neutral_count": int(((pair[left] == 0) | (pair[right] == 0)).sum()),
                        "ranking_allowed": False,
                        "model_selection_allowed": False,
                    }
                )
    return rows


def cta_disagreement_episodes(aligned: pd.DataFrame, models: list[str]) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for _, row in aligned.iterrows():
        states = [row[model] if pd.notna(row[model]) else None for model in models]
        if any(state is None for state in states):
            if current:
                episodes.append(make_episode(current, models))
                current = []
            continue
        if len(set(states)) == 1:
            if current:
                episodes.append(make_episode(current, models))
                current = []
            continue
        current.append({"observation_date": row["observation_date"], "states": states})
    if current:
        episodes.append(make_episode(current, models))
    return episodes


def make_episode(rows: list[dict[str, Any]], models: list[str]) -> dict[str, Any]:
    patterns = []
    for row in rows:
        pattern = "|".join(f"{model}:{state_label(int(state))}" for model, state in zip(models, row["states"]))
        patterns.append(pattern)
    return {
        "episode_start": rows[0]["observation_date"],
        "episode_end": rows[-1]["observation_date"],
        "observed_session_count": len(rows),
        "state_pattern_count": len(set(patterns)),
        "model_spec_state_patterns": ";".join(sorted(set(patterns))),
    }


def cta_top_state_divergence(aligned: pd.DataFrame, models: list[str], limit: int) -> list[dict[str, Any]]:
    rows = []
    for _, row in aligned.iterrows():
        states = [row[model] if pd.notna(row[model]) else None for model in models]
        valid = [int(state) for state in states if state is not None and not pd.isna(state)]
        if not valid:
            continue
        out = {"observation_date": row["observation_date"], "state_dispersion_count": len(set(valid))}
        for model, state in zip(models, states):
            out[f"{model}_state"] = state_label(None if state is None or pd.isna(state) else int(state))
        rows.append(out)
    rows.sort(key=lambda item: (-int(item["state_dispersion_count"]), str(item["observation_date"])))
    return rows[:limit]


def vol_spec_atlas(summary: pd.DataFrame, models: list[str], windows: list[str]) -> list[dict[str, Any]]:
    rows = summary.copy()
    rows["_model_order"] = rows["model_spec_id"].map(order_map(models))
    rows["_window_order"] = rows["analysis_window_id"].map(order_map(windows))
    rows = rows.sort_values(["_model_order", "_window_order"], kind="stable").drop(columns=["_model_order", "_window_order"])
    rows["ranking_allowed"] = False
    rows["model_selection_allowed"] = False
    rows["returns_analysis_allowed"] = False
    return rows.to_dict("records")


def vol_pairwise_atlas(pairwise: pd.DataFrame, models: list[str], windows: list[str]) -> list[dict[str, Any]]:
    model_order = order_map(models)
    rows = pairwise.copy()
    rows["_window_order"] = rows["analysis_window_id"].map(order_map(windows))
    rows["_left_order"] = rows["left_model_spec_id"].map(model_order)
    rows["_right_order"] = rows["right_model_spec_id"].map(model_order)
    rows = rows.sort_values(["_window_order", "_left_order", "_right_order"], kind="stable").drop(columns=["_window_order", "_left_order", "_right_order"])
    return rows.to_dict("records")


def align_vol_exposures(daily: dict[str, pd.DataFrame], models: list[str]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for model in models:
        frame = daily[model][["observation_date", "target_exposure", "exposure_change_label"]].rename(columns={"target_exposure": model, "exposure_change_label": f"{model}_label"})
        merged = frame if merged is None else merged.merge(frame, on="observation_date", how="outer")
    return merged.sort_values("observation_date").reset_index(drop=True)


def vol_daily_cross_spec_spread(aligned: pd.DataFrame, models: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in aligned.iterrows():
        exposures = [finite_float(row[model]) for model in models]
        valid = [value for value in exposures if value is not None]
        unavailable = len(models) - len(valid)
        if valid:
            minimum = min(valid)
            maximum = max(valid)
            mean = sum(valid) / len(valid)
            cap_count = sum(value >= 1.0 - 1e-12 for value in valid)
            spread = maximum - minimum
        else:
            minimum = maximum = mean = spread = ""
            cap_count = 0
        rows.append(
            {
                "observation_date": row["observation_date"],
                "valid_spec_count": len(valid),
                "minimum_target_exposure": minimum,
                "maximum_target_exposure": maximum,
                "cross_spec_exposure_range": spread,
                "mean_target_exposure_across_valid_specs": mean,
                "cap_binding_spec_count": cap_count,
                "input_unavailable_spec_count": unavailable,
            }
        )
    return rows


def vol_top_dispersion(spread_rows: list[dict[str, Any]], aligned: pd.DataFrame, models: list[str], limit: int) -> list[dict[str, Any]]:
    by_date = {row["observation_date"]: row for row in spread_rows}
    rows = []
    for _, row in aligned.iterrows():
        base = dict(by_date[row["observation_date"]])
        for model in models:
            value = finite_float(row[model])
            base[f"{model}_target_exposure"] = "" if value is None else value
        rows.append(base)
    rows.sort(key=lambda item: (-float(item["cross_spec_exposure_range"] or 0.0), str(item["observation_date"])))
    return rows[:limit]


def vol_spread_distribution(spread_rows: list[dict[str, Any]], windows: list[str]) -> list[dict[str, Any]]:
    df = pd.DataFrame(spread_rows)
    out = []
    for window in windows:
        group = apply_window(df, "observation_date", window)
        vals = pd.to_numeric(group["cross_spec_exposure_range"], errors="coerce").dropna()
        positive = vals[vals.gt(0)]
        out.append(
            {
                "analysis_window_id": window,
                "valid_cross_spec_day_count": int(vals.count()),
                "mean_cross_spec_exposure_range": "" if vals.empty else float(vals.mean()),
                "median_cross_spec_exposure_range": "" if vals.empty else float(vals.median()),
                "p90_cross_spec_exposure_range": "" if vals.empty else float(vals.quantile(0.9)),
                "p95_cross_spec_exposure_range": "" if vals.empty else float(vals.quantile(0.95)),
                "maximum_cross_spec_exposure_range": "" if vals.empty else float(vals.max()),
                "zero_range_day_count": int(vals.eq(0).sum()),
                "positive_range_day_count": int(positive.count()),
            }
        )
    return out


def narrative_report(path: Path, run_id: str, cta_rows: list[dict[str, Any]], vol_rows: list[dict[str, Any]]) -> None:
    text = f"""# Phase 1.5F CTA And Vol-Control Descriptive Interpretation Atlas

run_id: `{run_id}`

## Integrity And Provenance

All source artifacts were manifest-verified before reading. The output is research-only historical description.

Required flags:

- research_only=true
- actionization_allowed=false
- not_a_trading_signal=true
- predictive_pit_eligible=false
- phase2_eligible=false
- cross_module_metrics_computed=false
- cross_module_integration_performed=false

## CTA State-Path Description

The CTA section describes fixed transparent trend-state paths. It compares state transitions, pairwise state agreement, mixed-state episodes, and descriptive COT robustness rows by existing windows only.

## CTA COT Robustness Description

Leveraged Funds is broad, not CTA-only. NDX is a cash-index proxy for Nasdaq-100 consolidated futures COT. Availability alignment uses reconstructed availability and is not strict PIT. The atlas preserves `as_of_ex_post_only` and `availability_monitoring_only` as separate rows.

## CTA Limitations

The CTA rows are descriptive state-path differences within this limited comparator. They are not observed CTA flow, not manager exposure, and not an acceptance threshold.

## Vol State-Path Description

The Vol-control section describes six fixed transparent vol-target rules. It reports exposure levels, cap binding, rebalance intensity, pairwise exposure dispersion, daily cross-specification range, and fixed-window range distributions.

## Vol Dispersion Description

Vol models are transparent rules, not observed manager positions. Dispersion is cross-specification dispersion of transparent state paths only.

## Vol Limitations

No benchmark prices, returns, PnL, future outcomes, or manager-flow observations are used in the output tables.

## Explicit Non-Integration

CTA and Vol are independent report sections; no cross-module metric was computed and no cross-module integration was performed.

## Explicit Non-Selection And Non-Actionization

No row is ranked, selected, accepted, promoted, or used for actionization. The report does not produce a recommendation.

Output row counts:

- CTA state transition atlas: `{len(cta_rows)}`
- Vol spec characteristic atlas: `{len(vol_rows)}`
"""
    path.write_text(text, encoding="utf-8")


def build_atlas(args: argparse.Namespace) -> dict[str, Any]:
    spec = load_spec(args.interpretation_spec_id)
    output_dir = normalize_path(args.output_dir)
    reject_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cta_paths = [normalize_path(path) for path in args.cta_run_artifact]
    vol_paths = [normalize_path(path) for path in args.vol_run_artifact]
    cta_robust_path = normalize_path(args.cta_robustness_artifact)
    vol_char_path = normalize_path(args.vol_characterization_artifact)
    cta_models = [str(model) for model in spec["required_cta_model_specs"]]
    vol_models = [str(model) for model in spec["required_vol_model_specs"]]
    windows = [str(window) for window in spec["analysis_windows"]]

    cta_receipts, cta_daily = load_cta_runs(cta_paths, cta_models)
    vol_receipts, vol_daily = load_vol_runs(vol_paths, vol_models)
    cta_robust_receipt, cta_robust = load_cta_robustness(cta_robust_path, cta_models, windows)
    vol_char_receipt, vol_summary, vol_pairwise = load_vol_characterization(vol_char_path, vol_models, windows)
    require_receipt_matches_baseline(
        cta_robust_receipt,
        cta_receipts[0],
        ["input_id", "market_id", "source_manifest_hash", "model_spec_registry_hash", "repository_commit_sha", "module_source_sha256"],
        "cta_robustness",
    )
    require_receipt_matches_baseline(
        vol_char_receipt,
        vol_receipts[0],
        ["input_id", "benchmark_mode", "source_manifest_hash", "model_spec_registry_hash", "repository_commit_sha", "module_source_sha256"],
        "vol_characterization",
    )

    run_id = utc_run_id()
    cta_aligned = align_cta_states(cta_daily, cta_models)
    vol_aligned = align_vol_exposures(vol_daily, vol_models)

    cta_integrity = artifact_integrity_rows(cta_paths, cta_receipts, "cta_run")
    cta_integrity.append(
        {
            "artifact_type": "cta_robustness",
            "artifact_path": cta_robust_path.as_posix(),
            "model_spec_id": "",
            "run_id": cta_robust_receipt.get("run_id", ""),
            "input_id": cta_robust_receipt.get("input_id", ""),
            "source_manifest_hash": cta_robust_receipt.get("source_manifest_hash", ""),
            "model_spec_registry_hash": cta_robust_receipt.get("model_spec_registry_hash", ""),
            "repository_commit_sha": cta_robust_receipt.get("repository_commit_sha", ""),
            "module_source_sha256": cta_robust_receipt.get("module_source_sha256", ""),
            "verification_status": "valid",
            "research_only": True,
            "actionization_allowed": False,
            "not_a_trading_signal": True,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
            "cross_module_metrics_computed": False,
            "cross_module_integration_performed": False,
        }
    )
    vol_integrity = artifact_integrity_rows(vol_paths, vol_receipts, "vol_run")
    vol_integrity.append(
        {
            "artifact_type": "vol_characterization",
            "artifact_path": vol_char_path.as_posix(),
            "model_spec_id": "",
            "run_id": vol_char_receipt.get("run_id", ""),
            "input_id": vol_char_receipt.get("input_id", ""),
            "source_manifest_hash": vol_char_receipt.get("source_manifest_hash", ""),
            "model_spec_registry_hash": vol_char_receipt.get("model_spec_registry_hash", ""),
            "repository_commit_sha": vol_char_receipt.get("repository_commit_sha", ""),
            "module_source_sha256": vol_char_receipt.get("module_source_sha256", ""),
            "verification_status": "valid",
            "research_only": True,
            "actionization_allowed": False,
            "not_a_trading_signal": True,
            "predictive_pit_eligible": False,
            "phase2_eligible": False,
            "cross_module_metrics_computed": False,
            "cross_module_integration_performed": False,
        }
    )

    cta_metric_rows = cta_metric_atlas(cta_robust, cta_models, windows)
    cta_transition_rows = cta_state_transition_atlas(cta_daily, cta_models, windows)
    cta_pair_rows = cta_pairwise_agreement(cta_aligned, cta_models, windows)
    cta_episode_rows = cta_disagreement_episodes(cta_aligned, cta_models)
    cta_top_rows = cta_top_state_divergence(cta_aligned, cta_models, int(spec["cta_top_divergence_observation_count"]))

    vol_spec_rows = vol_spec_atlas(vol_summary, vol_models, windows)
    vol_pair_rows = vol_pairwise_atlas(vol_pairwise, vol_models, windows)
    vol_spread_rows = vol_daily_cross_spec_spread(vol_aligned, vol_models)
    vol_top_rows = vol_top_dispersion(vol_spread_rows, vol_aligned, vol_models, int(spec["vol_top_dispersion_observation_count"]))
    vol_dist_rows = vol_spread_distribution(vol_spread_rows, windows)

    write_csv(output_dir / "cta_artifact_integrity.csv", cta_integrity)
    write_csv(output_dir / "cta_cot_metric_atlas.csv", cta_metric_rows)
    write_csv(output_dir / "cta_state_transition_atlas.csv", cta_transition_rows)
    write_csv(output_dir / "cta_pairwise_state_agreement.csv", cta_pair_rows)
    write_csv(output_dir / "cta_multi_spec_disagreement_episodes.csv", cta_episode_rows)
    write_csv(output_dir / "cta_top_state_divergence_observations.csv", cta_top_rows)
    write_csv(output_dir / "vol_control_artifact_integrity.csv", vol_integrity)
    write_csv(output_dir / "vol_control_spec_characteristic_atlas.csv", vol_spec_rows)
    write_csv(output_dir / "vol_control_pairwise_dispersion_atlas.csv", vol_pair_rows)
    write_csv(output_dir / "vol_control_daily_cross_spec_spread.csv", vol_spread_rows)
    write_csv(output_dir / "vol_control_top_cross_spec_dispersion_observations.csv", vol_top_rows)
    write_csv(output_dir / "vol_control_cross_spec_spread_distribution.csv", vol_dist_rows)

    report_path = output_dir / f"flow_pressure_phase1_5f_cta_vol_descriptive_interpretation_report_{run_id}.md"
    narrative_report(report_path, run_id, cta_transition_rows, vol_spec_rows)
    receipt = {
        "run_id": run_id,
        "interpretation_spec_id": spec["interpretation_spec_id"],
        "mode": spec["mode"],
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "ranking_allowed": False,
        "model_selection_allowed": False,
        "returns_analysis_allowed": False,
        "cross_module_metrics_computed": False,
        "cross_module_integration_performed": False,
        "output_dir": output_dir.as_posix(),
        "report_path": report_path.as_posix(),
        "cta_run_artifact_count": len(cta_paths),
        "vol_run_artifact_count": len(vol_paths),
        "cta_metric_rows": len(cta_metric_rows),
        "vol_pairwise_rows": len(vol_pair_rows),
    }
    write_json(output_dir / "phase1_5f_interpretation_receipt.json", receipt)
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Phase 1.5F historical descriptive CTA and Vol-control interpretation atlas.")
    parser.add_argument("--cta-robustness-artifact", required=True)
    parser.add_argument("--cta-run-artifact", action="append", required=True)
    parser.add_argument("--vol-characterization-artifact", required=True)
    parser.add_argument("--vol-run-artifact", action="append", required=True)
    parser.add_argument("--interpretation-spec-id", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    receipt = build_atlas(args)
    print(json_dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
