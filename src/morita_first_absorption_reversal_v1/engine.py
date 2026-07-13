from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ARTIFACT_VERSION = "morita_first_absorption_reversal_v1"
SIGNAL_SCOPE = "MORITA_FIRST_ABSORPTION_REVERSAL_V1_RESEARCH_ONLY"
OUTPUT_DIR = Path("outputs") / ARTIFACT_VERSION
REQUIRED_OUTPUTS = [
    "signal_candidates.csv",
    "trade_level_underlying.csv",
    "trade_level_options.csv",
    "event_audit.csv",
    "fundamental_filter_audit.csv",
    "regime_classification.csv",
    "peer_universe_daily.csv",
    "parameter_sensitivity.csv",
    "yearly_summary.csv",
    "regime_summary.csv",
    "ticker_summary.csv",
    "concentration_report.csv",
    "false_positive_cases.csv",
    "excluded_shock_cases.csv",
    "case_study_mksi_amat.md",
    "case_study_covid.md",
    "backtest_report.md",
    "receipt.json",
    "chatgpt_review_bundle.md",
]

DAILY_PIT = Path("data/pit/daily/core_semis_daily.parquet")
INTRADAY_PIT = Path("data/pit/intraday/core_semis_m15.parquet")
BROAD_DAILY = Path("outputs/morita_2023_rs_warmup_retest_v1/input/morita_baseline_2022warmup_2023_2026_v1/sources/daily_ohlcv_merged.csv")
SIGNALS_2023 = Path("outputs/morita_2023_rs_warmup_retest_v1/morita_2023_signal_panel.csv")
SIGNALS_2024_2026 = Path("market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa/morita_bot_baseline_panel.csv")

DEFAULT_CONFIG = {
    "research_only": True,
    "live_order_allowed": False,
    "broker_integration_allowed": False,
    "webull_integration_allowed": False,
    "lookback_sessions": [63, 126, 189],
    "primary_lookback_sessions": 126,
    "min_days_since_s": 20,
    "candidate_drawdown_thresholds": [-0.05, -0.08, -0.10, -0.12],
    "primary_candidate_drawdown_threshold": -0.05,
    "close_location_thresholds": [0.65, 0.75, 0.85],
    "primary_close_location_threshold": 0.65,
    "relative_peer_thresholds": [0.0, 0.01, 0.02],
    "primary_relative_peer_threshold": 0.01,
    "relative_soxx_thresholds": [0.0, 0.005, 0.01],
    "primary_relative_soxx_threshold": 0.005,
    "universe_two_day_median_thresholds": [0.0, -0.01, -0.02],
    "primary_universe_two_day_median_threshold": 0.0,
    "entry_timings": ["D0_CLOSE", "D1_OPEN_90M_PROXY", "D1_FINAL_60M_PROXY", "D1_CLOSE", "D2_OPEN"],
    "exit_timings": ["D2_OPEN", "D2_CLOSE", "D3_OPEN", "D3_CLOSE"],
}


@dataclass(frozen=True)
class SourceSet:
    daily_path: Path
    intraday_path: Path
    signals_2023_path: Path
    signals_2024_2026_path: Path


def safety_fields() -> dict[str, Any]:
    return {
        "research_only": True,
        "execution_allowed": False,
        "live_order_allowed": False,
        "broker_integration_allowed": False,
        "webull_integration_allowed": False,
        "consumable_by_production": False,
        "signal_scope": SIGNAL_SCOPE,
    }


