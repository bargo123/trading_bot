from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Al Brooks — Trading Price Action Trading Ranges"


def _state(**overrides):
    state = {
        "symbol": "ES",
        "side": "BUY",
        "brooks_breakout_direction": "UP",
        "brooks_initial_breakout_confirmed": True,
        "brooks_pullback_bars": 2,
        "brooks_pullback_reached_breakout": True,
        "brooks_opposite_signal": False,
        "brooks_follow_through_confirmed": True,
        "brooks_data_provenance": "causal_completed_quote_bars",
    }
    state.update(overrides)
    return state


def test_brooks_breakout_pullback_test_resumes_in_the_breakout_direction():
    buy = evaluate_module("brooks_breakout_pullback_test", _state())
    sell = evaluate_module(
        "brooks_breakout_pullback_test",
        _state(side="SELL", brooks_breakout_direction="DOWN"),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"brooks_initial_breakout_confirmed": False},
        {"brooks_pullback_bars": 6},
        {"brooks_pullback_reached_breakout": False},
        {"brooks_opposite_signal": True},
        {"brooks_follow_through_confirmed": False},
    ],
)
def test_brooks_waits_until_the_pullback_test_is_validated(overrides):
    result = evaluate_module("brooks_breakout_pullback_test", _state(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_brooks_fails_closed_without_provenance():
    result = evaluate_module("brooks_breakout_pullback_test", {"symbol": "ES", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False
