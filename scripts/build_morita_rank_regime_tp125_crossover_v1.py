from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.build_morita_realized_dispersion_quick_screen_v1 as dispersion
from src.morita_single_call_reference import s_single_call_reference_engine as ref


ARTIFACT_VERSION = "morita_rank_regime_tp125_crossover_v1"
SPEC_PATH = REPO_ROOT / "config" / ARTIFACT_VERSION / "study_spec.json"
OUTPUT_DIR = REPO_ROOT / "outputs" / ARTIFACT_VERSION
CHATGPT_BUNDLE = REPO_ROOT / f"{ARTIFACT_VERSION}_chatgpt_bundle.md"
MANIFEST_NAME = "study_content_manifest.json"
D_METRIC = "broad_russell1000_cross_sectional_dispersion_20d"
L_METRIC = "broad_russell1000_qqq_minus_eqw_return_20d"
EXPECTED_D_HIGH_CUTOFF = 0.1076297441118458
EXPECTED_L_HIGH_CUTOFF = 0.0211600633543862
CELLS = [
    "S_NORMAL",
    "S_HIGH_DISPERSION",
    "S_NARROW_LEADERSHIP",
    "A_NORMAL",
    "A_HIGH_DISPERSION",
    "A_NARROW_LEADERSHIP",
]
REQUIRED_OUTPUTS = [
    "source_artifact_lineage.json",
    "threshold_inheritance.json",
    "option_contract_lineage.json",
    "rank_regime_tp125_reconciliation.csv",
    "rank_regime_tp125_trade_level.csv",
    "rank_regime_tp125_cell_summary.csv",
    "rank_regime_tp125_required_comparisons.csv",
    "rank_regime_tp125_concentration.csv",
    "rank_regime_tp125_primary_label.json",
    "rank_regime_tp125_period_comparison.csv",
    "study_receipt.json",
    "study_summary.md",
    MANIFEST_NAME,
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def safe_clean_output_dir(path: Path) -> None:
    if path.exists():
        resolved = path.resolve()
        if REPO_ROOT.resolve() not in resolved.parents and resolved != REPO_ROOT.resolve():
            raise SystemExit(f"refusing_to_clean_outside_repo:{resolved}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def nonempty(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return str(value).strip() != ""


def pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{value:.3f}"


def md_table(df: pd.DataFrame, limit: int | None = None) -> str:
    if df.empty:
        return "_No rows._"
    if limit is not None:
        df = df.head(limit).copy()
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        values = []
        for col in cols:
            value = row[col]
            if pd.isna(value):
                values.append("")
            elif isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUTS:
        if name == MANIFEST_NAME:
            continue
        path = output_dir / name
        if path.exists():
            files.append({"relative_path": name, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "manifest_version": ARTIFACT_VERSION,
        "created_at_utc": iso_now(),
        "required_files": REQUIRED_OUTPUTS,
        "files": files,
        "content_set_hash": text_hash(json.dumps(files, sort_keys=True)),
    }
    write_json(output_dir / MANIFEST_NAME, manifest)
    return manifest


def verify_manifest(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {"verified": False, "missing": [MANIFEST_NAME], "extra": [], "changed": []}
    manifest = load_json(manifest_path)
    missing = [name for name in REQUIRED_OUTPUTS if not (output_dir / name).exists()]
    expected = {row["relative_path"]: row["sha256"] for row in manifest.get("files", [])}
    changed = []
    for rel, expected_hash in expected.items():
        path = output_dir / rel
        if not path.exists() or file_sha256(path) != expected_hash:
            changed.append(rel)
    actual = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    extra = [name for name in actual if name not in REQUIRED_OUTPUTS]
    return {"verified": not missing and not changed and not extra, "missing": missing, "extra": extra, "changed": changed}


def load_threshold_inheritance(spec: dict[str, Any]) -> dict[str, Any]:
    source = REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_state_cutoffs.csv"
    cutoffs = pd.read_csv(source)
    rows = cutoffs[cutoffs["metric"].isin([D_METRIC, L_METRIC])]
    if len(rows) != 2:
        raise SystemExit("required_regime_thresholds_missing")
    values = {row["metric"]: {"p33": float(row["p33"]), "p67": float(row["p67"])} for _, row in rows.iterrows()}
    if abs(values[D_METRIC]["p67"] - EXPECTED_D_HIGH_CUTOFF) > 1e-12:
        raise SystemExit("D_high_cutoff_verification_failed")
    if abs(values[L_METRIC]["p67"] - EXPECTED_L_HIGH_CUTOFF) > 1e-12:
        raise SystemExit("L_high_cutoff_verification_failed")
    return {
        "threshold_source": repo_relative(source),
        "threshold_source_sha256": file_sha256(source),
        "threshold_source_manifest": repo_relative(REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_content_manifest.json"),
        "threshold_source_manifest_sha256": file_sha256(REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_content_manifest.json"),
        "D_metric_name": D_METRIC,
        "L_metric_name": L_METRIC,
        "D_high_cutoff": values[D_METRIC]["p67"],
        "D_low_cutoff": values[D_METRIC]["p33"],
        "L_high_cutoff": values[L_METRIC]["p67"],
        "L_low_cutoff": values[L_METRIC]["p33"],
        "classification": {
            "NORMAL": "D_value < D_high_cutoff regardless L_value",
            "HIGH_DISPERSION": "D_value >= D_high_cutoff and L_value < L_high_cutoff",
            "NARROW_LEADERSHIP": "D_value >= D_high_cutoff and L_value >= L_high_cutoff",
        },
        "verification_status": "passed",
        "no_threshold_reestimation": True,
    }


def classify_regime(D_value: Any, L_value: Any, thresholds: dict[str, Any]) -> dict[str, Any]:
    d = safe_float(D_value)
    l = safe_float(L_value)
    if d is None or l is None:
        return {"D_state": "unavailable", "L_state": "unavailable", "regime_state": "REGIME_UNAVAILABLE"}
    d_high = d >= float(thresholds["D_high_cutoff"])
    l_high = l >= float(thresholds["L_high_cutoff"])
    if d_high and l_high:
        regime = "NARROW_LEADERSHIP"
    elif d_high and not l_high:
        regime = "HIGH_DISPERSION"
    else:
        regime = "NORMAL"
    return {
        "D_state": "HIGH" if d_high else "NOT_HIGH",
        "L_state": "HIGH" if l_high else "NOT_HIGH",
        "regime_state": regime,
    }


def load_primary_panel(spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    baseline_dir = REPO_ROOT / spec["source_baseline_dir"]
    panel = pd.read_csv(baseline_dir / "morita_bot_baseline_panel.csv", dtype={"signal_id": str, "underlying_symbol": str})
    context = pd.read_csv(REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_signal_context_panel.csv", dtype={"signal_id": str})
    complete_sa = context[
        context["signal_rank"].astype(str).isin(spec["eligible_ranks"])
        & (context["outcome_status"].astype(str) == spec["complete_status"])
    ][["signal_id", "signal_decision_date"]].drop_duplicates()
    decision_end = str(complete_sa["signal_decision_date"].max())
    decision_start = str(complete_sa["signal_decision_date"].min())
    eligible_ids = set(complete_sa["signal_id"].astype(str))
    primary = panel[
        panel["signal_id"].astype(str).isin(eligible_ids)
        & panel["signal_rank"].astype(str).isin(spec["eligible_ranks"])
        & (panel["outcome_status"].astype(str) == spec["complete_status"])
    ].copy()
    meta = {
        "period_id": spec["primary_period"]["period_id"],
        "decision_start": decision_start,
        "decision_end": decision_end,
        "source": "realized_dispersion_signal_context_panel_complete_SA_window",
    }
    return primary, meta


def load_2023_panel(spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rs_dir = REPO_ROOT / spec["source_2023_rs_warmup_retest_dir"]
    panel = pd.read_csv(rs_dir / "morita_2023_signal_panel.csv", dtype={"signal_id": str, "underlying_symbol": str})
    start = spec["descriptive_period_2023"]["decision_start"]
    end = spec["descriptive_period_2023"]["decision_end"]
    eligible = panel[
        panel["signal_rank"].astype(str).isin(spec["eligible_ranks"])
        & (panel["outcome_status"].astype(str) == spec["complete_status"])
        & (panel["signal_decision_date"].astype(str) >= start)
        & (panel["signal_decision_date"].astype(str) <= end)
    ].copy()
    meta = {"period_id": spec["descriptive_period_2023"]["period_id"], "decision_start": start, "decision_end": end}
    return eligible, meta


def load_daily_regime_states(spec: dict[str, Any], thresholds: dict[str, Any]) -> pd.DataFrame:
    daily = pd.read_csv(REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_daily_panel.csv")
    required = ["date", D_METRIC, L_METRIC]
    missing = [col for col in required if col not in daily.columns]
    if missing:
        raise SystemExit(f"regime_daily_missing_column:{missing[0]}")
    state_rows = []
    for _, row in daily.iterrows():
        c = classify_regime(row[D_METRIC], row[L_METRIC], thresholds)
        state_rows.append(
            {
                "signal_decision_date": str(row["date"]),
                "D_value": row[D_METRIC],
                "L_value": row[L_METRIC],
                **c,
            }
        )
    out = pd.DataFrame(state_rows)
    if (out["regime_state"] == "REGIME_UNAVAILABLE").any():
        raise SystemExit("regime_unavailable_in_daily_panel")
    return out


def baseline_input_root_for_2023(spec: dict[str, Any]) -> Path:
    rs_dir = REPO_ROOT / spec["source_2023_rs_warmup_retest_dir"]
    receipt = load_json(rs_dir / "retest_receipt.json")
    input_root = receipt.get("extended_input_root") or receipt.get("input_root") or "input/morita_baseline_2022warmup_2023_2026_v1"
    root = REPO_ROOT / input_root
    if not (root / "sources" / "daily_ohlcv_merged.csv").exists():
        alt = rs_dir / "input" / "morita_baseline_2022warmup_2023_2026_v1"
        if (alt / "sources" / "daily_ohlcv_merged.csv").exists():
            return alt
        raise SystemExit("2023_ohlcv_input_missing")
    return root


def terminal_underlying_return(history: pd.DataFrame, entry_price: float, exit_date: str) -> float | None:
    row = history[history["date"] == pd.Timestamp(exit_date)]
    if row.empty or entry_price <= 0:
        return None
    return (float(row.iloc[0]["close"]) / entry_price - 1.0) * 100.0


def underlying_mae_until(history: pd.DataFrame, entry_session: str, exit_date: str, entry_price: float) -> float | None:
    if entry_price <= 0:
        return None
    sub = history[(history["date"] >= pd.Timestamp(entry_session)) & (history["date"] <= pd.Timestamp(exit_date))]
    if sub.empty:
        return None
    return (float(sub["low"].min()) / entry_price - 1.0) * 100.0


def breakout_low_breach_until(history: pd.DataFrame, entry_session: str, exit_date: str, breakout_day_low: Any) -> bool | None:
    low = safe_float(breakout_day_low)
    if low is None:
        return None
    sub = history[(history["date"] >= pd.Timestamp(entry_session)) & (history["date"] <= pd.Timestamp(exit_date))]
    if sub.empty:
        return None
    return bool((sub["low"].astype(float) < low).any())


def model_period_trades(
    panel: pd.DataFrame,
    period_id: str,
    input_root: Path,
    state_daily: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if panel.empty:
        return pd.DataFrame(), pd.DataFrame()
    tickers = set(panel["underlying_symbol"].astype(str))
    histories = ref.load_ohlcv_subset(input_root, tickers)
    state = state_daily.copy()
    state["signal_decision_date"] = state["signal_decision_date"].astype(str)
    rows = []
    coverage = []
    for _, row in panel.iterrows():
        sig = row.to_dict()
        signal_id = str(sig["signal_id"])
        ticker = str(sig["underlying_symbol"])
        state_match = state[state["signal_decision_date"] == str(sig["signal_decision_date"])]
        if state_match.empty:
            coverage.append({"period_id": period_id, "signal_id": signal_id, "ticker": ticker, "stage": "regime_join", "status": "excluded", "reason": "missing_regime_state"})
            continue
        if ticker not in histories:
            coverage.append({"period_id": period_id, "signal_id": signal_id, "ticker": ticker, "stage": "option_model", "status": "excluded", "reason": "missing_ticker_ohlcv"})
            continue
        result = ref.model_trade(sig, histories[ticker])
        if result["status"] != "eligible":
            coverage.append({"period_id": period_id, "signal_id": signal_id, "ticker": ticker, "stage": "option_model", "status": "excluded", "reason": result.get("excluded_reason", "")})
            continue
        state_row = state_match.iloc[0].to_dict()
        tp125_hit = nonempty(result.get("first_hit_125_date", ""))
        modeled_exit_date = str(result["first_hit_125_date"] if tp125_hit else result["terminal_date"])
        modeled_return = 125.0 if tp125_hit else float(result["terminal_net_return_pct"])
        entry_price = float(result["entry_underlying_price"])
        history = histories[ticker]
        rank = str(sig["signal_rank"])
        regime = str(state_row["regime_state"])
        cell = f"{rank}_{regime}"
        rows.append(
            {
                "period_id": period_id,
                "signal_id": signal_id,
                "signal_decision_date": sig["signal_decision_date"],
                "entry_session": sig["entry_session"],
                "ticker": ticker,
                "rank": rank,
                "cell": cell,
                "theme": sig.get("theme", ""),
                "production_adjusted_score": sig.get("production_adjusted_score", ""),
                "standard_rs_score": sig.get("standard_rs_score", ""),
                "volume_multiple": sig.get("volume_multiple", ""),
                "D_value": state_row["D_value"],
                "L_value": state_row["L_value"],
                "D_state": state_row["D_state"],
                "L_state": state_row["L_state"],
                "regime_state": regime,
                "entry_underlying_price": entry_price,
                "breakout_day_low": result.get("breakout_day_low", ""),
                "strike": result["strike"],
                "entry_delta": result["entry_delta"],
                "expiry_date": result["expiry_date"],
                "entry_debit": result["entry_debit"],
                "first_tp125_event_date": result["first_hit_125_date"],
                "first_tp125_event_session": result["first_hit_125_session"],
                "tp125_hit": tp125_hit,
                "modeled_exit_date": modeled_exit_date,
                "modeled_exit_reason": "TP125" if tp125_hit else result["terminal_reason"],
                "modeled_exit_option_return_pct": modeled_return,
                "terminal_net_return_pct_without_tp125_cap": result["terminal_net_return_pct"],
                "max_net_return_high_pct": result["max_net_return_high_pct"],
                "min_net_return_close_pct": result["min_net_return_close_pct"],
                "modeled_underlying_return_at_exit_pct": terminal_underlying_return(history, entry_price, modeled_exit_date),
                "modeled_underlying_MAE_pct": underlying_mae_until(history, sig["entry_session"], modeled_exit_date, entry_price),
                "breakout_low_breach_before_exit": breakout_low_breach_until(history, sig["entry_session"], modeled_exit_date, result.get("breakout_day_low", "")),
                "day10_plus5_success": boolish(sig.get("reached_plus_5pct_within_10_sessions", False)),
                "timeout_10_sessions_under_threshold": boolish(sig.get("timeout_10_sessions_under_threshold", False)),
                "source_outcome_status": sig.get("outcome_status", ""),
                "synthetic_fixed_iv_reference_model": True,
                "not_historical_option_fill_reconstruction": True,
                "not_live_execution_estimate": True,
            }
        )
        coverage.append({"period_id": period_id, "signal_id": signal_id, "ticker": ticker, "stage": "eligible", "status": "eligible", "reason": ""})
    return pd.DataFrame(rows), pd.DataFrame(coverage)


def profit_factor(returns: pd.Series) -> float | None:
    if returns.empty:
        return None
    gains = returns[returns > 0].sum()
    losses = returns[returns < 0].sum()
    if losses == 0:
        return math.inf if gains > 0 else None
    return float(gains / abs(losses))


def mean_loss(returns: pd.Series) -> float | None:
    losses = returns[returns < 0]
    if losses.empty:
        return None
    return float(losses.mean())


def median_loss(returns: pd.Series) -> float | None:
    losses = returns[returns < 0]
    if losses.empty:
        return None
    return float(losses.median())


def top_share(group: pd.DataFrame, col: str, n: int) -> float | None:
    if group.empty:
        return None
    positives = group[group[col] > 0].copy()
    total = positives[col].sum()
    if total <= 0:
        return None
    return float(positives[col].sort_values(ascending=False).head(n).sum() / total)


def summarize_group(group: pd.DataFrame, period_id: str, cell: str) -> dict[str, Any]:
    r = pd.to_numeric(group["modeled_exit_option_return_pct"], errors="coerce").dropna()
    ticker_counts = group["ticker"].astype(str).value_counts() if not group.empty else pd.Series(dtype=int)
    theme_counts = group["theme"].astype(str).value_counts() if not group.empty else pd.Series(dtype=int)
    return {
        "period_id": period_id,
        "cell": cell,
        "rank": cell.split("_", 1)[0],
        "regime_state": cell.split("_", 1)[1],
        "trade_count": int(len(group)),
        "unique_ticker_count": int(group["ticker"].nunique()) if not group.empty else 0,
        "tp125_hit_rate": float(group["tp125_hit"].map(bool).mean()) if not group.empty else None,
        "profit_factor": profit_factor(r),
        "mean_option_return_pct": float(r.mean()) if not r.empty else None,
        "median_option_return_pct": float(r.median()) if not r.empty else None,
        "p10_option_return_pct": float(r.quantile(0.10)) if not r.empty else None,
        "p25_option_return_pct": float(r.quantile(0.25)) if not r.empty else None,
        "p75_option_return_pct": float(r.quantile(0.75)) if not r.empty else None,
        "mean_loss_pct": mean_loss(r),
        "median_loss_pct": median_loss(r),
        "median_option_MAE_pct": float(pd.to_numeric(group["min_net_return_close_pct"], errors="coerce").median()) if not group.empty else None,
        "median_underlying_MAE_pct": float(pd.to_numeric(group["modeled_underlying_MAE_pct"], errors="coerce").median()) if not group.empty else None,
        "breakout_low_breach_rate": float(group["breakout_low_breach_before_exit"].dropna().map(bool).mean()) if group["breakout_low_breach_before_exit"].notna().any() else None,
        "day10_plus5_success_rate": float(group["day10_plus5_success"].map(bool).mean()) if not group.empty else None,
        "timeout_rate": float(group["timeout_10_sessions_under_threshold"].map(bool).mean()) if not group.empty else None,
        "largest_single_ticker": str(ticker_counts.index[0]) if not ticker_counts.empty else "",
        "largest_single_ticker_share": float(ticker_counts.iloc[0] / len(group)) if not ticker_counts.empty else None,
        "top5_ticker_share": float(ticker_counts.head(5).sum() / len(group)) if not ticker_counts.empty else None,
        "largest_theme": str(theme_counts.index[0]) if not theme_counts.empty else "",
        "largest_theme_share": float(theme_counts.iloc[0] / len(group)) if not theme_counts.empty else None,
        "top1_profit_share": top_share(group, "modeled_exit_option_return_pct", 1),
        "top3_profit_share": top_share(group, "modeled_exit_option_return_pct", 3),
        "sample_flag": "SPARSE_SAMPLE" if len(group) < 10 else "",
    }


def build_cell_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period_id in sorted(trades["period_id"].unique()) if not trades.empty else []:
        period = trades[trades["period_id"] == period_id]
        for cell in CELLS:
            rows.append(summarize_group(period[period["cell"] == cell].copy(), period_id, cell))
    return pd.DataFrame(rows)


def build_concentration(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (period_id, cell), group in trades.groupby(["period_id", "cell"], dropna=False):
        for ticker, count in group["ticker"].astype(str).value_counts().head(10).items():
            rows.append(
                {
                    "period_id": period_id,
                    "cell": cell,
                    "dimension": "ticker",
                    "name": ticker,
                    "trade_count": int(count),
                    "share": float(count / len(group)),
                    "profit_sum_pct": float(group[group["ticker"].astype(str) == ticker]["modeled_exit_option_return_pct"].sum()),
                }
            )
        for theme, count in group["theme"].astype(str).value_counts().head(10).items():
            rows.append(
                {
                    "period_id": period_id,
                    "cell": cell,
                    "dimension": "theme",
                    "name": theme,
                    "trade_count": int(count),
                    "share": float(count / len(group)),
                    "profit_sum_pct": float(group[group["theme"].astype(str) == theme]["modeled_exit_option_return_pct"].sum()),
                }
            )
    return pd.DataFrame(rows)


def comparison_row(summary: pd.DataFrame, period_id: str, comp: dict[str, Any]) -> dict[str, Any]:
    left = summary[(summary["period_id"] == period_id) & (summary["cell"] == comp["left_cell"])]
    right = summary[(summary["period_id"] == period_id) & (summary["cell"] == comp["right_cell"])]
    l = left.iloc[0].to_dict() if not left.empty else {}
    r = right.iloc[0].to_dict() if not right.empty else {}

    def value(row: dict[str, Any], key: str) -> float | None:
        return safe_float(row.get(key))

    return {
        "period_id": period_id,
        "comparison_id": comp["comparison_id"],
        "comparison_role": comp["comparison_role"],
        "left_cell": comp["left_cell"],
        "right_cell": comp["right_cell"],
        "left_trade_count": int(l.get("trade_count", 0) or 0),
        "right_trade_count": int(r.get("trade_count", 0) or 0),
        "left_tp125_hit_rate": value(l, "tp125_hit_rate"),
        "right_tp125_hit_rate": value(r, "tp125_hit_rate"),
        "tp125_hit_rate_delta_left_minus_right": (value(l, "tp125_hit_rate") - value(r, "tp125_hit_rate")) if value(l, "tp125_hit_rate") is not None and value(r, "tp125_hit_rate") is not None else None,
        "left_profit_factor": value(l, "profit_factor"),
        "right_profit_factor": value(r, "profit_factor"),
        "pf_delta_left_minus_right": (value(l, "profit_factor") - value(r, "profit_factor")) if value(l, "profit_factor") is not None and value(r, "profit_factor") is not None and math.isfinite(value(l, "profit_factor")) and math.isfinite(value(r, "profit_factor")) else None,
        "left_median_option_return_pct": value(l, "median_option_return_pct"),
        "right_median_option_return_pct": value(r, "median_option_return_pct"),
        "median_delta_left_minus_right": (value(l, "median_option_return_pct") - value(r, "median_option_return_pct")) if value(l, "median_option_return_pct") is not None and value(r, "median_option_return_pct") is not None else None,
        "left_p10_option_return_pct": value(l, "p10_option_return_pct"),
        "right_p10_option_return_pct": value(r, "p10_option_return_pct"),
        "sample_status": "OK" if int(l.get("trade_count", 0) or 0) >= 10 and int(r.get("trade_count", 0) or 0) >= 10 else "SPARSE_SAMPLE",
    }


def build_comparisons(summary: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    periods = sorted(summary["period_id"].dropna().unique())
    for period_id in periods:
        for comp in spec["required_comparisons"]:
            rows.append(comparison_row(summary, period_id, comp))
    return pd.DataFrame(rows)


def build_period_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cell in CELLS:
        primary = summary[(summary["period_id"] == "primary_2024_2026_completed_confirmation_interval") & (summary["cell"] == cell)]
        y2023 = summary[(summary["period_id"] == "descriptive_2023_rs_warmup_frozen_threshold") & (summary["cell"] == cell)]
        combined = summary[(summary["period_id"] == "combined_2023_2026_descriptive") & (summary["cell"] == cell)]
        p = primary.iloc[0].to_dict() if not primary.empty else {}
        y = y2023.iloc[0].to_dict() if not y2023.empty else {}
        c = combined.iloc[0].to_dict() if not combined.empty else {}
        rows.append(
            {
                "cell": cell,
                "primary_trades": int(p.get("trade_count", 0) or 0),
                "primary_tp125_hit_rate": safe_float(p.get("tp125_hit_rate")),
                "primary_profit_factor": safe_float(p.get("profit_factor")),
                "descriptive_2023_trades": int(y.get("trade_count", 0) or 0),
                "descriptive_2023_tp125_hit_rate": safe_float(y.get("tp125_hit_rate")),
                "descriptive_2023_profit_factor": safe_float(y.get("profit_factor")),
                "combined_descriptive_trades": int(c.get("trade_count", 0) or 0),
                "combined_descriptive_tp125_hit_rate": safe_float(c.get("tp125_hit_rate")),
                "combined_descriptive_profit_factor": safe_float(c.get("profit_factor")),
                "period_pooling_status": "combined_row_descriptive_only_not_used_for_primary_label",
            }
        )
    return pd.DataFrame(rows)


def primary_label(summary: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    period_id = spec["primary_period"]["period_id"]
    a = summary[(summary["period_id"] == period_id) & (summary["cell"] == "A_NORMAL")]
    s = summary[(summary["period_id"] == period_id) & (summary["cell"] == "S_NARROW_LEADERSHIP")]
    arow = a.iloc[0].to_dict() if not a.empty else {}
    srow = s.iloc[0].to_dict() if not s.empty else {}
    a_count = int(arow.get("trade_count", 0) or 0)
    s_count = int(srow.get("trade_count", 0) or 0)
    min_side = int(spec["sample_gates"]["primary_comparison_min_per_side"])
    a_hit = safe_float(arow.get("tp125_hit_rate"))
    s_hit = safe_float(srow.get("tp125_hit_rate"))
    a_pf = safe_float(arow.get("profit_factor"))
    s_pf = safe_float(srow.get("profit_factor"))
    floor = float(spec["tp125_floor"]["floor_hit_rate"])
    preferred = float(spec["tp125_floor"]["preferred_hit_rate"])
    if a_count < min_side or s_count < min_side:
        label = "INSUFFICIENT_PRIMARY_SAMPLE"
    elif a_hit is None or a_hit < floor:
        label = "A_NORMAL_TP125_NOT_ESTABLISHED"
    elif a_hit >= preferred and s_hit is not None and a_hit > s_hit and a_pf is not None and s_pf is not None and a_pf > s_pf:
        label = "A_NORMAL_POTENTIAL_RANK_REGIME_CROSSOVER"
    elif a_hit >= preferred:
        label = "A_NORMAL_MEETS_PREFERRED_TP125_RATE"
    else:
        label = "A_NORMAL_MEETS_TP125_FLOOR"
    return {
        "artifact_version": ARTIFACT_VERSION,
        "period_id": period_id,
        "primary_question": "Can A_NORMAL beat S_NARROW_LEADERSHIP on standardized TP125 single-call reference?",
        "primary_label": label,
        "A_NORMAL_trade_count": a_count,
        "S_NARROW_LEADERSHIP_trade_count": s_count,
        "A_NORMAL_tp125_hit_rate": a_hit,
        "S_NARROW_LEADERSHIP_tp125_hit_rate": s_hit,
        "A_NORMAL_profit_factor": a_pf,
        "S_NARROW_LEADERSHIP_profit_factor": s_pf,
        "label_rules_fixed_in_spec": True,
        "primary_label_uses_2023": False,
        "research_only": True,
        "actionization_allowed": False,
    }


def verify_tp125_semantics(primary_trades: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    source = pd.read_csv(REPO_ROOT / spec["option_reference_output_dir"] / "s_single_call_trade_terminal_summary.csv", dtype={"signal_id": str})
    ours = primary_trades[primary_trades["rank"] == "S"].copy()
    merged = ours.merge(source[["signal_id", "terminal_net_return_pct", "first_hit_125_date", "terminal_date", "terminal_reason"]], on="signal_id", how="inner", suffixes=("_study", "_reference"))
    mismatches = []
    for _, row in merged.iterrows():
        ref_first_hit = row["first_hit_125_date_reference"] if "first_hit_125_date_reference" in row.index else row["first_hit_125_date"]
        ref_terminal = row["terminal_net_return_pct_reference"] if "terminal_net_return_pct_reference" in row.index else row["terminal_net_return_pct"]
        ref_hit = nonempty(ref_first_hit)
        expected = 125.0 if ref_hit else float(ref_terminal)
        if abs(float(row["modeled_exit_option_return_pct"]) - expected) > 1e-8:
            mismatches.append(str(row["signal_id"]))
    if mismatches:
        raise SystemExit(f"tp125_semantics_mismatch:{mismatches[0]}")
    return {
        "contract_id": ref.ASSUMPTIONS.model_id,
        "reference_output_dir": spec["option_reference_output_dir"],
        "reference_terminal_summary_sha256": file_sha256(REPO_ROOT / spec["option_reference_output_dir"] / "s_single_call_trade_terminal_summary.csv"),
        "engine_module": repo_relative(Path(ref.__file__)),
        "engine_sha256": file_sha256(Path(ref.__file__)),
        "model_spec": repo_relative(ref.MODEL_SPEC_PATH),
        "model_spec_sha256": file_sha256(ref.MODEL_SPEC_PATH),
        "primary_S_overlap_checked": int(len(merged)),
        "tp125_semantics_verified_against_existing_S_reference": True,
        "assumptions": ref.ASSUMPTIONS.__dict__,
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
    }


def build_reconciliation(primary_panel: pd.DataFrame, y2023_panel: pd.DataFrame, coverage: pd.DataFrame, trades: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for period_id, panel in [
        (spec["primary_period"]["period_id"], primary_panel),
        (spec["descriptive_period_2023"]["period_id"], y2023_panel),
    ]:
        cov = coverage[coverage["period_id"] == period_id] if not coverage.empty else pd.DataFrame()
        tr = trades[trades["period_id"] == period_id] if not trades.empty else pd.DataFrame()
        rows.extend(
            [
                {"period_id": period_id, "bucket": "source_rank_S_or_A_complete_rows", "count": int(len(panel)), "primary_denominator": True},
                {"period_id": period_id, "bucket": "eligible_trade_rows", "count": int(len(tr)), "primary_denominator": True},
                {"period_id": period_id, "bucket": "excluded_missing_regime_state", "count": int(((cov["reason"] == "missing_regime_state").sum()) if not cov.empty else 0), "primary_denominator": False},
                {"period_id": period_id, "bucket": "excluded_missing_or_invalid_option_model", "count": int(((cov["status"] == "excluded") & (cov["reason"] != "missing_regime_state")).sum()) if not cov.empty else 0, "primary_denominator": False},
                {"period_id": period_id, "bucket": "duplicate_signal_id_rows", "count": int(panel["signal_id"].duplicated().sum()) if "signal_id" in panel else 0, "primary_denominator": False},
                {"period_id": period_id, "bucket": "duplicate_ticker_date_rank_rows", "count": int(panel[["underlying_symbol", "signal_decision_date", "signal_rank"]].duplicated().sum()) if not panel.empty else 0, "primary_denominator": False},
            ]
        )
        if not tr.empty:
            for rank, count in tr["rank"].value_counts().items():
                rows.append({"period_id": period_id, "bucket": f"eligible_rank_{rank}", "count": int(count), "primary_denominator": False})
            for regime, count in tr["regime_state"].value_counts().items():
                rows.append({"period_id": period_id, "bucket": f"eligible_regime_{regime}", "count": int(count), "primary_denominator": False})
    return pd.DataFrame(rows)


def source_lineage(spec: dict[str, Any]) -> dict[str, Any]:
    paths = {
        "study_spec": SPEC_PATH,
        "baseline_panel": REPO_ROOT / spec["source_baseline_dir"] / "morita_bot_baseline_panel.csv",
        "baseline_receipt": REPO_ROOT / spec["source_baseline_dir"] / "baseline_receipt.json",
        "baseline_source_manifest": REPO_ROOT / spec["source_baseline_dir"] / "source_content_manifest.json",
        "realized_dispersion_context": REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_signal_context_panel.csv",
        "realized_dispersion_daily_panel": REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_daily_panel.csv",
        "realized_dispersion_manifest": REPO_ROOT / spec["source_realized_dispersion_dir"] / "realized_dispersion_content_manifest.json",
        "narrow_leadership_receipt": REPO_ROOT / spec["source_narrow_leadership_confirmation_dir"] / "narrow_leadership_receipt.json",
        "frozen_2023_receipt": REPO_ROOT / spec["source_2023_frozen_replication_dir"] / "replication_receipt.json",
        "rs_warmup_2023_panel": REPO_ROOT / spec["source_2023_rs_warmup_retest_dir"] / "morita_2023_signal_panel.csv",
        "rs_warmup_2023_manifest": REPO_ROOT / spec["source_2023_rs_warmup_retest_dir"] / "rs_warmup_retest_content_manifest.json",
        "dispersion_metric_implementation": Path(dispersion.__file__),
        "option_reference_engine": Path(ref.__file__),
    }
    return {
        "artifact_version": ARTIFACT_VERSION,
        "created_at_utc": iso_now(),
        "git_head_at_run": git_head(),
        "research_only": True,
        "actionization_allowed": False,
        "new_market_data_downloaded": False,
        "bot_rerun_or_rule_change": False,
        "sources": {name: {"path": repo_relative(path), "sha256": file_sha256(path)} for name, path in paths.items() if path.exists()},
    }


def render_summary(label: dict[str, Any], summary: pd.DataFrame, comparisons: pd.DataFrame, reconciliation: pd.DataFrame, meta: dict[str, Any]) -> str:
    primary_summary = summary[summary["period_id"] == "primary_2024_2026_completed_confirmation_interval"][
        ["cell", "trade_count", "tp125_hit_rate", "profit_factor", "median_option_return_pct", "p10_option_return_pct", "day10_plus5_success_rate", "breakout_low_breach_rate", "sample_flag"]
    ].copy()
    primary_comp = comparisons[comparisons["period_id"] == "primary_2024_2026_completed_confirmation_interval"][
        ["comparison_id", "left_trade_count", "right_trade_count", "left_tp125_hit_rate", "right_tp125_hit_rate", "left_profit_factor", "right_profit_factor", "sample_status"]
    ].copy()
    rec = reconciliation[reconciliation["period_id"] == "primary_2024_2026_completed_confirmation_interval"].copy()
    lines = [
        "# Morita Rank x Regime TP125 Crossover Study v1",
        "",
        "## Conclusion",
        f"- Primary label: `{label['primary_label']}`",
        f"- Primary window: `{meta['primary']['decision_start']}` to `{meta['primary']['decision_end']}`.",
        f"- A_NORMAL trades: `{label['A_NORMAL_trade_count']}`, TP125 hit rate `{pct(label['A_NORMAL_tp125_hit_rate'])}`, PF `{pct(label['A_NORMAL_profit_factor'])}`.",
        f"- S_NARROW_LEADERSHIP trades: `{label['S_NARROW_LEADERSHIP_trade_count']}`, TP125 hit rate `{pct(label['S_NARROW_LEADERSHIP_tp125_hit_rate'])}`, PF `{pct(label['S_NARROW_LEADERSHIP_profit_factor'])}`.",
        "- 2023 rows are descriptive only and are not pooled into the primary label.",
        "- This is a synthetic fixed-IV reference model, not historical option-fill reconstruction and not a live execution estimate.",
        "",
        "## Primary Cell Summary",
        md_table(primary_summary),
        "",
        "## Required Comparisons",
        md_table(primary_comp),
        "",
        "## Reconciliation",
        md_table(rec),
        "",
        "## Guardrails",
        "- Existing production rank, current source panels, and inherited realized-dispersion thresholds are used without threshold retuning.",
        "- The option contract is the same fixed-IV 60DTE Delta0.6 single-call reference engine used for S; TP125 semantics are verified against existing S reference output.",
        "- No notification, order, sizing, or live-bot behavior is changed.",
    ]
    return "\n".join(lines) + "\n"


def render_operations_doc(spec: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Morita Rank x Regime TP125 Crossover Operations v1",
            "",
            "This study is research-only. It does not alter production notification, sizing, or order behavior.",
            "",
            "## Run",
            "",
            "```powershell",
            "python scripts/build_morita_rank_regime_tp125_crossover_v1.py run",
            "python scripts/build_morita_rank_regime_tp125_crossover_v1.py verify",
            "```",
            "",
            "## Primary Label",
            "",
            "Use `outputs/morita_rank_regime_tp125_crossover_v1/rank_regime_tp125_primary_label.json`.",
            "The primary label is based only on the 2024-2026 completed confirmation interval. 2023 is descriptive.",
            "",
            "## No Live Use",
            "",
            "Do not route this output into alerts, execution, portfolio sizing, or risk overrides without a separate approved production task.",
        ]
    ) + "\n"


def render_docs(spec: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Morita Rank x Regime TP125 Crossover v1",
            "",
            "This document defines the fixed research comparison for whether A-rank signals in NORMAL regime can be more attractive than S-rank signals in NARROW_LEADERSHIP regime under the same TP125 single-call reference contract.",
            "",
            "## Fixed Inputs",
            "",
            f"- D metric: `{spec['D_metric_name']}`",
            f"- L metric: `{spec['L_metric_name']}`",
            f"- D high cutoff: `{spec['expected_D_high_cutoff']}`",
            f"- L high cutoff: `{spec['expected_L_high_cutoff']}`",
            "- NORMAL: D not high, regardless L.",
            "- HIGH_DISPERSION: D high and L not high.",
            "- NARROW_LEADERSHIP: D high and L high.",
            "",
            "## Contract",
            "",
            "- 60DTE call, target delta 0.6, fixed IV 60%.",
            "- Entry markup 5%, exit haircut 5%.",
            "- TP125 is an executable model-path high touch, capped to +125%.",
            "",
            "## Interpretation",
            "",
            "This is not a parameter search. It is a fixed crossover screen. Any live rule change requires a separate forward-tracking and production implementation task.",
        ]
    ) + "\n"


def run_study(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    safe_clean_output_dir(output_dir)
    thresholds = load_threshold_inheritance(spec)
    state_daily = load_daily_regime_states(spec, thresholds)
    primary_panel, primary_meta = load_primary_panel(spec)
    y2023_panel, y2023_meta = load_2023_panel(spec)
    primary_input_root = ref.baseline_input_root(REPO_ROOT / spec["source_baseline_dir"])
    y2023_input_root = baseline_input_root_for_2023(spec)
    primary_trades, primary_cov = model_period_trades(primary_panel, spec["primary_period"]["period_id"], primary_input_root, state_daily)
    y2023_trades, y2023_cov = model_period_trades(y2023_panel, spec["descriptive_period_2023"]["period_id"], y2023_input_root, state_daily)
    trades = pd.concat([primary_trades, y2023_trades], ignore_index=True)
    if not trades.empty:
        combined = trades.copy()
        combined["period_id"] = "combined_2023_2026_descriptive"
        trades_all = pd.concat([trades, combined], ignore_index=True)
    else:
        trades_all = trades
    coverage = pd.concat([primary_cov, y2023_cov], ignore_index=True)
    option_lineage = verify_tp125_semantics(primary_trades, spec)
    summary = build_cell_summary(trades_all)
    concentration = build_concentration(trades_all)
    comparisons = build_comparisons(summary, spec)
    period_comp = build_period_comparison(summary)
    label = primary_label(summary, spec)
    reconciliation = build_reconciliation(primary_panel, y2023_panel, coverage, trades, spec)
    lineage = source_lineage(spec)
    write_json(output_dir / "source_artifact_lineage.json", lineage)
    write_json(output_dir / "threshold_inheritance.json", thresholds)
    write_json(output_dir / "option_contract_lineage.json", option_lineage)
    write_dataframe(output_dir / "rank_regime_tp125_reconciliation.csv", reconciliation)
    write_dataframe(output_dir / "rank_regime_tp125_trade_level.csv", trades_all)
    write_dataframe(output_dir / "rank_regime_tp125_cell_summary.csv", summary)
    write_dataframe(output_dir / "rank_regime_tp125_required_comparisons.csv", comparisons)
    write_dataframe(output_dir / "rank_regime_tp125_concentration.csv", concentration)
    write_json(output_dir / "rank_regime_tp125_primary_label.json", label)
    write_dataframe(output_dir / "rank_regime_tp125_period_comparison.csv", period_comp)
    meta = {"primary": primary_meta, "descriptive_2023": y2023_meta}
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "status": "completed",
        "created_at_utc": iso_now(),
        "git_head_at_run": git_head(),
        "primary_label": label["primary_label"],
        "primary_period": primary_meta,
        "descriptive_2023_period": y2023_meta,
        "primary_source_rows": int(len(primary_panel)),
        "descriptive_2023_source_rows": int(len(y2023_panel)),
        "eligible_trade_rows_excluding_combined": int(len(trades)),
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
        "research_only": True,
        "actionization_allowed": False,
        "new_market_data_downloaded": False,
        "threshold_search_performed": False,
        "primary_label_uses_2023": False,
    }
    write_json(output_dir / "study_receipt.json", receipt)
    summary_md = render_summary(label, summary, comparisons, reconciliation, meta)
    (output_dir / "study_summary.md").write_text(summary_md, encoding="utf-8")
    build_manifest(output_dir)
    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / f"{ARTIFACT_VERSION}.md").write_text(render_docs(spec), encoding="utf-8")
    (docs_dir / "morita_rank_regime_tp125_crossover_operations_v1.md").write_text(render_operations_doc(spec), encoding="utf-8")
    bundle = "\n".join(
        [
            summary_md,
            "\n---\n",
            "## Source Artifact Lineage",
            "```json",
            json_dumps(lineage),
            "```",
            "",
            "## Threshold Inheritance",
            "```json",
            json_dumps(thresholds),
            "```",
            "",
            "## Option Contract Lineage",
            "```json",
            json_dumps(option_lineage),
            "```",
            "",
            "## Primary Label JSON",
            "```json",
            json_dumps(label),
            "```",
        ]
    )
    CHATGPT_BUNDLE.write_text(bundle + "\n", encoding="utf-8")
    return receipt


def verify_run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    status = verify_manifest(output_dir)
    if not status["verified"]:
        raise SystemExit(f"study_manifest_verification_failed:{status}")
    label = load_json(output_dir / "rank_regime_tp125_primary_label.json")
    receipt = load_json(output_dir / "study_receipt.json")
    if label.get("primary_label_uses_2023") is not False:
        raise SystemExit("primary_label_uses_2023")
    if receipt.get("actionization_allowed") is not False:
        raise SystemExit("actionization_guard_failed")
    if receipt.get("synthetic_fixed_iv_reference_model") is not True:
        raise SystemExit("option_model_guard_failed")
    return {"status": "verified", "output_dir": repo_relative(output_dir), "manifest_sha256": file_sha256(output_dir / MANIFEST_NAME)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "verify"])
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    out = Path(args.output_dir)
    if not out.is_absolute():
        out = REPO_ROOT / out
    if args.command == "run":
        print(json_dumps(run_study(out)))
    else:
        print(json_dumps(verify_run(out)))


if __name__ == "__main__":
    main()
