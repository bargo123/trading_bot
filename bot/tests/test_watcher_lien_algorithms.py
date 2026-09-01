from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _range_trade(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "lien_environment": "range",
        "lien_hourly_entry_context": "range_edge",
        "lien_daily_range_confirmed": True,
        "lien_oscillator": "RSI",
        "lien_oscillator_state": "oversold_reversal",
        "lien_key_level_behavior": "support_hold",
        "lien_data_provenance": "causal_multi_timeframe_quote_bars",
    }
    state.update(overrides)
    return state


def _breakout(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "BUY",
        "lien_environment": "breakout",
        "lien_short_volatility": 0.004,
        "lien_long_volatility": 0.012,
        "lien_pivot_confirmation": True,
        "lien_moving_average_alignment": "BUY",
        "lien_breakout_direction": "BUY",
        "lien_data_provenance": "causal_multi_timeframe_quote_bars",
    }
    state.update(overrides)
    return state


def test_lien_intraday_range_reversal_requires_range_oscillator_and_level_agreement():
    buy = evaluate_module("lien_intraday_range_reversal", _range_trade())
    sell = evaluate_module(
        "lien_intraday_range_reversal",
        _range_trade(
            side="SELL",
            lien_oscillator_state="overbought_reversal",
            lien_key_level_behavior="resistance_failure",
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == ["Kathy Lien — Day Trading and Swing Trading the Currency Market"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"lien_environment": "trend"},
        {"lien_daily_range_confirmed": False},
        {"lien_oscillator_state": "neutral"},
        {"lien_key_level_behavior": "unclear"},
    ],
)
def test_lien_range_reversal_waits_when_a_required_condition_is_missing(overrides):
    result = evaluate_module("lien_intraday_range_reversal", _range_trade(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_lien_breakout_requires_contracted_short_volatility_and_confirmations():
    result = evaluate_module("lien_medium_term_breakout", _breakout())
    assert result["view"] == "BUY"
    assert result["lien_volatility_contraction"] is True

    sell = evaluate_module(
        "lien_medium_term_breakout",
        _breakout(
            side="SELL",
            lien_moving_average_alignment="SELL",
            lien_breakout_direction="SELL",
        ),
    )
    assert sell["view"] == "SELL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"lien_short_volatility": 0.02},
        {"lien_pivot_confirmation": False},
        {"lien_moving_average_alignment": "SELL"},
        {"lien_breakout_direction": "SELL"},
        {"lien_environment": "range"},
    ],
)
def test_lien_breakout_waits_without_contraction_pivot_and_directional_alignment(overrides):
    result = evaluate_module("lien_medium_term_breakout", _breakout(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize("algorithm_id", ["lien_intraday_range_reversal", "lien_medium_term_breakout"])
def test_lien_algorithms_fail_closed_without_observed_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False


def _lien(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "lien_data_provenance": "causal_multi_timeframe_quote_bars",
    }
    state.update(overrides)
    return state


def test_lien_double_zero_fade_requires_quiet_confluence_and_bounded_geometry():
    buy = evaluate_module(
        "lien_double_zero_fade",
        _lien(
            lien_market_condition="quiet",
            lien_round_number_distance_pips=-5,
            lien_price_vs_intraday_sma20=-0.002,
            lien_round_number_confluence=True,
            lien_stop_pips=20,
            lien_target_risk_multiple=2,
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "lien_double_zero_fade",
        _lien(
            side="SELL",
            lien_market_condition="quiet",
            lien_round_number_distance_pips=7,
            lien_price_vs_intraday_sma20=0.002,
            lien_round_number_confluence=True,
            lien_stop_pips=18,
            lien_target_risk_multiple=2,
        ),
    )
    assert sell["view"] == "SELL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"lien_market_condition": "volatile"},
        {"lien_round_number_distance_pips": -12},
        {"lien_price_vs_intraday_sma20": 0.002},
        {"lien_round_number_confluence": False},
        {"lien_stop_pips": 21},
    ],
)
def test_lien_double_zero_fade_waits_when_a_source_condition_fails(overrides):
    state = {
        "lien_market_condition": "quiet",
        "lien_round_number_distance_pips": -5,
        "lien_price_vs_intraday_sma20": -0.002,
        "lien_round_number_confluence": True,
        "lien_stop_pips": 20,
        "lien_target_risk_multiple": 2,
    }
    state.update(overrides)
    result = evaluate_module(
        "lien_double_zero_fade",
        _lien(**state),
    )
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_lien_wait_for_real_deal_requires_gbp_usd_stop_hunt_and_reclaim():
    result = evaluate_module(
        "lien_wait_for_real_deal",
        _lien(
            symbol="GBPUSD",
            side="BUY",
            lien_session="london_open",
            lien_open_range_width_pips=25,
            lien_early_excursion="below_range",
            lien_opposite_range_penetrated=True,
            lien_noise_settled=True,
            lien_entry_offset_pips=10,
            lien_stop_pips=20,
        ),
    )
    assert result["view"] == "BUY"
    sell = evaluate_module(
        "lien_wait_for_real_deal",
        _lien(
            symbol="GBPUSD",
            side="SELL",
            lien_session="london_open",
            lien_open_range_width_pips=25,
            lien_early_excursion="above_range",
            lien_opposite_range_penetrated=True,
            lien_noise_settled=True,
            lien_entry_offset_pips=10,
            lien_stop_pips=20,
        ),
    )
    assert sell["view"] == "SELL"


def test_lien_wait_for_real_deal_rejects_other_pairs_or_unsettled_noise():
    result = evaluate_module(
        "lien_wait_for_real_deal",
        _lien(
            symbol="EURUSD",
            lien_session="london_open",
            lien_open_range_width_pips=30,
            lien_early_excursion="below_range",
            lien_opposite_range_penetrated=True,
            lien_noise_settled=True,
            lien_entry_offset_pips=10,
            lien_stop_pips=20,
        ),
    )
    assert result["view"] == "WAIT"


def test_lien_fader_requires_adx_weakness_and_two_sided_false_break():
    result = evaluate_module(
        "lien_fader",
        _lien(
            side="BUY",
            lien_adx=30,
            lien_adx_trend="falling",
            lien_previous_day_low_break_pips=15,
            lien_previous_day_high_reclaim_pips=15,
            lien_stop_pips=30,
            lien_target_risk_multiple=2,
        ),
    )
    assert result["view"] == "BUY"
    result = evaluate_module(
        "lien_fader",
        _lien(
            side="SELL",
            lien_adx=30,
            lien_adx_trend="falling",
            lien_previous_day_high_break_pips=15,
            lien_previous_day_low_reclaim_pips=15,
            lien_stop_pips=30,
            lien_target_risk_multiple=2,
        ),
    )
    assert result["view"] == "SELL"


def test_lien_filter_false_breakout_requires_20_day_extreme_reversal_and_rebreak():
    buy = evaluate_module(
        "lien_filter_false_breakout",
        _lien(
            lien_original_extreme="20_day_high",
            lien_reversal_extreme="2_day_low",
            lien_reversal_days=3,
            lien_rebreak_days=3,
            lien_original_extreme_rebroken=True,
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "lien_filter_false_breakout",
        _lien(
            side="SELL",
            lien_original_extreme="20_day_low",
            lien_reversal_extreme="2_day_high",
            lien_reversal_days=2,
            lien_rebreak_days=2,
            lien_original_extreme_rebroken=True,
        ),
    )
    assert sell["view"] == "SELL"


def test_lien_channel_breakout_requires_narrow_channel_break_and_double_range_plan():
    result = evaluate_module(
        "lien_channel_breakout",
        _lien(
            lien_channel_narrow=True,
            lien_channel_width_pips=30,
            lien_channel_break_direction="BUY",
            lien_channel_break_confirmed=True,
            lien_stop_distance_pips=10,
            lien_target_range_multiple=2,
        ),
    )
    assert result["view"] == "BUY"
    result = evaluate_module(
        "lien_channel_breakout",
        _lien(
            side="SELL",
            lien_channel_narrow=True,
            lien_channel_width_pips=15,
            lien_channel_break_direction="SELL",
            lien_channel_break_confirmed=True,
            lien_stop_distance_pips=10,
            lien_target_range_multiple=2,
        ),
    )
    assert result["view"] == "SELL"


def test_lien_perfect_order_requires_five_ma_stack_and_rising_adx():
    result = evaluate_module(
        "lien_perfect_order",
        _lien(
            lien_ma_10=1.105,
            lien_ma_20=1.104,
            lien_ma_50=1.102,
            lien_ma_100=1.100,
            lien_ma_200=1.095,
            lien_adx=25,
            lien_adx_rising=True,
            lien_formation_age_candles=5,
        ),
    )
    assert result["view"] == "BUY"
    result = evaluate_module(
        "lien_perfect_order",
        _lien(
            side="SELL",
            lien_ma_10=1.095,
            lien_ma_20=1.100,
            lien_ma_50=1.102,
            lien_ma_100=1.104,
            lien_ma_200=1.105,
            lien_adx=21,
            lien_adx_rising=True,
            lien_formation_age_candles=5,
        ),
    )
    assert result["view"] == "SELL"


def test_lien_20_100_momentum_requires_fresh_macd_turn_and_15_pip_cross():
    result = evaluate_module(
        "lien_short_term_momentum_20_100",
        _lien(
            lien_20_ema=1.1000,
            lien_100_sma=1.0990,
            lien_price_cross_distance_pips=15,
            lien_macd_direction="positive",
            lien_macd_turn_age_candles=5,
            lien_pre_cross_position="below_both",
            lien_break_candle_low_or_high_valid=True,
        ),
    )
    assert result["view"] == "BUY"
    result = evaluate_module(
        "lien_short_term_momentum_20_100",
        _lien(
            side="SELL",
            lien_20_ema=1.1000,
            lien_100_sma=1.1010,
            lien_price_cross_distance_pips=-15,
            lien_macd_direction="negative",
            lien_macd_turn_age_candles=4,
            lien_pre_cross_position="above_both",
            lien_break_candle_low_or_high_valid=True,
        ),
    )
    assert result["view"] == "SELL"


def test_lien_news_rules_require_event_timing_and_causal_surprise_evidence():
    proactive = evaluate_module(
        "lien_proactive_news",
        _lien(
            lien_news_phase="pre_release",
            lien_minutes_to_release=20,
            lien_major_release=True,
            lien_event_provenance="causal_economic_calendar",
            lien_range_lookback_hours=2,
            lien_stop_reference_valid=True,
            lien_surprise_bias="BUY",
        ),
    )
    assert proactive["view"] == "BUY"
    reactive = evaluate_module(
        "lien_reactive_news",
        _lien(
            lien_news_phase="post_release",
            lien_minutes_since_release=5,
            lien_major_release=True,
            lien_event_provenance="causal_economic_calendar",
            lien_news_surprise_fraction=1.1,
            lien_news_candle_reference_valid=True,
            lien_surprise_direction="BUY",
        ),
    )
    assert reactive["view"] == "BUY"


def test_lien_news_rules_wait_without_verified_event_or_timing():
    proactive = evaluate_module(
        "lien_proactive_news",
        _lien(
            lien_news_phase="pre_release",
            lien_minutes_to_release=20,
            lien_major_release=False,
            lien_range_lookback_hours=2,
            lien_stop_reference_valid=True,
            lien_surprise_bias="BUY",
            lien_event_provenance="causal_economic_calendar",
        ),
    )
    reactive = evaluate_module(
        "lien_reactive_news",
        _lien(
            lien_news_phase="post_release",
            lien_minutes_since_release=5,
            lien_major_release=True,
            lien_news_surprise_fraction=0.5,
            lien_news_candle_reference_valid=True,
            lien_surprise_direction="BUY",
            lien_event_provenance="causal_economic_calendar",
        ),
    )
    for result in (proactive, reactive):
        assert result["view"] == "WAIT"
        assert result["reasons"]


def test_lien_combined_news_requires_pre_release_half_and_confirming_post_release_half():
    result = evaluate_module(
        "lien_combined_news",
        _lien(
            lien_news_phase="pre_and_post",
            lien_minutes_to_release=20,
            lien_minutes_since_release=5,
            lien_major_release=True,
            lien_event_provenance="causal_economic_calendar",
            lien_initial_half_bias="BUY",
            lien_post_release_surprise_agrees=True,
            lien_second_entry_allowed=True,
            lien_second_entry_timing_valid=True,
            lien_stop_pips=45,
            lien_first_target_pips=45,
        ),
    )
    assert result["view"] == "BUY"


def test_lien_new_modules_fail_closed_without_provenance():
    for algorithm_id in (
        "lien_double_zero_fade",
        "lien_wait_for_real_deal",
        "lien_fader",
        "lien_filter_false_breakout",
        "lien_channel_breakout",
        "lien_perfect_order",
        "lien_short_term_momentum_20_100",
        "lien_proactive_news",
        "lien_reactive_news",
        "lien_combined_news",
    ):
        result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
        assert result["view"] == "MISSING_DATA"
        assert result["execution_authority"] is False
