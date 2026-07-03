from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "config" / "research_review_v1" / "phase1_6b_cross_module_downside_spec.json"

CTA_MODELS = [
    "cta_ts_20d_binary_v1",
    "cta_ts_60d_binary_v1",
    "cta_ts_120d_binary_v1",
    "cta_ts_20_60_120_equal_weight_v1",
]
VOL_MODELS = [
    "vc_daily_20d_target10_cap100_v1",
    "vc_daily_40d_target10_cap100_v1",
    "vc_daily_60d_target10_cap100_v1",
    "vc_daily_20d_target12_cap100_v1",
    "vc_daily_40d_target12_cap100_v1",
    "vc_daily_60d_target12_cap100_v1",
]
ETF_MODEL = "tqqq_sqqq_static_daily_reset_scale_v1"

CTA_MANIFEST = "cta_content_manifest.json"
CTA_RECEIPT = "cta_run_receipt.json"
CTA_DAILY = "cta_daily_exposure.csv"
VOL_MANIFEST = "vol_control_content_manifest.json"
VOL_RECEIPT = "vol_control_run_receipt.json"
VOL_DAILY = "vol_control_daily_exposure.csv"
ETF_MANIFEST = "leveraged_etf_scale_content_manifest.json"
ETF_RECEIPT = "leveraged_etf_scale_run_receipt.json"
ETF_DAILY = "leveraged_etf_scale_proxy_daily.csv"

REQUIRED_OUTPUT_FILES = [
    "cross_module_artifact_integrity.csv",
    "cross_module_alignment_audit.csv",
    "cross_module_daily_panel.csv",
    "cross_module_outcome_definitions.json",
    "cross_module_association_summary.csv",
    "cross_module_conditioned_downside_summary.csv",
    "cross_module_joint_condition_summary.csv",
    "cross_module_etf_mechanical_identity_audit.csv",
    "cross_module_window_coverage.csv",
    "phase1_6b_cross_module_downside_receipt.json",
    "phase1_6b_cross_module_downside_summary.md",
    "phase1_6b_cross_module_downside_limitations.md",
    "phase1_6b_cross_module_downside_content_manifest.json",
]

FORBIDDEN_OUTPUT_FIELDS = {
    "raw_close",
    "raw_price",
    "close",
    "pnl",
    "sharpe",
    "trade_instruction",
    "recommendation",
    "dealer",
    "option_chain",
}


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    lower = {name.lower() for name in fieldnames}
    blocked = sorted(lower & FORBIDDEN_OUTPUT_FIELDS)
    if blocked:
        raise SystemExit(f"cross_module_forbidden_output_field:{blocked[0]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def finite_series(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").replace([math.inf, -math.inf], pd.NA)


def bool_text(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def load_spec(spec_id: str) -> dict[str, Any]:
    registry = load_json(SPEC_PATH)
    for spec in registry.get("specs", []):
        if spec.get("study_spec_id") == spec_id:
            return spec
    raise SystemExit(f"unknown_study_spec_id:{spec_id}")


def verify_manifested_artifact(path: Path, manifest_name: str) -> dict[str, Any]:
    manifest_path = path / manifest_name
    if not manifest_path.exists():
        raise SystemExit("cross_module_source_artifact_invalid:missing_manifest")
    manifest = load_json(manifest_path)
    expected = {str(entry["relative_path"]): str(entry["sha256"]) for entry in manifest.get("files", [])}
    actual = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file() and p.name != manifest_name}
    for rel, expected_hash in expected.items():
        target = path / rel
        if not target.exists():
            raise SystemExit(f"cross_module_source_artifact_tampered:missing:{rel}")
        if file_sha256(target) != expected_hash:
            raise SystemExit(f"cross_module_source_artifact_tampered:sha:{rel}")
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise SystemExit(f"cross_module_source_artifact_tampered:extra:{extras[0]}")
    return manifest


