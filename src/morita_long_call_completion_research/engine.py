from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.morita_single_call_reference import s_single_call_reference_engine as ref
from src.morita_single_call_reference.black_scholes_reference import call_price, solve_strike_for_call_delta


REPO_ROOT = Path(__file__).resolve().parents[2]

BEHAVIORAL_OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_s_behavioral_discipline_v1"
PAUSE_OUTPUT_DIR = REPO_ROOT / "outputs" / "morita_call_bot_pause_v1"

BEHAVIORAL_REQUIRED_FILES = [
    "source_verification.csv",
    "behavioral_policy_summary.csv",
    "paired_damage_vs_baseline.csv",
    "false_exit_regret_summary.csv",
    "post_125_hold_summary.csv",
    "pain_atlas_summary.csv",
    "concentration_summary.csv",
    "chronological_summary.csv",
    "representative_paths.csv",
    "behavioral_discipline_receipt.json",
    "behavioral_discipline_content_manifest.json",
    "behavioral_discipline_summary.md",
]

PAUSE_REQUIRED_FILES = [
    "input_source_verification.csv",
    "state_coverage_summary.csv",
    "s_pause_strategy_impact.csv",
    "s_pause_market_risk_diagnostic.csv",
    "s_pause_concentration_summary.csv",
    "s_pause_chronological_summary.csv",
    "s_pause_candidate_labels.csv",
    "call_bot_pause_receipt.json",
    "call_bot_pause_content_manifest.json",
    "call_bot_pause_summary.md",
]

BEHAVIORAL_POLICIES = [
    "BASELINE_TP125",
    "FEAR_TP100",
    "COMPROMISE_STAGED_100_125",
    "PANIC_OPTION_STOP_25_NEXT_OPEN",
    "PANIC_OPTION_STOP_50_NEXT_OPEN",
    "BREAKOUT_LOW_RISK_ALERT_TO_EXIT_NEXT_OPEN",
    "GREED_IGNORE_TP125_HOLD_TO_INDEPENDENT_TERMINAL",
]

PAUSE_STATES = [
    "STATE_0_BASELINE",
    "STATE_1_NARROW_LEADERSHIP_ONLY",
    "STATE_2_TREND_BREAK_ONLY",
    "STATE_3_CASCADE",
    "STATE_4_FULL_CASCADE",
]

LIVE_ACTION_TOKENS = ref.LIVE_ACTION_TOKENS + ["CALL_BOT_PAUSE_ON", "SHORT_NOW"]


def repo_relative(path: Path) -> str:
    return ref.repo_relative(path)


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def has_value(value: Any) -> bool:
    return ref.has_value(value)


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    if text in {"", "nan", "NaN", "None"}:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    if not math.isfinite(out):
        return None
    return out


def quantile(values: list[float], q: float) -> float | str:
    if not values:
        return ""
    return float(pd.Series(values, dtype="float64").quantile(q))


def mean(values: list[float]) -> float | str:
    return float(pd.Series(values, dtype="float64").mean()) if values else ""


def median(values: list[float]) -> float | str:
    return float(pd.Series(values, dtype="float64").median()) if values else ""


def rate(values: list[bool]) -> float | str:
    return float(pd.Series(values, dtype="bool").mean()) if values else ""


def sequential_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return float(max_dd)


def return_stats(values: list[float]) -> dict[str, Any]:
    summary = ref.return_summary(values) if values else {
        "eligible_trade_count": 0,
        "mean_net_return_pct": "",
        "median_net_return_pct": "",
        "p10_net_return_pct": "",
        "p25_net_return_pct": "",
        "p75_net_return_pct": "",
        "p90_net_return_pct": "",
        "win_rate": "",
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "profit_factor": "",
        "max_single_trade_gain": "",
        "max_single_trade_loss": "",
        "maximum_consecutive_losses": 0,
    }
    summary["sequential_equal_unit_drawdown_proxy"] = sequential_drawdown(values) if values else 0.0
    return summary


def call_value(spot: float, strike: float, valuation_date: pd.Timestamp, expiry_date: pd.Timestamp) -> float:
    years = max((expiry_date.date() - valuation_date.date()).days, 0) / 365.25
    return call_price(
        spot,
        strike,
        years,
        ref.ASSUMPTIONS.annualized_implied_volatility,
        ref.ASSUMPTIONS.risk_free_rate,
        ref.ASSUMPTIONS.continuous_dividend_yield,
    )


@dataclass(frozen=True)
class ModeledPath:
    record: dict[str, Any]
    path: list[dict[str, Any]]


def model_trade_path(signal: dict[str, Any], history: pd.DataFrame) -> ModeledPath | dict[str, Any]:
    entry_session = pd.Timestamp(signal["entry_session"])
    entry_price = as_float(signal.get("entry_price"))
    if entry_price is None or entry_price <= 0:
        return {"status": "excluded", "excluded_reason": "missing_entry_price"}
    future = history[history["date"] >= entry_session].head(ref.ASSUMPTIONS.max_holding_sessions).copy()
    if future.empty or pd.Timestamp(future.iloc[0]["date"]) != entry_session:
        return {"status": "excluded", "excluded_reason": "missing_entry_session_ohlcv"}
    expiry_date = entry_session + pd.Timedelta(days=ref.ASSUMPTIONS.initial_calendar_dte)
    entry_years = ref.ASSUMPTIONS.initial_calendar_dte / 365.25
    strike, solved_delta = solve_strike_for_call_delta(
        entry_price,
        entry_years,
        ref.ASSUMPTIONS.annualized_implied_volatility,
        ref.ASSUMPTIONS.target_entry_delta,
        ref.ASSUMPTIONS.risk_free_rate,
        ref.ASSUMPTIONS.continuous_dividend_yield,
        tolerance=1e-10,
    )
    delta_error = abs(solved_delta - ref.ASSUMPTIONS.target_entry_delta)
    if delta_error > 1e-6:
        return {"status": "excluded", "excluded_reason": "delta_solve_failed"}
    entry_value = call_price(
        entry_price,
        strike,
        entry_years,
        ref.ASSUMPTIONS.annualized_implied_volatility,
        ref.ASSUMPTIONS.risk_free_rate,
        ref.ASSUMPTIONS.continuous_dividend_yield,
    )
    entry_debit = entry_value * (1.0 + ref.ASSUMPTIONS.entry_markup)
    path: list[dict[str, Any]] = []
    for idx, row in enumerate(future.itertuples(index=False), start=1):
        date = pd.Timestamp(row.date)
        row_out: dict[str, Any] = {
            "session_index": idx,
            "date": date,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        }
        for field in ["open", "high", "low", "close"]:
            value = call_value(float(getattr(row, field)), strike, date, expiry_date)
            row_out[f"net_return_{field}_pct"] = (value * (1.0 - ref.ASSUMPTIONS.exit_haircut) / entry_debit - 1.0) * 100.0
        path.append(row_out)
        if date >= expiry_date:
            break
    if len(path) < min(ref.ASSUMPTIONS.progress_gate_horizon_sessions, ref.ASSUMPTIONS.max_holding_sessions):
        return {"status": "excluded", "excluded_reason": "unavailable_required_path_data"}
    reached_plus5 = as_bool(signal.get("reached_plus_5pct_within_10_sessions", ""))
    if not reached_plus5:
        terminal = path[ref.ASSUMPTIONS.progress_gate_horizon_sessions - 1]
        terminal_reason = "day10_plus5_not_reached"
    else:
        terminal = path[-1]
        if terminal["date"] >= expiry_date:
            terminal_reason = "option_expiration"
        elif len(path) >= ref.ASSUMPTIONS.max_holding_sessions:
            terminal_reason = "max_holding_30_sessions"
        else:
            return {"status": "excluded", "excluded_reason": "unavailable_required_path_data"}
    terminal_path = path[: int(terminal["session_index"])]
    first_100 = next((row for row in terminal_path if row["net_return_high_pct"] >= 100.0), None)
    first_125 = next((row for row in terminal_path if row["net_return_high_pct"] >= 125.0), None)
    if first_100 is not None:
        post100 = [row for row in terminal_path if row["session_index"] >= first_100["session_index"]]
        post100_peak = max(row["net_return_high_pct"] for row in post100)
        post100_trough = min(row["net_return_close_pct"] for row in post100)
    else:
        post100_peak = ""
        post100_trough = ""
    record = {
        "status": "eligible",
        "signal_id": signal["signal_id"],
        "ticker": signal["underlying_symbol"],
        "signal_decision_date": str(signal["signal_decision_date"]),
        "entry_date": str(signal["entry_session"]),
        "theme": signal.get("theme", ""),
        "entry_underlying_price": entry_price,
        "breakout_day_low": signal.get("breakout_day_low", ""),
        "strike": strike,
        "entry_debit": entry_debit,
        "expiry_date": expiry_date.strftime("%Y-%m-%d"),
        "path_session_count": len(terminal_path),
        "terminal_date": pd.Timestamp(terminal["date"]).strftime("%Y-%m-%d"),
        "terminal_reason": terminal_reason,
        "terminal_net_return_pct": terminal["net_return_close_pct"],
        "first_hit_100_date": pd.Timestamp(first_100["date"]).strftime("%Y-%m-%d") if first_100 else "",
        "first_hit_100_session": int(first_100["session_index"]) if first_100 else "",
        "first_hit_125_date": pd.Timestamp(first_125["date"]).strftime("%Y-%m-%d") if first_125 else "",
        "first_hit_125_session": int(first_125["session_index"]) if first_125 else "",
        "max_net_return_high_pct": max(row["net_return_high_pct"] for row in terminal_path),
        "min_net_return_close_pct": min(row["net_return_close_pct"] for row in terminal_path),
        "min_net_return_low_pct": min(row["net_return_low_pct"] for row in terminal_path),
        "post_100_peak_net_return_pct": post100_peak,
        "post_100_trough_net_return_pct": post100_trough,
        "reached_plus_5pct_within_10_sessions": as_bool(signal.get("reached_plus_5pct_within_10_sessions", "")),
        "breakout_day_low_breach_before_timeout": as_bool(signal.get("breakout_day_low_breach_before_timeout", "")),
        "timeout_10_sessions_under_threshold": as_bool(signal.get("timeout_10_sessions_under_threshold", "")),
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
    }
    return ModeledPath(record=record, path=terminal_path)


