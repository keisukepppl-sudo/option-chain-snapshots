from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .utils import last_valid, normalize_ohlcv


@dataclass(frozen=True)
class TrendTemplateResult:
    passed: bool
    score: float
    close: float
    sma50: float
    sma150: float
    sma200: float
    high_52w: float
    low_52w: float
    price_stack: bool
    sma200_rising: bool
    near_high: bool
    above_low: bool


def evaluate_trend_template(history: pd.DataFrame) -> TrendTemplateResult:
    df = normalize_ohlcv(history)
    close = df["Close"]
    if len(close) < 200:
        raise ValueError("trend template requires at least 200 bars")

    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()

    c = last_valid(close)
    s50 = last_valid(sma50)
    s150 = last_valid(sma150)
    s200 = last_valid(sma200)
    s200_prev20 = float(sma200.dropna().iloc[-21]) if len(sma200.dropna()) >= 21 else np.nan
    high_52w = float(close.tail(252).max())
    low_52w = float(close.tail(252).min())

    price_stack = bool(c > s50 > s150 > s200)
    sma200_rising = bool(not pd.isna(s200_prev20) and s200 > s200_prev20)
    near_high = bool(c >= 0.75 * high_52w)
    above_low = bool(c >= 1.30 * low_52w)

    score = 0.0
    score += 10.0 if price_stack else 0.0
    score += 6.0 if sma200_rising else 0.0
    score += 5.0 if near_high else 0.0
    score += 4.0 if above_low else 0.0

    passed = bool(price_stack and sma200_rising and near_high)
    return TrendTemplateResult(
        passed=passed,
        score=score,
        close=c,
        sma50=s50,
        sma150=s150,
        sma200=s200,
        high_52w=high_52w,
        low_52w=low_52w,
        price_stack=price_stack,
        sma200_rising=sma200_rising,
        near_high=near_high,
        above_low=above_low,
    )
