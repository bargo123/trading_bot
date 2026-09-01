from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Adam Grimes — The Art and Science of Technical Analysis"


def _pullback(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "grimes_trend_direction": "up",
        "grimes_pullback_direction": "down",
        "grimes_impulse_strength": "significant",
        "grimes_momentum_divergence": False,
        "grimes_retracement_percent": 50,
        "grimes_pullback_volatility_relative": 0.6,
        "grimes_continuation_confirmed": True,
        "grimes_data_provenance": "causal_multi_timeframe_quote_bars",
    }
    state.update(overrides)
    return state


def _pushes(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "grimes_trend_direction": "up",
        "grimes_push_prices": [1.1000, 1.1050, 1.1100],
        "grimes_push_bar_indexes": [10, 15, 20],
        "grimes_trendline_break": True,
        "grimes_data_provenance": "causal_swing_points",
    }
    state.update(overrides)
    return state


def test_grimes_pullback_requires_impulse_alignment_and_continuation():
    buy = evaluate_module("grimes_pullback_quality", _pullback())
    sell = evaluate_module(
        "grimes_pullback_quality",
        _pullback(
            side="SELL",
            grimes_trend_direction="down",
            grimes_pullback_direction="up",
            grimes_impulse_strength="strong",
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"grimes_pullback_direction": "up"},
        {"grimes_impulse_strength": "weak"},
        {"grimes_momentum_divergence": True},
        {"grimes_retracement_percent": 90},
        {"grimes_pullback_volatility_relative": 1.4},
        {"grimes_continuation_confirmed": False},
    ],
)
def test_grimes_pullback_waits_when_a_winning_characteristic_is_missing(overrides):
    result = evaluate_module("grimes_pullback_quality", _pullback(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_grimes_three_pushes_are_an_exhaustion_warning_not_a_countertrend_entry():
    result = evaluate_module("grimes_three_push_exhaustion", _pushes())
    assert result["view"] == "WAIT"
    assert result["grimes_exhaustion_warning"] is True
    assert result["candidate_alignment"] == "UNRESOLVED"

    down = evaluate_module(
        "grimes_three_push_exhaustion",
        _pushes(
            side="SELL",
            grimes_trend_direction="down",
            grimes_push_prices=[1.1100, 1.1050, 1.1000],
        ),
    )
    assert down["grimes_exhaustion_warning"] is True


def test_grimes_exhaustion_requires_symmetric_pushes_and_trendline_break():
    assert evaluate_module("grimes_three_push_exhaustion", _pushes(grimes_push_bar_indexes=[1, 2, 20]))["view"] == "WAIT"
    assert evaluate_module("grimes_three_push_exhaustion", _pushes(grimes_trendline_break=False))["grimes_exhaustion_warning"] is False


@pytest.mark.parametrize("algorithm_id", ["grimes_pullback_quality", "grimes_three_push_exhaustion"])
def test_grimes_algorithms_fail_closed_without_observed_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
