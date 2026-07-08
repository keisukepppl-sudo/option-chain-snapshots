from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


POLICY_VERSION = "morita_mechanical_flow_monitor_v1"
DEFAULT_POLICY = Path("config/morita_mechanical_flow_monitor_v1/policy.json")
DEFAULT_OUTPUT_DIR = Path("outputs/morita_mechanical_flow_monitor_v1")
DAILY_FLOW_ROOT = Path("daily_flow_outputs")

REQUIRED_OUTPUT_FILES = [
    "mechanical_flow_daily_context.csv",
    "mechanical_flow_metric_availability.csv",
    "mechanical_flow_source_lineage.json",
    "mechanical_flow_receipt.json",
    "mechanical_flow_content_manifest.json",
    "mechanical_flow_summary.md",
]

CONTEXT_COLUMNS = [
    "decision_date",
    "data_asof_timestamp",
    "metric_family",
    "metric_name",
    "metric_value",
    "metric_state",
    "metric_source",
    "metric_available",
    "unavailable_reason",
    "policy_version",
    "research_only",
    "no_signal_filtering",
    "no_auto_execution",
]

METRIC_SPECS = [
    {
        "family": "cta_trend_following_proxy",
        "file_options": ["cta_signals.csv"],
        "value_columns": ["cta_score", "cta_flow_proxy", "ret1d"],
        "state_columns": ["cta_regime", "cta_notes"],
    },
    {
        "family": "volatility_control_proxy",
        "file_options": ["vol_control_proxy.csv"],
        "value_columns": ["vol_control_exposure_proxy", "vol_control_exposure_change", "vol_control_flow_proxy", "rv20", "rv60"],
        "state_columns": ["regime"],
    },
    {
        "family": "leveraged_etf_flow_proxy",
        "file_options": ["leveraged_etf_aum_flows.csv", "us_leveraged_etf_flows.csv"],
        "value_columns": ["flow_proxy", "aum_flow_proxy", "aum_flow", "ret1d"],
        "state_columns": ["flow_direction", "flow_status", "source"],
    },
    {
        "family": "breadth_proxy",
        "file_options": ["market_down_rs.csv"],
        "value_columns": ["market_down_rs", "down_rs", "rs_score", "ret1d"],
        "state_columns": ["breadth_state", "regime", "ticker"],
    },
    {
        "family": "qqq_spy_equal_weight_spread_context",
        "file_options": ["combined_mechanical_flow.csv", "daily_flow_report.md"],
        "value_columns": ["qqq_minus_spy", "qqq_minus_equal_weight", "combined_mechanical_sensitivity"],
        "state_columns": ["combined_scale_status", "context_category"],
    },
    {
        "family": "risk_parity_bond_vol_proxy",
        "file_options": ["risk_parity_proxy.csv", "bond_vol_proxy.csv"],
        "value_columns": ["bond_vol_proxy", "risk_parity_exposure_proxy"],
        "state_columns": ["risk_parity_state"],
    },
    {
        "family": "vix_curve_state",
        "file_options": ["vix_curve_state.csv", "vix_futures_curve.csv"],
        "value_columns": ["vix", "vix3m", "vix_curve_slope"],
        "state_columns": ["vix_curve_state"],
    },
]

SAFETY_FLAGS = {
    "research_only": True,
    "no_signal_filtering": True,
    "no_auto_execution": True,
}


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:
        return path.as_posix()


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "policy_version": POLICY_VERSION,
        "mode": "research_logging_only",
        "research_only": True,
        "no_signal_filtering": True,
        "no_auto_execution": True,
        "broker_execution_enabled": False,
        "auto_trade_action_enabled": False,
        "pushover_emergency_enabled": False,
    }
    for key, expected in required.items():
        if policy.get(key) != expected:
            raise SystemExit(f"mechanical_flow_policy_safety_flag_mismatch:{key}")
    for blocked in ["rank_change_allowed", "sizing_change_allowed", "notification_change_allowed"]:
        if policy.get(blocked) is not False:
            raise SystemExit(f"mechanical_flow_policy_safety_flag_mismatch:{blocked}")
    return policy


