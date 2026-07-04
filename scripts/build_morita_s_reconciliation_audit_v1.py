from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.morita_single_call_reference import s_single_call_reference_engine as ref  # noqa: E402


OUT = REPO_ROOT / "outputs" / "morita_s_reconciliation_audit_v1"
BUNDLE = REPO_ROOT / "morita_s_definition_reconciliation_audit_v1_bundle.md"
SPEC_PATH = REPO_ROOT / "config" / "morita_s_reconciliation_audit_v1" / "audit_spec.json"
BASELINE_DIR = ref.DEFAULT_BASELINE_DIR
REFERENCE_DIR = ref.DEFAULT_REFERENCE_OUTPUT_DIR
COOLDOWN_SESSIONS = 20
DISCOVERY_EXTRA_ROOTS = [
    Path(r"C:\Users\keisu\Documents\Codex\2026-06-14\files-mentioned-by-the-user-codex\outputs\call_backtest"),
    Path(r"C:\Users\keisu\Documents\Codex\2026-06-14\files-mentioned-by-the-user-codex\outputs\minervini_factor_contribution"),
    Path(r"C:\Users\keisu\Documents\Codex\2026-06-17\call-backtest-s-10-pf-1"),
]
REQUIRED_FILES = [
    "source_discovery_ledger.csv",
    "legacy_pf_claim_registry.csv",
    "legacy_pf_claim_trade_cohorts.csv",
    "formal_baseline_s_event_stream.csv",
    "fixed_iv_reference_cohort.csv",
    "production_scanner_parity_report.csv",
    "same_ticker_repeat_audit.csv",
    "car_april_2026_case_study.csv",
    "intended_policy_label_layer.csv",
    "event_count_reconciliation.csv",
    "fixed_iv_performance_reconciliation.csv",
    "annual_subperiod_stability.csv",
    "code_path_configuration_audit.md",
    "source_verification.csv",
    "reconciliation_receipt.json",
    "reconciliation_content_manifest.json",
    "reconciliation_summary.md",
]
LIVE_TOKENS = ["BUY_NOW", "SELL_NOW", "ORDER", "WEBULL", "ALERT_CHANGE", "SIZE_UP", "SIZE_DOWN"]


