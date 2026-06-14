from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .scoring import defensive_rs_bonus
from .utils import normalize_ohlcv, percentile_scores


@dataclass(frozen=True)
class RSResult:
    standard_raw: float
    standard_score: float
    defensive_raw: float
    defensive_score: float
    breakout_raw: float
    breakout_score: float
    rs_new_high_3m: bool
    rs_new_high_6m: bool
    rs_points: float
    defensive_bonus: float


def _aligned_close(history: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    stock_close = normalize_ohlcv(history)["Close"].rename("stock")
    bench_close = normalize_ohlcv(benchmark)["Close"].rename("bench")
    return pd.concat([stock_close, bench_close], axis=1).dropna()


def relative_return(history: pd.DataFrame, benchmark: pd.DataFrame, days: int) -> float:
    aligned = _aligned_close(history, benchmark)
    if len(aligned) <= days:
        return np.nan
    stock_ret = aligned["stock"].iloc[-1] / aligned["stock"].iloc[-days - 1] - 1.0
    bench_ret = aligned["bench"].iloc[-1] / aligned["bench"].iloc[-days - 1] - 1.0
    return float(stock_ret - bench_ret)


def standard_rs_raw(history: pd.DataFrame, benchmark: pd.DataFrame) -> float:
    rel_6m = relative_return(history, benchmark, 126)
    rel_3m = relative_return(history, benchmark, 63)
    rel_12m = relative_return(history, benchmark, 252)
    vals = [rel_6m, rel_3m, rel_12m]
    if any(pd.isna(v) for v in vals):
        return np.nan
    return float(0.5 * rel_6m + 0.3 * rel_3m + 0.2 * rel_12m)


def defensive_rs_raw(
    history: pd.DataFrame,
    benchmark: pd.DataFrame,
    down_day_threshold: float = -0.005,
    min_down_days: int = 5,
) -> float:
    aligned = _aligned_close(history, benchmark).tail(120)
    if len(aligned) < 20:
        return np.nan
    ret = aligned.pct_change().dropna()
    down = ret[ret["bench"] <= down_day_threshold]
    if len(down) < min_down_days:
        down = ret.tail(120)[ret.tail(120)["bench"] <= down_day_threshold]
    if down.empty:
        return np.nan
    return float((down["stock"] - down["bench"]).mean())


def breakout_rs_raw(history: pd.DataFrame, benchmark: pd.DataFrame, days: int = 20) -> float:
    return relative_return(history, benchmark, days)


def relative_line_new_high(history: pd.DataFrame, benchmark: pd.DataFrame, days: int) -> bool:
    aligned = _aligned_close(history, benchmark)
    if len(aligned) < days:
        return False
    line = aligned["stock"] / aligned["bench"]
    recent = line.tail(days)
    return bool(recent.iloc[-1] >= recent.max())


def score_rs_universe(
    histories: dict[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    down_day_threshold: float = -0.005,
    min_down_days: int = 5,
) -> dict[str, RSResult]:
    std_raw = {t: standard_rs_raw(h, benchmark) for t, h in histories.items()}
    def_raw = {t: defensive_rs_raw(h, benchmark, down_day_threshold, min_down_days) for t, h in histories.items()}
    brk_raw = {t: breakout_rs_raw(h, benchmark) for t, h in histories.items()}
    std_score = percentile_scores(std_raw)
    def_score = percentile_scores(def_raw)
    brk_score = percentile_scores(brk_raw)

    results: dict[str, RSResult] = {}
    for ticker, hist in histories.items():
        standard_points = 10.0 if std_score[ticker] >= 90 else (7.0 if std_score[ticker] >= 80 else 0.0)
        breakout_points = 5.0 if brk_score[ticker] >= 90 else 0.0
        new_high_3m = relative_line_new_high(hist, benchmark, 63)
        new_high_6m = relative_line_new_high(hist, benchmark, 126)
        new_high_points = 5.0 if (new_high_3m or new_high_6m) else 0.0
        rs_points = min(20.0, standard_points + breakout_points + new_high_points)
        defensive_bonus = defensive_rs_bonus(def_score[ticker])
        results[ticker] = RSResult(
            standard_raw=std_raw[ticker],
            standard_score=std_score[ticker],
            defensive_raw=def_raw[ticker],
            defensive_score=def_score[ticker],
            breakout_raw=brk_raw[ticker],
            breakout_score=brk_score[ticker],
            rs_new_high_3m=new_high_3m,
            rs_new_high_6m=new_high_6m,
            rs_points=rs_points,
            defensive_bonus=defensive_bonus,
        )
    return results
