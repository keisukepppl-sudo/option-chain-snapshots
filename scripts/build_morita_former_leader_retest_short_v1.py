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

from src.morita_single_call_reference.black_scholes_reference import norm_cdf


ARTIFACT_VERSION = "morita_former_leader_retest_short_v1"
SPEC_PATH = REPO_ROOT / "config" / ARTIFACT_VERSION / "study_spec.json"
OUTPUT_DIR = REPO_ROOT / "outputs" / ARTIFACT_VERSION
CHATGPT_BUNDLE = REPO_ROOT / f"{ARTIFACT_VERSION}_chatgpt_bundle.md"
D_METRIC = "broad_russell1000_cross_sectional_dispersion_20d"
L_METRIC = "broad_russell1000_qqq_minus_eqw_return_20d"
SETUP_NAME = "FL_RETEST_PRIMARY"
MANIFEST_NAME = "study_content_manifest.json"
OUTPUT_FILES = [
    "source_lineage.json",
    "threshold_inheritance.json",
    "former_leader_episode_panel.csv",
    "breakdown_panel.csv",
    "retest_touch_panel.csv",
    "retest_rejection_entry_panel.csv",
    "underlying_outcome_panel.csv",
    "option_model_lineage.json",
    "option_model_outcome_panel.csv",
    "cell_summary.csv",
    "regime_comparison.csv",
    "origin_comparison_bad_regime.csv",
    "period_comparison.csv",
    "concentration_diagnostics.csv",
    "interpretation_labels.json",
    "study_receipt.json",
    MANIFEST_NAME,
    "study_summary.md",
]
ORIGIN_ORDER = {
    "ORIGIN_S": 0,
    "ORIGIN_A": 1,
    "ORIGIN_RS98_BREAKOUT": 2,
    "ORIGIN_RS96_97_BREAKOUT": 3,
    "ORIGIN_RS90_95_BREAKOUT": 4,
}
ORIGIN_GROUPS = {
    "ORIGIN_S": "FORMER_S",
    "ORIGIN_A": "FORMER_A",
    "ORIGIN_RS98_BREAKOUT": "RS98_BREAKOUT",
    "ORIGIN_RS96_97_BREAKOUT": "RS96_97_BREAKOUT",
    "ORIGIN_RS90_95_BREAKOUT": "RS90_95_BREAKOUT",
}
EXIT_RULES = {
    "RULE_A_10D_TIME_EXIT": {"target": None, "stop": "retest_high", "time": 10},
    "RULE_B_MINUS_8_UNDERLYING_TARGET": {"target": 0.08, "stop": "retest_high", "time": 10},
    "RULE_C_MINUS_10_UNDERLYING_TARGET": {"target": 0.10, "stop": "retest_high", "time": 10},
    "RULE_D_20D_EXTENDED_TREND": {"target": 0.15, "stop": "50dma", "time": 20},
    "RULE_E_CONSERVATIVE_QUICK_PUT": {"target": 0.05, "stop": "retest_high", "time": 5},
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        if REPO_ROOT.resolve() not in resolved.parents:
            raise SystemExit(f"refusing_to_clean_outside_repo:{resolved}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


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


def rate(series: pd.Series) -> float | None:
    if series.empty:
        return None
    return float(series.astype(bool).mean())


def profit_factor(returns: pd.Series) -> float | None:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        return None
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / losses


def md_table(df: pd.DataFrame, limit: int | None = None) -> str:
    if df.empty:
        return "_No rows._"
    if limit is not None:
        df = df.head(limit).copy()
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        vals = []
        for col in cols:
            value = row[col]
            if pd.isna(value):
                vals.append("")
            elif isinstance(value, float):
                vals.append("inf" if math.isinf(value) else f"{value:.4f}")
            else:
                vals.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def put_price(spot: float, strike: float, years: float, volatility: float, risk_free_rate: float) -> float:
    if spot <= 0 or strike <= 0:
        raise ValueError("spot_and_strike_must_be_positive")
    if years <= 0 or volatility <= 0:
        return max(strike - spot, 0.0)
    vol_sqrt = volatility * math.sqrt(years)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility * volatility) * years) / vol_sqrt
    d2 = d1 - vol_sqrt
    return strike * math.exp(-risk_free_rate * years) * norm_cdf(-d2) - spot * norm_cdf(-d1)


def model_option_return(entry_spot: float, exit_spot: float, hold_sessions: int, model_type: str, model: dict[str, Any]) -> float | None:
    if entry_spot <= 0 or exit_spot <= 0:
        return None
    dte = int(model["dte"])
    entry_years = dte / 365.25
    exit_years = max((dte - max(0, hold_sessions)) / 365.25, 0.0)
    iv = float(model["iv"])
    r = float(model["risk_free_rate"])
    markup = 1.0 + float(model["entry_markup"])
    haircut = 1.0 - float(model["exit_haircut"])
    long_k = entry_spot
    long_entry = put_price(entry_spot, long_k, entry_years, iv, r)
    long_exit = put_price(exit_spot, long_k, exit_years, iv, r)
    if "vertical" in model_type:
        short_k = entry_spot * float(model["short_put_strike_pct"])
        short_entry = put_price(entry_spot, short_k, entry_years, iv, r)
        short_exit = put_price(exit_spot, short_k, exit_years, iv, r)
        entry_debit = (long_entry - short_entry) * markup
        exit_value = max(long_exit - short_exit, 0.0) * haircut
    else:
        entry_debit = long_entry * markup
        exit_value = long_exit * haircut
    if entry_debit <= 0:
        return None
    return (exit_value / entry_debit - 1.0) * 100.0


def classify_regime(D_value: Any, L_value: Any, thresholds: dict[str, Any]) -> dict[str, Any]:
    d = safe_float(D_value)
    l = safe_float(L_value)
    if d is None or l is None:
        return {"D_state": "unavailable", "L_state": "unavailable", "regime_state": "REGIME_UNAVAILABLE"}
    d_high = d >= float(thresholds["D_high_cutoff"])
    l_high = l >= float(thresholds["L_high_cutoff"])
    if d_high and l_high:
        regime = "NARROW_LEADERSHIP"
    elif d_high:
        regime = "HIGH_DISPERSION"
    else:
        regime = "NORMAL"
    return {"D_state": "HIGH" if d_high else "NOT_HIGH", "L_state": "HIGH" if l_high else "NOT_HIGH", "regime_state": regime}