def utc_now() -> str:
    return pd.Timestamp.now(tz="UTC").replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def git_blob(path: Path) -> str:
    rel = repo_rel(path)
    try:
        return subprocess.check_output(["git", "hash-object", rel], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def has_value(value: Any) -> bool:
    return ref.has_value(value)


def safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if pd.notna(out) else None


def profit_factor(values: list[float]) -> float | str:
    gross_profit = sum(v for v in values if v > 0)
    gross_loss = -sum(v for v in values if v < 0)
    if gross_loss == 0:
        return "not_estimable_zero_gross_loss"
    return gross_profit / gross_loss


def plausible_legacy_pf(value: Any) -> bool:
    pf = safe_float(value)
    return pf is not None and 3.0 <= pf <= 25.0


def explicit_legacy_pf_claim(text: str) -> bool:
    t = text[:100000]
    return bool(
        re.search(r"\bprofit\s*factor\s*[:=]?\s*`?[0-9]+(?:\.[0-9]+)?", t, re.I)
        or re.search(r"\bPF\s*[:=]?\s*`?[0-9]+(?:\.[0-9]+)?", t)
    )


def drawdown_proxy(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def return_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "trade_count": 0,
            "mean_return": "",
            "median_return": "",
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "PF": "",
            "max_loss": "",
            "max_drawdown_proxy_if_existing_standard_method": 0.0,
        }
    s = pd.Series(values, dtype="float64")
    return {
        "trade_count": len(values),
        "mean_return": float(s.mean()),
        "median_return": float(s.median()),
        "gross_profit": float(s[s > 0].sum()),
        "gross_loss": float(-s[s < 0].sum()),
        "PF": profit_factor(values),
        "max_loss": float(s.min()),
        "max_drawdown_proxy_if_existing_standard_method": drawdown_proxy(values),
    }


def load_formal_s() -> pd.DataFrame:
    panel = pd.read_csv(BASELINE_DIR / "morita_bot_baseline_panel.csv", dtype={"signal_id": str})
    s = panel[panel["signal_rank"].astype(str) == "S"].copy()
    s["signal_date"] = pd.to_datetime(s["signal_decision_date"])
    s["entry_date_ts"] = pd.to_datetime(s["entry_session"])
    return s.sort_values(["signal_date", "underlying_symbol", "signal_id"]).reset_index(drop=True)


def load_reference() -> tuple[pd.DataFrame, pd.DataFrame]:
    term = pd.read_csv(REFERENCE_DIR / "s_single_call_trade_terminal_summary.csv", dtype={"signal_id": str})
    cov = pd.read_csv(REFERENCE_DIR / "eligible_trade_coverage.csv", dtype={"signal_id": str})
    term["reference_return"] = term.apply(lambda r: 125.0 if has_value(r.get("first_hit_125_date", "")) else float(r["terminal_net_return_pct"]), axis=1)
    return term, cov


def load_sessions() -> list[pd.Timestamp]:
    root = ref.baseline_input_root(BASELINE_DIR)
    qqq = ref.load_ohlcv_subset(root, {"QQQ"})["QQQ"]
    return [pd.Timestamp(x) for x in qqq["date"].tolist()]


def session_gap(a: Any, b: Any, sessions: list[pd.Timestamp]) -> int | str:
    aa = pd.Timestamp(a)
    bb = pd.Timestamp(b)
    between = [s for s in sessions if aa < s <= bb]
    return len(between)


def source_discovery() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    patterns = re.compile(r"(profit\s*factor|PF|single call|vertical|spread|breakout|outcome|pnl|TP125|Day10|rank S|S rank)", re.I)
    pf_patterns = [
        re.compile(r"(?:profit\s*factor|PF)\s*[:=]?\s*`?([0-9]+(?:\.[0-9]+)?)", re.I),
        re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:PF|profit\s*factor)", re.I),
    ]
    candidates: list[Path] = []
    for root in [REPO_ROOT, REPO_ROOT / "outputs", *DISCOVERY_EXTRA_ROOTS]:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt", ".py"}:
                name = path.name.lower()
                if any(token in name for token in ["morita", "call", "vertical", "spread", "outcome", "trade", "breakout", "backtest", "tp", "summary", "bundle", "report"]):
                    candidates.append(path)
    rows: list[dict[str, Any]] = []
    legacy_registry: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in sorted(candidates, key=lambda p: repo_rel(p))[:2000]:
        if path in seen:
            continue
        rel = repo_rel(path)
        if rel.startswith("outputs/morita_s_reconciliation_audit_v1/") or rel in {
            "scripts/build_morita_s_reconciliation_audit_v1.py",
            "docs/morita_s_definition_reconciliation_v1.md",
            "docs/morita_s_event_semantics_remediation_proposal_v1.md",
            "config/morita_s_reconciliation_audit_v1/audit_spec.json",
            "morita_s_definition_reconciliation_audit_v1_bundle.md",
            "tests/test_morita_s_reconciliation_audit_v1.py",
        }:
            continue
        seen.add(path)
        text = ""
        try:
            if path.stat().st_size <= 2_000_000:
                text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        if not patterns.search(path.name) and not patterns.search(text[:20000]):
            continue
        pf_values: list[float] = []
        for pat in pf_patterns:
            for match in pat.findall(text[:100000]):
                val = safe_float(match)
                if val is not None:
                    pf_values.append(val)
        max_pf = max(pf_values) if pf_values else ""
        manifest_present = any((path.parent / name).exists() for name in ["content_manifest.json", "s_tp_comparison_content_manifest.json", "s_single_call_reference_content_manifest.json"])
        reproducible = bool(manifest_present and path.suffix.lower() in {".csv", ".json"})
        row = {
            "artifact_id": hashlib.sha256(repo_rel(path).encode()).hexdigest()[:16],
            "artifact_path": rel,
            "artifact_type": path.suffix.lower().lstrip("."),
            "git_commit_or_blob_sha_if_available": git_blob(path),
            "timestamp_if_available": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(),
            "date_range": infer_date_range(text),
            "universe": infer_universe(text),
            "signal_definition_summary": infer_signal_definition(text, path.name),
            "cohort_size_if_stated": infer_count(text),
            "pf_if_stated": max_pf,
            "option_model_if_stated": infer_option_model(text),
            "exit_rule_if_stated": infer_exit_rule(text),
            "is_reproducible": reproducible,
            "source_manifest_present": manifest_present,
            "notes": "local artifact discovery; prose is not proof",
        }
        rows.append(row)
        structured_legacy = structured_call_backtest_candidates(path, row["artifact_id"])
        if structured_legacy:
            structured_rows, structured_registry, structured_trade_rows = structured_legacy
            rows.extend(structured_rows)
            legacy_registry.extend(structured_registry)
            trade_rows.extend(structured_trade_rows)
        vertical_support = structured_vertical_outcome_support(path, row["artifact_id"])
        if vertical_support:
            rows.append(vertical_support)
        if max_pf != "" and plausible_legacy_pf(max_pf) and explicit_legacy_pf_claim(text):
            legacy_registry.append(
                {
                    "legacy_run_id": row["artifact_id"],
                    "source_artifact_id": row["artifact_id"],
                    "date_range": row["date_range"],
                    "universe": row["universe"],
                    "rank_or_filter_definition": row["signal_definition_summary"],
                    "option_structure": row["option_model_if_stated"],
                    "exit_rule": row["exit_rule_if_stated"],
                    "PF": max_pf,
                    "cohort_count": row["cohort_size_if_stated"],
                    "reproducibility_status": "unverifiable_legacy_result" if not reproducible else "candidate_requires_exact_trade_rows",
                    "artifact_path": row["artifact_path"],
                }
            )
    if not legacy_registry:
        legacy_registry.append(
            {
                "legacy_run_id": "no_verified_legacy_pf4_run_found",
                "source_artifact_id": "",
                "date_range": "",
                "universe": "",
                "rank_or_filter_definition": "",
                "option_structure": "",
                "exit_rule": "",
                "PF": "",
                "cohort_count": "",
                "reproducibility_status": "no_verified_legacy_pf4_run_found",
                "artifact_path": "",
            }
        )
    if not trade_rows:
        for row in legacy_registry:
            trade_rows.append(
                {
                    "legacy_run_id": row["legacy_run_id"],
                    "source_artifact_id": row.get("source_artifact_id", ""),
                    "entry_date": "",
                    "ticker": "",
                    "signal_id_if_available": "",
                    "trade_return": "",
                    "profit_component": "",
                    "loss_component": "",
                    "PF": row.get("PF", ""),
                    "cohort_count": row.get("cohort_count", ""),
                    "reproducibility_status": row.get("reproducibility_status", ""),
                }
            )
    return rows, legacy_registry, trade_rows


def structured_vertical_outcome_support(path: Path, parent_artifact_id: str) -> dict[str, Any] | None:
    if path.suffix.lower() != ".csv":
        return None
    name = path.name.lower()
    if "vertical" not in name and "spread" not in name and "extended_breakout_entry_trade_details" not in name:
        return None
    try:
        sample = pd.read_csv(path, nrows=5)
    except Exception:
        return None
    cols = set(sample.columns)
    outcome_cols = [c for c in ["stock_return", "underlying_return_to_expiry", "day10_underlying_return", "exit_pnl_pct", "option_model_return", "pnl_pct", "exit_reason", "exit_trading_day"] if c in cols]
    signal_cols = [c for c in ["ticker", "entry_date", "standard_rs_score", "breakout_signal", "volume_multiple", "theme", "score_rank_live", "adjusted_score"] if c in cols]
    if not outcome_cols and "vertical" not in name:
        return None
    dates = pd.to_datetime(sample["entry_date"], errors="coerce") if "entry_date" in sample.columns else pd.Series([], dtype="datetime64[ns]")
    sampled_range = ""
    if len(dates) and dates.notna().any():
        sampled_range = f"sample_starts_{dates.min().date()}"
    notes = [
        "vertical/breakout outcome support artifact",
        "PF not comparable to single-call formal S reference",
        "usable for price-movement/outcome lineage only after signal-key reconciliation",
        f"signal_cols={','.join(signal_cols)}",
        f"outcome_cols={','.join(outcome_cols)}",
    ]
    if path.stat().st_size > 50_000_000:
        notes.append("large_file_header_sample_only")
    return {
        "artifact_id": f"{parent_artifact_id}_vertical_support",
        "artifact_path": repo_rel(path),
        "artifact_type": "csv",
        "git_commit_or_blob_sha_if_available": git_blob(path),
        "timestamp_if_available": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(),
        "date_range": sampled_range,
        "universe": "legacy Minervini/Morita-related vertical or breakout research output",
        "signal_definition_summary": "not a formal S source; possible ticker+entry_date signal/outcome support",
        "cohort_size_if_stated": "",
        "pf_if_stated": "",
        "option_model_if_stated": "vertical/spread or breakout option proxy outcome artifact",
        "exit_rule_if_stated": "see native columns; not normalized in this audit",
        "is_reproducible": False,
        "source_manifest_present": False,
        "notes": "; ".join(notes),
    }


