from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreBreakdown:
    total_score: float
    rank: str
    alert_type: str
    alert_priority: int
    defensive_bonus: float
    volume_dry_up_bonus: float


def accumulation_points(accumulation_score: float) -> float:
    if accumulation_score >= 70:
        return 10.0
    if accumulation_score >= 50:
        return 6.0
    return 0.0


def defensive_rs_bonus(defensive_rs_score: float) -> float:
    if defensive_rs_score >= 90.0:
        return 10.0
    if defensive_rs_score >= 80.0:
        return 5.0
    return 0.0


def volume_dry_up_bonus(volume_dry_up: bool) -> float:
    return 5.0 if volume_dry_up else 0.0


def vcp_score_percent(vcp_points: float) -> float:
    return round(min(100.0, max(0.0, vcp_points / 15.0 * 100.0)), 2)


def is_s_rank_candidate(
    trend_passed: bool,
    standard_rs_score: float,
    breakout_rs_score: float,
    accumulation_score: float,
    vcp_score: float,
    near_breakout: bool,
    distance_to_pivot: float,
) -> bool:
    return bool(
        trend_passed
        and standard_rs_score >= 80.0
        and breakout_rs_score >= 80.0
        and accumulation_score >= 60.0
        and vcp_score >= 45.0
        and near_breakout
        and distance_to_pivot <= 0.05
    )


def alert_priority(rank: str) -> int:
    return {"S": 1, "A": 2, "B": 3, "C": 4}.get(rank, 5)


def classify_rank(
    total_score: float,
    breakout_today: bool,
    near_breakout: bool,
    trend_passed: bool,
    standard_rs_score: float,
    defensive_rs_score: float,
    breakout_rs_score: float,
    accumulation_score: float,
    vcp_score: float,
    distance_to_pivot: float,
    volume_dry_up: bool,
) -> tuple[str, str]:
    if is_s_rank_candidate(
        trend_passed=trend_passed,
        standard_rs_score=standard_rs_score,
        breakout_rs_score=breakout_rs_score,
        accumulation_score=accumulation_score,
        vcp_score=vcp_score,
        near_breakout=near_breakout,
        distance_to_pivot=distance_to_pivot,
    ):
        return "S", "early_entry"
    if total_score >= 80 and breakout_today:
        return "A", "breakout"
    if total_score >= 75 and near_breakout:
        return "B", "setup"
    if total_score >= 65 and trend_passed:
        return "C", "csv_only"
    return "D", "none"


def combine_scores(
    trend_points: float,
    rs_points: float,
    breakout_points: float,
    vcp_points: float,
    volume_surge_points: float,
    accumulation_score: float,
    defensive_bonus: float | None,
    breakout_today: bool,
    near_breakout: bool,
    trend_passed: bool,
    standard_rs_score: float = 0.0,
    defensive_rs_score: float = 0.0,
    breakout_rs_score: float = 0.0,
    distance_to_pivot: float = 1.0,
    volume_dry_up: bool = False,
) -> ScoreBreakdown:
    computed_defensive_bonus = defensive_rs_bonus(defensive_rs_score) if defensive_bonus is None else defensive_bonus
    dry_up_bonus = volume_dry_up_bonus(volume_dry_up)
    total = (
        trend_points
        + min(20.0, rs_points)
        + min(20.0, breakout_points)
        + min(15.0, vcp_points)
        + min(10.0, volume_surge_points)
        + accumulation_points(accumulation_score)
        + min(10.0, computed_defensive_bonus)
        + dry_up_bonus
    )
    vcp_score = vcp_score_percent(vcp_points)
    rank, alert = classify_rank(
        total_score=total,
        breakout_today=breakout_today,
        near_breakout=near_breakout,
        trend_passed=trend_passed,
        standard_rs_score=standard_rs_score,
        defensive_rs_score=defensive_rs_score,
        breakout_rs_score=breakout_rs_score,
        accumulation_score=accumulation_score,
        vcp_score=vcp_score,
        distance_to_pivot=distance_to_pivot,
        volume_dry_up=volume_dry_up,
    )
    return ScoreBreakdown(
        total_score=round(total, 2),
        rank=rank,
        alert_type=alert,
        alert_priority=alert_priority(rank),
        defensive_bonus=computed_defensive_bonus,
        volume_dry_up_bonus=dry_up_bonus,
    )
