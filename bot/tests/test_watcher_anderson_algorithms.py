from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Brian Anderson — The 1 Hour Trade"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "anderson_data_provenance": "causal_multi_timeframe_snapshot",
        "anderson_volume_provenance": "observed_traded_volume",
    }
    state.update(overrides)
    return state


def test_high_volume_runner_requires_opening_breakout_volume_and_green_flags():
    result = evaluate_module(
        "anderson_high_volume_runner",
        _state(
            anderson_volume_ratio=30.0,
            anderson_time_from_open_min=12.0,
            anderson_opening_range_breakout="confirmed",
            anderson_long_term_support=True,
            anderson_tight_low_volume_base=True,
            anderson_new_long_term_high=True,
            anderson_moving_average_breakout=True,
            anderson_resistance_overhead=False,
            anderson_recent_selloff=False,
            anderson_large_gap_up=False,
            anderson_ma_resistance=False,
        ),
    )

    assert result["view"] == "BUY"
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


def test_high_volume_runner_does_not_treat_tick_activity_as_traded_volume():
    result = evaluate_module(
        "anderson_high_volume_runner",
        _state(
            anderson_volume_ratio=30.0,
            anderson_volume_provenance="tick_activity_proxy",
            anderson_time_from_open_min=12.0,
            anderson_opening_range_breakout="confirmed",
            anderson_long_term_support=True,
            anderson_tight_low_volume_base=True,
            anderson_new_long_term_high=True,
            anderson_moving_average_breakout=True,
            anderson_resistance_overhead=False,
            anderson_recent_selloff=False,
            anderson_large_gap_up=False,
            anderson_ma_resistance=False,
        ),
    )

    assert result["view"] == "WAIT"
    assert any("volume" in warning.lower() for warning in result["warnings"])


def test_high_volume_runner_rejects_red_flags():
    result = evaluate_module(
        "anderson_high_volume_runner",
        _state(
            anderson_volume_ratio=35.0,
            anderson_time_from_open_min=10.0,
            anderson_opening_range_breakout="confirmed",
            anderson_long_term_support=True,
            anderson_tight_low_volume_base=True,
            anderson_new_long_term_high=True,
            anderson_moving_average_breakout=True,
            anderson_resistance_overhead=True,
            anderson_recent_selloff=False,
            anderson_large_gap_up=False,
            anderson_ma_resistance=False,
        ),
    )

    assert result["view"] == "WAIT"
    assert "red flag" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_high_volume_runner_fails_closed_without_required_inputs(side):
    result = evaluate_module("anderson_high_volume_runner", _state(side=side))

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _conditional_bracket(**overrides):
    state = {
        "symbol": "ABC",
        "side": "BUY",
        "anderson_first_15m_high": 5.15,
        "anderson_entry_stop_price": 5.16,
        "anderson_entry_limit_price": 5.19,
        "anderson_pullback_low": 4.93,
        "anderson_stop_price": 4.92,
        "anderson_tick_size": 0.01,
        "anderson_entry_buffer_ticks": 1,
        "anderson_order_type": "stop_limit",
        "anderson_bracket_type": "one_triggers_all",
        "anderson_stop_order_type": "stop_on_quote",
        "anderson_stop_reference": "opening_range_pullback_low",
        "anderson_data_provenance": "observed timestamped 15m and 1m order-state replay",
    }
    state.update(overrides)
    return state


def test_high_volume_runner_conditional_bracket_uses_breakout_and_pullback_stop():
    result = evaluate_module("anderson_conditional_bracket", _conditional_bracket())

    assert result["view"] == "BUY"
    assert result["anderson_order_action"] == "ARM_CONDITIONAL_BRACKET"
    assert result["anderson_entry_stop_price"] == 5.16
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"anderson_entry_stop_price": 5.17},
        {"anderson_order_type": "market"},
        {"anderson_bracket_type": "separate_orders"},
        {"anderson_stop_reference": "former_high"},
        {"anderson_stop_price": 5.14},
    ],
)
def test_high_volume_runner_conditional_bracket_waits_without_source_order_geometry(overrides):
    result = evaluate_module("anderson_conditional_bracket", _conditional_bracket(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]
