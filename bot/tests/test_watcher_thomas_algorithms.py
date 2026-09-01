from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "The 10XROI Trading System"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "thomas_push_pull_direction": "up",
        "thomas_push_pull_pattern": "confirmed_push_pull",
        "thomas_momentum_strength": "strong",
        "thomas_pullback_to_level": True,
        "thomas_hourly_confirmation": True,
        "thomas_level_role": "support",
        "thomas_candle_confirmation": "confirmed",
        "thomas_clear_stop": True,
        "thomas_session": "london",
        "thomas_target_r_multiple": 10.0,
        "thomas_data_provenance": "causal_daily_hourly_price_action_proxy",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("side", "direction", "level", "expected"),
    [("BUY", "up", "support", "BUY"), ("SELL", "down", "resistance", "SELL")],
)
def test_push_pull_requires_momentum_pullback_and_clear_hourly_entry(side, direction, level, expected):
    result = evaluate_module(
        "thomas_push_pull_10xroi",
        _state(side=side, thomas_push_pull_direction=direction, thomas_level_role=level),
    )

    assert result["view"] == expected
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"thomas_momentum_strength": "weak"},
        {"thomas_pullback_to_level": False},
        {"thomas_hourly_confirmation": False},
        {"thomas_clear_stop": False},
        {"thomas_target_r_multiple": 5.0},
        {"thomas_session": "asia"},
    ],
)
def test_push_pull_waits_when_source_context_is_not_clear(overrides):
    result = evaluate_module("thomas_push_pull_10xroi", _state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_push_pull_fails_closed_without_causal_evidence():
    result = evaluate_module("thomas_push_pull_10xroi", {"symbol": "EURUSD", "side": "BUY"})

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_breakout_context_recognizes_confirmed_source_breakout_families():
    result = evaluate_module(
        "thomas_breakout_context",
        _state(
            thomas_breakout_type="flag_continuation",
            thomas_breakout_direction="up",
            thomas_breakout_confirmation=True,
            thomas_opposing_level_clear=True,
            thomas_breakout_data_provenance="observed daily and hourly breakout context",
        ),
    )

    assert result["view"] == "BUY"
    assert result["thomas_breakout_assessment"] == "CONFIRMED_FLAG_CONTINUATION"
    assert result["execution_authority"] is False


def test_breakout_context_blocks_a_short_break_into_observed_support():
    result = evaluate_module(
        "thomas_breakout_context",
        _state(
            thomas_breakout_type="horizontal_continuation",
            thomas_breakout_direction="down",
            thomas_breakout_confirmation=True,
            thomas_opposing_level_clear=False,
            thomas_breakout_data_provenance="observed daily and hourly breakout context",
        ),
    )

    assert result["view"] == "WAIT"
    assert "support" in result["reasons"][0]


def test_parabolic_weekly_level_warning_only_applies_after_eight_r():
    result = evaluate_module(
        "thomas_parabolic_exhaustion_exit",
        _state(
            thomas_trade_in_profit=True,
            thomas_r_multiple=8.5,
            thomas_parabolic_move=True,
            thomas_weekly_level_near=True,
            thomas_parabolic_data_provenance="observed price and weekly-level context",
        ),
    )

    assert result["thomas_parabolic_action"] == "EXIT_END_OF_PARABOLIC_RUN"
    assert result["thomas_management_action"] == "RESEARCH_EXIT_WARNING"
    assert result["execution_authority"] is False
