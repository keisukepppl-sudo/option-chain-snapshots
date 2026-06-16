from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd


TRADE_LOG_COLUMNS = [
    "log_created_at_jst",
    "timestamp_jst",
    "schedule_utc",
    "entry_status",
    "ticker",
    "company_name",
    "alert_price",
    "prior_20d_high",
    "breakout_pct",
    "rs_score",
    "volume_multiple",
    "rank",
    "score",
    "sector",
    "theme",
    "market_cap",
    "market_cap_bucket",
    "gap_pct",
    "option_iv",
    "option_liquidity_warning",
    "suggested_contract",
    "dte",
    "long_strike",
    "short_strike",
    "mid_price",
    "bid",
    "ask",
    "spread_pct",
    "day10_target_price",
    "profit_target_pct",
    "exit_rule",
    "manual_entry_datetime_jst",
    "manual_entry_price",
    "contracts",
    "account_size",
    "position_pct",
    "day1_close",
    "day3_close",
    "day5_close",
    "day10_close",
    "max_high_10d",
    "achieved_plus5pct",
    "exit_datetime",
    "exit_price",
    "pnl_pct",
    "pnl_jpy",
    "result_notes",
]

LOG_RANKS = ["S", "A", "B", "C"]


def _safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    return str(value)


def _get(row: pd.Series, *names: str, default: Any = "") -> Any:
    for name in names:
        if name in row.index:
            value = row.get(name)
            try:
                if value is not None and not pd.isna(value):
                    return value
            except Exception:
                if value is not None:
                    return value
    return default


def _breakout_pct(price: float, prior_high: float) -> float:
    if pd.notna(price) and pd.notna(prior_high) and prior_high > 0:
        return price / prior_high - 1.0
    return math.nan


def _spread_pct(bid: float, ask: float, mid: float) -> float:
    if pd.notna(bid) and pd.notna(ask) and pd.notna(mid) and mid > 0:
        return (ask - bid) / mid
    return math.nan


def _suggested_contract(row: pd.Series) -> str:
    existing = _safe_str(_get(row, "suggested_contract", "contract", default=""))
    if existing:
        return existing
    long_strike = _get(row, "long_strike", "atm_strike", default="")
    short_strike = _get(row, "short_strike", default="")
    dte = _get(row, "dte", "target_dte", default="60")
    if long_strike != "" and short_strike != "":
        return f"{dte}DTE {long_strike}/{short_strike} call vertical"
    return "60DTE ATM/+10% call vertical"


