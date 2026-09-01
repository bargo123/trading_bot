from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Andrew Pole — Statistical Arbitrage"


def _popcorn(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "pole_spread_value": 3.0,
        "pole_local_mean": 1.0,
        "pole_local_scale": 1.0,
        "pole_entry_multiple": 2.0,
        "pole_exit_tolerance": 0.10,
        "pole_popcorn_position": "flat",
        "pole_popcorn_data_provenance": "observed timestamped spread",
    }
    state.update(overrides)
    return state


def _turning_point(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "pole_turning_point_type": "peak",
        "pole_turning_point_extreme_price": 100.0,
        "pole_turning_point_current_price": 98.0,
        "pole_turning_point_annualized_volatility": 0.05,
        "pole_turning_point_qualifying_fraction": 0.30,
        "pole_turning_point_data_provenance": "observed timestamped price series",
    }
    state.update(overrides)
    return state


def test_popcorn_rule_sells_a_sufficiently_distant_upper_spread_and_exposes_mean_exit():
    result = evaluate_module("pole_popcorn_reversion", _popcorn())

    assert result["source_books"] == [SOURCE]
    assert result["view"] == "SELL"
    assert result["pole_popcorn_action"] == "ENTER_SHORT_SPREAD"
    assert result["pole_popcorn_zscore"] == pytest.approx(2.0)
    assert result["pole_popcorn_exit_rule"] == "UNWIND_AT_LOCAL_MEAN"


def test_popcorn_rule_buys_a_sufficiently_distant_lower_spread():
    result = evaluate_module(
        "pole_popcorn_reversion",
        _popcorn(side="BUY", pole_spread_value=-1.0, pole_local_mean=1.0),
    )

    assert result["view"] == "BUY"
    assert result["pole_popcorn_action"] == "ENTER_LONG_SPREAD"
    assert result["pole_popcorn_zscore"] == pytest.approx(-2.0)


def test_popcorn_rule_has_no_position_when_spread_is_inside_entry_band():
    result = evaluate_module(
        "pole_popcorn_reversion",
        _popcorn(pole_spread_value=1.8),
    )

    assert result["view"] == "WAIT"
    assert result["pole_popcorn_action"] == "WAIT_IN_LOCAL_BAND"


@pytest.mark.parametrize(
    ("position", "spread", "action"),
    [
        ("long_spread", 1.05, "UNWIND_LONG_SPREAD_AT_MEAN"),
        ("short_spread", 0.95, "UNWIND_SHORT_SPREAD_AT_MEAN"),
    ],
)
def test_popcorn_rule_unwinds_an_open_position_at_the_local_mean(position, spread, action):
    result = evaluate_module(
        "pole_popcorn_reversion",
        _popcorn(pole_popcorn_position=position, pole_spread_value=spread),
    )

    assert result["view"] == "WAIT"
    assert result["pole_popcorn_action"] == action
    assert result["pole_popcorn_exit_triggered"] is True


def test_popcorn_rule_requires_observed_point_in_time_spread_data():
    result = evaluate_module(
        "pole_popcorn_reversion",
        _popcorn(pole_popcorn_data_provenance="synthetic fixture"),
    )

    assert result["view"] == "MISSING_DATA"
    assert "pole_popcorn_data_provenance" in result["missing_inputs"]


def test_turning_point_rule_confirms_a_peak_only_after_a_causal_reversal_move():
    result = evaluate_module("pole_turning_point_event", _turning_point())

    assert result["source_books"] == [SOURCE]
    assert result["view"] == "SELL"
    assert result["pole_turning_point_action"] == "CONFIRMED_PEAK"
    assert result["pole_turning_point_reversal_return"] == pytest.approx(-0.02)
    assert result["pole_turning_point_threshold_return"] == pytest.approx(-0.015)
    assert result["uses_future_data"] is False