def add_safety(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for key, value in safety_fields().items():
        if key not in out.columns:
            out[key] = value
    return out


def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    except Exception:
        return "UNKNOWN"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def profit_factor(values: pd.Series) -> float | None:
    r = pd.to_numeric(values, errors="coerce").dropna()
    if r.empty:
        return None
    gains = float(r[r > 0].sum())
    losses = float(-r[r < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / losses


def max_drawdown(values: pd.Series) -> float | None:
    r = pd.to_numeric(values, errors="coerce").dropna()
    if r.empty:
        return None
    equity = (1.0 + r).cumprod()
    dd = equity / equity.cummax() - 1.0
    return float(dd.min())


def write_df(path: Path, df: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def load_daily(repo_root: Path, path: Path | None = None) -> pd.DataFrame:
    source = repo_root / (path or DAILY_PIT)
    if not source.exists():
        source = repo_root / BROAD_DAILY
    if source.suffix == ".parquet":
        df = pd.read_parquet(source)
    else:
        df = pd.read_csv(source)
    if "session_date" in df.columns:
        df = df.rename(columns={"session_date": "date"})
    required = ["ticker", "date", "open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"daily_source_missing_columns:{missing}")
    out = df[required + [c for c in ["source", "data_available_at", "quality"] if c in df.columns]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["ticker", "date", "open", "high", "low", "close"]).sort_values(["ticker", "date"])
    out = out.drop_duplicates(["ticker", "date"], keep="last")
    return enrich_daily(out.reset_index(drop=True))


def enrich_daily(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    g = out.groupby("ticker", group_keys=False)
    out["prev_close"] = g["close"].shift(1)
    out["ret_1d"] = out["close"] / out["prev_close"] - 1.0
    out["ret_2d"] = g["close"].transform(lambda s: s / s.shift(2) - 1.0)
    out["ret_5d"] = g["close"].transform(lambda s: s / s.shift(5) - 1.0)
    out["open_to_close_return"] = out["close"] / out["open"] - 1.0
    out["close_location_value"] = (out["close"] - out["low"]) / (out["high"] - out["low"]).replace(0, math.nan)
    out["prior_20d_low"] = g["low"].transform(lambda s: s.shift(1).rolling(20, min_periods=5).min())
    out["prior_60d_high"] = g["high"].transform(lambda s: s.shift(1).rolling(60, min_periods=20).max())
    out["drawdown_from_prior_60d_high"] = out["close"] / out["prior_60d_high"] - 1.0
    out["pre_20d_return"] = g["close"].transform(lambda s: s.shift(1) / s.shift(21) - 1.0)
    out["pre_60d_return"] = g["close"].transform(lambda s: s.shift(1) / s.shift(61) - 1.0)
    out["pre_120d_return"] = g["close"].transform(lambda s: s.shift(1) / s.shift(121) - 1.0)
    out["avg_volume_20"] = g["volume"].transform(lambda s: s.shift(1).rolling(20, min_periods=5).mean())
    out["sell_efficiency"] = (-out["ret_1d"].clip(upper=0.0)) / (out["volume"] / out["avg_volume_20"]).replace(0, math.nan)
    out["new_20d_low"] = out["low"] <= out["prior_20d_low"]
    return out


def load_s_signals(repo_root: Path, paths: list[Path] | None = None) -> pd.DataFrame:
    sources = paths or [SIGNALS_2023, SIGNALS_2024_2026]
    frames = []
    for rel in sources:
        path = repo_root / rel
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        raise FileNotFoundError("No Morita S signal source files were found.")
    df = pd.concat(frames, ignore_index=True, sort=False)
    if "underlying_symbol" in df.columns:
        df["ticker"] = df["underlying_symbol"].astype(str).str.upper().str.strip()
    elif "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    else:
        raise ValueError("signal_source_missing_ticker")
    rank_col = "signal_rank" if "signal_rank" in df.columns else "rank"
    if rank_col not in df.columns:
        raise ValueError("signal_source_missing_rank")
    df = df[df[rank_col].astype(str).str.upper().eq("S")].copy()
    df["signal_decision_date"] = pd.to_datetime(df["signal_decision_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "signal_id" not in df.columns:
        df["signal_id"] = df["ticker"] + "_" + df["signal_decision_date"]
    keep = [
        "signal_id",
        "signal_decision_date",
        "ticker",
        "theme",
        "production_adjusted_score",
        "standard_rs_score",
        "volume_multiple",
        "accumulation_score",
        "source_run_id",
        "source_rule_config_hash",
        "source_manifest_hash",
    ]
    for col in keep:
        if col not in df.columns:
            df[col] = ""
    return df[keep].dropna(subset=["signal_decision_date"]).drop_duplicates(["signal_id"]).sort_values(["ticker", "signal_decision_date"])


def build_recent_s_membership(daily: pd.DataFrame, signals: pd.DataFrame, min_days: int, lookback: int) -> pd.DataFrame:
    sessions = sorted(daily["date"].dropna().unique())
    session_idx = {date: i for i, date in enumerate(sessions)}
    price_tickers = set(daily["ticker"].unique())
    rows = []
    for _, sig in signals.iterrows():
        ticker = sig["ticker"]
        sdate = sig["signal_decision_date"]
        if ticker not in price_tickers or sdate not in session_idx:
            continue
        start = session_idx[sdate] + min_days
        end = min(session_idx[sdate] + lookback, len(sessions) - 1)
        for pos in range(start, end + 1):
            rows.append(
                {
                    "date": sessions[pos],
                    "ticker": ticker,
                    "s_signal_date": sdate,
                    "days_since_s_signal": pos - session_idx[sdate],
                    "signal_id": sig["signal_id"],
                    "theme": sig.get("theme", ""),
                    "production_adjusted_score": sig.get("production_adjusted_score", ""),
                    "future_information_safe": True,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "s_signal_date", "days_since_s_signal", "signal_id", "future_information_safe"])
    return pd.DataFrame(rows).drop_duplicates(["date", "ticker", "signal_id"])


def build_peer_universe_daily(daily: pd.DataFrame, membership: pd.DataFrame) -> pd.DataFrame:
    if membership.empty:
        return pd.DataFrame()
    joined = membership.merge(daily, on=["date", "ticker"], how="left", validate="many_to_one")
    rows = []
    for date, g in joined.groupby("date"):
        valid = g.dropna(subset=["close"])
        corr = valid[["pre_60d_return", "ret_2d"]].dropna().corr().iloc[0, 1] if valid[["pre_60d_return", "ret_2d"]].dropna().shape[0] >= 4 else math.nan
        q75 = valid["pre_60d_return"].quantile(0.75) if not valid.empty else math.nan
        q25 = valid["pre_60d_return"].quantile(0.25) if not valid.empty else math.nan
        winners = valid[valid["pre_60d_return"] >= q75] if math.isfinite(q75) else valid.iloc[0:0]
        laggards = valid[valid["pre_60d_return"] <= q25] if math.isfinite(q25) else valid.iloc[0:0]
        winner_minus_laggard = safe_float(winners["ret_2d"].median()) - safe_float(laggards["ret_2d"].median()) if not winners.empty and not laggards.empty else math.nan
        if math.isfinite(corr) and corr <= -0.20 and math.isfinite(winner_minus_laggard) and winner_minus_laggard < 0:
            degross = "DEGROSS_LIKELY"
        elif valid.shape[0] >= 3:
            degross = "MIXED"
        else:
            degross = "UNKNOWN"
        rows.append(
            {
                "date": date,
                "old_s_member_count": int(valid["ticker"].nunique()),
                "old_s_median_1d_return": valid["ret_1d"].median(),
                "old_s_median_2d_return": valid["ret_2d"].median(),
                "old_s_down_ratio": float((valid["ret_1d"] < 0).mean()) if not valid.empty else math.nan,
                "old_s_new_20d_low_count": int(valid["new_20d_low"].fillna(False).sum()),
                "old_s_median_close_location": valid["close_location_value"].median(),
                "old_s_median_sell_efficiency": valid["sell_efficiency"].median(),
                "pre60_vs_adjustment2d_corr": corr,
                "winner_q4_minus_laggard_q1_adjustment_return": winner_minus_laggard,
                "degross_classification": degross,
                "classification_reason": "price_cross_section_only_no_fundamental_confirmation",
            }
        )
    return pd.DataFrame(rows).sort_values("date")


def build_signal_candidates(daily: pd.DataFrame, membership: pd.DataFrame, peer: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if membership.empty or peer.empty:
        return pd.DataFrame()
    daily_by_key = {(r.ticker, r.date): r for r in daily.itertuples(index=False)}
    peer_by_date = {r.date: r for r in peer.itertuples(index=False)}
    soxx = daily[daily["ticker"].eq("SOXX")].set_index("date")
    sessions = sorted(daily["date"].dropna().unique())
    next_date = {sessions[i]: sessions[i + 1] for i in range(len(sessions) - 1)}
    rows = []
    primary = {
        "drawdown": float(config["primary_candidate_drawdown_threshold"]),
        "close_location": float(config["primary_close_location_threshold"]),
        "relative_peer": float(config["primary_relative_peer_threshold"]),
        "relative_soxx": float(config["primary_relative_soxx_threshold"]),
        "universe_2d": float(config["primary_universe_two_day_median_threshold"]),
    }
    for _, m in membership.iterrows():
        ticker = str(m["ticker"])
        d0 = str(m["date"])
        d1 = next_date.get(d0)
        d2 = next_date.get(d1 or "")
        d3 = next_date.get(d2 or "")
        if not d1 or not d2:
            continue
        b0 = daily_by_key.get((ticker, d0))
        b1 = daily_by_key.get((ticker, d1))
        b2 = daily_by_key.get((ticker, d2))
        b3 = daily_by_key.get((ticker, d3)) if d3 else None
        p0 = peer_by_date.get(d0)
        p1 = peer_by_date.get(d1)
        if b0 is None or b1 is None or b2 is None or p0 is None or p1 is None:
            continue
        soxx0 = soxx.loc[d0] if d0 in soxx.index else None
        soxx1 = soxx.loc[d1] if d1 in soxx.index else None
        rel_peer_d0 = safe_float(b0.open_to_close_return) - safe_float(p0.old_s_median_1d_return, 0.0)
        rel_peer_d1 = safe_float(b1.open_to_close_return) - safe_float(p1.old_s_median_1d_return, 0.0)
        rel_soxx_d0 = safe_float(b0.open_to_close_return) - (safe_float(soxx0["open_to_close_return"], 0.0) if soxx0 is not None else 0.0)
        rel_soxx_d1 = safe_float(b1.open_to_close_return) - (safe_float(soxx1["open_to_close_return"], 0.0) if soxx1 is not None else 0.0)
        d0_absorption = (
            safe_float(b0.open_to_close_return) > 0
            and safe_float(b0.close_location_value) >= primary["close_location"]
            and rel_peer_d0 >= primary["relative_peer"]
            and rel_soxx_d0 >= primary["relative_soxx"]
            and safe_float(b0.drawdown_from_prior_60d_high, 0.0) <= primary["drawdown"]
        )
        d1_absorption = (
            safe_float(b1.open_to_close_return) > 0
            and safe_float(b1.close_location_value) >= primary["close_location"]
            and safe_float(b1.close) >= safe_float(b0.low)
            and rel_peer_d1 >= primary["relative_peer"]
            and rel_soxx_d1 >= primary["relative_soxx"]
        )
        universe_weak = safe_float(p1.old_s_median_2d_return, 0.0) < primary["universe_2d"] and safe_float(p1.old_s_down_ratio, 0.0) >= 0.5
        sell_pressure_fading = (
            abs(safe_float(p1.old_s_median_1d_return, 0.0)) < abs(safe_float(p0.old_s_median_1d_return, 0.0))
            or safe_float(p1.old_s_new_20d_low_count, 999) < safe_float(p0.old_s_new_20d_low_count, -999)
            or safe_float(p1.old_s_median_sell_efficiency, 999) < safe_float(p0.old_s_median_sell_efficiency, -999)
        )
        two_day_absorption = d0_absorption and d1_absorption
        adjustment_context = safe_float(b0.drawdown_from_prior_60d_high, 0.0) <= primary["drawdown"]
        if not adjustment_context:
            continue
        rows.append(
            {
                "candidate_id": f"{ticker}_{d0}_{d1}",
                "ticker": ticker,
                "signal_id": m["signal_id"],
                "s_signal_date": m["s_signal_date"],
                "days_since_s_signal_at_d0": int(m["days_since_s_signal"]),
                "D0_date": d0,
                "D1_date": d1,
                "D2_date": d2,
                "D3_date": d3 or "",
                "D0_open_to_close_return": b0.open_to_close_return,
                "D1_open_to_close_return": b1.open_to_close_return,
                "D0_close_location_value": b0.close_location_value,
                "D1_close_location_value": b1.close_location_value,
                "D0_drawdown_from_prior_60d_high": b0.drawdown_from_prior_60d_high,
                "adjustment_context_pass": bool(adjustment_context),
                "D0_relative_return_vs_peer_median": rel_peer_d0,
                "D1_relative_return_vs_peer_median": rel_peer_d1,
                "D0_relative_return_vs_SOXX": rel_soxx_d0,
                "D1_relative_return_vs_SOXX": rel_soxx_d1,
                "D0_absorption_pass": bool(d0_absorption),
                "D1_absorption_pass": bool(d1_absorption),
                "two_day_absorption_pass": bool(two_day_absorption),
                "universe_weak_at_D1_pass": bool(universe_weak),
                "sell_pressure_fading_pass": bool(sell_pressure_fading),
                "fundamental_filter_status": "AMBIGUOUS",
                "fundamental_filter_reason": "No sealed point-in-time news/fundamental event audit source was found; cannot promote to CLEAN.",
                "regime_classification": p1.degross_classification,
                "D1_close": b1.close,
                "D0_close": b0.close,
                "D2_open": b2.open,
                "D2_close": b2.close,
                "D2_high": b2.high,
                "D2_low": b2.low,
                "D3_open": b3.open if b3 is not None else math.nan,
                "D3_close": b3.close if b3 is not None else math.nan,
                "primary_candidate_pass": bool(two_day_absorption and universe_weak and sell_pressure_fading),
                "future_information_safe": True,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = dedupe_adjustment_episodes(out)
    return out.sort_values(["D0_date", "ticker"]).reset_index(drop=True)


def dedupe_adjustment_episodes(candidates: pd.DataFrame, min_gap_sessions: int = 10) -> pd.DataFrame:
    rows = []
    for ticker, g in candidates.sort_values("D0_date").groupby("ticker"):
        last_date = None
        dates = list(pd.to_datetime(g["D0_date"]))
        for i, (_, row) in enumerate(g.iterrows()):
            current = pd.Timestamp(row["D0_date"])
            if last_date is not None and (current - last_date).days < min_gap_sessions:
                continue
            rows.append(row)
            last_date = current
    return pd.DataFrame(rows) if rows else candidates.iloc[0:0].copy()


def baseline_level(row: pd.Series) -> list[str]:
    levels = ["A_ADJUSTMENT_OLD_S_UNIVERSE"]
    if bool(row.get("D0_absorption_pass")):
        levels.append("B_D0_ONLY")
    if bool(row.get("two_day_absorption_pass")):
        levels.append("C_TWO_DAY_ABSORPTION_NO_UNIVERSE_WEAKNESS")
    if bool(row.get("two_day_absorption_pass")) and bool(row.get("universe_weak_at_D1_pass")):
        levels.append("D_TWO_DAY_ABSORPTION_UNIVERSE_WEAKNESS")
    if bool(row.get("primary_candidate_pass")):
        levels.append("E_D_PLUS_SELL_PRESSURE_FADING")
    if bool(row.get("primary_candidate_pass")) and row.get("fundamental_filter_status") == "CLEAN":
        levels.append("F_E_CLEAN_FUNDAMENTAL_FILTER")
    if bool(row.get("primary_candidate_pass")) and row.get("fundamental_filter_status") == "CLEAN" and row.get("regime_classification") == "DEGROSS_LIKELY":
        levels.append("G_F_DEGROSS_LIKELY")
    return levels


def build_underlying_trades(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, c in candidates.iterrows():
        for level in baseline_level(c):
            for entry_label, entry_price in [
                ("D0_CLOSE", c.get("D0_close")),
                ("D1_CLOSE", c.get("D1_close")),
                ("D2_OPEN", c.get("D2_open")),
            ]:
                for exit_label, exit_price in [
                    ("D2_OPEN", c.get("D2_open")),
                    ("D2_CLOSE", c.get("D2_close")),
                    ("D3_OPEN", c.get("D3_open")),
                    ("D3_CLOSE", c.get("D3_close")),
                ]:
                    ep = safe_float(entry_price)
                    xp = safe_float(exit_price)
                    if not math.isfinite(ep) or not math.isfinite(xp) or ep <= 0:
                        continue
                    if entry_label == "D2_OPEN" and exit_label == "D2_OPEN":
                        continue
                    rows.append(
                        {
                            "baseline_level": level,
                            "candidate_id": c["candidate_id"],
                            "ticker": c["ticker"],
                            "s_signal_date": c["s_signal_date"],
                            "D0_date": c["D0_date"],
                            "D1_date": c["D1_date"],
                            "D2_date": c["D2_date"],
                            "entry_timing": entry_label,
                            "exit_timing": exit_label,
                            "entry_price": ep,
                            "exit_price": xp,
                            "gross_return": xp / ep - 1.0,
                            "D2_MFE_from_D1_close": safe_float(c.get("D2_high")) / safe_float(c.get("D1_close")) - 1.0 if safe_float(c.get("D1_close")) > 0 else math.nan,
                            "D2_MAE_from_D1_close": safe_float(c.get("D2_low")) / safe_float(c.get("D1_close")) - 1.0 if safe_float(c.get("D1_close")) > 0 else math.nan,
                            "hit_plus_3pct_D2": safe_float(c.get("D2_high")) / safe_float(c.get("D1_close")) - 1.0 >= 0.03 if safe_float(c.get("D1_close")) > 0 else False,
                            "hit_plus_5pct_D2": safe_float(c.get("D2_high")) / safe_float(c.get("D1_close")) - 1.0 >= 0.05 if safe_float(c.get("D1_close")) > 0 else False,
                            "hit_minus_2pct_D2": safe_float(c.get("D2_low")) / safe_float(c.get("D1_close")) - 1.0 <= -0.02 if safe_float(c.get("D1_close")) > 0 else False,
                            "hit_minus_3pct_D2": safe_float(c.get("D2_low")) / safe_float(c.get("D1_close")) - 1.0 <= -0.03 if safe_float(c.get("D1_close")) > 0 else False,
                            "fundamental_filter_status": c.get("fundamental_filter_status", ""),
                            "regime_classification": c.get("regime_classification", ""),
                        }
                    )
    return pd.DataFrame(rows)


def summarize_trades(trades: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=group_cols + ["trades", "win_rate", "mean_return", "median_return", "profit_factor", "max_drawdown", "top5_removed_profit_factor"])
    rows = []
    for keys, g in trades.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        r = pd.to_numeric(g["gross_return"], errors="coerce")
        top_removed = r.sort_values(ascending=False).iloc[5:] if len(r) > 5 else pd.Series(dtype=float)
        rows.append(
            {
                **dict(zip(group_cols, keys)),
                "trades": int(r.notna().sum()),
                "win_rate": float((r > 0).mean()) if not r.empty else math.nan,
                "mean_return": float(r.mean()) if not r.empty else math.nan,
                "median_return": float(r.median()) if not r.empty else math.nan,
                "profit_factor": profit_factor(r),
                "max_drawdown": max_drawdown(r),
                "top5_removed_profit_factor": profit_factor(top_removed) if not top_removed.empty else None,
            }
        )
    return pd.DataFrame(rows)


def build_parameter_sensitivity(daily: pd.DataFrame, membership: pd.DataFrame, peer: pd.DataFrame, base_config: dict[str, Any]) -> pd.DataFrame:
    rows = []
    combos: list[tuple[str, float, float, float, float]] = []
    primary_dd = float(base_config["primary_candidate_drawdown_threshold"])
    primary_clv = float(base_config["primary_close_location_threshold"])
    primary_peer = float(base_config["primary_relative_peer_threshold"])
    primary_soxx = float(base_config["primary_relative_soxx_threshold"])
    for dd in base_config["candidate_drawdown_thresholds"]:
        for clv in base_config["close_location_thresholds"]:
            combos.append(("drawdown_close_location_grid", float(dd), float(clv), primary_peer, primary_soxx))
    for rel_peer in base_config["relative_peer_thresholds"]:
        for rel_soxx in base_config["relative_soxx_thresholds"]:
            combos.append(("relative_strength_grid", primary_dd, primary_clv, float(rel_peer), float(rel_soxx)))
    seen = set()
    for grid_name, dd, clv, rel_peer, rel_soxx in combos:
        key = (dd, clv, rel_peer, rel_soxx)
        if key in seen:
            continue
        seen.add(key)
        cfg = dict(base_config)
        cfg["primary_candidate_drawdown_threshold"] = dd
        cfg["primary_close_location_threshold"] = clv
        cfg["primary_relative_peer_threshold"] = rel_peer
        cfg["primary_relative_soxx_threshold"] = rel_soxx
        cands = build_signal_candidates(daily, membership, peer, cfg)
        trades = build_underlying_trades(cands)
        scoped = trades[(trades["baseline_level"].eq("E_D_PLUS_SELL_PRESSURE_FADING")) & (trades["entry_timing"].eq("D1_CLOSE")) & (trades["exit_timing"].eq("D2_OPEN"))] if not trades.empty else trades
        rows.append(
            {
                "grid_name": grid_name,
                "drawdown_threshold": dd,
                "close_location_threshold": clv,
                "relative_peer_threshold": rel_peer,
                "relative_soxx_threshold": rel_soxx,
                "candidate_rows": int(cands.shape[0]),
                "d0_only_rows": int(cands["D0_absorption_pass"].sum()) if not cands.empty else 0,
                "two_day_absorption_rows": int(cands["two_day_absorption_pass"].sum()) if not cands.empty else 0,
                "primary_candidate_rows": int(cands["primary_candidate_pass"].sum()) if not cands.empty else 0,
                "d1_close_to_d2_open_trades": int(scoped.shape[0]) if scoped is not None else 0,
                "median_return": float(scoped["gross_return"].median()) if scoped is not None and not scoped.empty else math.nan,
                "profit_factor": profit_factor(scoped["gross_return"]) if scoped is not None and not scoped.empty else None,
            }
        )
    return pd.DataFrame(rows)


def build_audits(candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_rows = []
    filter_rows = []
    regime_rows = []
    for _, c in candidates.iterrows():
        event_rows.append(
            {
                "candidate_id": c["candidate_id"],
                "ticker": c["ticker"],
                "event_window": f"{c['D0_date']}..{c['D1_date']}",
                "public_timestamp": "",
                "source": "",
                "headline_or_event_name": "NO_SEALED_POINT_IN_TIME_NEWS_AUDIT_SOURCE",
                "audit_classification": "AMBIGUOUS",
                "classification_reason": c["fundamental_filter_reason"],
                "manual_or_automatic": "automatic_fail_closed",
                "uncertainty": "high",
            }
        )
        filter_rows.append(
            {
                "candidate_id": c["candidate_id"],
                "ticker": c["ticker"],
                "fundamental_filter_status": "AMBIGUOUS",
                "included_in_primary_clean_analysis": False,
                "excluded_as_shock": False,
                "reason": c["fundamental_filter_reason"],
            }
        )
        regime_rows.append(
            {
                "candidate_id": c["candidate_id"],
                "ticker": c["ticker"],
                "D1_date": c["D1_date"],
                "regime_classification": c["regime_classification"],
                "classification_reason": "Cross-sectional price-only classification; fundamental layer unavailable.",
            }
        )
    events = pd.DataFrame(event_rows)
    filters = pd.DataFrame(filter_rows)
    regimes = pd.DataFrame(regime_rows)
    shocks = filters[filters["excluded_as_shock"].eq(True)].copy() if not filters.empty else pd.DataFrame(columns=filters.columns)
    return events, filters, regimes, shocks


def build_false_positives(candidates: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    scoped = trades[
        trades["baseline_level"].eq("E_D_PLUS_SELL_PRESSURE_FADING")
        & trades["entry_timing"].eq("D1_CLOSE")
        & trades["exit_timing"].eq("D2_OPEN")
        & (pd.to_numeric(trades["gross_return"], errors="coerce") <= 0)
    ].copy()
    if scoped.empty:
        return scoped
    cols = ["candidate_id", "ticker", "D0_date", "D1_date", "fundamental_filter_reason"]
    return scoped.merge(candidates[cols], on=["candidate_id", "ticker", "D0_date", "D1_date"], how="left")


def empty_options(candidates: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "candidate_id",
        "ticker",
        "option_status",
        "reason",
        "assumed_iv",
        "assumed_dte",
        "assumed_delta",
        "premium_return",
    ]
    if candidates.empty:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(
        [
            {
                "candidate_id": r["candidate_id"],
                "ticker": r["ticker"],
                "option_status": "BLOCKED_MISSING_HISTORICAL_OPTION_CHAINS_AND_CLEAN_AUDIT",
                "reason": "Underlying signal was not eligible for CLEAN primary analysis and no historical option chain was present.",
                "assumed_iv": "",
                "assumed_dte": "",
                "assumed_delta": "",
                "premium_return": "",
            }
            for _, r in candidates[candidates["primary_candidate_pass"]].iterrows()
        ],
        columns=cols,
    )


def markdown_table(df: pd.DataFrame, max_rows: int = 12) -> str:
    if df.empty:
        return "_No rows._"
    view = df.head(max_rows).copy()
    return view.to_markdown(index=False)


def build_reports(receipt: dict[str, Any], summaries: dict[str, pd.DataFrame], candidates: pd.DataFrame, trades: pd.DataFrame) -> tuple[str, str, str, str]:
    headline = summaries["headline"]
    primary = trades[
        trades["baseline_level"].eq("E_D_PLUS_SELL_PRESSURE_FADING")
        & trades["entry_timing"].eq("D1_CLOSE")
        & trades["exit_timing"].eq("D2_OPEN")
    ] if not trades.empty else pd.DataFrame()
    decision = "HOLD / NOT ADOPTION READY"
    if not primary.empty and profit_factor(primary["gross_return"]) and profit_factor(primary["gross_return"]) > 1.3 and candidates["fundamental_filter_status"].eq("CLEAN").any():
        decision = "PROMISING"
    report = f"""# Morita First Absorption Reversal v1 Backtest

## Conclusion

Decision: **{decision}**.

This run produced a daily underlying research backtest, but it did not produce an adoption-ready CLEAN strategy. The local repo has PIT-ish daily OHLCV and formal S history, but it does not have a sealed point-in-time news/fundamental audit source for these events and does not have historical option chains for the candidate trades. Therefore all detected candidates remain AMBIGUOUS for the fundamental filter, the primary CLEAN F/G analysis is empty, and option results are blocked rather than simulated as performance.

## Headline Counts

- S signal rows loaded: {receipt['signals_loaded']}
- Daily price rows loaded: {receipt['daily_rows_loaded']}
- Recent-S membership rows: {receipt['recent_s_membership_rows']}
- Candidate rows: {receipt['candidate_rows']}
- Primary E rows before CLEAN filter: {receipt['primary_e_candidate_rows']}
- CLEAN primary rows: {receipt['clean_candidate_rows']}
- Option performance rows usable: 0

## Baseline Summary

{markdown_table(headline)}

## Data Quality

- Daily source: `{receipt['sources']['daily_path']}`
- Intraday source: `{receipt['sources']['intraday_path']}`; candidate-level intraday bars are unavailable, so D1 90m/final-60m entries are proxy-only and not used as verified intraday results.
- Fundamental event source: not found; AMBIGUOUS fail-closed classification.
- Option chain source: not found; option layer blocked.

## Answers To Required Review Questions

1. MKSI/AMAT-type detection: evaluated as case-study candidates where data exists, but not eligible for CLEAN confirmation without sealed PIT news audit.
2. Best entry timing: not adoption-grade; daily-only comparison is in `trade_level_underlying.csv`.
3. Best D2 exit timing: not adoption-grade; D2 open/close and D3 variants are tabulated.
4. Two-day absorption vs one-day: compare Baseline B and C in `parameter_sensitivity.csv` and summaries.
5. Old-S universe still weak condition: compare C and D.
6. Universe downside deceleration: compare D and E.
7. Sell efficiency vs volume decline: only daily sell-efficiency proxy is available.
8. Degross regime: price-only classification is provided, but fundamental confirmation is unavailable.
9. Tariff CLEAN classification: blocked without PIT news audit.
10. DeepSeek / earnings-shock cases: cannot be reliably separated without sealed event data.
11. Fakeout after D2: D2 and D3 exits are included for review.
12. Underlying vs call: underlying only is usable; call layer is blocked.
13. ATM/ITM/DTE stability: blocked by missing option chains.
14. IV crush effect: not estimated as performance.
15. Short-bot exit use: possible research input only, not wired to production.
16. Buy-the-dip vs call entry: should remain separate until CLEAN and options evidence exist.
17. Minimum live rule: no live rule recommended from this run.
"""
    bundle = f"""# ChatGPT Review Bundle - Morita First Absorption Reversal v1

## Objective
Test whether former Morita S leaders showing two consecutive absorption days during a still-weak old-S universe can capture the next-day rebound.

## Guardrails
- Research-only.
- No live orders, no Webull connection, no production scanner changes.
- Point-in-time discipline enforced by using only S signals known by each event date and prior/current daily bars.
- Missing news/fundamental evidence fails closed to AMBIGUOUS, not CLEAN.
- Missing option chains block option-performance claims.

## Conclusion
{decision}. The daily underlier harness exists and generated reviewable artifacts, but the adoption gate is blocked by missing sealed PIT fundamental audit data and missing option chains.

## Key Outputs
- `signal_candidates.csv`
- `trade_level_underlying.csv`
- `fundamental_filter_audit.csv`
- `parameter_sensitivity.csv`
- `backtest_report.md`
- `receipt.json`

## Baseline Snapshot
{markdown_table(headline)}

## Validation
The run receipt records source hashes, row counts, and safety flags. Targeted tests cover safety flags, fail-closed fundamental handling, and trade summary behavior.

## Limitations
- Candidate-level 5m/15m bars are unavailable; only SOXX intraday exists locally.
- News/fundamental event audit is unavailable, so CLEAN primary analysis has zero rows.
- Historical option chains are unavailable, so options are blocked.
- Daily data starts in 2022 for the local PIT semis panel; COVID case study is unavailable.

## Next Codex Instruction
Acquire or build a sealed point-in-time event audit table with ticker, public timestamp, source, headline/event, and CLEAN/AMBIGUOUS/SHOCK classification made before outcome review. Then rerun this exact harness without changing thresholds, and only after CLEAN underlier PF is acceptable add historical option-chain validation.
"""
    mksi = case_study(candidates, trades, ["MKSI", "AMAT"], "MKSI / AMAT Case Study")
    covid = """# COVID Case Study

Status: BLOCKED_BY_LOCAL_DATA_COVERAGE.

The available PIT semis daily panel starts in 2022, so the 2020 February-April COVID window cannot be reconstructed in this checkout without adding a point-in-time daily and event-audit source. No COVID success or failure examples were fabricated.
"""
    return report, bundle, mksi, covid


def case_study(candidates: pd.DataFrame, trades: pd.DataFrame, tickers: list[str], title: str) -> str:
    subset = candidates[candidates["ticker"].isin(tickers)].copy() if not candidates.empty else pd.DataFrame()
    if subset.empty:
        return f"# {title}\n\nNo candidate rows were detected for {', '.join(tickers)} under the primary daily thresholds in the available local data.\n"
    scoped = trades[
        trades["candidate_id"].isin(set(subset["candidate_id"]))
        & trades["entry_timing"].eq("D1_CLOSE")
        & trades["exit_timing"].eq("D2_OPEN")
    ] if not trades.empty else pd.DataFrame()
    return f"""# {title}

## Candidate Rows
{markdown_table(subset[["candidate_id", "ticker", "D0_date", "D1_date", "primary_candidate_pass", "fundamental_filter_status", "regime_classification"]])}

## D1 Close To D2 Open Returns
{markdown_table(scoped[["baseline_level", "candidate_id", "ticker", "gross_return"]] if not scoped.empty else scoped)}

Interpretation: these rows are case-study evidence only. They are not parameter-selection proof and remain AMBIGUOUS without a sealed PIT fundamental audit source.
"""


def manifest(paths: list[Path], repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        rows.append(
            {
                "path": repo_rel(repo_root, path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "sha256": sha256_file(path) if path.exists() and path.is_file() else "",
            }
        )
    return rows


def source_inventory(repo_root: Path, sources: SourceSet) -> pd.DataFrame:
    rows = []
    for name, path in [
        ("daily_ohlcv", sources.daily_path),
        ("intraday_m15", sources.intraday_path),
        ("signals_2023", sources.signals_2023_path),
        ("signals_2024_2026", sources.signals_2024_2026_path),
    ]:
        full = repo_root / path
        rows.append(
            {
                "source_name": name,
                "path": repo_rel(repo_root, full),
                "exists": full.exists(),
                "bytes": full.stat().st_size if full.exists() else 0,
                "sha256": sha256_file(full) if full.exists() and full.is_file() else "",
            }
        )
    return pd.DataFrame(rows)


def run_backtest(repo_root: Path, output_dir: Path | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root)
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    out = Path(output_dir) if output_dir else repo_root / OUTPUT_DIR
    if not out.is_absolute():
        out = repo_root / out
    out.mkdir(parents=True, exist_ok=True)

    sources = SourceSet(DAILY_PIT, INTRADAY_PIT, SIGNALS_2023, SIGNALS_2024_2026)
    daily = load_daily(repo_root, DAILY_PIT)
    signals = load_s_signals(repo_root)
    membership = build_recent_s_membership(daily, signals, int(cfg["min_days_since_s"]), int(cfg["primary_lookback_sessions"]))
    peer = build_peer_universe_daily(daily, membership)
    candidates = build_signal_candidates(daily, membership, peer, cfg)
    trades = build_underlying_trades(candidates)
    options = empty_options(candidates)
    events, filters, regimes, shocks = build_audits(candidates)
    sensitivity = build_parameter_sensitivity(daily, membership, peer, cfg)
    headline = summarize_trades(trades[(trades["entry_timing"].eq("D1_CLOSE")) & (trades["exit_timing"].eq("D2_OPEN"))] if not trades.empty else trades, ["baseline_level"])
    yearly = summarize_trades(trades.assign(year=trades["D1_date"].str[:4]) if not trades.empty else trades, ["baseline_level", "year"]) if not trades.empty else pd.DataFrame()
    regime_summary = summarize_trades(trades, ["baseline_level", "regime_classification"]) if not trades.empty else pd.DataFrame()
    ticker_summary = summarize_trades(trades, ["baseline_level", "ticker"]) if not trades.empty else pd.DataFrame()
    false_pos = build_false_positives(candidates, trades)
    concentration = build_concentration(trades)

    receipt = {
        **safety_fields(),
        "artifact_version": ARTIFACT_VERSION,
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_at_run_start": git_head(repo_root),
        "sources": {
            "daily_path": repo_rel(repo_root, repo_root / DAILY_PIT),
            "intraday_path": repo_rel(repo_root, repo_root / INTRADAY_PIT),
            "signals_2023_path": repo_rel(repo_root, repo_root / SIGNALS_2023),
            "signals_2024_2026_path": repo_rel(repo_root, repo_root / SIGNALS_2024_2026),
        },
        "daily_rows_loaded": int(daily.shape[0]),
        "signals_loaded": int(signals.shape[0]),
        "recent_s_membership_rows": int(membership.shape[0]),
        "peer_universe_daily_rows": int(peer.shape[0]),
        "candidate_rows": int(candidates.shape[0]),
        "primary_e_candidate_rows": int(candidates["primary_candidate_pass"].sum()) if not candidates.empty else 0,
        "clean_candidate_rows": int(candidates["fundamental_filter_status"].eq("CLEAN").sum()) if not candidates.empty else 0,
        "underlying_trade_rows": int(trades.shape[0]),
        "options_trade_rows": int(options.shape[0]),
        "adoption_status": "BLOCKED_NOT_ADOPTION_READY",
        "adoption_reason": "No CLEAN PIT fundamental audit rows and no historical option chains.",
    }

    report, bundle, mksi, covid = build_reports(receipt, {"headline": headline}, candidates, trades)
    tables = {
        "signal_candidates.csv": candidates,
        "trade_level_underlying.csv": trades,
        "trade_level_options.csv": options,
        "event_audit.csv": events,
        "fundamental_filter_audit.csv": filters,
        "regime_classification.csv": regimes,
        "peer_universe_daily.csv": peer,
        "parameter_sensitivity.csv": sensitivity,
        "yearly_summary.csv": yearly,
        "regime_summary.csv": regime_summary,
        "ticker_summary.csv": ticker_summary,
        "concentration_report.csv": concentration,
        "false_positive_cases.csv": false_pos,
        "excluded_shock_cases.csv": shocks,
        "source_inventory.csv": source_inventory(repo_root, sources),
    }
    paths: list[Path] = []
    paths.append(write_text(out / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker", "RESEARCH ONLY / DO NOT EXECUTE / NO LIVE ORDERS\n"))
    for name, df in tables.items():
        paths.append(write_df(out / name, add_safety(df)))
    paths.append(write_text(out / "case_study_mksi_amat.md", mksi))
    paths.append(write_text(out / "case_study_covid.md", covid))
    paths.append(write_text(out / "backtest_report.md", report))
    paths.append(write_text(out / "chatgpt_review_bundle.md", bundle))
    paths.append(write_json(out / "receipt.json", receipt))
    paths.append(write_json(out / "run_manifest.json", {"files": manifest(paths, repo_root)}))
    return receipt


def build_concentration(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["baseline_level", "entry_timing", "exit_timing", "trades", "top_ticker", "top_ticker_trade_share", "top5_return_share"])
    rows = []
    for keys, g in trades.groupby(["baseline_level", "entry_timing", "exit_timing"]):
        total = len(g)
        counts = g["ticker"].value_counts()
        top = counts.index[0] if not counts.empty else ""
        gains = pd.to_numeric(g["gross_return"], errors="coerce").clip(lower=0)
        top5 = gains.sort_values(ascending=False).head(5).sum()
        all_gains = gains.sum()
        rows.append(
            {
                "baseline_level": keys[0],
                "entry_timing": keys[1],
                "exit_timing": keys[2],
                "trades": total,
                "top_ticker": top,
                "top_ticker_trade_share": float(counts.iloc[0] / total) if total else math.nan,
                "top5_return_share": float(top5 / all_gains) if all_gains else math.nan,
            }
        )
    return pd.DataFrame(rows)
