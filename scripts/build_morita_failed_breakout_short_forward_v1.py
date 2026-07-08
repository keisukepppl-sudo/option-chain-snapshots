from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


POLICY_VERSION = "morita_failed_breakout_short_forward_v1"
DEFAULT_POLICY = Path("config/morita_failed_breakout_short_forward_v1/policy.json")
DEFAULT_OUTPUT_DIR = Path("outputs/morita_failed_breakout_short_forward_v1")
EXPECTED_D_HIGH = 0.1076297441118458
EXPECTED_L_HIGH = 0.0211600633543862
OPTION_MODEL_STATUS = "not_implemented_in_forward_logger_v1"

REQUIRED_OUTPUT_FILES = [
    "failed_breakout_candidate_watchlist.csv",
    "failed_breakout_entry_log.csv",
    "failed_breakout_forward_outcomes.csv",
    "failed_breakout_regime_summary.csv",
    "failed_breakout_rs_bucket_summary.csv",
    "failed_breakout_source_lineage.json",
    "failed_breakout_receipt.json",
    "failed_breakout_content_manifest.json",
    "failed_breakout_summary.md",
]

SAFETY_FLAGS = {
    "research_only": True,
    "no_live_signal": True,
    "no_broker_action": True,
    "no_auto_execution": True,
}

CANDIDATE_COLUMNS = [
    "candidate_id",
    "ticker",
    "decision_date",
    "close",
    "prior_65d_high",
    "breakout_day_low",
    "breakout_day_high",
    "volume",
    "volume_multiple",
    "RS_value",
    "RS_bucket",
    "regime_state",
    "D_value",
    "L_value",
    "D_state",
    "L_state",
    "source_scanner_rule",
    "research_only",
]

ENTRY_COLUMNS = [
    "failed_breakout_id",
    "original_candidate_id",
    "ticker",
    "breakout_decision_date",
    "failure_confirm_date",
    "hypothetical_entry_date",
    "hypothetical_entry_open",
    "RS_value",
    "RS_bucket",
    "regime_state",
    "D_value",
    "L_value",
    "breakout_day_low",
    "breakout_day_high",
    "failure_trigger",
    "diagnostic_intraday_low_breach_before_primary",
    "research_status",
    "option_model_status",
    "no_live_signal",
    "no_broker_action",
    "no_auto_execution",
]

OUTCOME_COLUMNS = [
    "failed_breakout_id",
    "ticker",
    "entry_date",
    "entry_open",
    "outcome_status",
    "outcome_complete_date",
    "underlying_return_5d",
    "underlying_return_10d",
    "underlying_return_20d",
    "reached_minus_5pct_within_10d",
    "reached_minus_8pct_within_10d",
    "reached_minus_10pct_within_10d",
    "reached_minus_15pct_within_20d",
    "max_favorable_excursion_10d",
    "max_favorable_excursion_20d",
    "max_adverse_excursion_10d",
    "max_adverse_excursion_20d",
    "recovered_breakout_high_within_10d",
    "recovered_breakout_high_within_20d",
    "close_above_breakout_high_stop_triggered",
    "first_stop_trigger_date",
    "RS_bucket",
    "regime_state",
    "no_live_signal",
    "no_broker_action",
    "no_auto_execution",
]


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def _float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required_false = [
        "daily_research_summary_enabled",
        "pushover_emergency_enabled",
        "broker_execution_enabled",
        "auto_trade_action_enabled",
        "live_short_signal_enabled",
        "put_alert_enabled",
        "long_s_logic_change_allowed",
        "rank_universe_rule_change_allowed",
        "regime_sizing_policy_change_allowed",
    ]
    if policy.get("policy_version") != POLICY_VERSION or policy.get("mode") != "research_logging_only":
        raise SystemExit("failed_breakout_policy_identity_mismatch")
    for key in required_false:
        if policy.get(key) is not False:
            raise SystemExit(f"failed_breakout_policy_safety_flag_mismatch:{key}")
    verify_threshold_lineage(policy)
    return policy


