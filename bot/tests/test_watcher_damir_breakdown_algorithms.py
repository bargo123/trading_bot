from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Laurentiu Damir — Price Action Breakdown"


def _rejection_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "damir_value_high": 1.1100,
        "damir_value_low": 1.1000,
        "damir_rejection_level": 1.0980,
        "damir_rejection_side": "below",
        "damir_tail_or_excess_observed": True,
        "damir_first_initiative_direction": "up",
        "damir_responsive_move_to_value": True,
        "damir_second_initiative_direction": "up",
        "damir_second_initiative_confirmed": True,
        "damir_value_rejection_provenance": "observed_lower_timeframe_value_sequence",
        "damir_rejection_stop_pips": 12.0,
        "damir_rejection_target_pips": 30.0,
    }
    state.update(overrides)
    return state


def test_damir_value_rejection_requires_the_confirmed_two_initiative_sequence():
    buy = evaluate_module("damir_value_rejection_sequence", _rejection_state())
    sell = evaluate_module(
        "damir_value_rejection_sequence",
        _rejection_state(
            side="SELL",
            damir_rejection_level=1.1120,
            damir_rejection_side="above",
            damir_first_initiative_direction="down",
            damir_second_initiative_direction="down",
        ),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["damir_rejection_sequence_confirmed"] is True
    assert buy["source_books"] == [SOURCE]
    assert buy["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"damir_tail_or_excess_observed": False},
        {"damir_responsive_move_to_value": False},
        {"damir_second_initiative_confirmed": False},
        {"damir_second_initiative_direction": "down"},
        {"damir_rejection_side": "above"},
        {"damir_rejection_target_pips": 8.0},
    ],
)
def test_damir_value_rejection_waits_for_each_source_condition(overrides):
    result = evaluate_module("damir_value_rejection_sequence", _rejection_state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def _location_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "damir_value_trend": "uptrend",
        "damir_current_price": 1.1040,
        "damir_value_high": 1.1100,
        "damir_value_low": 1.1000,
        "damir_control_price": 1.1050,
        "damir_excess_high": 1.1140,
        "damir_excess_low": 1.0960,
        "damir_location_data_provenance": "observed_higher_timeframe_value_area",
        "damir_location_stop_pips": 15.0,
        "damir_location_target_pips": 35.0,
    }
    state.update(overrides)
    return state


def test_damir_value_location_uses_trend_aware_advantageous_zones():
    buy = evaluate_module("damir_value_location_guideline", _location_state())
    sell = evaluate_module(
        "damir_value_location_guideline",
        _location_state(side="SELL", damir_current_price=1.1120),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["damir_advantageous_zone"] == "uptrend_buy_excess_to_control"


@pytest.mark.parametrize(
    "overrides",
    [
        {"side": "BUY", "damir_current_price": 1.1080},
        {"side": "SELL", "damir_current_price": 1.1030},
        {"damir_control_price": 1.1120},
        {"damir_location_target_pips": 10.0},
    ],
)
def test_damir_value_location_rejects_non_advantageous_or_invalid_geometry(overrides):
    result = evaluate_module("damir_value_location_guideline", _location_state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def _health_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "damir_market_trend": "uptrend",
        "damir_recent_excess_side": "above",
        "damir_rotation_location": "lower",
        "damir_current_rotation_narrow": True,
        "damir_value_health_provenance": "observed_value_rotation_sequence",
    }
    state.update(overrides)
    return state


def test_damir_value_health_flags_opposing_excess_and_narrow_rotations():
    result = evaluate_module("damir_value_health_warning", _health_state())

    assert result["view"] == "WAIT"
    assert result["damir_trend_exhaustion_warning"] is True
    assert "do not buy" in result["reasons"][0].lower()


def test_damir_value_health_warns_on_the_downtrend_mirror_case():
    result = evaluate_module(
        "damir_value_health_warning",
        _health_state(
            side="SELL",
            damir_market_trend="downtrend",
            damir_recent_excess_side="below",
            damir_rotation_location="upper",
        ),
    )

    assert result["view"] == "WAIT"
    assert result["damir_trend_exhaustion_warning"] is True
    assert "do not sell" in result["reasons"][0].lower()


def test_damir_value_health_does_not_invent_a_warning_without_the_full_state():
    result = evaluate_module(
        "damir_value_health_warning",
        _health_state(damir_recent_excess_side="below"),
    )

    assert result["view"] == "WAIT"
    assert result["damir_trend_exhaustion_warning"] is False
    assert "no source trend-exhaustion warning" in result["reasons"][0].lower()
