from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

import pandas as pd


POLICY_VERSION = "morita_material_spike_put_vertical_v1"
DEFAULT_POLICY = Path("config/morita_material_spike_put_vertical_v1/policy.json")
DEFAULT_OUTPUT_DIR = Path("outputs/morita_material_spike_put_vertical_v1")
MODEL_STATUS = "synthetic_fixed_iv_not_historical_option_fill_reconstruction"

REQUIRED_OUTPUT_FILES = [
    "material_spike_candidate_panel.csv",
    "material_spike_failure_entry_log.csv",
    "material_spike_underlying_outcomes.csv",
    "material_spike_put_vertical_reference.csv",
    "material_spike_bucket_summary.csv",
    "material_spike_source_lineage.json",
    "material_spike_receipt.json",
    "material_spike_content_manifest.json",
    "material_spike_summary.md",
]

SAFETY_FLAGS = {
    "research_only": True,
    "no_live_signal": True,
    "no_broker_action": True,
    "no_auto_execution": True,
    "not_historical_option_fill_reconstruction": True,
}

CANDIDATE_COLUMNS = [
    "candidate_id",
    "signal_date",
    "ticker",
    "close",
    "prior_high",
    "volume_multiple",
    "gap_pct",
    "signal_date_return",
    "breakout_excess_pct",
    "standard_rs_score",
    "production_adjusted_score",
    "accumulation_score",
    "theme",
    "d0_low_risk_width_pct",
    "market_cap_at_signal",
    "price_bucket",
    "market_cap_bucket",
    "option_liquidity_available",
    "option_bid_ask_proxy",
    "catalyst_type",
    "catalyst_strength_label",
    "material_spike_label",
    "is_material_spike_candidate",
    "is_extreme_material_spike_candidate",
    "research_only",
    "no_live_signal",
    "no_broker_action",
    "no_auto_execution",
]

ENTRY_COLUMNS = [
    "failure_entry_id",
    "candidate_id",
    "ticker",
    "signal_date",
    "failure_rule",
    "failure_confirm_date",
    "entry_date",
    "entry_open",
    "D0_high",
    "D0_low",
    "D0_close",
    "D0_volume",
    "breakout_level",
    "market_cap_bucket",
    "price_bucket",
    "catalyst_strength_label",
    "material_spike_label",
    "theme",
    "research_status",
    "no_live_signal",
    "no_broker_action",
    "no_auto_execution",
]

UNDERLYING_COLUMNS = [
    "failure_entry_id",
    "ticker",
    "entry_date",
    "entry_open",
    "forward_3d_return",
    "forward_5d_return",
    "forward_10d_return",
    "forward_15d_return",
    "target_down_5pct_within_5d",
    "target_down_8pct_within_10d",
    "target_down_10pct_within_15d",
    "adverse_up_5pct_before_target",
    "adverse_close_above_D0_high_before_exit",
    "MFE_down_5d",
    "MFE_down_10d",
    "MFE_down_15d",
    "MAE_up_5d",
    "MAE_up_10d",
    "MAE_up_15d",
    "no_live_signal",
    "no_broker_action",
    "no_auto_execution",
]

VERTICAL_COLUMNS = [
    "failure_entry_id",
    "ticker",
    "exit_policy",
    "iv_scenario",
    "post_catalyst_iv_crush",
    "model_status",
    "entry_date",
    "entry_open",
    "buy_put_delta",
    "sell_put_delta",
    "buy_put_strike",
    "sell_put_strike",
    "spread_debit",
    "exit_date",
    "exit_underlying_price",
    "exit_value",
    "vertical_return",
    "exit_reason",
    "holding_sessions",
    "no_live_signal",
    "no_broker_action",
    "no_auto_execution",
]


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