def verify_output_manifest(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "phase1_6b_cross_module_downside_content_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("cross_module_output_manifest_missing")
    manifest = load_json(manifest_path)
    expected = {str(entry["relative_path"]): str(entry["sha256"]) for entry in manifest.get("files", [])}
    actual = {p.relative_to(output_dir).as_posix(): p for p in output_dir.rglob("*") if p.is_file() and p.name != manifest_path.name}
    for rel in REQUIRED_OUTPUT_FILES:
        if rel == manifest_path.name:
            continue
        if rel not in expected:
            raise SystemExit(f"cross_module_output_manifest_missing_entry:{rel}")
    for rel, expected_hash in expected.items():
        target = output_dir / rel
        if not target.exists():
            raise SystemExit(f"cross_module_output_tampered:missing:{rel}")
        if file_sha256(target) != expected_hash:
            raise SystemExit(f"cross_module_output_tampered:sha:{rel}")
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise SystemExit(f"cross_module_output_tampered:extra:{extras[0]}")
    return manifest


def reject_output_dir(path: Path) -> None:
    parts = {part.lower() for part in path.resolve().parts}
    if "market_bomb_history" in parts:
        raise SystemExit("cross_module_output_dir_rejected")


def require_receipt_flags(receipt: dict[str, Any], module: str) -> None:
    expected_false = ["actionization_allowed", "predictive_pit_eligible", "phase2_eligible"]
    expected_true = ["research_only", "not_a_trading_signal", "not_market_impact_estimate"]
    for key in expected_false:
        if bool_text(receipt.get(key)) is not False:
            raise SystemExit(f"cross_module_source_safety_flag_mismatch:{module}:{key}")
    for key in expected_true:
        if bool_text(receipt.get(key)) is not True:
            raise SystemExit(f"cross_module_source_safety_flag_mismatch:{module}:{key}")
    if module == "cta":
        for key in ["not_actual_cta_position_estimate", "not_actual_cta_flow_estimate"]:
            if bool_text(receipt.get(key)) is not True:
                raise SystemExit(f"cross_module_source_safety_flag_mismatch:{module}:{key}")
    if module == "vol":
        if bool_text(receipt.get("not_actual_manager_flow_estimate")) is not True:
            raise SystemExit("cross_module_source_safety_flag_mismatch:vol:not_actual_manager_flow_estimate")
    if module == "etf":
        for key in ["not_actual_creation_redemption_flow", "not_actual_investor_flow", "not_actual_manager_trade_estimate"]:
            if bool_text(receipt.get(key)) is not True:
                raise SystemExit(f"cross_module_source_safety_flag_mismatch:{module}:{key}")


def require_roster(receipts: list[dict[str, Any]], expected: list[str], code: str) -> None:
    observed = [str(r.get("model_spec_id", "")) for r in receipts]
    if observed != expected:
        raise SystemExit(code)


def require_columns(df: pd.DataFrame, required: list[str]) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise SystemExit(f"cross_module_missing_required_daily_field:{missing[0]}")


def require_unique_dates(df: pd.DataFrame, model: str) -> None:
    dates = pd.to_datetime(df["observation_date"], errors="coerce")
    if dates.isna().any():
        raise SystemExit(f"cross_module_invalid_effective_session:{model}")
    if df["observation_date"].duplicated().any():
        raise SystemExit(f"cross_module_duplicate_observation_date:{model}")


def load_source_artifacts(cta_paths: list[Path], vol_paths: list[Path], etf_path: Path) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, pd.DataFrame], dict[str, Any], pd.DataFrame, list[dict[str, Any]]]:
    integrity: list[dict[str, Any]] = []
    cta_receipts: list[dict[str, Any]] = []
    cta_daily: dict[str, pd.DataFrame] = {}
    for path in cta_paths:
        verify_manifested_artifact(path, CTA_MANIFEST)
        receipt = load_json(path / CTA_RECEIPT)
        require_receipt_flags(receipt, "cta")
        model = str(receipt.get("model_spec_id", ""))
        df = read_csv(path / CTA_DAILY)
        require_columns(df, ["observation_date", "effective_session", "target_exposure", "exposure_change", "model_spec_id"])
        require_unique_dates(df, model)
        cta_receipts.append(receipt)
        cta_daily[model] = df
        integrity.append(integrity_row("CTA", path, receipt))
    require_roster(cta_receipts, CTA_MODELS, "cross_module_cta_model_set_mismatch")

    vol_receipts: list[dict[str, Any]] = []
    vol_daily: dict[str, pd.DataFrame] = {}
    for path in vol_paths:
        verify_manifested_artifact(path, VOL_MANIFEST)
        receipt = load_json(path / VOL_RECEIPT)
        require_receipt_flags(receipt, "vol")
        model = str(receipt.get("model_spec_id", ""))
        df = read_csv(path / VOL_DAILY)
        require_columns(df, ["observation_date", "effective_session", "target_exposure", "exposure_change", "model_spec_id"])
        require_unique_dates(df, model)
        vol_receipts.append(receipt)
        vol_daily[model] = df
        integrity.append(integrity_row("Vol-control", path, receipt))
    require_roster(vol_receipts, VOL_MODELS, "cross_module_vol_model_set_mismatch")

    verify_manifested_artifact(etf_path, ETF_MANIFEST)
    etf_receipt = load_json(etf_path / ETF_RECEIPT)
    require_receipt_flags(etf_receipt, "etf")
    if etf_receipt.get("model_spec_id") != ETF_MODEL:
        raise SystemExit("cross_module_etf_model_mismatch")
    if etf_receipt.get("benchmark_mode") != "ndx_exact":
        raise SystemExit("cross_module_etf_benchmark_mismatch")
    for key in ["tqqq_lagged_capital_coverage_ratio", "sqqq_lagged_capital_coverage_ratio", "combined_overlap_coverage_ratio"]:
        if finite_float(etf_receipt.get(key)) != 1.0:
            raise SystemExit("cross_module_etf_benchmark_mismatch")
    etf_daily = read_csv(etf_path / ETF_DAILY)
    require_columns(etf_daily, ["observation_date", "benchmark_instrument", "benchmark_return", "tqqq_lagged_capital_usd", "sqqq_lagged_capital_usd", "combined_rebalance_notional_proxy", "combined_scale_status"])
    require_unique_dates(etf_daily, ETF_MODEL)
    if set(etf_daily["benchmark_instrument"].dropna().unique()) != {"NDX"}:
        raise SystemExit("cross_module_etf_benchmark_mismatch")
    returns = finite_series(etf_daily["benchmark_return"])
    if returns.isna().any():
        raise SystemExit("cross_module_return_sequence_invalid")
    if not pd.to_datetime(etf_daily["observation_date"]).is_monotonic_increasing:
        raise SystemExit("cross_module_return_sequence_invalid")
    integrity.append(integrity_row("Leveraged ETF scale", etf_path, etf_receipt))
    return cta_receipts, cta_daily, vol_receipts, vol_daily, etf_receipt, etf_daily, integrity


