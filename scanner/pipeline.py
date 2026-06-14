from __future__ import annotations

from typing import Any

import pandas as pd

from .accumulation import evaluate_accumulation
from .breakout import detect_breakout
from .rs import score_rs_universe
from .scoring import accumulation_points, combine_scores, vcp_score_percent
from .trend_template import evaluate_trend_template
from .universe import evaluate_universe_filter
from .utils import DEFAULT_THRESHOLDS, Thresholds, normalize_ohlcv
from .vcp import evaluate_vcp


def scan_universe(
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    market_caps: dict[str, float] | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> pd.DataFrame:
    market_caps = market_caps or {}
    normalized: dict[str, pd.DataFrame] = {}
    skipped: list[dict[str, Any]] = []

    for ticker, history in histories.items():
        symbol = ticker.upper()
        try:
            df = normalize_ohlcv(history)
            filter_result = evaluate_universe_filter(symbol, df, thresholds, market_caps.get(symbol))
            if not filter_result.passed:
                skipped.append({"ticker": symbol, "skip_reason": filter_result.reason})
                continue
            normalized[symbol] = df
        except Exception as exc:
            skipped.append({"ticker": symbol, "skip_reason": str(exc)})

    if not normalized:
        return pd.DataFrame(skipped)

    rs_results = score_rs_universe(
        normalized,
        benchmark_history,
        down_day_threshold=thresholds.defensive_down_day_threshold,
        min_down_days=thresholds.min_down_days,
    )

    rows: list[dict[str, Any]] = []
    for ticker, history in normalized.items():
        try:
            trend = evaluate_trend_template(history)
            breakout = detect_breakout(
                history,
                lookback_max=int(thresholds.breakout_lookback_days),
                volume_multiple=thresholds.breakout_volume_multiple,
                near_pct=thresholds.near_breakout_pct,
            )
            vcp = evaluate_vcp(
                history,
                dry_up_multiple=thresholds.vcp_volume_dry_up_multiple,
                tight_close_pct=thresholds.tight_close_pct,
            )
            accumulation = evaluate_accumulation(history)
            rs = rs_results[ticker]
            score = combine_scores(
                trend_points=trend.score,
                rs_points=rs.rs_points,
                breakout_points=breakout.score,
                vcp_points=vcp.score,
                volume_surge_points=breakout.volume_surge_points,
                accumulation_score=accumulation.score,
                defensive_bonus=rs.defensive_bonus,
                breakout_today=breakout.breakout_today,
                near_breakout=breakout.near_breakout,
                trend_passed=trend.passed,
                standard_rs_score=rs.standard_score,
                defensive_rs_score=rs.defensive_score,
                breakout_rs_score=rs.breakout_score,
                distance_to_pivot=breakout.distance_to_pivot,
                volume_dry_up=vcp.volume_dry_up,
            )
            vcp_score = vcp_score_percent(vcp.score)
            rows.append(
                {
                    "ticker": ticker,
                    "rank": score.rank,
                    "alert_type": score.alert_type,
                    "alert_priority": score.alert_priority,
                    "total_score": score.total_score,
                    "close": trend.close,
                    "pivot": breakout.pivot,
                    "distance_to_pivot": breakout.distance_to_pivot,
                    "avg_volume_50d": breakout.avg_volume_50d,
                    "market_cap": market_caps.get(ticker),
                    "volume_multiple": breakout.volume_multiple,
                    "trend_points": trend.score,
                    "trend_passed": trend.passed,
                    "standard_rs_score": rs.standard_score,
                    "defensive_rs_score": rs.defensive_score,
                    "breakout_rs_score": rs.breakout_score,
                    "rs_points": rs.rs_points,
                    "defensive_bonus": rs.defensive_bonus,
                    "volume_dry_up_bonus": score.volume_dry_up_bonus,
                    "rs_new_high_3m": rs.rs_new_high_3m,
                    "rs_new_high_6m": rs.rs_new_high_6m,
                    "breakout_points": breakout.score,
                    "breakout_today": breakout.breakout_today,
                    "near_breakout": breakout.near_breakout,
                    "failed_breakout": breakout.failed_breakout,
                    "vcp_score": vcp_score,
                    "vcp_points": vcp.score,
                    "vcp_contraction": vcp.contraction_sequence,
                    "vcp_volume_dry_up": vcp.volume_dry_up,
                    "vcp_tight_closes": vcp.tight_closes,
                    "accumulation_score": accumulation.score,
                    "accumulation_points": accumulation_points(accumulation.score),
                }
            )
        except Exception as exc:
            rows.append({"ticker": ticker, "rank": "D", "alert_type": "none", "alert_priority": 5, "skip_reason": str(exc)})

    out = pd.DataFrame(rows + skipped)
    if "total_score" in out.columns:
        out = out.sort_values(["alert_priority", "total_score"], ascending=[True, False], na_position="last")
    return out.reset_index(drop=True)
