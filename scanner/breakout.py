from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .utils import normalize_ohlcv, safe_div


@dataclass(frozen=True)
class BreakoutResult:
    pivot: float
    close: float
    distance_to_pivot: float
    avg_volume_50d: float
    volume_multiple: float
    breakout_today: bool
    near_breakout: bool
    failed_breakout: bool
    score: float
    volume_surge_points: float


def detect_breakout(
    history: pd.DataFrame,
    lookback_min: int = 20,
    lookback_max: int = 65,
    volume_multiple: float = 1.5,
    near_pct: float = 0.03,
) -> BreakoutResult:
    df = normalize_ohlcv(history)
    if len(df) < lookback_max + 1:
        raise ValueError("breakout detection requires at least 66 bars")

    prior = df.iloc[-lookback_max - 1 : -1]
    pivot = float(prior["High"].tail(lookback_max).max())
    close = float(df["Close"].iloc[-1])
    volume = float(df["Volume"].iloc[-1])
    avg_volume_50d = float(df["Volume"].tail(50).mean())
    vol_mult = safe_div(volume, avg_volume_50d, np.nan)
    distance = safe_div(pivot - close, pivot, np.nan)
    breakout_today = bool(close > pivot and vol_mult >= volume_multiple)
    near_breakout = bool(0.0 <= distance <= near_pct)
    failed_breakout = _failed_breakout(df, pivot)

    score = 0.0
    if breakout_today:
        score = 20.0
    elif near_breakout:
        score = 12.0
    elif close > pivot:
        score = 8.0
    volume_surge_points = min(10.0, max(0.0, (vol_mult - 1.0) / 0.5 * 5.0)) if not pd.isna(vol_mult) else 0.0
    return BreakoutResult(
        pivot=pivot,
        close=close,
        distance_to_pivot=distance,
        avg_volume_50d=avg_volume_50d,
        volume_multiple=vol_mult,
        breakout_today=breakout_today,
        near_breakout=near_breakout,
        failed_breakout=failed_breakout,
        score=score,
        volume_surge_points=volume_surge_points,
    )


def _failed_breakout(df: pd.DataFrame, pivot: float) -> bool:
    if len(df) < 6 or pivot <= 0:
        return False
    recent = df.tail(6)
    crossed = recent["Close"] > pivot
    if not crossed.any():
        return False
    crossed_pos = np.where(crossed.to_numpy())[0]
    first_breakout_pos = int(crossed_pos[0])
    after = recent.iloc[first_breakout_pos + 1 :]
    if after.empty:
        return False
    avg_volume_50d = float(df["Volume"].tail(50).mean())
    pivot_lost = (after["Close"] < pivot).any()
    heavy_down = ((after["Close"].pct_change() < -0.03) & (after["Volume"] > 1.2 * avg_volume_50d)).any()
    return bool(pivot_lost or heavy_down)
