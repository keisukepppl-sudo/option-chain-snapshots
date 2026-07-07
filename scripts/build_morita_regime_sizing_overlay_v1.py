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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.build_morita_realized_dispersion_quick_screen_v1 as dispersion


POLICY_VERSION = "morita_regime_sizing_overlay_v1"
D_METRIC = "broad_russell1000_cross_sectional_dispersion_20d"
L_METRIC = "broad_russell1000_qqq_minus_eqw_return_20d"
EXPECTED_D_HIGH_CUTOFF = 0.1076297441118458
EXPECTED_L_HIGH_CUTOFF = 0.0211600633543862
POLICY_PATH = REPO_ROOT / "config" / POLICY_VERSION / "policy.json"
OUTPUT_DIR = REPO_ROOT / "outputs" / POLICY_VERSION
CHATGPT_BUNDLE = REPO_ROOT / f"{POLICY_VERSION}_chatgpt_bundle.md"
DISPERSION_DIR = REPO_ROOT / "outputs" / "morita_realized_dispersion_quick_screen"
NARROW_DIR = REPO_ROOT / "outputs" / "morita_narrow_leadership_confirmation"
FROZEN_2023_DIR = REPO_ROOT / "outputs" / "morita_narrow_leadership_2023_frozen_replication_v2"
MANIFEST_NAME = "regime_overlay_content_manifest.json"
REQUIRED_OUTPUTS = [
    "regime_overlay_daily_state.csv",
    "regime_overlay_signal_decisions.csv",
    "regime_overlay_rolling_sleeve_ledger.csv",
    "regime_overlay_forward_review.csv",
    "regime_overlay_receipt.json",
    "regime_overlay_summary.md",
]
DECISION_COLUMNS = [
    "signal_id",
    "ticker",
    "rank",
    "signal_decision_date",
    "notification_timestamp",
    "regime_observation_date",
    "regime_data_asof_timestamp",
    "D_value",
    "L_value",
    "D_high_cutoff",
    "L_high_cutoff",
    "D_state",
    "L_state",
    "regime_state",
    "policy_version",
    "threshold_source",
    "threshold_manifest_hash",
    "normal_base_target_pct",
    "legacy_50pct_exception_eligible",
    "legacy_50pct_exception_allowed",
    "regime_target_premium_pct",
    "rolling_10_session_cap_pct",
    "actual_confirmed_rolling_premium_pct",
    "planned_recommendation_rolling_premium_pct",
    "rolling_budget_source",
    "remaining_rolling_sleeve_capacity_pct",
    "suggested_max_premium_pct",
    "sleeve_capacity_status",
    "data_availability_status",
    "conservative_fallback_reason",
    "no_auto_execution",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


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
        return str(path.resolve())


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception:
        return None


def safe_date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        return None


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def verify_manifest(path: Path, manifest_name: str) -> str:
    manifest_path = path / manifest_name
    if not manifest_path.exists():
        raise FileNotFoundError(f"required_manifest_missing:{repo_relative(manifest_path)}")
    manifest = load_json(manifest_path)
    for entry in manifest.get("files", []):
        rel = entry.get("relative_path")
        expected = entry.get("sha256")
        if not rel or not expected:
            raise ValueError(f"manifest_entry_invalid:{repo_relative(manifest_path)}")
        current = path / rel
        if not current.exists():
            raise FileNotFoundError(f"manifest_file_missing:{repo_relative(current)}")
        if file_sha256(current) != expected:
            raise ValueError(f"manifest_hash_mismatch:{repo_relative(current)}")
    return file_sha256(manifest_path)


def verify_source_artifacts() -> dict[str, Any]:
    artifacts = {
        "realized_dispersion": (DISPERSION_DIR, "realized_dispersion_content_manifest.json"),
        "narrow_leadership_confirmation": (NARROW_DIR, "narrow_leadership_content_manifest.json"),
        "narrow_leadership_2023_frozen_replication_v2": (FROZEN_2023_DIR, "replication_content_manifest.json"),
    }
    verified: dict[str, Any] = {}
    for name, (path, manifest) in artifacts.items():
        verified[name] = {
            "path": repo_relative(path),
            "manifest": manifest,
            "manifest_hash": verify_manifest(path, manifest),
        }
    verified["metric_implementation_module"] = repo_relative(Path(dispersion.__file__))
    verified["metric_implementation_sha256"] = file_sha256(Path(dispersion.__file__))
    return verified


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = load_json(path)
    if policy.get("policy_version") != POLICY_VERSION:
        raise ValueError("policy_version_mismatch")
    if policy.get("broker_execution_enabled") is not False:
        raise ValueError("broker_execution_must_be_false")
    if policy.get("auto_trade_action_enabled") is not False:
        raise ValueError("auto_trade_action_must_be_false")
    return policy


def load_thresholds(cutoff_path: Path = DISPERSION_DIR / "realized_dispersion_state_cutoffs.csv") -> dict[str, Any]:
    if not cutoff_path.exists():
        raise FileNotFoundError(f"threshold_artifact_missing:{repo_relative(cutoff_path)}")
    cutoffs = pd.read_csv(cutoff_path)
    required = cutoffs[cutoffs["metric"].isin([D_METRIC, L_METRIC])].copy()
    if len(required) != 2:
        raise ValueError("required_thresholds_missing")
    values = {row["metric"]: float(row["p67"]) for _, row in required.iterrows()}
    if abs(values[D_METRIC] - EXPECTED_D_HIGH_CUTOFF) > 1e-12:
        raise ValueError("D_high_cutoff_failed_verification")
    if abs(values[L_METRIC] - EXPECTED_L_HIGH_CUTOFF) > 1e-12:
        raise ValueError("L_high_cutoff_failed_verification")
    if cutoff_path.resolve() == (DISPERSION_DIR / "realized_dispersion_state_cutoffs.csv").resolve():
        manifest_hash = file_sha256(DISPERSION_DIR / "realized_dispersion_content_manifest.json")
    else:
        manifest_hash = "non_default_threshold_test_fixture"
    return {
        "D_high_cutoff": values[D_METRIC],
        "L_high_cutoff": values[L_METRIC],
        "threshold_source": repo_relative(cutoff_path),
        "threshold_manifest_hash": manifest_hash,
        "threshold_construction": "inherited_p67_from_realized_dispersion_state_cutoffs",
    }


def classify_regime(
    D_value: float | None,
    L_value: float | None,
    thresholds: dict[str, Any],
    *,
    lineage_ok: bool = True,
    timing_ok: bool = True,
) -> dict[str, Any]:
    D_cutoff = float(thresholds["D_high_cutoff"])
    L_cutoff = float(thresholds["L_high_cutoff"])
    if D_value is None or L_value is None or not lineage_ok or not timing_ok:
        return {
            "D_state": "unavailable",
            "L_state": "unavailable",
            "regime_state": "REGIME_UNAVAILABLE_CONSERVATIVE",
            "data_availability_status": "UNAVAILABLE_OR_FAILED_VALIDATION",
            "conservative_fallback_reason": "state unavailable / verification failure",
        }
    D_high = D_value >= D_cutoff
    L_high = L_value >= L_cutoff
    if D_high and L_high:
        regime = "NARROW_LEADERSHIP"
    elif D_high and not L_high:
        regime = "HIGH_DISPERSION"
    else:
        regime = "NORMAL"
    return {
        "D_state": "HIGH" if D_high else "NOT_HIGH",
        "L_state": "HIGH" if L_high else "NOT_HIGH",
        "regime_state": regime,
        "data_availability_status": "AVAILABLE",
        "conservative_fallback_reason": "",
    }


def apply_sizing_policy(
    regime_state: str,
    policy: dict[str, Any],
    *,
    legacy_50pct_exception_eligible: bool = False,
    current_rolling_recommendation_pct: float = 0.0,
) -> dict[str, Any]:
    normal_target = float(policy["normal"]["base_target_premium_pct"])
    if regime_state == "NORMAL":
        regime_target = 0.50 if legacy_50pct_exception_eligible else normal_target
        cap = None
        allowed = bool(policy["normal"]["legacy_50pct_exception_allowed"]) and legacy_50pct_exception_eligible
    elif regime_state == "HIGH_DISPERSION":
        regime_target = float(policy["high_dispersion"]["target_premium_pct"])
        cap = float(policy["high_dispersion"]["rolling_10_session_new_S_cap_pct"])
        allowed = False
    elif regime_state == "NARROW_LEADERSHIP":
        regime_target = float(policy["narrow_leadership"]["target_premium_pct"])
        cap = float(policy["narrow_leadership"]["rolling_10_session_new_S_cap_pct"])
        allowed = False
    else:
        regime_target = float(policy["regime_unavailable_conservative"]["target_premium_pct"])
        cap = float(policy["regime_unavailable_conservative"]["rolling_10_session_new_S_cap_pct"])
        allowed = False

    if cap is None:
        remaining = math.nan
        suggested = regime_target
        sleeve_status = "NO_ROLLING_CAP"
    else:
        remaining = max(0.0, cap - max(0.0, current_rolling_recommendation_pct))
        suggested = min(regime_target, remaining)
        if remaining <= 1e-12:
            sleeve_status = "EXHAUSTED"
        elif remaining < regime_target:
            sleeve_status = "PARTIALLY_AVAILABLE"
        else:
            sleeve_status = "AVAILABLE"
    return {
        "normal_base_target_pct": normal_target,
        "legacy_50pct_exception_allowed": allowed,
        "regime_target_premium_pct": regime_target,
        "rolling_10_session_cap_pct": cap,
        "remaining_rolling_sleeve_capacity_pct": remaining,
        "suggested_max_premium_pct": suggested,
        "sleeve_capacity_status": sleeve_status,
    }


def build_regime_daily_state(thresholds: dict[str, Any]) -> pd.DataFrame:
    daily_path = DISPERSION_DIR / "realized_dispersion_daily_panel.csv"
    if not daily_path.exists():
        raise FileNotFoundError(f"daily_state_missing:{repo_relative(daily_path)}")
    daily = pd.read_csv(daily_path)
    rows = []
    for _, row in daily.iterrows():
        date = safe_date(row.get("date"))
        D_value = safe_float(row.get(D_METRIC))
        L_value = safe_float(row.get(L_METRIC))
        cls = classify_regime(D_value, L_value, thresholds)
        rows.append(
            {
                "regime_observation_date": date,
                "regime_data_asof_timestamp": f"{date}T20:00:00Z" if date else "",
                "D_value": D_value,
                "L_value": L_value,
                "D_high_cutoff": thresholds["D_high_cutoff"],
                "L_high_cutoff": thresholds["L_high_cutoff"],
                "D_state": cls["D_state"],
                "L_state": cls["L_state"],
                "regime_state": cls["regime_state"],
                "threshold_source": thresholds["threshold_source"],
                "threshold_manifest_hash": thresholds["threshold_manifest_hash"],
                "policy_version": POLICY_VERSION,
                "research_basis": "historical_regime_overlay",
                "no_signal_filtering": True,
                "no_broker_execution": True,
                "no_automatic_trade_action": True,
                "forward_review_required": True,
            }
        )
    return pd.DataFrame(rows)


def resolve_signal_decision_date(row: pd.Series | dict[str, Any]) -> str | None:
    for key in ["signal_decision_date", "breakout_date", "date", "scan_date"]:
        date = safe_date(row.get(key))
        if date:
            return date
    return safe_date(pd.Timestamp.now(tz="America/New_York"))


def signal_id_for(row: pd.Series | dict[str, Any], signal_date: str | None) -> str:
    existing = row.get("signal_id")
    if existing is not None and not pd.isna(existing) and str(existing).strip():
        return str(existing)
    ticker = str(row.get("ticker") or row.get("underlying_symbol") or "UNKNOWN")
    raw = f"{ticker}|{signal_date}|{row.get('production_adjusted_score','')}"
    return "overlay_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def load_state_for_signal(signal_date: str | None, daily_state: pd.DataFrame) -> dict[str, Any]:
    if not signal_date:
        thresholds = load_thresholds()
        cls = classify_regime(None, None, thresholds, lineage_ok=False)
        return {
            "regime_observation_date": "",
            "regime_data_asof_timestamp": "",
            "D_value": None,
            "L_value": None,
            "D_high_cutoff": thresholds["D_high_cutoff"],
            "L_high_cutoff": thresholds["L_high_cutoff"],
            "threshold_source": thresholds["threshold_source"],
            "threshold_manifest_hash": thresholds["threshold_manifest_hash"],
            **cls,
        }
    match = daily_state[daily_state["regime_observation_date"] == signal_date]
    if match.empty:
        thresholds = load_thresholds()
        cls = classify_regime(None, None, thresholds, lineage_ok=False)
        return {
            "regime_observation_date": signal_date,
            "regime_data_asof_timestamp": "",
            "D_value": None,
            "L_value": None,
            "D_high_cutoff": thresholds["D_high_cutoff"],
            "L_high_cutoff": thresholds["L_high_cutoff"],
            "threshold_source": thresholds["threshold_source"],
            "threshold_manifest_hash": thresholds["threshold_manifest_hash"],
            **cls,
        }
    return match.iloc[0].to_dict()


def rolling_decision_dates(daily_state: pd.DataFrame, signal_date: str, window: int) -> list[str]:
    dates = sorted(d for d in daily_state["regime_observation_date"].dropna().unique().tolist() if d <= signal_date)
    if signal_date not in dates:
        dates.append(signal_date)
        dates = sorted(dates)
    return dates[-window:]


def load_prior_recommendations(output_dir: Path = OUTPUT_DIR) -> pd.DataFrame:
    path = output_dir / "regime_overlay_signal_decisions.csv"
    if path.exists():
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    return pd.DataFrame()


def recommendation_rolling_total(
    prior: pd.DataFrame,
    window_dates: list[str],
    *,
    exclude_signal_id: str | None = None,
) -> float:
    if prior.empty:
        return 0.0
    work = prior.copy()
    if "rank" in work.columns:
        work = work[work["rank"].astype(str) == "S"]
    if "signal_decision_date" not in work.columns or "suggested_max_premium_pct" not in work.columns:
        return 0.0
    work = work[work["signal_decision_date"].astype(str).isin(set(window_dates))]
    if exclude_signal_id and "signal_id" in work.columns:
        work = work[work["signal_id"].astype(str) != exclude_signal_id]
    return float(pd.to_numeric(work["suggested_max_premium_pct"], errors="coerce").fillna(0.0).sum())


def confirmed_execution_rolling_total(execution_ledger: pd.DataFrame | None, window_dates: list[str]) -> tuple[float, str]:
    if execution_ledger is None or execution_ledger.empty:
        return 0.0, "RECOMMENDATION_ONLY"
    required = {"rank", "execution_status", "entry_decision_date", "initial_premium_pct"}
    if not required.issubset(execution_ledger.columns):
        return 0.0, "RECOMMENDATION_ONLY"
    ok_status = {"filled", "opened", "confirmed"}
    work = execution_ledger[
        (execution_ledger["rank"].astype(str) == "S")
        & (execution_ledger["execution_status"].astype(str).str.lower().isin(ok_status))
        & (execution_ledger["entry_decision_date"].astype(str).isin(set(window_dates)))
    ].copy()
    return float(pd.to_numeric(work["initial_premium_pct"], errors="coerce").fillna(0.0).sum()), "CONFIRMED_EXECUTION"


def decision_from_signal(
    row: pd.Series | dict[str, Any],
    *,
    daily_state: pd.DataFrame | None = None,
    policy: dict[str, Any] | None = None,
    prior_recommendations: pd.DataFrame | None = None,
    execution_ledger: pd.DataFrame | None = None,
    notification_timestamp: str | None = None,
) -> dict[str, Any]:
    policy = policy or load_policy()
    thresholds = load_thresholds()
    daily_state = daily_state if daily_state is not None else build_regime_daily_state(thresholds)
    notification_timestamp = notification_timestamp or iso_now()
    signal_date = resolve_signal_decision_date(row)
    signal_id = signal_id_for(row, signal_date)
    state = load_state_for_signal(signal_date, daily_state)
    window_dates = rolling_decision_dates(daily_state, signal_date or "", int(policy["rolling_window_sessions"]))
    prior_recommendations = prior_recommendations if prior_recommendations is not None else load_prior_recommendations()
    planned_total = recommendation_rolling_total(prior_recommendations, window_dates, exclude_signal_id=signal_id)
    actual_total, source = confirmed_execution_rolling_total(execution_ledger, window_dates)
    legacy_eligible = str(row.get("legacy_50pct_exception_eligible", "")).strip().lower() in {"true", "1", "yes"}
    sizing = apply_sizing_policy(
        str(state["regime_state"]),
        policy,
        legacy_50pct_exception_eligible=legacy_eligible,
        current_rolling_recommendation_pct=planned_total,
    )
    return {
        "signal_id": signal_id,
        "ticker": row.get("ticker") or row.get("underlying_symbol"),
        "rank": row.get("alert_rank") or row.get("signal_rank"),
        "signal_decision_date": signal_date,
        "notification_timestamp": notification_timestamp,
        "regime_observation_date": state.get("regime_observation_date"),
        "regime_data_asof_timestamp": state.get("regime_data_asof_timestamp"),
        "D_value": state.get("D_value"),
        "L_value": state.get("L_value"),
        "D_high_cutoff": thresholds["D_high_cutoff"],
        "L_high_cutoff": thresholds["L_high_cutoff"],
        "D_state": state.get("D_state"),
        "L_state": state.get("L_state"),
        "regime_state": state.get("regime_state"),
        "policy_version": POLICY_VERSION,
        "threshold_source": thresholds["threshold_source"],
        "threshold_manifest_hash": thresholds["threshold_manifest_hash"],
        "normal_base_target_pct": sizing["normal_base_target_pct"],
        "legacy_50pct_exception_eligible": legacy_eligible,
        "legacy_50pct_exception_allowed": sizing["legacy_50pct_exception_allowed"],
        "regime_target_premium_pct": sizing["regime_target_premium_pct"],
        "rolling_10_session_cap_pct": sizing["rolling_10_session_cap_pct"],
        "actual_confirmed_rolling_premium_pct": actual_total,
        "planned_recommendation_rolling_premium_pct": planned_total,
        "rolling_budget_source": source,
        "remaining_rolling_sleeve_capacity_pct": sizing["remaining_rolling_sleeve_capacity_pct"],
        "suggested_max_premium_pct": sizing["suggested_max_premium_pct"],
        "sleeve_capacity_status": sizing["sleeve_capacity_status"],
        "data_availability_status": state.get("data_availability_status", "AVAILABLE"),
        "conservative_fallback_reason": state.get("conservative_fallback_reason", ""),
        "research_basis": "historical_regime_overlay",
        "no_signal_filtering": True,
        "no_broker_execution": True,
        "no_automatic_trade_action": True,
        "forward_review_required": True,
        "no_auto_execution": True,
    }


def enrich_s_candidates(
    candidates: pd.DataFrame,
    *,
    output_dir: Path = OUTPUT_DIR,
    notification_timestamp: str | None = None,
    execution_ledger: pd.DataFrame | None = None,
    write_logs: bool = False,
) -> pd.DataFrame:
    if candidates.empty or "alert_rank" not in candidates.columns:
        return candidates.copy()
    policy = load_policy()
    thresholds = load_thresholds()
    daily_state = build_regime_daily_state(thresholds)
    prior = load_prior_recommendations(output_dir)
    enriched = candidates.copy()
    decisions: list[dict[str, Any]] = []
    for idx, row in enriched.iterrows():
        if str(row.get("alert_rank")) != "S":
            continue
        decision = decision_from_signal(
            row,
            daily_state=daily_state,
            policy=policy,
            prior_recommendations=prior,
            execution_ledger=execution_ledger,
            notification_timestamp=notification_timestamp,
        )
        decisions.append(decision)
        for key, value in decision.items():
            enriched.loc[idx, f"regime_overlay_{key}"] = value
    if write_logs:
        write_runtime_outputs(daily_state=daily_state, decisions=pd.DataFrame(decisions), output_dir=output_dir)
    return enriched


def pct(value: Any) -> str:
    v = safe_float(value)
    if v is None:
        return "N/A"
    return f"{v * 100:.1f}%"


def num(value: Any) -> str:
    v = safe_float(value)
    if v is None:
        return "N/A"
    return f"{v:.4f}"


def notification_overlay_block(row: pd.Series | dict[str, Any]) -> str:
    rank = str(row.get("alert_rank") or row.get("signal_rank") or "")
    if rank != "S":
        return ""
    try:
        decision = decision_from_signal(row)
    except Exception as exc:
        thresholds = {"D_high_cutoff": EXPECTED_D_HIGH_CUTOFF, "L_high_cutoff": EXPECTED_L_HIGH_CUTOFF}
        decision = {
            "regime_state": "REGIME_UNAVAILABLE_CONSERVATIVE",
            "D_value": None,
            "L_value": None,
            "D_state": "unavailable",
            "L_state": "unavailable",
            "D_high_cutoff": thresholds["D_high_cutoff"],
            "L_high_cutoff": thresholds["L_high_cutoff"],
            "suggested_max_premium_pct": 0.20,
            "planned_recommendation_rolling_premium_pct": 0.0,
            "rolling_10_session_cap_pct": 0.40,
            "legacy_50pct_exception_allowed": False,
            "rolling_budget_source": "RECOMMENDATION_ONLY",
            "regime_observation_date": resolve_signal_decision_date(row) or "",
            "policy_version": POLICY_VERSION,
            "conservative_fallback_reason": f"state unavailable / verification failure: {type(exc).__name__}",
        }
    legacy_text = "existing-rule-dependent" if bool(decision.get("legacy_50pct_exception_allowed")) else "DISABLED"
    cap_text = pct(decision.get("rolling_10_session_cap_pct"))
    planned_text = pct(decision.get("planned_recommendation_rolling_premium_pct"))
    if str(decision.get("regime_state")) == "NORMAL":
        suggested_label = "Suggested base premium"
    else:
        suggested_label = "Suggested max premium"
    reason = decision.get("conservative_fallback_reason") or ""
    reason_line = f"\nReason: {reason}" if reason else ""
    return (
        "Regime sizing overlay\n"
        f"Regime: {decision.get('regime_state')}\n"
        f"D20: {num(decision.get('D_value'))} ({decision.get('D_state')}; cutoff {num(decision.get('D_high_cutoff'))})\n"
        f"QQQ minus EQW 20d: {num(decision.get('L_value'))} ({decision.get('L_state')}; cutoff {num(decision.get('L_high_cutoff'))})\n"
        f"{suggested_label}: {pct(decision.get('suggested_max_premium_pct'))}\n"
        f"Rolling 10-session S sleeve: {planned_text} / {cap_text}\n"
        f"50% exception: {legacy_text}\n"
        f"Budget source: {decision.get('rolling_budget_source')}\n"
        f"As-of: {decision.get('regime_observation_date')} close\n"
        f"Policy: {decision.get('policy_version')}"
        f"{reason_line}"
    )


def build_rolling_ledger(decisions: pd.DataFrame) -> pd.DataFrame:
    if decisions.empty:
        return pd.DataFrame(
            columns=[
                "signal_id",
                "ticker",
                "signal_decision_date",
                "regime_state",
                "planned_recommendation_rolling_premium_pct",
                "actual_confirmed_rolling_premium_pct",
                "rolling_10_session_cap_pct",
                "remaining_rolling_sleeve_capacity_pct",
                "sleeve_capacity_status",
                "rolling_budget_source",
            ]
        )
    cols = [
        "signal_id",
        "ticker",
        "signal_decision_date",
        "regime_state",
        "planned_recommendation_rolling_premium_pct",
        "actual_confirmed_rolling_premium_pct",
        "rolling_10_session_cap_pct",
        "remaining_rolling_sleeve_capacity_pct",
        "sleeve_capacity_status",
        "rolling_budget_source",
    ]
    return decisions.reindex(columns=cols)


def create_manifest(output_dir: Path) -> dict[str, Any]:
    expected_names = set(REQUIRED_OUTPUTS)
    actual_names = {p.name for p in output_dir.iterdir() if p.is_file() and p.name != MANIFEST_NAME}
    unexpected = sorted(actual_names - expected_names)
    if unexpected:
        raise ValueError(f"unexpected_output_files:{unexpected}")
    files = []
    for name in REQUIRED_OUTPUTS:
        path = output_dir / name
        if not path.exists():
            raise FileNotFoundError(f"required_output_missing:{repo_relative(path)}")
        files.append({"relative_path": name, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "artifact_version": POLICY_VERSION,
        "created_at_utc": iso_now(),
        "git_head": git_head(),
        "files": files,
        "content_set_hash": hashlib.sha256(json_dumps(files).encode("utf-8")).hexdigest(),
        "no_broker_execution": True,
        "no_automatic_trade_action": True,
    }
    write_json(output_dir / MANIFEST_NAME, manifest)
    return manifest


def write_runtime_outputs(
    *,
    daily_state: pd.DataFrame | None = None,
    decisions: pd.DataFrame | None = None,
    forward_review: pd.DataFrame | None = None,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    thresholds = load_thresholds()
    artifacts = verify_source_artifacts()
    if daily_state is None:
        daily_state = build_regime_daily_state(thresholds)
    if decisions is None:
        decisions = pd.DataFrame()
    if decisions.empty:
        decisions = pd.DataFrame(columns=DECISION_COLUMNS)
    if forward_review is None:
        try:
            import scripts.build_morita_regime_sizing_overlay_forward_review_v1 as forward

            forward_review = forward.build_forward_review()
        except Exception:
            forward_review = pd.DataFrame(
                [
                    {
                        "regime_state": "FORWARD_REVIEW_UNAVAILABLE",
                        "complete_signal_count": 0,
                        "note": "forward review failed; see receipt",
                    }
                ]
            )
    write_dataframe(output_dir / "regime_overlay_daily_state.csv", daily_state)
    write_dataframe(output_dir / "regime_overlay_signal_decisions.csv", decisions)
    write_dataframe(output_dir / "regime_overlay_rolling_sleeve_ledger.csv", build_rolling_ledger(decisions))
    write_dataframe(output_dir / "regime_overlay_forward_review.csv", forward_review)
    receipt = {
        "artifact_version": POLICY_VERSION,
        "created_at_utc": iso_now(),
        "git_head": git_head(),
        "policy_path": repo_relative(POLICY_PATH),
        "thresholds": thresholds,
        "source_artifacts": artifacts,
        "policy_mode": "notification_and_logging_only",
        "no_signal_filtering": True,
        "no_broker_execution": True,
        "no_automatic_trade_action": True,
        "runtime_decision_count": int(len(decisions)),
    }
    write_json(output_dir / "regime_overlay_receipt.json", receipt)
    summary = [
        "# Morita Regime Sizing Overlay v1",
        "",
        "Status: completed runtime artifact build.",
        "",
        f"- policy_version: `{POLICY_VERSION}`",
        f"- D_high cutoff: `{thresholds['D_high_cutoff']}`",
        f"- L_high cutoff: `{thresholds['L_high_cutoff']}`",
        f"- threshold_source: `{thresholds['threshold_source']}`",
        f"- signal filtering introduced: `false`",
        f"- broker execution enabled: `false`",
        f"- automatic trade action enabled: `false`",
        "",
        "Policy is logging/notification only and remains manual/config-driven.",
    ]
    (output_dir / "regime_overlay_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    manifest = create_manifest(output_dir)
    return {"receipt": receipt, "manifest": manifest}


def build_handoff_bundle(output_dir: Path = OUTPUT_DIR) -> None:
    thresholds = load_thresholds()
    policy = load_policy()
    manifest_hash = file_sha256(output_dir / MANIFEST_NAME) if (output_dir / MANIFEST_NAME).exists() else "not_built"
    lines = [
        "# Morita Regime Sizing Overlay v1 - ChatGPT Handoff Bundle",
        "",
        "## Completion Status",
        "",
        f"- policy_version: `{POLICY_VERSION}`",
        f"- git_head_at_build: `{git_head()}`",
        f"- output_manifest_hash: `{manifest_hash}`",
        "- mode: notification and logging only",
        "",
        "## Verified Source Artifacts",
        "",
        f"- realized dispersion: `{repo_relative(DISPERSION_DIR)}`",
        f"- narrow leadership confirmation: `{repo_relative(NARROW_DIR)}`",
        f"- 2023 frozen replication v2: `{repo_relative(FROZEN_2023_DIR)}`",
        f"- metric implementation: `{repo_relative(Path(dispersion.__file__))}`",
        "",
        "## Inherited Thresholds",
        "",
        f"- D = `{D_METRIC}` high cutoff `{thresholds['D_high_cutoff']}`",
        f"- L = `{L_METRIC}` high cutoff `{thresholds['L_high_cutoff']}`",
        f"- threshold source: `{thresholds['threshold_source']}`",
        f"- threshold manifest hash: `{thresholds['threshold_manifest_hash']}`",
        "",
        "## Policy Table",
        "",
        "| Regime | Suggested max/base premium | Rolling 10-session new-S cap | 50% exception |",
        "| --- | ---: | ---: | --- |",
        f"| NORMAL | {policy['normal']['base_target_premium_pct']:.0%} base | none | existing-rule-dependent |",
        f"| HIGH_DISPERSION | {policy['high_dispersion']['target_premium_pct']:.0%} max | {policy['high_dispersion']['rolling_10_session_new_S_cap_pct']:.0%} | disabled |",
        f"| NARROW_LEADERSHIP | {policy['narrow_leadership']['target_premium_pct']:.0%} max | {policy['narrow_leadership']['rolling_10_session_new_S_cap_pct']:.0%} | disabled |",
        f"| REGIME_UNAVAILABLE_CONSERVATIVE | {policy['regime_unavailable_conservative']['target_premium_pct']:.0%} max | {policy['regime_unavailable_conservative']['rolling_10_session_new_S_cap_pct']:.0%} | disabled |",
        "",
        "## Source Timing Contract",
        "",
        "- Join rule: `regime_observation_date == signal_decision_date`.",
        "- Future dates and missing D/L states fail closed to `REGIME_UNAVAILABLE_CONSERVATIVE`.",
        "- No new threshold, universe, provider, or proxy was introduced.",
        "",
        "## Notification Examples",
        "",
        "S notifications receive a compact `Regime sizing overlay` block. A/B notifications are not modified by the overlay.",
        "",
        "```text",
        "Regime sizing overlay",
        "Regime: NARROW_LEADERSHIP",
        "D20: 0.1120 (HIGH; cutoff 0.1076)",
        "QQQ minus EQW 20d: 0.0310 (HIGH; cutoff 0.0212)",
        "Suggested max premium: 15.0%",
        "Rolling 10-session S sleeve: 15.0% / 30.0%",
        "50% exception: DISABLED",
        "Budget source: RECOMMENDATION_ONLY",
        "As-of: YYYY-MM-DD close",
        "Policy: morita_regime_sizing_overlay_v1",
        "```",
        "",
        "## Rolling Sleeve Definition",
        "",
        "- Window: current decision session plus preceding nine trading decision sessions.",
        "- Confirmed execution ledger is read-only if supplied.",
        "- Without confirmed fills, prior overlay recommendations are used as advisory bookkeeping and labeled `RECOMMENDATION_ONLY`.",
        "- Exhausted capacity never suppresses an S notification; it only lowers displayed suggested maximum to the remaining capacity.",
        "",
        "## Confirmations",
        "",
        "- S signal logic did not change.",
        "- A/B notification eligibility did not change.",
        "- No threshold was retuned.",
        "- No broker order was created.",
        "- No broker/account data was fetched.",
        "- No automatic execution exists.",
        "- Forward review is logging-only.",
        "- Policy values do not auto-adjust; changes require manual config edits.",
    ]
    CHATGPT_BUNDLE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    thresholds = load_thresholds()
    daily_state = build_regime_daily_state(thresholds)
    write_runtime_outputs(daily_state=daily_state, decisions=pd.DataFrame(), output_dir=output_dir)
    build_handoff_bundle(output_dir)
    print(json_dumps({"status": "completed", "output_dir": repo_relative(output_dir), "bundle": repo_relative(CHATGPT_BUNDLE)}))


if __name__ == "__main__":
    main()
