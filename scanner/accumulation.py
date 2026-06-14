from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .utils import normalize_ohlcv, rolling_slope, safe_div


@dataclass(frozen=True)
class AccumulationResult:
    score: float
    obv_points: float
    up_down_volume_points: float
    clv_points: float
    low_down_day_volume_points: float
    tight_close_points: float
    dry_up_points: float
    up_down_volume_ratio: float
    avg_clv20: float
    volume_ratio_5d_50d: float


def evaluate_accumulation(history: pd.DataFrame) -> AccumulationResult:
    df = normalize_ohlcv(history)
    if len(df) < 60:
        raise ValueError("accumulation score requires at least 60 bars")

    close = df["Close"]
    volume = df["Volume"]
    direction = close.diff().fillna(0.0).apply(lambda v: 1 if v > 0 else (-1 if v < 0 else 0))
    obv = (direction * volume).cumsum()
    obv_slope = rolling_slope(obv, 20)
    price_slope = rolling_slope(close, 20)
    obv_points = 20.0 if obv_slope > 0 and obv_slope > price_slope else 0.0

    last50 = df.tail(50).copy()
    up_volume = float(last50.loc[last50["Close"].diff() > 0, "Volume"].sum())
    down_volume = float(last50.loc[last50["Close"].diff() < 0, "Volume"].sum())
    up_down_ratio = safe_div(up_volume, down_volume, 0.0)
    if up_down_ratio > 1.5:
        up_down_points = 25.0
    elif up_down_ratio > 1.2:
        up_down_points = 15.0
    else:
        up_down_points = 0.0

    clv = ((df["Close"] - df["Low"]) / (df["High"] - df["Low"]).replace(0, pd.NA)).astype("float64")
    avg_clv20 = float(clv.tail(20).mean())
    clv_points = 20.0 if avg_clv20 > 0.6 else (10.0 if avg_clv20 > 0.5 else 0.0)

    avg_vol_50d = float(volume.tail(50).mean())
    down_day_avg_20d = float(df.tail(20).loc[df.tail(20)["Close"].diff() < 0, "Volume"].mean())
    low_down_day_points = 15.0 if pd.notna(down_day_avg_20d) and down_day_avg_20d < avg_vol_50d else 0.0

    close_range_pct = safe_div(float(close.tail(5).max() - close.tail(5).min()), float(close.iloc[-1]), 0.0)
    tight_close_points = 10.0 if close_range_pct < 0.05 else 0.0

    volume_ratio = safe_div(float(volume.tail(5).mean()), avg_vol_50d, 0.0)
    dry_up_points = 10.0 if volume_ratio < 0.70 else 0.0

    score = obv_points + up_down_points + clv_points + low_down_day_points + tight_close_points + dry_up_points
    return AccumulationResult(
        score=min(100.0, score),
        obv_points=obv_points,
        up_down_volume_points=up_down_points,
        clv_points=clv_points,
        low_down_day_volume_points=low_down_day_points,
        tight_close_points=tight_close_points,
        dry_up_points=dry_up_points,
        up_down_volume_ratio=up_down_ratio,
        avg_clv20=avg_clv20,
        volume_ratio_5d_50d=volume_ratio,
    )