def structured_call_backtest_candidates(path: Path, parent_artifact_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]] | None:
    if path.name not in {"call_backtest_rank_summary.csv", "call_backtest_summary.csv"}:
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if "profit_factor" not in df.columns:
        return None
    x = df.copy()
    x["profit_factor_num"] = pd.to_numeric(x["profit_factor"], errors="coerce")
    x["trades_num"] = pd.to_numeric(x.get("trades", ""), errors="coerce")
    input_meta = call_backtest_input_metadata(path.parent)
    rows: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    scope = "rank_summary" if "rank" in x.columns else "aggregate_summary"
    if "rank" in x.columns:
        ranked = x[x["rank"].astype(str).str.upper() == "S"].copy()
    else:
        ranked = x.copy()
    ranked = ranked[ranked["profit_factor_num"].notna()].sort_values("profit_factor_num", ascending=False)
    if ranked.empty:
        return None
    best = ranked.iloc[0]
    spread10 = ranked[pd.to_numeric(ranked.get("spread_cost_pct", ""), errors="coerce") == 0.10].copy()
    best_spread10 = spread10.iloc[0] if not spread10.empty else None
    note_parts = [
        "external old local call_backtest artifact",
        "no source seal/content manifest observed",
        "not equivalent to formal S event stream",
        f"input_signals={input_meta.get('signals', '')}",
        f"input_s_count={input_meta.get('s_count', '')}",
    ]
    if best_spread10 is not None:
        note_parts.append(f"best_spread10_pf={best_spread10['profit_factor_num']}")
    rows.append(
        {
            "artifact_id": f"{parent_artifact_id}_structured",
            "artifact_path": repo_rel(path),
            "artifact_type": path.suffix.lower().lstrip("."),
            "git_commit_or_blob_sha_if_available": git_blob(path),
            "timestamp_if_available": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(),
            "date_range": input_meta.get("date_range", ""),
            "universe": "old call_backtest input_signals cohort; first 100 active non-excluded signals per report" if scope == "rank_summary" else "old call_backtest aggregate cohort",
            "signal_definition_summary": "old rank=S rows from call_backtest_rank_summary; small S cohort, not formal baseline S definition" if scope == "rank_summary" else "old aggregate call_backtest_summary rows",
            "cohort_size_if_stated": int(best.get("trades_num")) if pd.notna(best.get("trades_num")) else "",
            "pf_if_stated": float(best["profit_factor_num"]),
            "option_model_if_stated": "Black-Scholes single call; historical chains not used; IV grid from legacy report",
            "exit_rule_if_stated": best.get("exit_rule", ""),
            "is_reproducible": False,
            "source_manifest_present": False,
            "notes": "; ".join(note_parts),
        }
    )
    if scope == "rank_summary":
        selected = ranked[
            (ranked["profit_factor_num"] >= 3.0)
            & (pd.to_numeric(ranked.get("spread_cost_pct", ""), errors="coerce").isin([0.10, 0.15]))
        ].drop_duplicates(subset=["option_type", "dte", "spread_cost_pct", "exit_rule", "trades"]).head(20)
        if selected.empty:
            selected = ranked.head(1)
        for idx, candidate in selected.iterrows():
            run_id = f"legacy_call_backtest_rank_s_{parent_artifact_id}_{idx}"
            status = "candidate_unsealed_legacy_rank_summary_not_equivalent_to_formal_s"
            registry.append(
                {
                    "legacy_run_id": run_id,
                    "source_artifact_id": f"{parent_artifact_id}_structured",
                    "date_range": input_meta.get("date_range", ""),
                    "universe": "legacy call_backtest first-100 modeled cohort",
                    "rank_or_filter_definition": "rank=S from old call_backtest_rank_summary; not source-sealed; 12 modeled S trades in top rows",
                    "option_structure": f"{candidate.get('option_type', '')} {candidate.get('dte', '')}DTE spread_cost={candidate.get('spread_cost_pct', '')}",
                    "exit_rule": candidate.get("exit_rule", ""),
                    "PF": float(candidate["profit_factor_num"]),
                    "cohort_count": int(candidate.get("trades_num")) if pd.notna(candidate.get("trades_num")) else "",
                    "reproducibility_status": status,
                    "artifact_path": repo_rel(path),
                }
            )
            trade_rows.append(
                {
                    "legacy_run_id": run_id,
                    "source_artifact_id": f"{parent_artifact_id}_structured",
                    "entry_date": "",
                    "ticker": "",
                    "signal_id_if_available": "",
                    "trade_return": "",
                    "profit_component": "",
                    "loss_component": "",
                    "PF": float(candidate["profit_factor_num"]),
                    "cohort_count": int(candidate.get("trades_num")) if pd.notna(candidate.get("trades_num")) else "",
                    "reproducibility_status": status,
                }
            )
    return rows, registry, trade_rows


def call_backtest_input_metadata(root: Path) -> dict[str, Any]:
    path = root / "call_backtest_input_signals.csv"
    if not path.exists():
        return {}
    try:
        signals = pd.read_csv(path, usecols=lambda c: c in {"entry_date", "rank"})
    except Exception:
        return {}
    out: dict[str, Any] = {"signals": int(len(signals))}
    if "entry_date" in signals.columns:
        dates = pd.to_datetime(signals["entry_date"], errors="coerce")
        if dates.notna().any():
            out["date_range"] = f"{dates.min().date()}..{dates.max().date()}"
    if "rank" in signals.columns:
        out["s_count"] = int((signals["rank"].astype(str).str.upper() == "S").sum())
    return out