def load_modeled_paths(
    baseline_run_dir: Path = ref.DEFAULT_BASELINE_DIR,
) -> tuple[list[ModeledPath], list[dict[str, Any]], dict[str, Any]]:
    s_panel, receipt = ref.load_formal_s_panel(baseline_run_dir)
    input_root = ref.baseline_input_root(baseline_run_dir)
    tickers = set(s_panel["underlying_symbol"].astype(str))
    histories = ref.load_ohlcv_subset(input_root, tickers)
    modeled: list[ModeledPath] = []
    coverage: list[dict[str, Any]] = []
    for _, row in s_panel.iterrows():
        sig = row.to_dict()
        ticker = str(sig["underlying_symbol"])
        if ticker not in histories:
            result: ModeledPath | dict[str, Any] = {"status": "excluded", "excluded_reason": "missing_ticker_ohlcv"}
        else:
            result = model_trade_path(sig, histories[ticker])
        status = result.record["status"] if isinstance(result, ModeledPath) else str(result["status"])
        reason = "" if isinstance(result, ModeledPath) else str(result.get("excluded_reason", ""))
        coverage.append({"signal_id": sig["signal_id"], "ticker": ticker, "entry_date": sig["entry_session"], "status": status, "excluded_reason": reason})
        if isinstance(result, ModeledPath):
            modeled.append(result)
    return modeled, coverage, {"baseline_receipt": receipt, "input_root": input_root, "formal_s_records": len(s_panel)}


def baseline_tp125_return(path: ModeledPath) -> float:
    return 125.0 if has_value(path.record.get("first_hit_125_date")) else float(path.record["terminal_net_return_pct"])


def behavioral_returns(path: ModeledPath) -> dict[str, dict[str, Any]]:
    base = path.record
    rows = path.path
    terminal = float(base["terminal_net_return_pct"])
    first125 = int(base["first_hit_125_session"]) if has_value(base.get("first_hit_125_session")) else None
    first100 = int(base["first_hit_100_session"]) if has_value(base.get("first_hit_100_session")) else None
    out: dict[str, dict[str, Any]] = {
        "BASELINE_TP125": {
            "return_pct": 125.0 if first125 is not None else terminal,
            "status": "valid",
            "exit_session": first125 if first125 is not None else int(base["path_session_count"]),
            "exit_reason": "tp125" if first125 is not None else base["terminal_reason"],
            "triggered": first125 is not None,
        },
        "FEAR_TP100": {
            "return_pct": 100.0 if first100 is not None else terminal,
            "status": "valid",
            "exit_session": first100 if first100 is not None else int(base["path_session_count"]),
            "exit_reason": "tp100" if first100 is not None else base["terminal_reason"],
            "triggered": first100 is not None,
        },
        "COMPROMISE_STAGED_100_125": {
            "return_pct": 0.5 * 100.0 + 0.5 * (125.0 if first125 is not None else terminal) if first100 is not None else terminal,
            "status": "valid",
            "exit_session": first100 if first100 is not None else (first125 if first125 is not None else int(base["path_session_count"])),
            "exit_reason": "staged_100_125" if first100 is not None else base["terminal_reason"],
            "triggered": first100 is not None,
        },
        "GREED_IGNORE_TP125_HOLD_TO_INDEPENDENT_TERMINAL": {
            "return_pct": terminal,
            "status": "valid",
            "exit_session": int(base["path_session_count"]),
            "exit_reason": base["terminal_reason"],
            "triggered": first125 is not None,
        },
    }
    for policy, threshold in [
        ("PANIC_OPTION_STOP_25_NEXT_OPEN", -25.0),
        ("PANIC_OPTION_STOP_50_NEXT_OPEN", -50.0),
    ]:
        variant = {"return_pct": terminal, "status": "valid", "exit_session": int(base["path_session_count"]), "exit_reason": base["terminal_reason"], "triggered": False}
        for idx, row in enumerate(rows):
            if row["net_return_high_pct"] >= 125.0:
                variant = {"return_pct": 125.0, "status": "valid", "exit_session": int(row["session_index"]), "exit_reason": "tp125_priority", "triggered": False}
                break
            if row["net_return_close_pct"] <= threshold:
                if idx + 1 >= len(rows):
                    variant = {"return_pct": "", "status": "unavailable_next_open", "exit_session": "", "exit_reason": "missing_next_open", "triggered": True}
                else:
                    nxt = rows[idx + 1]
                    variant = {
                        "return_pct": float(nxt["net_return_open_pct"]),
                        "status": "valid",
                        "exit_session": int(nxt["session_index"]),
                        "exit_reason": "panic_next_open",
                        "triggered": True,
                    }
                break
        out[policy] = variant
    breakout_low = as_float(base.get("breakout_day_low"))
    low_variant = {"return_pct": terminal, "status": "valid", "exit_session": int(base["path_session_count"]), "exit_reason": base["terminal_reason"], "triggered": False}
    if breakout_low is None:
        low_variant = {"return_pct": "", "status": "missing_breakout_day_low", "exit_session": "", "exit_reason": "missing_breakout_day_low", "triggered": False}
    else:
        for idx, row in enumerate(rows):
            hit_target = row["net_return_high_pct"] >= 125.0
            hit_low = row["low"] <= breakout_low
            if hit_target and hit_low:
                low_variant = {"return_pct": "", "status": "ambiguous_same_day_stop_tp", "exit_session": "", "exit_reason": "ambiguous_same_day_stop_tp", "triggered": True}
                break
            if hit_target:
                low_variant = {"return_pct": 125.0, "status": "valid", "exit_session": int(row["session_index"]), "exit_reason": "tp125", "triggered": False}
                break
            if hit_low:
                if idx + 1 >= len(rows):
                    low_variant = {"return_pct": "", "status": "unavailable_next_open", "exit_session": "", "exit_reason": "missing_next_open", "triggered": True}
                else:
                    nxt = rows[idx + 1]
                    low_variant = {
                        "return_pct": float(nxt["net_return_open_pct"]),
                        "status": "valid",
                        "exit_session": int(nxt["session_index"]),
                        "exit_reason": "breakout_low_next_open",
                        "triggered": True,
                    }
                break
    out["BREAKOUT_LOW_RISK_ALERT_TO_EXIT_NEXT_OPEN"] = low_variant
    return out


