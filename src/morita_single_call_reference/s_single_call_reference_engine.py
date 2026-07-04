from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.morita_single_call_reference.black_scholes_reference import call_delta, call_price, solve_strike_for_call_delta


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_SPEC_PATH = REPO_ROOT / "config" / "morita_s_single_call_reference_v1" / "fixed_iv_reference_model_spec.json"
COMPARISON_SPEC_PATH = REPO_ROOT / "config" / "morita_s_single_call_reference_v1" / "tp100_tp125_staged_comparison_spec.json"
DEFAULT_BASELINE_DIR = (
    REPO_ROOT
    / "market_bomb_history"
    / "morita_bot_historical_baseline_v1"
    / "historical_runs"
    / "morita_baseline_20260703T123912Z_4994e3744ffa"
)
DEFAULT_REFERENCE_OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_s_single_call_reference_v1"
DEFAULT_COMPARISON_OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_s_tp_comparison_v2"
CHATGPT_BUNDLE_PATH = REPO_ROOT / "morita_s_single_call_reference_and_tp100_tp125_bundle.md"

REFERENCE_REQUIRED_FILES = [
    "model_source_verification.csv",
    "model_assumption_ledger.json",
    "eligible_trade_coverage.csv",
    "s_single_call_daily_path_summary.csv",
    "s_single_call_trade_terminal_summary.csv",
    "s_single_call_reference_receipt.json",
    "s_single_call_reference_content_manifest.json",
    "s_single_call_reference_summary.md",
]
COMPARISON_REQUIRED_FILES = [
    "s_tp_policy_trade_summary.csv",
    "s_tp_policy_drawdown_proxy_summary.csv",
    "s_tp100_to_tp125_path_classes.csv",
    "s_tp100_to_tp125_giveback_summary.csv",
    "s_tp100_to_tp125_chronological_summary.csv",
    "s_tp100_to_tp125_concentration_summary.csv",
    "s_tp100_to_tp125_representative_paths.csv",
    "s_tp_comparison_receipt.json",
    "s_tp_comparison_content_manifest.json",
    "s_tp_comparison_summary.md",
]
LIVE_ACTION_TOKENS = ["BUY_NOW", "SELL_NOW", "ORDER", "ALERT_CHANGE", "SIZE_UP", "SIZE_DOWN", "LIVE_TARGET_CHANGE", "WEBULL"]


@dataclass(frozen=True)
class ModelAssumptions:
    model_id: str = "morita_s_single_call_fixed_iv_reference_v1"
    option_side: str = "call"
    initial_calendar_dte: int = 60
    target_entry_delta: float = 0.60
    annualized_implied_volatility: float = 0.60
    risk_free_rate: float = 0.0
    continuous_dividend_yield: float = 0.0
    entry_markup: float = 0.05
    exit_haircut: float = 0.05
    progress_gate_horizon_sessions: int = 10
    progress_gate_underlying_return: float = 0.05
    max_holding_sessions: int = 30


