from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Jeremy du Plessis — The Definitive Guide to Point and Figure"


def _catapult(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "pf_box_reversal": "3-box",
        "pf_pattern_type": "triple_top",
        "pf_initial_breakout_boxes": 2,
        "pf_pullback_into_pattern": True,
        "pf_pullback_reverse_signal": False,
        "pf_second_breakout_beyond_initial": True,
        "pf_data_provenance": "causal_point_and_figure_from_quote_series",
    }
    state.update(overrides)
    return state


def test_point_figure_bullish_and_bearish_catapults_are_symmetric():
    buy = evaluate_module("pf_three_box_catapult", _catapult())
    sell = evaluate_module(
        "pf_three_box_catapult",
        _catapult(side="SELL", pf_pattern_type="triple_bottom"),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]
    assert buy["pf_catapult_geometry"]["initial_breakout_boxes"] == 2.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"pf_box_reversal": "1-box"},
        {"pf_pattern_type": "double_top"},
        {"pf_initial_breakout_boxes": 4},
        {"pf_pullback_into_pattern": False},
        {"pf_pullback_reverse_signal": True},
        {"pf_second_breakout_beyond_initial": False},
    ],
)
def test_point_figure_catapult_waits_when_any_source_condition_fails(overrides):
    result = evaluate_module("pf_three_box_catapult", _catapult(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_point_figure_catapult_fails_closed_without_provenance():
    result = evaluate_module("pf_three_box_catapult", {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _basic_signal(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "pf_box_reversal": "3-box",
        "pf_pattern_type": "double_top",
        "pf_pattern_structure": "continuation",
        "pf_breakout_direction": "up",
        "pf_pattern_columns": 3,
        "pf_breakout_confirmed": True,
        "pf_data_provenance": "causal_point_and_figure_from_quote_series",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("specific", "expected_view", "side"),
    [
        ({}, "BUY", "BUY"),
        (
            {
                "side": "SELL",
                "pf_pattern_type": "double_bottom",
                "pf_pattern_structure": "reversal",
                "pf_breakout_direction": "down",
                "pf_pattern_columns": 4,
            },
            "SELL",
            "SELL",
        ),
    ],
)
def test_point_figure_double_signal_requires_source_pattern_geometry(specific, expected_view, side):
    result = evaluate_module("pf_double_top_bottom", _basic_signal(**specific))

    assert result["view"] == expected_view
    assert result["candidate_side"] == side
    assert result["applicability"] == "APPLICABLE"


@pytest.mark.parametrize(
    "overrides",
    [
        {"pf_box_reversal": "1-box"},
        {"pf_pattern_type": "triple_top"},
        {"pf_pattern_structure": "reversal", "pf_pattern_columns": 3},
        {"pf_pattern_columns": 2},
        {"pf_breakout_direction": "down"},
        {"pf_breakout_confirmed": False},
    ],
)
def test_point_figure_double_signal_waits_when_a_named_condition_fails(overrides):
    result = evaluate_module("pf_double_top_bottom", _basic_signal(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_point_figure_triple_signal_requires_two_prior_tests():
    state = _basic_signal(
        pf_pattern_type="triple_top",
        pf_triple_level_tests=2,
        pf_breakout_direction="up",
    )
    result = evaluate_module("pf_triple_top_bottom", state)

    assert result["view"] == "BUY"
    assert result["pf_triple_level_tests"] == 2


@pytest.mark.parametrize(
    ("pattern", "direction", "expected"),
    [("triple_top", "up", "BUY"), ("triple_bottom", "down", "SELL")],
)
def test_point_figure_triple_signal_is_symmetric(pattern, direction, expected):
    result = evaluate_module(
        "pf_triple_top_bottom",
        _basic_signal(
            side=expected,
            pf_pattern_type=pattern,
            pf_triple_level_tests=2,
            pf_breakout_direction=direction,
        ),
    )
    assert result["view"] == expected


def test_point_figure_triple_signal_without_the_required_prior_tests_waits():
    result = evaluate_module(
        "pf_triple_top_bottom",
        _basic_signal(
            pf_pattern_type="triple_top",
            pf_triple_level_tests=1,
            pf_breakout_direction="up",
        ),
    )
    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("pole_type", "expected_view", "side"),
    [("high", "SELL", "SELL"), ("low", "BUY", "BUY")],
)
def test_point_figure_pole_reversal_uses_the_fifty_percent_rule(pole_type, expected_view, side):
    result = evaluate_module(
        "pf_pole_reversal",
        {
            "symbol": "EURUSD",
            "side": side,
            "pf_box_reversal": "3-box",
            "pf_pole_type": pole_type,
            "pf_initial_column_boxes": 10,
            "pf_reversal_column_boxes": 6,
            "pf_reversal_percent": 60,
            "pf_reversal_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == expected_view
    assert result["pf_reversal_percent"] == 60.0


def test_point_figure_pole_below_half_retracement_is_not_complete():
    result = evaluate_module(
        "pf_pole_reversal",
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "pf_box_reversal": "3-box",
            "pf_pole_type": "high",
            "pf_initial_column_boxes": 10,
            "pf_reversal_column_boxes": 4,
            "pf_reversal_percent": 40,
            "pf_reversal_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("line_trend", "signal_direction", "expected_view"),
    [("down", "up", "BUY"), ("up", "down", "SELL")],
)
def test_point_figure_trendline_break_requires_a_nearby_matching_signal(
    line_trend, signal_direction, expected_view
):
    result = evaluate_module(
        "pf_trendline_signal_confirmation",
        {
            "symbol": "EURUSD",
            "side": expected_view,
            "pf_trendline_trend": line_trend,
            "pf_trendline_signal_direction": signal_direction,
            "pf_trendline_signal_timing": "within_two_boxes_before",
            "pf_trendline_break_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == expected_view


def test_point_figure_trendline_break_without_nearby_signal_waits():
    result = evaluate_module(
        "pf_trendline_signal_confirmation",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "pf_trendline_trend": "down",
            "pf_trendline_signal_direction": "up",
            "pf_trendline_signal_timing": "none",
            "pf_trendline_break_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("first_pole", "second_pole", "expected_view", "side"),
    [
        ("high", "low", "BUY", "BUY"),
        ("low", "high", "SELL", "SELL"),
    ],
)
def test_point_figure_opposing_poles_confirm_the_second_reversal(
    first_pole, second_pole, expected_view, side
):
    result = evaluate_module(
        "pf_opposing_poles",
        {
            "symbol": "EURUSD",
            "side": side,
            "pf_first_pole_type": first_pole,
            "pf_second_pole_type": second_pole,
            "pf_opposing_poles_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )

    assert result["view"] == expected_view
    assert result["pf_opposing_poles_assessment"] == "CONFIRMED"


def test_point_figure_same_direction_poles_are_not_opposing():
    result = evaluate_module(
        "pf_opposing_poles",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "pf_first_pole_type": "high",
            "pf_second_pole_type": "high",
            "pf_opposing_poles_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("trend", "break_direction", "expected_view", "side"),
    [("up", "below", "SELL", "SELL"), ("down", "above", "BUY", "BUY")],
)
def test_point_figure_45_degree_line_break_requires_the_source_thrust_geometry(
    trend, break_direction, expected_view, side
):
    result = evaluate_module(
        "pf_45_degree_trendline",
        {
            "symbol": "EURUSD",
            "side": side,
            "pf_45_trend_direction": trend,
            "pf_45_reversal_boxes": 3,
            "pf_45_thrust_boxes": 5,
            "pf_45_break_direction": break_direction,
            "pf_45_break_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )

    assert result["view"] == expected_view
    assert result["pf_45_required_thrust_boxes"] == 5


def test_point_figure_45_degree_line_does_not_signal_before_break():
    result = evaluate_module(
        "pf_45_degree_trendline",
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "pf_45_trend_direction": "up",
            "pf_45_reversal_boxes": 3,
            "pf_45_thrust_boxes": 4,
            "pf_45_break_direction": "below",
            "pf_45_break_confirmed": False,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("trend", "extreme", "expected_view", "side"),
    [("up", "lower_low", "BUY", "BUY"), ("down", "higher_high", "SELL", "SELL")],
)
def test_point_figure_early_fulcrum_entry_uses_two_box_reaction_and_one_box_stop(
    trend, extreme, expected_view, side
):
    result = evaluate_module(
        "pf_early_fulcrum_entry",
        {
            "symbol": "EURUSD",
            "side": side,
            "pf_fulcrum_trend": trend,
            "pf_fulcrum_new_extreme": extreme,
            "pf_early_reaction_boxes": 2,
            "pf_early_stop_boxes": 1,
            "pf_early_entry_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == expected_view
    assert result["pf_early_entry_assessment"] == "CONFIRMED"


def test_point_figure_early_fulcrum_entry_waits_for_the_second_box():
    result = evaluate_module(
        "pf_early_fulcrum_entry",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "pf_fulcrum_trend": "up",
            "pf_fulcrum_new_extreme": "lower_low",
            "pf_early_reaction_boxes": 1,
            "pf_early_stop_boxes": 1,
            "pf_early_entry_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("trend", "signal", "expected_view", "side"),
    [("up", "up", "BUY", "BUY"), ("down", "down", "SELL", "SELL")],
)
def test_point_figure_trend_aligned_signal_supports_the_prevailing_trend(
    trend, signal, expected_view, side
):
    result = evaluate_module(
        "pf_trend_aligned_signal",
        {
            "symbol": "EURUSD",
            "side": side,
            "pf_prevailing_trend": trend,
            "pf_signal_direction": signal,
            "pf_signal_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == expected_view


def test_point_figure_countertrend_signal_is_not_promoted_by_the_filter():
    result = evaluate_module(
        "pf_trend_aligned_signal",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "pf_prevailing_trend": "down",
            "pf_signal_direction": "up",
            "pf_signal_confirmed": True,
            "pf_data_provenance": "causal_point_and_figure_from_quote_series",
        },
    )
    assert result["view"] == "WAIT"
