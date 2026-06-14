from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .utils import Thresholds, normalize_ohlcv


@dataclass(frozen=True)
class UniverseFilterResult:
    passed: bool
    reason: str
    close: float | None = None
    avg_volume_50d: float | None = None
    market_cap: float | None = None


def evaluate_universe_filter(
    ticker: str,
    history: pd.DataFrame,
    thresholds: Thresholds,
    market_cap: float | None = None,
) -> UniverseFilterResult:
    df = normalize_ohlcv(history)
    close = float(df["Close"].iloc[-1])
    avg_volume_50d = float(df["Volume"].tail(50).mean())
    if close < thresholds.min_price:
        return UniverseFilterResult(False, "price_below_min", close, avg_volume_50d, market_cap)
    if avg_volume_50d < thresholds.min_avg_volume_50d:
        return UniverseFilterResult(False, "avg_volume_below_min", close, avg_volume_50d, market_cap)
    if market_cap is not None and market_cap < thresholds.min_market_cap:
        return UniverseFilterResult(False, "market_cap_below_min", close, avg_volume_50d, market_cap)
    if _looks_like_non_common_stock(ticker):
        return UniverseFilterResult(False, "likely_non_common_stock", close, avg_volume_50d, market_cap)
    return UniverseFilterResult(True, "ok", close, avg_volume_50d, market_cap)


def _looks_like_non_common_stock(ticker: str) -> bool:
    symbol = ticker.upper()
    non_common_suffixes = ("-W", "-WT", "-U", "-P", "-PR", ".W", ".WT", ".U", ".P", ".PR")
    return symbol.endswith(non_common_suffixes)