def concentration(rows: list[dict[str, Any]], return_field: str = "return_pct") -> dict[str, Any]:
    if not rows:
        return {
            "unique_ticker_count": 0,
            "largest_single_ticker_share": "",
            "top_five_ticker_share": "",
            "largest_calendar_quarter_share": "",
            "concentration_flag": False,
        }
    by_ticker = Counter(str(row["ticker"]) for row in rows)
    total = len(rows)
    ticker_shares = sorted((count / total for count in by_ticker.values()), reverse=True)
    quarters = Counter(pd.Timestamp(row["entry_date"]).to_period("Q").strftime("%YQ%q") for row in rows)
    quarter_share = max((count / total for count in quarters.values()), default=0.0)
    flag = ticker_shares[0] > 0.30 or quarter_share > 0.50
    return {
        "unique_ticker_count": len(by_ticker),
        "largest_single_ticker_share": ticker_shares[0],
        "top_five_ticker_share": sum(ticker_shares[:5]),
        "largest_calendar_quarter_share": quarter_share,
        "concentration_flag": bool(flag),
    }


def label_behavioral_variant(
    policy: str,
    baseline: dict[str, Any],
    row: dict[str, Any],
    concentration_flag: bool,
    baseline_n: int,
    ambiguous_rate: float = 0.0,
) -> str:
    if policy == "BASELINE_TP125":
        return "baseline_reference"
    if row["N"] < baseline_n * 0.80:
        return "insufficient_variant_coverage"
    if policy == "BREAKOUT_LOW_RISK_ALERT_TO_EXIT_NEXT_OPEN" and (ambiguous_rate > 0.10 or row["N"] < baseline_n * 0.80):
        return "diagnostic_only_ambiguous_ordering"
    if concentration_flag:
        return "tradeoff_not_clear"
    try:
        pf = float(row["PF"])
        base_pf = float(baseline["PF"])
    except (TypeError, ValueError):
        pf = math.nan
        base_pf = math.nan
    mean_delta = float(row["mean"]) - float(baseline["mean"])
    dd_delta = float(row["DD_proxy"]) - float(baseline["DD_proxy"])
    if (math.isfinite(pf) and math.isfinite(base_pf) and pf <= base_pf - 0.15) or mean_delta <= -5.0:
        return "materially_worse_than_baseline"
    if math.isfinite(pf) and math.isfinite(base_pf) and pf >= base_pf + 0.15 and dd_delta >= -5.0:
        return "appears_better_under_fixed_iv_model"
    return "tradeoff_not_clear"


