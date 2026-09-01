from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Getting Started in Technical Analysis"


def _ma(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_ma_current": 1.1010,
        "schwager_ma_previous": 1.1000,
        "schwager_ma_minimum_turn": 0.0005,
        "schwager_market_regime": "trend",
        "schwager_ma_data_provenance": "observed timestamped moving average",
    }
    state.update(overrides)
    return state


def _breakout(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_range_duration": 40,
        "schwager_range_width": 0.001,
        "schwager_range_narrowness": "narrow",
        "schwager_breakout_direction": "UP",
        "schwager_breakout_penetration": 0.0002,
        "schwager_breakout_confirmation_count": 3,
        "schwager_breakout_required_confirmation": 3,
        "schwager_breakout_data_provenance": "observed timestamped chart bars",
    }
    state.update(overrides)
    return state


def _range(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_market_regime": "range",
        "schwager_range_predictability": "low",
        "schwager_range_strategy": "generic trend following",
        "schwager_range_boundary_breach": False,
        "schwager_range_data_provenance": "observed timestamped range bars",
    }
    state.update(overrides)
    return state


def test_schwager_moving_average_turn_works_in_trends_but_not_ranges():
    buy = evaluate_module("schwager_ma_turn_filter", _ma())
    sell = evaluate_module(
        "schwager_ma_turn_filter",
        _ma(side="SELL", schwager_ma_current=1.0990),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["schwager_ma_assessment"] == "CONFIRMED_TREND_TURN"
    assert buy["source_books"] == [SOURCE]

    range_state = evaluate_module(
        "schwager_ma_turn_filter",
        _ma(schwager_market_regime="range"),
    )
    assert range_state["view"] == "WAIT"
    assert range_state["schwager_ma_assessment"] == "RANGE_WHIPSAW_RISK"


@pytest.mark.parametrize(
    ("trend", "extreme", "close_relation", "expected"),
    [
        ("UP", "NEW_HIGH", "BELOW_PRIOR_LOW", "SELL"),
        ("DOWN", "NEW_LOW", "ABOVE_PRIOR_HIGH", "BUY"),
    ],
)
def test_schwager_restrictive_reversal_day_requires_close_beyond_the_prior_extreme(
    trend, extreme, close_relation, expected
):
    result = evaluate_module(
        "schwager_restrictive_reversal_day",
        {
            "symbol": "EURUSD",
            "side": expected,
            "schwager_reversal_day_trend": trend,
            "schwager_reversal_day_extreme": extreme,
            "schwager_reversal_day_close_relation": close_relation,
            "schwager_reversal_day_confirmation": True,
            "schwager_reversal_day_data_provenance": "observed timestamped completed bars",
        },
    )

    assert result["view"] == expected
    assert result["schwager_reversal_day_assessment"] == "RESTRICTIVE_REVERSAL_DAY"
    assert result["warnings"]


def test_schwager_restrictive_reversal_day_rejects_the_weaker_prior_close_definition():
    result = evaluate_module(
        "schwager_restrictive_reversal_day",
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "schwager_reversal_day_trend": "UP",
            "schwager_reversal_day_extreme": "NEW_HIGH",
            "schwager_reversal_day_close_relation": "BELOW_PRIOR_CLOSE",
            "schwager_reversal_day_confirmation": True,
            "schwager_reversal_day_data_provenance": "observed timestamped completed bars",
        },
    )

    assert result["view"] == "WAIT"
    assert "prior" in " ".join(result["reasons"]).lower()


def test_schwager_range_breakout_requires_penetration_and_explicit_confirmation():
    result = evaluate_module("schwager_range_breakout_confirmation", _breakout())
    assert result["view"] == "BUY"
    assert result["schwager_breakout_assessment"] == "CONFIRMED_NARROW"

    unconfirmed = evaluate_module(
        "schwager_range_breakout_confirmation",
        _breakout(schwager_breakout_confirmation_count=2),
    )
    assert unconfirmed["view"] == "WAIT"
    assert unconfirmed["schwager_breakout_assessment"] == "UNCONFIRMED"