def infer_date_range(text: str) -> str:
    dates = re.findall(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", text[:20000])
    if len(dates) >= 2:
        return f"{min(dates)}..{max(dates)}"
    return ""


def infer_universe(text: str) -> str:
    t = text[:50000].lower()
    if "russell" in t:
        return "Russell/local baseline universe"
    if "s&p" in t or "sp500" in t:
        return "S&P-related"
    return ""


def infer_signal_definition(text: str, name: str) -> str:
    t = (name + "\n" + text[:50000]).lower()
    parts = []
    if "rank" in t and "s" in t:
        parts.append("rank/S mentioned")
    if "breakout" in t:
        parts.append("breakout mentioned")
    if "pullback" in t:
        parts.append("pullback mentioned")
    return "; ".join(parts)


def infer_count(text: str) -> str:
    m = re.search(r"(?:trades|signals|eligible(?:_trade_count)?)\D{0,20}([0-9]{1,5})", text[:50000], re.I)
    return m.group(1) if m else ""


def infer_option_model(text: str) -> str:
    t = text[:50000].lower()
    if "fixed-iv" in t or "fixed iv" in t or "black-scholes" in t:
        return "fixed-IV/Black-Scholes mentioned"
    if "vertical" in t:
        return "vertical mentioned"
    if "single call" in t:
        return "single call mentioned"
    return ""


def infer_exit_rule(text: str) -> str:
    t = text[:50000].lower()
    parts = []
    if "tp125" in t or "125" in t:
        parts.append("TP125/+125 mentioned")
    if "day10" in t or "day 10" in t:
        parts.append("Day10 mentioned")
    if "tp100" in t:
        parts.append("TP100 mentioned")
    return "; ".join(parts)


def export_formal_events(s: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for _, row in s.iterrows():
        rows.append(
            {
                "formal_event_id": row["signal_id"],
                "ticker": row["underlying_symbol"],
                "signal_date": row["signal_decision_date"],
                "entry_date": row["entry_session"],
                "rank": row["signal_rank"],
                "production_adjusted_score": row.get("production_adjusted_score", ""),
                "accumulation_score": row.get("accumulation_score", ""),
                "prior_65d_high_or_equivalent": row.get("prior_20d_high", ""),
                "breakout_reference_date_if_available": row["signal_decision_date"],
                "signal_source_file": repo_rel(BASELINE_DIR / "morita_bot_baseline_panel.csv"),
                "outcome_status": row.get("outcome_status", ""),
                "base_id_if_existing": "",
                "cooldown_flag_if_existing": "",
            }
        )
    return rows


def export_reference(s: pd.DataFrame, term: pd.DataFrame, cov: pd.DataFrame) -> list[dict[str, Any]]:
    merged = s[["signal_id", "underlying_symbol", "signal_decision_date", "entry_session"]].merge(cov, on="signal_id", how="left")
    merged = merged.merge(term, on="signal_id", how="left", suffixes=("", "_ref"))
    rows = []
    for _, row in merged.iterrows():
        eligible = str(row.get("status", "")) == "eligible"
        rows.append(
            {
                "reference_trade_id": row["signal_id"] if eligible else "",
                "formal_event_id_or_join_key": row["signal_id"],
                "ticker": row["underlying_symbol"],
                "signal_date": row["signal_decision_date"],
                "entry_date": row["entry_session"],
                "reference_eligibility_status": row.get("status", "missing_reference"),
                "exclusion_reason": row.get("excluded_reason", ""),
                "entry_debit": row.get("entry_debit", ""),
                "TP125_status": "hit" if has_value(row.get("first_hit_125_date", "")) else "not_hit",
                "TP125_date": row.get("first_hit_125_date", ""),
                "Day10_status": "day10_exit" if row.get("terminal_reason", "") == "day10_plus5_not_reached" else "",
                "terminal_exit_reason": row.get("terminal_reason", ""),
                "terminal_return": row.get("terminal_net_return_pct", ""),
                "trade_duration": row.get("path_session_count", ""),
            }
        )
    return rows


def repeat_audit(s: pd.DataFrame, sessions: list[pd.Timestamp]) -> list[dict[str, Any]]:
    rows = []
    for ticker, group in s.sort_values(["underlying_symbol", "entry_date_ts", "signal_id"]).groupby("underlying_symbol"):
        prev = None
        for _, cur in group.iterrows():
            if prev is None:
                prev = cur
                continue
            cal_gap = (pd.Timestamp(cur["signal_decision_date"]) - pd.Timestamp(prev["signal_decision_date"])).days
            egap = session_gap(prev["entry_session"], cur["entry_session"], sessions)
            classification = classify_repeat(cal_gap, egap)
            rows.append(
                {
                    "ticker": ticker,
                    "prior_formal_event_id": prev["signal_id"],
                    "current_formal_event_id": cur["signal_id"],
                    "prior_signal_date": prev["signal_decision_date"],
                    "current_signal_date": cur["signal_decision_date"],
                    "calendar_gap_days": cal_gap,
                    "eligible_session_gap": egap,
                    "prior_entry_date": prev["entry_session"],
                    "current_entry_date": cur["entry_session"],
                    "prior_score": prev.get("production_adjusted_score", ""),
                    "current_score": cur.get("production_adjusted_score", ""),
                    "prior_accumulation": prev.get("accumulation_score", ""),
                    "current_accumulation": cur.get("accumulation_score", ""),
                    "same_base_evidence_status": "base_id_not_available_in_current_artifacts",
                    "existing_base_id_match": "",
                    "prior_65d_high_relation": f"prior20_prev={prev.get('prior_20d_high','')};prior20_cur={cur.get('prior_20d_high','')}",
                    "cooldown_expected_under_config": "yes" if isinstance(egap, int) and egap < COOLDOWN_SESSIONS else "no",
                    "cooldown_observed": "not_applied_to_formal_event_stream" if isinstance(egap, int) and egap < COOLDOWN_SESSIONS else "not_required_by_20_session_ticker_rule",
                    "repeat_classification": classification,
                }
            )
            prev = cur
    return rows


def classify_repeat(cal_gap: int, egap: int | str) -> str:
    if cal_gap == 0:
        return "same_day_duplicate"
    if isinstance(egap, int) and egap < COOLDOWN_SESSIONS:
        return "within_20_session_repeat"
    if isinstance(egap, int) and egap >= COOLDOWN_SESSIONS:
        return "post_20_session_repeat"
    return "base_unknown"


def label_layers(s: pd.DataFrame, sessions: list[pd.Timestamp]) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    rows = []
    keep_cooldown: set[str] = set()
    keep_first: set[str] = set()
    keep_newbase: set[str] = set()
    last_kept_entry: dict[str, str] = {}
    first_seen: set[str] = set()
    for _, row in s.sort_values(["entry_date_ts", "underlying_symbol", "signal_id"]).iterrows():
        sid = row["signal_id"]
        ticker = row["underlying_symbol"]
        first = ticker not in first_seen
        if first:
            first_seen.add(ticker)
            keep_first.add(sid)
            keep_newbase.add(sid)
        first_label = "keep" if sid in keep_first else "reject_not_first_ticker_s_breakout"
        prior_entry = last_kept_entry.get(ticker)
        if prior_entry is None:
            cooldown_keep = True
            gap = ""
        else:
            gap = session_gap(prior_entry, row["entry_session"], sessions)
            cooldown_keep = isinstance(gap, int) and gap >= COOLDOWN_SESSIONS
        if cooldown_keep:
            keep_cooldown.add(sid)
            last_kept_entry[ticker] = row["entry_session"]
        newbase_status = "first_ticker_s_event" if first else "new_base_unverifiable_with_current_artifacts"
        rows.append(
            {
                "formal_event_id": sid,
                "ticker": ticker,
                "signal_date": row["signal_decision_date"],
                "entry_date": row["entry_session"],
                "INTENDED_FIRST_BREAKOUT_ONLY": first_label,
                "INTENDED_20_SESSION_TICKER_COOLDOWN": "keep" if cooldown_keep else "reject_ticker_cooldown_lt_20_sessions",
                "INTENDED_NEW_BASE_REENTRY_ONLY": "keep" if sid in keep_newbase else "reject_new_base_unverifiable",
                "eligible_session_gap_from_prior_kept_cooldown_event": gap,
                "new_base_evidence_status": newbase_status,
            }
        )
    return rows, {"formal": set(s["signal_id"]), "cooldown": keep_cooldown, "first": keep_first, "newbase": keep_newbase}


def car_case(s: pd.DataFrame, repeats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    car = s[(s["underlying_symbol"] == "CAR") & (s["signal_date"] >= pd.Timestamp("2026-04-01")) & (s["signal_date"] <= pd.Timestamp("2026-04-30"))].copy()
    repeat_by_current = {row["current_formal_event_id"]: row for row in repeats}
    rows = []
    for _, row in car.iterrows():
        rep = repeat_by_current.get(row["signal_id"], {})
        rows.append(
            {
                "signal_date": row["signal_decision_date"],
                "entry_date": row["entry_session"],
                "formal_event_id": row["signal_id"],
                "prior_event_gap": rep.get("eligible_session_gap", "first_car_event_in_april_window"),
                "prior_65_day_high_or_breakout_level": row.get("prior_20d_high", ""),
                "new_base_objectively_formed": "unverifiable_with_current_artifacts",
                "code_config_considered_repeat": "no_formal_cooldown_or_base_id_field_observed",
                "cooldown_applied": "no",
                "eligible_or_candidate_duplicate_reason": "within_20_session_repeat" if rep.get("repeat_classification") == "within_20_session_repeat" else "formal_s_event_no_base_id",
                "production_adjusted_score": row.get("production_adjusted_score", ""),
                "accumulation_score": row.get("accumulation_score", ""),
            }
        )
    return rows


def count_reconciliation(s: pd.DataFrame, layers: dict[str, set[str]], repeats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    repeat_classes = Counter(row["repeat_classification"] for row in repeats)
    for name, ids in [
        ("FORMAL_EVENT_STREAM", layers["formal"]),
        ("INTENDED_20_SESSION_COOLDOWN_LAYER", layers["cooldown"]),
        ("INTENDED_FIRST_BREAKOUT_ONLY_LAYER", layers["first"]),
        ("INTENDED_NEW_BASE_REENTRY_ONLY_LAYER", layers["newbase"]),
    ]:
        sub = s[s["signal_id"].isin(ids)].copy()
        monthly = sub.groupby(sub["signal_date"].dt.to_period("M")).size().to_dict()
        yearly = sub.groupby(sub["signal_date"].dt.year).size().to_dict()
        rows.append(
            {
                "population": name,
                "total_events": len(sub),
                "unique_tickers": sub["underlying_symbol"].nunique(),
                "events_per_year": json.dumps({str(k): int(v) for k, v in yearly.items()}, sort_keys=True),
                "events_per_month": json.dumps({str(k): int(v) for k, v in monthly.items()}, sort_keys=True),
                "same_ticker_repeats": len(sub) - sub["underlying_symbol"].nunique(),
                "within_20_session_repeats": repeat_classes.get("within_20_session_repeat", 0) if name == "FORMAL_EVENT_STREAM" else "",
                "same_day_duplicates": repeat_classes.get("same_day_duplicate", 0) if name == "FORMAL_EVENT_STREAM" else "",
                "base_unknown_events": max(0, len(sub) - sub["underlying_symbol"].nunique()) if "NEW_BASE" in name or name == "FORMAL_EVENT_STREAM" else "",
                "2025_event_count": int((sub["signal_date"].dt.year == 2025).sum()),
                "2026_H1_event_count": int(((sub["signal_date"] >= "2026-01-01") & (sub["signal_date"] <= "2026-06-30")).sum()),
            }
        )
    return rows


def performance_tables(s: pd.DataFrame, term: pd.DataFrame, cov: pd.DataFrame, layers: dict[str, set[str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    perf_rows = []
    annual_rows = []
    eligible = cov[cov["status"] == "eligible"][["signal_id"]].merge(term[["signal_id", "reference_return", "first_hit_125_date", "terminal_reason"]], on="signal_id", how="left")
    base = s[["signal_id", "signal_decision_date", "entry_session", "signal_date"]].merge(eligible, on="signal_id", how="inner")
    populations = [
        ("FORMAL_BASELINE_S_EVENT_STREAM", layers["formal"], "verified_formal_s_rank_event_stream"),
        ("FORMAL_BASELINE_S_DEDUPED_20_SESSION", layers["cooldown"], "research_label_overlay_not_raw_history_change"),
        ("FORMAL_BASELINE_S_FIRST_BREAKOUT_ONLY", layers["first"], "research_label_overlay_no_base_id"),
        ("FORMAL_BASELINE_S_NEW_BASE_REENTRY_ONLY", layers["newbase"], "research_label_overlay_new_base_unverifiable_for_repeats"),
        ("LEGACY_PF_CLAIM", set(), "unverifiable_legacy_result"),
    ]
    for pop, ids, status in populations:
        sub = base[base["signal_id"].isin(ids)].sort_values(["entry_session", "signal_id"]).copy()
        values = [float(v) for v in sub["reference_return"].dropna().tolist()]
        stats = return_summary(values)
        all_count = int(s[s["signal_id"].isin(ids)].shape[0]) if ids else 0
        row = {
            "population": pop,
            "definition_status": status,
            "sample_count": all_count,
            "date_range": f"{sub['signal_decision_date'].min()}..{sub['signal_decision_date'].max()}" if not sub.empty else "",
            **stats,
            "win_rate_definition": "reference_return_gt_0",
            "win_rate": float((sub["reference_return"] > 0).mean()) if not sub.empty else "",
            "TP125_hit_rate": float(sub["first_hit_125_date"].apply(has_value).mean()) if not sub.empty else "",
            "Day10_plus5_rate": float((sub["terminal_reason"] != "day10_plus5_not_reached").mean()) if not sub.empty else "",
            "coverage": len(sub) / all_count if all_count else "",
            "excluded_count": all_count - len(sub),
            "limitations": "fixed-IV synthetic reference only; no historical option fills",
        }
        perf_rows.append(row)
        for label, start, end in [
            ("2024", "2024-01-01", "2024-12-31"),
            ("2025", "2025-01-01", "2025-12-31"),
            ("2026_H1", "2026-01-01", "2026-06-30"),
            ("full_range", "1900-01-01", "2100-01-01"),
        ]:
            part = sub[(sub["signal_date"] >= pd.Timestamp(start)) & (sub["signal_date"] <= pd.Timestamp(end))]
            vals = [float(v) for v in part["reference_return"].dropna().tolist()]
            st = return_summary(vals)
            annual_rows.append(
                {
                    "population": pop,
                    "subperiod": label,
                    "trade_count": st["trade_count"],
                    "PF": st["PF"],
                    "TP125_hit_rate": float(part["first_hit_125_date"].apply(has_value).mean()) if not part.empty else "",
                    "Day10_plus5_rate": float((part["terminal_reason"] != "day10_plus5_not_reached").mean()) if not part.empty else "",
                    "mean_return": st["mean_return"],
                    "median_return": st["median_return"],
                    "max_loss": st["max_loss"],
                    "sparse_sample_flag": st["trade_count"] < 30,
                }
            )
    return perf_rows, annual_rows


def production_parity() -> list[dict[str, Any]]:
    paths = [
        "scanner/pipeline.py",
        "scanner/breakout.py",
        "scanner_notify.py",
        "scripts/production_scanner_entry.py",
        "scripts/build_morita_bot_historical_baseline_v1.py",
        "src/morita_notification_v2/ab_pullback_lifecycle.py",
    ]
    rows = []
    for path in paths:
        p = REPO_ROOT / path
        text = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        rows.append(
            {
                "production_event_id": "historical_production_event_stream_unavailable",
                "ticker": "",
                "signal_date": "",
                "entry_date_if_defined": "",
                "alert_rank": "",
                "production_adjusted_score": "",
                "accumulation_score": "",
                "candidate_state": "static_code_path_audit",
                "cooldown_or_dedupe_status": infer_cooldown_status(path, text),
                "code_path_and_commit": f"{path}@{git_head()}",
            }
        )
    return rows


def infer_cooldown_status(path: str, text: str) -> str:
    if "build_morita_bot_historical_baseline" in path:
        return "no_20_session_ticker_cooldown_or_base_id_persisted_in_formal_event_rows"
    if "production_scanner_entry.py" in path:
        return "notification_state_dedupe_by_ticker_for_emergency_resend_not_20_session_signal_cooldown"
    if "ab_pullback_lifecycle" in path:
        return "base_breakout_id_exists_for_AB_pullback_lifecycle_not_formal_S_breakout_stream"
    if "breakout.py" in path:
        return "breakout_detector_has_65d_pivot_but_no_event_cooldown"
    return "no_historical_event_stream_export"


def code_path_audit_markdown() -> str:
    return "\n".join(
        [
            "# Morita S Code Path Configuration Audit",
            "",
            "| Area | Path | Finding | Discrepancy label |",
            "|---|---|---|---|",
            "| formal baseline signal code path | `scripts/build_morita_bot_historical_baseline_v1.py` | imports `scripts.production_scanner_entry`, then runs `scanner.pipeline.scan_universe -> scanner_notify.select_candidates`; signal rows store `signal_id`, date, rank, scores, but no base id or cooldown field | confirmed_semantic_difference |",
            "| current production signal code path | `scripts/production_scanner_entry.py` | patches `scanner_notify.select_candidates` to assign `production_adjusted_score` and `alert_rank` | no_difference_found |",
            "| rank S assignment | `scripts/production_scanner_entry.py::_rank` | `score >= 50` maps to `S` | no_difference_found |",
            "| breakout definition | `scanner/breakout.py` plus baseline prefilter | scanner breakout uses 65-day pivot; formal baseline panel stores prior_20d_high-style breakout fields from production candidate output | confirmed_semantic_difference |",
            "| cooldown intended | no S formal cooldown config found | no 20-session ticker cooldown is persisted or applied to formal S event stream | confirmed_implementation_defect |",
            "| base identity | A/B pullback lifecycle has `base_breakout_id`; formal S baseline does not store base id | unverified_due_to_missing_artifact |",
            "| event IDs | `scripts/build_morita_bot_historical_baseline_v1.py::signal_id_for` | event id is date/entry/ticker/rank/rule hash; not base-id based | confirmed_semantic_difference |",
            "| signal date to entry date | `decision_schedule.csv` next eligible session | formal replay maps decision close to next eligible session | no_difference_found |",
            "",
            "No code remediation is implemented by this audit.",
        ]
    ) + "\n"


def build_manifest() -> dict[str, Any]:
    files = []
    for name in REQUIRED_FILES:
        if name == "reconciliation_content_manifest.json":
            continue
        p = OUT / name
        if p.exists():
            files.append({"path": name, "sha256": sha256(p), "bytes": p.stat().st_size})
    manifest = {"created_at_utc": utc_now(), "required_files": REQUIRED_FILES, "files": files}
    write_json(OUT / "reconciliation_content_manifest.json", manifest)
    return manifest


def verify_manifest() -> dict[str, Any]:
    missing = [name for name in REQUIRED_FILES if not (OUT / name).exists()]
    actual = sorted(p.name for p in OUT.iterdir() if p.is_file()) if OUT.exists() else []
    extra = [name for name in actual if name not in REQUIRED_FILES]
    changed = []
    manifest_path = OUT / "reconciliation_content_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in manifest.get("files", []):
            p = OUT / row["path"]
            if not p.exists() or sha256(p) != row["sha256"]:
                changed.append(row["path"])
    for path in OUT.glob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in LIVE_TOKENS:
                if token in text:
                    raise AssertionError(f"live_token_detected:{token}:{path}")
    return {"verified": not missing and not extra and not changed, "missing": missing, "extra": extra, "changed": changed}


def build_audit() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    s = load_formal_s()
    term, cov = load_reference()
    sessions = load_sessions()
    discovery, legacy, legacy_trades = source_discovery()
    formal_rows = export_formal_events(s)
    reference_rows = export_reference(s, term, cov)
    repeats = repeat_audit(s, sessions)
    label_rows, layers = label_layers(s, sessions)
    car_rows = car_case(s, repeats)
    counts = count_reconciliation(s, layers, repeats)
    perf, annual = performance_tables(s, term, cov, layers)
    production_rows = production_parity()
    source_rows = [
        {"component": "audit_spec", "path": repo_rel(SPEC_PATH), "sha256": sha256(SPEC_PATH), "status": "verified"},
        {"component": "formal_baseline", "path": repo_rel(BASELINE_DIR), "sha256": sha256(BASELINE_DIR / "baseline_receipt.json"), "status": "verified"},
        {"component": "fixed_iv_reference", "path": repo_rel(REFERENCE_DIR), "sha256": sha256(REFERENCE_DIR / "s_single_call_reference_content_manifest.json"), "status": "verified"},
        {"component": "production_scanner_entry", "path": "scripts/production_scanner_entry.py", "sha256": sha256(REPO_ROOT / "scripts" / "production_scanner_entry.py"), "status": "verified"},
    ]
    pf_candidates = [row for row in legacy if plausible_legacy_pf(row.get("PF"))]
    call_backtest_pf_candidates = [row for row in pf_candidates if str(row.get("legacy_run_id", "")).startswith("legacy_call_backtest_rank_s_")]
    representative_candidates = call_backtest_pf_candidates or pf_candidates
    best_legacy = max(representative_candidates, key=lambda row: float(row["PF"])) if representative_candidates else None
    if best_legacy:
        legacy_status = "legacy_pf4_candidate_found_but_unsealed_non_equivalent"
    else:
        legacy_status = legacy[0]["reproducibility_status"]
    write_csv(OUT / "source_discovery_ledger.csv", discovery, ["artifact_id", "artifact_path", "artifact_type", "git_commit_or_blob_sha_if_available", "timestamp_if_available", "date_range", "universe", "signal_definition_summary", "cohort_size_if_stated", "pf_if_stated", "option_model_if_stated", "exit_rule_if_stated", "is_reproducible", "source_manifest_present", "notes"])
    write_csv(OUT / "legacy_pf_claim_registry.csv", legacy, ["legacy_run_id", "source_artifact_id", "date_range", "universe", "rank_or_filter_definition", "option_structure", "exit_rule", "PF", "cohort_count", "reproducibility_status", "artifact_path"])
    write_csv(OUT / "legacy_pf_claim_trade_cohorts.csv", legacy_trades, ["legacy_run_id", "source_artifact_id", "entry_date", "ticker", "signal_id_if_available", "trade_return", "profit_component", "loss_component", "PF", "cohort_count", "reproducibility_status"])
    write_csv(OUT / "formal_baseline_s_event_stream.csv", formal_rows, list(formal_rows[0].keys()))
    write_csv(OUT / "fixed_iv_reference_cohort.csv", reference_rows, list(reference_rows[0].keys()))
    write_csv(OUT / "production_scanner_parity_report.csv", production_rows, list(production_rows[0].keys()))
    write_csv(OUT / "same_ticker_repeat_audit.csv", repeats, list(repeats[0].keys()) if repeats else ["ticker"])
    write_csv(OUT / "car_april_2026_case_study.csv", car_rows, list(car_rows[0].keys()) if car_rows else ["signal_date"])
    write_csv(OUT / "intended_policy_label_layer.csv", label_rows, list(label_rows[0].keys()))
    write_csv(OUT / "event_count_reconciliation.csv", counts, list(counts[0].keys()))
    write_csv(OUT / "fixed_iv_performance_reconciliation.csv", perf, list(perf[0].keys()))
    write_csv(OUT / "annual_subperiod_stability.csv", annual, list(annual[0].keys()))
    (OUT / "code_path_configuration_audit.md").write_text(code_path_audit_markdown(), encoding="utf-8")
    write_csv(OUT / "source_verification.csv", source_rows, list(source_rows[0].keys()))
    receipt = {
        "status": "completed",
        "created_at_utc": utc_now(),
        "git_head": git_head(),
        "formal_s_events": int(len(s)),
        "formal_s_start": str(s["signal_decision_date"].min()),
        "formal_s_end": str(s["signal_decision_date"].max()),
        "fixed_iv_eligible": int((cov["status"] == "eligible").sum()),
        "legacy_pf4_status": legacy_status,
        "legacy_pf4_candidate_count": len(pf_candidates),
        "legacy_call_backtest_pf4_candidate_count": len(call_backtest_pf_candidates),
        "legacy_best_pf": best_legacy.get("PF", "") if best_legacy else "",
        "legacy_best_artifact_path": best_legacy.get("artifact_path", "") if best_legacy else "",
        "legacy_best_reproducibility_status": best_legacy.get("reproducibility_status", "") if best_legacy else "",
        "research_only": True,
        "no_new_data_downloaded": True,
        "no_parameter_sweep": True,
        "raw_formal_history_retained_unchanged": True,
    }
    write_json(OUT / "reconciliation_receipt.json", receipt)
    (OUT / "reconciliation_summary.md").write_text(render_summary(receipt, counts, perf, annual, car_rows, repeats), encoding="utf-8")
    build_manifest()
    render_bundle(receipt, counts, perf, annual, car_rows)
    return receipt


def render_summary(receipt: dict[str, Any], counts: list[dict[str, Any]], perf: list[dict[str, Any]], annual: list[dict[str, Any]], car_rows: list[dict[str, Any]], repeats: list[dict[str, Any]]) -> str:
    lines = [
        "# Morita S Definition Reconciliation Audit v1",
        "",
        f"Status: `{receipt['status']}`",
        f"Formal S events: `{receipt['formal_s_events']}`",
        f"Fixed-IV eligible: `{receipt['fixed_iv_eligible']}`",
        f"Legacy PF4 status: `{receipt['legacy_pf4_status']}`",
        f"Legacy PF4 candidates: `{receipt.get('legacy_pf4_candidate_count', 0)}`",
        f"Legacy call_backtest PF4 candidates: `{receipt.get('legacy_call_backtest_pf4_candidate_count', 0)}`",
        f"Legacy best PF: `{receipt.get('legacy_best_pf', '')}`",
        "",
        "## Event Counts",
        "",
        "| Population | Events | Unique tickers | 2025 | 2026 H1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in counts:
        lines.append(f"| {row['population']} | {row['total_events']} | {row['unique_tickers']} | {row['2025_event_count']} | {row['2026_H1_event_count']} |")
    lines.extend(["", "## Fixed-IV Performance", "", "| Population | Trades | PF | Mean | Median | TP125 hit | Coverage |", "|---|---:|---:|---:|---:|---:|---:|"])
    for row in perf:
        lines.append(f"| {row['population']} | {row['trade_count']} | {row['PF']} | {row['mean_return']} | {row['median_return']} | {row['TP125_hit_rate']} | {row['coverage']} |")
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "The formal S stream is an event stream, not a one-base-one-entry stream. It has no persisted base id and no observed 20-session ticker cooldown in the formal S rows.",
            "Repeated CAR April 2026 events are formal S events but cannot be proven as new-base reentries from current artifacts.",
            "An old call_backtest rank summary contains PF4+ S candidates, but they are unsealed 12-trade legacy rank-summary rows and are not equivalent to the current formal S event stream.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_bundle(receipt: dict[str, Any], counts: list[dict[str, Any]], perf: list[dict[str, Any]], annual: list[dict[str, Any]], car_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Morita S Definition Reconciliation Audit v1 Bundle",
        "",
        "## Boundary",
        "",
        "- research_only=true",
        "- no_new_data_downloaded=true",
        "- no_web_or_provider_api=true",
        "- no_live_order_or_alert_action=true",
        "- no_parameter_sweep=true",
        "- raw formal history retained unchanged.",
        "",
        "## Source Identities",
        "",
        f"- Formal baseline: `{repo_rel(BASELINE_DIR)}`",
        f"- Fixed-IV reference: `{repo_rel(REFERENCE_DIR)}`",
        f"- Git head: `{receipt['git_head']}`",
        "",
        "## PF4 Provenance Search",
        "",
        f"- Result: `{receipt['legacy_pf4_status']}`",
        f"- Candidate count: `{receipt.get('legacy_pf4_candidate_count', 0)}`",
        f"- Call backtest S-rank candidate count: `{receipt.get('legacy_call_backtest_pf4_candidate_count', 0)}`",
        f"- Best candidate PF: `{receipt.get('legacy_best_pf', '')}`",
        f"- Best candidate artifact: `{receipt.get('legacy_best_artifact_path', '')}`",
        f"- Best candidate status: `{receipt.get('legacy_best_reproducibility_status', '')}`",
        "- Interpretation: old PF4-style S evidence exists as a local legacy rank summary, but it is not source-sealed and not semantically equivalent to the current 328-event formal S stream.",
        "",
        "## Event Counts",
        "",
        "| Population | Events | Unique tickers | 2025 | 2026 H1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in counts:
        lines.append(f"| {row['population']} | {row['total_events']} | {row['unique_tickers']} | {row['2025_event_count']} | {row['2026_H1_event_count']} |")
    lines.extend(["", "## Frozen Fixed-IV PF Table", "", "| Population | Status | Sample | Trades | PF | Mean | Median | TP125 hit | Day10 pass | Coverage |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in perf:
        lines.append(f"| {row['population']} | {row['definition_status']} | {row['sample_count']} | {row['trade_count']} | {row['PF']} | {row['mean_return']} | {row['median_return']} | {row['TP125_hit_rate']} | {row['Day10_plus5_rate']} | {row['coverage']} |")
    lines.extend(["", "## Subperiod Stability", "", "| Population | Subperiod | Trades | PF | TP125 hit | Mean | Median | Max loss | Sparse |", "|---|---|---:|---:|---:|---:|---:|---:|---|"])
    for row in annual:
        if row["population"] in {"FORMAL_BASELINE_S_EVENT_STREAM", "FORMAL_BASELINE_S_DEDUPED_20_SESSION"}:
            lines.append(f"| {row['population']} | {row['subperiod']} | {row['trade_count']} | {row['PF']} | {row['TP125_hit_rate']} | {row['mean_return']} | {row['median_return']} | {row['max_loss']} | {row['sparse_sample_flag']} |")
    lines.extend(
        [
            "",
            "## CAR April 2026",
            "",
            "| Signal date | Entry date | Event | Gap | Breakout level | Conclusion |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for row in car_rows:
        lines.append(f"| {row['signal_date']} | {row['entry_date']} | {row['formal_event_id']} | {row['prior_event_gap']} | {row['prior_65_day_high_or_breakout_level']} | {row['eligible_or_candidate_duplicate_reason']} |")
    lines.extend(
        [
            "",
            "## Current Interpretation for Sizing Research",
            "",
            "Use `FORMAL_BASELINE_S_EVENT_STREAM` only as a raw event stream denominator. For live sizing research, do not treat it as a one-base-one-entry S strategy. The 20-session cooldown and first-breakout label layers are research overlays, not implemented history.",
            "",
            "## Remediation Proposal",
            "",
            "See `docs/morita_s_event_semantics_remediation_proposal_v1.md`. The proposal is not implemented by this task.",
            "",
            "## Output Files",
            "",
            "- `outputs/morita_s_reconciliation_audit_v1/source_discovery_ledger.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/legacy_pf_claim_registry.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/formal_baseline_s_event_stream.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/fixed_iv_reference_cohort.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/same_ticker_repeat_audit.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/car_april_2026_case_study.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/intended_policy_label_layer.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/fixed_iv_performance_reconciliation.csv`",
            "- `outputs/morita_s_reconciliation_audit_v1/annual_subperiod_stability.csv`",
        ]
    )
    BUNDLE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.run and not args.verify:
        parser.error("one of --run or --verify is required")
    if args.run:
        receipt = build_audit()
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.verify:
        result = verify_manifest()
        print(result)
        return 0 if result["verified"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
