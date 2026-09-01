from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "W. D. Gann — How to Make Profits in Commodities"


def _state(**overrides):
    state = {
        "symbol": "WHEAT",
        "side": "BUY",
        "gann_market_trend": "declining",
        "gann_extreme_break": True,
        "gann_close_location": "near_high",
        "gann_data_provenance": "causal_daily_high_low_quote_bars",
    }
    state.update(overrides)
    return state


def test_gann_reverse_signal_day_reverses_after_a_decline_or_advance():
    buy = evaluate_module("gann_reverse_signal_day", _state())
    sell = evaluate_module(
        "gann_reverse_signal_day",
        _state(side="SELL", gann_market_trend="advancing", gann_close_location="near_low"),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"gann_extreme_break": False},
        {"gann_close_location": "mid_range"},
        {"gann_market_trend": "sideways"},
    ],
)
def test_gann_reverse_signal_day_waits_without_the_source_reversal_shape(overrides):
    result = evaluate_module("gann_reverse_signal_day", _state(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_gann_reverse_signal_day_fails_closed_without_provenance():
    result = evaluate_module("gann_reverse_signal_day", {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_gann_higher_tops_and_bottoms_follow_the_observed_trend():
    buy = evaluate_module(
        "gann_higher_tops_bottoms",
        {
            "symbol": "WHEAT",
            "side": "BUY",
            "gann_structure": "higher tops and higher bottoms",
            "gann_structure_confirmed": True,
            "gann_structure_data_provenance": "causal_completed_quote_bars",
        },
    )
    sell = evaluate_module(
        "gann_higher_tops_bottoms",
        {
            "symbol": "WHEAT",
            "side": "SELL",
            "gann_structure": "lower tops and lower bottoms",
            "gann_structure_confirmed": True,
            "gann_structure_data_provenance": "causal_completed_quote_bars",
        },
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["execution_authority"] is False


@pytest.mark.parametrize(
    "structure",
    ["higher tops", "mixed tops and bottoms", "range"],
)
def test_gann_higher_tops_and_bottoms_require_the_complete_progression(structure):
    result = evaluate_module(
        "gann_higher_tops_bottoms",
        {
            "symbol": "WHEAT",
            "side": "BUY",
            "gann_structure": structure,
            "gann_structure_confirmed": True,
            "gann_structure_data_provenance": "causal_completed_quote_bars",
        },
    )
    assert result["view"] == "WAIT"


def test_gann_halfway_point_requires_observed_interaction_not_just_a_level():
    buy = evaluate_module(
        "gann_halfway_point",
        {
            "symbol": "WHEAT",
            "side": "BUY",
            "gann_halfway_percent": 50.0,
            "gann_halfway_move": "up",
            "gann_halfway_interaction": "held_support",
            "gann_halfway_confirmed": True,
            "gann_halfway_data_provenance": "causal_swing_and_quote_bars",
        },
    )
    sell = evaluate_module(
        "gann_halfway_point",
        {
            "symbol": "WHEAT",
            "side": "SELL",
            "gann_halfway_percent": 50.0,
            "gann_halfway_move": "down",
            "gann_halfway_interaction": "crossed_down",
            "gann_halfway_confirmed": True,
            "gann_halfway_data_provenance": "causal_swing_and_quote_bars",
        },
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    no_interaction = dict(
        symbol="WHEAT",
        side="BUY",
        gann_halfway_percent=50.0,
        gann_halfway_move="up",
        gann_halfway_interaction="untested",
        gann_halfway_confirmed=True,
        gann_halfway_data_provenance="causal_swing_and_quote_bars",
    )
    assert evaluate_module("gann_halfway_point", no_interaction)["view"] == "WAIT"


def test_gann_repeated_levels_distinguish_double_and_triple_reversals():
    bottom = evaluate_module(
        "gann_repeated_level_reversal",
        {
            "symbol": "WHEAT",
            "side": "BUY",
            "gann_repeated_level_type": "bottom",
            "gann_repeated_level_tests": 2,
            "gann_repeated_level_break": "up",
            "gann_repeated_level_confirmed": True,
            "gann_repeated_level_data_provenance": "causal_completed_swing_bars",
        },
    )
    top = evaluate_module(
        "gann_repeated_level_reversal",
        {
            "symbol": "WHEAT",
            "side": "SELL",
            "gann_repeated_level_type": "top",
            "gann_repeated_level_tests": 3,
            "gann_repeated_level_break": "down",
            "gann_repeated_level_confirmed": True,
            "gann_repeated_level_data_provenance": "causal_completed_swing_bars",
        },
    )
    assert bottom["view"] == "BUY"
    assert top["view"] == "SELL"
    assert top["gann_repeated_level_strength"] == "TRIPLE_LEVEL"


def test_gann_secondary_reaction_uses_lower_top_or_higher_bottom_after_primary_move():
    sell = evaluate_module(
        "gann_secondary_reaction",
        {
            "symbol": "WHEAT",
            "side": "SELL",
            "gann_primary_trend": "bearish",
            "gann_secondary_pattern": "lower top",
            "gann_secondary_after_primary_move": True,
            "gann_secondary_confirmed": True,
            "gann_secondary_data_provenance": "causal_completed_swing_bars",
        },
    )
    buy = evaluate_module(
        "gann_secondary_reaction",
        {
            "symbol": "WHEAT",
            "side": "BUY",
            "gann_primary_trend": "bullish",
            "gann_secondary_pattern": "higher bottom",
            "gann_secondary_after_primary_move": True,
            "gann_secondary_confirmed": True,
            "gann_secondary_data_provenance": "causal_completed_swing_bars",
        },
    )
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"


def test_gann_fourth_same_level_is_distinct_from_a_double_or_triple_level():
    result = evaluate_module(
        "gann_fourth_level_reversal",
        {
            "symbol": "WHEAT",
            "side": "SELL",
            "gann_fourth_level_type": "top",
            "gann_fourth_level_tests": 4,
            "gann_fourth_level_break": "down",
            "gann_fourth_level_confirmed": True,
            "gann_fourth_level_data_provenance": "causal_completed_swing_bars",
        },
    )
    assert result["view"] == "SELL"
    assert result["gann_fourth_level_assessment"] == "FOURTH_TOP_REVERSAL"
    not_fourth = dict(
        symbol="WHEAT",
        side="SELL",
        gann_fourth_level_type="top",
        gann_fourth_level_tests=3,
        gann_fourth_level_break="down",
        gann_fourth_level_confirmed=True,
        gann_fourth_level_data_provenance="causal_completed_swing_bars",
    )
    assert evaluate_module("gann_fourth_level_reversal", not_fourth)["view"] == "WAIT"
