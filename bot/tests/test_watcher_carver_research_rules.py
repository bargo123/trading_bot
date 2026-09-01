from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Robert Carver — Systematic Trading"


def _forecast(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carver_forecast": 16.0,
        "carver_forecast_average_abs": 10.0,
        "carver_forecast_cap_multiple": 2.0,
        "carver_forecast_data_provenance": "observed expanding historical forecasts",
    }
    state.update(overrides)
    return state


def _inertia(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carver_current_position": 45.0,
        "carver_rounded_target_position": 50.0,
        "carver_position_inertia_fraction": 0.10,
        "carver_position_data_provenance": "observed target and current positions",
    }
    state.update(overrides)
    return state


def _speed(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carver_standardized_cost_sr": 0.002,
        "carver_turnover_per_year": 50.0,
        "carver_expected_pre_cost_sr": 0.40,
        "carver_max_cost_fraction": 1.0 / 3.0,
        "carver_speed_data_provenance": "observed execution cost and turnover history",
    }
    state.update(overrides)
    return state


def test_carver_forecast_cap_keeps_extreme_forecasts_as_a_risk_warning():
    result = evaluate_module("carver_forecast_cap", _forecast(carver_forecast=22.0))
    assert result["view"] == "WAIT"
    assert result["carver_forecast_action"] == "FORECAST_CAPPED"
    assert result["carver_forecast_cap"] == 20.0
    assert result["directional_claim"] is False
    assert result["source_books"] == [SOURCE]


def test_carver_position_inertia_suppresses_small_turnover_and_allows_large_rebalance():
    hold = evaluate_module("carver_position_inertia", _inertia())
    assert hold["view"] == "WAIT"
    assert hold["carver_inertia_action"] == "POSITION_INERTIA_HOLD"

    rebalance = evaluate_module(
        "carver_position_inertia",
        _inertia(carver_current_position=40.0),
    )
    assert rebalance["view"] == "BUY"
    assert rebalance["carver_inertia_action"] == "REBALANCE_REQUIRED"


def test_carver_speed_limit_compares_annualized_cost_with_pre_cost_edge():
    within = evaluate_module("carver_speed_limit", _speed())
    assert within["view"] == "WAIT"
    assert within["carver_speed_action"] == "SPEED_WITHIN_COST_BUDGET"
    assert within["carver_annualized_cost_sr"] == 0.1

    too_fast = evaluate_module(
        "carver_speed_limit",
        _speed(carver_turnover_per_year=100.0),
    )
    assert too_fast["carver_speed_action"] == "SPEED_LIMIT_EXCEEDED"
    assert too_fast["carver_max_turnover"] == pytest.approx(66.66666666666666)


def test_carver_rules_fail_closed_without_observed_inputs():
    for algorithm_id in (
        "carver_forecast_cap",
        "carver_position_inertia",
        "carver_speed_limit",
    ):
        result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
        assert result["view"] == "MISSING_DATA"
        assert result["applicability"] == "MISSING_DATA"
        assert result["execution_authority"] is False
