from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "John F. Carter — Mastering the Trade"


def _gap(**overrides):
    state = {
        "symbol": "YM",
        "side": "BUY",
        "carter_gap_market": "YM",
        "carter_gap_previous_close": 40000.0,
        "carter_gap_open": 39970.0,
        "carter_gap_premarket_volume_regime": "low",
        "carter_gap_session_minutes_et": 570,
        "carter_gap_day_of_week": "tuesday",
        "carter_gap_special_day": False,
        "carter_gap_data_provenance": "observed_cash_open_and_premarket_volume",
    }
    state.update(overrides)
    return state


def _pivot(**overrides):
    state = {
        "symbol": "ES",
        "side": "BUY",
        "carter_pivot_market": "ES",
        "carter_pivot_level": 5000.0,
        "carter_pivot_entry_price": 5000.25,
        "carter_pivot_next_level": 5002.0,
        "carter_pivot_next_next_level": 5004.0,
        "carter_pivot_day_type": "trending",
        "carter_pivot_five_min_volume": 30000,
        "carter_pivot_quarterway_advance": True,
        "carter_pivot_gap_playable": False,
        "carter_pivot_pullback_confirmed": True,
        "carter_pivot_minutes_et": 600,
        "carter_pivot_consecutive_hard_losses": 0,
        "carter_pivot_data_provenance": "observed_prior_session_pivots_and_quote_bars",
    }
    state.update(overrides)
    return state


def _mean(**overrides):
    state = {
        "symbol": "XAUUSD",
        "side": "SELL",
        "carter_mean_timeframe": "daily",
        "carter_mean_price": 1.115,
        "carter_mean_ema13": 1.100,
        "carter_mean_ema21": 1.101,
        "carter_mean_atr14": 0.010,
        "carter_mean_band_multiple": 1.5,
        "carter_mean_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _flow(**overrides):
    state = {
        "symbol": "ES",
        "side": "SELL",
        "carter_flow_market": "ES",
        "carter_flow_minutes_et": 720,
        "carter_flow_tick_value": -1400,
        "carter_flow_tick_ema8": -1200,
        "carter_flow_tick_ema21": -900,
        "carter_flow_persistent_extreme": True,
        "carter_flow_zero_retest_rejected": True,
        "carter_flow_data_provenance": "observed_nyse_tick_breadth",
    }
    state.update(overrides)
    return state


def test_carter_opening_gap_fade_uses_cash_open_and_premarket_volume():
    result = evaluate_module("carter_opening_gap_fade", _gap())
    assert result["view"] == "BUY"
    assert result["candidate_alignment"] == "SUPPORTS"
    assert result["carter_gap_points"] == 30.0
    assert result["carter_gap_stop_points"] == 45.0
    assert result["carter_gap_target_points"] == 30.0
    assert result["source_books"] == [SOURCE]

    sell = evaluate_module(
        "carter_opening_gap_fade",
        _gap(side="SELL", carter_gap_open=40050.0, carter_gap_premarket_volume_regime="moderate"),
    )
    assert sell["view"] == "SELL"
    assert sell["carter_gap_target_points"] == 25.0
    assert evaluate_module("carter_opening_gap_fade", _gap(carter_gap_premarket_volume_regime="high"))["view"] == "WAIT"
    assert evaluate_module("carter_opening_gap_fade", _gap(carter_gap_day_of_week="monday"))["view"] == "WAIT"
    assert evaluate_module("carter_opening_gap_fade", _gap(carter_gap_open=39995.0))["view"] == "WAIT"


def test_carter_pivot_play_requires_retracement_volume_filter_and_daily_loss_limit():
    result = evaluate_module("carter_pivot_play", _pivot())
    assert result["view"] == "BUY"
    assert result["carter_pivot_entry_offset_points"] == 0.25
    assert result["carter_pivot_stop_points"] == 2.0
    assert result["carter_pivot_first_target"] == 5002.0
    assert result["carter_pivot_second_target"] == 5004.0

    sell = evaluate_module(
        "carter_pivot_play",
        _pivot(side="SELL", carter_pivot_entry_price=4999.75),
    )
    assert sell["view"] == "SELL"
    assert evaluate_module("carter_pivot_play", _pivot(carter_pivot_quarterway_advance=False))["view"] == "WAIT"
    assert evaluate_module("carter_pivot_play", _pivot(carter_pivot_consecutive_hard_losses=2))["view"] == "WAIT"


def test_carter_atr_mean_reversion_requires_observed_daily_extension():
    result = evaluate_module("carter_atr_mean_reversion", _mean())
    assert result["view"] == "SELL"
    assert result["carter_mean_extension_atr"] == pytest.approx(1.45)
    buy = evaluate_module(
        "carter_atr_mean_reversion",
        _mean(side="BUY", carter_mean_price=1.086),
    )
    assert buy["view"] == "BUY"
    assert evaluate_module("carter_atr_mean_reversion", _mean(carter_mean_price=1.105))["view"] == "WAIT"
    assert evaluate_module("carter_atr_mean_reversion", _mean(carter_mean_timeframe="5m"))["view"] == "NOT_APPLICABLE"


def test_carter_tick_flow_follow_is_distinct_from_extreme_fade():
    result = evaluate_module("carter_tick_flow_follow", _flow())
    assert result["view"] == "SELL"
    assert result["carter_flow_regime"] == "persistent_selling"
    buy = evaluate_module(
        "carter_tick_flow_follow",
        _flow(
            side="BUY",
            carter_flow_tick_value=1400,
            carter_flow_tick_ema8=1200,
            carter_flow_tick_ema21=900,
            carter_flow_zero_retest_rejected=True,
        ),
    )
    assert buy["view"] == "BUY"
    assert evaluate_module("carter_tick_flow_follow", _flow(carter_flow_persistent_extreme=False))["view"] == "WAIT"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "carter_opening_gap_fade",
        "carter_pivot_play",
        "carter_atr_mean_reversion",
        "carter_tick_flow_follow",
    ],
)
def test_carter_expansions_fail_closed_without_observed_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False
