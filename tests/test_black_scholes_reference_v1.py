from __future__ import annotations

from src.morita_single_call_reference.black_scholes_reference import call_delta, call_price, solve_strike_for_call_delta


def test_continuous_strike_solves_to_delta_060() -> None:
    strike, delta = solve_strike_for_call_delta(100.0, 60 / 365.25, 0.60, 0.60)
    assert strike > 0
    assert abs(delta - 0.60) <= 1e-6
    assert abs(call_delta(100.0, strike, 60 / 365.25, 0.60) - 0.60) <= 1e-6


def test_initial_dte_is_60_calendar_day_year_fraction() -> None:
    price = call_price(100.0, 100.0, 60 / 365.25, 0.60)
    assert price > 0


def test_expired_call_value_is_intrinsic() -> None:
    assert call_price(120.0, 100.0, 0.0, 0.60) == 20.0
    assert call_price(80.0, 100.0, 0.0, 0.60) == 0.0