def test_schwager_range_filter_warns_against_unpredictable_range_participation():
    result = evaluate_module("schwager_range_participation_filter", _range())
    assert result["view"] == "WAIT"
    assert result["schwager_range_assessment"] == "MINIMIZE_PARTICIPATION"
    assert result["directional_claim"] is False

    breached = evaluate_module(
        "schwager_range_participation_filter",
        _range(schwager_range_boundary_breach=True),
    )
    assert breached["schwager_range_assessment"] == "RANGE_INVALIDATED"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "schwager_ma_turn_filter",
        "schwager_range_breakout_confirmation",
        "schwager_range_participation_filter",
    ],
)
def test_schwager_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False


def _minor_reaction(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_reaction_trend": "UP",
        "schwager_reaction_pattern": "n_day_low",
        "schwager_reaction_lookback_n": 5,
        "schwager_reaction_resumption_trigger": "close_above_x_day_high",
        "schwager_reaction_lookback_x": 3,
        "schwager_reaction_resumption_confirmed": True,
        "schwager_reaction_data_provenance": "observed timestamped completed bars",
    }
    state.update(overrides)
    return state


def _long_ma_reaction(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_long_ma_trend": "UP",
        "schwager_long_ma_period": 40,
        "schwager_long_ma_value": 1.1000,
        "schwager_long_ma_price": 1.0995,
        "schwager_long_ma_reaction_confirmed": True,
        "schwager_long_ma_data_provenance": "observed timestamped moving average and quote bars",
    }
    state.update(overrides)
    return state


def _oscillator_confirmation(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_oscillator_extreme": "oversold",
        "schwager_price_reversal_direction": "UP",
        "schwager_price_reversal_confirmed": True,
        "schwager_oscillator_data_provenance": "observed timestamped oscillator and price bars",
    }
    state.update(overrides)
    return state


def _trend_adjusted_oscillator(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_oscillator_trend": "UP",
        "schwager_oscillator_extreme": "oversold",
        "schwager_trend_adjustment_observed": True,
        "schwager_trend_adjusted_oscillator_data_provenance": "observed timestamped trend and oscillator bars",
    }
    state.update(overrides)
    return state


def _island(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "schwager_island_type": "top",
        "schwager_island_first_gap_direction": "UP",
        "schwager_island_second_gap_direction": "DOWN",
        "schwager_island_days_since_completion": 4,
        "schwager_island_gap_filled": False,
        "schwager_island_confirmation": True,
        "schwager_island_data_provenance": "observed timestamped daily bars",
    }
    state.update(overrides)
    return state


def _equity(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_equity_deterioration_observed": True,
        "schwager_equity_deterioration_kind": "abrupt decline",
        "schwager_equity_data_provenance": "observed timestamped closed-trade equity curve",
    }
    state.update(overrides)
    return state


def test_schwager_minor_reaction_reentry_uses_trend_specific_extreme_and_close():
    buy = evaluate_module("schwager_minor_reaction_reentry", _minor_reaction())
    assert buy["view"] == "BUY"
    assert buy["schwager_reaction_assessment"] == "UPTREND_RESUMPTION"

    sell = evaluate_module(
        "schwager_minor_reaction_reentry",
        _minor_reaction(
            side="SELL",
            schwager_reaction_trend="DOWN",
            schwager_reaction_pattern="n_day_high",
            schwager_reaction_resumption_trigger="close_below_x_day_low",
        ),
    )
    assert sell["view"] == "SELL"
    assert sell["schwager_reaction_assessment"] == "DOWNTREND_RESUMPTION"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schwager_reaction_pattern": "n_day_high"},
        {"schwager_reaction_resumption_trigger": "close_below_x_day_low"},
        {"schwager_reaction_resumption_confirmed": False},
        {"schwager_reaction_lookback_n": 0},
    ],
)
def test_schwager_minor_reaction_reentry_waits_for_the_exact_resumption_state(overrides):
    result = evaluate_module("schwager_minor_reaction_reentry", _minor_reaction(**overrides))
    assert result["view"] == "WAIT"


