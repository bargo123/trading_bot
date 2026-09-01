from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


ALDRIDGE_SOURCE = "Irene Aldridge — High-Frequency Trading"
DALTON_SOURCES = [
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Peter Steidlmayer — Steidlmayer on Markets",
]


def _pair(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "aldridge_pair_spread_zscore": 2.5,
        "aldridge_pair_entry_zscore": 2.0,
        "aldridge_pair_stationarity": "validated",
        "aldridge_pair_signal": "SELL",
        "aldridge_pair_data_provenance": "causal_pair_prices",
    }
    state.update(overrides)
    return state


def _trend_day(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "dalton_day_type": "trend day",
        "dalton_direction": "up",
        "dalton_close_location_percent": 5,
        "dalton_countertrend_rotations": 1,
        "dalton_directional_integrity": True,
        "dalton_data_provenance": "causal_market_profile",
    }
    state.update(overrides)
    return state


def _auction(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "dalton_auction_point_direction": "up",
        "dalton_auction_point_price": 1.1000,
        "dalton_retest_price": 1.1001,
        "dalton_retest_holds": True,
        "dalton_retest_close_direction": "up",
        "dalton_auction_point_violation_ticks": 1,
        "dalton_significant_violation_ticks": 2,
        "dalton_data_provenance": "causal_market_profile",
    }
    state.update(overrides)
    return state


def test_aldridge_pair_dislocation_requires_stationarity_and_cost_aware_zscore():
    sell = evaluate_module("aldridge_pair_dislocation", _pair())
    buy = evaluate_module(
        "aldridge_pair_dislocation",
        _pair(
            side="BUY",
            aldridge_pair_spread_zscore=-2.5,
            aldridge_pair_signal="BUY",
        ),
    )
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"
    assert sell["source_books"] == [ALDRIDGE_SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"aldridge_pair_spread_zscore": 1.2},
        {"aldridge_pair_stationarity": "not validated"},
        {"aldridge_pair_signal": "BUY"},
    ],
)
def test_aldridge_pair_waits_without_a_validated_dislocation(overrides):
    result = evaluate_module("aldridge_pair_dislocation", _pair(**overrides))
    assert result["view"] in {"WAIT", "MISSING_DATA"}
    assert result["reasons"] or result["missing_inputs"]


def test_dalton_trend_day_requires_close_near_extreme_and_directional_integrity():
    result = evaluate_module("dalton_trend_day_integrity", _trend_day())
    assert result["view"] == "BUY"
    assert result["source_books"] == DALTON_SOURCES
    assert result["dalton_trend_day"] is True

    sell = evaluate_module(
        "dalton_trend_day_integrity",
        _trend_day(side="SELL", dalton_direction="down"),
    )
    assert sell["view"] == "SELL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"dalton_day_type": "normal day"},
        {"dalton_close_location_percent": 15},
        {"dalton_countertrend_rotations": 3},
        {"dalton_directional_integrity": False},
    ],
)
def test_dalton_trend_day_waits_when_integrity_is_lost(overrides):
    result = evaluate_module("dalton_trend_day_integrity", _trend_day(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_dalton_auction_point_retest_requires_a_holding_level_and_directional_close():
    result = evaluate_module("dalton_auction_point_retest", _auction())
    assert result["view"] == "BUY"
    assert result["dalton_auction_point_holds"] is True

    sell = evaluate_module(
        "dalton_auction_point_retest",
        _auction(
            side="SELL",
            dalton_auction_point_direction="down",
            dalton_retest_close_direction="down",
        ),
    )
    assert sell["view"] == "SELL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"dalton_retest_holds": False},
        {"dalton_retest_close_direction": "down"},
        {"dalton_auction_point_violation_ticks": 3},
    ],
)
def test_dalton_auction_point_retest_waits_after_level_failure(overrides):
    result = evaluate_module("dalton_auction_point_retest", _auction(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize("algorithm_id", [
    "aldridge_pair_dislocation",
    "dalton_trend_day_integrity",
    "dalton_auction_point_retest",
])
def test_aldridge_dalton_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