def verify_threshold_lineage(policy: dict[str, Any]) -> dict[str, float]:
    thresholds = policy.get("regime_thresholds") or {}
    lineage = thresholds.get("threshold_source_lineage") or {}
    d = _float(thresholds.get("D_high_cutoff"))
    l = _float(thresholds.get("L_high_cutoff"))
    if not math.isclose(d, EXPECTED_D_HIGH, rel_tol=0.0, abs_tol=1e-15):
        raise SystemExit("failed_breakout_D_threshold_lineage_mismatch")
    if not math.isclose(l, EXPECTED_L_HIGH, rel_tol=0.0, abs_tol=1e-15):
        raise SystemExit("failed_breakout_L_threshold_lineage_mismatch")
    if lineage.get("expected_D_high_cutoff") != EXPECTED_D_HIGH or lineage.get("expected_L_high_cutoff") != EXPECTED_L_HIGH:
        raise SystemExit("failed_breakout_threshold_lineage_expected_values_missing")
    if lineage.get("source") != "inherited_morita_regime_sizing_overlay":
        raise SystemExit("failed_breakout_threshold_lineage_source_missing")
    return {"D_high_cutoff": d, "L_high_cutoff": l}


def classify_rs_bucket(rs_value: float) -> str:
    rs = float(rs_value)
    if 90.0 <= rs < 96.0:
        return "RS90_95"
    if 96.0 <= rs < 98.0:
        return "RS96_97"
    if rs >= 98.0:
        return "RS98_PLUS"
    return "RS_BELOW_90"


def classify_regime(d_value: float, l_value: float, thresholds: dict[str, float]) -> tuple[str, str, str]:
    d_high = float(d_value) >= thresholds["D_high_cutoff"]
    l_high = float(l_value) >= thresholds["L_high_cutoff"]
    if not d_high:
        return "NORMAL", "D_not_high", "L_high" if l_high else "L_not_high"
    if l_high:
        return "NARROW_LEADERSHIP", "D_high", "L_high"
    return "HIGH_DISPERSION", "D_high", "L_not_high"


