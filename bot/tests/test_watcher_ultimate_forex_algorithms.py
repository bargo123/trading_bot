from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Anna Coulling — The Ultimate Forex Trading System"


def _rejection(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "ultimate_pin_type": "head",
        "ultimate_pin_location": "resistance",
        "ultimate_pin_height": 0.0020,
        "ultimate_pin_count": 1,
        "ultimate_trend": "up",
        "ultimate_data_provenance": "causal_completed_1h_4h_quote_bars",
    }
    state.update(overrides)
    return state


def _correlation(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "BUY",
        "ultimate_corr_coefficient": 0.80,
        "ultimate_corr_window_hours": 300,
        "ultimate_leading_return": 0.020,
        "ultimate_lagging_return": 0.005,
        "ultimate_min_lag_gap": 0.005,
        "ultimate_lagging_setup_confirmed": True,
        "ultimate_lagging_setup_direction": "BUY",
        "ultimate_hours_since_divergence": 1.0,
        "ultimate_data_provenance": "causal_1h_pair_returns",
    }
    state.update(overrides)
    return state


def _abandoned_baby(**overrides):
    state = {
        "symbol": "USDJPY",
        "side": "BUY",
        "ultimate_candle_type": "doji",
        "ultimate_timeframe": "daily",
        "ultimate_ema_period": 5,
        "ultimate_ema_value": 150.0,
        "ultimate_reversal_close": 148.0,
        "ultimate_previous_bar_range": 1.0,
        "ultimate_new_bar_open_alert": True,
        "ultimate_data_provenance": "causal_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _triangle(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "ultimate_triangle_shape": "weakening_m",
        "ultimate_triangle_leg_directions": ["UP", "DOWN", "UP"],
        "ultimate_triangle_leg_sizes": [0.030, 0.012, 0.003],
        "ultimate_triangle_final_leg_weak": True,
        "ultimate_triangle_completed": True,
        "ultimate_data_provenance": "causal_completed_quote_bars",
    }
    state.update(overrides)
    return state


def _cascade(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "SELL",
        "ultimate_cascade_directions": ["UP", "UP", "UP", "DOWN", "UP", "UP", "DOWN"],
        "ultimate_cascade_leg_sizes": [5.0, 4.0, 3.0, 1.0, 2.0, 1.5, 0.5],
        "ultimate_cascade_dominant_direction": "UP",
        "ultimate_cascade_phase": "matured_reversal",
        "ultimate_cascade_matured": True,
        "ultimate_cascade_at_extreme": True,
        "ultimate_data_provenance": "causal_completed_quote_bars",
    }
    state.update(overrides)
    return state


def _news(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ultimate_news_impact": "high",
        "ultimate_news_currency": "USD",
        "ultimate_news_pair_affected": True,
        "ultimate_news_level_type": "support",
        "ultimate_news_direction": "BUY",
        "ultimate_news_stop_pips": 12.0,
        "ultimate_news_target_pips": 30.0,
        "ultimate_news_rr": 2.5,
        "ultimate_news_minutes_to_release": 5.0,
        "ultimate_news_entry_timing": "pre_release_extreme",
        "ultimate_data_provenance": "causal_news_calendar_and_quote_bars",
    }
    state.update(overrides)
    return state


def test_price_rejection_uses_head_at_resistance_and_tail_at_support():
    sell = evaluate_module("ultimate_price_rejection", _rejection())
    buy = evaluate_module(
        "ultimate_price_rejection",
        _rejection(side="BUY", ultimate_pin_type="tail", ultimate_pin_location="support"),
    )
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"
    assert sell["source_books"] == [SOURCE]


def test_price_rejection_ignores_wrong_zone_and_trend_combination():
    result = evaluate_module(
        "ultimate_price_rejection",
        _rejection(ultimate_pin_type="head", ultimate_pin_location="support", ultimate_trend="up"),
    )
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_correlation_lag_trades_only_the_lagging_pair():
    result = evaluate_module("ultimate_correlation_lag", _correlation())
    assert result["view"] == "BUY"
    assert result["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"ultimate_corr_coefficient": 0.60},
        {"ultimate_lagging_setup_confirmed": False},
        {"ultimate_hours_since_divergence": 4.0},
        {"ultimate_lagging_setup_direction": "SELL"},
    ],
)
def test_correlation_lag_waits_for_the_source_conditions(overrides):
    result = evaluate_module("ultimate_correlation_lag", _correlation(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_abandoned_baby_ema5_reverts_toward_the_mean():
    buy = evaluate_module("ultimate_abandoned_baby_ema5", _abandoned_baby())
    sell = evaluate_module(
        "ultimate_abandoned_baby_ema5",
        _abandoned_baby(side="SELL", ultimate_reversal_close=152.0),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"ultimate_ema_period": 10},
        {"ultimate_timeframe": "hourly"},
        {"ultimate_new_bar_open_alert": False},
        {"ultimate_previous_bar_range": 3.0},
    ],
)
def test_abandoned_baby_ema5_waits_when_the_baseline_is_not_met(overrides):
    result = evaluate_module("ultimate_abandoned_baby_ema5", _abandoned_baby(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_triangle_weakening_m_sells_and_strengthening_w_buys():
    sell = evaluate_module("ultimate_triangle_pattern", _triangle())
    buy = evaluate_module(
        "ultimate_triangle_pattern",
        _triangle(
            side="BUY",
            ultimate_triangle_shape="strengthening_w",
            ultimate_triangle_leg_directions=["DOWN", "UP", "DOWN"],
        ),
    )
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"


def test_triangle_waits_for_a_weak_middle_and_final_leg():
    result = evaluate_module(
        "ultimate_triangle_pattern",
        _triangle(ultimate_triangle_final_leg_weak=False),
    )
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_cascade_exhaustion_reverses_a_matured_move():
    result = evaluate_module("ultimate_cascade_exhaustion", _cascade())
    assert result["view"] == "SELL"
    assert result["source_books"] == [SOURCE]


def test_cascade_can_report_early_continuation_without_calling_it_a_reversal():
    result = evaluate_module(
        "ultimate_cascade_exhaustion",
        _cascade(
            side="BUY",
            ultimate_cascade_phase="early_continuation",
            ultimate_cascade_matured=False,
            ultimate_cascade_at_extreme=False,
        ),
    )
    assert result["view"] == "BUY"
    assert any("early" in reason for reason in result["reasons"])


def test_cascade_reversal_requires_extreme_and_maturity():
    result = evaluate_module(
        "ultimate_cascade_exhaustion",
        _cascade(ultimate_cascade_at_extreme=False),
    )
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_news_strategy_requires_support_resistance_and_after_cost_reward():
    result = evaluate_module("ultimate_news_sr_reaction", _news())
    assert result["view"] == "BUY"
    assert result["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"ultimate_news_pair_affected": False},
        {"ultimate_news_rr": 1.9},
        {"ultimate_news_stop_pips": 40.0},
        {"ultimate_news_entry_timing": "after_release"},
    ],
)
def test_news_strategy_waits_when_execution_conditions_are_not_met(overrides):
    result = evaluate_module("ultimate_news_sr_reaction", _news(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "ultimate_price_rejection",
        "ultimate_correlation_lag",
        "ultimate_abandoned_baby_ema5",
        "ultimate_triangle_pattern",
        "ultimate_cascade_exhaustion",
        "ultimate_news_sr_reaction",
    ],
)
def test_ultimate_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False
