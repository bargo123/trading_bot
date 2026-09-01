from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "John F. Carter — Mastering the Trade"


def _scalper(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carter_scalper_closes": [1.1000, 1.1010, 1.1020],
        "carter_scalper_trigger_low": 1.1005,
        "carter_scalper_prior_low": 1.0995,
        "carter_scalper_trigger_high": 1.1012,
        "carter_scalper_confirmation_close": 1.1015,
        "carter_scalper_data_provenance": "causal_completed_quote_bars",
    }
    state.update(overrides)
    return state


def _tick(**overrides):
    state = {
        "symbol": "YM",
        "side": "SELL",
        "carter_tick_market": "YM",
        "carter_tick_value": 1000,
        "carter_tick_minutes_et": 660,
        "carter_tick_zero_cross_seen": True,
        "carter_tick_hard_stopouts": 0,
        "carter_tick_data_provenance": "observed_nyse_tick_breadth",
    }
    state.update(overrides)
    return state


def _squeeze(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carter_squeeze_state": "released",
        "carter_squeeze_direction": "up",
        "carter_anchor_direction": "up",
        "carter_wave_a": 0.2,
        "carter_wave_b": 0.4,
        "carter_wave_c": 0.8,
        "carter_squeeze_momentum_slope": 0.5,
        "carter_squeeze_entry_edge": "near_ema",
        "carter_squeeze_data_provenance": "causal_multi_timeframe_quote_bars",
    }
    state.update(overrides)
    return state


def _bricks(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carter_brick_directions": ["DOWN", "DOWN", "DOWN", "UP", "UP", "UP"],
        "carter_brick_reference_high": 1.1000,
        "carter_brick_reference_low": 1.0900,
        "carter_brick_break_price": 1.1010,
        "carter_brick_data_provenance": "causal_fixed_size_quote_bricks",
    }
    state.update(overrides)
    return state


def _holp(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "carter_holp_mode": "LOHP",
        "carter_trend_direction": "up",
        "carter_extreme_lookback": 20,
        "carter_extreme_bar_high": 1.1100,
        "carter_extreme_bar_low": 1.1050,
        "carter_latest_close": 1.1040,
        "carter_data_provenance": "causal_completed_quote_bars",
    }
    state.update(overrides)
    return state


def _eod(**overrides):
    state = {
        "symbol": "ES",
        "side": "SELL",
        "carter_eod_market": "ES",
        "carter_eod_minutes_et": 952,
        "carter_eod_price_at_1530": 5000.0,
        "carter_eod_price_at_entry": 5001.5,
        "carter_eod_data_provenance": "causal_one_minute_index_future_bars",
    }
    state.update(overrides)
    return state


def _propulsion(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carter_propulsion_instrument": "stock",
        "carter_propulsion_timeframe": "daily",
        "carter_ema_fast": 105.0,
        "carter_ema_slow": 100.0,
        "carter_entry_price": 104.0,
        "carter_pullback_to_fast": True,
        "carter_data_provenance": "causal_daily_quote_bars",
    }
    state.update(overrides)
    return state