def normalize_price_panel(price_panel: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "symbol": "ticker",
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = price_panel.rename(columns={k: v for k, v in aliases.items() if k in price_panel.columns}).copy()
    required = {"ticker", "date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"failed_breakout_price_panel_missing_columns:{sorted(missing)}")
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


def normalize_rs_panel(rs_panel: pd.DataFrame) -> pd.DataFrame:
    df = rs_panel.rename(columns={"symbol": "ticker", "RS": "RS_value", "rs": "RS_value"}).copy()
    if not {"ticker", "date", "RS_value"}.issubset(df.columns):
        raise SystemExit("failed_breakout_rs_panel_missing_columns")
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["RS_value"] = pd.to_numeric(df["RS_value"], errors="coerce")
    return df[["ticker", "date", "RS_value"]]


def normalize_regime_panel(regime_panel: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    df = regime_panel.rename(
        columns={
            "decision_date": "date",
            "D": "D_value",
            "L": "L_value",
            "broad_russell1000_cross_sectional_dispersion_20d": "D_value",
            "broad_russell1000_qqq_minus_eqw_return_20d": "L_value",
        }
    ).copy()
    if not {"date", "D_value", "L_value"}.issubset(df.columns):
        raise SystemExit("failed_breakout_regime_panel_missing_columns")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["D_value"] = pd.to_numeric(df["D_value"], errors="coerce")
    df["L_value"] = pd.to_numeric(df["L_value"], errors="coerce")
    states = [classify_regime(d, l, thresholds) for d, l in zip(df["D_value"], df["L_value"])]
    df["regime_state"] = [s[0] for s in states]
    df["D_state"] = [s[1] for s in states]
    df["L_state"] = [s[2] for s in states]
    return df[["date", "D_value", "L_value", "regime_state", "D_state", "L_state"]]


def build_breakout_candidates(
    price_panel: pd.DataFrame,
    rs_panel: pd.DataFrame,
    regime_panel: pd.DataFrame,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    thresholds = verify_threshold_lineage(policy)
    prices = normalize_price_panel(price_panel)
    rs = normalize_rs_panel(rs_panel)
    regimes = normalize_regime_panel(regime_panel, thresholds)
    rule = policy["breakout_rule"]
    lookback = int(rule["prior_high_lookback_sessions"])
    volume_lookback = int(rule["volume_lookback_sessions"])
    volume_min = float(rule["volume_multiple_min"])
    rs_map = {(r.ticker, r.date): r.RS_value for r in rs.itertuples(index=False)}
    regime_map = {r.date: r for r in regimes.itertuples(index=False)}
    rows: list[dict[str, Any]] = []
    for ticker, group in prices.groupby("ticker", sort=True):
        group = group.reset_index(drop=True)
        for idx in range(lookback, len(group)):
            row = group.iloc[idx]
            date = str(row["date"])
            reg = regime_map.get(date)
            if reg is None or reg.regime_state == "NORMAL":
                continue
            rs_value = rs_map.get((ticker, date), math.nan)
            bucket = classify_rs_bucket(_float(rs_value))
            if bucket == "RS_BELOW_90":
                continue
            prior = group.iloc[idx - lookback : idx]
            prior_high = float(prior["high"].max())
            close = float(row["close"])
            avg_volume = float(group.iloc[max(0, idx - volume_lookback + 1) : idx + 1]["volume"].mean())
            volume_multiple = _float(row["volume"]) / avg_volume if avg_volume > 0 else math.nan
            if close > prior_high and pd.notna(volume_multiple) and volume_multiple >= volume_min:
                rows.append(
                    {
                        "candidate_id": f"{ticker}_{date}_FBW",
                        "ticker": ticker,
                        "decision_date": date,
                        "close": close,
                        "prior_65d_high": prior_high,
                        "breakout_day_low": float(row["low"]),
                        "breakout_day_high": float(row["high"]),
                        "volume": float(row["volume"]),
                        "volume_multiple": volume_multiple,
                        "RS_value": float(rs_value),
                        "RS_bucket": bucket,
                        "regime_state": reg.regime_state,
                        "D_value": float(reg.D_value),
                        "L_value": float(reg.L_value),
                        "D_state": reg.D_state,
                        "L_state": reg.L_state,
                        "source_scanner_rule": str(rule["source_scanner_rule"]),
                        "research_only": True,
                    }
                )
    return rows


def build_failed_breakout_entries(candidates: list[dict[str, Any]], price_panel: pd.DataFrame, policy: dict[str, Any]) -> list[dict[str, Any]]:
    prices = normalize_price_panel(price_panel)
    tracking = int(policy["failure_rule"]["tracking_sessions_after_breakout"])
    entries: list[dict[str, Any]] = []
    by_ticker = {ticker: group.reset_index(drop=True) for ticker, group in prices.groupby("ticker", sort=True)}
    for cand in candidates:
        ticker = str(cand["ticker"])
        group = by_ticker.get(ticker)
        if group is None:
            continue
        matches = group.index[group["date"].eq(str(cand["decision_date"]))].tolist()
        if not matches:
            continue
        start = matches[0]
        window = group.iloc[start + 1 : start + 1 + tracking]
        diagnostic_seen = bool((window["low"] < float(cand["breakout_day_low"])).any())
        failed = window[window["close"] < float(cand["breakout_day_low"])]
        if failed.empty:
            continue
        fail_idx = int(failed.index[0])
        entry_idx = fail_idx + 1
        if entry_idx >= len(group):
            continue
        entry_row = group.iloc[entry_idx]
        failure_date = str(group.loc[fail_idx, "date"])
        failed_id = f"FB_{ticker}_{failure_date}"
        entries.append(
            {
                "failed_breakout_id": failed_id,
                "original_candidate_id": cand["candidate_id"],
                "ticker": ticker,
                "breakout_decision_date": cand["decision_date"],
                "failure_confirm_date": failure_date,
                "hypothetical_entry_date": str(entry_row["date"]),
                "hypothetical_entry_open": float(entry_row["open"]),
                "RS_value": cand["RS_value"],
                "RS_bucket": cand["RS_bucket"],
                "regime_state": cand["regime_state"],
                "D_value": cand["D_value"],
                "L_value": cand["L_value"],
                "breakout_day_low": cand["breakout_day_low"],
                "breakout_day_high": cand["breakout_day_high"],
                "failure_trigger": "close_below_breakout_day_low",
                "diagnostic_intraday_low_breach_before_primary": diagnostic_seen,
                "research_status": "forward_research_only",
                "option_model_status": OPTION_MODEL_STATUS,
                "no_live_signal": True,
                "no_broker_action": True,
                "no_auto_execution": True,
            }
        )
    return entries


def _horizon_close(group: pd.DataFrame, entry_idx: int, horizon: int) -> tuple[str, float] | tuple[str, float]:
    target_idx = entry_idx + horizon
    if target_idx >= len(group):
        return "", math.nan
    row = group.iloc[target_idx]
    return str(row["date"]), float(row["close"])


def _bool(value: bool) -> bool:
    return bool(value)


def build_forward_outcomes(entries: list[dict[str, Any]], price_panel: pd.DataFrame) -> list[dict[str, Any]]:
    prices = normalize_price_panel(price_panel)
    by_ticker = {ticker: group.reset_index(drop=True) for ticker, group in prices.groupby("ticker", sort=True)}
    outcomes: list[dict[str, Any]] = []
    for entry in entries:
        ticker = str(entry["ticker"])
        group = by_ticker.get(ticker)
        if group is None:
            continue
        matches = group.index[group["date"].eq(str(entry["hypothetical_entry_date"]))].tolist()
        if not matches:
            continue
        entry_idx = matches[0]
        entry_open = float(entry["hypothetical_entry_open"])
        dates_closes = {h: _horizon_close(group, entry_idx, h) for h in [5, 10, 20]}
        max_complete = max([h for h, pair in dates_closes.items() if pair[0]] or [0])
        complete_date = dates_closes.get(20, ("", math.nan))[0] or dates_closes.get(10, ("", math.nan))[0] or dates_closes.get(5, ("", math.nan))[0]
        w10 = group.iloc[entry_idx + 1 : min(len(group), entry_idx + 11)]
        w20 = group.iloc[entry_idx + 1 : min(len(group), entry_idx + 21)]
        min_low_10 = float(w10["low"].min()) if not w10.empty else math.nan
        min_low_20 = float(w20["low"].min()) if not w20.empty else math.nan
        max_high_10 = float(w10["high"].max()) if not w10.empty else math.nan
        max_high_20 = float(w20["high"].max()) if not w20.empty else math.nan
        close_stop_rows = w20[w20["close"] > float(entry["breakout_day_high"])] if not w20.empty else pd.DataFrame()
        outcomes.append(
            {
                "failed_breakout_id": entry["failed_breakout_id"],
                "ticker": ticker,
                "entry_date": entry["hypothetical_entry_date"],
                "entry_open": entry_open,
                "outcome_status": "complete" if max_complete >= 20 else f"pending_{max_complete}d",
                "outcome_complete_date": complete_date,
                "underlying_return_5d": dates_closes[5][1] / entry_open - 1.0 if dates_closes[5][0] else math.nan,
                "underlying_return_10d": dates_closes[10][1] / entry_open - 1.0 if dates_closes[10][0] else math.nan,
                "underlying_return_20d": dates_closes[20][1] / entry_open - 1.0 if dates_closes[20][0] else math.nan,
                "reached_minus_5pct_within_10d": _bool(pd.notna(min_low_10) and min_low_10 <= entry_open * 0.95),
                "reached_minus_8pct_within_10d": _bool(pd.notna(min_low_10) and min_low_10 <= entry_open * 0.92),
                "reached_minus_10pct_within_10d": _bool(pd.notna(min_low_10) and min_low_10 <= entry_open * 0.90),
                "reached_minus_15pct_within_20d": _bool(pd.notna(min_low_20) and min_low_20 <= entry_open * 0.85),
                "max_favorable_excursion_10d": (entry_open - min_low_10) / entry_open if pd.notna(min_low_10) else math.nan,
                "max_favorable_excursion_20d": (entry_open - min_low_20) / entry_open if pd.notna(min_low_20) else math.nan,
                "max_adverse_excursion_10d": max(0.0, (max_high_10 - entry_open) / entry_open) if pd.notna(max_high_10) else math.nan,
                "max_adverse_excursion_20d": max(0.0, (max_high_20 - entry_open) / entry_open) if pd.notna(max_high_20) else math.nan,
                "recovered_breakout_high_within_10d": _bool((not w10.empty) and (w10["close"] >= float(entry["breakout_day_high"])).any()),
                "recovered_breakout_high_within_20d": _bool((not w20.empty) and (w20["close"] >= float(entry["breakout_day_high"])).any()),
                "close_above_breakout_high_stop_triggered": _bool(not close_stop_rows.empty),
                "first_stop_trigger_date": "" if close_stop_rows.empty else str(close_stop_rows.iloc[0]["date"]),
                "RS_bucket": entry["RS_bucket"],
                "regime_state": entry["regime_state"],
                "no_live_signal": True,
                "no_broker_action": True,
                "no_auto_execution": True,
            }
        )
    return outcomes


def _summary_counts(rows: list[dict[str, Any]], keys: list[str], count_name: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    grouped = df.groupby(keys, dropna=False).size().reset_index(name=count_name)
    for flag, value in SAFETY_FLAGS.items():
        if flag != "research_only":
            grouped[flag] = value
    return grouped.to_dict("records")


def build_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUT_FILES:
        if name == "failed_breakout_content_manifest.json":
            continue
        path = output_dir / name
        if not path.exists():
            raise SystemExit(f"failed_breakout_manifest_missing_required_file:{name}")
        files.append({"relative_path": name, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    payload = {"policy_version": POLICY_VERSION, "required_files": REQUIRED_OUTPUT_FILES, "files": files}
    payload["content_set_hash"] = text_hash(json_dumps(files))
    return payload


def verify_output_manifest(output_dir: Path) -> dict[str, Any]:
    expected = set(REQUIRED_OUTPUT_FILES)
    actual = {p.name for p in output_dir.iterdir() if p.is_file()}
    if actual != expected:
        raise SystemExit(f"failed_breakout_manifest_file_set_mismatch:{sorted(actual ^ expected)}")
    manifest = json.loads((output_dir / "failed_breakout_content_manifest.json").read_text(encoding="utf-8"))
    rebuilt = build_manifest(output_dir)
    if manifest.get("content_set_hash") != rebuilt.get("content_set_hash"):
        raise SystemExit("failed_breakout_manifest_hash_mismatch")
    return manifest


def build_forward_logger(
    price_panel: pd.DataFrame,
    rs_panel: pd.DataFrame,
    regime_panel: pd.DataFrame,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    thresholds = verify_threshold_lineage(policy)
    candidates = build_breakout_candidates(price_panel, rs_panel, regime_panel, policy)
    entries = build_failed_breakout_entries(candidates, price_panel, policy)
    outcomes = build_forward_outcomes(entries, price_panel)
    regime_summary = _summary_counts(candidates, ["regime_state", "RS_bucket"], "breakout_candidate_count")
    bucket_summary = _summary_counts(entries, ["RS_bucket", "regime_state"], "failed_breakout_entry_count")
    lineage = {
        "policy_version": POLICY_VERSION,
        "RS_source": "caller_supplied_rs_panel",
        "breakout_source": policy["breakout_rule"]["source_scanner_rule"],
        "regime_thresholds": thresholds,
        "regime_threshold_lineage": policy["regime_thresholds"]["threshold_source_lineage"],
        "option_model_status": OPTION_MODEL_STATUS,
        **SAFETY_FLAGS,
    }
    receipt = {
        "run_status": "failed_breakout_forward_logger_completed",
        "breakout_candidate_count": len(candidates),
        "failed_breakout_entry_count": len(entries),
        "forward_outcome_count": len(outcomes),
        "output_dir": repo_relative(output_dir),
        "D_high_cutoff": thresholds["D_high_cutoff"],
        "L_high_cutoff": thresholds["L_high_cutoff"],
        "option_model_status": OPTION_MODEL_STATUS,
        **SAFETY_FLAGS,
    }

    write_csv(output_dir / "failed_breakout_candidate_watchlist.csv", candidates, CANDIDATE_COLUMNS)
    write_csv(output_dir / "failed_breakout_entry_log.csv", entries, ENTRY_COLUMNS)
    write_csv(output_dir / "failed_breakout_forward_outcomes.csv", outcomes, OUTCOME_COLUMNS)
    write_csv(output_dir / "failed_breakout_regime_summary.csv", regime_summary, ["regime_state", "RS_bucket", "breakout_candidate_count", "no_live_signal", "no_broker_action", "no_auto_execution"])
    write_csv(output_dir / "failed_breakout_rs_bucket_summary.csv", bucket_summary, ["RS_bucket", "regime_state", "failed_breakout_entry_count", "no_live_signal", "no_broker_action", "no_auto_execution"])
    write_json(output_dir / "failed_breakout_source_lineage.json", lineage)
    write_json(output_dir / "failed_breakout_receipt.json", receipt)
    (output_dir / "failed_breakout_summary.md").write_text(
        "# Failed Breakout Short Forward Logger v1\n\n"
        f"Research candidates logged: `{len(candidates)}`. Failed-breakout research entries logged: `{len(entries)}`.\n\n"
        "This module is forward logging only. It does not activate live signals, put alerts, broker access, account access, order creation, or automatic execution.\n",
        encoding="utf-8",
    )
    write_json(output_dir / "failed_breakout_content_manifest.json", build_manifest(output_dir))
    verify_output_manifest(output_dir)
    return receipt


def _load_csv(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    return pd.read_csv(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-panel", required=True)
    parser.add_argument("--rs-panel", required=True)
    parser.add_argument("--regime-panel", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    args = parser.parse_args()
    receipt = build_forward_logger(_load_csv(args.price_panel), _load_csv(args.rs_panel), _load_csv(args.regime_panel), Path(args.output_dir), Path(args.policy))
    print(json_dumps(receipt))


if __name__ == "__main__":
    main()
