from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .utils import normalize_ohlcv, safe_div


@dataclass(frozen=True)
class VCPResult:
    contraction_sequence: bool
    volatility_compression: bool
    volume_dry_up: bool
    tight_closes: bool
    score: float
    atr20_pct: float
    atr60_pct: float
    volume_ratio_5d_50d: float
    close_range_5d_pct: float


def true_range(df: pd.DataFrame) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)


def evaluate_vcp(history: pd.DataFrame, dry_up_multiple: float = 0.70, tight_close_pct: float = 0.05) -> VCPResult:
    df = normalize_ohlcv(history)
    if len(df) < 65:
        raise ValueError("VCP detection requires at least 65 bars")

    swing_ranges = []
    for window in (60, 40, 20):
        part = df.tail(window)
        swing_ranges.append(safe_div(float(part["High"].max() - part["Low"].min()), float(part["Close"].iloc[-1]), np.nan))
    contraction_sequence = bool(swing_ranges[0] > swing_ranges[1] > swing_ranges[2])

    atr = true_range(df)
    atr20_pct = safe_div(float(atr.tail(20).mean()), float(df["Close"].iloc[-1]), np.nan)
    atr60_pct = safe_div(float(atr.tail(60).mean()), float(df["Close"].iloc[-1]), np.nan)
    volatility_compression = bool(not pd.isna(atr20_pct) and not pd.isna(atr60_pct) and atr20_pct < atr60_pct)

    volume_ratio = safe_div(float(df["Volume"].tail(5).mean()), float(df["Volume"].tail(50).mean()), np.nan)
    volume_dry_up = bool(not pd.isna(volume_ratio) and volume_ratio < dry_up_multiple)

    close_range = safe_div(float(df["Close"].tail(5).max() - df["Close"].tail(5).min()), float(df["Close"].iloc[-1]), np.nan)
    tight_closes = bool(not pd.isna(close_range) and close_range < tight_close_pct)

    score = 0.0
    score += 5.0 if contraction_sequence else 0.0
    score += 4.0 if volatility_compression else 0.0
    score += 4.0 if volume_dry_up else 0.0
    score += 2.0 if tight_closes else 0.0
    return VCPResult(
        contraction_sequence=contraction_sequence,
        volatility_compression=volatility_compression,
        volume_dry_up=volume_dry_up,
        tight_closes=tight_closes,
        score=score,
        atr20_pct=atr20_pct,
        atr60_pct=atr60_pct,
        volume_ratio_5d_50d=volume_ratio,
        close_range_5d_pct=close_range,
    )