def test_schwager_long_ma_reaction_buys_pullback_in_uptrend_and_sells_rally_in_downtrend():
    buy = evaluate_module("schwager_long_ma_reaction", _long_ma_reaction())
    assert buy["view"] == "BUY"
    assert buy["schwager_long_ma_assessment"] == "UPTREND_PULLBACK_TO_LONG_MA"

    sell = evaluate_module(
        "schwager_long_ma_reaction",
        _long_ma_reaction(
            side="SELL",
            schwager_long_ma_trend="DOWN",
            schwager_long_ma_price=1.1005,
        ),
    )
    assert sell["view"] == "SELL"
    assert sell["schwager_long_ma_assessment"] == "DOWNTREND_RALLY_TO_LONG_MA"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schwager_long_ma_period": 10},
        {"schwager_long_ma_trend": "UP", "schwager_long_ma_price": 1.1005},
        {"schwager_long_ma_reaction_confirmed": False},
    ],
)
def test_schwager_long_ma_reaction_does_not_trade_without_a_long_ma_pullback(overrides):
    result = evaluate_module("schwager_long_ma_reaction", _long_ma_reaction(**overrides))
    assert result["view"] == "WAIT"


def test_schwager_oscillator_is_only_an_alert_until_price_confirms_the_reversal():
    buy = evaluate_module("schwager_oscillator_price_confirmation", _oscillator_confirmation())
    assert buy["view"] == "BUY"
    assert buy["schwager_oscillator_assessment"] == "OVERSOLD_PRICE_CONFIRMED"

    alert = evaluate_module(
        "schwager_oscillator_price_confirmation",
        _oscillator_confirmation(schwager_price_reversal_confirmed=False),
    )
    assert alert["view"] == "WAIT"
    assert alert["schwager_oscillator_assessment"] == "ALERT_ONLY"

    mismatch = evaluate_module(
        "schwager_oscillator_price_confirmation",
        _oscillator_confirmation(schwager_price_reversal_direction="DOWN"),
    )
    assert mismatch["view"] == "WAIT"


def test_schwager_trend_adjusted_oscillator_keeps_the_useful_extreme_and_warns_on_the_bad_one():
    buy = evaluate_module("schwager_trend_adjusted_oscillator", _trend_adjusted_oscillator())
    assert buy["view"] == "BUY"
    assert buy["schwager_trend_adjustment"] == "UPTREND_OVERSOLD_ENTRY"

    warning = evaluate_module(
        "schwager_trend_adjusted_oscillator",
        _trend_adjusted_oscillator(schwager_oscillator_extreme="overbought"),
    )
    assert warning["view"] == "WAIT"
    assert warning["schwager_trend_adjustment"] == "UPTREND_OVERBOUGHT_COUNTERTREND_WARNING"

    down_buy_warning = evaluate_module(
        "schwager_trend_adjusted_oscillator",
        _trend_adjusted_oscillator(
            side="BUY",
            schwager_oscillator_trend="DOWN",
            schwager_oscillator_extreme="oversold",
        ),
    )
    assert down_buy_warning["view"] == "WAIT"


def test_schwager_island_reversal_requires_unfilled_gap_and_confirmation_delay():
    result = evaluate_module("schwager_island_reversal_validation", _island())
    assert result["view"] == "SELL"
    assert result["schwager_island_assessment"] == "VALID_TOP"

    too_early = evaluate_module(
        "schwager_island_reversal_validation",
        _island(schwager_island_days_since_completion=2),
    )
    assert too_early["view"] == "WAIT"

    filled = evaluate_module(
        "schwager_island_reversal_validation",
        _island(schwager_island_gap_filled=True),
    )
    assert filled["view"] == "WAIT"


def test_schwager_equity_deterioration_is_a_research_warning_not_a_trade_signal():
    result = evaluate_module("schwager_equity_deterioration_warning", _equity())
    assert result["view"] == "WAIT"
    assert result["directional_claim"] is False
    assert result["schwager_equity_assessment"] == "REDUCE_EXPOSURE_AND_REASSESS"
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "algorithm_id, state",
    [
        ("schwager_minor_reaction_reentry", _minor_reaction()),
        ("schwager_long_ma_reaction", _long_ma_reaction()),
        ("schwager_oscillator_price_confirmation", _oscillator_confirmation()),
        ("schwager_trend_adjusted_oscillator", _trend_adjusted_oscillator()),
        ("schwager_island_reversal_validation", _island()),
        ("schwager_equity_deterioration_warning", _equity()),
    ],
)
def test_new_schwager_algorithms_fail_closed_without_provenance(algorithm_id, state):
    provenance_keys = [key for key in state if "provenance" in key]
    for key in provenance_keys:
        state.pop(key)
    result = evaluate_module(algorithm_id, state)
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
