from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Beat the Forex Dealer"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "silvani_crowded_side": "SELL",
        "silvani_positioning_extreme": True,
        "silvani_market_trend": "up",
        "silvani_data_provenance": "observed_retail_positioning_report",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("side", "crowded", "trend", "expected"),
    [
        ("BUY", "SELL", "up", "BUY"),
        ("SELL", "BUY", "down", "SELL"),
    ],
)
def test_retail_crowding_supports_a_contrarian_trend_aligned_view(side, crowded, trend, expected):
    result = evaluate_module(
        "silvani_retail_contrarian",
        _state(side=side, silvani_crowded_side=crowded, silvani_market_trend=trend),
    )

    assert result["view"] == expected
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"silvani_positioning_extreme": False},
        {"silvani_crowded_side": "BUY", "silvani_market_trend": "up"},
        {"silvani_market_trend": "range"},
    ],
)
def test_retail_contrarian_waits_without_extreme_divergent_evidence(overrides):
    result = evaluate_module("silvani_retail_contrarian", _state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_retail_contrarian_fails_closed_without_observed_positioning():
    result = evaluate_module("silvani_retail_contrarian", {"symbol": "EURUSD", "side": "BUY"})

    assert result["view"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _pivot_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "silvani_pivot_high_4h": 1.1100,
        "silvani_pivot_low_4h": 1.1000,
        "silvani_pivot_close_4h": 1.1050,
        "silvani_rolling_pivot": 1.1050,
        "silvani_current_price": 1.1060,
        "silvani_pivot_event": "filter_not_break",
        "silvani_pivot_data_provenance": "observed timestamped four-hour OHLC",
    }
    state.update(overrides)
    return state


def test_rolling_pivot_filter_allows_only_the_side_above_or_below_pivot():
    buy = evaluate_module("silvani_rolling_pivot_filter", _pivot_state())
    sell = evaluate_module(
        "silvani_rolling_pivot_filter",
        _pivot_state(side="SELL", silvani_current_price=1.1040),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["silvani_pivot"] == pytest.approx(1.1050)
    assert buy["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"silvani_rolling_pivot": 1.1049},
        {"silvani_current_price": 1.1050},
        {"silvani_pivot_event": "breaking_pivot"},
    ],
)
def test_rolling_pivot_filter_waits_without_exact_non_breaking_context(overrides):
    result = evaluate_module("silvani_rolling_pivot_filter", _pivot_state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def _friday_stop_run(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "SELL",
        "silvani_friday_event": "friday_stop_run_setup",
        "silvani_weekday": "Friday",
        "silvani_retail_side": "BUY",
        "silvani_artificial_support": True,
        "silvani_stop_cluster_observed": True,
        "silvani_price_approaching_support": True,
        "silvani_support_level": 1.2500,
        "silvani_current_price": 1.2502,
        "silvani_pip_size": 0.0001,
        "silvani_target_pips": 15.0,
        "silvani_friday_data_provenance": "observed timestamped Friday quote and stop-cluster study",
    }
    state.update(overrides)
    return state


def test_friday_stop_run_fade_targets_the_opposite_side_of_retail_support():
    result = evaluate_module("silvani_friday_stop_run", _friday_stop_run())

    assert result["view"] == "SELL"
    assert result["silvani_stop_run_assessment"] == "FADE_RETAIL_SUPPORT"
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"silvani_weekday": "Thursday"},
        {"silvani_artificial_support": False},
        {"silvani_stop_cluster_observed": False},
        {"silvani_target_pips": 25.0},
    ],
)
def test_friday_stop_run_waits_without_the_complete_setup(overrides):
    result = evaluate_module("silvani_friday_stop_run", _friday_stop_run(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]