def _float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _str(value: Any, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    return str(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raw = _str(value).strip().lower()
    return raw in {"1", "true", "yes", "y"}


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("policy_version") != POLICY_VERSION or policy.get("mode") != "research_only":
        raise SystemExit("material_spike_policy_identity_mismatch")
    for key in [
        "broker_execution_enabled",
        "auto_trade_action_enabled",
        "live_signal_enabled",
        "rank_change_allowed",
        "sizing_change_allowed",
        "notification_change_allowed",
        "existing_morita_behavior_change_allowed",
        "future_leakage_allowed",
    ]:
        if policy.get(key) is not False:
            raise SystemExit(f"material_spike_policy_safety_flag_mismatch:{key}")
    model = policy.get("put_vertical_reference_model") or {}
    if model.get("model_status") != MODEL_STATUS:
        raise SystemExit("material_spike_option_model_status_mismatch")
    return policy


def normalize_price_panel(price_panel: pd.DataFrame) -> pd.DataFrame:
    aliases = {"symbol": "ticker", "Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    df = price_panel.rename(columns={k: v for k, v in aliases.items() if k in price_panel.columns}).copy()
    required = {"ticker", "date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"material_spike_price_panel_missing_columns:{sorted(missing)}")
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


def normalize_baseline_panel(panel: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "decision_date": "signal_date",
        "symbol": "ticker",
        "latest_price": "close",
        "prior_65d_high": "prior_high",
        "prior_20d_high": "prior_high",
        "gap_pct_value": "gap_pct",
        "market_cap": "market_cap_at_signal",
        "RS": "standard_rs_score",
    }
    df = panel.rename(columns={k: v for k, v in aliases.items() if k in panel.columns}).copy()
    required = {"signal_date", "ticker", "close", "prior_high"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"material_spike_baseline_missing_columns:{sorted(missing)}")
    df["signal_date"] = pd.to_datetime(df["signal_date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = df["ticker"].astype(str).str.upper()
    for col in [
        "close",
        "prior_high",
        "volume_multiple",
        "gap_pct",
        "signal_date_return",
        "breakout_excess_pct",
        "standard_rs_score",
        "production_adjusted_score",
        "accumulation_score",
        "d0_low_risk_width_pct",
        "market_cap_at_signal",
        "option_bid_ask_proxy",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "breakout_excess_pct" not in df.columns:
        df["breakout_excess_pct"] = df["close"] / df["prior_high"] - 1.0
    return df


def market_cap_bucket(value: float) -> str:
    cap = _float(value)
    if pd.isna(cap):
        return "UNKNOWN"
    if cap < 300_000_000:
        return "MICRO_LT_300M"
    if cap < 2_000_000_000:
        return "SMALL_300M_2B"
    if cap < 10_000_000_000:
        return "SMALL_MID_2B_10B"
    if cap < 20_000_000_000:
        return "MID_10B_20B"
    return "LARGE_GT_20B"


def price_bucket(value: float) -> str:
    price = _float(value)
    if pd.isna(price):
        return "UNKNOWN"
    if 5 <= price < 10:
        return "5_10"
    if 10 <= price < 20:
        return "10_20"
    if 20 <= price < 50:
        return "20_50"
    if price >= 50:
        return "GT_50"
    return "LT_5"


def gap_bucket(value: float) -> str:
    gap = _float(value)
    if pd.isna(gap):
        return "UNKNOWN"
    if gap < 0.05:
        return "gap_0_5"
    if gap < 0.10:
        return "gap_5_10"
    if gap < 0.20:
        return "gap_10_20"
    return "gap_GT_20"


def volume_multiple_bucket(value: float) -> str:
    vol = _float(value)
    if pd.isna(vol):
        return "UNKNOWN"
    if vol < 1.2:
        return "vol_LT_1_2"
    if vol < 2:
        return "vol_1_2_2"
    if vol < 3:
        return "vol_2_3"
    if vol < 5:
        return "vol_3_5"
    return "vol_GT_5"


def normalize_catalyst_type(value: Any) -> str:
    raw = _str(value, "unknown_news_proxy").strip().lower()
    allowed = {
        "earnings_or_guidance",
        "contract_award",
        "partnership",
        "product_launch",
        "analyst_upgrade",
        "financing",
        "regulatory",
        "ai_pr_or_theme_pr",
        "unknown_news_proxy",
    }
    mapped = {
        "earnings": "earnings_or_guidance",
        "guidance": "earnings_or_guidance",
        "contract": "contract_award",
        "contract_partnership": "contract_award",
        "ai_semiconductor_theme": "ai_pr_or_theme_pr",
        "unknown": "unknown_news_proxy",
    }.get(raw, raw)
    return mapped if mapped in allowed else "unknown_news_proxy"


def catalyst_strength_label(row: pd.Series) -> str:
    explicit = _str(row.get("catalyst_strength_label"), "").strip().upper()
    if explicit in {"FUNDAMENTAL_STRONG", "PR_WEAK", "UNKNOWN"}:
        return explicit
    ctype = normalize_catalyst_type(row.get("catalyst_type"))
    if ctype in {"earnings_or_guidance", "contract_award"}:
        return "FUNDAMENTAL_STRONG"
    if ctype in {"partnership", "product_launch", "ai_pr_or_theme_pr", "financing"}:
        return "PR_WEAK"
    return "UNKNOWN"


def material_spike_flags(row: pd.Series, policy: dict[str, Any]) -> tuple[bool, bool, str]:
    proxy = policy["material_spike_proxy"]
    gap = _float(row.get("gap_pct"))
    ret = _float(row.get("signal_date_return"))
    vol = _float(row.get("volume_multiple"))
    excess = _float(row.get("breakout_excess_pct"))
    base = proxy["candidate_material_spike"]
    extreme = proxy["candidate_extreme_material_spike"]
    is_extreme = (
        (pd.notna(gap) and gap >= extreme["gap_pct_min"])
        or (pd.notna(ret) and ret >= extreme["signal_date_return_min"])
        or (pd.notna(vol) and vol >= extreme["volume_multiple_min"])
    )
    is_material = is_extreme or (
        (pd.notna(gap) and gap >= base["gap_pct_min"])
        or (pd.notna(ret) and ret >= base["signal_date_return_min"])
        or (pd.notna(vol) and vol >= base["volume_multiple_min"])
        or (pd.notna(excess) and excess >= base["breakout_excess_pct_min"])
    )
    label = "CANDIDATE_EXTREME_MATERIAL_SPIKE" if is_extreme else ("CANDIDATE_MATERIAL_SPIKE" if is_material else "NOT_MATERIAL_SPIKE")
    return is_material, is_extreme, label


def build_candidate_panel(baseline_panel: pd.DataFrame, policy: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = normalize_baseline_panel(baseline_panel)
    rows: list[dict[str, Any]] = []
    for _, row in baseline.iterrows():
        is_material, is_extreme, material_label = material_spike_flags(row, policy)
        ctype = normalize_catalyst_type(row.get("catalyst_type"))
        strength = catalyst_strength_label(row)
        out = {
            "candidate_id": f"{row['ticker']}_{row['signal_date']}_MSPV",
            "signal_date": row["signal_date"],
            "ticker": row["ticker"],
            "close": _float(row.get("close")),
            "prior_high": _float(row.get("prior_high")),
            "volume_multiple": _float(row.get("volume_multiple")),
            "gap_pct": _float(row.get("gap_pct")),
            "signal_date_return": _float(row.get("signal_date_return")),
            "breakout_excess_pct": _float(row.get("breakout_excess_pct")),
            "standard_rs_score": _float(row.get("standard_rs_score")),
            "production_adjusted_score": _float(row.get("production_adjusted_score")),
            "accumulation_score": _float(row.get("accumulation_score")),
            "theme": _str(row.get("theme"), "UNKNOWN"),
            "d0_low_risk_width_pct": _float(row.get("d0_low_risk_width_pct")),
            "market_cap_at_signal": _float(row.get("market_cap_at_signal")),
            "price_bucket": price_bucket(_float(row.get("close"))),
            "market_cap_bucket": market_cap_bucket(_float(row.get("market_cap_at_signal"))),
            "option_liquidity_available": _bool(row.get("option_liquidity_available")) if "option_liquidity_available" in row else False,
            "option_bid_ask_proxy": _float(row.get("option_bid_ask_proxy")),
            "catalyst_type": ctype,
            "catalyst_strength_label": strength,
            "material_spike_label": material_label,
            "is_material_spike_candidate": is_material,
            "is_extreme_material_spike_candidate": is_extreme,
            **SAFETY_FLAGS,
        }
        rows.append(out)
    return rows


def _price_context(candidate: dict[str, Any], prices: pd.DataFrame) -> tuple[pd.DataFrame, int] | tuple[None, None]:
    group = prices[prices["ticker"].eq(candidate["ticker"])].reset_index(drop=True)
    matches = group.index[group["date"].eq(str(candidate["signal_date"]))].tolist()
    if not matches:
        return None, None
    return group, int(matches[0])


def _lower_highs_lower_closes(window: pd.DataFrame, pos: int) -> bool:
    if pos < 1:
        return False
    cur = window.iloc[pos]
    prev = window.iloc[pos - 1]
    return bool(cur["high"] < prev["high"] and cur["close"] < prev["close"])


def _failure_matches(candidate: dict[str, Any], group: pd.DataFrame, d0_idx: int, policy: dict[str, Any]) -> list[tuple[str, int]]:
    d0 = group.iloc[d0_idx]
    tracking = int(policy["failure_window_sessions"])
    window = group.iloc[d0_idx + 1 : d0_idx + 1 + tracking].reset_index()
    if window.empty:
        return []
    d0_high = float(d0["high"])
    d0_low = float(d0["low"])
    d0_close = float(d0["close"])
    d0_mid = (d0_high + d0_low) / 2.0
    d0_volume = float(d0["volume"])
    breakout_level = float(candidate["prior_high"])
    matches: dict[str, int] = {}
    for pos, row in window.iterrows():
        original_idx = int(row["index"])
        prior_day_low = float(group.iloc[original_idx - 1]["low"])
        close = float(row["close"])
        high_not_updated_to_date = bool((group.iloc[d0_idx + 1 : original_idx + 1]["close"] <= d0_high).all())
        if high_not_updated_to_date and close < d0_close:
            matches.setdefault("F1_no_close_update_D0_high_and_close_below_D0_close", original_idx)
        if close < breakout_level:
            matches.setdefault("F2_close_below_breakout_level", original_idx)
        if close < d0_mid and float(row["volume"]) < d0_volume * 0.60:
            matches.setdefault("F3_close_below_D0_mid_volume_fade", original_idx)
        if close < prior_day_low and high_not_updated_to_date:
            matches.setdefault("F4_close_below_previous_day_low_D0_high_not_updated", original_idx)
        if _lower_highs_lower_closes(window, pos):
            matches.setdefault("F5_two_consecutive_lower_highs_lower_closes", original_idx)
    return sorted(matches.items(), key=lambda item: (item[1], item[0]))


def build_failure_entries(candidates: list[dict[str, Any]], price_panel: pd.DataFrame, policy: dict[str, Any]) -> list[dict[str, Any]]:
    prices = normalize_price_panel(price_panel)
    entries: list[dict[str, Any]] = []
    for candidate in candidates:
        if not bool(candidate["is_material_spike_candidate"]):
            continue
        group, d0_idx = _price_context(candidate, prices)
        if group is None:
            continue
        matches = _failure_matches(candidate, group, d0_idx, policy)
        if not matches:
            continue
        d0 = group.iloc[int(d0_idx)]
        for rule, failure_idx in matches:
            entry_idx = int(failure_idx) + 1
            if entry_idx >= len(group):
                continue
            entry = group.iloc[entry_idx]
            failure = group.iloc[int(failure_idx)]
            entries.append(
                {
                    "failure_entry_id": f"MSPV_{candidate['ticker']}_{failure['date']}_{rule[:2]}",
                    "candidate_id": candidate["candidate_id"],
                    "ticker": candidate["ticker"],
                    "signal_date": candidate["signal_date"],
                    "failure_rule": rule,
                    "failure_confirm_date": str(failure["date"]),
                    "entry_date": str(entry["date"]),
                    "entry_open": float(entry["open"]),
                    "D0_high": float(d0["high"]),
                    "D0_low": float(d0["low"]),
                    "D0_close": float(d0["close"]),
                    "D0_volume": float(d0["volume"]),
                    "breakout_level": float(candidate["prior_high"]),
                    "market_cap_bucket": candidate["market_cap_bucket"],
                    "price_bucket": candidate["price_bucket"],
                    "catalyst_strength_label": candidate["catalyst_strength_label"],
                    "material_spike_label": candidate["material_spike_label"],
                    "theme": candidate["theme"],
                    "research_status": "research_only_failed_material_spike_put_vertical_candidate",
                    "no_live_signal": True,
                    "no_broker_action": True,
                    "no_auto_execution": True,
                }
            )
    return entries


def _horizon_return(group: pd.DataFrame, entry_idx: int, entry_open: float, horizon: int) -> float:
    idx = entry_idx + horizon
    if idx >= len(group):
        return math.nan
    return float(group.iloc[idx]["close"]) / entry_open - 1.0


def _window(group: pd.DataFrame, entry_idx: int, horizon: int) -> pd.DataFrame:
    return group.iloc[entry_idx + 1 : min(len(group), entry_idx + horizon + 1)]


def build_underlying_outcomes(entries: list[dict[str, Any]], price_panel: pd.DataFrame) -> list[dict[str, Any]]:
    prices = normalize_price_panel(price_panel)
    rows: list[dict[str, Any]] = []
    for entry in entries:
        group = prices[prices["ticker"].eq(entry["ticker"])].reset_index(drop=True)
        matches = group.index[group["date"].eq(str(entry["entry_date"]))].tolist()
        if not matches:
            continue
        entry_idx = int(matches[0])
        entry_open = float(entry["entry_open"])
        w5 = _window(group, entry_idx, 5)
        w10 = _window(group, entry_idx, 10)
        w15 = _window(group, entry_idx, 15)
        target10 = (not w15.empty) and (w15["low"] <= entry_open * 0.90).any()
        before_target = w15
        if target10:
            first_target_idx = int(w15.index[w15["low"] <= entry_open * 0.90][0])
            before_target = w15[w15.index <= first_target_idx]
        rows.append(
            {
                "failure_entry_id": entry["failure_entry_id"],
                "ticker": entry["ticker"],
                "entry_date": entry["entry_date"],
                "entry_open": entry_open,
                "forward_3d_return": _horizon_return(group, entry_idx, entry_open, 3),
                "forward_5d_return": _horizon_return(group, entry_idx, entry_open, 5),
                "forward_10d_return": _horizon_return(group, entry_idx, entry_open, 10),
                "forward_15d_return": _horizon_return(group, entry_idx, entry_open, 15),
                "target_down_5pct_within_5d": bool((not w5.empty) and (w5["low"] <= entry_open * 0.95).any()),
                "target_down_8pct_within_10d": bool((not w10.empty) and (w10["low"] <= entry_open * 0.92).any()),
                "target_down_10pct_within_15d": bool(target10),
                "adverse_up_5pct_before_target": bool((not before_target.empty) and (before_target["high"] >= entry_open * 1.05).any()),
                "adverse_close_above_D0_high_before_exit": bool((not w15.empty) and (w15["close"] > float(entry["D0_high"])).any()),
                "MFE_down_5d": (entry_open - float(w5["low"].min())) / entry_open if not w5.empty else math.nan,
                "MFE_down_10d": (entry_open - float(w10["low"].min())) / entry_open if not w10.empty else math.nan,
                "MFE_down_15d": (entry_open - float(w15["low"].min())) / entry_open if not w15.empty else math.nan,
                "MAE_up_5d": max(0.0, (float(w5["high"].max()) - entry_open) / entry_open) if not w5.empty else math.nan,
                "MAE_up_10d": max(0.0, (float(w10["high"].max()) - entry_open) / entry_open) if not w10.empty else math.nan,
                "MAE_up_15d": max(0.0, (float(w15["high"].max()) - entry_open) / entry_open) if not w15.empty else math.nan,
                "no_live_signal": True,
                "no_broker_action": True,
                "no_auto_execution": True,
            }
        )
    return rows


def _norm_cdf(x: float) -> float:
    return NormalDist().cdf(x)


def _put_price(spot: float, strike: float, t_years: float, iv: float, r: float) -> float:
    if t_years <= 0 or iv <= 0:
        return max(0.0, strike - spot)
    vol_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / vol_t
    d2 = d1 - vol_t
    return strike * math.exp(-r * t_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _strike_for_put_delta(spot: float, target_delta: float, t_years: float, iv: float, r: float) -> float:
    d1 = NormalDist().inv_cdf(target_delta + 1.0)
    return spot / math.exp(d1 * iv * math.sqrt(t_years) - (r + 0.5 * iv * iv) * t_years)


def _spread_value(spot: float, buy_strike: float, sell_strike: float, t_years: float, iv: float, r: float) -> float:
    return max(0.0, _put_price(spot, buy_strike, t_years, iv, r) - _put_price(spot, sell_strike, t_years, iv, r))


def _exit_price_for_policy(group: pd.DataFrame, entry_idx: int, entry: dict[str, Any], policy: dict[str, Any], exit_policy: dict[str, Any], debit: float, buy_strike: float, sell_strike: float, iv: float, crush: float, r: float, dte_days: int) -> tuple[str, float, float, str, int]:
    max_sessions = int(exit_policy["max_holding_sessions"])
    exit_iv = max(0.05, iv + crush)
    last_idx = min(len(group) - 1, entry_idx + max_sessions)
    for idx in range(entry_idx + 1, last_idx + 1):
        sessions = idx - entry_idx
        remaining_days = max(0, dte_days - sessions * 2)
        row = group.iloc[idx]
        value = _spread_value(float(row["close"]), buy_strike, sell_strike, remaining_days / 365.0, exit_iv, r)
        ret = value / debit - 1.0 if debit > 0 else math.nan
        if ret >= float(exit_policy["take_profit_return"]):
            return str(row["date"]), float(row["close"]), value, "take_profit", sessions
        if ret <= float(exit_policy["stop_loss_return"]):
            return str(row["date"]), float(row["close"]), value, "stop_loss", sessions
        if bool(exit_policy.get("exit_on_close_above_d0_high_next_open")) and float(row["close"]) > float(entry["D0_high"]):
            next_idx = min(len(group) - 1, idx + 1)
            next_row = group.iloc[next_idx]
            sessions = next_idx - entry_idx
            remaining_days = max(0, dte_days - sessions * 2)
            value = _spread_value(float(next_row["open"]), buy_strike, sell_strike, remaining_days / 365.0, exit_iv, r)
            return str(next_row["date"]), float(next_row["open"]), value, "close_above_D0_high_next_open", sessions
    row = group.iloc[last_idx]
    sessions = last_idx - entry_idx
    remaining_days = max(0, dte_days - sessions * 2)
    value = _spread_value(float(row["close"]), buy_strike, sell_strike, remaining_days / 365.0, exit_iv, r)
    return str(row["date"]), float(row["close"]), value, "time_exit", sessions


def build_put_vertical_reference(entries: list[dict[str, Any]], price_panel: pd.DataFrame, policy: dict[str, Any]) -> list[dict[str, Any]]:
    prices = normalize_price_panel(price_panel)
    model = policy["put_vertical_reference_model"]
    dte_days = int(model["dte_calendar_days"])
    buy_delta = float(model["buy_put_delta"])
    sell_delta = float(model["sell_put_delta"])
    markup = float(model["entry_markup"])
    haircut = float(model["exit_haircut"])
    r = float(model["risk_free_rate"])
    rows: list[dict[str, Any]] = []
    for entry in entries:
        group = prices[prices["ticker"].eq(entry["ticker"])].reset_index(drop=True)
        matches = group.index[group["date"].eq(str(entry["entry_date"]))].tolist()
        if not matches:
            continue
        entry_idx = int(matches[0])
        spot = float(entry["entry_open"])
        for iv in model["iv_scenarios"]:
            iv = float(iv)
            t_years = dte_days / 365.0
            buy_strike = _strike_for_put_delta(spot, buy_delta, t_years, iv, r)
            sell_strike = _strike_for_put_delta(spot, sell_delta, t_years, iv, r)
            raw_debit = _spread_value(spot, buy_strike, sell_strike, t_years, iv, r)
            debit = raw_debit * (1.0 + markup)
            for crush in model["post_catalyst_iv_crush_scenarios"]:
                for name, exit_policy in policy["exit_policies"].items():
                    exit_date, exit_spot, raw_exit_value, reason, sessions = _exit_price_for_policy(
                        group, entry_idx, entry, policy, exit_policy, debit, buy_strike, sell_strike, iv, float(crush), r, dte_days
                    )
                    exit_value = raw_exit_value * (1.0 - haircut)
                    rows.append(
                        {
                            "failure_entry_id": entry["failure_entry_id"],
                            "ticker": entry["ticker"],
                            "exit_policy": name,
                            "iv_scenario": iv,
                            "post_catalyst_iv_crush": float(crush),
                            "model_status": MODEL_STATUS,
                            "entry_date": entry["entry_date"],
                            "entry_open": spot,
                            "buy_put_delta": buy_delta,
                            "sell_put_delta": sell_delta,
                            "buy_put_strike": buy_strike,
                            "sell_put_strike": sell_strike,
                            "spread_debit": debit,
                            "exit_date": exit_date,
                            "exit_underlying_price": exit_spot,
                            "exit_value": exit_value,
                            "vertical_return": exit_value / debit - 1.0 if debit > 0 else math.nan,
                            "exit_reason": reason,
                            "holding_sessions": sessions,
                            "no_live_signal": True,
                            "no_broker_action": True,
                            "no_auto_execution": True,
                        }
                    )
    return rows


def build_bucket_summary(candidates: list[dict[str, Any]], entries: list[dict[str, Any]], underlying: list[dict[str, Any]], verticals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return []
    cand = pd.DataFrame(candidates)
    ent = pd.DataFrame(entries)
    und = pd.DataFrame(underlying)
    vert = pd.DataFrame(verticals)
    rows: list[dict[str, Any]] = []
    keys = ["market_cap_bucket", "price_bucket", "catalyst_strength_label", "theme", "material_spike_label"]
    for values, group in ent.groupby(keys, dropna=False):
        mask = pd.Series(True, index=cand.index)
        for key, value in zip(keys, values):
            if key in cand.columns:
                mask &= cand[key].astype(str).eq(str(value))
        ids = set(group["failure_entry_id"].astype(str))
        und_g = und[und["failure_entry_id"].astype(str).isin(ids)] if not und.empty else pd.DataFrame()
        vert_g = vert[vert["failure_entry_id"].astype(str).isin(ids)] if not vert.empty else pd.DataFrame()
        rows.append(
            {
                **{key: value for key, value in zip(keys, values)},
                "baseline_candidate_count": int(mask.sum()),
                "failure_entry_count": int(len(group)),
                "target_down_8pct_within_10d_rate": float(und_g["target_down_8pct_within_10d"].astype(bool).mean()) if not und_g.empty else math.nan,
                "median_MFE_down_10d": float(und_g["MFE_down_10d"].median()) if not und_g.empty else math.nan,
                "median_MAE_up_10d": float(und_g["MAE_up_10d"].median()) if not und_g.empty else math.nan,
                "synthetic_vertical_median_return": float(vert_g["vertical_return"].median()) if not vert_g.empty else math.nan,
                "synthetic_vertical_positive_rate": float((vert_g["vertical_return"] > 0).mean()) if not vert_g.empty else math.nan,
                "research_only": True,
                "no_live_signal": True,
                "no_broker_action": True,
                "no_auto_execution": True,
            }
        )
    return rows


def build_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUT_FILES:
        if name == "material_spike_content_manifest.json":
            continue
        path = output_dir / name
        if not path.exists():
            raise SystemExit(f"material_spike_manifest_missing_required_file:{name}")
        files.append({"relative_path": name, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    payload = {"policy_version": POLICY_VERSION, "required_files": REQUIRED_OUTPUT_FILES, "files": files}
    payload["content_set_hash"] = text_hash(json_dumps(files))
    return payload


def verify_output_manifest(output_dir: Path) -> dict[str, Any]:
    expected = set(REQUIRED_OUTPUT_FILES)
    actual = {p.name for p in output_dir.iterdir() if p.is_file()}
    if actual != expected:
        raise SystemExit(f"material_spike_manifest_file_set_mismatch:{sorted(actual ^ expected)}")
    manifest = json.loads((output_dir / "material_spike_content_manifest.json").read_text(encoding="utf-8"))
    rebuilt = build_manifest(output_dir)
    if manifest.get("content_set_hash") != rebuilt.get("content_set_hash"):
        raise SystemExit("material_spike_manifest_hash_mismatch")
    return manifest


def build_research(
    baseline_panel: pd.DataFrame,
    price_panel: pd.DataFrame,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = build_candidate_panel(baseline_panel, policy)
    entries = build_failure_entries(candidates, price_panel, policy)
    underlying = build_underlying_outcomes(entries, price_panel)
    verticals = build_put_vertical_reference(entries, price_panel, policy)
    summary = build_bucket_summary(candidates, entries, underlying, verticals)
    receipt = {
        "run_status": "material_spike_put_vertical_research_completed",
        "candidate_count": len(candidates),
        "material_spike_candidate_count": sum(1 for row in candidates if row["is_material_spike_candidate"]),
        "failure_entry_count": len(entries),
        "underlying_outcome_count": len(underlying),
        "synthetic_vertical_reference_count": len(verticals),
        "model_status": MODEL_STATUS,
        "output_dir": repo_relative(output_dir),
        **SAFETY_FLAGS,
    }
    lineage = {
        "policy_version": POLICY_VERSION,
        "baseline_source": "caller_supplied_existing_morita_initial_breakout_candidate_panel",
        "price_source": "caller_supplied_ohlcv_forward_path_panel",
        "entry_available_fields": ["OHLCV", "rank", "score", "theme", "market_cap", "catalyst_label"],
        "future_leakage_allowed": False,
        "model_status": MODEL_STATUS,
        **SAFETY_FLAGS,
    }
    write_csv(output_dir / "material_spike_candidate_panel.csv", candidates, CANDIDATE_COLUMNS)
    write_csv(output_dir / "material_spike_failure_entry_log.csv", entries, ENTRY_COLUMNS)
    write_csv(output_dir / "material_spike_underlying_outcomes.csv", underlying, UNDERLYING_COLUMNS)
    write_csv(output_dir / "material_spike_put_vertical_reference.csv", verticals, VERTICAL_COLUMNS)
    write_csv(
        output_dir / "material_spike_bucket_summary.csv",
        summary,
        [
            "market_cap_bucket",
            "price_bucket",
            "catalyst_strength_label",
            "theme",
            "material_spike_label",
            "baseline_candidate_count",
            "failure_entry_count",
            "target_down_8pct_within_10d_rate",
            "median_MFE_down_10d",
            "median_MAE_up_10d",
            "synthetic_vertical_median_return",
            "synthetic_vertical_positive_rate",
            "research_only",
            "no_live_signal",
            "no_broker_action",
            "no_auto_execution",
        ],
    )
    write_json(output_dir / "material_spike_source_lineage.json", lineage)
    write_json(output_dir / "material_spike_receipt.json", receipt)
    (output_dir / "material_spike_summary.md").write_text(
        "# Morita Material Spike Put Vertical Research v1\n\n"
        f"Candidates: `{len(candidates)}`. Failure entries: `{len(entries)}`. Synthetic put-vertical rows: `{len(verticals)}`.\n\n"
        "Research-only. Synthetic fixed-IV reference only; not historical option fill reconstruction. No live signal, broker action, order, sizing, rank, notification, or existing Morita Bot behavior change is created.\n",
        encoding="utf-8",
    )
    write_json(output_dir / "material_spike_content_manifest.json", build_manifest(output_dir))
    verify_output_manifest(output_dir)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-panel", required=True)
    parser.add_argument("--price-panel", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    args = parser.parse_args()
    receipt = build_research(pd.read_csv(args.baseline_panel), pd.read_csv(args.price_panel), Path(args.output_dir), Path(args.policy))
    print(json_dumps(receipt))


if __name__ == "__main__":
    main()
