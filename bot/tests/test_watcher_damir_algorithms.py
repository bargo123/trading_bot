from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Laurentiu Damir — Trade the Price Action"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "damir_trend": "up",
        "damir_chart_timeframe": "4h",
        "damir_daily_ema200_aligned": True,
        "damir_correction_observed": True,
        "damir_fibonacci_retracement": 61.8,
        "damir_reversal_pattern": "morning_star",
        "damir_pattern_completed": True,
        "damir_entry_after_pattern_close": True,
        "damir_stop_pips": 30.0,
        "damir_target_pips": 100.0,
        "damir_data_provenance": "causal_4h_daily_quote_bars",
    }
    state.update(overrides)
    return state


def test_damir_confluence_reversal_follows_aligned_trend():
    buy = evaluate_module("damir_fib_confluence_reversal", _state())
    sell = evaluate_module(
        "damir_fib_confluence_reversal",
        _state(side="SELL", damir_trend="down", damir_reversal_pattern="hammer"),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]
    assert buy["damir_geometry"]["reward_risk"] > 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"damir_daily_ema200_aligned": False},
        {"damir_correction_observed": False},
        {"damir_fibonacci_retracement": 38.2},
        {"damir_pattern_completed": False},
        {"damir_entry_after_pattern_close": False},
        {"damir_target_pips": 20.0},
    ],
)
def test_damir_waits_without_full_source_confluence(overrides):
    result = evaluate_module("damir_fib_confluence_reversal", _state(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_damir_fails_closed_without_provenance():
    result = evaluate_module("damir_fib_confluence_reversal", {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_damir_reversal_requires_a_named_source_candlestick_pattern():
    result = evaluate_module(
        "damir_fib_confluence_reversal",
        _state(damir_reversal_pattern="made_up_pattern"),
    )

    assert result["view"] == "WAIT"
    assert "candlestick" in result["reasons"][0]


def _trend_change_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "damir_prior_trend": "down",
        "damir_last_swing_breached": True,
        "damir_correction_after_breach": True,
        "damir_new_swing_direction": "up",
        "damir_new_swing_confirmed": True,
        "damir_trend_change_data_provenance": "observed_4h_swing_sequence",
    }
    state.update(overrides)
    return state


def test_damir_trend_change_requires_breach_correction_and_confirmation():
    buy = evaluate_module("damir_confirmed_trend_change", _trend_change_state())
    sell = evaluate_module(
        "damir_confirmed_trend_change",
        _trend_change_state(
            side="SELL",
            damir_prior_trend="up",
            damir_new_swing_direction="down",
        ),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["damir_trend_change_confirmed"] is True
    assert buy["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"damir_last_swing_breached": False},
        {"damir_correction_after_breach": False},
        {"damir_new_swing_confirmed": False},
        {"damir_new_swing_direction": "down"},
    ],
)
def test_damir_trend_change_waits_for_the_complete_sequence(overrides):
    result = evaluate_module("damir_confirmed_trend_change", _trend_change_state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]
