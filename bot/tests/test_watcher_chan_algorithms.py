from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale"


def _linear(**overrides):
    state = {
        "symbol": "USDCAD",
        "side": "BUY",
        "chan_linear_zscore": -2.0,
        "chan_linear_entry_zscore": 1.0,
        "chan_linear_half_life": 10.0,
        "chan_linear_horizon": 5.0,
        "chan_linear_stationarity": "validated",
        "chan_linear_data_provenance": "causal_daily_price_series",
    }
    state.update(overrides)
    return state


def _kalman(**overrides):
    state = {
        "symbol": "EWC",
        "side": "BUY",
        "chan_kalman_pair": "EWA-EWC",
        "chan_kalman_error": -0.20,
        "chan_kalman_predicted_std": 0.10,
        "chan_kalman_entry_sigma": 1.0,
        "chan_kalman_beta": 1.0,
        "chan_kalman_data_provenance": "causal_pair_quote_series",
    }
    state.update(overrides)
    return state


def _cross_sectional(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "chan_cross_sectional_relative_return": -0.03,
        "chan_cross_sectional_universe_mean": 0.01,
        "chan_cross_sectional_normalization": 0.08,
        "chan_cross_sectional_universe_n": 100,
        "chan_cross_sectional_rank_ready": True,
        "chan_cross_sectional_data_provenance": "causal_universe_close_returns",
    }
    state.update(overrides)
    return state


def _time_series(**overrides):
    state = {
        "symbol": "TU",
        "side": "BUY",
        "chan_tsm_past_return": 0.08,
        "chan_tsm_lookback_days": 250,
        "chan_tsm_holding_days": 25,
        "chan_tsm_timeframe": "daily",
        "chan_tsm_parameter_validation": "chronological_oos",
        "chan_tsm_data_provenance": "causal_daily_futures_returns",
    }
    state.update(overrides)
    return state


def _alexander(**overrides):
    state = {
        "symbol": "CL",
        "side": "BUY",
        "chan_alexander_reference_price": 100.0,
        "chan_alexander_current_price": 101.5,
        "chan_alexander_subsequent_peak": 101.5,
        "chan_alexander_threshold": 0.01,
        "chan_alexander_data_provenance": "causal_daily_price_series",
    }
    state.update(overrides)
    return state


def test_linear_mean_reversion_buys_negative_zscore_and_sells_positive_zscore():
    buy = evaluate_module("chan_linear_mean_reversion", _linear())
    sell = evaluate_module(
        "chan_linear_mean_reversion",
        _linear(side="SELL", chan_linear_zscore=2.0),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]
    assert buy["execution_authority"] is False


def test_linear_mean_reversion_waits_without_stationarity_or_horizon_support():
    for overrides in (
        {"chan_linear_stationarity": "failed"},
        {"chan_linear_horizon": 20.0},
        {"chan_linear_zscore": 0.2},
    ):
        result = evaluate_module("chan_linear_mean_reversion", _linear(**overrides))
        assert result["view"] == "WAIT"
        assert result["reasons"]


