from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Alexander Elder — The New Trading for a Living"


def _triple(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "elder_long_term_trend": "up",
        "elder_intermediate_wave": "decline",
        "elder_timeframe_ratio": 5.0,
        "elder_oscillator_signal": "below_zero",
        "elder_entry_technique": "ema_penetration",
        "elder_data_provenance": "causal_multi_timeframe_quote_bars",
    }
    state.update(overrides)
    return state


def _impulse(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "elder_ema_slope": "rising",
        "elder_macd_histogram_slope": "rising",
        "elder_data_provenance": "causal_ema_and_macd_quote_bars",
    }
    state.update(overrides)
    return state


def _force(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "elder_long_term_trend": "up",
        "elder_force_index_ema_period": 2,
        "elder_force_index_ema_value": -0.5,
        "elder_entry_trigger": "above_high",
        "elder_latest_bar_high": 1.1010,
        "elder_latest_bar_low": 1.0990,
        "elder_entry_price": 1.1011,
        "elder_stop_price": 1.0985,
        "elder_data_provenance": "causal_price_and_tick_volume_bars",
    }
    state.update(overrides)
    return state


def test_elder_triple_screen_uses_tide_wave_and_entry_direction():
    buy = evaluate_module("elder_triple_screen", _triple())
    sell = evaluate_module(
        "elder_triple_screen",
        _triple(
            side="SELL",
            elder_long_term_trend="down",
            elder_intermediate_wave="rally",
            elder_oscillator_signal="above_zero",
            elder_entry_technique="downside_breakout",
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"elder_timeframe_ratio": 3.0},
        {"elder_intermediate_wave": "up"},
        {"elder_oscillator_signal": "above_zero"},
        {"elder_entry_technique": "random_entry"},
    ],
)
def test_elder_triple_screen_waits_without_three_screen_alignment(overrides):
    result = evaluate_module("elder_triple_screen", _triple(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_elder_impulse_is_a_censorship_permission_not_a_fake_entry_signal():
    permitted = evaluate_module("elder_impulse_censorship", _impulse())
    prohibited = evaluate_module(
        "elder_impulse_censorship",
        _impulse(side="SELL"),
    )
    assert permitted["view"] == "PERMITTED"
    assert permitted["elder_impulse_state"] == "GREEN"
    assert prohibited["view"] == "WAIT"
    assert "prohibit" in prohibited["reasons"][0].lower()


def test_elder_impulse_blue_permits_both_sides():
    for side in ("BUY", "SELL"):
        result = evaluate_module(
            "elder_impulse_censorship",
            _impulse(side=side, elder_macd_histogram_slope="falling"),
        )
        assert result["view"] == "PERMITTED"
        assert result["elder_impulse_state"] == "BLUE"


def test_elder_force_index_marks_pullback_entry_and_structural_stop():
    buy = evaluate_module("elder_force_index_pullback", _force())
    sell = evaluate_module(
        "elder_force_index_pullback",
        _force(
            side="SELL",
            elder_long_term_trend="down",
            elder_force_index_ema_value=0.5,
            elder_entry_trigger="below_low",
            elder_entry_price=1.0989,
            elder_stop_price=1.1015,
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["elder_force_index_period"] == 2.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"elder_force_index_ema_period": 13},
        {"elder_force_index_ema_value": 0.5},
        {"elder_entry_trigger": "market"},
        {"elder_entry_price": 1.1000},
        {"elder_stop_price": 1.1015},
    ],
)
def test_elder_force_index_waits_without_source_pullback_geometry(overrides):
    result = evaluate_module("elder_force_index_pullback", _force(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize(
    "algorithm_id",
    ["elder_triple_screen", "elder_impulse_censorship", "elder_force_index_pullback"],
)
def test_elder_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False
