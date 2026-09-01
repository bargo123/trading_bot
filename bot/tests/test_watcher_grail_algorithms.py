from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "James Windsor — The Holy Grail Forex Trading System"


def _state(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "BUY",
        "grail_reference_pair": "GBPUSD",
        "grail_anchor_time": "08:00 UK",
        "grail_anchor_price": 1.2500,
        "grail_current_price": 1.2540,
        "grail_pip_size": 0.0001,
        "grail_breakout_distance_pips": 40,
        "grail_stop_pips": 80,
        "grail_target_pips": 240,
        "grail_trailing_stop_pips": 60,
        "grail_rule_version": "appendix_baseline",
        "grail_data_provenance": "causal_0800_uk_anchor_quote",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("side", "current", "expected"),
    [("BUY", 1.2540, "BUY"), ("SELL", 1.2460, "SELL")],
)
def test_grail_uses_the_0800_anchor_and_symmetric_price_trigger(side, current, expected):
    result = evaluate_module(
        "grail_time_anchor_breakout",
        _state(side=side, grail_current_price=current),
    )

    assert result["view"] == expected
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"grail_current_price": 1.2520},
        {"grail_anchor_time": "09:00 UK"},
        {"grail_target_pips": 280},
        {"grail_rule_version": "unverified_variant"},
        {"grail_reference_pair": "EURUSD"},
    ],
)
def test_grail_waits_when_the_baseline_rule_is_not_exactly_observed(overrides):
    result = evaluate_module("grail_time_anchor_breakout", _state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_grail_fails_closed_without_causal_anchor_evidence():
    result = evaluate_module(
        "grail_time_anchor_breakout",
        {"symbol": "GBPUSD", "side": "BUY"},
    )

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _lifecycle_state(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "BUY",
        "grail_reference_pair": "GBPUSD",
        "grail_anchor_time": "08:00 UK",
        "grail_anchor_price": 1.2500,
        "grail_buy_stop_price": 1.2540,
        "grail_sell_stop_price": 1.2460,
        "grail_pip_size": 0.0001,
        "grail_stop_pips": 80.0,
        "grail_target_pips": 240.0,
        "grail_trailing_stop_pips": 60.0,
        "grail_lifecycle_event": "ARMED",
        "grail_opposite_order_deleted": False,
        "grail_lifecycle_provenance": "observed timestamped GBPUSD order-state replay",
    }
    state.update(overrides)
    return state


def test_grail_lifecycle_arms_symmetric_orders_and_cancels_the_opposite_after_trigger():
    armed = evaluate_module("grail_bracket_lifecycle", _lifecycle_state())
    triggered = evaluate_module(
        "grail_bracket_lifecycle",
        _lifecycle_state(
            grail_lifecycle_event="BUY_TRIGGERED",
            grail_opposite_order_deleted=True,
        ),
    )

    assert armed["view"] == "WAIT"
    assert armed["grail_lifecycle_action"] == "BRACKET_ARMED"
    assert triggered["view"] == "BUY"
    assert triggered["grail_lifecycle_action"] == "DELETE_OPPOSITE_ORDER"
    assert triggered["execution_authority"] is False


def test_grail_lifecycle_closes_at_the_source_session_boundary():
    result = evaluate_module(
        "grail_bracket_lifecycle",
        _lifecycle_state(grail_lifecycle_event="TIME_CLOSE", grail_current_uk_time="18:00 UK"),
    )

    assert result["view"] == "WAIT"
    assert result["grail_lifecycle_action"] == "CLOSE_ALL_AT_SESSION_BOUNDARY"


@pytest.mark.parametrize(
    "overrides",
    [
        {"grail_buy_stop_price": 1.2539},
        {"grail_sell_stop_price": 1.2461},
        {"grail_lifecycle_event": "BUY_TRIGGERED", "grail_opposite_order_deleted": False},
        {"grail_lifecycle_event": "TIME_CLOSE", "grail_current_uk_time": "17:59 UK"},
    ],
)
def test_grail_lifecycle_waits_when_the_appendix_state_is_not_exact(overrides):
    result = evaluate_module("grail_bracket_lifecycle", _lifecycle_state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]