def test_kalman_mean_reversion_uses_error_against_predicted_standard_deviation():
    buy = evaluate_module("chan_kalman_mean_reversion", _kalman())
    sell = evaluate_module(
        "chan_kalman_mean_reversion",
        _kalman(side="SELL", chan_kalman_error=0.20),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


def test_kalman_mean_reversion_waits_inside_the_predicted_error_band():
    result = evaluate_module(
        "chan_kalman_mean_reversion",
        _kalman(chan_kalman_error=0.05),
    )

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_cross_sectional_mean_reversion_buys_underperformers_and_sells_overperformers():
    buy = evaluate_module("chan_cross_sectional_mean_reversion", _cross_sectional())
    sell = evaluate_module(
        "chan_cross_sectional_mean_reversion",
        _cross_sectional(side="SELL", chan_cross_sectional_relative_return=0.03),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


def test_cross_sectional_mean_reversion_waits_without_a_causal_universe_rank():
    result = evaluate_module(
        "chan_cross_sectional_mean_reversion",
        _cross_sectional(chan_cross_sectional_rank_ready=False),
    )

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_time_series_momentum_uses_the_validated_past_return_sign():
    buy = evaluate_module("chan_time_series_momentum", _time_series())
    sell = evaluate_module(
        "chan_time_series_momentum",
        _time_series(side="SELL", chan_tsm_past_return=-0.08),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


def test_time_series_momentum_waits_for_daily_oos_parameter_selection():
    result = evaluate_module(
        "chan_time_series_momentum",
        _time_series(chan_tsm_parameter_validation="in_sample"),
    )

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_alexander_filter_buys_after_up_threshold_and_sells_after_peak_drawdown():
    buy = evaluate_module("chan_alexander_filter", _alexander())
    sell = evaluate_module(
        "chan_alexander_filter",
        _alexander(side="SELL", chan_alexander_current_price=100.0, chan_alexander_subsequent_peak=101.5),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [SOURCE]


def test_alexander_filter_waits_without_a_threshold_break():
    result = evaluate_module(
        "chan_alexander_filter",
        _alexander(chan_alexander_current_price=100.5),
    )

    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "chan_linear_mean_reversion",
        "chan_kalman_mean_reversion",
        "chan_cross_sectional_mean_reversion",
        "chan_time_series_momentum",
        "chan_alexander_filter",
    ],
)
def test_chan_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _opening_gap(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "BUY",
        "chan_gap_open_price": 1.1050,
        "chan_gap_prior_high": 1.1000,
        "chan_gap_prior_low": 1.0950,
        "chan_gap_reference_volatility": 0.02,
        "chan_gap_entry_zscore": 0.1,
        "chan_gap_data_provenance": "observed timestamped session open and prior range",
    }
    state.update(overrides)
    return state


def _news_drift(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "chan_news_event_present": True,
        "chan_news_event_timing": "after_close_before_open",
        "chan_news_open_return": 0.012,
        "chan_news_baseline_std": 0.01,
        "chan_news_event_type": "macro_release",
        "chan_news_data_provenance": "observed timestamped event calendar and executable open",
    }
    state.update(overrides)
    return state


def _stop_trigger(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "chan_stop_level": 1.1000,
        "chan_stop_price": 1.1002,
        "chan_stop_level_role": "resistance",
        "chan_stop_break_confirmed": True,
        "chan_stop_data_provenance": "observed timestamped support resistance and quote break",
    }
    state.update(overrides)
    return state


def _order_flow(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "chan_order_flow_value": 125.0,
        "chan_order_flow_min_abs": 100.0,
        "chan_order_flow_lookback": 20,
        "chan_order_flow_source": "real_transaction_signed_volume",
        "chan_order_flow_data_provenance": "observed timestamped trade and quote tape",
    }
    state.update(overrides)
    return state


def _imbalance(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "chan_bid_size": 300.0,
        "chan_ask_size": 100.0,
        "chan_imbalance_min_ratio": 2.0,
        "chan_imbalance_data_provenance": "observed timestamped level two order book",
    }
    state.update(overrides)
    return state


def _rebalance(**overrides):
    state = {
        "symbol": "SPY",
        "side": "BUY",
        "chan_rebalance_underlying_return": 0.025,
        "chan_rebalance_threshold": 0.02,
        "chan_rebalance_minutes_to_close": 10.0,
        "chan_rebalance_window_minutes": 15.0,
        "chan_rebalance_data_provenance": "observed timestamped leveraged-fund rebalance state",
    }
    state.update(overrides)
    return state


def _kelly(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "chan_kelly_p_win": 0.60,
        "chan_kelly_avg_win_loss_ratio": 1.5,
        "chan_kelly_max_leverage": 1.0,
        "chan_kelly_fraction": 0.5,
        "chan_kelly_data_provenance": "observed chronological net trade outcomes",
    }
    state.update(overrides)
    return state


def test_chan_opening_gap_momentum_requires_a_volatility_scaled_break_of_prior_range():
    result = evaluate_module("chan_opening_gap_momentum", _opening_gap())
    assert result["view"] == "BUY"
    assert result["chan_gap_assessment"] == "UP_GAP_BREAK"

    quiet = evaluate_module("chan_opening_gap_momentum", _opening_gap(chan_gap_open_price=1.1005))
    assert quiet["view"] == "WAIT"


def test_chan_news_drift_requires_event_timing_and_a_half_sigma_open_move():
    result = evaluate_module("chan_news_drift", _news_drift())
    assert result["view"] == "BUY"
    assert result["chan_news_assessment"] == "POST_EVENT_DRIFT"

    mistimed = evaluate_module("chan_news_drift", _news_drift(chan_news_event_timing="during_open"))
    assert mistimed["view"] == "WAIT"


def test_chan_stop_trigger_momentum_requires_confirmed_support_or_resistance_breach():
    result = evaluate_module("chan_stop_order_momentum", _stop_trigger())
    assert result["view"] == "BUY"
    assert result["chan_stop_assessment"] == "RESISTANCE_STOP_CASCADE"

    unconfirmed = evaluate_module("chan_stop_order_momentum", _stop_trigger(chan_stop_break_confirmed=False))
    assert unconfirmed["view"] == "WAIT"


def test_chan_order_flow_momentum_uses_signed_transaction_flow_not_volume_proxy():
    result = evaluate_module("chan_order_flow_momentum", _order_flow())
    assert result["view"] == "BUY"
    assert result["chan_order_flow_assessment"] == "POSITIVE_FLOW"

    proxy = evaluate_module(
        "chan_order_flow_momentum",
        _order_flow(chan_order_flow_source="tick_volume_proxy"),
    )
    assert proxy["view"] == "MISSING_DATA"


def test_chan_bid_ask_imbalance_requires_a_real_book_ratio():
    buy = evaluate_module("chan_bid_ask_imbalance", _imbalance())
    sell = evaluate_module(
        "chan_bid_ask_imbalance",
        _imbalance(side="SELL", chan_bid_size=100.0, chan_ask_size=300.0),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["chan_imbalance_ratio"] == pytest.approx(3.0)


def test_chan_leveraged_rebalance_momentum_is_limited_to_the_close_window():
    result = evaluate_module("chan_leveraged_rebalance_momentum", _rebalance())
    assert result["view"] == "BUY"
    assert result["chan_rebalance_assessment"] == "CLOSE_REBALANCE_MOMENTUM"

    late = evaluate_module(
        "chan_leveraged_rebalance_momentum",
        _rebalance(chan_rebalance_minutes_to_close=20.0),
    )
    assert late["view"] == "WAIT"


def test_chan_half_kelly_is_a_capped_risk_recommendation_not_a_directional_signal():
    result = evaluate_module("chan_half_kelly_cap", _kelly())
    assert result["view"] == "WAIT"
    assert result["directional_claim"] is False
    assert result["chan_recommended_leverage"] == pytest.approx(1.0 / 6.0)
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "chan_opening_gap_momentum",
        "chan_news_drift",
        "chan_stop_order_momentum",
        "chan_order_flow_momentum",
        "chan_bid_ask_imbalance",
        "chan_leveraged_rebalance_momentum",
        "chan_half_kelly_cap",
    ],
)
def test_chan_expansions_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["execution_authority"] is False