def _row_to_log(row: pd.Series, timestamp_jst: str, schedule_utc: str) -> dict[str, Any]:
    price = _safe_float(_get(row, "latest_price", "close", "price", default=math.nan))
    prior_high = _safe_float(_get(row, "prior_20d_high", "twenty_day_high", default=math.nan))
    score = _safe_float(_get(row, "production_adjusted_score", "adjusted_score", "score", default=math.nan))
    bid = _safe_float(_get(row, "vertical_bid", "bid", "option_bid", default=math.nan))
    ask = _safe_float(_get(row, "vertical_ask", "ask", "option_ask", default=math.nan))
    mid = _safe_float(_get(row, "vertical_mid", "mid_price", "mid", "option_mid", default=math.nan))
    if pd.isna(mid) and pd.notna(bid) and pd.notna(ask):
        mid = (bid + ask) / 2.0
    breakout = _safe_float(_get(row, "breakout_pct", default=math.nan))
    if pd.isna(breakout):
        breakout = _breakout_pct(price, prior_high)

    out = {
        "log_created_at_jst": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(),
        "timestamp_jst": timestamp_jst,
        "schedule_utc": schedule_utc,
        "entry_status": "alert_only",
        "ticker": _safe_str(_get(row, "ticker", default="")),
        "company_name": _safe_str(_get(row, "company_name", "name", default="")),
        "alert_price": price,
        "prior_20d_high": prior_high,
        "breakout_pct": breakout,
        "rs_score": _safe_float(_get(row, "standard_rs_score", "rs", default=math.nan)),
        "volume_multiple": _safe_float(_get(row, "volume_multiple", default=math.nan)),
        "rank": _safe_str(_get(row, "alert_rank", "production_rank", "rank", default="")),
        "score": score,
        "sector": _safe_str(_get(row, "sector_proxy", "source_sector", "sector", default="")),
        "theme": _safe_str(_get(row, "theme", default="")),
        "market_cap": _safe_float(_get(row, "market_cap", default=math.nan)),
        "market_cap_bucket": _safe_str(_get(row, "market_cap_bucket", default="")),
        "gap_pct": _safe_float(_get(row, "gap_pct", default=math.nan)),
        "option_iv": _safe_float(_get(row, "option_iv", default=math.nan)),
        "option_liquidity_warning": _safe_str(_get(row, "option_liquidity_warning", "option_liquidity_reason", default="")),
        "suggested_contract": _suggested_contract(row),
        "dte": _get(row, "dte", "target_dte", default="60"),
        "long_strike": _get(row, "long_strike", "atm_strike", default=""),
        "short_strike": _get(row, "short_strike", default=""),
        "mid_price": mid,
        "bid": bid,
        "ask": ask,
        "spread_pct": _spread_pct(bid, ask, mid),
        "day10_target_price": price * 1.05 if pd.notna(price) else math.nan,
        "profit_target_pct": 100,
        "exit_rule": "Day10 underlying +5% not reached -> exit; +100%/+125% profit target -> take profit",
        "manual_entry_datetime_jst": "",
        "manual_entry_price": "",
        "contracts": "",
        "account_size": "",
        "position_pct": "",
        "day1_close": "",
        "day3_close": "",
        "day5_close": "",
        "day10_close": "",
        "max_high_10d": "",
        "achieved_plus5pct": "",
        "exit_datetime": "",
        "exit_price": "",
        "pnl_pct": "",
        "pnl_jpy": "",
        "result_notes": "",
    }
    return {column: out.get(column, "") for column in TRADE_LOG_COLUMNS}


def append_alert_log(candidates: pd.DataFrame, outdir: Path, schedule_utc: str = "") -> Path:
    """Append S/A/B/C breakout alerts to scanner_alerts/trade_log.csv with de-duplication."""
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir.parent / "trade_log.csv"
    daily_path = outdir / "trade_log_snapshot.csv"
    timestamp_jst = pd.Timestamp.now(tz="Asia/Tokyo").isoformat()

    if candidates.empty:
        existing = pd.DataFrame(columns=TRADE_LOG_COLUMNS)
        if log_path.exists():
            existing = pd.read_csv(log_path)
        existing.to_csv(daily_path, index=False)
        print("Trade log updated: 0 new rows", flush=True)
        return log_path

    visible = candidates.copy()
    if "exclusion_reason" in visible.columns:
        visible = visible[visible["exclusion_reason"].fillna("") == ""]
    if "alert_rank" in visible.columns:
        visible = visible[visible["alert_rank"].isin(LOG_RANKS)]

    new_rows = [_row_to_log(row, timestamp_jst, schedule_utc) for _, row in visible.iterrows()]
    new_df = pd.DataFrame(new_rows, columns=TRADE_LOG_COLUMNS)

    if log_path.exists():
        old_df = pd.read_csv(log_path)
    else:
        old_df = pd.DataFrame(columns=TRADE_LOG_COLUMNS)
    for column in TRADE_LOG_COLUMNS:
        if column not in old_df.columns:
            old_df[column] = ""
    old_df = old_df[TRADE_LOG_COLUMNS]

    combined = pd.concat([old_df, new_df], ignore_index=True)
    if not combined.empty:
        combined["_dedupe_key"] = (
            combined["timestamp_jst"].astype(str).str[:10]
            + "|" + combined["schedule_utc"].astype(str)
            + "|" + combined["ticker"].astype(str)
            + "|" + combined["rank"].astype(str)
        )
        combined = combined.drop_duplicates("_dedupe_key", keep="first").drop(columns=["_dedupe_key"])
    combined.to_csv(log_path, index=False)
    combined.to_csv(daily_path, index=False)
    print(f"Trade log updated: {len(new_df)} new rows / {len(combined)} total rows", flush=True)
    return log_path