ASSUMPTIONS = ModelAssumptions()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def build_manifest(output_dir: Path, manifest_name: str, required_files: list[str]) -> dict[str, Any]:
    files = []
    for name in required_files:
        if name == manifest_name:
            continue
        path = output_dir / name
        if path.exists():
            files.append({"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {
        "manifest_version": manifest_name.replace(".json", ""),
        "created_at_utc": utc_now(),
        "required_files": required_files,
        "files": files,
        "content_set_hash": text_hash(json.dumps(files, sort_keys=True)),
    }
    write_json(output_dir / manifest_name, manifest)
    return manifest


def verify_manifest(output_dir: Path, manifest_name: str, required_files: list[str]) -> dict[str, Any]:
    missing = [name for name in required_files if not (output_dir / name).exists()]
    actual = sorted(path.name for path in output_dir.iterdir() if path.is_file()) if output_dir.exists() else []
    extra = [name for name in actual if name not in required_files]
    changed = []
    manifest_path = output_dir / manifest_name
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        for row in manifest.get("files", []):
            path = output_dir / row["path"]
            if not path.exists() or sha256_file(path) != row["sha256"]:
                changed.append(row["path"])
    return {"verified": not missing and not extra and not changed, "missing": missing, "extra": extra, "changed": changed}


def assert_no_actionization(output_dir: Path) -> None:
    for path in output_dir.glob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in LIVE_ACTION_TOKENS:
                if token in text:
                    raise AssertionError(f"live_action_token_detected:{token}:{path}")


def baseline_input_root(baseline_dir: Path) -> Path:
    lineage_path = baseline_dir / "source_input_lineage.json"
    lineage = read_json(lineage_path)
    inputs = lineage.get("inputs", [])
    if len(inputs) != 1:
        raise ValueError("unexpected_baseline_input_lineage")
    rel = inputs[0].get("repository_relative_path_or_local_alias", "")
    root = REPO_ROOT / rel
    if not (root / "sources" / "daily_ohlcv_merged.csv").exists():
        raise ValueError("baseline_ohlcv_lineage_missing")
    return root


def load_formal_s_panel(baseline_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    receipt = read_json(baseline_dir / "baseline_receipt.json")
    panel = pd.read_csv(baseline_dir / "morita_bot_baseline_panel.csv", dtype={"signal_id": str, "underlying_symbol": str})
    s_panel = panel[(panel["signal_rank"].astype(str) == "S") & (panel["outcome_status"].astype(str) == "complete")].copy()
    return s_panel, receipt


def load_ohlcv_subset(input_root: Path, tickers: set[str]) -> dict[str, pd.DataFrame]:
    source = input_root / "sources" / "daily_ohlcv_merged.csv"
    usecols = ["date", "ticker", "open", "high", "low", "close", "volume"]
    chunks = []
    for chunk in pd.read_csv(source, usecols=usecols, chunksize=250_000):
        chunk = chunk[chunk["ticker"].astype(str).isin(tickers)].copy()
        if not chunk.empty:
            chunks.append(chunk)
    if not chunks:
        return {}
    raw = pd.concat(chunks, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["date"])
    histories: dict[str, pd.DataFrame] = {}
    for ticker, df in raw.groupby("ticker", sort=True):
        histories[str(ticker)] = df.sort_values("date").reset_index(drop=True)
    return histories


def option_value(spot: float, strike: float, valuation_date: pd.Timestamp, expiry_date: pd.Timestamp) -> float:
    years = max((expiry_date.date() - valuation_date.date()).days, 0) / 365.25
    return call_price(spot, strike, years, ASSUMPTIONS.annualized_implied_volatility, ASSUMPTIONS.risk_free_rate, ASSUMPTIONS.continuous_dividend_yield)


def model_trade(signal: dict[str, Any], history: pd.DataFrame) -> dict[str, Any]:
    entry_session = pd.Timestamp(signal["entry_session"])
    try:
        entry_price = float(signal["entry_price"])
    except (TypeError, ValueError):
        return {"status": "excluded", "excluded_reason": "missing_entry_price"}
    if not math.isfinite(entry_price) or entry_price <= 0:
        return {"status": "excluded", "excluded_reason": "missing_entry_price"}
    future = history[history["date"] >= entry_session].head(ASSUMPTIONS.max_holding_sessions).copy()
    if future.empty or pd.Timestamp(future.iloc[0]["date"]) != entry_session:
        return {"status": "excluded", "excluded_reason": "missing_entry_session_ohlcv"}
    expiry_date = entry_session + pd.Timedelta(days=ASSUMPTIONS.initial_calendar_dte)
    entry_years = ASSUMPTIONS.initial_calendar_dte / 365.25
    strike, solved_delta = solve_strike_for_call_delta(
        entry_price,
        entry_years,
        ASSUMPTIONS.annualized_implied_volatility,
        ASSUMPTIONS.target_entry_delta,
        ASSUMPTIONS.risk_free_rate,
        ASSUMPTIONS.continuous_dividend_yield,
        tolerance=1e-10,
    )
    delta_error = abs(solved_delta - ASSUMPTIONS.target_entry_delta)
    if delta_error > 1e-6:
        return {"status": "excluded", "excluded_reason": "delta_solve_failed"}
    entry_value = call_price(entry_price, strike, entry_years, ASSUMPTIONS.annualized_implied_volatility, ASSUMPTIONS.risk_free_rate, ASSUMPTIONS.continuous_dividend_yield)
    entry_debit = entry_value * (1.0 + ASSUMPTIONS.entry_markup)
    path_rows = []
    for idx, row in enumerate(future.itertuples(index=False), start=1):
        date = pd.Timestamp(row.date)
        high_value = option_value(float(row.high), strike, date, expiry_date)
        close_value = option_value(float(row.close), strike, date, expiry_date)
        path_rows.append(
            {
                "session_index": idx,
                "date": date,
                "net_return_high_pct": (high_value * (1.0 - ASSUMPTIONS.exit_haircut) / entry_debit - 1.0) * 100.0,
                "net_return_close_pct": (close_value * (1.0 - ASSUMPTIONS.exit_haircut) / entry_debit - 1.0) * 100.0,
                "close": float(row.close),
                "high": float(row.high),
            }
        )
        if date >= expiry_date:
            break
    if len(path_rows) < min(ASSUMPTIONS.progress_gate_horizon_sessions, ASSUMPTIONS.max_holding_sessions):
        return {"status": "excluded", "excluded_reason": "unavailable_required_path_data"}
    reached_plus5 = str(signal.get("reached_plus_5pct_within_10_sessions", "")).lower() == "true"
    if not reached_plus5:
        terminal = path_rows[ASSUMPTIONS.progress_gate_horizon_sessions - 1]
        terminal_reason = "day10_plus5_not_reached"
    else:
        terminal = path_rows[-1]
        if terminal["date"] >= expiry_date:
            terminal_reason = "option_expiration"
        elif len(path_rows) >= ASSUMPTIONS.max_holding_sessions:
            terminal_reason = "max_holding_30_sessions"
        else:
            return {"status": "excluded", "excluded_reason": "unavailable_required_path_data"}
    terminal_idx = int(terminal["session_index"])
    terminal_path = path_rows[:terminal_idx]
    first_100 = next((row for row in terminal_path if row["net_return_high_pct"] >= 100.0), None)
    first_125 = next((row for row in terminal_path if row["net_return_high_pct"] >= 125.0), None)
    if first_100 is not None:
        post100 = [row for row in terminal_path if row["session_index"] >= first_100["session_index"]]
        post100_peak = max(row["net_return_high_pct"] for row in post100)
        post100_trough = min(row["net_return_close_pct"] for row in post100)
    else:
        post100_peak = ""
        post100_trough = ""
    return {
        "status": "eligible",
        "excluded_reason": "",
        "signal_id": signal["signal_id"],
        "ticker": signal["underlying_symbol"],
        "signal_decision_date": signal["signal_decision_date"],
        "entry_date": signal["entry_session"],
        "theme": signal.get("theme", ""),
        "entry_underlying_price": entry_price,
        "breakout_day_low": signal.get("breakout_day_low", ""),
        "strike": strike,
        "entry_delta": solved_delta,
        "delta_error": delta_error,
        "entry_theoretical_value": entry_value,
        "entry_debit": entry_debit,
        "expiry_date": expiry_date.strftime("%Y-%m-%d"),
        "path_session_count": len(terminal_path),
        "terminal_date": pd.Timestamp(terminal["date"]).strftime("%Y-%m-%d"),
        "terminal_reason": terminal_reason,
        "terminal_net_return_pct": terminal["net_return_close_pct"],
        "first_hit_100_date": pd.Timestamp(first_100["date"]).strftime("%Y-%m-%d") if first_100 else "",
        "first_hit_100_session": first_100["session_index"] if first_100 else "",
        "first_hit_125_date": pd.Timestamp(first_125["date"]).strftime("%Y-%m-%d") if first_125 else "",
        "first_hit_125_session": first_125["session_index"] if first_125 else "",
        "max_net_return_high_pct": max(row["net_return_high_pct"] for row in terminal_path),
        "min_net_return_close_pct": min(row["net_return_close_pct"] for row in terminal_path),
        "post_100_peak_net_return_pct": post100_peak,
        "post_100_trough_net_return_pct": post100_trough,
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
    }


def build_reference_outputs(baseline_run_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    s_panel, receipt = load_formal_s_panel(baseline_run_dir)
    input_root = baseline_input_root(baseline_run_dir)
    tickers = set(s_panel["underlying_symbol"].astype(str))
    histories = load_ohlcv_subset(input_root, tickers)
    terminal_rows = []
    coverage_rows = []
    for _, row in s_panel.iterrows():
        sig = row.to_dict()
        ticker = str(sig["underlying_symbol"])
        if ticker not in histories:
            result = {"status": "excluded", "excluded_reason": "missing_ticker_ohlcv"}
        else:
            result = model_trade(sig, histories[ticker])
        coverage_rows.append(
            {
                "signal_id": sig["signal_id"],
                "ticker": ticker,
                "entry_date": sig["entry_session"],
                "status": result["status"],
                "excluded_reason": result.get("excluded_reason", ""),
            }
        )
        if result["status"] == "eligible":
            terminal_rows.append(result)
    eligible_count = len(terminal_rows)
    formal_complete_s = len(s_panel)
    coverage_rate = eligible_count / formal_complete_s if formal_complete_s else 0.0
    verification_rows = [
        {
            "component": "formal_baseline",
            "path": repo_relative(baseline_run_dir),
            "status": "verified",
            "sha256": sha256_file(baseline_run_dir / "baseline_receipt.json"),
            "notes": "Formal S complete cohort source.",
        },
        {
            "component": "formal_ohlcv_lineage",
            "path": repo_relative(input_root / "sources" / "daily_ohlcv_merged.csv"),
            "status": "verified",
            "sha256": sha256_file(input_root / "source_manifest.json"),
            "notes": "Local OHLCV lineage referenced by source_input_lineage.json.",
        },
        {
            "component": "fixed_iv_reference_model_spec",
            "path": repo_relative(MODEL_SPEC_PATH),
            "status": "verified",
            "sha256": sha256_file(MODEL_SPEC_PATH),
            "notes": "Synthetic fixed-IV reference model, not historical option fill reconstruction.",
        },
    ]
    write_csv(output_dir / "model_source_verification.csv", verification_rows, ["component", "path", "status", "sha256", "notes"])
    write_json(
        output_dir / "model_assumption_ledger.json",
        {
            **ASSUMPTIONS.__dict__,
            "synthetic_fixed_iv_reference_model": True,
            "not_historical_option_fill_reconstruction": True,
            "not_live_execution_estimate": True,
            "strike_representation": "continuous_theoretical_delta_matched",
            "target_touch_underlying_price": "daily_high",
            "terminal_exit_underlying_price": "daily_close",
            "breakout_day_low": "diagnostic_only_no_hard_exit",
        },
    )
    write_csv(output_dir / "eligible_trade_coverage.csv", coverage_rows, ["signal_id", "ticker", "entry_date", "status", "excluded_reason"])
    write_csv(
        output_dir / "s_single_call_daily_path_summary.csv",
        terminal_rows,
        [
            "signal_id",
            "ticker",
            "entry_date",
            "path_session_count",
            "first_hit_100_date",
            "first_hit_100_session",
            "first_hit_125_date",
            "first_hit_125_session",
            "max_net_return_high_pct",
            "min_net_return_close_pct",
            "post_100_peak_net_return_pct",
            "post_100_trough_net_return_pct",
        ],
    )
    write_csv(
        output_dir / "s_single_call_trade_terminal_summary.csv",
        terminal_rows,
        [
            "signal_id",
            "ticker",
            "signal_decision_date",
            "entry_date",
            "theme",
            "entry_underlying_price",
            "breakout_day_low",
            "strike",
            "entry_delta",
            "delta_error",
            "entry_theoretical_value",
            "entry_debit",
            "expiry_date",
            "path_session_count",
            "terminal_date",
            "terminal_reason",
            "terminal_net_return_pct",
            "first_hit_100_date",
            "first_hit_100_session",
            "first_hit_125_date",
            "first_hit_125_session",
            "max_net_return_high_pct",
            "min_net_return_close_pct",
            "post_100_peak_net_return_pct",
            "post_100_trough_net_return_pct",
            "synthetic_fixed_iv_reference_model",
            "not_historical_option_fill_reconstruction",
            "not_live_execution_estimate",
        ],
    )
    excluded = Counter(row["excluded_reason"] for row in coverage_rows if row["status"] != "eligible")
    run_status = "completed" if coverage_rate >= 0.8 else "insufficient_formal_path_coverage"
    ref_receipt = {
        "status": run_status,
        "model_id": ASSUMPTIONS.model_id,
        "created_at_utc": utc_now(),
        "baseline_run_id": receipt.get("run_id", ""),
        "formal_s_signals": int(receipt.get("signal_count_by_rank", {}).get("S", 0)),
        "formal_complete_s_records": formal_complete_s,
        "eligible_trade_count": eligible_count,
        "excluded_trade_count": formal_complete_s - eligible_count,
        "path_coverage_rate": coverage_rate,
        "excluded_by_reason": dict(sorted(excluded.items())),
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
        "research_only": True,
        "actionization_allowed": False,
        "new_market_or_option_data_downloaded": False,
    }
    write_json(output_dir / "s_single_call_reference_receipt.json", ref_receipt)
    summary = render_reference_summary(ref_receipt)
    (output_dir / "s_single_call_reference_summary.md").write_text(summary, encoding="utf-8")
    build_manifest(output_dir, "s_single_call_reference_content_manifest.json", REFERENCE_REQUIRED_FILES)
    return ref_receipt


def render_reference_summary(receipt: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Morita S Single-Call Fixed-IV Reference v1",
            "",
            f"Status: `{receipt['status']}`",
            f"Model: `{receipt['model_id']}`",
            f"Baseline: `{receipt['baseline_run_id']}`",
            "",
            "This is a synthetic fixed-IV Black-Scholes daily-bar proxy. It is not historical option-fill reconstruction and not a live execution estimate.",
            "",
            f"- Formal S signals: `{receipt['formal_s_signals']}`",
            f"- Formal complete S records: `{receipt['formal_complete_s_records']}`",
            f"- Eligible reference trades: `{receipt['eligible_trade_count']}`",
            f"- Path coverage rate: `{receipt['path_coverage_rate']:.4f}`",
            f"- Excluded by reason: `{receipt['excluded_by_reason']}`",
            "",
            "No Bot rule, alert, stop, target, size, or trading behavior was changed.",
        ]
    ) + "\n"


def pct_or_blank(value: Any) -> float | str:
    if value == "" or pd.isna(value):
        return ""
    return float(value)


def has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    return str(value).strip() not in {"", "nan", "NaN", "None"}


def policy_returns(row: dict[str, Any]) -> dict[str, Any]:
    terminal = float(row["terminal_net_return_pct"])
    hit100 = has_value(row.get("first_hit_100_date", ""))
    hit125 = has_value(row.get("first_hit_125_date", ""))
    tp100 = 100.0 if hit100 else terminal
    tp125 = 125.0 if hit125 else terminal
    staged = 0.5 * 100.0 + 0.5 * (125.0 if hit125 else terminal) if hit100 else terminal
    return {"TP100": tp100, "TP125": tp125, "STAGED": staged}


def classify_100_to_125(row: dict[str, Any]) -> str:
    if not has_value(row.get("first_hit_100_date", "")):
        return "NO_100_HIT"
    terminal = float(row["terminal_net_return_pct"])
    hit125 = has_value(row.get("first_hit_125_date", ""))
    trough = float(row["post_100_trough_net_return_pct"])
    if hit125 and trough < 100.0:
        return "DIP_THEN_125"
    if hit125:
        return "DIRECT_100_TO_125"
    if terminal < 100.0:
        return "100_ONLY_TERMINAL_BELOW_100"
    return "100_ONLY_TERMINAL_AT_OR_ABOVE_100"


def profit_factor(values: list[float]) -> float | str:
    gross_profit = sum(v for v in values if v > 0)
    gross_loss = -sum(v for v in values if v < 0)
    if gross_loss == 0:
        return "not_estimable_zero_gross_loss"
    return gross_profit / gross_loss


def return_summary(values: list[float]) -> dict[str, Any]:
    series = pd.Series(values, dtype="float64")
    gross_profit = float(series[series > 0].sum())
    gross_loss = float(-series[series < 0].sum())
    return {
        "eligible_trade_count": len(values),
        "mean_net_return_pct": float(series.mean()) if len(series) else "",
        "median_net_return_pct": float(series.median()) if len(series) else "",
        "p10_net_return_pct": float(series.quantile(0.10)) if len(series) else "",
        "p25_net_return_pct": float(series.quantile(0.25)) if len(series) else "",
        "p75_net_return_pct": float(series.quantile(0.75)) if len(series) else "",
        "p90_net_return_pct": float(series.quantile(0.90)) if len(series) else "",
        "win_rate": float((series > 0).mean()) if len(series) else "",
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor(values),
        "max_single_trade_gain": float(series.max()) if len(series) else "",
        "max_single_trade_loss": float(series.min()) if len(series) else "",
        "maximum_consecutive_losses": max_consecutive_losses(values),
    }


def max_consecutive_losses(values: list[float]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def drawdown_proxy(rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row["entry_date"], row["ticker"], row["signal_id"]))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    values = []
    for row in ordered:
        ret = float(row[f"{policy}_return_pct"])
        equity += ret
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        values.append(ret)
    worst_10 = min((sum(values[i : i + 10]) for i in range(max(1, len(values) - 9))), default=0.0)
    return {"policy": policy, "max_drawdown_proxy": max_dd, "worst_10_trade_sum_proxy": worst_10}


def gross_profit_concentration(rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    profits: dict[str, float] = {}
    for row in rows:
        value = float(row[f"{policy}_return_pct"])
        if value > 0:
            profits[row["ticker"]] = profits.get(row["ticker"], 0.0) + value
    total = sum(profits.values())
    shares = sorted((v / total for v in profits.values()), reverse=True) if total else []
    return {
        "unique_ticker_count": len({row["ticker"] for row in rows}),
        "largest_single_ticker_share_of_gross_profit": shares[0] if shares else "",
        "top_five_ticker_share_of_gross_profit": sum(shares[:5]) if shares else "",
        "concentration_flag": bool(shares and shares[0] > 0.30),
    }


def chronological_halves(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    dates = sorted({row["entry_date"] for row in rows})
    split = (len(dates) + 1) // 2
    early = set(dates[:split])
    return {"early_half": [row for row in rows if row["entry_date"] in early], "late_half": [row for row in rows if row["entry_date"] not in early]}


def choose_label(policy_rows: list[dict[str, Any]], dd_rows: list[dict[str, Any]], concentration_rows: list[dict[str, Any]], coverage_rate: float) -> str:
    if coverage_rate < 0.8:
        return "insufficient_formal_path_coverage"
    by_policy = {row["policy":] if False else row["policy"]: row for row in policy_rows}
    by_dd = {row["policy"]: row for row in dd_rows}
    conc = any(bool(row.get("concentration_flag")) for row in concentration_rows if row["scope"] in {"TP100", "TP125", "STAGED"})
    if conc:
        return "no_clear_preference_under_fixed_iv_reference_model"
    try:
        tp100_pf = float(by_policy["TP100"]["profit_factor"])
        tp125_pf = float(by_policy["TP125"]["profit_factor"])
        staged_pf = float(by_policy["STAGED"]["profit_factor"])
    except (ValueError, TypeError):
        return "no_clear_preference_under_fixed_iv_reference_model"
    tp100_dd = float(by_dd["TP100"]["max_drawdown_proxy"])
    tp125_dd = float(by_dd["TP125"]["max_drawdown_proxy"])
    staged_dd = float(by_dd["STAGED"]["max_drawdown_proxy"])
    if tp100_pf - tp125_pf >= 0.15 and tp100_dd >= tp125_dd - 5.0:
        return "tp100_preferred_under_fixed_iv_reference_model"
    if tp125_pf - tp100_pf >= 0.15 and tp125_dd >= tp100_dd - 5.0:
        return "tp125_preferred_under_fixed_iv_reference_model"
    if staged_pf >= max(tp100_pf, tp125_pf) - 0.10 and staged_dd > tp100_dd and staged_dd > tp125_dd:
        return "staged_preferred_under_fixed_iv_reference_model"
    return "no_clear_preference_under_fixed_iv_reference_model"


def build_comparison_outputs(reference_model_output_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ref_receipt = read_json(reference_model_output_dir / "s_single_call_reference_receipt.json")
    df = pd.read_csv(reference_model_output_dir / "s_single_call_trade_terminal_summary.csv")
    rows = df.to_dict("records")
    enriched = []
    for row in rows:
        out = dict(row)
        returns = policy_returns(row)
        for policy, value in returns.items():
            out[f"{policy}_return_pct"] = value
        out["path_class"] = classify_100_to_125(row)
        enriched.append(out)
    policy_rows = []
    for policy in ["TP100", "TP125", "STAGED"]:
        values = [float(row[f"{policy}_return_pct"]) for row in enriched]
        summary = return_summary(values)
        concentration = gross_profit_concentration(enriched, policy)
        policy_rows.append(
            {
                "policy": policy,
                **summary,
                **concentration,
                "synthetic_fixed_iv_reference_model": True,
                "not_historical_option_fill_reconstruction": True,
            }
        )
    dd_rows = [drawdown_proxy(enriched, policy) for policy in ["TP100", "TP125", "STAGED"]]
    class_counter = Counter(row["path_class"] for row in enriched if row["path_class"] != "NO_100_HIT")
    hit100_rows = [row for row in enriched if row["path_class"] != "NO_100_HIT"]
    hit100_n = len(hit100_rows)
    class_rows = []
    for cls in ["DIRECT_100_TO_125", "DIP_THEN_125", "100_ONLY_TERMINAL_BELOW_100", "100_ONLY_TERMINAL_AT_OR_ABOVE_100", "PATH_UNAVAILABLE"]:
        subset = [row for row in hit100_rows if row["path_class"] == cls]
        class_rows.append(
            {
                "path_class": cls,
                "count": len(subset),
                "rate_among_100_hit": len(subset) / hit100_n if hit100_n else "",
                "median_terminal_net_return_pct": median([float(row["terminal_net_return_pct"]) for row in subset]),
                "median_post_100_trough_net_return_pct": median([float(row["post_100_trough_net_return_pct"]) for row in subset if row["post_100_trough_net_return_pct"] != ""]),
                "median_post_100_peak_net_return_pct": median([float(row["post_100_peak_net_return_pct"]) for row in subset if row["post_100_peak_net_return_pct"] != ""]),
                "median_sessions_100_to_125": median([int(row["first_hit_125_session"]) - int(row["first_hit_100_session"]) for row in subset if has_value(row.get("first_hit_125_session")) and has_value(row.get("first_hit_100_session"))]),
            }
        )
    giveback = giveback_summary(hit100_rows, all_eligible_count=len(enriched))
    chronology_rows = chronology_summary(enriched)
    concentration_rows = concentration_by_scope(enriched)
    label = choose_label(policy_rows, dd_rows, concentration_rows, float(ref_receipt["path_coverage_rate"]))
    write_csv(output_dir / "s_tp_policy_trade_summary.csv", policy_rows, list(policy_rows[0].keys()) if policy_rows else [])
    write_csv(output_dir / "s_tp_policy_drawdown_proxy_summary.csv", dd_rows, ["policy", "max_drawdown_proxy", "worst_10_trade_sum_proxy"])
    write_csv(output_dir / "s_tp100_to_tp125_path_classes.csv", class_rows, ["path_class", "count", "rate_among_100_hit", "median_terminal_net_return_pct", "median_post_100_trough_net_return_pct", "median_post_100_peak_net_return_pct", "median_sessions_100_to_125"])
    write_csv(output_dir / "s_tp100_to_tp125_giveback_summary.csv", giveback, ["metric", "value", "denominator"])
    write_csv(output_dir / "s_tp100_to_tp125_chronological_summary.csv", chronology_rows, list(chronology_rows[0].keys()) if chronology_rows else [])
    write_csv(output_dir / "s_tp100_to_tp125_concentration_summary.csv", concentration_rows, ["scope", "unique_ticker_count", "largest_single_ticker_share", "top_five_ticker_share", "concentration_flag"])
    representatives = representative_paths(enriched)
    write_csv(
        output_dir / "s_tp100_to_tp125_representative_paths.csv",
        representatives,
        ["ticker", "signal_date", "entry_date", "first_plus_100_date", "first_plus_125_date", "independent_terminal_date", "independent_terminal_reason", "TP100_modeled_return", "TP125_modeled_return", "staged_modeled_return", "post_100_trough", "post_100_peak", "path_class"],
    )
    receipt = {
        "status": "completed" if label != "insufficient_formal_path_coverage" else label,
        "overall_label": label,
        "created_at_utc": utc_now(),
        "reference_model_status": ref_receipt["status"],
        "baseline_run_id": ref_receipt["baseline_run_id"],
        "eligible_trade_count": len(enriched),
        "path_coverage_rate": ref_receipt["path_coverage_rate"],
        "plus_100_hit_count": hit100_n,
        "plus_125_hit_count": sum(1 for row in enriched if has_value(row.get("first_hit_125_date", ""))),
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
        "research_only": True,
        "actionization_allowed": False,
        "new_market_or_option_data_downloaded": False,
        "no_optimization": True,
        "no_live_alert_or_trading_change": True,
    }
    write_json(output_dir / "s_tp_comparison_receipt.json", receipt)
    summary = render_comparison_summary(receipt, policy_rows, dd_rows, giveback, chronology_rows)
    (output_dir / "s_tp_comparison_summary.md").write_text(summary, encoding="utf-8")
    build_manifest(output_dir, "s_tp_comparison_content_manifest.json", COMPARISON_REQUIRED_FILES)
    write_bundle(reference_model_output_dir, output_dir, ref_receipt, receipt)
    return receipt


def median(values: list[float]) -> float | str:
    return float(pd.Series(values, dtype="float64").median()) if values else ""


def quantile(values: list[float], q: float) -> float | str:
    return float(pd.Series(values, dtype="float64").quantile(q)) if values else ""


def giveback_summary(hit100_rows: list[dict[str, Any]], all_eligible_count: int | None = None) -> list[dict[str, Any]]:
    denomin = len(hit100_rows)
    never125 = [row for row in hit100_rows if not has_value(row.get("first_hit_125_date", ""))]
    terminal_below100 = [row for row in never125 if float(row["terminal_net_return_pct"]) < 100.0]
    terminal_below0 = [row for row in never125 if float(row["terminal_net_return_pct"]) < 0.0]
    dip_then125 = [row for row in hit100_rows if row["path_class"] == "DIP_THEN_125"]
    drawdowns = [float(row["post_100_trough_net_return_pct"]) - 100.0 for row in hit100_rows if row["post_100_trough_net_return_pct"] != ""]
    time_to125 = [int(row["first_hit_125_session"]) - int(row["first_hit_100_session"]) for row in hit100_rows if has_value(row.get("first_hit_125_session")) and has_value(row.get("first_hit_100_session"))]
    metrics = {
        "all_eligible_trades": all_eligible_count if all_eligible_count is not None else "",
        "plus_100_hit_count": denomin,
        "never_reach_125_after_100_rate": len(never125) / denomin if denomin else "",
        "terminal_below_100_without_125_rate": len(terminal_below100) / denomin if denomin else "",
        "terminal_below_0_without_125_rate": len(terminal_below0) / denomin if denomin else "",
        "dip_then_125_rate": len(dip_then125) / denomin if denomin else "",
        "gave_back_25pp_or_more_rate": sum(dd <= -25 for dd in drawdowns) / denomin if denomin else "",
        "gave_back_50pp_or_more_rate": sum(dd <= -50 for dd in drawdowns) / denomin if denomin else "",
        "gave_back_100pp_or_more_rate": sum(dd <= -100 for dd in drawdowns) / denomin if denomin else "",
        "post_100_drawdown_median_pp": median(drawdowns),
        "post_100_drawdown_p10_pp": quantile(drawdowns, 0.10),
        "post_100_drawdown_p05_pp": quantile(drawdowns, 0.05),
        "post_100_drawdown_worst_pp": min(drawdowns) if drawdowns else "",
        "time_100_to_125_median_sessions": median(time_to125),
        "time_100_to_125_p90_sessions": quantile(time_to125, 0.90),
    }
    return [{"metric": key, "value": value, "denominator": denomin} for key, value in metrics.items()]


def chronology_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    halves = chronological_halves(rows)
    out = []
    for half, subset in halves.items():
        row: dict[str, Any] = {"half": half, "trade_count": len(subset)}
        for policy in ["TP100", "TP125", "STAGED"]:
            values = [float(item[f"{policy}_return_pct"]) for item in subset]
            row[f"{policy}_profit_factor"] = profit_factor(values)
            row[f"{policy}_mean_return_pct"] = float(pd.Series(values).mean()) if values else ""
        hit100 = [item for item in subset if item["path_class"] != "NO_100_HIT"]
        never125 = [item for item in hit100 if not has_value(item.get("first_hit_125_date", ""))]
        row["plus_100_hit_count"] = len(hit100)
        row["never_reach_125_after_100_rate"] = len(never125) / len(hit100) if hit100 else ""
        out.append(row)
    return out


def concentration_by_scope(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scopes: dict[str, list[dict[str, Any]]] = {policy: rows for policy in ["TP100", "TP125", "STAGED"]}
    for cls in ["DIRECT_100_TO_125", "DIP_THEN_125", "100_ONLY_TERMINAL_BELOW_100", "100_ONLY_TERMINAL_AT_OR_ABOVE_100"]:
        scopes[cls] = [row for row in rows if row["path_class"] == cls]
    out = []
    for scope, subset in scopes.items():
        counts = Counter(row["ticker"] for row in subset)
        total = sum(counts.values())
        shares = sorted((v / total for v in counts.values()), reverse=True) if total else []
        out.append(
            {
                "scope": scope,
                "unique_ticker_count": len(counts),
                "largest_single_ticker_share": shares[0] if shares else "",
                "top_five_ticker_share": sum(shares[:5]) if shares else "",
                "concentration_flag": bool(shares and shares[0] > 0.30),
            }
        )
    return out


def representative_paths(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    limits = {
        "DIRECT_100_TO_125": 3,
        "DIP_THEN_125": 3,
        "100_ONLY_TERMINAL_BELOW_100": 2,
        "100_ONLY_TERMINAL_AT_OR_ABOVE_100": 2,
    }
    for cls, limit in limits.items():
        for row in [r for r in rows if r["path_class"] == cls][:limit]:
            out.append(
                {
                    "ticker": row["ticker"],
                    "signal_date": row["signal_decision_date"],
                    "entry_date": row["entry_date"],
                    "first_plus_100_date": row["first_hit_100_date"],
                    "first_plus_125_date": row["first_hit_125_date"],
                    "independent_terminal_date": row["terminal_date"],
                    "independent_terminal_reason": row["terminal_reason"],
                    "TP100_modeled_return": row["TP100_return_pct"],
                    "TP125_modeled_return": row["TP125_return_pct"],
                    "staged_modeled_return": row["STAGED_return_pct"],
                    "post_100_trough": row["post_100_trough_net_return_pct"],
                    "post_100_peak": row["post_100_peak_net_return_pct"],
                    "path_class": cls,
                }
            )
    return out[:10]


def render_comparison_summary(receipt: dict[str, Any], policy_rows: list[dict[str, Any]], dd_rows: list[dict[str, Any]], giveback: list[dict[str, Any]], chronology: list[dict[str, Any]]) -> str:
    lines = [
        "# Morita S TP100 vs TP125 vs Staged Comparison v2",
        "",
        f"Status: `{receipt['status']}`",
        f"Overall label: `{receipt['overall_label']}`",
        "",
        "Synthetic fixed-IV reference model only. Not historical option-fill reconstruction and not a live execution estimate.",
        "",
        "## Policy Summary",
        "",
        "| Policy | PF | Mean | Median | Gross Profit | Gross Loss | Max Loss |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in policy_rows:
        lines.append(f"| {row['policy']} | {row['profit_factor']} | {row['mean_net_return_pct']} | {row['median_net_return_pct']} | {row['gross_profit']} | {row['gross_loss']} | {row['max_single_trade_loss']} |")
    lines.extend(["", "## Drawdown Proxy", "", "| Policy | Max DD proxy | Worst 10-trade sum |", "|---|---:|---:|"])
    for row in dd_rows:
        lines.append(f"| {row['policy']} | {row['max_drawdown_proxy']} | {row['worst_10_trade_sum_proxy']} |")
    lines.extend(["", "## Giveback", ""])
    for row in giveback:
        lines.append(f"- {row['metric']}: `{row['value']}`")
    lines.extend(["", "No Bot rule, alert, stop, target, size, or trading behavior was changed."])
    return "\n".join(lines) + "\n"


def write_bundle(reference_dir: Path, comparison_dir: Path, ref_receipt: dict[str, Any], comp_receipt: dict[str, Any]) -> None:
    comp_summary = (comparison_dir / "s_tp_comparison_summary.md").read_text(encoding="utf-8") if (comparison_dir / "s_tp_comparison_summary.md").exists() else ""
    text = "\n".join(
        [
            "# ChatGPT Handoff: Morita S Fixed-IV Reference Engine and TP Comparison",
            "",
            "## Status",
            "",
            f"- Reference status: `{ref_receipt['status']}`",
            f"- Comparison status: `{comp_receipt['status']}`",
            f"- Overall label: `{comp_receipt['overall_label']}`",
            f"- Baseline run: `{ref_receipt['baseline_run_id']}`",
            f"- Formal complete S records: `{ref_receipt['formal_complete_s_records']}`",
            f"- Eligible trades: `{ref_receipt['eligible_trade_count']}`",
            f"- Path coverage: `{ref_receipt['path_coverage_rate']}`",
            "",
            "## Model Warning",
            "",
            "This is a synthetic fixed-IV Black-Scholes daily-bar reference model. It is not historical option-fill reconstruction, not a live execution estimate, and not a recommendation to change live targets.",
            "",
            "## Output Roots",
            "",
            f"- `{repo_relative(reference_dir)}`",
            f"- `{repo_relative(comparison_dir)}`",
            "",
            "## Embedded Comparison Summary",
            "",
            comp_summary,
        ]
    )
    CHATGPT_BUNDLE_PATH.write_text(text, encoding="utf-8")


from collections import Counter