def test_carter_scalper_alert_requires_three_closes_and_price_confirmation():
    buy = evaluate_module("carter_scalper_alert", _scalper())
    sell = evaluate_module(
        "carter_scalper_alert",
        _scalper(
            side="SELL",
            carter_scalper_closes=[1.1020, 1.1010, 1.1000],
            carter_scalper_trigger_low=1.0988,
            carter_scalper_prior_low=1.0995,
            carter_scalper_trigger_high=1.1005,
            carter_scalper_prior_high=1.1015,
            carter_scalper_confirmation_close=1.0980,
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]
    assert evaluate_module("carter_scalper_alert", _scalper(carter_scalper_closes=[1.1, 1.0, 1.01]))["view"] == "WAIT"


def test_carter_tick_extreme_fade_is_market_and_session_specific():
    sell = evaluate_module("carter_tick_extreme_fade", _tick())
    buy = evaluate_module("carter_tick_extreme_fade", _tick(side="BUY", carter_tick_value=-1000))
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"
    assert sell["carter_tick_stop_points"] == 30.0
    assert sell["carter_tick_target_points"] == 20.0
    assert evaluate_module("carter_tick_extreme_fade", _tick(carter_tick_value=900))["view"] == "WAIT"
    assert evaluate_module("carter_tick_extreme_fade", _tick(carter_tick_minutes_et=950))["view"] == "WAIT"


def test_carter_anchor_squeeze_requires_anchor_alignment_and_entry_edge():
    buy = evaluate_module("carter_anchor_squeeze", _squeeze())
    sell_blocked = evaluate_module(
        "carter_anchor_squeeze",
        _squeeze(side="SELL", carter_squeeze_direction="down", carter_anchor_direction="up", carter_wave_c=-0.5),
    )
    assert buy["view"] == "BUY"
    assert sell_blocked["view"] == "WAIT"
    assert evaluate_module("carter_anchor_squeeze", _squeeze(carter_squeeze_entry_edge="chasing"))["view"] == "WAIT"


def test_carter_brick_reversal_uses_third_brick_reference_break():
    buy = evaluate_module("carter_brick_reversal", _bricks())
    sell = evaluate_module(
        "carter_brick_reversal",
        _bricks(
            side="SELL",
            carter_brick_directions=["UP", "UP", "UP", "DOWN", "DOWN", "DOWN"],
            carter_brick_break_price=1.0890,
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert evaluate_module("carter_brick_reversal", _bricks(carter_brick_break_price=1.0990))["view"] == "WAIT"


def test_carter_holp_lohp_requires_trend_extreme_and_close_break():
    sell = evaluate_module("carter_holp_lohp", _holp())
    buy = evaluate_module(
        "carter_holp_lohp",
        _holp(
            side="BUY",
            carter_holp_mode="HOLP",
            carter_trend_direction="down",
            carter_extreme_bar_high=1.0950,
            carter_extreme_bar_low=1.0900,
            carter_latest_close=1.0960,
        ),
    )
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"
    assert sell["carter_initial_stop"] == 1.1100
    assert evaluate_module("carter_holp_lohp", _holp(carter_latest_close=1.1060))["view"] == "WAIT"


def test_carter_end_of_day_fade_requires_exact_time_and_measured_move():
    sell = evaluate_module("carter_end_of_day_fade", _eod())
    buy = evaluate_module(
        "carter_end_of_day_fade",
        _eod(side="BUY", carter_eod_price_at_entry=4998.5),
    )
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"
    assert sell["carter_exit_minutes_et"] == 973.0
    assert evaluate_module("carter_end_of_day_fade", _eod(carter_eod_price_at_entry=5000.5))["view"] == "WAIT"
    assert evaluate_module("carter_end_of_day_fade", _eod(carter_eod_minutes_et=951))["view"] == "WAIT"


def test_carter_ema_propulsion_requires_trend_cross_and_pullback():
    buy = evaluate_module("carter_ema_propulsion", _propulsion())
    sell = evaluate_module(
        "carter_ema_propulsion",
        _propulsion(
            side="SELL",
            carter_ema_fast=95.0,
            carter_ema_slow=100.0,
            carter_entry_price=96.0,
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["carter_target_price"] == pytest.approx(112.32)
    assert buy["carter_watermark_percent"] == 4.0
    assert evaluate_module("carter_ema_propulsion", _propulsion(carter_pullback_to_fast=False))["view"] == "WAIT"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "carter_scalper_alert",
        "carter_tick_extreme_fade",
        "carter_anchor_squeeze",
        "carter_brick_reversal",
        "carter_holp_lohp",
        "carter_end_of_day_fade",
        "carter_ema_propulsion",
    ],
)
def test_carter_algorithms_fail_closed_without_observed_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False