def test_turning_point_rule_confirms_a_trough_with_the_mirrored_return():
    result = evaluate_module(
        "pole_turning_point_event",
        _turning_point(
            side="BUY",
            pole_turning_point_type="trough",
            pole_turning_point_extreme_price=100.0,
            pole_turning_point_current_price=102.0,
        ),
    )

    assert result["view"] == "BUY"
    assert result["pole_turning_point_action"] == "CONFIRMED_TROUGH"
    assert result["pole_turning_point_reversal_return"] == pytest.approx(0.02)


def test_turning_point_rule_waits_when_the_reversal_has_not_reached_the_volatility_fraction():
    result = evaluate_module(
        "pole_turning_point_event",
        _turning_point(pole_turning_point_current_price=99.5),
    )

    assert result["view"] == "WAIT"
    assert result["pole_turning_point_action"] == "WAIT_FOR_QUALIFYING_REVERSAL"


def _pair_selection(**overrides):
    state = {
        "symbol": "EURUSD",
        "pole_event_similarity": 0.85,
        "pole_interevent_return_correlation": -0.25,
        "pole_min_event_similarity": 0.70,
        "pole_max_interevent_return_correlation": 0.10,
        "pole_pair_selection_data_provenance": "observed timestamped event series",
    }
    state.update(overrides)
    return state


def test_event_pair_selection_requires_similar_risk_events_and_dispersed_interevent_returns():
    result = evaluate_module("pole_event_pair_selection", _pair_selection())

    assert result["view"] == "WAIT"
    assert result["pole_pair_selection_action"] == "SELECT_PAIR"
    assert result["pole_pair_risk_event_similarity"] == pytest.approx(0.85)
    assert result["pole_pair_interevent_return_correlation"] == pytest.approx(-0.25)


@pytest.mark.parametrize(
    "overrides",
    [
        {"pole_event_similarity": 0.60},
        {"pole_interevent_return_correlation": 0.40},
    ],
)
def test_event_pair_selection_rejects_a_pair_when_either_source_condition_fails(overrides):
    result = evaluate_module("pole_event_pair_selection", _pair_selection(**overrides))

    assert result["view"] == "WAIT"
    assert result["pole_pair_selection_action"] == "REJECT_PAIR"


def _staged(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "pole_staged_displacement": 4.0,
        "pole_staged_direction": "upper",
        "pole_staged_first_entry": 4.0,
        "pole_staged_next_entry": 6.0,
        "pole_staged_entry_capacity": 2,
        "pole_staged_existing_entries": 0,
        "pole_staged_data_provenance": "observed timestamped spread",
    }
    state.update(overrides)
    return state


def test_staged_spread_rule_enters_the_first_upper_displacement_at_the_first_level():
    result = evaluate_module("pole_staged_spread_entries", _staged())

    assert result["view"] == "SELL"
    assert result["pole_staged_action"] == "ENTER_FIRST_SHORT_SPREAD"
    assert result["pole_staged_required_displacement"] == pytest.approx(4.0)
    assert result["pole_staged_exit_policy"] == "SEPARATE_REVERSION_RULE"


def test_staged_spread_rule_enters_an_additional_upper_clip_only_at_the_next_level():
    result = evaluate_module(
        "pole_staged_spread_entries",
        _staged(pole_staged_displacement=6.0, pole_staged_existing_entries=1),
    )

    assert result["view"] == "SELL"
    assert result["pole_staged_action"] == "ADD_STAGED_SHORT_SPREAD"
    assert result["pole_staged_required_displacement"] == pytest.approx(6.0)


def test_staged_spread_rule_mirrors_the_lower_displacement_to_a_long_spread():
    result = evaluate_module(
        "pole_staged_spread_entries",
        _staged(side="BUY", pole_staged_direction="lower"),
    )

    assert result["view"] == "BUY"
    assert result["pole_staged_action"] == "ENTER_FIRST_LONG_SPREAD"


def test_staged_spread_rule_does_not_add_beyond_explicit_capacity():
    result = evaluate_module(
        "pole_staged_spread_entries",
        _staged(pole_staged_displacement=8.0, pole_staged_existing_entries=2),
    )

    assert result["view"] == "WAIT"
    assert result["pole_staged_action"] == "CAPACITY_REACHED"
