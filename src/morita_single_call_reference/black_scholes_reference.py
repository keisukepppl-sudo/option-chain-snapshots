from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def call_price(spot: float, strike: float, years: float, volatility: float, risk_free_rate: float = 0.0, dividend_yield: float = 0.0) -> float:
    if spot <= 0 or strike <= 0:
        raise ValueError("spot_and_strike_must_be_positive")
    if years <= 0 or volatility <= 0:
        return max(spot - strike, 0.0)
    vol_sqrt = volatility * math.sqrt(years)
    d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * years) / vol_sqrt
    d2 = d1 - vol_sqrt
    return spot * math.exp(-dividend_yield * years) * norm_cdf(d1) - strike * math.exp(-risk_free_rate * years) * norm_cdf(d2)


def call_delta(spot: float, strike: float, years: float, volatility: float, risk_free_rate: float = 0.0, dividend_yield: float = 0.0) -> float:
    if spot <= 0 or strike <= 0:
        raise ValueError("spot_and_strike_must_be_positive")
    if years <= 0 or volatility <= 0:
        return 1.0 if spot > strike else 0.0
    vol_sqrt = volatility * math.sqrt(years)
    d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * years) / vol_sqrt
    return math.exp(-dividend_yield * years) * norm_cdf(d1)


def solve_strike_for_call_delta(
    spot: float,
    years: float,
    volatility: float,
    target_delta: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
    tolerance: float = 1e-8,
    max_iterations: int = 200,
) -> tuple[float, float]:
    if not (0.0 < target_delta < 1.0):
        raise ValueError("target_delta_must_be_between_zero_and_one")
    if spot <= 0 or years <= 0 or volatility <= 0:
        raise ValueError("invalid_delta_solve_inputs")
    low = spot * 0.01
    high = spot * 10.0
    for _ in range(max_iterations):
        mid = (low + high) / 2.0
        delta = call_delta(spot, mid, years, volatility, risk_free_rate, dividend_yield)
        if abs(delta - target_delta) <= tolerance:
            return mid, delta
        if delta > target_delta:
            low = mid
        else:
            high = mid
    strike = (low + high) / 2.0
    return strike, call_delta(spot, strike, years, volatility, risk_free_rate, dividend_yield)