def verify_thresholds(spec: dict[str, Any]) -> dict[str, Any]:
    source = REPO_ROOT / spec["source_regime_cutoffs"]
    cutoffs = pd.read_csv(source)
    rows = cutoffs[cutoffs["metric"].isin([D_METRIC, L_METRIC])]
    if len(rows) != 2:
        raise SystemExit("required_regime_thresholds_missing")
    values = {r["metric"]: {"p33": float(r["p33"]), "p67": float(r["p67"])} for _, r in rows.iterrows()}
    if abs(values[D_METRIC]["p67"] - float(spec["expected_D_high_cutoff"])) > 1e-12:
        raise SystemExit("D_high_cutoff_verification_failed")
    if abs(values[L_METRIC]["p67"] - float(spec["expected_L_high_cutoff"])) > 1e-12:
        raise SystemExit("L_high_cutoff_verification_failed")
    return {
        "threshold_source": repo_relative(source),
        "threshold_source_sha256": file_sha256(source),
        "D_metric_name": D_METRIC,
        "L_metric_name": L_METRIC,
        "D_high_cutoff": values[D_METRIC]["p67"],
        "D_low_cutoff": values[D_METRIC]["p33"],
        "L_high_cutoff": values[L_METRIC]["p67"],
        "L_low_cutoff": values[L_METRIC]["p33"],
        "regime_mapping": {
            "NORMAL": "D_not_high",
            "HIGH_DISPERSION": "D_high AND L_not_high",
            "NARROW_LEADERSHIP": "D_high AND L_high",
            "HIGH_D_OR_NARROW": "HIGH_DISPERSION or NARROW_LEADERSHIP",
        },
        "verification_status": "passed",
        "retuned": False,
    }


def period_for(date_value: Any) -> str:
    date = str(date_value)[:10]
    if "2022-01-01" <= date <= "2022-12-31":
        return "2022"
    if "2023-01-01" <= date <= "2023-12-31":
        return "2023"
    if "2024-01-01" <= date <= "2026-06-30":
        return "2024_2026"
    return "out_of_scope"


def origin_rs_bucket(rs: Any) -> str:
    value = safe_float(rs)
    if value is None:
        return "UNKNOWN"
    if value >= 98:
        return "RS98_PLUS"
    if value >= 96:
        return "RS96_97"
    if value >= 90:
        return "RS90_95"
    return "LT90"


