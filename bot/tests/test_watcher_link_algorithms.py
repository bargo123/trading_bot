from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "link_data_provenance": "causal_completed_quote_bars",
    }
    state.update(overrides)
    return state


def test_link_ten_period_breakout_requires_trend_aligned_close_and_three_bar_exit_rule():
    buy = evaluate_module(
        "link_ten_period_breakout",
        _state(
            link_major_trend_direction="BUY",
            link_breakout_close_distance_pips=1,
            link_breakout_confirmed=True,
            link_exit_rule="three_bar_low",
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_ten_period_breakout",
        _state(
            side="SELL",
            link_major_trend_direction="SELL",
            link_breakout_close_distance_pips=-1,
            link_breakout_confirmed=True,
            link_exit_rule="three_bar_high",
        ),
    )
    assert sell["view"] == "SELL"


def test_link_trendline_buffer_breakout_requires_directional_buffer():
    buy = evaluate_module(
        "link_trendline_buffer_breakout",
        _state(
            link_trendline_direction="down",
            link_break_distance_ticks=10,
            link_breakout_confirmed=True,
            link_exit_rule="two_consecutive_closes_back_below",
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_trendline_buffer_breakout",
        _state(
            side="SELL",
            link_trendline_direction="up",
            link_break_distance_ticks=-12,
            link_breakout_confirmed=True,
            link_exit_rule="two_consecutive_closes_back_above",
        ),
    )
    assert sell["view"] == "SELL"


def test_link_opening_range_breakout_waits_until_thirty_minutes_and_trend_alignment():
    buy = evaluate_module(
        "link_opening_range_breakout_30m",
        _state(
            link_minutes_since_open=31,
            link_opening_range_established=True,
            link_opening_range_break_distance_ticks=2,
            link_major_trend_direction="BUY",
            link_breakout_close_confirmed=True,
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_opening_range_breakout_30m",
        _state(
            side="SELL",
            link_minutes_since_open=60,
            link_opening_range_established=True,
            link_opening_range_break_distance_ticks=-2,
            link_major_trend_direction="SELL",
            link_breakout_close_confirmed=True,
        ),
    )
    assert sell["view"] == "SELL"
    early = evaluate_module(
        "link_opening_range_breakout_30m",
        _state(
            link_minutes_since_open=29,
            link_opening_range_established=True,
            link_opening_range_break_distance_ticks=2,
            link_major_trend_direction="BUY",
            link_breakout_close_confirmed=True,
        ),
    )
    assert early["view"] == "WAIT"


def test_link_reversal_day_requires_lower_low_close_reversal_and_volume():
    buy = evaluate_module(
        "link_reversal_day",
        _state(
            link_prior_trend="down",
            link_reversal_type="key",
            link_low_vs_prior_low=-1,
            link_close_vs_prior_close=1,
            link_high_vs_prior_high=1,
            link_stochastic_state="oversold",
            link_volume_confirmed=True,
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_reversal_day",
        _state(
            side="SELL",
            link_prior_trend="up",
            link_reversal_type="key",
            link_low_vs_prior_low=-1,
            link_close_vs_prior_close=-1,
            link_high_vs_prior_high=1,
            link_stochastic_state="overbought",
            link_volume_confirmed=True,
        ),
    )
    assert sell["view"] == "SELL"


def test_link_double_top_bottom_reversal_requires_failed_extreme_and_trendline_break():
    buy = evaluate_module(
        "link_double_top_bottom_reversal",
        _state(
            link_reversal_pattern="double_bottom",
            link_previous_extreme_failed=True,
            link_trendline_break_confirmed=True,
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_double_top_bottom_reversal",
        _state(
            side="SELL",
            link_reversal_pattern="double_top",
            link_previous_extreme_failed=True,
            link_trendline_break_confirmed=True,
        ),
    )
    assert sell["view"] == "SELL"


def test_link_pain_reversal_requires_fast_exhaustion_and_failed_follow_through():
    buy = evaluate_module(
        "link_pain_reversal",
        _state(
            link_prior_trend="down",
            link_exhaustion_move_direction="down",
            link_exhaustion_magnitude=3,
            link_move_speed="fast",
            link_volume_relative="above_average",
            link_follow_through_failed=True,
            link_stochastic_extreme="oversold",
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_pain_reversal",
        _state(
            side="SELL",
            link_prior_trend="up",
            link_exhaustion_move_direction="up",
            link_exhaustion_magnitude=3,
            link_move_speed="fast",
            link_volume_relative="above_average",
            link_follow_through_failed=True,
            link_stochastic_extreme="overbought",
        ),
    )
    assert sell["view"] == "SELL"


def test_link_key_number_reversal_requires_rejection_near_psychological_level():
    buy = evaluate_module(
        "link_key_number_reversal",
        _state(
            link_approach_direction="down",
            link_key_number_distance_ticks=2,
            link_key_number_rejection=True,
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_key_number_reversal",
        _state(
            side="SELL",
            link_approach_direction="up",
            link_key_number_distance_ticks=1,
            link_key_number_rejection=True,
        ),
    )
    assert sell["view"] == "SELL"


def test_link_multi_timeframe_confirmation_requires_alignment_from_weekly_to_entry_chart():
    buy = evaluate_module(
        "link_multi_timeframe_confirmation",
        _state(
            link_weekly_trend_direction="BUY",
            link_daily_trend_direction="BUY",
            link_intermediate_trend_direction="BUY",
            link_entry_timeframe_direction="BUY",
            link_entry_stability=True,
        ),
    )
    assert buy["view"] == "BUY"
    sell = evaluate_module(
        "link_multi_timeframe_confirmation",
        _state(
            side="SELL",
            link_weekly_trend_direction="SELL",
            link_daily_trend_direction="SELL",
            link_intermediate_trend_direction="SELL",
            link_entry_timeframe_direction="SELL",
            link_entry_stability=True,
        ),
    )
    assert sell["view"] == "SELL"


def test_link_news_reaction_fade_waits_for_digest_and_failed_expected_move():
    result = evaluate_module(
        "link_news_reaction_fade",
        _state(
            link_expected_news_direction="BUY",
            link_pre_news_direction="BUY",
            link_news_result_in_line=True,
            link_post_news_follow_through=False,
            link_post_news_reversal_confirmed=True,
            link_post_news_break_confirmed=True,
            link_post_news_digest_minutes=30,
        ),
    )
    assert result["view"] == "SELL"
    result = evaluate_module(
        "link_news_reaction_fade",
        _state(
            side="SELL",
            link_expected_news_direction="SELL",
            link_pre_news_direction="SELL",
            link_news_result_in_line=True,
            link_post_news_follow_through=False,
            link_post_news_reversal_confirmed=True,
            link_post_news_break_confirmed=True,
            link_post_news_digest_minutes=31,
        ),
    )
    assert result["view"] == "BUY"


@pytest.mark.parametrize("algorithm_id", ["link_multi_timeframe_confirmation", "link_news_reaction_fade"])
def test_link_additional_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "link_ten_period_breakout",
        "link_trendline_buffer_breakout",
        "link_opening_range_breakout_30m",
        "link_reversal_day",
        "link_double_top_bottom_reversal",
        "link_pain_reversal",
        "link_key_number_reversal",
    ],
)
def test_link_algorithms_fail_closed_without_book_data_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["execution_authority"] is False
