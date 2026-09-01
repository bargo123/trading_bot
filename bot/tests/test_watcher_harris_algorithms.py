from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Trading and Exchanges: Market Microstructure for Practitioners"


def _immediacy(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "harris_best_bid": 1.1000,
        "harris_best_ask": 1.1002,
        "harris_order_side": "BUY",
        "harris_execution_style": "market",
        "harris_fee_per_unit": 0.00001,
        "harris_data_provenance": "observed executable BBO",
    }
    state.update(overrides)
    return state


def _limit(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "harris_limit_order_side": "BUY",
        "harris_limit_price": 1.1000,
        "harris_best_bid": 1.1000,
        "harris_best_ask": 1.1002,
        "harris_limit_fill_probability": 0.8,
        "harris_limit_adverse_move_probability": 0.1,
        "harris_limit_expected_stand_s": 2.0,
        "harris_limit_order_provenance": "observed limit-order-book state",
    }
    state.update(overrides)
    return state


def _stop(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "harris_stop_triggered": True,
        "harris_stop_direction": "BUY",
        "harris_stop_follow_through": True,
        "harris_stop_order_provenance": "observed broker stop activation",
    }
    state.update(overrides)
    return state


def test_harris_immediacy_prices_market_order_cost_without_fabricating_direction():
    result = evaluate_module("harris_immediacy_cost", _immediacy())
    assert result["view"] == "WAIT"
    assert result["directional_claim"] is False
    assert result["harris_half_spread"] == pytest.approx(0.0001)
    assert result["harris_round_trip_spread_cost"] == pytest.approx(0.0002)
    assert result["source_books"] == [SOURCE]

    invalid = evaluate_module("harris_immediacy_cost", _immediacy(harris_best_ask=1.0999))
    assert invalid["harris_immediacy_assessment"] == "UNKNOWN"


def test_harris_limit_order_perspective_separates_fill_uncertainty_from_regret():
    result = evaluate_module("harris_limit_order_regret", _limit())
    assert result["view"] == "WAIT"
    assert result["harris_limit_assessment"] == "LOW_REGRET_RISK"
    assert result["harris_execution_uncertainty"] is False

    adverse = evaluate_module(
        "harris_limit_order_regret",
        _limit(harris_limit_fill_probability=0.2, harris_limit_adverse_move_probability=0.8),
    )
    assert adverse["harris_limit_assessment"] == "HIGH_REGRET_RISK"
    assert adverse["harris_execution_uncertainty"] is True


def test_harris_stop_order_momentum_requires_observed_trigger_and_follow_through():
    buy = evaluate_module("harris_stop_order_momentum", _stop())
    sell = evaluate_module(
        "harris_stop_order_momentum",
        _stop(side="SELL", harris_stop_direction="SELL"),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["harris_stop_assessment"] == "MOMENTUM_CONFIRMATION"

    no_follow = evaluate_module(
        "harris_stop_order_momentum",
        _stop(harris_stop_follow_through=False),
    )
    assert no_follow["view"] == "WAIT"
    assert no_follow["harris_stop_assessment"] == "NO_FOLLOW_THROUGH"


@pytest.mark.parametrize(
    "algorithm_id",
    ["harris_immediacy_cost", "harris_limit_order_regret", "harris_stop_order_momentum"],
)
def test_harris_algorithms_fail_closed_without_observed_market_data(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