def load_price_panel(spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = REPO_ROOT / spec["source_ohlcv_path"]
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["date"] <= spec["analysis_end_date"]].dropna(subset=["ticker", "open", "high", "low", "close"]).copy()
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = df.groupby("ticker", group_keys=False)
    df["sma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["sma50"] = g["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
    df["sma100"] = g["close"].transform(lambda s: s.rolling(100, min_periods=100).mean())
    df["sma200"] = g["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
    df["prior_65d_high"] = g["high"].transform(lambda s: s.shift(1).rolling(65, min_periods=65).max())
    df["avg_volume_50"] = g["volume"].transform(lambda s: s.shift(1).rolling(50, min_periods=20).mean())
    df["volume_multiple"] = df["volume"] / df["avg_volume_50"]
    df["return_252"] = g["close"].transform(lambda s: s / s.shift(252) - 1.0)
    df["rs_252"] = df.groupby("date")["return_252"].rank(pct=True) * 100.0
    coverage = {
        "ohlcv_source": repo_relative(path),
        "ohlcv_sha256": file_sha256(path),
        "min_date": str(df["date"].min()),
        "max_date": str(df["date"].max()),
        "ticker_count": int(df["ticker"].nunique()),
        "row_count": int(len(df)),
        "has_required_2021_warmup_for_2022": bool(str(df["date"].min()) <= spec["required_ohlcv_start_for_2022_rs_warmup"]),
    }
    return df, coverage


def load_signal_origins(spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for path in [REPO_ROOT / spec["source_baseline_run_dir"] / "morita_bot_baseline_panel.csv", REPO_ROOT / spec["source_2023_signal_panel"]]:
        if not path.exists():
            continue
        panel = pd.read_csv(path)
        panel = panel[panel["signal_rank"].isin(["S", "A"])].copy()
        for _, row in panel.iterrows():
            rank = str(row["signal_rank"])
            rows.append(
                {
                    "ticker": row["underlying_symbol"],
                    "origin_date": str(row["signal_decision_date"])[:10],
                    "origin_type": f"ORIGIN_{rank}",
                    "origin_rank": rank,
                    "origin_RS_value": safe_float(row.get("standard_rs_score")),
                    "origin_close": safe_float(row.get("breakout_price", row.get("entry_price"))),
                    "origin_high": None,
                    "origin_low": safe_float(row.get("breakout_day_low")),
                    "origin_volume": None,
                    "origin_65d_high": safe_float(row.get("prior_20d_high")),
                    "origin_volume_multiple": safe_float(row.get("volume_multiple")),
                }
            )
    return pd.DataFrame(rows)


def build_rs_breakout_origins(price: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    min_vol = float(spec["rs_breakout_volume_multiple_min"])
    mask = (
        (price["date"] >= "2023-01-01")
        & (price["date"] <= spec["analysis_end_date"])
        & (price["close"] > price["prior_65d_high"])
        & (price["volume_multiple"] >= min_vol)
        & (price["rs_252"] >= 90)
    )
    rows = []
    for _, row in price[mask].iterrows():
        rs = float(row["rs_252"])
        if rs >= 98:
            origin_type = "ORIGIN_RS98_BREAKOUT"
        elif rs >= 96:
            origin_type = "ORIGIN_RS96_97_BREAKOUT"
        else:
            origin_type = "ORIGIN_RS90_95_BREAKOUT"
        rows.append(
            {
                "ticker": row["ticker"],
                "origin_date": row["date"],
                "origin_type": origin_type,
                "origin_rank": "",
                "origin_RS_value": rs,
                "origin_close": row["close"],
                "origin_high": row["high"],
                "origin_low": row["low"],
                "origin_volume": row["volume"],
                "origin_65d_high": row["prior_65d_high"],
                "origin_volume_multiple": row["volume_multiple"],
            }
        )
    return pd.DataFrame(rows)


def dedupe_episodes(origins: pd.DataFrame, price: pd.DataFrame, thresholds: dict[str, Any], spec: dict[str, Any]) -> pd.DataFrame:
    if origins.empty:
        return pd.DataFrame()
    origins = origins.copy()
    origins["origin_order"] = origins["origin_type"].map(ORIGIN_ORDER).fillna(99)
    origins = origins.sort_values(["ticker", "origin_date", "origin_order"]).reset_index(drop=True)
    date_pos = {ticker: {d: i for i, d in enumerate(g["date"].tolist())} for ticker, g in price.groupby("ticker")}
    regime_by_date = {}
    if "source_regime_daily_panel" in spec:
        regime = build_regime_panel(spec, thresholds)
        regime_by_date = regime.set_index("date").to_dict("index")
    episodes = []
    for ticker, group in origins.groupby("ticker"):
        last_kept_pos: int | None = None
        current_idx: int | None = None
        reinforcement = 0
        for _, row in group.iterrows():
            pos = date_pos.get(ticker, {}).get(row["origin_date"])
            if pos is None:
                continue
            if last_kept_pos is None or pos - last_kept_pos > int(spec["former_leader_episode_dedup_sessions"]):
                if current_idx is not None:
                    episodes[current_idx]["episode_reinforcement_count"] = reinforcement
                r = row.to_dict()
                reg = regime_by_date.get(r["origin_date"], {})
                r.update(
                    {
                        "episode_id": f"flr_{ticker}_{r['origin_date'].replace('-', '')}_{len(episodes)+1:06d}",
                        "origin_type_group": ORIGIN_GROUPS.get(r["origin_type"], r["origin_type"]),
                        "origin_RS_bucket": origin_rs_bucket(r.get("origin_RS_value")),
                        "origin_regime_state": reg.get("regime_state", "REGIME_UNAVAILABLE"),
                        "origin_D_value": reg.get("D_value"),
                        "origin_L_value": reg.get("L_value"),
                        "episode_reinforcement_count": 0,
                        "origin_session_index": pos,
                    }
                )
                episodes.append(r)
                current_idx = len(episodes) - 1
                last_kept_pos = pos
                reinforcement = 0
            else:
                reinforcement += 1
        if current_idx is not None:
            episodes[current_idx]["episode_reinforcement_count"] = reinforcement
    out = pd.DataFrame(episodes)
    return out.drop(columns=["origin_order"], errors="ignore")


def build_regime_panel(spec: dict[str, Any], thresholds: dict[str, Any]) -> pd.DataFrame:
    path = REPO_ROOT / spec["source_regime_daily_panel"]
    daily = pd.read_csv(path)
    daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    out = daily[["date", D_METRIC, L_METRIC]].rename(columns={D_METRIC: "D_value", L_METRIC: "L_value"}).copy()
    states = out.apply(lambda r: classify_regime(r["D_value"], r["L_value"], thresholds), axis=1, result_type="expand")
    out = pd.concat([out, states], axis=1)
    out["D_value_5_sessions_ago"] = out["D_value"].shift(5)
    out["D_change_5_sessions"] = out["D_value"] - out["D_value_5_sessions_ago"]
    out["D_rising_5d"] = out["D_value"] > out["D_value_5_sessions_ago"]
    out["D_value_10_sessions_ago"] = out["D_value"].shift(10)
    out["D_change_10_sessions"] = out["D_value"] - out["D_value_10_sessions_ago"]
    out["D_rising_10d"] = out["D_value"] > out["D_value_10_sessions_ago"]
    return out


def detect_breakdowns(episodes: pd.DataFrame, price: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    by_ticker = {ticker: g.reset_index(drop=True) for ticker, g in price.groupby("ticker")}
    for _, ep in episodes.iterrows():
        bars = by_ticker.get(ep["ticker"])
        if bars is None:
            continue
        start = int(ep["origin_session_index"]) + int(spec["breakdown_min_sessions_after_origin"])
        end = min(int(ep["origin_session_index"]) + int(spec["breakdown_max_sessions_after_origin"]), len(bars) - 1)
        for i in range(start, end + 1):
            bar = bars.iloc[i]
            origin_close = safe_float(ep.get("origin_close"))
            if origin_close is None:
                continue
            primary = bool(bar["close"] < bar["sma20"] and bar["close"] < origin_close)
            if not primary:
                continue
            rows.append(
                {
                    **ep.to_dict(),
                    "breakdown_date": bar["date"],
                    "breakdown_close": bar["close"],
                    "breakdown_low": bar["low"],
                    "breakdown_volume": bar["volume"],
                    "breakdown_relative_to_origin_pct": bar["close"] / origin_close - 1.0,
                    "broke_20dma": bool(bar["close"] < bar["sma20"]),
                    "broke_50dma": bool(bar["close"] < bar["sma50"]),
                    "broke_origin_close": bool(bar["close"] < origin_close),
                    "broke_origin_low": bool(bar["close"] < safe_float(ep.get("origin_low", origin_close))),
                    "broke_20d_low": bool(bar["close"] < bars.loc[max(0, i - 20) : i - 1, "low"].min()) if i > 0 else False,
                    "sessions_from_origin_to_breakdown": i - int(ep["origin_session_index"]),
                    "breakdown_session_index": i,
                }
            )
            break
    return pd.DataFrame(rows)


def zone_touch(bar: pd.Series, reference: float, tolerance: float) -> bool:
    return bool(bar["high"] >= reference * (1.0 - tolerance) and bar["low"] <= reference * (1.0 + tolerance))


def detect_retests(breakdowns: pd.DataFrame, price: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    touch_rows = []
    entry_rows = []
    by_ticker = {ticker: g.reset_index(drop=True) for ticker, g in price.groupby("ticker")}
    tol = float(spec["primary_retest_tolerance_pct"])
    for _, bd in breakdowns.iterrows():
        bars = by_ticker.get(bd["ticker"])
        if bars is None:
            continue
        start = int(bd["breakdown_session_index"]) + int(spec["retest_min_sessions_after_breakdown"])
        end = min(int(bd["breakdown_session_index"]) + int(spec["retest_max_sessions_after_breakdown"]), len(bars) - 2)
        for i in range(start, end + 1):
            bar = bars.iloc[i]
            refs = {
                "retest_zone_20dma": safe_float(bar.get("sma20")),
                "retest_zone_50dma": safe_float(bar.get("sma50")),
                "retest_zone_origin_close": safe_float(bd.get("origin_close")),
                "retest_zone_breakdown_close": safe_float(bd.get("breakdown_close")),
                "retest_zone_origin_low": safe_float(bd.get("origin_low")),
            }
            touched = [(name, value) for name, value in refs.items() if value is not None and zone_touch(bar, value, tol)]
            if not touched:
                continue
            name, ref = touched[0]
            daily_range = bar["high"] - bar["low"]
            close_pos = (bar["close"] - bar["low"]) / daily_range if daily_range > 0 else 1.0
            upper_wick = (bar["high"] - max(bar["open"], bar["close"])) / daily_range if daily_range > 0 else 0.0
            rejection = bool(bar["close"] < bar["open"] and bar["close"] < ref and close_pos <= 0.5)
            common = {
                **bd.to_dict(),
                "retest_date": bar["date"],
                "retest_high": bar["high"],
                "retest_close": bar["close"],
                "retest_open": bar["open"],
                "retest_low": bar["low"],
                "touched_zone_type": name,
                "resistance_reference_value": ref,
                "close_vs_resistance_pct": bar["close"] / ref - 1.0,
                "range_close_position": close_pos,
                "upper_wick_pct": upper_wick,
                "rejection_volume_multiple": bar["volume_multiple"],
                "diagnostic_upper_wick_rejection": bool(upper_wick >= 0.4),
                "diagnostic_close_below_prior_low": bool(i > 0 and bar["close"] < bars.iloc[i - 1]["low"]),
                "diagnostic_volume_rejection": bool(bar["volume_multiple"] >= 1.5),
                "sessions_from_breakdown_to_retest": i - int(bd["breakdown_session_index"]),
                "sessions_from_origin_to_retest": i - int(bd["origin_session_index"]),
                "retest_session_index": i,
            }
            for diag_tol in spec["diagnostic_retest_tolerances_pct"]:
                common[f"touched_retest_zone_{int(float(diag_tol)*1000)}bp_diagnostic"] = any(
                    value is not None and zone_touch(bar, value, float(diag_tol)) for value in refs.values()
                )
            touch_rows.append(common)
            if rejection:
                next_bar = bars.iloc[i + 1]
                entry_rows.append(
                    {
                        **common,
                        "retest_rejection_date": bar["date"],
                        "hypothetical_entry_date": next_bar["date"],
                        "hypothetical_entry_open": next_bar["open"],
                        "entry_session_index": i + 1,
                        "setup_name": SETUP_NAME,
                    }
                )
            break
    return pd.DataFrame(touch_rows), pd.DataFrame(entry_rows)


def simulate_exit(entry: pd.Series, bars: pd.DataFrame, rule_name: str, rule: dict[str, Any]) -> dict[str, Any]:
    entry_idx = int(entry["entry_session_index"])
    entry_price = float(entry["hypothetical_entry_open"])
    max_i = min(entry_idx + int(rule["time"]), len(bars) - 1)
    stop_level = float(entry["retest_high"])
    exit_i = max_i
    exit_price = float(bars.iloc[max_i]["close"])
    reason = f"time_exit_{rule['time']}d_close"
    for i in range(entry_idx, max_i + 1):
        bar = bars.iloc[i]
        if rule["target"] is not None and bar["low"] <= entry_price * (1.0 - float(rule["target"])):
            exit_i = i
            exit_price = entry_price * (1.0 - float(rule["target"]))
            reason = f"underlying_target_minus_{int(float(rule['target'])*100)}pct"
            break
        if rule["stop"] == "retest_high":
            stop_hit = bool(bar["close"] > stop_level)
        else:
            stop_hit = bool(bar["close"] > bar["sma50"])
        if stop_hit:
            exit_i = min(i + 1, len(bars) - 1)
            exit_price = float(bars.iloc[exit_i]["open"])
            reason = f"close_above_{rule['stop']}_exit_next_open"
            break
    return {
        "exit_rule": rule_name,
        "exit_date": bars.iloc[exit_i]["date"],
        "exit_underlying_price": exit_price,
        "exit_reason": reason,
        "hold_sessions": exit_i - entry_idx,
        "underlying_short_return_pct": (entry_price - exit_price) / entry_price * 100.0,
    }


def compute_outcomes(entries: pd.DataFrame, price: pd.DataFrame, regime: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    underlying_rows = []
    option_rows = []
    by_ticker = {ticker: g.reset_index(drop=True) for ticker, g in price.groupby("ticker")}
    regime_by_date = regime.set_index("date").to_dict("index")
    for _, entry in entries.iterrows():
        bars = by_ticker.get(entry["ticker"])
        if bars is None:
            continue
        idx = int(entry["entry_session_index"])
        if idx + 20 >= len(bars):
            continue
        entry_price = float(entry["hypothetical_entry_open"])
        future20 = bars.iloc[idx : idx + 21].copy()
        min10 = float(future20.head(11)["low"].min())
        min20 = float(future20["low"].min())
        max10 = float(future20.head(11)["high"].max())
        max20 = float(future20["high"].max())
        reg = regime_by_date.get(entry["retest_rejection_date"], {})
        base = {
            **entry.to_dict(),
            "period": period_for(entry["hypothetical_entry_date"]),
            "regime_observation_date": entry["retest_rejection_date"],
            "D_value": reg.get("D_value"),
            "L_value": reg.get("L_value"),
            "D_value_5_sessions_ago": reg.get("D_value_5_sessions_ago"),
            "D_change_5_sessions": reg.get("D_change_5_sessions"),
            "D_rising_5d": reg.get("D_rising_5d"),
            "D_value_10_sessions_ago": reg.get("D_value_10_sessions_ago"),
            "D_change_10_sessions": reg.get("D_change_10_sessions"),
            "D_rising_10d": reg.get("D_rising_10d"),
            "regime_state": reg.get("regime_state", "REGIME_UNAVAILABLE"),
            "HIGH_D_OR_NARROW": reg.get("regime_state") in {"HIGH_DISPERSION", "NARROW_LEADERSHIP"},
            "underlying_return_5d": float(future20.iloc[5]["close"] / entry_price - 1.0),
            "underlying_return_10d": float(future20.iloc[10]["close"] / entry_price - 1.0),
            "underlying_return_20d": float(future20.iloc[20]["close"] / entry_price - 1.0),
            "reached_minus_5pct_within_10d": bool(min10 <= entry_price * 0.95),
            "reached_minus_8pct_within_10d": bool(min10 <= entry_price * 0.92),
            "reached_minus_10pct_within_10d": bool(min10 <= entry_price * 0.90),
            "reached_minus_15pct_within_20d": bool(min20 <= entry_price * 0.85),
            "reached_minus_20pct_within_20d": bool(min20 <= entry_price * 0.80),
            "max_favorable_excursion_10d": min10 / entry_price - 1.0,
            "max_favorable_excursion_20d": min20 / entry_price - 1.0,
            "max_adverse_excursion_10d": max10 / entry_price - 1.0,
            "max_adverse_excursion_20d": max20 / entry_price - 1.0,
            "recovered_retest_high_within_10d": bool(max10 >= float(entry["retest_high"])),
            "recovered_retest_high_within_20d": bool(max20 >= float(entry["retest_high"])),
            "recovered_origin_close_within_20d": bool(max20 >= float(entry["origin_close"])),
            "recovered_50dma_within_20d": bool((future20["high"] >= future20["sma50"]).any()),
            "close_above_retest_high_stop_triggered": bool((future20["close"] > float(entry["retest_high"])).any()),
            "close_above_50dma_stop_triggered": bool((future20["close"] > future20["sma50"]).any()),
        }
        underlying_rows.append(base)
        for rule_name, rule in EXIT_RULES.items():
            exit_result = simulate_exit(entry, bars, rule_name, rule)
            for model_type, model in spec["option_models"].items():
                modeled = model_option_return(entry_price, float(exit_result["exit_underlying_price"]), int(exit_result["hold_sessions"]), model_type, model)
                option_rows.append(
                    {
                        **base,
                        **exit_result,
                        "option_model_type": model_type,
                        "modeled_option_return_pct": modeled,
                        "synthetic_fixed_IV_reference_only": True,
                        "not_historical_option_fill_reconstruction": True,
                    }
                )
    return pd.DataFrame(underlying_rows), pd.DataFrame(option_rows)


def sample_status(n: int, spec: dict[str, Any]) -> str:
    if n < int(spec["sample_gates"]["minimum_sample"]):
        return "insufficient_sample"
    if n >= int(spec["sample_gates"]["preferred_sample"]):
        return "preferred_sample_met"
    return "minimum_sample_met"


def concentration(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {"unique_ticker_count": 0, "largest_single_ticker": "", "largest_single_ticker_share": None, "top_five_ticker_share": None}
    counts = group["ticker"].value_counts()
    return {
        "unique_ticker_count": int(counts.size),
        "largest_single_ticker": str(counts.index[0]),
        "largest_single_ticker_share": float(counts.iloc[0] / len(group)),
        "top_five_ticker_share": float(counts.head(5).sum() / len(group)),
    }


def summarize_cell(group: pd.DataFrame, episodes: pd.DataFrame, breakdowns: pd.DataFrame, touches: pd.DataFrame, entries: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    conc = concentration(group)
    n = int(len(group))
    returns = pd.to_numeric(group.get("modeled_option_return_pct", pd.Series(dtype=float)), errors="coerce")
    out = {
        "former_leader_episode_count": int(len(episodes)),
        "breakdown_count": int(len(breakdowns)),
        "retest_touch_count": int(len(touches)),
        "retest_rejection_entry_count": int(len(entries)),
        "completed_trade_count": n,
        "breakdown_rate": len(breakdowns) / len(episodes) if len(episodes) else None,
        "retest_touch_rate": len(touches) / len(breakdowns) if len(breakdowns) else None,
        "entry_rate": len(entries) / len(touches) if len(touches) else None,
        "reached_minus_5pct_10d_rate": rate(group["reached_minus_5pct_within_10d"]) if n else None,
        "reached_minus_8pct_10d_rate": rate(group["reached_minus_8pct_within_10d"]) if n else None,
        "reached_minus_10pct_10d_rate": rate(group["reached_minus_10pct_within_10d"]) if n else None,
        "reached_minus_15pct_20d_rate": rate(group["reached_minus_15pct_within_20d"]) if n else None,
        "reached_minus_20pct_20d_rate": rate(group["reached_minus_20pct_within_20d"]) if n else None,
        "recovered_retest_high_10d_rate": rate(group["recovered_retest_high_within_10d"]) if n else None,
        "recovered_retest_high_20d_rate": rate(group["recovered_retest_high_within_20d"]) if n else None,
        "median_MFE_10d": group["max_favorable_excursion_10d"].median() if n else None,
        "median_MAE_10d": group["max_adverse_excursion_10d"].median() if n else None,
        "p75_MAE_10d": group["max_adverse_excursion_10d"].quantile(0.75) if n else None,
        "p90_MAE_10d": group["max_adverse_excursion_10d"].quantile(0.90) if n else None,
        "modeled_PF": profit_factor(returns),
        "modeled_win_rate": float((returns > 0).mean()) if returns.notna().any() else None,
        "modeled_mean_return_pct": returns.mean() if returns.notna().any() else None,
        "modeled_median_return_pct": returns.median() if returns.notna().any() else None,
        "modeled_mean_loss_pct": returns[returns < 0].mean() if (returns < 0).any() else None,
        "modeled_p10_return_pct": returns.quantile(0.10) if returns.notna().any() else None,
        "modeled_p90_return_pct": returns.quantile(0.90) if returns.notna().any() else None,
        "earliest_entry_date": group["hypothetical_entry_date"].min() if n else "",
        "latest_entry_date": group["hypothetical_entry_date"].max() if n else "",
        "sample_status": sample_status(n, spec),
        **conc,
    }
    out["concentration_flag"] = bool(
        (out["largest_single_ticker_share"] is not None and out["largest_single_ticker_share"] > float(spec["sample_gates"]["largest_single_ticker_share_max"]))
        or (out["top_five_ticker_share"] is not None and out["top_five_ticker_share"] > float(spec["sample_gates"]["top_five_ticker_share_max"]))
    )
    return out


def cell_summary(option_rows: pd.DataFrame, episodes: pd.DataFrame, breakdowns: pd.DataFrame, touches: pd.DataFrame, entries: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    rows = []
    periods = ["2022", "2023", "2024_2026", "combined_2022_2026_descriptive_only"]
    origin_groups = ["FORMER_S", "FORMER_A", "RS98_BREAKOUT", "RS96_97_BREAKOUT", "RS90_95_BREAKOUT", "ALL_FORMER_LEADERS"]
    regimes = ["NORMAL", "HIGH_DISPERSION", "NARROW_LEADERSHIP", "HIGH_D_OR_NARROW"]
    for period in periods:
        for origin in origin_groups:
            for regime in regimes:
                for rule in EXIT_RULES:
                    for model_type in spec["option_models"]:
                        def filt(df: pd.DataFrame, date_col: str = "hypothetical_entry_date") -> pd.Series:
                            m = pd.Series(True, index=df.index)
                            if period != "combined_2022_2026_descriptive_only" and date_col in df:
                                m &= df[date_col].astype(str).map(period_for).eq(period)
                            if origin != "ALL_FORMER_LEADERS" and "origin_type_group" in df:
                                m &= df["origin_type_group"].eq(origin)
                            if "regime_state" in df:
                                if regime == "HIGH_D_OR_NARROW":
                                    m &= df["regime_state"].isin(["HIGH_DISPERSION", "NARROW_LEADERSHIP"])
                                else:
                                    m &= df["regime_state"].eq(regime)
                            return m
                        g = option_rows[filt(option_rows) & option_rows["exit_rule"].eq(rule) & option_rows["option_model_type"].eq(model_type)].copy()
                        eps = episodes
                        if origin != "ALL_FORMER_LEADERS" and not eps.empty:
                            eps = eps[eps["origin_type_group"].eq(origin)]
                        row = {
                            "period": period,
                            "origin_type_group": origin,
                            "origin_RS_bucket": "ALL",
                            "regime_state": regime,
                            "setup_name": SETUP_NAME,
                            "exit_rule": rule,
                            "option_model_type": model_type,
                        }
                        row.update(summarize_cell(g, eps, breakdowns, touches, entries, spec))
                        rows.append(row)
    return pd.DataFrame(rows)


def interpretation(row: pd.Series, period_support: dict[tuple[str, str, str], int], spec: dict[str, Any]) -> str:
    n = int(row["completed_trade_count"])
    pf = safe_float(row.get("modeled_PF"))
    med = safe_float(row.get("modeled_median_return_pct"))
    if n < int(spec["sample_gates"]["minimum_sample"]):
        return "insufficient_sample"
    if pf is not None and pf < 1.20:
        return "not_viable"
    if (pf is None or pf < 1.50) and (
        safe_float(row.get("reached_minus_8pct_10d_rate")) and safe_float(row.get("reached_minus_8pct_10d_rate")) >= 0.35
    ):
        return "price_behavior_promising_option_model_weak"
    if pf is not None and pf >= 1.50 and (med is None or med <= 0):
        return "PF_above_1_5_but_median_negative"
    if pf is not None and pf >= 1.50 and bool(row.get("concentration_flag")):
        return "PF_above_1_5_but_concentrated"
    key = (row["origin_type_group"], row["regime_state"], row["option_model_type"])
    if pf is not None and pf >= 1.50 and period_support.get(key, 0) < 2:
        return "PF_above_1_5_single_period_only"
    mae_ok = safe_float(row.get("median_MAE_10d")) is not None and safe_float(row.get("median_MAE_10d")) <= float(spec["sample_gates"]["acceptable_median_mae_10d_max"])
    rec_ok = safe_float(row.get("recovered_retest_high_10d_rate")) is not None and safe_float(row.get("recovered_retest_high_10d_rate")) <= float(spec["sample_gates"]["acceptable_recovered_retest_high_10d_rate_max"])
    p90_ok = safe_float(row.get("p90_MAE_10d")) is not None and safe_float(row.get("p90_MAE_10d")) <= float(spec["sample_gates"]["acceptable_p90_mae_10d_max"])
    if n >= int(spec["sample_gates"]["preferred_sample"]) and pf is not None and pf >= 1.50 and med is not None and med > 0 and not bool(row.get("concentration_flag")) and period_support.get(key, 0) >= 2 and rec_ok and p90_ok:
        return "strong_research_candidate"
    if pf is not None and pf >= 1.50 and med is not None and med > 0 and not bool(row.get("concentration_flag")) and rec_ok and mae_ok:
        return "research_candidate"
    return "not_viable"


def add_interpretations(summary: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    qualifying = summary[
        (summary["period"].isin(["2022", "2023", "2024_2026"]))
        & (summary["modeled_PF"] >= 1.50)
        & (summary["modeled_median_return_pct"] > 0)
    ].copy()
    support = Counter(zip(qualifying["origin_type_group"], qualifying["regime_state"], qualifying["option_model_type"]))
    out = summary.copy()
    out["interpretation_label"] = out.apply(lambda r: interpretation(r, support, spec), axis=1)
    major = out[
        (out["period"].isin(["2022", "2023", "2024_2026", "combined_2022_2026_descriptive_only"]))
        & (out["origin_type_group"].eq("ALL_FORMER_LEADERS"))
        & (out["regime_state"].isin(["NORMAL", "HIGH_D_OR_NARROW"]))
    ]
    labels = {
        "created_at_utc": iso_now(),
        "label_rules_fixed": True,
        "labels_by_major_cell": major[
            ["period", "origin_type_group", "regime_state", "exit_rule", "option_model_type", "completed_trade_count", "modeled_PF", "modeled_median_return_pct", "concentration_flag", "interpretation_label"]
        ].to_dict("records"),
    }
    return out, labels


def best_rows(summary: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    g = summary.copy()
    for col, val in filters.items():
        if isinstance(val, list):
            g = g[g[col].isin(val)]
        else:
            g = g[g[col].eq(val)]
    if g.empty:
        return g
    return g.sort_values(["modeled_PF", "modeled_median_return_pct", "completed_trade_count"], ascending=[False, False, False]).head(1)


def build_comparisons(summary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    regime_rows = []
    for period in ["2022", "2023", "2024_2026", "combined_2022_2026_descriptive_only"]:
        left = best_rows(summary, {"period": period, "origin_type_group": "ALL_FORMER_LEADERS", "regime_state": "HIGH_D_OR_NARROW"})
        right = best_rows(summary, {"period": period, "origin_type_group": "ALL_FORMER_LEADERS", "regime_state": "NORMAL"})
        for label, rowdf in [("HIGH_D_OR_NARROW", left), ("NORMAL", right)]:
            if rowdf.empty:
                continue
            r = rowdf.iloc[0].to_dict()
            regime_rows.append({"period": period, "comparison_side": label, **r})
    regime = pd.DataFrame(regime_rows)
    origin = summary[(summary["regime_state"] == "HIGH_D_OR_NARROW") & (summary["origin_type_group"] != "ALL_FORMER_LEADERS")].copy()
    origin = origin.sort_values(["period", "modeled_PF"], ascending=[True, False])
    origin = origin.groupby(["period", "origin_type_group"], as_index=False).head(1)
    period = summary[(summary["origin_type_group"] == "ALL_FORMER_LEADERS") & (summary["regime_state"].isin(["NORMAL", "HIGH_D_OR_NARROW"]))].copy()
    period = period.sort_values(["period", "regime_state", "modeled_PF"], ascending=[True, True, False]).groupby(["period", "regime_state"], as_index=False).head(1)
    conc = summary[summary["completed_trade_count"] > 0][
        ["period", "origin_type_group", "regime_state", "exit_rule", "option_model_type", "completed_trade_count", "unique_ticker_count", "largest_single_ticker", "largest_single_ticker_share", "top_five_ticker_share", "concentration_flag"]
    ].copy()
    return regime, origin, period, conc


def build_source_lineage(spec: dict[str, Any], coverage: dict[str, Any], threshold: dict[str, Any]) -> dict[str, Any]:
    paths = {
        "scanner_source": "scripts/production_scanner_entry.py",
        "RS_implementation": "scripts/build_morita_bot_historical_baseline_v1.py plus 252-session close-return percentile in this study for RS breakout origins",
        "signal_baseline_source": spec["source_baseline_run_dir"] + "/morita_bot_baseline_panel.csv and " + spec["source_2023_signal_panel"],
        "breakout_definition": "close above prior 65-day high; S/A origins use existing Morita baseline signal rows",
        "moving_average_implementation": "pandas rolling SMA20/SMA50/SMA100/SMA200 on source OHLCV",
        "universe_source": spec["source_universe_path"],
        "OHLCV_source": spec["source_ohlcv_path"],
        "dispersion_regime_source": spec["source_regime_daily_panel"],
        "option_model_source": "src/morita_single_call_reference/black_scholes_reference.py with put parity formula in this study",
        "timing_convention": "entry next session open after retest rejection; regime observation date equals retest rejection date",
    }
    existing = {}
    for key, rel in paths.items():
        first = str(rel).split(" and ")[0]
        path = REPO_ROOT / first
        existing[key + "_exists"] = path.exists()
    return {
        "artifact_version": ARTIFACT_VERSION,
        "created_at_utc": iso_now(),
        "repository_head_at_run": git_head(),
        "lineage": paths,
        "existence_check": existing,
        "coverage": coverage,
        "threshold_inheritance": threshold,
        "limitations": [
            "No existing 2021 OHLCV warmup was found; 2022 is hard-blocked for RS-dependent adoption conclusions.",
            "Synthetic option values are fixed-IV references, not historical option fill reconstructions.",
            "This artifact is research-only and creates no live short signal.",
        ],
    }


def build_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for name in OUTPUT_FILES:
        if name == MANIFEST_NAME:
            continue
        path = output_dir / name
        if path.exists():
            files.append({"relative_path": name, "sha256": file_sha256(path), "bytes": path.stat().st_size})
    missing = [name for name in OUTPUT_FILES if name != MANIFEST_NAME and not (output_dir / name).exists()]
    manifest = {"artifact_version": ARTIFACT_VERSION, "created_at_utc": iso_now(), "files": files, "missing": missing, "unexpected": []}
    write_json(output_dir / MANIFEST_NAME, manifest)
    return manifest


def verify_manifest(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    manifest_path = output_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {"verified": False, "missing": [MANIFEST_NAME], "changed": [], "unexpected": []}
    manifest = load_json(manifest_path)
    missing = [name for name in OUTPUT_FILES if not (output_dir / name).exists()]
    changed = []
    for row in manifest.get("files", []):
        path = output_dir / row["relative_path"]
        if not path.exists() or file_sha256(path) != row["sha256"]:
            changed.append(row["relative_path"])
    actual = sorted(p.name for p in output_dir.iterdir() if p.is_file())
    unexpected = [name for name in actual if name not in OUTPUT_FILES]
    return {"verified": not missing and not changed and not unexpected, "missing": missing, "changed": changed, "unexpected": unexpected}


def write_summary(output_dir: Path, coverage: dict[str, Any], episodes: pd.DataFrame, breakdowns: pd.DataFrame, touches: pd.DataFrame, entries: pd.DataFrame, underlying: pd.DataFrame, options: pd.DataFrame, summary: pd.DataFrame, regime: pd.DataFrame, origin: pd.DataFrame, period: pd.DataFrame, labels: dict[str, Any]) -> None:
    origin_counts = episodes["origin_type_group"].value_counts().rename_axis("origin_type_group").reset_index(name="episode_count") if not episodes.empty else pd.DataFrame(columns=["origin_type_group", "episode_count"])
    best_pf = summary[(summary["completed_trade_count"] > 0)].sort_values("modeled_PF", ascending=False).head(10)
    outcome_cols = ["period", "regime_state", "completed_trade_count", "reached_minus_5pct_10d_rate", "reached_minus_8pct_10d_rate", "reached_minus_10pct_10d_rate", "reached_minus_15pct_20d_rate", "reached_minus_20pct_20d_rate", "recovered_retest_high_10d_rate", "median_MFE_10d", "median_MAE_10d"]
    outcome = summary[(summary["origin_type_group"] == "ALL_FORMER_LEADERS") & (summary["exit_rule"] == "RULE_A_10D_TIME_EXIT") & summary["option_model_type"].str.startswith("long_put")][outcome_cols].drop_duplicates()
    lines = [
        f"# Morita Former Leader Retest Short v1",
        "",
        "Research-only former leader retest rejection short/put study. No live bot, long S logic, regime sizing, broker, account, order, or notification path was changed.",
        "",
        "## Coverage",
        "",
        f"- OHLCV source min date: `{coverage.get('min_date')}`",
        f"- OHLCV source max date: `{coverage.get('max_date')}`",
        f"- 2022 status: `blocked_missing_2021_rs_warmup`" if not coverage.get("has_required_2021_warmup_for_2022") else "- 2022 status: `available`",
        "",
        "## Funnel",
        "",
        f"- Former leader episodes: `{len(episodes)}`",
        f"- Primary breakdowns: `{len(breakdowns)}`",
        f"- Retest touches: `{len(touches)}`",
        f"- Retest rejection entries: `{len(entries)}`",
        "",
        "## Episode Counts By Origin",
        "",
        md_table(origin_counts),
        "",
        "## Underlying Outcome Summary",
        "",
        md_table(outcome, 20),
        "",
        "## Best Modeled Option Cells",
        "",
        md_table(best_pf[["period", "origin_type_group", "regime_state", "exit_rule", "option_model_type", "completed_trade_count", "modeled_PF", "modeled_median_return_pct", "concentration_flag", "interpretation_label"]], 10),
        "",
        "## Primary Regime Comparison",
        "",
        md_table(regime[["period", "comparison_side", "completed_trade_count", "exit_rule", "option_model_type", "modeled_PF", "modeled_median_return_pct", "concentration_flag", "interpretation_label"]] if not regime.empty else regime, 20),
        "",
        "## Origin Comparison In HIGH_D_OR_NARROW",
        "",
        md_table(origin[["period", "origin_type_group", "completed_trade_count", "exit_rule", "option_model_type", "modeled_PF", "modeled_median_return_pct", "concentration_flag", "interpretation_label"]] if not origin.empty else origin, 30),
        "",
        "## Period Comparison",
        "",
        md_table(period[["period", "regime_state", "completed_trade_count", "exit_rule", "option_model_type", "modeled_PF", "modeled_median_return_pct", "interpretation_label"]] if not period.empty else period, 20),
        "",
        "## Interpretation",
        "",
        "- No group should be treated as live-tradable from this study alone.",
        "- `2022` cannot be evaluated with the available approved source tree because 2021 OHLCV warmup is missing.",
        "- Rising-D fields were logged only as diagnostics and do not drive adoption labels.",
        "",
        "## Required Confirmations",
        "",
        "- no live bot was changed",
        "- no long S logic changed",
        "- no regime threshold was retuned",
        "- no broker/account/order path was accessed",
        "- no short signal was activated",
    ]
    (output_dir / "study_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    CHATGPT_BUNDLE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    spec = load_json(SPEC_PATH)
    safe_clean_output_dir(output_dir)
    threshold = verify_thresholds(spec)
    write_json(output_dir / "threshold_inheritance.json", threshold)
    price, coverage = load_price_panel(spec)
    signal_origins = load_signal_origins(spec)
    rs_origins = build_rs_breakout_origins(price, spec)
    origins = pd.concat([signal_origins, rs_origins], ignore_index=True)
    episodes = dedupe_episodes(origins, price, threshold, spec)
    breakdowns = detect_breakdowns(episodes, price, spec)
    touches, entries = detect_retests(breakdowns, price, spec)
    regime_panel = build_regime_panel(spec, threshold)
    underlying, option_rows = compute_outcomes(entries, price, regime_panel, spec)
    summary = cell_summary(option_rows, episodes, breakdowns, touches, entries, spec)
    summary, labels = add_interpretations(summary, spec)
    regime_cmp, origin_cmp, period_cmp, concentration_diag = build_comparisons(summary)
    lineage = build_source_lineage(spec, coverage, threshold)
    option_lineage = {
        "model_source": "Black-Scholes fixed-IV reference with put pricing in scripts/build_morita_former_leader_retest_short_v1.py",
        "not_historical_option_fill_reconstruction": True,
        "not_broker_executable": True,
        "models": spec["option_models"],
    }
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "created_at_utc": iso_now(),
        "repository_head_at_run": git_head(),
        "research_only": True,
        "actionization_allowed": False,
        "run_status": "completed_with_2022_hard_blocker" if not coverage["has_required_2021_warmup_for_2022"] else "completed",
        "period_2022_status": "blocked_missing_2021_rs_warmup" if not coverage["has_required_2021_warmup_for_2022"] else "computed",
        "former_leader_episode_count": int(len(episodes)),
        "breakdown_count": int(len(breakdowns)),
        "retest_touch_count": int(len(touches)),
        "retest_rejection_entry_count": int(len(entries)),
        "guardrails": {
            "no_live_bot_changed": True,
            "no_long_s_logic_changed": True,
            "no_regime_threshold_retuned": True,
            "no_broker_account_order_path_accessed": True,
            "no_short_signal_activated": True,
        },
    }
    write_json(output_dir / "source_lineage.json", lineage)
    write_json(output_dir / "option_model_lineage.json", option_lineage)
    write_dataframe(output_dir / "former_leader_episode_panel.csv", episodes)
    write_dataframe(output_dir / "breakdown_panel.csv", breakdowns)
    write_dataframe(output_dir / "retest_touch_panel.csv", touches)
    write_dataframe(output_dir / "retest_rejection_entry_panel.csv", entries)
    write_dataframe(output_dir / "underlying_outcome_panel.csv", underlying)
    write_dataframe(output_dir / "option_model_outcome_panel.csv", option_rows)
    write_dataframe(output_dir / "cell_summary.csv", summary)
    write_dataframe(output_dir / "regime_comparison.csv", regime_cmp)
    write_dataframe(output_dir / "origin_comparison_bad_regime.csv", origin_cmp)
    write_dataframe(output_dir / "period_comparison.csv", period_cmp)
    write_dataframe(output_dir / "concentration_diagnostics.csv", concentration_diag)
    write_json(output_dir / "interpretation_labels.json", labels)
    write_json(output_dir / "study_receipt.json", receipt)
    write_summary(output_dir, coverage, episodes, breakdowns, touches, entries, underlying, option_rows, summary, regime_cmp, origin_cmp, period_cmp, labels)
    manifest = build_manifest(output_dir)
    receipt["manifest_verified"] = verify_manifest(output_dir)["verified"]
    write_json(output_dir / "study_receipt.json", receipt)
    manifest = build_manifest(output_dir)
    return {"receipt": receipt, "manifest": manifest}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args(argv)
    if not args.run and not args.verify:
        parser.error("one of --run or --verify is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = Path(args.output_dir)
    if args.run:
        result = run(output_dir)
        print(json.dumps({"status": result["receipt"]["run_status"], "entries": result["receipt"]["retest_rejection_entry_count"]}, sort_keys=True))
    if args.verify:
        result = verify_manifest(output_dir)
        print(json.dumps(result, sort_keys=True))
        if not result["verified"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