def latest_flow_dir(root: Path = DAILY_FLOW_ROOT, decision_date: str | None = None) -> Path | None:
    if decision_date:
        candidate = root / decision_date
        return candidate if candidate.exists() else None
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return sorted(dirs, key=lambda p: p.name)[-1] if dirs else None


def _asof_from_file(path: Path) -> str:
    return pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").isoformat()


def _read_csv_safe(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _available_rows(spec: dict[str, Any], flow_dir: Path, decision_date: str, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = next((flow_dir / name for name in spec["file_options"] if (flow_dir / name).exists()), None)
    family = str(spec["family"])
    if source is None:
        reason = "no_existing_source_file_found"
        row = _context_row(decision_date, pd.Timestamp.now(tz="UTC").isoformat(), family, family, "", "unavailable", "", False, reason, policy)
        return [row], {"metric_family": family, "metric_available": False, "source": "", "unavailable_reason": reason}
    if source.suffix.lower() != ".csv":
        reason = "source_file_not_tabular_csv"
        row = _context_row(decision_date, _asof_from_file(source), family, family, "", "unavailable", repo_relative(source), False, reason, policy)
        return [row], {"metric_family": family, "metric_available": False, "source": repo_relative(source), "unavailable_reason": reason}

    df = _read_csv_safe(source)
    if df.empty:
        reason = "source_file_empty_or_unreadable"
        row = _context_row(decision_date, _asof_from_file(source), family, family, "", "unavailable", repo_relative(source), False, reason, policy)
        return [row], {"metric_family": family, "metric_available": False, "source": repo_relative(source), "unavailable_reason": reason}

    value_cols = [c for c in spec["value_columns"] if c in df.columns]
    state_cols = [c for c in spec["state_columns"] if c in df.columns]
    rows: list[dict[str, Any]] = []
    if not value_cols and not state_cols:
        reason = "source_file_present_but_expected_metric_columns_missing"
        rows.append(_context_row(decision_date, _asof_from_file(source), family, family, "", "unavailable", repo_relative(source), False, reason, policy))
        return rows, {"metric_family": family, "metric_available": False, "source": repo_relative(source), "unavailable_reason": reason}

    sample = df.tail(20)
    for col in value_cols:
        series = sample[col].dropna()
        value = "" if series.empty else series.iloc[-1]
        state = ""
        for state_col in state_cols:
            state_series = sample[state_col].dropna()
            if not state_series.empty:
                state = str(state_series.iloc[-1])
                break
        rows.append(_context_row(decision_date, _asof_from_file(source), family, col, value, state or "logged", repo_relative(source), True, "", policy))
    if not rows:
        state_col = state_cols[0]
        state_series = sample[state_col].dropna()
        state = "" if state_series.empty else str(state_series.iloc[-1])
        rows.append(_context_row(decision_date, _asof_from_file(source), family, state_col, state, state or "logged", repo_relative(source), True, "", policy))
    return rows, {"metric_family": family, "metric_available": True, "source": repo_relative(source), "unavailable_reason": ""}


def _context_row(
    decision_date: str,
    asof: str,
    family: str,
    name: str,
    value: Any,
    state: str,
    source: str,
    available: bool,
    unavailable_reason: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision_date": decision_date,
        "data_asof_timestamp": asof,
        "metric_family": family,
        "metric_name": name,
        "metric_value": value,
        "metric_state": state,
        "metric_source": source,
        "metric_available": bool(available),
        "unavailable_reason": unavailable_reason,
        "policy_version": str(policy["policy_version"]),
        **SAFETY_FLAGS,
    }


def build_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUT_FILES:
        if name == "mechanical_flow_content_manifest.json":
            continue
        path = output_dir / name
        if not path.exists():
            raise SystemExit(f"mechanical_flow_manifest_missing_required_file:{name}")
        files.append({"relative_path": name, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    payload = {"policy_version": POLICY_VERSION, "required_files": REQUIRED_OUTPUT_FILES, "files": files}
    payload["content_set_hash"] = text_hash(json_dumps(files))
    return payload


def verify_output_manifest(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "mechanical_flow_content_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = set(REQUIRED_OUTPUT_FILES)
    actual = {p.name for p in output_dir.iterdir() if p.is_file()}
    if actual != expected:
        raise SystemExit(f"mechanical_flow_manifest_file_set_mismatch:{sorted(actual ^ expected)}")
    rebuilt = build_manifest(output_dir)
    if manifest.get("content_set_hash") != rebuilt.get("content_set_hash"):
        raise SystemExit("mechanical_flow_manifest_hash_mismatch")
    return manifest


def build_monitor(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    policy_path: Path = DEFAULT_POLICY,
    daily_flow_root: Path = DAILY_FLOW_ROOT,
    decision_date: str | None = None,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    flow_dir = latest_flow_dir(daily_flow_root, decision_date)
    decision = decision_date or (flow_dir.name if flow_dir else pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"))
    output_dir.mkdir(parents=True, exist_ok=True)

    context_rows: list[dict[str, Any]] = []
    availability_rows: list[dict[str, Any]] = []
    for spec in METRIC_SPECS:
        rows, availability = _available_rows(spec, flow_dir, decision, policy) if flow_dir else (
            [_context_row(decision, pd.Timestamp.now(tz="UTC").isoformat(), spec["family"], spec["family"], "", "unavailable", "", False, "daily_flow_outputs_directory_missing", policy)],
            {"metric_family": spec["family"], "metric_available": False, "source": "", "unavailable_reason": "daily_flow_outputs_directory_missing"},
        )
        context_rows.extend(rows)
        availability_rows.append({"decision_date": decision, **availability, "policy_version": POLICY_VERSION, **SAFETY_FLAGS})

    lineage = {
        "policy_version": POLICY_VERSION,
        "daily_flow_root": repo_relative(daily_flow_root),
        "selected_flow_dir": repo_relative(flow_dir) if flow_dir else "",
        "metric_specs": METRIC_SPECS,
        **SAFETY_FLAGS,
    }
    receipt = {
        "run_status": "mechanical_flow_context_logged",
        "decision_date": decision,
        "context_row_count": len(context_rows),
        "available_metric_family_count": sum(1 for r in availability_rows if bool(r["metric_available"])),
        "output_dir": repo_relative(output_dir),
        **SAFETY_FLAGS,
    }

    write_csv(output_dir / "mechanical_flow_daily_context.csv", context_rows, CONTEXT_COLUMNS)
    write_csv(
        output_dir / "mechanical_flow_metric_availability.csv",
        availability_rows,
        ["decision_date", "metric_family", "metric_available", "source", "unavailable_reason", "policy_version", "research_only", "no_signal_filtering", "no_auto_execution"],
    )
    write_json(output_dir / "mechanical_flow_source_lineage.json", lineage)
    write_json(output_dir / "mechanical_flow_receipt.json", receipt)
    (output_dir / "mechanical_flow_summary.md").write_text(
        "# Mechanical Flow Monitor v1\n\n"
        f"Mechanical flow context logged for `{decision}`.\n\n"
        "This output is research-only thermometer context. It does not filter signals, change ranks, alter sizing, or authorize automatic execution.\n",
        encoding="utf-8",
    )
    write_json(output_dir / "mechanical_flow_content_manifest.json", build_manifest(output_dir))
    verify_output_manifest(output_dir)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--daily-flow-root", default=str(DAILY_FLOW_ROOT))
    parser.add_argument("--decision-date")
    args = parser.parse_args()
    print(json_dumps(build_monitor(Path(args.output_dir), Path(args.policy), Path(args.daily_flow_root), args.decision_date)))


if __name__ == "__main__":
    main()