def build_behavioral_outputs(output_dir: Path = BEHAVIORAL_OUTPUT_DIR, baseline_run_dir: Path = ref.DEFAULT_BASELINE_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    modeled, coverage, source_meta = load_modeled_paths(baseline_run_dir)
    baseline_reference = pd.read_csv(ref.DEFAULT_REFERENCE_OUTPUT_DIR / "s_single_call_trade_terminal_summary.csv", dtype={"signal_id": str})
    if len(modeled) != len(baseline_reference):
        raise ValueError(f"reference_denominator_mismatch:recomputed={len(modeled)}:reference={len(baseline_reference)}")
    expected = set(baseline_reference["signal_id"].astype(str))
    actual = {path.record["signal_id"] for path in modeled}
    if expected != actual:
        raise ValueError("reference_signal_id_mismatch")
    policy_trade_rows: list[dict[str, Any]] = []
    per_signal: dict[str, dict[str, dict[str, Any]]] = {}
    for path in modeled:
        returns = behavioral_returns(path)
        per_signal[path.record["signal_id"]] = returns
        for policy, result in returns.items():
            value = as_float(result.get("return_pct"))
            if result["status"] == "valid" and value is not None:
                policy_trade_rows.append(
                    {
                        **path.record,
                        "policy": policy,
                        "return_pct": value,
                        "variant_path_status": result["status"],
                        "exit_session": result["exit_session"],
                        "exit_reason": result["exit_reason"],
                        "triggered": result["triggered"],
                    }
                )
    source_rows = [
        {
            "component": "formal_baseline",
            "path": repo_relative(baseline_run_dir),
            "status": "verified",
            "sha256": ref.sha256_file(baseline_run_dir / "baseline_receipt.json"),
            "notes": "Formal S complete records only.",
        },
        {
            "component": "fixed_iv_reference_model",
            "path": repo_relative(ref.DEFAULT_REFERENCE_OUTPUT_DIR),
            "status": "verified",
            "sha256": ref.sha256_file(ref.DEFAULT_REFERENCE_OUTPUT_DIR / "s_single_call_reference_receipt.json"),
            "notes": "Synthetic fixed-IV reference model identity.",
        },
        {
            "component": "baseline_ohlcv_lineage",
            "path": repo_relative(source_meta["input_root"] / "sources" / "daily_ohlcv_merged.csv"),
            "status": "verified",
            "sha256": ref.sha256_file(source_meta["input_root"] / "source_manifest.json"),
            "notes": "Local formal-baseline lineage only; no new data acquired.",
        },
    ]
    ref.write_csv(output_dir / "source_verification.csv", source_rows, ["component", "path", "status", "sha256", "notes"])
    baseline_n = len(modeled)
    policy_summary_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    by_policy_rows = {policy: [row for row in policy_trade_rows if row["policy"] == policy] for policy in BEHAVIORAL_POLICIES}
    baseline_values = [float(row["return_pct"]) for row in by_policy_rows["BASELINE_TP125"]]
    baseline_stats = return_stats(baseline_values)
    baseline_row = {
        "policy": "BASELINE_TP125",
        "N": baseline_stats["eligible_trade_count"],
        "PF": baseline_stats["profit_factor"],
        "mean": baseline_stats["mean_net_return_pct"],
        "median": baseline_stats["median_net_return_pct"],
        "gross_profit": baseline_stats["gross_profit"],
        "gross_loss": baseline_stats["gross_loss"],
        "max_loss": baseline_stats["max_single_trade_loss"],
        "DD_proxy": baseline_stats["sequential_equal_unit_drawdown_proxy"],
        "delta_vs_baseline_mean": 0.0,
        "label": "baseline_reference",
    }
    for policy in BEHAVIORAL_POLICIES:
        rows = by_policy_rows[policy]
        values = [float(row["return_pct"]) for row in rows]
        stats = return_stats(values)
        conc = concentration(rows)
        concentration_rows.append({"scope": policy, **conc})
        status_counts = Counter(per_signal[path.record["signal_id"]][policy]["status"] for path in modeled)
        ambiguous_rate = status_counts.get("ambiguous_same_day_stop_tp", 0) / baseline_n if baseline_n else 0.0
        summary_row = {
            "policy": policy,
            "N": stats["eligible_trade_count"],
            "PF": stats["profit_factor"],
            "mean": stats["mean_net_return_pct"],
            "median": stats["median_net_return_pct"],
            "gross_profit": stats["gross_profit"],
            "gross_loss": stats["gross_loss"],
            "max_loss": stats["max_single_trade_loss"],
            "DD_proxy": stats["sequential_equal_unit_drawdown_proxy"],
            "delta_vs_baseline_mean": (float(stats["mean_net_return_pct"]) - float(baseline_stats["mean_net_return_pct"])) if values else "",
            "variant_valid_coverage_rate": len(rows) / baseline_n if baseline_n else "",
            "unavailable_next_open_count": status_counts.get("unavailable_next_open", 0),
            "ambiguous_same_day_stop_tp_count": status_counts.get("ambiguous_same_day_stop_tp", 0),
            "ambiguous_same_day_stop_tp_rate": ambiguous_rate,
            "synthetic_fixed_iv_reference_model": True,
            "not_historical_option_fill_reconstruction": True,
        }
        summary_row["label"] = label_behavioral_variant(policy, baseline_row, summary_row, bool(conc["concentration_flag"]), baseline_n, ambiguous_rate)
        policy_summary_rows.append(summary_row)
    paired_rows: list[dict[str, Any]] = []
    regret_rows: list[dict[str, Any]] = []
    for policy in BEHAVIORAL_POLICIES:
        if policy == "BASELINE_TP125":
            continue
        deltas: list[float] = []
        foregone: list[float] = []
        base_win_variant_loss = 0
        cut_before_target = 0
        exit_then_baseline_125 = 0
        trigger_count = 0
        valid_count = 0
        beats = 0
        loses = 0
        for path in modeled:
            sid = path.record["signal_id"]
            base_result = per_signal[sid]["BASELINE_TP125"]
            variant = per_signal[sid][policy]
            base_val = as_float(base_result["return_pct"])
            variant_val = as_float(variant["return_pct"])
            if base_val is None or variant_val is None or variant["status"] != "valid":
                continue
            valid_count += 1
            delta = variant_val - base_val
            deltas.append(delta)
            if base_val > 0 and variant_val < 0:
                base_win_variant_loss += 1
            first125 = as_float(path.record.get("first_hit_125_session"))
            exit_session = as_float(variant.get("exit_session"))
            if variant.get("triggered"):
                trigger_count += 1
            if first125 is not None and exit_session is not None and exit_session < first125:
                cut_before_target += 1
                exit_then_baseline_125 += 1
                foregone.append(base_val - variant_val)
            if policy == "GREED_IGNORE_TP125_HOLD_TO_INDEPENDENT_TERMINAL" and first125 is not None:
                if variant_val > base_val:
                    beats += 1
                elif variant_val < base_val:
                    loses += 1
        delta_stats = return_stats(deltas)
        paired_rows.append(
            {
                "policy": policy,
                "valid_paired_count": valid_count,
                "variant_minus_baseline_mean_return": delta_stats["mean_net_return_pct"],
                "variant_minus_baseline_median_return": delta_stats["median_net_return_pct"],
                "variant_minus_baseline_gross_profit": delta_stats["gross_profit"],
                "variant_minus_baseline_gross_loss": delta_stats["gross_loss"],
                "variant_minus_baseline_profit_factor": delta_stats["profit_factor"],
                "variant_minus_baseline_drawdown_proxy": delta_stats["sequential_equal_unit_drawdown_proxy"],
                "baseline_win_to_variant_loss_count": base_win_variant_loss,
                "baseline_win_to_variant_loss_rate": base_win_variant_loss / valid_count if valid_count else "",
                "baseline_TP125_winner_cut_before_target_count": cut_before_target,
                "baseline_TP125_winner_cut_before_target_rate": cut_before_target / valid_count if valid_count else "",
                "variant_exit_then_baseline_reaches_125_count": exit_then_baseline_125,
                "variant_exit_then_baseline_reaches_125_rate": exit_then_baseline_125 / valid_count if valid_count else "",
                "median_foregone_baseline_return_after_premature_exit": median(foregone),
                "p10_foregone_baseline_return_after_premature_exit": quantile(foregone, 0.10),
                "p05_foregone_baseline_return_after_premature_exit": quantile(foregone, 0.05),
                "worst_foregone_baseline_return_after_premature_exit": min(foregone) if foregone else "",
                "greedy_hold_beats_TP125_count": beats,
                "greedy_hold_loses_to_TP125_count": loses,
            }
        )
        regret_rows.append(
            {
                "policy": policy,
                "trigger_count": trigger_count,
                "valid_paired_count": valid_count,
                "cut_before_baseline_TP125_count": cut_before_target,
                "cut_before_baseline_TP125_rate": cut_before_target / valid_count if valid_count else "",
                "eventual_baseline_TP125_after_exit_count": exit_then_baseline_125,
                "foregone_return_median": median(foregone),
                "foregone_return_p10": quantile(foregone, 0.10),
                "foregone_return_p05": quantile(foregone, 0.05),
                "foregone_return_worst": min(foregone) if foregone else "",
            }
        )
    post_rows = post_125_hold_summary(modeled)
    pain_rows = pain_atlas(modeled)
    chronological_rows = behavioral_chronological(policy_trade_rows)
    representative_rows = behavioral_representatives(modeled, per_signal)
    ref.write_csv(output_dir / "behavioral_policy_summary.csv", policy_summary_rows, list(policy_summary_rows[0].keys()))
    ref.write_csv(output_dir / "paired_damage_vs_baseline.csv", paired_rows, list(paired_rows[0].keys()))
    ref.write_csv(output_dir / "false_exit_regret_summary.csv", regret_rows, list(regret_rows[0].keys()))
    ref.write_csv(output_dir / "post_125_hold_summary.csv", post_rows, list(post_rows[0].keys()))
    ref.write_csv(output_dir / "pain_atlas_summary.csv", pain_rows, list(pain_rows[0].keys()))
    ref.write_csv(output_dir / "concentration_summary.csv", concentration_rows, list(concentration_rows[0].keys()))
    ref.write_csv(output_dir / "chronological_summary.csv", chronological_rows, list(chronological_rows[0].keys()))
    ref.write_csv(output_dir / "representative_paths.csv", representative_rows, list(representative_rows[0].keys()) if representative_rows else ["category", "signal_id"])
    receipt = {
        "status": "completed",
        "created_at_utc": ref.utc_now(),
        "baseline_run_id": source_meta["baseline_receipt"].get("run_id", ""),
        "formal_complete_s_records": source_meta["formal_s_records"],
        "eligible_trade_count": baseline_n,
        "excluded_trade_count": len([row for row in coverage if row["status"] != "eligible"]),
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
        "research_only_no_live_strategy_change": True,
        "new_market_or_option_data_downloaded": False,
    }
    ref.write_json(output_dir / "behavioral_discipline_receipt.json", receipt)
    (output_dir / "behavioral_discipline_summary.md").write_text(render_behavioral_summary(policy_summary_rows, regret_rows, post_rows, pain_rows), encoding="utf-8")
    ref.build_manifest(output_dir, "behavioral_discipline_content_manifest.json", BEHAVIORAL_REQUIRED_FILES)
    assert_no_actionization(output_dir)
    return receipt


def post_125_hold_summary(modeled: list[ModeledPath]) -> list[dict[str, Any]]:
    rows = []
    hit_paths = [path for path in modeled if has_value(path.record.get("first_hit_125_session"))]
    drawdowns: list[float] = []
    terminal_returns: list[float] = []
    times: list[int] = []
    for path in hit_paths:
        first = int(path.record["first_hit_125_session"])
        post = [row for row in path.path if row["session_index"] >= first]
        trough = min(row["net_return_close_pct"] for row in post)
        drawdown = trough - 125.0
        drawdowns.append(drawdown)
        terminal = float(path.record["terminal_net_return_pct"])
        terminal_returns.append(terminal)
        times.append(int(path.record["path_session_count"]) - first)
    n = len(hit_paths)
    rows.append(
        {
            "cohort": "TP125_hit_trades",
            "N": n,
            "terminal_below_125_rate": sum(v < 125.0 for v in terminal_returns) / n if n else "",
            "terminal_below_100_rate": sum(v < 100.0 for v in terminal_returns) / n if n else "",
            "terminal_below_0_rate": sum(v < 0.0 for v in terminal_returns) / n if n else "",
            "terminal_above_125_rate": sum(v > 125.0 for v in terminal_returns) / n if n else "",
            "post_125_drawdown_median": median(drawdowns),
            "post_125_drawdown_p10": quantile(drawdowns, 0.10),
            "post_125_drawdown_p05": quantile(drawdowns, 0.05),
            "post_125_drawdown_worst": min(drawdowns) if drawdowns else "",
            "post_125_drawdown_le_minus25pp_rate": sum(v <= -25.0 for v in drawdowns) / n if n else "",
            "post_125_drawdown_le_minus50pp_rate": sum(v <= -50.0 for v in drawdowns) / n if n else "",
            "post_125_drawdown_le_minus100pp_rate": sum(v <= -100.0 for v in drawdowns) / n if n else "",
            "post_125_drawdown_le_minus125pp_rate": sum(v <= -125.0 for v in drawdowns) / n if n else "",
            "terminal_return_median": median(terminal_returns),
            "terminal_return_p10": quantile(terminal_returns, 0.10),
            "terminal_return_p05": quantile(terminal_returns, 0.05),
            "terminal_return_worst": min(terminal_returns) if terminal_returns else "",
            "time_from_first_125_to_terminal_median": median([float(x) for x in times]),
        }
    )
    return rows


def pain_atlas(modeled: list[ModeledPath]) -> list[dict[str, Any]]:
    rows = []
    winners = [path for path in modeled if has_value(path.record.get("first_hit_125_session"))]
    for cohort, paths in [("TP125_winners_pre_target", winners), ("all_baseline_trades", modeled)]:
        mae_low: list[float] = []
        mae_close: list[float] = []
        sessions: list[float] = []
        under_entry_counts: list[float] = []
        for path in paths:
            if cohort == "TP125_winners_pre_target":
                first = int(path.record["first_hit_125_session"])
                sample = [row for row in path.path if row["session_index"] < first]
                sessions.append(float(first))
                under_entry_counts.append(float(sum(row["net_return_close_pct"] < 0.0 for row in sample)))
            else:
                sample = path.path
                sessions.append(float(path.record["path_session_count"]))
            if sample:
                mae_low.append(min(row["net_return_low_pct"] for row in sample))
                mae_close.append(min(row["net_return_close_pct"] for row in sample))
        n = len(paths)
        rows.append(
            {
                "cohort": cohort,
                "N": n,
                "MAE_low_median": median(mae_low),
                "MAE_low_p10": quantile(mae_low, 0.10),
                "MAE_low_p05": quantile(mae_low, 0.05),
                "MAE_low_worst": min(mae_low) if mae_low else "",
                "MAE_close_median": median(mae_close),
                "MAE_close_p10": quantile(mae_close, 0.10),
                "MAE_close_p05": quantile(mae_close, 0.05),
                "MAE_close_worst": min(mae_close) if mae_close else "",
                "share_low_le_minus10_before_TP125": sum(v <= -10.0 for v in mae_low) / len(mae_low) if mae_low and cohort == "TP125_winners_pre_target" else "",
                "share_low_le_minus25_before_TP125": sum(v <= -25.0 for v in mae_low) / len(mae_low) if mae_low and cohort == "TP125_winners_pre_target" else "",
                "share_low_le_minus50_before_TP125": sum(v <= -50.0 for v in mae_low) / len(mae_low) if mae_low and cohort == "TP125_winners_pre_target" else "",
                "share_low_le_minus75_before_TP125": sum(v <= -75.0 for v in mae_low) / len(mae_low) if mae_low and cohort == "TP125_winners_pre_target" else "",
                "median_sessions_to_TP125_or_terminal": median(sessions),
                "median_sessions_under_entry_close_before_TP125": median(under_entry_counts),
            }
        )
    return rows


def behavioral_chronological(policy_trade_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    dates = sorted({row["entry_date"] for row in policy_trade_rows})
    split = (len(dates) + 1) // 2
    early = set(dates[:split])
    for policy in BEHAVIORAL_POLICIES:
        rows = [row for row in policy_trade_rows if row["policy"] == policy]
        for half_name, subset in [("early_half", [row for row in rows if row["entry_date"] in early]), ("late_half", [row for row in rows if row["entry_date"] not in early])]:
            values = [float(row["return_pct"]) for row in subset]
            stats = return_stats(values)
            output.append(
                {
                    "policy": policy,
                    "chronological_half": half_name,
                    "N": len(subset),
                    "PF": stats["profit_factor"],
                    "mean": stats["mean_net_return_pct"],
                    "median": stats["median_net_return_pct"],
                    "DD_proxy": stats["sequential_equal_unit_drawdown_proxy"],
                }
            )
    return output


def behavioral_representatives(modeled: list[ModeledPath], per_signal: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    winner_pain = []
    panic25 = []
    panic50 = []
    greed = []
    for path in modeled:
        sid = path.record["signal_id"]
        if has_value(path.record.get("first_hit_125_session")):
            first = int(path.record["first_hit_125_session"])
            pre = [row for row in path.path if row["session_index"] < first]
            if pre:
                winner_pain.append((min(row["net_return_low_pct"] for row in pre), path))
            terminal = float(path.record["terminal_net_return_pct"])
            greed.append((terminal - 125.0, path))
        for policy, bucket in [("PANIC_OPTION_STOP_25_NEXT_OPEN", panic25), ("PANIC_OPTION_STOP_50_NEXT_OPEN", panic50)]:
            variant = per_signal[sid][policy]
            first = as_float(path.record.get("first_hit_125_session"))
            exit_sess = as_float(variant.get("exit_session"))
            if first is not None and exit_sess is not None and exit_sess < first:
                bucket.append((float(variant["return_pct"]) - 125.0, path))
    for category, items in [
        ("severe_drawdown_eventual_TP125_winner", sorted(winner_pain, key=lambda x: x[0])[:5]),
        ("panic25_exit_later_TP125", sorted(panic25, key=lambda x: x[0])[:5]),
        ("panic50_exit_later_TP125", sorted(panic50, key=lambda x: x[0])[:5]),
        ("greed_hold_material_giveback", sorted(greed, key=lambda x: x[0])[:5]),
    ]:
        for rank, (score, path) in enumerate(items, start=1):
            rows.append(
                {
                    "category": category,
                    "rank": rank,
                    "signal_id": path.record["signal_id"],
                    "ticker": path.record["ticker"],
                    "entry_date": path.record["entry_date"],
                    "theme": path.record.get("theme", ""),
                    "derived_score": score,
                    "baseline_TP125_return_pct": baseline_tp125_return(path),
                    "terminal_net_return_pct": path.record["terminal_net_return_pct"],
                    "first_hit_125_session": path.record.get("first_hit_125_session", ""),
                }
            )
    return rows


def render_behavioral_summary(policy_rows: list[dict[str, Any]], regret_rows: list[dict[str, Any]], post_rows: list[dict[str, Any]], pain_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Morita S Behavioral Discipline / Drawdown Atlas v1",
        "",
        "synthetic_fixed_iv_reference_model=true",
        "not_historical_option_fill_reconstruction=true",
        "not_live_execution_estimate=true",
        "research_only_no_live_strategy_change=true",
        "",
        "## Policy Summary",
        "",
        "| Policy | N | PF | Mean | Median | DD Proxy | Label |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in policy_rows:
        lines.append(f"| {row['policy']} | {row['N']} | {row['PF']} | {row['mean']} | {row['median']} | {row['DD_proxy']} | {row['label']} |")
    lines.extend(
        [
            "",
            "Low valuations are diagnostics only. No live alert/trading/pause change is made.",
            "",
            "## Post-125 Hold Summary",
            "",
            f"`{post_rows[0]}`",
            "",
            "## TP125 Winner Pain Atlas",
            "",
            f"`{pain_rows[0]}`",
        ]
    )
    return "\n".join(lines) + "\n"


def assert_no_actionization(output_dir: Path) -> None:
    for path in output_dir.glob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in LIVE_ACTION_TOKENS:
                if token in text:
                    raise AssertionError(f"live_action_token_detected:{token}:{path}")


def verify_behavioral_manifest(output_dir: Path = BEHAVIORAL_OUTPUT_DIR) -> dict[str, Any]:
    result = ref.verify_manifest(output_dir, "behavioral_discipline_content_manifest.json", BEHAVIORAL_REQUIRED_FILES)
    assert_no_actionization(output_dir)
    return result


def load_pause_trade_panel() -> tuple[pd.DataFrame, dict[str, Any]]:
    terminal = pd.read_csv(ref.DEFAULT_REFERENCE_OUTPUT_DIR / "s_single_call_trade_terminal_summary.csv", dtype={"signal_id": str})
    terminal["TP125_return_pct"] = terminal.apply(lambda row: 125.0 if has_value(row.get("first_hit_125_date")) else float(row["terminal_net_return_pct"]), axis=1)
    s_panel, receipt = ref.load_formal_s_panel(ref.DEFAULT_BASELINE_DIR)
    keep = [
        "signal_id",
        "underlying_symbol",
        "signal_rank",
        "reached_plus_5pct_within_10_sessions",
        "breakout_day_low_breach_before_timeout",
        "timeout_10_sessions_under_threshold",
    ]
    merged = terminal.merge(s_panel[keep], on="signal_id", how="left", validate="one_to_one")
    if not (merged["signal_rank"].astype(str) == "S").all():
        raise ValueError("pause_denominator_not_s_only")
    return merged, {"baseline_receipt": receipt}


def load_qqq_history() -> pd.DataFrame:
    root = ref.baseline_input_root(ref.DEFAULT_BASELINE_DIR)
    histories = ref.load_ohlcv_subset(root, {"QQQ"})
    if "QQQ" not in histories:
        raise ValueError("qqq_lineage_missing")
    qqq = histories["QQQ"].copy()
    qqq["sma20"] = qqq["close"].rolling(20, min_periods=20).mean()
    qqq["sma50"] = qqq["close"].rolling(50, min_periods=50).mean()
    qqq["QQQ_TREND_BREAK_ON"] = (qqq["close"] < qqq["sma50"]) & (qqq["sma20"] < qqq["sma50"])
    return qqq


def narrow_leadership_states() -> pd.DataFrame:
    source = REPO_ROOT / "outputs" / "morita_realized_dispersion_quick_screen" / "realized_dispersion_signal_context_panel.csv"
    raw = pd.read_csv(source, dtype={"signal_id": str})
    raw = raw[raw["scope"] == "broad_market_context"].copy()
    pivot = raw.pivot_table(index="signal_id", columns="metric", values="metric_state", aggfunc="first").reset_index()
    pivot["NARROW_LEADERSHIP_ON"] = (
        pivot["broad_russell1000_cross_sectional_dispersion_20d"].astype(str).eq("high")
        & pivot["broad_russell1000_qqq_minus_eqw_return_20d"].astype(str).eq("high")
    )
    return pivot[["signal_id", "NARROW_LEADERSHIP_ON"]]


def add_pause_states(trades: pd.DataFrame, qqq: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["decision_ts"] = pd.to_datetime(out["signal_decision_date"])
    qqq_by_date = qqq.set_index("date")
    trend_values = []
    fwd_metrics = []
    for date in out["decision_ts"]:
        if date not in qqq_by_date.index:
            trend_values.append(pd.NA)
            fwd_metrics.append({})
            continue
        loc = qqq.index[qqq["date"] == date][0]
        base_close = float(qqq.loc[loc, "close"])
        trend_values.append(bool(qqq.loc[loc, "QQQ_TREND_BREAK_ON"]) if not pd.isna(qqq.loc[loc, "QQQ_TREND_BREAK_ON"]) else pd.NA)
        metrics: dict[str, Any] = {}
        for horizon in [20, 40]:
            future = qqq.iloc[loc + 1 : loc + 1 + horizon]
            if len(future) < horizon:
                metrics[f"forward_{horizon}_session_return"] = pd.NA
                metrics[f"forward_{horizon}_session_max_drawdown_from_decision_close"] = pd.NA
            else:
                metrics[f"forward_{horizon}_session_return"] = float(future.iloc[-1]["close"] / base_close - 1.0)
                metrics[f"forward_{horizon}_session_max_drawdown_from_decision_close"] = float(future["close"].min() / base_close - 1.0)
        fwd_metrics.append(metrics)
    out["QQQ_TREND_BREAK_ON"] = trend_values
    fwd = pd.DataFrame(fwd_metrics)
    out = pd.concat([out.reset_index(drop=True), fwd.reset_index(drop=True)], axis=1)
    narrow = narrow_leadership_states()
    out = out.merge(narrow, on="signal_id", how="left", validate="one_to_one")
    cross = pd.read_csv(REPO_ROOT / "outputs" / "phase1_6b_cross_module_downside" / "cross_module_daily_panel.csv")
    cross["observation_date"] = pd.to_datetime(cross["observation_date"])
    out = out.merge(
        cross[["observation_date", "cta_consensus_category", "vol_change_consensus_category"]],
        left_on="decision_ts",
        right_on="observation_date",
        how="left",
        validate="many_to_one",
    )
    out["CTA_RISK_OFF"] = out["cta_consensus_category"].astype(str).eq("cta_all_risk_off")
    out["CTA_AVAILABLE"] = out["cta_consensus_category"].astype(str).ne("cta_incomplete") & out["cta_consensus_category"].notna()
    out["VOL_ALL_REDUCE"] = out["vol_change_consensus_category"].astype(str).eq("vol_all_reduce_risk")
    out["VOL_AVAILABLE"] = out["vol_change_consensus_category"].astype(str).ne("vol_incomplete") & out["vol_change_consensus_category"].notna()
    out["STATE_0_BASELINE"] = False
    out["STATE_1_NARROW_LEADERSHIP_ONLY"] = out["NARROW_LEADERSHIP_ON"].fillna(False).astype(bool)
    out["STATE_2_TREND_BREAK_ONLY"] = out["QQQ_TREND_BREAK_ON"].fillna(False).astype(bool)
    risk_off_or_reduce = out["CTA_RISK_OFF"].fillna(False).astype(bool) | out["VOL_ALL_REDUCE"].fillna(False).astype(bool)
    out["STATE_3_CASCADE"] = out["STATE_2_TREND_BREAK_ONLY"] & risk_off_or_reduce
    out["STATE_4_FULL_CASCADE"] = out["STATE_2_TREND_BREAK_ONLY"] & out["STATE_1_NARROW_LEADERSHIP_ONLY"] & risk_off_or_reduce
    out["FWD20_DD10"] = out["forward_20_session_max_drawdown_from_decision_close"] <= -0.10
    out["FWD40_DD15"] = out["forward_40_session_max_drawdown_from_decision_close"] <= -0.15
    return out


def state_component_coverage(panel: pd.DataFrame, state: str) -> float:
    if state == "STATE_0_BASELINE":
        return 1.0
    if state == "STATE_1_NARROW_LEADERSHIP_ONLY":
        return float(panel["NARROW_LEADERSHIP_ON"].notna().mean())
    if state == "STATE_2_TREND_BREAK_ONLY":
        return float(panel["QQQ_TREND_BREAK_ON"].notna().mean())
    if state == "STATE_3_CASCADE":
        return float((panel["QQQ_TREND_BREAK_ON"].notna() & (panel["CTA_AVAILABLE"] | panel["VOL_AVAILABLE"])).mean())
    if state == "STATE_4_FULL_CASCADE":
        return float((panel["QQQ_TREND_BREAK_ON"].notna() & panel["NARROW_LEADERSHIP_ON"].notna() & (panel["CTA_AVAILABLE"] | panel["VOL_AVAILABLE"])).mean())
    raise ValueError(state)


def pause_group_stats(rows: pd.DataFrame, state: str, group_name: str) -> dict[str, Any]:
    values = [float(v) for v in rows["TP125_return_pct"].dropna().tolist()]
    stats = return_stats(values)
    return {
        "state": state,
        "group": group_name,
        "count": len(rows),
        "rate": len(rows) / stats["eligible_trade_count"] if False else "",
        "mean_TP125_return_pct": stats["mean_net_return_pct"],
        "median_TP125_return_pct": stats["median_net_return_pct"],
        "p10_TP125_return_pct": stats["p10_net_return_pct"],
        "p25_TP125_return_pct": stats["p25_net_return_pct"],
        "p75_TP125_return_pct": stats["p75_net_return_pct"],
        "p90_TP125_return_pct": stats["p90_net_return_pct"],
        "gross_profit": stats["gross_profit"],
        "gross_loss": stats["gross_loss"],
        "profit_factor": stats["profit_factor"],
        "max_single_loss": stats["max_single_trade_loss"],
        "plus5_within_10_rate": float(rows["reached_plus_5pct_within_10_sessions"].astype(str).str.lower().eq("true").mean()) if len(rows) else "",
        "breakout_day_low_breach_rate": float(rows["breakout_day_low_breach_before_timeout"].astype(str).str.lower().eq("true").mean()) if len(rows) else "",
        "timeout_rate": float(rows["timeout_10_sessions_under_threshold"].astype(str).str.lower().eq("true").mean()) if len(rows) else "",
        "sequential_equal_unit_drawdown_proxy": stats["sequential_equal_unit_drawdown_proxy"],
    }


def forward_risk_stats(rows: pd.DataFrame, state: str, group_name: str) -> dict[str, Any]:
    return {
        "state": state,
        "group": group_name,
        "count": len(rows),
        "FWD20_DD10_incidence": float(rows["FWD20_DD10"].fillna(False).mean()) if len(rows) else "",
        "FWD40_DD15_incidence": float(rows["FWD40_DD15"].fillna(False).mean()) if len(rows) else "",
        "mean_forward_20_session_return": mean([float(v) for v in rows["forward_20_session_return"].dropna().tolist()]),
        "median_forward_20_session_return": median([float(v) for v in rows["forward_20_session_return"].dropna().tolist()]),
        "mean_forward_40_session_return": mean([float(v) for v in rows["forward_40_session_return"].dropna().tolist()]),
        "median_forward_40_session_return": median([float(v) for v in rows["forward_40_session_return"].dropna().tolist()]),
        "mean_forward_20_session_max_drawdown": mean([float(v) for v in rows["forward_20_session_max_drawdown_from_decision_close"].dropna().tolist()]),
        "median_forward_20_session_max_drawdown": median([float(v) for v in rows["forward_20_session_max_drawdown_from_decision_close"].dropna().tolist()]),
        "mean_forward_40_session_max_drawdown": mean([float(v) for v in rows["forward_40_session_max_drawdown_from_decision_close"].dropna().tolist()]),
        "median_forward_40_session_max_drawdown": median([float(v) for v in rows["forward_40_session_max_drawdown_from_decision_close"].dropna().tolist()]),
    }


def label_pause_state(paused: dict[str, Any], allowed: dict[str, Any], risk_paused: dict[str, Any], risk_allowed: dict[str, Any], conc_flag: bool, coverage: float) -> str:
    paused_count = int(paused["count"])
    allowed_count = int(allowed["count"])
    if paused_count < 20 or coverage < 0.90:
        return "insufficient_sample_or_coverage"
    try:
        paused_pf = float(paused["profit_factor"])
        allowed_pf = float(allowed["profit_factor"])
    except (TypeError, ValueError):
        paused_pf = math.nan
        allowed_pf = math.nan
    paused_breach = as_float(paused["breakout_day_low_breach_rate"]) or 0.0
    allowed_breach = as_float(allowed["breakout_day_low_breach_rate"]) or 0.0
    paused_fwd = as_float(risk_paused["FWD20_DD10_incidence"]) or 0.0
    allowed_fwd = as_float(risk_allowed["FWD20_DD10_incidence"]) or 0.0
    adverse = 0
    if math.isfinite(paused_pf) and math.isfinite(allowed_pf) and paused_pf < allowed_pf:
        adverse += 1
    if paused_breach > allowed_breach:
        adverse += 1
    if paused_fwd > allowed_fwd:
        adverse += 1
    if (
        paused_count >= 20
        and allowed_count >= 100
        and math.isfinite(paused_pf)
        and math.isfinite(allowed_pf)
        and paused_pf <= allowed_pf - 0.30
        and paused_breach >= allowed_breach + 0.10
        and paused_fwd >= allowed_fwd + 0.10
        and not conc_flag
    ):
        return "pause_candidate_supported_descriptively"
    if adverse >= 2:
        return "warning_only_descriptively"
    return "no_visible_pause_benefit"


def build_pause_outputs(output_dir: Path = PAUSE_OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trades, meta = load_pause_trade_panel()
    qqq = load_qqq_history()
    panel = add_pause_states(trades, qqq)
    source_rows = [
        {
            "component": "fixed_iv_reference_model",
            "path": repo_relative(ref.DEFAULT_REFERENCE_OUTPUT_DIR),
            "status": "verified",
            "sha256": ref.sha256_file(ref.DEFAULT_REFERENCE_OUTPUT_DIR / "s_single_call_reference_receipt.json"),
            "notes": "Primary S-call outcome source.",
        },
        {
            "component": "realized_dispersion_narrow_leadership",
            "path": "outputs/morita_realized_dispersion_quick_screen/realized_dispersion_signal_context_panel.csv",
            "status": "verified",
            "sha256": ref.sha256_file(REPO_ROOT / "outputs" / "morita_realized_dispersion_quick_screen" / "realized_dispersion_signal_context_panel.csv"),
            "notes": "Narrow leadership state source.",
        },
        {
            "component": "cta_vol_cross_module_daily_panel",
            "path": "outputs/phase1_6b_cross_module_downside/cross_module_daily_panel.csv",
            "status": "verified",
            "sha256": ref.sha256_file(REPO_ROOT / "outputs" / "phase1_6b_cross_module_downside" / "cross_module_daily_panel.csv"),
            "notes": "CTA and Vol-control state source.",
        },
        {
            "component": "qqq_formal_lineage_ohlcv",
            "path": repo_relative(ref.baseline_input_root(ref.DEFAULT_BASELINE_DIR) / "sources" / "daily_ohlcv_merged.csv"),
            "status": "verified",
            "sha256": ref.sha256_file(ref.baseline_input_root(ref.DEFAULT_BASELINE_DIR) / "source_manifest.json"),
            "notes": "QQQ trend and forward risk from formal local lineage.",
        },
    ]
    ref.write_csv(output_dir / "input_source_verification.csv", source_rows, ["component", "path", "status", "sha256", "notes"])
    coverage_rows = []
    impact_rows = []
    risk_rows = []
    concentration_rows = []
    chronological_rows = []
    label_rows = []
    n = len(panel)
    for state in PAUSE_STATES:
        coverage = state_component_coverage(panel, state)
        paused = panel[panel[state].fillna(False).astype(bool)].copy()
        allowed = panel[~panel[state].fillna(False).astype(bool)].copy()
        coverage_rows.append(
            {
                "state": state,
                "eligible_trade_count": n,
                "required_component_coverage": coverage,
                "pause_count": len(paused),
                "allow_count": len(allowed),
                "narrow_available_rate": float(panel["NARROW_LEADERSHIP_ON"].notna().mean()),
                "trend_available_rate": float(panel["QQQ_TREND_BREAK_ON"].notna().mean()),
                "cta_available_rate": float(panel["CTA_AVAILABLE"].mean()),
                "vol_available_rate": float(panel["VOL_AVAILABLE"].mean()),
            }
        )
        groups = [("BASELINE_ALL_SIGNALS", panel), ("PAUSED_SIGNALS_ONLY", paused), ("ALLOW_ONLY_AFTER_PAUSE", allowed)]
        group_stats = {}
        risk_stats = {}
        for group, subset in groups:
            row = pause_group_stats(subset, state, group)
            row["rate"] = len(subset) / n if n else ""
            impact_rows.append(row)
            group_stats[group] = row
            rrow = forward_risk_stats(subset, state, group)
            risk_rows.append(rrow)
            risk_stats[group] = rrow
        conc = concentration(paused.to_dict("records")) if len(paused) else concentration([])
        concentration_rows.append({"state": state, "group": "PAUSED_SIGNALS_ONLY", "unique_dates": int(paused["entry_date"].nunique()), **conc})
        label = label_pause_state(
            group_stats["PAUSED_SIGNALS_ONLY"],
            group_stats["ALLOW_ONLY_AFTER_PAUSE"],
            risk_stats["PAUSED_SIGNALS_ONLY"],
            risk_stats["ALLOW_ONLY_AFTER_PAUSE"],
            bool(conc["concentration_flag"]),
            coverage,
        )
        label_rows.append(
            {
                "state": state,
                "fixed_research_label": label,
                "paused_count": len(paused),
                "allowed_count": len(allowed),
                "required_component_coverage": coverage,
                "concentration_flag": bool(conc["concentration_flag"]),
                "research_only_no_live_pause_action": True,
                "not_a_top_prediction_model": True,
                "not_a_short_signal": True,
            }
        )
        dates = sorted(panel["entry_date"].unique())
        split = (len(dates) + 1) // 2
        early = set(dates[:split])
        for half_name, half_rows in [("early_half", panel[panel["entry_date"].isin(early)]), ("late_half", panel[~panel["entry_date"].isin(early)])]:
            half_paused = half_rows[half_rows[state].fillna(False).astype(bool)]
            half_allowed = half_rows[~half_rows[state].fillna(False).astype(bool)]
            pstats = pause_group_stats(half_paused, state, "paused")
            astats = pause_group_stats(half_allowed, state, "allowed")
            chronological_rows.append(
                {
                    "state": state,
                    "chronological_half": half_name,
                    "pause_count": len(half_paused),
                    "allow_count": len(half_allowed),
                    "paused_TP125_PF": pstats["profit_factor"],
                    "allowed_TP125_PF": astats["profit_factor"],
                    "paused_plus5_rate": pstats["plus5_within_10_rate"],
                    "allowed_plus5_rate": astats["plus5_within_10_rate"],
                    "paused_breakout_low_breach_rate": pstats["breakout_day_low_breach_rate"],
                    "allowed_breakout_low_breach_rate": astats["breakout_day_low_breach_rate"],
                    "paused_FWD20_DD10_incidence": float(half_paused["FWD20_DD10"].fillna(False).mean()) if len(half_paused) else "",
                    "allowed_FWD20_DD10_incidence": float(half_allowed["FWD20_DD10"].fillna(False).mean()) if len(half_allowed) else "",
                }
            )
    ref.write_csv(output_dir / "state_coverage_summary.csv", coverage_rows, list(coverage_rows[0].keys()))
    ref.write_csv(output_dir / "s_pause_strategy_impact.csv", impact_rows, list(impact_rows[0].keys()))
    ref.write_csv(output_dir / "s_pause_market_risk_diagnostic.csv", risk_rows, list(risk_rows[0].keys()))
    ref.write_csv(output_dir / "s_pause_concentration_summary.csv", concentration_rows, list(concentration_rows[0].keys()))
    ref.write_csv(output_dir / "s_pause_chronological_summary.csv", chronological_rows, list(chronological_rows[0].keys()))
    ref.write_csv(output_dir / "s_pause_candidate_labels.csv", label_rows, list(label_rows[0].keys()))
    receipt = {
        "status": "completed",
        "created_at_utc": ref.utc_now(),
        "baseline_run_id": meta["baseline_receipt"].get("run_id", ""),
        "eligible_trade_count": n,
        "formal_sample_start_limitation": "This cannot validate a 2022-scale crash-transition detector. It only measures predeclared conditions within the available formal S sample.",
        "synthetic_fixed_iv_reference_model": True,
        "not_historical_option_fill_reconstruction": True,
        "not_live_execution_estimate": True,
        "research_only_no_live_pause_action": True,
        "not_a_top_prediction_model": True,
        "not_a_short_signal": True,
        "new_market_or_option_data_downloaded": False,
    }
    ref.write_json(output_dir / "call_bot_pause_receipt.json", receipt)
    (output_dir / "call_bot_pause_summary.md").write_text(render_pause_summary(label_rows, impact_rows, risk_rows), encoding="utf-8")
    ref.build_manifest(output_dir, "call_bot_pause_content_manifest.json", PAUSE_REQUIRED_FILES)
    assert_no_actionization(output_dir)
    return receipt


def render_pause_summary(label_rows: list[dict[str, Any]], impact_rows: list[dict[str, Any]], risk_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Morita CALL_BOT_PAUSE Research v1",
        "",
        "synthetic_fixed_iv_reference_model=true",
        "not_historical_option_fill_reconstruction=true",
        "not_live_execution_estimate=true",
        "research_only_no_live_pause_action=true",
        "not_a_top_prediction_model=true",
        "not_a_short_signal=true",
        "",
        "This cannot validate a 2022-scale crash-transition detector. It only measures predeclared conditions within the available formal S sample.",
        "",
        "| State | Paused | Allowed | Coverage | Label |",
        "|---|---:|---:|---:|---|",
    ]
    for row in label_rows:
        lines.append(f"| {row['state']} | {row['paused_count']} | {row['allowed_count']} | {row['required_component_coverage']} | {row['fixed_research_label']} |")
    lines.append("")
    lines.append("No live alert/trading/pause change is made.")
    return "\n".join(lines) + "\n"


def verify_pause_manifest(output_dir: Path = PAUSE_OUTPUT_DIR) -> dict[str, Any]:
    result = ref.verify_manifest(output_dir, "call_bot_pause_content_manifest.json", PAUSE_REQUIRED_FILES)
    assert_no_actionization(output_dir)
    return result