def integrity_row(module: str, path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": module,
        "artifact_path_relative": repo_relative(path),
        "run_id": receipt.get("run_id", ""),
        "model_spec_id": receipt.get("model_spec_id", ""),
        "verification_status": "valid",
        "source_manifest_hash": receipt.get("source_manifest_hash", ""),
        "model_spec_registry_hash": receipt.get("model_spec_registry_hash", ""),
        "repository_commit_sha": receipt.get("repository_commit_sha", ""),
        "module_source_sha256": receipt.get("module_source_sha256", ""),
        "research_only": bool_text(receipt.get("research_only")),
        "actionization_allowed": bool_text(receipt.get("actionization_allowed")),
        "predictive_pit_eligible": bool_text(receipt.get("predictive_pit_eligible")),
        "phase2_eligible": bool_text(receipt.get("phase2_eligible")),
    }


def numeric(value: Any) -> float | None:
    return finite_float(value)


def cta_state(value: Any) -> int | None:
    f = numeric(value)
    if f is None:
        return None
    if f > 0:
        return 1
    if f < 0:
        return -1
    return 0


def reduce_indicator(change: Any) -> int | None:
    f = numeric(change)
    if f is None:
        return None
    return 1 if f < 0 else 0


def build_base_panel(etf_daily: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    df = etf_daily.copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.strftime("%Y-%m-%d")
    df["same_day_ndx_return"] = finite_series(df["benchmark_return"]).astype(float)
    df["tqqq_lagged_capital_usd"] = finite_series(df["tqqq_lagged_capital_usd"]).astype(float)
    df["sqqq_lagged_capital_usd"] = finite_series(df["sqqq_lagged_capital_usd"]).astype(float)
    df["combined_rebalance_notional_proxy"] = finite_series(df["combined_rebalance_notional_proxy"]).astype(float)
    df["combined_mechanical_sensitivity"] = 6.0 * df["tqqq_lagged_capital_usd"] + 12.0 * df["sqqq_lagged_capital_usd"]
    q = float(spec["etf_sensitivity_high_quantile"])
    threshold = float(df["combined_mechanical_sensitivity"].quantile(q))
    df["combined_mechanical_sensitivity_ex_post_quartile"] = [
        "etf_sensitivity_q4_ex_post" if value >= threshold else "etf_sensitivity_q1_to_q3"
        for value in df["combined_mechanical_sensitivity"]
    ]
    dates = list(df["observation_date"])
    returns = dict(zip(dates, df["same_day_ndx_return"]))
    next_dates = {date: dates[i + 1] if i + 1 < len(dates) else "" for i, date in enumerate(dates)}
    df["next_effective_session"] = [next_dates[d] for d in dates]
    df["next_session_ndx_return"] = [returns.get(next_dates[d], pd.NA) if next_dates[d] else pd.NA for d in dates]
    fwd_cum: list[Any] = []
    fwd_dd: list[Any] = []
    for i, _date in enumerate(dates):
        window = [returns[dates[j]] for j in range(i + 1, min(i + 6, len(dates)))]
        if len(window) < 5:
            fwd_cum.append(pd.NA)
            fwd_dd.append(pd.NA)
            continue
        path = []
        acc = 1.0
        for r in window:
            acc *= 1.0 + float(r)
            path.append(acc - 1.0)
        fwd_cum.append(acc - 1.0)
        fwd_dd.append(min(path))
    df["forward_5_session_cumulative_return"] = fwd_cum
    df["forward_5_session_max_drawdown_from_start"] = fwd_dd
    df["same_day_down_1pct"] = df["same_day_ndx_return"] <= float(spec["same_day_down_1pct_threshold"])
    df["same_day_down_2pct"] = df["same_day_ndx_return"] <= float(spec["same_day_down_2pct_threshold"])
    df["next_session_down_1pct"] = finite_series(df["next_session_ndx_return"]) <= float(spec["next_session_down_1pct_threshold"])
    df["next_session_down_2pct"] = finite_series(df["next_session_ndx_return"]) <= float(spec["next_session_down_2pct_threshold"])
    df["forward_5_session_drawdown_3pct"] = finite_series(df["forward_5_session_max_drawdown_from_start"]) <= float(spec["forward_5_session_drawdown_threshold"])
    keep = [
        "observation_date",
        "next_effective_session",
        "same_day_ndx_return",
        "next_session_ndx_return",
        "forward_5_session_cumulative_return",
        "forward_5_session_max_drawdown_from_start",
        "same_day_down_1pct",
        "same_day_down_2pct",
        "next_session_down_1pct",
        "next_session_down_2pct",
        "forward_5_session_drawdown_3pct",
        "tqqq_lagged_capital_usd",
        "sqqq_lagged_capital_usd",
        "combined_mechanical_sensitivity",
        "combined_mechanical_sensitivity_ex_post_quartile",
        "combined_rebalance_notional_proxy",
        "combined_scale_status",
    ]
    return df[keep].copy()


def add_model_features(panel: pd.DataFrame, cta_daily: dict[str, pd.DataFrame], vol_daily: dict[str, pd.DataFrame]) -> pd.DataFrame:
    panel = panel.copy()
    for model in CTA_MODELS:
        src = cta_daily[model].copy()
        src["state"] = [cta_state(v) for v in src["target_exposure"]]
        src["reduce"] = [reduce_indicator(v) for v in src["exposure_change"]]
        mapping = src.set_index("observation_date")
        panel[f"cta_{model}_state"] = [mapping["state"].get(d, pd.NA) for d in panel["observation_date"]]
        panel[f"cta_{model}_exposure_change"] = [numeric(mapping["exposure_change"].get(d, pd.NA)) for d in panel["observation_date"]]
        panel[f"cta_{model}_reduce_risk_indicator"] = [mapping["reduce"].get(d, pd.NA) for d in panel["observation_date"]]
    cta_state_cols = [f"cta_{model}_state" for model in CTA_MODELS]
    panel["cta_valid_model_count"] = panel[cta_state_cols].notna().sum(axis=1)
    panel["cta_risk_off_model_count"] = (panel[cta_state_cols] == -1).sum(axis=1)
    panel["cta_consensus_category"] = [classify_cta(row) for _, row in panel.iterrows()]

    for model in VOL_MODELS:
        src = vol_daily[model].copy()
        src["target"] = [numeric(v) for v in src["target_exposure"]]
        src["change"] = [numeric(v) for v in src["exposure_change"]]
        src["reduce"] = [reduce_indicator(v) for v in src["exposure_change"]]
        mapping = src.set_index("observation_date")
        panel[f"vol_{model}_target_exposure"] = [mapping["target"].get(d, pd.NA) for d in panel["observation_date"]]
        panel[f"vol_{model}_exposure_change"] = [mapping["change"].get(d, pd.NA) for d in panel["observation_date"]]
        panel[f"vol_{model}_reduce_risk_indicator"] = [mapping["reduce"].get(d, pd.NA) for d in panel["observation_date"]]
    vol_target_cols = [f"vol_{model}_target_exposure" for model in VOL_MODELS]
    vol_change_cols = [f"vol_{model}_exposure_change" for model in VOL_MODELS]
    panel["vol_valid_model_count"] = panel[vol_target_cols].notna().sum(axis=1)
    panel["vol_reduce_risk_model_count"] = (panel[vol_change_cols] < 0).sum(axis=1)
    panel["vol_change_consensus_category"] = [classify_vol(row) for _, row in panel.iterrows()]
    return panel


def classify_cta(row: pd.Series) -> str:
    vals = [row.get(f"cta_{model}_state") for model in CTA_MODELS]
    valid = [int(v) for v in vals if pd.notna(v)]
    if len(valid) < 4:
        return "cta_incomplete"
    if all(v == 1 for v in valid):
        return "cta_all_risk_on"
    if all(v == -1 for v in valid):
        return "cta_all_risk_off"
    return "cta_mixed"


def classify_vol(row: pd.Series) -> str:
    vals = [row.get(f"vol_{model}_exposure_change") for model in VOL_MODELS]
    valid = [float(v) for v in vals if pd.notna(v)]
    if len(valid) < 6:
        return "vol_incomplete"
    if all(v > 0 for v in valid):
        return "vol_all_increase_risk"
    if all(v < 0 for v in valid):
        return "vol_all_reduce_risk"
    return "vol_mixed_or_unchanged"


def alignment_rows(cta_daily: dict[str, pd.DataFrame], vol_daily: dict[str, pd.DataFrame], etf_daily: pd.DataFrame) -> list[dict[str, Any]]:
    etf_dates = set(etf_daily["observation_date"].astype(str))
    rows: list[dict[str, Any]] = []
    for module, daily_map in [("CTA", cta_daily), ("Vol-control", vol_daily)]:
        for model, df in daily_map.items():
            effective = df["effective_session"].astype(str)
            mapped = effective.isin(etf_dates)
            forward_complete = 0
            dates = list(etf_daily["observation_date"].astype(str))
            idx = {d: i for i, d in enumerate(dates)}
            for eff in effective[mapped]:
                if idx.get(eff, 10**9) + 4 < len(dates):
                    forward_complete += 1
            if module == "CTA":
                valid_rows = sum(finite_float(v) is not None for v in df["target_exposure"])
            else:
                valid_rows = sum(finite_float(v) is not None for v in df["exposure_change"])
            ratio = float(mapped.mean()) if len(mapped) else 0.0
            rows.append(
                {
                    "source_module_model": f"{module}/{model}",
                    "source_rows": len(df),
                    "observation_date_coverage": f"{df['observation_date'].min()}..{df['observation_date'].max()}",
                    "valid_state_rows": valid_rows,
                    "effective_session_rows": len(effective),
                    "mapped_next_session_rows": int(mapped.sum()),
                    "unmapped_next_session_rows": int((~mapped).sum()),
                    "next_session_alignment_ratio": ratio,
                    "forward_5_complete_rows": forward_complete,
                    "duplicate_dates": int(df["observation_date"].duplicated().sum()),
                    "invalid_dates": int(pd.to_datetime(df["observation_date"], errors="coerce").isna().sum()),
                    "status": "valid" if ratio >= 0.90 else "alignment_below_threshold",
                }
            )
    return rows


def window_frame(panel: pd.DataFrame, window: dict[str, Any]) -> pd.DataFrame:
    df = panel.copy()
    dates = pd.to_datetime(df["observation_date"], errors="coerce")
    if window.get("start"):
        df = df[dates >= pd.Timestamp(window["start"])]
        dates = pd.to_datetime(df["observation_date"], errors="coerce")
    if window.get("end"):
        df = df[dates <= pd.Timestamp(window["end"])]
    return df


def corr_or_blank(df: pd.DataFrame, feature: str, outcome: str, min_pairs: int) -> dict[str, Any]:
    work = df[[feature, outcome]].copy()
    work[feature] = pd.to_numeric(work[feature], errors="coerce")
    work[outcome] = pd.to_numeric(work[outcome], errors="coerce")
    work = work.dropna()
    pair_count = len(work)
    if pair_count < min_pairs:
        return {"pair_count": pair_count, "metrics_available": False, "reason": "pair_count_below_60"}
    if work[feature].nunique(dropna=True) < 2 or work[outcome].nunique(dropna=True) < 2:
        return {"pair_count": pair_count, "metrics_available": False, "reason": "constant_input"}
    return {
        "pair_count": pair_count,
        "metrics_available": True,
        "reason": "",
        "pearson": work[feature].corr(work[outcome], method="pearson"),
        "spearman": work[feature].corr(work[outcome], method="spearman"),
        "feature_mean": work[feature].mean(),
        "feature_median": work[feature].median(),
        "outcome_mean": work[outcome].mean(),
        "outcome_median": work[outcome].median(),
        "outcome_downside_event_rate": (work[outcome] < 0).mean(),
    }


def association_rows(panel: pd.DataFrame, spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    outcomes = ["next_session_ndx_return", "forward_5_session_cumulative_return", "forward_5_session_max_drawdown_from_start"]
    features: list[tuple[str, str, str, str]] = []
    for model in CTA_MODELS:
        features.append(("CTA", model, "target_exposure", f"cta_{model}_state"))
        features.append(("CTA", model, "reduce_risk_indicator", f"cta_{model}_reduce_risk_indicator"))
    for model in VOL_MODELS:
        features.append(("Vol-control", model, "target_exposure", f"vol_{model}_target_exposure"))
        features.append(("Vol-control", model, "exposure_change", f"vol_{model}_exposure_change"))
        features.append(("Vol-control", model, "reduce_risk_indicator", f"vol_{model}_reduce_risk_indicator"))
    features.append(("Leveraged ETF scale", ETF_MODEL, "combined_mechanical_sensitivity", "combined_mechanical_sensitivity"))
    for window in spec["analysis_windows"]:
        wf = window_frame(panel, window)
        for module, model, feature_id, col in features:
            for outcome in outcomes:
                c = corr_or_blank(wf, col, outcome, int(spec["minimum_pair_count_for_correlation"]))
                rows.append(
                    {
                        "module": module,
                        "model_spec_id": model,
                        "feature_id": feature_id,
                        "feature_type": "continuous" if feature_id in {"target_exposure", "exposure_change", "combined_mechanical_sensitivity"} else "binary",
                        "analysis_window_id": window["analysis_window_id"],
                        "window_class": window["window_class"],
                        "outcome_id": outcome,
                        "pair_count": c["pair_count"],
                        "metrics_available": c["metrics_available"],
                        "metrics_unavailable_reason": c["reason"],
                        "pearson_correlation": c.get("pearson", ""),
                        "spearman_correlation": c.get("spearman", ""),
                        "feature_mean": c.get("feature_mean", ""),
                        "feature_median": c.get("feature_median", ""),
                        "outcome_mean": c.get("outcome_mean", ""),
                        "outcome_median": c.get("outcome_median", ""),
                        "outcome_downside_event_rate": c.get("outcome_downside_event_rate", ""),
                        "ex_post_only": True,
                        "not_predictive": True,
                        "not_a_model_selection_metric": True,
                    }
                )
    return rows


def condition_rows(panel: pd.DataFrame, spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    conditions: list[tuple[str, str, str, str, str, Any]] = []
    for model in CTA_MODELS:
        conditions += [
            ("CTA", model, "state", "risk_on", f"cta_{model}_state", 1),
            ("CTA", model, "state", "risk_off", f"cta_{model}_state", -1),
            ("CTA", model, "transition", "reduce_risk", f"cta_{model}_reduce_risk_indicator", 1),
            ("CTA", model, "transition", "not_reduce_risk", f"cta_{model}_reduce_risk_indicator", 0),
        ]
    for model in VOL_MODELS:
        conditions += [
            ("Vol-control", model, "target_exposure", "full_exposure", f"vol_{model}_target_exposure", "full"),
            ("Vol-control", model, "target_exposure", "below_full_exposure", f"vol_{model}_target_exposure", "below"),
            ("Vol-control", model, "change", "reduce_risk", f"vol_{model}_reduce_risk_indicator", 1),
            ("Vol-control", model, "change", "not_reduce_risk", f"vol_{model}_reduce_risk_indicator", 0),
        ]
    conditions += [
        ("Leveraged ETF scale", ETF_MODEL, "capital_sensitivity", "q1_to_q3_ex_post", "combined_mechanical_sensitivity_ex_post_quartile", "etf_sensitivity_q1_to_q3"),
        ("Leveraged ETF scale", ETF_MODEL, "capital_sensitivity", "q4_ex_post", "combined_mechanical_sensitivity_ex_post_quartile", "etf_sensitivity_q4_ex_post"),
    ]
    for window in spec["analysis_windows"]:
        wf = window_frame(panel, window)
        for module, model, feature_id, condition_id, col, value in conditions:
            if value == "full":
                mask = pd.to_numeric(wf[col], errors="coerce") == 1.0
            elif value == "below":
                mask = pd.to_numeric(wf[col], errors="coerce") < 1.0
            else:
                mask = wf[col] == value
            sub = wf[mask].copy()
            count = len(sub)
            metrics = downside_metrics(sub) if count >= int(spec["minimum_condition_count"]) else {}
            rows.append(
                {
                    "module": module,
                    "model_spec_id": model,
                    "feature_id": feature_id,
                    "condition_id": condition_id,
                    "analysis_window_id": window["analysis_window_id"],
                    "window_class": window["window_class"],
                    "condition_count": count,
                    "metrics_available": bool(metrics),
                    "metrics_unavailable_reason": "" if metrics else "condition_count_below_20",
                    **metrics,
                    "ex_post_only": True,
                    "not_predictive": True,
                }
            )
    return rows


def downside_metrics(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "next_session_down_1pct_rate": pd.to_numeric(df["next_session_down_1pct"], errors="coerce").mean(),
        "next_session_down_2pct_rate": pd.to_numeric(df["next_session_down_2pct"], errors="coerce").mean(),
        "next_session_return_mean": pd.to_numeric(df["next_session_ndx_return"], errors="coerce").mean(),
        "next_session_return_median": pd.to_numeric(df["next_session_ndx_return"], errors="coerce").median(),
        "forward_5_session_cumulative_return_mean": pd.to_numeric(df["forward_5_session_cumulative_return"], errors="coerce").mean(),
        "forward_5_session_cumulative_return_median": pd.to_numeric(df["forward_5_session_cumulative_return"], errors="coerce").median(),
        "forward_5_session_drawdown_3pct_rate": pd.to_numeric(df["forward_5_session_drawdown_3pct"], errors="coerce").mean(),
        "forward_5_session_max_drawdown_median": pd.to_numeric(df["forward_5_session_max_drawdown_from_start"], errors="coerce").median(),
    }


def joint_rows(panel: pd.DataFrame, spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cta_cats = ["cta_all_risk_on", "cta_all_risk_off", "cta_mixed", "cta_incomplete"]
    vol_cats = ["vol_all_increase_risk", "vol_all_reduce_risk", "vol_mixed_or_unchanged", "vol_incomplete"]
    etf_cats = ["etf_sensitivity_q1_to_q3", "etf_sensitivity_q4_ex_post", "etf_sensitivity_unavailable"]
    for window in spec["analysis_windows"]:
        wf = window_frame(panel, window)
        for cta_cat in cta_cats:
            for vol_cat in vol_cats:
                for etf_cat in etf_cats:
                    sub = wf[
                        (wf["cta_consensus_category"] == cta_cat)
                        & (wf["vol_change_consensus_category"] == vol_cat)
                        & (wf["combined_mechanical_sensitivity_ex_post_quartile"] == etf_cat)
                    ]
                    count = len(sub)
                    metrics = downside_metrics(sub) if count >= int(spec["minimum_joint_cell_count"]) else {}
                    rows.append(
                        {
                            "cta_consensus_category": cta_cat,
                            "vol_change_consensus_category": vol_cat,
                            "etf_sensitivity_category": etf_cat,
                            "analysis_window_id": window["analysis_window_id"],
                            "window_class": window["window_class"],
                            "cell_count": count,
                            "metrics_available": bool(metrics),
                            "metrics_unavailable_reason": "" if metrics else "joint_cell_count_below_20",
                            **metrics,
                            "ex_post_only": True,
                            "not_predictive": True,
                            "not_a_composite_score": True,
                            "not_a_trading_signal": True,
                        }
                    )
    return rows


def identity_rows(panel: pd.DataFrame, spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window in spec["analysis_windows"]:
        wf = window_frame(panel, window).copy()
        expected = pd.to_numeric(wf["combined_mechanical_sensitivity"], errors="coerce") * pd.to_numeric(wf["same_day_ndx_return"], errors="coerce")
        actual = pd.to_numeric(wf["combined_rebalance_notional_proxy"], errors="coerce")
        residual = (actual - expected).abs()
        down1 = wf[pd.to_numeric(wf["same_day_down_1pct"], errors="coerce") == 1]
        down2 = wf[pd.to_numeric(wf["same_day_down_2pct"], errors="coerce") == 1]
        valid_rows = int(residual.notna().sum())
        max_abs = residual.max()
        match_status = "no_valid_rows" if valid_rows == 0 else ("valid" if max_abs <= 1e-4 else "residual_above_tolerance")
        rows.append(
            {
                "analysis_window_id": window["analysis_window_id"],
                "valid_rows": valid_rows,
                "identity_residual_max_abs": max_abs,
                "identity_residual_mean_abs": residual.mean(),
                "identity_match_status": match_status,
                "same_day_down_1pct_count": len(down1),
                "same_day_down_2pct_count": len(down2),
                "same_day_down_1pct_abs_proxy_median": pd.to_numeric(down1["combined_rebalance_notional_proxy"], errors="coerce").abs().median(),
                "same_day_down_1pct_abs_proxy_p90": pd.to_numeric(down1["combined_rebalance_notional_proxy"], errors="coerce").abs().quantile(0.90),
                "same_day_down_2pct_abs_proxy_median": pd.to_numeric(down2["combined_rebalance_notional_proxy"], errors="coerce").abs().median(),
                "same_day_down_2pct_abs_proxy_p90": pd.to_numeric(down2["combined_rebalance_notional_proxy"], errors="coerce").abs().quantile(0.90),
                "mechanically_induced_same_day_relationship": True,
                "not_an_empirical_predictive_test": True,
            }
        )
    return rows


def coverage_rows(panel: pd.DataFrame, spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window in spec["analysis_windows"]:
        wf = window_frame(panel, window)
        rows.append(
            {
                "analysis_window_id": window["analysis_window_id"],
                "window_class": window["window_class"],
                "rows": len(wf),
                "first_observation_date": wf["observation_date"].min() if len(wf) else "",
                "last_observation_date": wf["observation_date"].max() if len(wf) else "",
                "next_session_available_rows": int(wf["next_session_ndx_return"].notna().sum()),
                "forward_5_available_rows": int(wf["forward_5_session_cumulative_return"].notna().sum()),
                "cta_complete_rows": int((wf["cta_valid_model_count"] == 4).sum()) if "cta_valid_model_count" in wf else 0,
                "vol_complete_rows": int((wf["vol_valid_model_count"] == 6).sum()) if "vol_valid_model_count" in wf else 0,
                "etf_sensitivity_available_rows": int(wf["combined_mechanical_sensitivity"].notna().sum()) if "combined_mechanical_sensitivity" in wf else 0,
            }
        )
    return rows


def build_content_manifest(output_dir: Path, run_id: str) -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUT_FILES:
        if name == "phase1_6b_cross_module_downside_content_manifest.json":
            continue
        path = output_dir / name
        files.append({"relative_path": name, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "artifact_version": "phase1_6b_cross_module_downside_v1_0_0",
        "module_name": "phase1_6b_cross_module_downside_study",
        "run_id": run_id,
        "files": files,
    }
    write_json(output_dir / "phase1_6b_cross_module_downside_content_manifest.json", manifest)
    return manifest


def build_study(args: argparse.Namespace) -> dict[str, Any]:
    spec = load_spec(args.spec_id)
    output_dir = Path(args.output_dir)
    reject_output_dir(output_dir)
    cta_paths = [Path(p) for p in args.cta_run_artifact]
    vol_paths = [Path(p) for p in args.vol_run_artifact]
    etf_path = Path(args.etf_scale_run_artifact)
    cta_receipts, cta_daily, vol_receipts, vol_daily, etf_receipt, etf_daily, integrity = load_source_artifacts(cta_paths, vol_paths, etf_path)
    alignment = alignment_rows(cta_daily, vol_daily, etf_daily)
    min_ratio = min(float(r["next_session_alignment_ratio"]) for r in alignment)
    if min_ratio < float(spec["minimum_cross_module_next_session_alignment_ratio"]):
        raise SystemExit("cross_module_alignment_coverage_inadequate")

    panel = add_model_features(build_base_panel(etf_daily, spec), cta_daily, vol_daily)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "cross_module_artifact_integrity.csv", integrity, list(integrity[0].keys()))
    write_csv(output_dir / "cross_module_alignment_audit.csv", alignment, list(alignment[0].keys()))
    write_csv(output_dir / "cross_module_daily_panel.csv", panel.to_dict("records"), list(panel.columns))
    outcome_defs = {
        "next_session_ndx_return": "NDX benchmark return at effective session t+1.",
        "forward_5_session_cumulative_return": "Product of one plus NDX returns from t+1 through t+5 minus one.",
        "forward_5_session_max_drawdown_from_start": "Minimum cumulative path return from t+1 through t+5.",
        "same_day_etf_proxy_caveat": "Same-day ETF realized proxy includes same-day return by construction.",
    }
    write_json(output_dir / "cross_module_outcome_definitions.json", outcome_defs)
    assoc = association_rows(panel, spec)
    cond = condition_rows(panel, spec)
    joint = joint_rows(panel, spec)
    identity = identity_rows(panel, spec)
    coverage = coverage_rows(panel, spec)
    write_csv(output_dir / "cross_module_association_summary.csv", assoc, list(assoc[0].keys()))
    write_csv(output_dir / "cross_module_conditioned_downside_summary.csv", cond, list(cond[0].keys()))
    write_csv(output_dir / "cross_module_joint_condition_summary.csv", joint, list(joint[0].keys()))
    write_csv(output_dir / "cross_module_etf_mechanical_identity_audit.csv", identity, list(identity[0].keys()))
    write_csv(output_dir / "cross_module_window_coverage.csv", coverage, list(coverage[0].keys()))
    receipt = {
        "run_status": "phase1_6b_cross_module_downside_completed",
        "run_id": run_id,
        "study_spec_id": spec["study_spec_id"],
        "created_at_utc": iso_now(),
        "repository_commit_sha": git_head(),
        "research_only": True,
        "actionization_allowed": False,
        "not_a_trading_signal": True,
        "predictive_pit_eligible": False,
        "phase2_eligible": False,
        "ranking_allowed": False,
        "model_selection_allowed": False,
        "returns_analysis_allowed": True,
        "outcome_linked_descriptive_analysis_only": True,
        "cross_module_integration_performed": True,
        "cross_module_composite_score_created": False,
        "cross_module_actionization_created": False,
        "not_actual_cta_position_estimate": True,
        "not_actual_cta_flow_estimate": True,
        "not_actual_manager_flow_estimate": True,
        "not_actual_etf_flow_estimate": True,
        "not_actual_market_impact_estimate": True,
        "source_artifact_count": len(integrity),
        "minimum_next_session_alignment_ratio": min_ratio,
        "daily_panel_rows": len(panel),
        "output_dir": repo_relative(output_dir),
    }
    write_json(output_dir / "phase1_6b_cross_module_downside_receipt.json", receipt)
    write_summary(output_dir, receipt, coverage, alignment, assoc, cond, joint, identity)
    write_limitations(output_dir)
    build_content_manifest(output_dir, run_id)
    return receipt


def write_summary(output_dir: Path, receipt: dict[str, Any], coverage: list[dict[str, Any]], alignment: list[dict[str, Any]], assoc: list[dict[str, Any]], cond: list[dict[str, Any]], joint: list[dict[str, Any]], identity: list[dict[str, Any]]) -> None:
    sparse = sum(1 for r in joint if not bool_text(r["metrics_available"]))
    assoc_available = sum(1 for r in assoc if bool_text(r["metrics_available"]))
    condition_available = sum(1 for r in cond if bool_text(r["metrics_available"]))
    lines = [
        "# Phase 1.6B Cross-Module Downside Study",
        "",
        f"- run_status: `{receipt['run_status']}`",
        f"- source_artifact_count: `{receipt['source_artifact_count']}`",
        f"- minimum_next_session_alignment_ratio: `{receipt['minimum_next_session_alignment_ratio']}`",
        f"- daily_panel_rows: `{receipt['daily_panel_rows']}`",
        "",
        "## Integrity And Alignment",
        "",
        "All declared source artifacts were content-manifest verified before read. CTA and Vol-control observations use next-session alignment. ETF same-day realized proxy mechanics are isolated in the identity audit.",
        "",
        "## Fixed Window Coverage",
        "",
        "| Window | Rows | Next Session Rows | Forward 5 Rows |",
        "|---|---:|---:|---:|",
    ]
    for row in coverage:
        lines.append(f"| {row['analysis_window_id']} | {row['rows']} | {row['next_session_available_rows']} | {row['forward_5_available_rows']} |")
    lines += [
        "",
        "## Descriptive Tables",
        "",
        f"- association rows with metrics available: `{assoc_available}`",
        f"- conditioned rows with metrics available: `{condition_available}`",
        f"- sparse joint rows retained with unavailable metrics: `{sparse}`",
        "",
        "## ETF Mechanical Identity",
        "",
        "| Window | Valid Rows | Max Abs Residual | Status |",
        "|---|---:|---:|---|",
    ]
    for row in identity:
        lines.append(f"| {row['analysis_window_id']} | {row['valid_rows']} | {row['identity_residual_max_abs']} | {row['identity_match_status']} |")
    lines += [
        "",
        "## Interpretation Boundary",
        "",
        "This is an in-sample ex-post historical association and conditional distribution study. It does not create a composite score, a selection decision, a causal estimate, a forecast, an actionization gate, or a market-impact estimate.",
    ]
    (output_dir / "phase1_6b_cross_module_downside_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_limitations(output_dir: Path) -> None:
    text = """# Phase 1.6B Limitations

- CTA and Vol-control features are aligned to the next eligible session.
- ETF realized same-day notional proxy includes same-day benchmark return by construction; identity-audit quantities are not empirical forecasting tests.
- Source vintages are descriptive and do not create strict PIT eligibility.
- The sample is NDX-only.
- Forward five-session outcomes overlap.
- Results are in-sample ex-post historical associations with multiple fixed comparisons.
- No causal inference is made.
- No actual CTA, manager, ETF flow, or market-impact claim is made.
- No actionization, release promotion, notification, sizing, execution, or trading use is created.
"""
    (output_dir / "phase1_6b_cross_module_downside_limitations.md").write_text(text, encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-id", default="phase1_6b_ndx_cross_module_downside_v1")
    parser.add_argument("--cta-run-artifact", action="append", default=[])
    parser.add_argument("--vol-run-artifact", action="append", default=[])
    parser.add_argument("--etf-scale-run-artifact")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-output-dir")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.verify_output_dir:
        manifest = verify_output_manifest(Path(args.verify_output_dir))
        print(json_dumps({"verification_status": "valid", "manifest_run_id": manifest.get("run_id")}))
        return 0
    if len(args.cta_run_artifact) != 4:
        raise SystemExit("cross_module_cta_model_set_mismatch")
    if len(args.vol_run_artifact) != 6:
        raise SystemExit("cross_module_vol_model_set_mismatch")
    if not args.etf_scale_run_artifact or not args.output_dir:
        raise SystemExit("missing_required_arguments")
    receipt = build_study(args)
    print(json_dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
