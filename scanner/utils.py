from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_OHLCV = ("Open", "High", "Low", "Close", "Volume")


@dataclass(frozen=True)
class Thresholds:
    min_price: float = 5.0
    min_avg_volume_50d: float = 500_000.0
    min_market_cap: float = 300_000_000.0
    breakout_lookback_days: int = 20
    breakout_volume_multiple: float = 1.5
    near_breakout_pct: float = 0.05
    defensive_down_day_threshold: float = -0.005
    min_down_days: int = 5
    vcp_volume_dry_up_multiple: float = 0.70
    tight_close_pct: float = 0.05


DEFAULT_THRESHOLDS = Thresholds()


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("price history is empty")

    mapping = {str(c).strip().lower(): c for c in df.columns}
    rename = {}
    for target in REQUIRED_OHLCV:
        src = mapping.get(target.lower())
        if src is None:
            raise ValueError(f"missing required column: {target}")
        rename[src] = target

    out = df.rename(columns=rename).copy()
    out = out.loc[:, list(REQUIRED_OHLCV)]
    for col in REQUIRED_OHLCV:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["High", "Low", "Close"])
    if not isinstance(out.index, pd.DatetimeIndex):
        try:
            out.index = pd.to_datetime(out.index)
        except Exception:
            pass
    return out.sort_index()


def last_valid(series: pd.Series, default: float = np.nan) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    return float(vals.iloc[-1]) if len(vals) else default


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    if den is None or pd.isna(den) or den == 0:
        return default
    return float(num) / float(den)


def percentile_scores(values: dict[str, float]) -> dict[str, float]:
    items = {k: v for k, v in values.items() if v is not None and not pd.isna(v)}
    if not items:
        return {k: np.nan for k in values}
    s = pd.Series(items, dtype="float64")
    ranked = s.rank(pct=True, method="average") * 100.0
    return {k: float(ranked[k]) if k in ranked else np.nan for k in values}


def recent_return(close: pd.Series, days: int) -> float:
    close = pd.to_numeric(close, errors="coerce").dropna()
    if len(close) <= days:
        return np.nan
    return float(close.iloc[-1] / close.iloc[-days - 1] - 1.0)


def rolling_slope(series: pd.Series, window: int) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna().tail(window)
    if len(vals) < max(3, window // 2):
        return np.nan
    x = np.arange(len(vals), dtype="float64")
    return float(np.polyfit(x, vals.to_numpy(dtype="float64"), 1)[0])


def mean_or_nan(values: Iterable[float]) -> float:
    vals = [v for v in values if v is not None and not pd.isna(v)]
    return float(np.mean(vals)) if vals else np.nan
