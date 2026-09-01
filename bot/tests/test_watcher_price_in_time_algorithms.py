from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "The Price in Time — Forex Strategy"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "pit_data_provenance": "causal_session_range_quote_proxy",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("side", "direction", "expected"),
    [("BUY", "up", "BUY"), ("SELL", "down", "SELL")],
)
def test_ntz_breakout_requires_valid_range_london_timing_and_confirmation(side, direction, expected):
    result = evaluate_module(
        "price_in_time_ntz_breakout",
        _state(
            side=side,
            pit_session="london_after_0800_gmt",
            pit_ntz_width_pips=19.0,
            pit_breakout_direction=direction,
            pit_breakout_confirmation="confirmed",
            pit_inside_ntz=False,
            pit_anomalous_day=False,
        ),
    )

    assert result["view"] == expected
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"pit_ntz_width_pips": 8.0},
        {"pit_ntz_width_pips": 35.0},
        {"pit_session": "inside_ntz_before_london"},
        {"pit_inside_ntz": True},
        {"pit_anomalous_day": True},
    ],
)
def test_ntz_breakout_waits_when_the_range_or_session_is_not_valid(overrides):
    state = _state(
        pit_session="london_after_0800_gmt",
        pit_ntz_width_pips=19.0,
        pit_breakout_direction="up",
        pit_breakout_confirmation="confirmed",
        pit_inside_ntz=False,
        pit_anomalous_day=False,
    )
    state.update(overrides)
    result = evaluate_module("price_in_time_ntz_breakout", state)

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_ntz_breakout_fails_closed_without_session_range_evidence():
    result = evaluate_module("price_in_time_ntz_breakout", _state())

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _management_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "pit_management_model": "MODEL_1",
        "pit_tp_stage": 1,
        "pit_management_data_provenance": "observed timestamped NTZ trade-management replay",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("model", "stage", "action"),
    [
        ("MODEL_1", 1, "MOVE_STOP_TO_BREAKEVEN"),
        ("MODEL_1", 2, "MOVE_STOP_TO_TP1"),
        ("MODEL_1", 3, "MOVE_STOP_TO_TP2"),
        ("MODEL_2", 1, "CLOSE_HALF_KEEP_STOP"),
        ("MODEL_2", 2, "MOVE_STOP_TO_TP1"),
        ("MODEL_2", 3, "CLOSE_REMAINDER_AT_TP3"),
        ("MODEL_3", 1, "MOVE_STOP_TO_BREAKEVEN"),
        ("MODEL_3", 2, "CLOSE_ALL_AT_TP2"),
    ],
)
def test_ntz_management_models_follow_the_source_tp_lifecycle(model, stage, action):
    result = evaluate_module(
        "price_in_time_trade_management_models",
        _management_state(pit_management_model=model, pit_tp_stage=stage),
    )

    assert result["pit_management_action"] == action
    assert result["view"] == "WAIT"
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"pit_management_model": "MODEL_4"},
        {"pit_tp_stage": 5},
        {"pit_tp_stage": 0},
    ],
)
def test_ntz_management_models_wait_on_undefined_source_states(overrides):
    result = evaluate_module(
        "price_in_time_trade_management_models",
        _management_state(**overrides),
    )

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_opening_price_break_is_a_distinct_directional_perspective():
    result = evaluate_module(
        "price_in_time_opening_price",
        _state(
            pit_europe_open_price=1.1000,
            pit_current_price=1.1003,
            pit_opening_price_relation="above",
            pit_opening_cross_direction="up",
            pit_opening_data_provenance="observed Frankfurt opening quote",
        ),
    )

    assert result["view"] == "BUY"
    assert result["pit_opening_assessment"] == "UPWARD_OPENING_BREAK"
    assert result["execution_authority"] is False


@pytest.mark.parametrize("window", ["asian", "frankfurt_ntz", "post_london"])
def test_price_in_time_session_filter_excludes_non_trading_windows(window):
    result = evaluate_module(
        "price_in_time_session_filter",
        _state(
            pit_session_window=window,
            pit_session_data_provenance="observed GMT session clock",
        ),
    )

    assert result["view"] == "WAIT"
    assert result["pit_session_assessment"] == "EXCLUDE_SESSION"
    assert result["pit_session_action"] == "NO_TRADE"


def test_price_in_time_session_filter_allows_london_and_new_york_overlap():
    result = evaluate_module(
        "price_in_time_session_filter",
        _state(
            pit_session_window="london_new_york_overlap",
            pit_session_data_provenance="observed GMT session clock",
        ),
    )

    assert result["view"] == "WAIT"
    assert result["pit_session_assessment"] == "TRADE_WINDOW"
    assert result["pit_session_action"] == "ALLOW_SOURCE_WINDOW"


def test_price_in_time_anomaly_filter_rejects_large_asian_move():
    result = evaluate_module(
        "price_in_time_anomaly_filter",
        _state(
            pit_anomalous_day="anomalous_quote_range_proxy",
            pit_asian_width_pips=52.0,
            pit_asian_range_limit_pips=40.0,
            pit_anomaly_data_provenance="observed causal Asian quote range",
            pit_macro_event_state="clear",
            pit_holiday_state="open",
        ),
    )

    assert result["pit_anomaly_assessment"] == "EXCLUDE_ABNORMAL_DAY"
    assert result["pit_session_action"] == "NO_TRADE"
    assert result["view"] == "WAIT"


def test_pending_order_variant_keeps_opposite_order_after_early_target_reversal():
    result = evaluate_module(
        "price_in_time_pending_order",
        _state(
            pit_first_trade_status="tp1_reached",
            pit_second_pending_order_active=True,
            pit_second_pending_order_side="SELL",
            pit_pending_order_data_provenance="observed timestamped NTZ trade state",
            pit_session_window="london_morning",
            pit_direction_change_after_target=True,
        ),
    )

    assert result["pit_pending_order_action"] == "KEEP_OPPOSITE_PENDING"


def test_model_one_moves_stop_to_previous_target_at_tp4():
    result = evaluate_module(
        "price_in_time_trade_management_models",
        _management_state(pit_management_model="MODEL_1", pit_tp_stage=4),
    )

    assert result["pit_management_action"] == "MOVE_STOP_TO_TP3"
