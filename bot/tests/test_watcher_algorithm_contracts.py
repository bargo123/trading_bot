from __future__ import annotations

from importlib import import_module

import pytest

from aegis.research.watcher_algorithms import ALGORITHM_MODULES, evaluate_module


def test_every_registered_module_declares_its_source_and_input_contract():
    for algorithm_id in ALGORITHM_MODULES:
        module = import_module(f"aegis.research.watcher_algorithms.{algorithm_id}")
        assert module.ALGORITHM_ID == algorithm_id
        assert isinstance(module.SOURCES, tuple) and module.SOURCES
        assert isinstance(module.KEYS, tuple) and module.KEYS


@pytest.mark.parametrize(
    "state",
    [None, {}, {"side": ["BUY"], "context": "not-a-mapping", "short_returns": object()}],
    ids=("none", "empty", "malformed"),
)
def test_every_registered_module_fails_closed_on_missing_or_malformed_state(state):
    for algorithm_id in ALGORITHM_MODULES:
        result = evaluate_module(algorithm_id, state)
        assert result["algorithm_id"] == algorithm_id
        assert result["view"] in {"MISSING_DATA", "NOT_APPLICABLE", "WAIT"}
        assert result["view"] not in {"BUY", "SELL"}
        assert result["execution_authority"] is False
        assert result["uses_future_data"] is False
        assert result["research_only"] is True


def test_murphy_volume_open_interest_continuation_requires_real_inputs():
    result = evaluate_module(
        "volume_open_interest",
        {
            "side": "BUY",
            "volume_oi_price_trend": "rising",
            "volume_oi_volume_trend": "up",
            "volume_oi_open_interest_trend": "up",
            "volume_oi_volume_provenance": "real_traded_volume",
            "volume_oi_open_interest_provenance": "real_open_interest",
        },
    )
    assert result["view"] == "BUY"
    assert result["volume_open_interest_assessment"] == "STRONG_CONTINUATION"
    assert result["execution_authority"] is False

    bearish = evaluate_module(
        "volume_open_interest",
        {
            "side": "SELL",
            "volume_oi_price_trend": "declining",
            "volume_oi_volume_trend": "up",
            "volume_oi_open_interest_trend": "up",
            "volume_oi_volume_provenance": "real_traded_volume",
            "volume_oi_open_interest_provenance": "real_open_interest",
        },
    )
    assert bearish["view"] == "SELL"
    assert bearish["volume_open_interest_assessment"] == "STRONG_CONTINUATION"

    warning = evaluate_module(
        "volume_open_interest",
        {
            "side": "BUY",
            "volume_oi_price_trend": "rising",
            "volume_oi_volume_trend": "down",
            "volume_oi_open_interest_trend": "down",
            "volume_oi_volume_provenance": "real_traded_volume",
            "volume_oi_open_interest_provenance": "real_open_interest",
        },
    )
    assert warning["view"] == "WAIT"
    assert warning["volume_open_interest_assessment"] == "TREND_END_WARNING"

    unavailable = evaluate_module(
        "volume_open_interest",
        {
            "side": "BUY",
            "volume_oi_price_trend": "rising",
            "volume_oi_volume_trend": "up",
            "volume_oi_open_interest_trend": "up",
            "volume_oi_volume_provenance": "tick_volume_proxy",
            "volume_oi_open_interest_provenance": "unavailable",
        },
    )
    assert unavailable["view"] == "MISSING_DATA"


def test_murphy_percentage_retracement_uses_the_33_to_50_percent_reference_zone():
    bullish = evaluate_module(
        "murphy_percentage_retracement",
        {
            "side": "BUY",
            "murphy_retracement_trend": "up",
            "murphy_retracement_percent": 42.0,
            "murphy_retracement_reaction_direction": "up",
            "murphy_retracement_reaction_confirmed": True,
            "murphy_retracement_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert bullish["view"] == "BUY"
    assert bullish["retracement_assessment"] == "PREFERRED_CONTINUATION_ZONE"

    bearish = evaluate_module(
        "murphy_percentage_retracement",
        {
            "side": "SELL",
            "murphy_retracement_trend": "down",
            "murphy_retracement_percent": 42.0,
            "murphy_retracement_reaction_direction": "down",
            "murphy_retracement_reaction_confirmed": "confirmed",
            "murphy_retracement_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert bearish["view"] == "SELL"

    deep = evaluate_module(
        "murphy_percentage_retracement",
        {
            "side": "BUY",
            "murphy_retracement_trend": "up",
            "murphy_retracement_percent": 62.0,
            "murphy_retracement_reaction_direction": "up",
            "murphy_retracement_reaction_confirmed": True,
            "murphy_retracement_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert deep["view"] == "WAIT"
    assert deep["retracement_assessment"] == "DEEP_BUT_WITHIN_NORMAL_RANGE"


def test_murphy_speed_resistance_lines_require_observed_line_reaction():
    result = evaluate_module(
        "murphy_speed_resistance_lines",
        {
            "side": "BUY",
            "murphy_speedline_trend": "up",
            "murphy_speedline_one_third_price": 1.1010,
            "murphy_speedline_two_thirds_price": 1.1020,
            "murphy_speedline_current_price": 1.1022,
            "murphy_speedline_location": "above_two_thirds",
            "murphy_speedline_reaction": "support_hold",
            "murphy_speedline_reaction_direction": "up",
            "murphy_speedline_reaction_confirmed": True,
            "murphy_speedline_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert result["view"] == "BUY"
    assert result["speedline_assessment"] == "SPEEDLINE_SUPPORT_HOLD"

    broken = evaluate_module(
        "murphy_speed_resistance_lines",
        {
            "side": "BUY",
            "murphy_speedline_trend": "up",
            "murphy_speedline_one_third_price": 1.1010,
            "murphy_speedline_two_thirds_price": 1.1020,
            "murphy_speedline_current_price": 1.1005,
            "murphy_speedline_location": "broken_below_one_third",
            "murphy_speedline_reaction": "broken",
            "murphy_speedline_reaction_direction": "down",
            "murphy_speedline_reaction_confirmed": True,
            "murphy_speedline_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert broken["view"] == "WAIT"
    assert broken["speedline_assessment"] == "BROKEN_LINE_WAIT"


def test_pf_vertical_count_uses_three_box_geometry_and_activation():
    active = evaluate_module(
        "pf_vertical_count_target",
        {
            "side": "BUY",
            "pf_box_reversal": "3 box",
            "pf_box_size": 0.0001,
            "pf_count_direction": "up",
            "pf_count_column_type": "X",
            "pf_count_column_boxes": 10,
            "pf_count_anchor_price": 1.1000,
            "pf_count_anchor_role": "preceding_opposite_column_low",
            "pf_count_source": "breakout_column",
            "pf_count_column_fixed": True,
            "pf_count_activated": True,
            "pf_count_negated": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert active["view"] == "BUY"
    assert active["pf_vertical_count_target"] == pytest.approx(1.1030)
    assert active["pf_vertical_count_status"] == "ACTIVE"
    assert active["execution_authority"] is False

    not_activated = evaluate_module(
        "pf_vertical_count_target",
        {
            "side": "BUY",
            "pf_box_reversal": "3 box",
            "pf_box_size": 0.0001,
            "pf_count_direction": "up",
            "pf_count_column_type": "X",
            "pf_count_column_boxes": 10,
            "pf_count_anchor_price": 1.1000,
            "pf_count_anchor_role": "preceding_opposite_column_low",
            "pf_count_source": "breakout_column",
            "pf_count_column_fixed": True,
            "pf_count_activated": False,
            "pf_count_negated": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert not_activated["view"] == "WAIT"
    assert not_activated["pf_vertical_count_target"] == pytest.approx(1.1030)
    assert not_activated["pf_vertical_count_status"] == "ESTABLISHED_NOT_ACTIVATED"

    bearish = evaluate_module(
        "pf_vertical_count_target",
        {
            "side": "SELL",
            "pf_box_reversal": "3 box",
            "pf_box_size": 0.001,
            "pf_count_direction": "down",
            "pf_count_column_type": "O",
            "pf_count_column_boxes": 8,
            "pf_count_anchor_price": 1.2000,
            "pf_count_anchor_role": "preceding_opposite_column_high",
            "pf_count_source": "mini_top",
            "pf_count_column_fixed": True,
            "pf_count_activated": True,
            "pf_count_negated": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert bearish["view"] == "SELL"
    assert bearish["pf_vertical_count_target"] == pytest.approx(1.176)


def test_pf_horizontal_count_uses_reversal_specific_width_formula():
    three_box = evaluate_module(
        "pf_horizontal_count_target",
        {
            "side": "BUY",
            "pf_box_reversal": "3 box",
            "pf_box_size": 0.0001,
            "pf_count_method": "horizontal",
            "pf_count_direction": "up",
            "pf_count_columns": 12,
            "pf_count_anchor_price": 1.1000,
            "pf_count_anchor_role": "most_filled_row",
            "pf_count_pattern": "congestion_bottom",
            "pf_count_width_fixed": True,
            "pf_count_activated": True,
            "pf_count_negated": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert three_box["view"] == "BUY"
    assert three_box["pf_horizontal_count_target"] == pytest.approx(1.1036)
    assert three_box["pf_horizontal_count_multiplier"] == 3
    assert three_box["pf_horizontal_count_status"] == "ACTIVE"

    one_box = evaluate_module(
        "pf_horizontal_count_target",
        {
            "side": "SELL",
            "pf_box_reversal": "1 box",
            "pf_box_size": 0.0001,
            "pf_count_method": "horizontal",
            "pf_count_direction": "down",
            "pf_count_columns": 8,
            "pf_count_anchor_price": 1.1000,
            "pf_count_anchor_role": "pattern_anchor_row",
            "pf_count_pattern": "congestion_top",
            "pf_count_width_fixed": True,
            "pf_count_activated": True,
            "pf_count_negated": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert one_box["view"] == "SELL"
    assert one_box["pf_horizontal_count_target"] == pytest.approx(1.0992)
    assert one_box["pf_horizontal_count_multiplier"] == 1

    not_activated = evaluate_module(
        "pf_horizontal_count_target",
        {
            "side": "BUY",
            "pf_box_reversal": "3 box",
            "pf_box_size": 0.0001,
            "pf_count_method": "horizontal",
            "pf_count_direction": "up",
            "pf_count_columns": 12,
            "pf_count_anchor_price": 1.1000,
            "pf_count_anchor_role": "most_filled_row",
            "pf_count_pattern": "congestion_bottom",
            "pf_count_width_fixed": True,
            "pf_count_activated": False,
            "pf_count_negated": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert not_activated["view"] == "WAIT"
    assert not_activated["pf_horizontal_count_status"] == "ESTABLISHED_NOT_ACTIVATED"


def test_pf_shakeout_filter_keeps_first_countertrend_signal_as_a_warning():
    ignored = evaluate_module(
        "pf_shakeout_filter",
        {
            "side": "SELL",
            "pf_trend": "up",
            "pf_signal": "SELL",
            "pf_first_countertrend_signal": True,
            "pf_trendline_broken": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert ignored["view"] == "WAIT"
    assert ignored["pf_shakeout_assessment"] == "SHAKEOUT_IGNORE"

    confirmed = evaluate_module(
        "pf_shakeout_filter",
        {
            "side": "SELL",
            "pf_trend": "up",
            "pf_signal": "SELL",
            "pf_first_countertrend_signal": True,
            "pf_trendline_broken": True,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert confirmed["view"] == "SELL"
    assert confirmed["pf_shakeout_assessment"] == "SHAKEOUT_CONFIRMED_BREAK"

    bearish = evaluate_module(
        "pf_shakeout_filter",
        {
            "side": "BUY",
            "pf_trend": "down",
            "pf_signal": "BUY",
            "pf_first_countertrend_signal": True,
            "pf_trendline_broken": False,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert bearish["view"] == "WAIT"
    assert bearish["pf_shakeout_assessment"] == "SHAKEOUT_IGNORE"


def test_pf_trap_reversal_waits_for_the_confirmed_opposite_signal():
    bull_trap = evaluate_module(
        "pf_trap_reversal",
        {
            "side": "SELL",
            "pf_trap_type": "bull_trap",
            "pf_initial_signal": "BUY",
            "pf_reversal_signal": "SELL",
            "pf_reversal_confirmed": True,
            "pf_pattern_depth_boxes": 4,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert bull_trap["view"] == "SELL"
    assert bull_trap["pf_trap_assessment"] == "BULL_TRAP_CONFIRMED"

    pending = evaluate_module(
        "pf_trap_reversal",
        {
            "side": "BUY",
            "pf_trap_type": "bull_trap",
            "pf_initial_signal": "BUY",
            "pf_reversal_signal": "SELL",
            "pf_reversal_confirmed": False,
            "pf_pattern_depth_boxes": 4,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert pending["view"] == "WAIT"
    assert pending["pf_trap_assessment"] == "TRAP_PENDING_OPPOSITE_CONFIRMATION"

    bear_trap = evaluate_module(
        "pf_trap_reversal",
        {
            "side": "BUY",
            "pf_trap_type": "bear_trap",
            "pf_initial_signal": "SELL",
            "pf_reversal_signal": "BUY",
            "pf_reversal_confirmed": True,
            "pf_pattern_depth_boxes": 3,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert bear_trap["view"] == "BUY"
    assert bear_trap["pf_trap_assessment"] == "BEAR_TRAP_CONFIRMED"


def test_pf_one_box_semicatapult_requires_pullback_and_white_space_breakout():
    result = evaluate_module(
        "pf_one_box_semicatapult",
        {
            "side": "BUY",
            "pf_box_reversal": "1 box",
            "pf_pattern_type": "semi-catapult",
            "pf_trend": "up",
            "pf_initial_move_confirmed": True,
            "pf_pullback_confirmed": True,
            "pf_breakout_confirmed": True,
            "pf_breakout_direction": "up",
            "pf_white_space_boxes": 2,
            "pf_pattern_width_columns": 5,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert result["view"] == "BUY"
    assert result["pf_semicatapult_assessment"] == "CONFIRMED_WITH_WHITE_SPACE"

    no_pullback = evaluate_module(
        "pf_one_box_semicatapult",
        {
            "side": "BUY",
            "pf_box_reversal": "1 box",
            "pf_pattern_type": "semi-catapult",
            "pf_trend": "up",
            "pf_initial_move_confirmed": True,
            "pf_pullback_confirmed": False,
            "pf_breakout_confirmed": True,
            "pf_breakout_direction": "up",
            "pf_white_space_boxes": 2,
            "pf_pattern_width_columns": 5,
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert no_pullback["view"] == "WAIT"


def test_pf_one_box_fulcrum_requires_reversal_and_catapult_confirmation():
    result = evaluate_module(
        "pf_one_box_fulcrum",
        {
            "side": "SELL",
            "pf_box_reversal": "1 box",
            "pf_pattern_type": "fulcrum",
            "pf_fulcrum_direction": "down",
            "pf_move_into_pattern_confirmed": True,
            "pf_move_out_pattern_confirmed": True,
            "pf_catapult_breakout_confirmed": True,
            "pf_catapult_breakout_direction": "down",
            "pf_exit_structure": "falling_tops",
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert result["view"] == "SELL"
    assert result["pf_fulcrum_assessment"] == "CONFIRMED_REVERSAL"


def test_nison_hammer_and_hanging_man_use_the_preceding_trend_and_confirmation():
    hammer = evaluate_module(
        "nison_hammer_hanging_man",
        {
            "side": "BUY",
            "nison_single_line_type": "hammer",
            "nison_single_line_trend": "downtrend",
            "nison_single_line_shape": "long_lower_shadow_small_body_near_high",
            "nison_single_line_confirmation": "not_required",
            "nison_data_provenance": "observed_completed_quote_bar",
        },
    )
    assert hammer["view"] == "BUY"
    assert hammer["nison_single_line_assessment"] == "HAMMER_AFTER_DOWNTREND"

    range_shape = evaluate_module(
        "nison_hammer_hanging_man",
        {
            "side": "BUY",
            "nison_single_line_type": "hammer",
            "nison_single_line_trend": "range",
            "nison_single_line_shape": "long_lower_shadow_small_body_near_high",
            "nison_single_line_confirmation": "not_required",
            "nison_data_provenance": "observed_completed_quote_bar",
        },
    )
    assert range_shape["view"] == "WAIT"

    hanging_state = {
        "side": "SELL",
        "nison_single_line_type": "hanging_man",
        "nison_single_line_trend": "uptrend",
        "nison_single_line_shape": "long_lower_shadow_small_body_near_high",
        "nison_single_line_confirmation": "bearish_confirmed",
        "nison_data_provenance": "observed_completed_quote_bar",
    }
    hanging = evaluate_module(
        "nison_hammer_hanging_man",
        hanging_state,
    )
    assert hanging["view"] == "SELL"
    assert hanging["nison_single_line_assessment"] == "HANGING_MAN_CONFIRMED"

    unconfirmed = dict(hanging_state)
    unconfirmed["nison_single_line_confirmation"] = "unconfirmed"
    assert evaluate_module("nison_hammer_hanging_man", unconfirmed)["view"] == "WAIT"


def test_nison_shooting_star_requires_an_uptrend_and_rejection_shape():
    result = evaluate_module(
        "nison_shooting_star",
        {
            "side": "SELL",
            "nison_shooting_star_present": True,
            "nison_shooting_star_trend": "uptrend",
            "nison_shooting_star_shape": "long_upper_shadow_small_body_near_low",
            "nison_data_provenance": "observed_completed_quote_bar",
        },
    )
    assert result["view"] == "SELL"
    assert result["nison_shooting_star_assessment"] == "CONFIRMED_AFTER_UPTREND"

    wrong_trend = dict(
        {
            "side": "SELL",
            "nison_shooting_star_present": True,
            "nison_shooting_star_trend": "downtrend",
            "nison_shooting_star_shape": "long_upper_shadow_small_body_near_low",
            "nison_data_provenance": "observed_completed_quote_bar",
        }
    )
    assert evaluate_module("nison_shooting_star", wrong_trend)["view"] == "WAIT"


def test_nison_doji_is_transition_context_until_next_session_confirms():
    confirmed_state = {
        "side": "BUY",
        "nison_doji_present": True,
        "nison_doji_context": "mature_downtrend",
        "nison_doji_confirmation_direction": "up",
        "nison_doji_confirmation_bars": 1,
        "nison_data_provenance": "observed_completed_quote_bar",
    }
    confirmed = evaluate_module(
        "nison_doji_confirmation",
        confirmed_state,
    )
    assert confirmed["view"] == "BUY"
    assert confirmed["nison_doji_assessment"] == "BULLISH_CONFIRMATION"

    no_confirmation = dict(confirmed_state)
    no_confirmation["nison_doji_confirmation_direction"] = "none"
    assert evaluate_module("nison_doji_confirmation", no_confirmation)["view"] == "WAIT"

    lateral = dict(confirmed_state)
    lateral["nison_doji_context"] = "lateral_range"
    assert evaluate_module("nison_doji_confirmation", lateral)["view"] == "WAIT"


def test_nison_two_line_reversals_require_pattern_geometry_and_context():
    dark_cloud_state = {
        "side": "SELL",
        "nison_two_line_pattern": "dark_cloud_cover",
        "nison_two_line_prior_trend": "uptrend",
        "nison_two_line_first_color": "white",
        "nison_two_line_second_color": "black",
        "nison_two_line_open_relation": "above_prior_high",
        "nison_two_line_close_relation": "below_midpoint",
        "nison_two_line_body_engulfed": False,
        "nison_two_line_geometry_confirmed": True,
        "nison_two_line_followthrough": "not_required",
        "nison_data_provenance": "observed_completed_quote_bars",
    }
    dark_cloud = evaluate_module(
        "nison_two_line_reversal",
        dark_cloud_state,
    )
    assert dark_cloud["view"] == "SELL"
    assert dark_cloud["nison_two_line_assessment"] == "DARK_CLOUD_IDEAL"

    bullish_engulfing = evaluate_module(
        "nison_two_line_reversal",
        {
            "side": "BUY",
            "nison_two_line_pattern": "bullish_engulfing",
            "nison_two_line_prior_trend": "downtrend",
            "nison_two_line_first_color": "black",
            "nison_two_line_second_color": "white",
            "nison_two_line_open_relation": "below_prior_close",
            "nison_two_line_close_relation": "above_prior_body",
            "nison_two_line_body_engulfed": True,
            "nison_two_line_geometry_confirmed": True,
            "nison_two_line_followthrough": "not_required",
            "nison_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert bullish_engulfing["view"] == "BUY"

    incomplete = dict(dark_cloud_state)
    incomplete["nison_two_line_close_relation"] = "inside_body_not_midpoint"
    incomplete["nison_two_line_followthrough"] = "none"
    assert evaluate_module("nison_two_line_reversal", incomplete)["view"] == "WAIT"


def test_nison_three_line_stars_require_all_three_completed_roles():
    morning_state = {
        "side": "BUY",
        "nison_three_line_pattern": "morning_star",
        "nison_three_line_prior_trend": "downtrend",
        "nison_three_line_first_color": "long_black",
        "nison_three_line_middle_body": "small_body",
        "nison_three_line_third_color": "long_white",
        "nison_three_line_penetration": "well_into_first_body",
        "nison_three_line_bodies_separated": True,
        "nison_three_line_closed": True,
        "nison_data_provenance": "observed_completed_quote_bars",
    }
    morning = evaluate_module(
        "nison_three_line_star",
        morning_state,
    )
    assert morning["view"] == "BUY"
    assert morning["nison_three_line_assessment"] == "MORNING_STAR_CONFIRMED"

    evening = dict(morning_state)
    evening.update(
        {
            "side": "SELL",
            "nison_three_line_pattern": "evening_doji_star",
            "nison_three_line_prior_trend": "uptrend",
            "nison_three_line_first_color": "long_white",
            "nison_three_line_middle_body": "doji",
            "nison_three_line_third_color": "long_black",
        }
    )
    assert evaluate_module("nison_three_line_star", evening)["view"] == "SELL"

    incomplete = dict(morning_state)
    incomplete["nison_three_line_penetration"] = "shallow"
    assert evaluate_module("nison_three_line_star", incomplete)["view"] == "WAIT"


def test_nison_spring_and_upthrust_require_failed_break_and_reclaim():
    spring_state = {
        "side": "BUY",
        "nison_western_event": "spring",
        "nison_event_level_type": "support",
        "nison_event_breach_confirmed": True,
        "nison_event_failed_hold": True,
        "nison_event_reclaim_direction": "up",
        "nison_event_confirmation": True,
        "nison_data_provenance": "observed_completed_quote_bars",
    }
    spring = evaluate_module(
        "nison_spring_upthrust",
        spring_state,
    )
    assert spring["view"] == "BUY"
    assert spring["nison_event_assessment"] == "SPRING_RECLAIM"

    upthrust = dict(spring_state)
    upthrust.update(
        {
            "side": "SELL",
            "nison_western_event": "upthrust",
            "nison_event_level_type": "resistance",
            "nison_event_reclaim_direction": "down",
        }
    )
    assert evaluate_module("nison_spring_upthrust", upthrust)["view"] == "SELL"

    held = dict(spring_state)
    held["nison_event_failed_hold"] = False
    assert evaluate_module("nison_spring_upthrust", held)["view"] == "WAIT"


def test_nison_last_engulfing_requires_the_contextual_trend_and_reversal_close():
    bottom_state = {
        "side": "BUY",
        "nison_last_engulfing_type": "bottom",
        "nison_last_engulfing_trend": "downtrend",
        "nison_last_engulfing_body_color": "black",
        "nison_last_engulfing_envelopes": True,
        "nison_last_engulfing_confirmation": "close_above_black_candle",
        "nison_last_engulfing_confirmation_direction": "up",
        "nison_data_provenance": "observed_completed_quote_bars",
    }
    bottom = evaluate_module("nison_last_engulfing", bottom_state)
    assert bottom["view"] == "BUY"
    assert bottom["nison_last_engulfing_assessment"] == "LAST_ENGULFING_BOTTOM_CONFIRMED"

    top_state = dict(bottom_state)
    top_state.update(
        {
            "side": "SELL",
            "nison_last_engulfing_type": "top",
            "nison_last_engulfing_trend": "uptrend",
            "nison_last_engulfing_body_color": "white",
            "nison_last_engulfing_confirmation": "close_below_white_candle",
            "nison_last_engulfing_confirmation_direction": "down",
        }
    )
    assert evaluate_module("nison_last_engulfing", top_state)["view"] == "SELL"

    no_close = dict(bottom_state)
    no_close["nison_last_engulfing_confirmation_direction"] = "none"
    assert evaluate_module("nison_last_engulfing", no_close)["view"] == "WAIT"


def test_nison_window_distinguishes_unfilled_directional_confirmation_from_a_close_break():
    rising_state = {
        "side": "BUY",
        "nison_window_direction": "rising",
        "nison_window_role": "support",
        "nison_window_filled": False,
        "nison_window_age_sessions": 3,
        "nison_window_break_close": "none",
        "nison_window_confirmed": True,
        "nison_data_provenance": "observed_completed_quote_bars",
    }
    rising = evaluate_module(
        "nison_window_context",
        rising_state,
    )
    assert rising["view"] == "BUY"
    assert rising["nison_window_assessment"] == "RISING_WINDOW_CONFIRMED_SUPPORT"

    broken = dict(
        {
            "side": "SELL",
            "nison_window_direction": "rising",
            "nison_window_role": "support",
            "nison_window_filled": False,
            "nison_window_age_sessions": 1,
            "nison_window_break_close": "below_bottom",
            "nison_window_confirmed": True,
            "nison_data_provenance": "observed_completed_quote_bars",
        }
    )
    assert evaluate_module("nison_window_context", broken)["view"] == "SELL"

    premature = dict(rising_state)
    premature["nison_window_age_sessions"] = 2
    assert evaluate_module("nison_window_context", premature)["view"] == "WAIT"


def test_nison_record_sessions_require_an_eight_to_ten_count_and_reversal_confirmation():
    high = evaluate_module(
        "nison_record_sessions",
        {
            "side": "SELL",
            "nison_record_session_direction": "higher_highs",
            "nison_record_session_count": 8,
            "nison_record_session_origin_confirmed": True,
            "nison_record_session_confirmation_direction": "down",
            "nison_record_session_confirmation": True,
            "nison_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert high["view"] == "SELL"
    assert high["nison_record_session_assessment"] == "RECORD_HIGH_REVERSAL_CONFIRMED"

    low = evaluate_module(
        "nison_record_sessions",
        {
            "side": "BUY",
            "nison_record_session_direction": "lower_lows",
            "nison_record_session_count": 10,
            "nison_record_session_origin_confirmed": True,
            "nison_record_session_confirmation_direction": "up",
            "nison_record_session_confirmation": True,
            "nison_data_provenance": "observed_completed_quote_bars",
        },
    )
    assert low["view"] == "BUY"

    seven = dict(
        {
            "side": "SELL",
            "nison_record_session_direction": "higher_highs",
            "nison_record_session_count": 7,
            "nison_record_session_origin_confirmed": True,
            "nison_record_session_confirmation_direction": "down",
            "nison_record_session_confirmation": True,
            "nison_data_provenance": "observed_completed_quote_bars",
        }
    )
    assert evaluate_module("nison_record_sessions", seven)["view"] == "WAIT"


def test_aldridge_order_flow_autocorrelation_requires_high_frequency_persistent_flow():
    buy_state = {
        "side": "BUY",
        "aldridge_order_flow_imbalance": 12.0,
        "aldridge_order_flow_autocorrelation": 0.35,
        "aldridge_order_flow_frequency": "high_frequency",
        "aldridge_order_flow_observation_n": 100,
        "aldridge_order_flow_data_provenance": "classified_buyer_seller_trades",
    }
    buy = evaluate_module("aldridge_order_flow_autocorrelation", buy_state)
    assert buy["view"] == "BUY"
    assert buy["aldridge_order_flow_assessment"] == "PERSISTENT_BUY_FLOW"

    sell_state = dict(buy_state)
    sell_state.update({"side": "SELL", "aldridge_order_flow_imbalance": -8.0})
    assert evaluate_module("aldridge_order_flow_autocorrelation", sell_state)["view"] == "SELL"

    nonpersistent = dict(buy_state)
    nonpersistent["aldridge_order_flow_autocorrelation"] = -0.1
    assert evaluate_module("aldridge_order_flow_autocorrelation", nonpersistent)["view"] == "WAIT"

    low_frequency = dict(buy_state)
    low_frequency["aldridge_order_flow_frequency"] = "lower_frequency"
    assert evaluate_module("aldridge_order_flow_autocorrelation", low_frequency)["view"] == "WAIT"


def test_aldridge_trade_aggressiveness_requires_classified_market_order_share():
    buy_state = {
        "side": "BUY",
        "aldridge_aggressive_buy_fraction": 0.72,
        "aldridge_aggressive_sell_fraction": 0.31,
        "aldridge_aggressiveness_state": "high",
        "aldridge_trade_observation_n": 80,
        "aldridge_trade_aggressiveness_provenance": "classified_market_vs_limit_orders",
    }
    buy = evaluate_module("aldridge_trade_aggressiveness", buy_state)
    assert buy["view"] == "BUY"
    assert buy["aldridge_trade_aggressiveness_assessment"] == "AGGRESSIVE_BUY_FLOW"

    sell_state = dict(buy_state)
    sell_state.update(
        {
            "side": "SELL",
            "aldridge_aggressive_buy_fraction": 0.22,
            "aldridge_aggressive_sell_fraction": 0.65,
        }
    )
    assert evaluate_module("aldridge_trade_aggressiveness", sell_state)["view"] == "SELL"

    equal = dict(buy_state)
    equal["aldridge_aggressive_sell_fraction"] = 0.72
    assert evaluate_module("aldridge_trade_aggressiveness", equal)["view"] == "WAIT"

    tick_proxy = dict(buy_state)
    tick_proxy["aldridge_trade_aggressiveness_provenance"] = "tick_proxy_only"
    assert evaluate_module("aldridge_trade_aggressiveness", tick_proxy)["view"] == "MISSING_DATA"


def test_johnson_implementation_shortfall_measures_signed_price_and_cost_components_once():
    result = evaluate_module(
        "johnson_implementation_shortfall",
        {
            "side": "BUY",
            "johnson_decision_price": 1.1000,
            "johnson_expected_execution_price": 1.1002,
            "johnson_expected_spread_cost": 0.0001,
            "johnson_expected_delay_cost": 0.00005,
            "johnson_expected_market_impact": 0.00002,
            "johnson_expected_timing_risk": 0.00003,
            "johnson_expected_commission": 0.00001,
            "johnson_cost_model_status": "validated_cost_model",
            "johnson_shortfall_data_provenance": "observed_pretrade_cost_model",
        },
    )
    assert result["view"] == "WAIT"
    assert result["johnson_price_shortfall"] == pytest.approx(0.0002)
    assert result["johnson_expected_shortfall"] == pytest.approx(0.00041)
    assert result["johnson_shortfall_assessment"] == "COST_EXPOSURE"

    invalid = {
        "side": "BUY",
        "johnson_decision_price": 1.1000,
        "johnson_expected_execution_price": 1.1002,
        "johnson_expected_spread_cost": 0.0001,
        "johnson_expected_delay_cost": 0.00005,
        "johnson_expected_market_impact": 0.00002,
        "johnson_expected_timing_risk": 0.00003,
        "johnson_expected_commission": 0.00001,
        "johnson_cost_model_status": "uncalibrated",
        "johnson_shortfall_data_provenance": "observed_pretrade_cost_model",
    }
    assert evaluate_module("johnson_implementation_shortfall", invalid)["view"] == "MISSING_DATA"


def test_johnson_adaptive_shortfall_distinguishes_aim_and_pim_price_adaptation():
    favorable = evaluate_module(
        "johnson_adaptive_shortfall",
        {
            "side": "BUY",
            "johnson_benchmark_price": 1.1000,
            "johnson_current_mid": 1.0990,
            "johnson_adaptation_type": "aggressive_in_the_money",
            "johnson_adaptive_price_provenance": "observed_quote_benchmark",
        },
    )
    assert favorable["view"] == "BUY"
    assert favorable["johnson_adaptive_shortfall_assessment"] == "FAVORABLE_AIM"
    assert favorable["johnson_price_moneyness"] > 0

    adverse_pim = evaluate_module(
        "johnson_adaptive_shortfall",
        {
            "side": "BUY",
            "johnson_benchmark_price": 1.1000,
            "johnson_current_mid": 1.1010,
            "johnson_adaptation_type": "passive_in_the_money",
            "johnson_adaptive_price_provenance": "observed_quote_benchmark",
        },
    )
    assert adverse_pim["view"] == "BUY"
    assert adverse_pim["johnson_adaptive_shortfall_assessment"] == "ADVERSE_PIM_URGENCY"

    missing = dict(adverse_pim)
    assert missing["execution_authority"] is False


def test_johnson_price_inline_requires_a_price_sensitive_baseline_and_favorable_price():
    result = evaluate_module(
        "johnson_price_inline",
        {
            "side": "SELL",
            "johnson_inline_benchmark_price": 1.1000,
            "johnson_inline_current_mid": 1.1010,
            "johnson_inline_baseline": "POV",
            "johnson_inline_adaptation": "AIM",
            "johnson_inline_data_provenance": "observed_quote_benchmark",
        },
    )
    assert result["view"] == "SELL"
    assert result["johnson_price_inline_assessment"] == "FAVORABLE_AIM"

    unsupported_baseline = {
        "side": "SELL",
        "johnson_inline_benchmark_price": 1.1000,
        "johnson_inline_current_mid": 1.1010,
        "johnson_inline_baseline": "manual",
        "johnson_inline_adaptation": "AIM",
        "johnson_inline_data_provenance": "observed_quote_benchmark",
    }
    assert evaluate_module("johnson_price_inline", unsupported_baseline)["view"] == "MISSING_DATA"


def test_johnson_liquidity_seeking_requires_observed_depth_and_execution_probability():
    result = evaluate_module(
        "johnson_liquidity_seeking",
        {
            "side": "BUY",
            "johnson_favorable_depth": 100.0,
            "johnson_total_depth": 150.0,
            "johnson_execution_probability": 0.8,
            "johnson_favorable_price": True,
            "johnson_depth_data_provenance": "observed_live_order_book",
        },
    )
    assert result["view"] == "BUY"
    assert result["johnson_liquidity_seeking_assessment"] == "FAVORABLE_DEPTH"
    assert result["johnson_favorable_depth_ratio"] == pytest.approx(2 / 3)

    proxy = {
        "side": "BUY",
        "johnson_favorable_depth": 100.0,
        "johnson_total_depth": 150.0,
        "johnson_execution_probability": 0.8,
        "johnson_favorable_price": True,
        "johnson_depth_data_provenance": "tick_volume_proxy",
    }
    assert evaluate_module("johnson_liquidity_seeking", proxy)["view"] == "MISSING_DATA"


def test_johnson_order_difficulty_combines_size_liquidity_volatility_momentum_and_urgency():
    easy = evaluate_module(
        "johnson_order_difficulty",
        {
            "side": "BUY",
            "johnson_order_size_to_adv": 0.005,
            "johnson_liquidity_state": "high_liquidity",
            "johnson_volatility_state": "low",
            "johnson_price_momentum_direction": "up",
            "johnson_urgency": "low",
            "johnson_horizon_s": 60,
            "johnson_difficulty_data_provenance": "observed_tca_inputs",
        },
    )
    assert easy["view"] == "WAIT"
    assert easy["johnson_order_difficulty"] == "LOW"

    hard = evaluate_module(
        "johnson_order_difficulty",
        {
            "side": "BUY",
            "johnson_order_size_to_adv": 0.30,
            "johnson_liquidity_state": "thin",
            "johnson_volatility_state": "high",
            "johnson_price_momentum_direction": "down",
            "johnson_urgency": "high",
            "johnson_horizon_s": 5,
            "johnson_difficulty_data_provenance": "observed_tca_inputs",
        },
    )
    assert hard["johnson_order_difficulty"] == "HIGH"


def test_nison_harami_requires_trend_context_body_containment_and_location():
    result = evaluate_module(
        "nison_harami",
        {
            "side": "BUY",
            "nison_harami_trend": "downtrend",
            "nison_harami_first_color": "long white",
            "nison_harami_second_body": "small body",
            "nison_harami_second_location": "middle",
            "nison_harami_second_range_inside": True,
            "nison_harami_follow_through": "none",
            "nison_data_provenance": "observed_completed_candles",
        },
    )
    assert result["view"] == "BUY"
    assert result["nison_harami_assessment"] == "BULLISH_HARAMI_REVERSAL"

    low_price = {
        "side": "BUY",
        "nison_harami_trend": "downtrend",
        "nison_harami_first_color": "long white",
        "nison_harami_second_body": "small body",
        "nison_harami_second_location": "low",
        "nison_harami_second_range_inside": True,
        "nison_harami_follow_through": "none",
        "nison_data_provenance": "observed_completed_candles",
    }
    assert evaluate_module("nison_harami", low_price)["view"] == "WAIT"

    uncontained = dict(result)
    assert uncontained["execution_authority"] is False


def test_nison_harami_cross_is_the_doji_variant_and_requires_middle_location():
    result = evaluate_module(
        "nison_harami_cross",
        {
            "side": "SELL",
            "nison_harami_cross_trend": "uptrend",
            "nison_harami_cross_first_color": "long black",
            "nison_harami_cross_second_location": "middle",
            "nison_harami_cross_second_range_inside": True,
            "nison_harami_cross_follow_through": "none",
            "nison_data_provenance": "observed_completed_candles",
        },
    )
    assert result["view"] == "SELL"
    assert result["nison_harami_cross_assessment"] == "BEARISH_HARAMI_CROSS_REVERSAL"

    edge = dict(
        side="SELL",
        nison_harami_cross_trend="uptrend",
        nison_harami_cross_first_color="long black",
        nison_harami_cross_second_location="upper",
        nison_harami_cross_second_range_inside=True,
        nison_harami_cross_follow_through="none",
        nison_data_provenance="observed_completed_candles",
    )
    assert evaluate_module("nison_harami_cross", edge)["view"] == "WAIT"


def test_nison_two_black_gapping_requires_a_falling_window_and_two_black_bodies():
    result = evaluate_module(
        "nison_two_black_gapping",
        {
            "side": "SELL",
            "nison_gapping_window_direction": "falling",
            "nison_gapping_window_confirmed": True,
            "nison_gapping_window_filled": False,
            "nison_gapping_first_body_color": "black",
            "nison_gapping_second_body_color": "black",
            "nison_data_provenance": "observed_completed_candles",
        },
    )
    assert result["view"] == "SELL"
    assert result["nison_two_black_gapping_assessment"] == "CONFIRMED_BEARISH_GAP_SEQUENCE"

    wrong_window = {
        "side": "SELL",
        "nison_gapping_window_direction": "rising",
        "nison_gapping_window_confirmed": True,
        "nison_gapping_window_filled": False,
        "nison_gapping_first_body_color": "black",
        "nison_gapping_second_body_color": "black",
        "nison_data_provenance": "observed_completed_candles",
    }
    assert evaluate_module("nison_two_black_gapping", wrong_window)["view"] == "WAIT"


def test_elliott_impulse_requires_the_three_non_negotiable_wave_rules():
    result = evaluate_module(
        "elliott_impulse_rules",
        {
            "side": "BUY",
            "elliott_impulse_direction": "up",
            "elliott_impulse_mode": "motive",
            "elliott_impulse_subwave_count": 5,
            "elliott_wave_2_retraces_less_than_wave_1": True,
            "elliott_wave_3_not_shortest": True,
            "elliott_wave_4_no_overlap_wave_1": True,
            "elliott_data_provenance": "observed_wave_annotation",
        },
    )
    assert result["view"] == "BUY"
    assert result["elliott_impulse_assessment"] == "VALID_FIVE_WAVE_IMPULSE"

    invalid = {
        "side": "BUY",
        "elliott_impulse_direction": "up",
        "elliott_impulse_mode": "motive",
        "elliott_impulse_subwave_count": 5,
        "elliott_wave_2_retraces_less_than_wave_1": True,
        "elliott_wave_3_not_shortest": False,
        "elliott_wave_4_no_overlap_wave_1": True,
        "elliott_data_provenance": "observed_wave_annotation",
    }
    assert evaluate_module("elliott_impulse_rules", invalid)["view"] == "WAIT"


def test_elliott_corrective_structure_requires_three_wave_mode_and_stays_non_directional():
    result = evaluate_module(
        "elliott_corrective_structure",
        {
            "side": "BUY",
            "elliott_corrective_mode": "corrective",
            "elliott_corrective_subwave_count": 3,
            "elliott_corrective_type": "zigzag",
            "elliott_corrective_complete": True,
            "elliott_data_provenance": "observed_wave_annotation",
        },
    )
    assert result["view"] == "WAIT"
    assert result["elliott_corrective_assessment"] == "COMPLETED_ZIGZAG_CORRECTION"
    assert result["execution_authority"] is False

    five = dict(
        side="BUY",
        elliott_corrective_mode="corrective",
        elliott_corrective_subwave_count=5,
        elliott_corrective_type="zigzag",
        elliott_corrective_complete=True,
        elliott_data_provenance="observed_wave_annotation",
    )
    assert evaluate_module("elliott_corrective_structure", five)["view"] == "WAIT"


def test_elliott_alternation_accepts_sharp_sideways_pair_only():
    result = evaluate_module(
        "elliott_alternation",
        {
            "side": "BUY",
            "elliott_alternation_wave_direction": "up",
            "elliott_wave_2_form": "sharp",
            "elliott_wave_4_form": "sideways",
            "elliott_data_provenance": "observed_wave_annotation",
        },
    )
    assert result["view"] == "BUY"
    assert result["elliott_alternation_assessment"] == "ALTERNATION_PRESENT"

    repeated = dict(
        side="BUY",
        elliott_alternation_wave_direction="up",
        elliott_wave_2_form="sharp",
        elliott_wave_4_form="sharp",
        elliott_data_provenance="observed_wave_annotation",
    )
    assert evaluate_module("elliott_alternation", repeated)["view"] == "WAIT"


def test_price_in_time_ntz_projection_repeats_the_measured_range_from_the_breakout():
    result = evaluate_module(
        "price_in_time_ntz_projection",
        {
            "side": "BUY",
            "pit_projection_direction": "up",
            "pit_projection_width_pips": 20.0,
            "pit_projection_breakout_price": 1.1020,
            "pit_projection_pip_size": 0.0001,
            "pit_projection_level": 2,
            "pit_projection_target_price": 1.1060,
            "pit_projection_data_provenance": "observed_ntz_range",
        },
    )
    assert result["view"] == "BUY"
    assert result["pit_projection_assessment"] == "TARGET_2_CONFIRMED"
    assert result["pit_projected_target_price"] == pytest.approx(1.1060)

    wrong_target = {
        "side": "BUY",
        "pit_projection_direction": "up",
        "pit_projection_width_pips": 20.0,
        "pit_projection_breakout_price": 1.1020,
        "pit_projection_pip_size": 0.0001,
        "pit_projection_level": 2,
        "pit_projection_target_price": 1.1050,
        "pit_projection_data_provenance": "observed_ntz_range",
    }
    assert evaluate_module("price_in_time_ntz_projection", wrong_target)["view"] == "WAIT"


def test_price_in_time_range_cycle_reports_contraction_and_expansion_regimes():
    contraction = evaluate_module(
        "price_in_time_range_cycle",
        {
            "side": "BUY",
            "pit_current_ntz_width_pips": 18.0,
            "pit_previous_ntz_width_pips": 42.0,
            "pit_range_cycle_data_provenance": "observed_daily_ntz_ranges",
        },
    )
    assert contraction["view"] == "WAIT"
    assert contraction["pit_range_cycle_assessment"] == "CONTRACTION_EXPECTED"

    expansion = dict(
        side="BUY",
        pit_current_ntz_width_pips=18.0,
        pit_previous_ntz_width_pips=8.0,
        pit_range_cycle_data_provenance="observed_daily_ntz_ranges",
    )
    assert evaluate_module("price_in_time_range_cycle", expansion)["pit_range_cycle_assessment"] == "EXPANSION_EXPECTED"


def test_price_in_time_pending_order_rule_keeps_only_the_opposite_order_after_a_stop():
    target = evaluate_module(
        "price_in_time_pending_order",
        {
            "side": "BUY",
            "pit_first_trade_status": "target_reached",
            "pit_second_pending_order_active": True,
            "pit_second_pending_order_side": "SELL",
            "pit_pending_order_data_provenance": "observed_ntz_trade_state",
        },
    )
    assert target["pit_pending_order_action"] == "CANCEL_SECOND_PENDING"

    stop = evaluate_module(
        "price_in_time_pending_order",
        {
            "side": "BUY",
            "pit_first_trade_status": "stop_loss",
            "pit_second_pending_order_active": True,
            "pit_second_pending_order_side": "SELL",
            "pit_pending_order_data_provenance": "observed_ntz_trade_state",
        },
    )
    assert stop["pit_pending_order_action"] == "KEEP_OPPOSITE_PENDING"

    both_stops = dict(
        side="BUY",
        pit_first_trade_status="both_stop_loss",
        pit_second_pending_order_active=True,
        pit_second_pending_order_side="SELL",
        pit_pending_order_data_provenance="observed_ntz_trade_state",
    )
    assert evaluate_module("price_in_time_pending_order", both_stops)["pit_pending_order_action"] == "DAY_COMPLETE"

    missing_breakout = evaluate_module(
        "pf_one_box_fulcrum",
        {
            "side": "BUY",
            "pf_box_reversal": "1 box",
            "pf_pattern_type": "fulcrum",
            "pf_fulcrum_direction": "up",
            "pf_move_into_pattern_confirmed": True,
            "pf_move_out_pattern_confirmed": True,
            "pf_catapult_breakout_confirmed": False,
            "pf_catapult_breakout_direction": "up",
            "pf_exit_structure": "rising_bottoms",
            "pf_data_provenance": "observed_point_and_figure_chart",
        },
    )
    assert missing_breakout["view"] == "WAIT"


@pytest.mark.parametrize(
    ("algorithm_id", "state", "expected_view"),
    [
        ("trend_continuation", {"side": "BUY", "trend": "up", "pullback": "bullish_pullback_reclaimed"}, "BUY"),
        ("trend_pullback", {"side": "SELL", "m15_trend": "down", "pullback": "bearish_pullback_reclaimed"}, "SELL"),
        ("range_edge_fade", {"side": "BUY", "range_state": "range", "range_edge_rejection": "lower_edge_reclaimed"}, "BUY"),
        ("failed_breakout", {"side": "SELL", "breakout_state": "failed_break_up"}, "SELL"),
        ("breakout_continuation", {"side": "BUY", "breakout_state": "breakout_up_confirmed"}, "BUY"),
        ("volume_effort_result", {"side": "BUY", "volume_context": {"is_real_volume": True}, "volume_data_provenance": "real_traded_volume", "effort_result_direction": "BUY", "volume_confirmation": "confirmed"}, "BUY"),
        ("pyramiding", {"side": "BUY", "pyramid_state": "authorized", "same_thesis": True, "position_profit": 0.02, "pyramid_signal": "BUY"}, "BUY"),
        ("adverse_selection", {"side": "BUY", "quote_fresh": True, "quote_age_s": 0.2, "spread_pips": 0.5, "adverse_selection_state": "low", "adverse_selection_provenance": "point_in_time_quote_flow"}, "WAIT"),
        ("time_stop", {"side": "BUY", "elapsed_s": 1.0, "horizon_s": 3.0, "time_stop_s": 3.0, "current_executable_pnl": -0.01, "remaining_ev": 0.01}, "WAIT"),
        ("intermarket_analysis", {"side": "BUY", "intermarket_signal": "BUY", "intermarket_confirmation": "confirmed", "intermarket_provenance": "point_in_time_cross_asset", "intermarket_as_of": "2026-08-29T10:00:00Z", "dollar_index_direction": "down", "bond_direction": "up"}, "BUY"),
        ("noise_filter", {"side": "BUY", "noise_state": "low_noise", "noise_provenance": "point_in_time_quote_history", "quote_fresh": True, "quote_age_s": 0.2}, "WAIT"),
        ("tail_risk", {"side": "BUY", "tail_risk_state": "controlled", "tail_risk_provenance": "walk_forward_net_outcomes", "p95_loss": -0.05, "risk_budget": 0.15}, "WAIT"),
        ("event_arbitrage", {"side": "BUY", "event_state": "released", "event_as_of": "2026-08-29T10:00:00Z", "decision_as_of": "2026-08-29T10:00:02Z", "event_window_s": 15, "event_surprise": 1.5, "event_response_direction": "BUY", "event_response_confirmation": "confirmed", "event_oos_n": 40, "event_expectancy_net": 0.02, "event_provenance": "timestamped_event_study"}, "BUY"),
        ("spread_scalping", {"side": "BUY", "spread_scalping_state": "controlled", "spread_scalping_provenance": "point_in_time_quote_history", "two_sided_quote": True, "inventory_state": "flat", "adverse_selection_state": "low", "closeability": "observed", "net_edge": 0.01}, "WAIT"),
        ("latency_arbitrage", {"side": "BUY", "latency_state": "measured", "venue_count": 2, "venue_price_discrepancy": 0.0004, "latency_budget_ms": 20, "latency_observed_ms": 5, "net_edge_after_cost": 0.02, "latency_provenance": "timestamped_multi_venue_quotes", "venue_timestamps_synchronized": True}, "WAIT"),
        ("rebate_capture", {"side": "BUY", "rebate_state": "measured", "rebate_provenance": "venue_fee_schedule", "rebate_per_unit": 0.001, "transaction_cost_per_unit": 0.0005, "fill_probability": 0.7, "directional_probability": 0.6, "net_edge_after_cost": 0.001}, "WAIT"),
        ("market_impact_symmetry", {"side": "BUY", "impact_buy": 0.0002, "impact_sell": -0.0002, "impact_observation_n": 200, "impact_symmetry_status": "symmetric", "impact_provenance": "timestamped_trade_outcomes"}, "WAIT"),
        ("al_brooks_high_low_count", {"side": "BUY", "bar_count_direction": "up", "bar_count": 2, "bar_count_context": "bullish pullback", "bar_count_trendline_break": True, "bar_count_confirmation": "confirmed"}, "BUY"),
        ("al_brooks_wedge", {"side": "BUY", "wedge_reversal_direction": "BUY", "wedge_pushes": 3, "wedge_trendline_break": True, "wedge_confirmation": "confirmed"}, "BUY"),
        ("al_brooks_failed_failure", {"side": "BUY", "failed_failure_direction": "BUY", "initial_breakout_failed": True, "failure_of_failure": True, "failed_failure_confirmation": "confirmed"}, "BUY"),
        ("al_brooks_spike_channel", {"side": "BUY", "spike_channel_signal": "BUY", "spike_channel_state": "spike_then_channel", "spike_channel_test": "held", "spike_channel_confirmation": "confirmed"}, "BUY"),
        ("al_brooks_double_flag", {"side": "BUY", "double_flag_type": "double_bottom_bull_flag", "double_flag_second_test": "held", "double_flag_confirmation": "confirmed"}, "BUY"),
        ("al_brooks_range_location", {"side": "BUY", "range_state": "range", "range_location": "lower_edge", "range_location_provenance": "point_in_time_price_action", "range_location_confirmation": "observed"}, "WAIT"),
        ("momentum", {"side": "BUY", "momentum": 0.001, "momentum_direction": "up", "follow_through": "present"}, "BUY"),
        ("market_profile", {"side": "SELL", "market_profile": {"source": "real_volume_profile"}, "profile_data_provenance": "real_volume_profile", "profile_signal": "SELL"}, "SELL"),
        ("mean_reversion", {"side": "BUY", "regime": "range", "zscore": -2.5}, "BUY"),
        ("trend_structure", {"side": "BUY", "structure": "bullish higher highs", "m15_trend": "up", "h1_trend": "up"}, "BUY"),
        ("breakout_quality", {"side": "BUY", "breakout_state": "breakout_up_confirmed", "structure": "bullish", "retest": "retest_confirmed"}, "BUY"),
        ("pullback_retest", {"side": "BUY", "pullback": "bullish_pullback_reclaimed", "retest": "retest_confirmed", "m15_trend": "up"}, "BUY"),
        ("price_action_candles", {"side": "BUY", "candle": "bullish_signal_bar", "closed_bar": True}, "BUY"),
        ("momentum_exhaustion", {"side": "BUY", "momentum": 0.1, "follow_through": "present"}, "BUY"),
        ("volume_price", {"side": "BUY", "volume": 10, "volume_ratio": 1.4, "bar_range": 0.001, "price_change": "rising", "effort_result": "rising_price_on_tick_activity"}, "WAIT"),
        ("volatility_regime", {"side": "BUY", "volatility_state": "stable", "realized_volatility": 0.001}, "WAIT"),
        ("microstructure", {"side": "BUY", "spread_pips": 0.5, "quote_age_s": 0.1, "quote_fresh": True, "imbalance": 0.2}, "BUY"),
        ("mean_reversion_vs_momentum", {"side": "BUY", "regime": "range", "zscore": -2.5}, "BUY"),
        ("higher_timeframe_alignment", {"side": "BUY", "m15_trend": "up", "h1_trend": "up"}, "BUY"),
        ("session_liquidity", {"side": "BUY", "session": "london", "market_open": True, "liquidity": "observed"}, "WAIT"),
        ("risk_reward_geometry", {"side": "BUY", "entry": 1.1000, "stop": 1.0990, "target": 1.1020, "expected_net_ev": 0.05}, "BUY"),
        ("validation_integrity", {"side": "BUY", "sample_size": 200, "oos_n": 80, "validation_status": "WALK_FORWARD", "uses_future_data": False}, "WAIT"),
        ("market_profile_auction", {"side": "BUY", "auction_state": "initiative_up", "opening_drive": "up", "value_area": {"low": 1.1, "high": 1.101}}, "BUY"),
        ("statistical_arbitrage", {"side": "BUY", "pair": "EURUSD~GBPUSD", "spread_zscore": 2.5, "stationarity": "validated"}, "SELL"),
        ("oscillator_signal", {"side": "BUY", "oscillator": "rsi", "oscillator_state": "oversold", "rsi": 25.0}, "BUY"),
        ("scalping_execution", {"side": "BUY", "spread_pips": 0.5, "quote_age_s": 0.1, "quote_fresh": True, "horizon_s": 3, "tick_direction": "up", "entry": 1.1}, "BUY"),
        ("support_resistance", {"side": "BUY", "support": 1.0990, "resistance": 1.1010, "level_role": "support_hold"}, "BUY"),
        ("chart_patterns", {"side": "BUY", "pattern": "bull_flag", "pattern_confirmation": "confirmed"}, "BUY"),
        ("moving_average_context", {"side": "BUY", "ema_fast": 1.101, "ema_slow": 1.100, "ema_cross": "cross_up"}, "BUY"),
        ("channel_analysis", {"side": "BUY", "channel_state": "ascending", "channel_direction": "ascending"}, "BUY"),
        ("range_edge_rejection", {"side": "BUY", "range_state": "range", "range_edge_rejection": "lower_edge_reclaimed"}, "BUY"),
        ("volatility_breakout", {"side": "BUY", "volatility_transition": "compression_expansion", "breakout_state": "breakout_up_confirmed"}, "BUY"),
        ("divergence", {"side": "BUY", "divergence": "bullish_divergence"}, "BUY"),
        ("opening_range", {"side": "BUY", "opening_range_state": "complete", "opening_range_breakout": "breakout_up"}, "BUY"),
        ("news_event_risk", {"side": "BUY", "news_state": "no_high_impact_news", "high_impact_news": False}, "BUY"),
        ("liquidity_sweep", {"side": "BUY", "liquidity_sweep": "sell_side_sweep_reclaimed"}, "BUY"),
        ("correlation_context", {"side": "BUY", "correlation_state": "aligned", "correlation": 0.8}, "BUY"),
        ("trade_management", {"side": "BUY", "remaining_ev": 0.05, "continuation_probability": 0.8, "expected_additional_upside": 0.10, "expected_downside": 0.02}, "BUY"),
        ("bollinger_bands", {"side": "BUY", "bollinger_state": "below_lower", "bollinger_lower": 1.101, "bollinger_middle": 1.102, "bollinger_upper": 1.103, "entry": 1.1005}, "BUY"),
        ("macd_signal", {"side": "BUY", "macd_state": "bullish", "macd_histogram": 0.0002, "macd_cross": "cross_up"}, "BUY"),
        ("atr_regime", {"side": "BUY", "atr_state": "stable", "atr_14": 0.001}, "WAIT"),
        ("fibonacci_retracement", {"side": "BUY", "fib_retracement_zone": "0.618", "fib_direction": "up", "trend": "up"}, "BUY"),
        ("pivot_levels", {"side": "BUY", "pivot": 1.1000, "pivot_relation": "above_pivot", "previous_session_high": 1.101, "previous_session_low": 1.099, "previous_session_close": 1.1005}, "BUY"),
        ("rsi_reversal", {"side": "BUY", "rsi": 25.0, "rsi_state": "oversold"}, "BUY"),
        ("stochastic_reversal", {"side": "BUY", "stochastic_k": 15.0, "stochastic_state": "oversold"}, "BUY"),
        ("donchian_breakout", {"side": "BUY", "donchian_high": 1.101, "donchian_low": 1.099, "donchian_state": "breakout_up"}, "BUY"),
        ("adx_trend_strength", {"side": "BUY", "adx": 30.0, "di_plus": 35.0, "di_minus": 15.0, "adx_state": "strong", "adx_direction": "up"}, "BUY"),
        ("keltner_channel", {"side": "BUY", "keltner_state": "above_upper", "keltner_middle": 1.1, "keltner_upper": 1.101, "keltner_lower": 1.099}, "BUY"),
        ("ichimoku_context", {"side": "BUY", "ichimoku_state": "bullish", "tenkan_sen": 1.101, "kijun_sen": 1.100, "senkou_span_a": 1.1005, "senkou_span_b": 1.099}, "BUY"),
        ("cci_reversal", {"side": "BUY", "cci": -150.0, "cci_state": "oversold"}, "BUY"),
        ("williams_reversal", {"side": "BUY", "williams_r": -90.0, "williams_state": "oversold"}, "BUY"),
        ("vwap_context", {"side": "BUY", "vwap_proxy": 1.099, "vwap_relation": "above_vwap", "vwap_data_provenance": "tick_volume_proxy"}, "WAIT"),
        ("obv_volume", {"side": "BUY", "obv_proxy": 100.0, "obv_direction": "up", "obv_data_provenance": "tick_volume_proxy"}, "WAIT"),
        ("rate_of_change", {"side": "BUY", "roc_5": 0.002, "roc_state": "positive"}, "BUY"),
        ("parabolic_sar", {"side": "BUY", "parabolic_sar": 1.099, "sar_state": "bullish", "sar_direction": "up"}, "BUY"),
        ("elliott_wave", {"side": "BUY", "elliott_wave_state": "impulse_up", "wave_confirmation": "confirmed", "wave_count": 5}, "BUY"),
        ("harmonic_patterns", {"side": "BUY", "harmonic_pattern": "gartley", "harmonic_direction": "up", "harmonic_confirmation": "confirmed"}, "BUY"),
        ("gann_levels", {"side": "BUY", "gann_state": "support_hold", "gann_direction": "up", "gann_confirmation": "confirmed"}, "BUY"),
        ("cointegration_pairs", {"side": "BUY", "pair": "EURUSD~GBPUSD", "cointegration": "validated", "spread_zscore": -2.5, "pair_signal": "BUY"}, "BUY"),
        ("kalman_filter", {"side": "BUY", "kalman_state": "oversold_reversion", "kalman_zscore": -2.5, "kalman_confirmation": "confirmed"}, "BUY"),
        ("seasonality_context", {"side": "BUY", "seasonal_state": "favorable", "seasonal_direction": "up", "seasonal_sample_n": 200, "seasonal_expectancy": 0.01, "seasonal_validation": "VALIDATED_WALK_FORWARD"}, "BUY"),
        ("order_book_imbalance", {"side": "BUY", "order_book_imbalance": 0.2, "order_book_age_s": 0.2, "depth_levels": 5, "order_book_data_provenance": "real_depth"}, "BUY"),
        ("volume_profile_context", {"side": "BUY", "volume_profile": {"source": "real_volume", "poc": 1.1, "vah": 1.101, "val": 1.099}, "volume_profile_state": "above_value", "volume_profile_direction": "up"}, "BUY"),
        ("fundamental_macro", {"side": "BUY", "macro_bias": "bullish", "macro_confirmation": "confirmed", "macro_data_provenance": "verified_calendar"}, "BUY"),
        ("sentiment_positioning", {"side": "BUY", "sentiment_bias": "bullish", "sentiment_confirmation": "confirmed", "sentiment_data_provenance": "verified_positioning", "sentiment_sample_n": 200}, "BUY"),
        ("time_series_forecasting", {"side": "BUY", "forecast_price": 1.101, "forecast_current_price": 1.100, "forecast_horizon_s": 20, "forecast_oos_status": "WALK_FORWARD", "forecast_uncertainty": 0.0001, "forecast_oos_n": 40, "forecast_mae": 0.00005, "forecast_data_provenance": "causal_quote_walk_forward"}, "BUY"),
        ("machine_learning_signal", {"symbol": "EURUSD", "side": "BUY", "ml_prediction": "BUY", "ml_probability": 0.68, "ml_artifact_status": "EXECUTION_CANDIDATE", "ml_calibration_status": "CALIBRATED", "ml_authorized_symbols": ["EURUSD"], "ml_horizon_s": 5}, "BUY"),
        ("portfolio_allocation", {"side": "BUY", "portfolio_state": "within_limit", "portfolio_impact": "low", "marginal_risk": 0.01, "portfolio_bias": "up"}, "BUY"),
        ("bollinger_pair_mean_reversion", {"side": "BUY", "pair": "EURUSD~GBPUSD", "pair_stationarity": "validated", "pair_zscore": -1.5, "pair_signal": "BUY"}, "BUY"),
        ("ten_period_sd_breakout", {"side": "BUY", "breakout_lookback": 10, "breakout_high_10": 1.1000, "breakout_low_10": 1.0980, "breakout_sd": 0.0002, "current_price": 1.1002}, "BUY"),
        ("triple_screen", {"side": "BUY", "primary_trend": "up", "intermediate_oscillator": "oversold_recovery", "short_trigger": "up_confirmed"}, "BUY"),
        ("volume_spread_analysis", {"side": "BUY", "vsa_pattern": "stopping_volume", "vsa_confirmation": "confirmed", "vsa_volume_ratio": 1.8, "vsa_bar_spread": 0.0003}, "WAIT"),
        ("candlestick_patterns", {"side": "BUY", "candlestick_pattern": "bullish_engulfing", "closed_bar": True}, "BUY"),
        ("initial_balance_profile", {"side": "BUY", "initial_balance_high": 1.1000, "initial_balance_low": 1.0980, "current_price": 1.1003, "profile_state": "initiative_up"}, "BUY"),
        ("cross_sectional_momentum", {"side": "BUY", "momentum_rank_percentile": 0.9, "rank_universe_n": 20, "momentum_direction": "up"}, "BUY"),
        ("meta_labeling", {"side": "BUY", "primary_signal": "BUY", "meta_probability": 0.65, "meta_calibration_status": "CALIBRATED", "meta_oos_status": "WALK_FORWARD"}, "BUY"),
        ("force_index", {"side": "BUY", "force_index": 2.0, "force_index_direction": "up", "force_index_confirmation": "confirmed"}, "WAIT"),
        ("elder_impulse", {"side": "BUY", "ema_slope": "up", "macd_histogram_slope": "up", "impulse_state": "green"}, "BUY"),
        ("market_making_inventory", {"side": "BUY", "market_maker_signal": "buy", "inventory_state": "flat", "microprice": 1.1002, "mid_price": 1.1000, "spread": 0.0002}, "BUY"),
        ("forecast_combination", {"side": "BUY", "forecast_values": [1.101, 1.1008], "forecast_weights": [0.5, 0.5], "forecast_current_price": 1.1000, "forecast_uncertainty": 0.0001, "forecast_oos_status": "WALK_FORWARD"}, "BUY"),
        ("triple_barrier_label", {"side": "BUY", "label_entry_price": 1.1000, "upper_barrier": 1.1010, "lower_barrier": 1.0990, "label_horizon_s": 10, "label_policy": "triple_barrier"}, "WAIT"),
        ("purged_walk_forward", {"validation_status": "PURGED_WALK_FORWARD", "purge_gap_s": 20, "max_label_horizon_s": 10, "embargo_s": 5, "validation_splits": 5}, "WAIT"),
        ("realized_volatility", {"realized_volatility": 0.001, "realized_volatility_window_s": 60, "realized_volatility_observation_n": 60}, "WAIT"),
        ("fractional_differentiation", {"fractional_diff_d": 0.5, "fractional_diff_stationarity": "validated", "fractional_diff_observation_n": 200}, "WAIT"),
        ("risk_parity_allocation", {"risk_parity_weights": {"EURUSD": 0.5, "GBPUSD": 0.5}, "risk_parity_covariance_status": "validated", "risk_parity_budget_status": "within_limit"}, "WAIT"),
        ("vwap_execution", {"vwap_reference": 1.1000, "execution_average_price": 1.1001, "execution_side": "BUY", "execution_volume": 100, "vwap_data_provenance": "real_volume"}, "WAIT"),
        ("twap_execution", {"twap_reference": 1.1000, "execution_average_price": 1.1001, "execution_side": "BUY", "schedule_elapsed_fraction": 0.5, "schedule_status": "active"}, "WAIT"),
        ("participation_execution", {"target_participation_rate": 0.1, "actual_participation_rate": 0.08, "execution_side": "BUY", "market_volume": 1000, "execution_volume": 80}, "WAIT"),
        ("ewmac_trend_following", {"side": "BUY", "ewma_fast": 1.101, "ewma_slow": 1.100, "ewmac_fast_lookback": 8, "ewmac_slow_lookback": 32}, "BUY"),
        ("carry_rule", {"side": "BUY", "carry_return_pct": 2.0, "carry_funding_cost_pct": 0.5, "carry_data_provenance": "verified_forward_carry", "carry_signal": "BUY"}, "BUY"),
        ("ab_system", {"side": "BUY", "ab_mode": "profit_taker", "ab_a": 1, "ab_b": 5, "ab_entry_price": 1.1000, "ab_deviation": 0.001, "ab_high_since_entry": 1.1015, "current_price": 1.1012}, "SELL"),
        ("wyckoff_spring_upthrust", {"side": "BUY", "wyckoff_event": "spring", "wyckoff_confirmation": "confirmed", "wyckoff_volume_confirmation": "confirmed"}, "BUY"),
        ("ttm_squeeze", {"side": "BUY", "squeeze_state": "released", "squeeze_direction": "up", "squeeze_momentum": 0.2, "squeeze_confirmation": "confirmed"}, "BUY"),
        ("al_brooks_second_entry", {"side": "BUY", "second_entry_direction": "up", "second_entry_number": 2, "second_entry_context": "bullish_pullback", "second_entry_confirmation": "confirmed"}, "BUY"),
        ("kangaroo_tail", {"side": "BUY", "tail_direction": "bullish", "tail_context": "support", "tail_confirmation": "confirmed", "tail_wick_ratio": 2.5}, "BUY"),
        ("relative_strength", {"side": "BUY", "relative_strength_ratio": 1.2, "relative_strength_direction": "up", "relative_strength_benchmark": "DXY", "relative_strength_as_of": "2026-08-29T10:00:00Z"}, "BUY"),
        ("point_and_figure", {"side": "BUY", "pnf_pattern": "double_top_breakout", "pnf_direction": "up", "pnf_confirmation": "confirmed", "pnf_box_size": 0.001, "pnf_reversal_boxes": 3}, "BUY"),
        ("cycle_analysis", {"side": "BUY", "cycle_state": "trough_rising", "cycle_direction": "up", "cycle_period": 20, "cycle_confidence": 0.7}, "BUY"),
        ("factor_momentum", {"side": "BUY", "factor_signal": "BUY", "factor_score": 1.2, "factor_rank_percentile": 0.9, "factor_as_of": "2026-08-29T10:00:00Z"}, "BUY"),
        ("fundamental_law", {"signal_breadth": 20, "information_coefficient": 0.05, "transfer_coefficient": 0.5, "fundamental_law_status": "validated"}, "WAIT"),
        ("market_impact", {"order_size": 100, "average_daily_volume": 10000, "spread": 0.0002, "estimated_market_impact": 0.0001, "impact_model_status": "validated"}, "WAIT"),
        ("garch_volatility", {"garch_forecast": 0.001, "garch_model_status": "WALK_FORWARD", "garch_observation_n": 500}, "WAIT"),
        ("hawkes_order_flow", {"hawkes_buy_intensity": 2.0, "hawkes_sell_intensity": 1.0, "hawkes_model_status": "validated", "hawkes_confirmation": "confirmed"}, "BUY"),
        ("turtle_breakout", {"side": "BUY", "turtle_entry_lookback": 20, "turtle_exit_lookback": 10, "turtle_high": 1.1000, "turtle_low": 1.0980, "current_price": 1.1002, "turtle_confirmation": "confirmed"}, "BUY"),
        ("volatility_targeting", {"target_volatility": 0.2, "realized_volatility": 0.15, "volatility_scalar": 1.33, "volatility_target_status": "validated"}, "WAIT"),
        ("position_sizing", {"risk_budget_usd": 0.15, "stop_distance": 0.001, "value_per_price_unit": 100.0, "sizing_status": "validated"}, "WAIT"),
        ("random_forest_signal", {"side": "BUY", "rf_prediction": "BUY", "rf_probability": 0.65, "rf_model_status": "CALIBRATED_WALK_FORWARD", "rf_symbol": "EURUSD"}, "BUY"),
        ("bayesian_pairs", {"side": "BUY", "pair": "EURUSD~GBPUSD", "bayesian_pair_status": "validated", "bayesian_spread_zscore": -2.2, "bayesian_pair_signal": "BUY", "bayesian_posterior_uncertainty": 0.2}, "BUY"),
        ("pca_eigenportfolio", {"pca_status": "validated", "pca_explained_variance": 0.8, "pca_loading": 0.4, "pca_portfolio_name": "eigen_1"}, "WAIT"),
        ("bet_sizing", {"bet_probability": 0.6, "bet_payoff_ratio": 1.5, "bet_sizing_cap": 0.02, "bet_sizing_status": "validated"}, "WAIT"),
        ("feature_importance_stability", {"feature_importance_stability": 0.8, "feature_importance_oos_status": "WALK_FORWARD", "feature_importance_observation_n": 200}, "WAIT"),
        ("stochastic_volatility", {"stochastic_volatility_forecast": 0.001, "stochastic_volatility_status": "WALK_FORWARD", "stochastic_volatility_observation_n": 500}, "WAIT"),
    ],
)
def test_every_registered_algorithm_has_a_meaningful_read_only_fixture(algorithm_id, state, expected_view):
    result = evaluate_module(algorithm_id, state)

    assert algorithm_id in ALGORITHM_MODULES
    assert result["algorithm_id"] == algorithm_id
    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == expected_view
    assert result["source_books"]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False
    assert result["research_only"] is True


def test_context_algorithms_return_explicit_classifications_without_direction_fabrication():
    volatility = evaluate_module(
        "volatility_regime",
        {"volatility_state": "expanding", "volatility_expansion": 1.8, "realized_volatility": 0.002},
    )
    validation = evaluate_module(
        "validation_integrity",
        {
            "sample_size": 100,
            "oos_n": 40,
            "validation_status": "WALK_FORWARD",
            "cost_assumptions": {"spread": True},
            "uses_future_data": True,
        },
    )
    management = evaluate_module(
        "trade_management",
        {
            "side": "BUY",
            "remaining_ev": 0.05,
            "continuation_probability": 0.8,
            "expected_additional_upside": 0.10,
            "expected_downside": 0.02,
        },
    )
    session = evaluate_module(
        "session_liquidity",
        {"session": "london", "market_open": True, "liquidity": "observed_quote_activity"},
    )

    assert volatility["regime_classification"] == "EXPANDING"
    assert volatility["view"] == "WAIT"
    assert validation["validation_assessment"] == "LEAKAGE_RISK"
    assert validation["view"] == "WAIT"
    assert management["management_action"] == "HOLD"
    assert "continuation" in management["why_continuing"].lower()
    assert session["session_class"] == "LONDON"
    assert session["liquidity_assessment"] == "OBSERVED"
    assert session["view"] == "WAIT"


def test_data_intensive_book_perspectives_fail_closed_on_proxy_or_unvalidated_inputs():
    order_book = evaluate_module(
        "order_book_imbalance",
        {"side": "BUY", "order_book_imbalance": 0.8, "order_book_data_provenance": "tick_activity_proxy", "depth_levels": 5},
    )
    volume_profile = evaluate_module(
        "volume_profile_context",
        {"side": "BUY", "volume_profile": {"source": "tick_price_profile_proxy"}, "volume_profile_direction": "up"},
    )
    shadow_ml = evaluate_module(
        "machine_learning_signal",
        {"symbol": "EURUSD", "side": "BUY", "ml_prediction": "BUY", "ml_probability": 0.99, "ml_artifact_status": "SHADOW_ONLY", "ml_calibration_status": "CALIBRATED", "ml_authorized_symbols": ["EURUSD"]},
    )
    macro = evaluate_module(
        "fundamental_macro",
        {"side": "BUY", "macro_bias": "bullish", "macro_confirmation": "confirmed", "macro_data_provenance": "unverified_feed"},
    )
    forecast = evaluate_module(
        "time_series_forecasting",
        {"side": "BUY", "forecast_price": 1.1001, "forecast_current_price": 1.1000, "forecast_uncertainty": 0.001, "forecast_oos_status": "WALK_FORWARD"},
    )
    portfolio = evaluate_module(
        "portfolio_allocation",
        {"side": "BUY", "portfolio_state": "within_limit", "portfolio_impact": "high_correlation", "marginal_risk": 0.01, "portfolio_bias": "up"},
    )

    assert order_book["view"] == "WAIT"
    assert volume_profile["view"] == "WAIT"
    assert shadow_ml["view"] == "WAIT"
    assert macro["view"] == "WAIT"
    assert forecast["applicability"] == "MISSING_DATA"
    assert forecast["view"] == "MISSING_DATA"
    assert portfolio["view"] == "WAIT"
    assert portfolio["allocation_assessment"] == "OUTSIDE_LIMIT"
    assert all(item["execution_authority"] is False for item in (order_book, volume_profile, shadow_ml, macro, forecast))


def test_wyckoff_requires_separate_price_and_volume_confirmation():
    result = evaluate_module(
        "wyckoff_spring_upthrust",
        {
            "side": "BUY",
            "wyckoff_event": "spring",
            "wyckoff_confirmation": "quote_price_proxy_confirmed",
            "wyckoff_volume_confirmation": "volume_unavailable",
        },
    )
    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "WAIT"
    assert "volume" in result["reasons"][0].lower()


@pytest.mark.parametrize(
    ("algorithm_id", "state", "derived_field"),
    [
        (
            "bayesian_pairs",
            {
                "side": "BUY",
                "pair": "EURUSD~GBPUSD",
                "bayesian_pair_status": "NOT_VALIDATED",
                "bayesian_spread_zscore": -2.2,
                "bayesian_pair_signal": "BUY",
                "bayesian_posterior_uncertainty": 0.2,
            },
            None,
        ),
        (
            "bollinger_pair_mean_reversion",
            {
                "side": "BUY",
                "pair": "EURUSD~GBPUSD",
                "pair_stationarity": "NOT_VALIDATED",
                "pair_zscore": -2.0,
                "pair_signal": "BUY",
            },
            None,
        ),
        (
            "carry_rule",
            {
                "side": "BUY",
                "carry_return_pct": 2.0,
                "carry_funding_cost_pct": 0.5,
                "carry_signal": "BUY",
                "carry_data_provenance": "UNVERIFIED_FORWARD_CARRY",
            },
            "net_carry_pct",
        ),
        (
            "forecast_combination",
            {
                "side": "BUY",
                "forecast_values": [1.101, 1.1008],
                "forecast_weights": [0.5, 0.5],
                "forecast_current_price": 1.1000,
                "forecast_uncertainty": 0.0001,
                "forecast_oos_status": "NOT_VALIDATED",
            },
            "combined_forecast",
        ),
        (
            "fundamental_law",
            {
                "signal_breadth": 20,
                "information_coefficient": 0.05,
                "transfer_coefficient": 0.5,
                "fundamental_law_status": "NOT_VALIDATED",
            },
            "forecast_quality_score",
        ),
        (
            "market_impact",
            {
                "order_size": 100,
                "average_daily_volume": 10000,
                "spread": 0.0002,
                "estimated_market_impact": 0.0001,
                "impact_model_status": "NOT_VALIDATED",
            },
            "size_to_adv",
        ),
        (
            "meta_labeling",
            {
                "side": "BUY",
                "primary_signal": "BUY",
                "meta_probability": 0.65,
                "meta_calibration_status": "UNCALIBRATED",
                "meta_oos_status": "WALK_FORWARD",
            },
            None,
        ),
        (
            "pca_eigenportfolio",
            {
                "pca_status": "NOT_VALIDATED",
                "pca_explained_variance": 0.8,
                "pca_loading": 0.4,
                "pca_portfolio_name": "eigen_1",
            },
            "factor_assessment",
        ),
        (
            "position_sizing",
            {
                "risk_budget_usd": 0.15,
                "stop_distance": 0.001,
                "value_per_price_unit": 100.0,
                "sizing_status": "NOT_VALIDATED",
            },
            "theoretical_units",
        ),
        (
            "random_forest_signal",
            {
                "side": "BUY",
                "rf_prediction": "BUY",
                "rf_probability": 0.65,
                "rf_model_status": "UNCALIBRATED_WALK_FORWARD",
                "rf_symbol": "EURUSD",
            },
            None,
        ),
        (
            "risk_parity_allocation",
            {
                "risk_parity_weights": {"EURUSD": 0.5, "GBPUSD": 0.5},
                "risk_parity_covariance_status": "NOT_VALIDATED",
                "risk_parity_budget_status": "within_limit",
            },
            "allocation_assessment",
        ),
        (
            "volatility_targeting",
            {
                "target_volatility": 0.2,
                "realized_volatility": 0.15,
                "volatility_scalar": 1.33,
                "volatility_target_status": "NOT_VALIDATED",
            },
            "implied_scalar",
        ),
    ],
)
def test_negative_validation_labels_never_authorize_or_derive_validated_context(
    algorithm_id, state, derived_field
):
    result = evaluate_module(algorithm_id, state)

    assert result["view"] in {"WAIT", "MISSING_DATA"}
    if derived_field is not None:
        assert derived_field not in result


@pytest.mark.parametrize(
    ("algorithm_id", "state"),
    [
        (
            "al_brooks_second_entry",
            {
                "side": "BUY",
                "second_entry_direction": "up",
                "second_entry_number": 2,
                "second_entry_context": "bullish_pullback",
                "second_entry_confirmation": "unconfirmed",
            },
        ),
        (
            "candlestick_patterns",
            {
                "side": "BUY",
                "candlestick_pattern": "bullish_engulfing",
                "closed_bar": False,
                "candlestick_confirmation": "unconfirmed",
            },
        ),
        (
            "chart_patterns",
            {
                "side": "BUY",
                "pattern": "bull_flag",
                "pattern_confirmation": "unconfirmed",
            },
        ),
        (
            "opening_range",
            {
                "side": "BUY",
                "opening_range_state": "complete",
                "opening_range_breakout": "breakout_up_unconfirmed",
            },
        ),
        (
            "force_index",
            {
                "side": "BUY",
                "force_index": 2.0,
                "force_index_direction": "up",
                "force_index_confirmation": "unconfirmed",
            },
        ),
        (
            "ttm_squeeze",
            {
                "side": "BUY",
                "squeeze_state": "released",
                "squeeze_direction": "up",
                "squeeze_momentum": 0.2,
                "squeeze_confirmation": "unconfirmed",
            },
        ),
        (
            "point_and_figure",
            {
                "side": "BUY",
                "pnf_pattern": "double_top_breakout",
                "pnf_direction": "up",
                "pnf_confirmation": "unconfirmed",
                "pnf_box_size": 0.001,
                "pnf_reversal_boxes": 3,
            },
        ),
        (
            "turtle_breakout",
            {
                "side": "BUY",
                "turtle_entry_lookback": 20,
                "turtle_exit_lookback": 10,
                "turtle_high": 1.1000,
                "turtle_low": 1.0980,
                "current_price": 1.1002,
                "turtle_confirmation": "unconfirmed",
            },
        ),
        (
            "volume_spread_analysis",
            {
                "side": "BUY",
                "vsa_pattern": "stopping_volume",
                "vsa_confirmation": "unconfirmed",
                "vsa_volume_ratio": 1.8,
                "vsa_bar_spread": 0.0003,
            },
        ),
        (
            "volatility_breakout",
            {
                "side": "BUY",
                "volatility_transition": "compression_expansion",
                "breakout_state": "breakout_up_unconfirmed",
                "trend": "up",
            },
        ),
        (
            "wyckoff_spring_upthrust",
            {
                "side": "BUY",
                "wyckoff_event": "spring",
                "wyckoff_confirmation": "unconfirmed",
                "wyckoff_volume_confirmation": "unconfirmed",
            },
        ),
    ],
)
def test_unconfirmed_labels_never_pass_confirmation_gates(algorithm_id, state):
    result = evaluate_module(algorithm_id, state)

    assert result["view"] in {"WAIT", "MISSING_DATA"}


@pytest.mark.parametrize(
    ("algorithm_id", "state"),
    [
        (
            "cointegration_pairs",
            {
                "side": "BUY",
                "pair": "EURUSD~GBPUSD",
                "spread_zscore": -2.5,
                "pair_signal": "BUY",
            },
        ),
        (
            "donchian_breakout",
            {
                "side": "BUY",
                "donchian_high": 1.101,
                "donchian_low": 1.099,
                "donchian_state": "breakout_up",
                "breakout_state": "breakout_up",
                "breakout_confirmation": "unconfirmed",
            },
        ),
        (
            "seasonality_context",
            {
                "side": "BUY",
                "seasonal_state": "favorable",
                "seasonal_direction": "up",
                "seasonal_sample_n": 200,
                "seasonal_expectancy": 0.01,
            },
        ),
        (
            "statistical_arbitrage",
            {
                "side": "BUY",
                "pair": "EURUSD~GBPUSD",
                "spread_zscore": -2.5,
            },
        ),
    ],
)
def test_validation_dependent_perspectives_fail_closed_without_positive_validation(
    algorithm_id, state
):
    result = evaluate_module(algorithm_id, state)

    assert result["view"] in {"WAIT", "MISSING_DATA"}


def test_negative_provenance_and_schedule_labels_do_not_become_positive_evidence():
    macro = evaluate_module(
        "fundamental_macro",
        {
            "side": "BUY",
            "macro_bias": "bullish",
            "macro_confirmation": "confirmed",
            "macro_data_provenance": "calendar",
        },
    )
    sentiment = evaluate_module(
        "sentiment_positioning",
        {
            "side": "BUY",
            "sentiment_bias": "bullish",
            "sentiment_confirmation": "confirmed",
            "sentiment_data_provenance": "positioning",
            "sentiment_sample_n": 200,
        },
    )
    volume_price = evaluate_module(
        "volume_price",
        {
            "side": "BUY",
            "volume": 10,
            "volume_ratio": 1.4,
            "bar_range": 0.001,
            "price_change": "rising",
            "effort_result": "rising_price_on_tick_activity",
            "volume_context": {"source": "tick_activity_proxy"},
        },
    )
    vwap = evaluate_module(
        "vwap_context",
        {
            "side": "BUY",
            "vwap_proxy": 1.099,
            "vwap_relation": "above_vwap",
            "vwap_data_provenance": "tick_volume_proxy",
        },
    )
    obv = evaluate_module(
        "obv_volume",
        {
            "side": "BUY",
            "obv_proxy": 100.0,
            "obv_direction": "up",
            "obv_data_provenance": "tick_volume_proxy",
        },
    )
    force = evaluate_module(
        "force_index",
        {
            "side": "BUY",
            "force_index": 2.0,
            "force_index_direction": "up",
            "force_index_confirmation": "quote_proxy_confirmed",
            "force_index_data_provenance": "tick_volume_proxy",
        },
    )
    vsa = evaluate_module(
        "volume_spread_analysis",
        {
            "side": "BUY",
            "vsa_pattern": "stopping_volume",
            "vsa_confirmation": "quote_proxy_confirmed",
            "vsa_volume_ratio": 1.8,
            "vsa_bar_spread": 0.0003,
            "vsa_data_provenance": "tick_activity_proxy",
        },
    )
    wyckoff = evaluate_module(
        "wyckoff_spring_upthrust",
        {
            "side": "BUY",
            "wyckoff_event": "spring",
            "wyckoff_confirmation": "quote_price_proxy_confirmed",
            "wyckoff_volume_confirmation": "quote_volume_proxy_confirmed",
        },
    )
    order_book = evaluate_module(
        "order_book_imbalance",
        {
            "side": "BUY",
            "order_book_imbalance": 0.8,
            "order_book_data_provenance": "unreal_depth",
            "depth_levels": 5,
        },
    )
    volume_profile = evaluate_module(
        "volume_profile_context",
        {
            "side": "BUY",
            "volume_profile": {"source": "unreal_volume"},
            "volume_profile_direction": "up",
        },
    )
    market_profile = evaluate_module(
        "market_profile_auction",
        {
            "side": "BUY",
            "market_profile": {"source": "tick_price_profile_proxy"},
            "auction_state": "initiative_up",
            "opening_drive": "up",
        },
    )
    purged = evaluate_module(
        "purged_walk_forward",
        {
            "validation_status": "UNPURGED_WALK_FORWARD",
            "purge_gap_s": 20,
            "max_label_horizon_s": 10,
            "embargo_s": 5,
            "validation_splits": 5,
        },
    )
    twap = evaluate_module(
        "twap_execution",
        {
            "twap_reference": 1.1000,
            "execution_average_price": 1.1001,
            "execution_side": "BUY",
            "schedule_elapsed_fraction": 0.5,
            "schedule_status": "inactive",
        },
    )

    assert macro["view"] == "WAIT"
    assert sentiment["view"] == "WAIT"
    assert volume_price["view"] == "WAIT"
    assert vwap["view"] == "WAIT"
    assert obv["view"] == "WAIT"
    assert force["view"] == "WAIT"
    assert vsa["view"] == "WAIT"
    assert wyckoff["view"] == "WAIT"
    assert order_book["view"] == "WAIT"
    assert volume_profile["view"] == "WAIT"
    assert market_profile["view"] == "WAIT"
    assert purged["view"] == "WAIT"
    assert purged.get("validation_assessment") != "LEAKAGE_CONTROLS_PRESENT"
    assert twap["schedule_assessment"] == "OBSERVED"


def test_rate_of_change_accepts_numeric_horizon_alias_without_state_label():
    result = evaluate_module("rate_of_change", {"side": "BUY", "roc_5": 0.001})

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "BUY"


def test_book_specific_algorithms_fail_closed_without_their_required_evidence():
    for algorithm_id in (
        "bollinger_pair_mean_reversion",
        "ten_period_sd_breakout",
        "triple_screen",
        "volume_spread_analysis",
        "candlestick_patterns",
        "initial_balance_profile",
        "cross_sectional_momentum",
        "meta_labeling",
        "force_index",
        "elder_impulse",
        "market_making_inventory",
        "forecast_combination",
        "triple_barrier_label",
        "purged_walk_forward",
        "realized_volatility",
        "fractional_differentiation",
        "risk_parity_allocation",
        "vwap_execution",
        "twap_execution",
        "participation_execution",
        "ewmac_trend_following",
        "carry_rule",
        "ab_system",
        "wyckoff_spring_upthrust",
        "ttm_squeeze",
        "al_brooks_second_entry",
        "kangaroo_tail",
        "relative_strength",
        "point_and_figure",
        "cycle_analysis",
        "factor_momentum",
        "fundamental_law",
        "market_impact",
        "garch_volatility",
        "hawkes_order_flow",
        "turtle_breakout",
        "volatility_targeting",
        "position_sizing",
        "random_forest_signal",
        "bayesian_pairs",
        "pca_eigenportfolio",
        "bet_sizing",
        "feature_importance_stability",
        "stochastic_volatility",
    ):
        result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
        assert result["applicability"] == "MISSING_DATA"
        assert result["view"] == "MISSING_DATA"
        assert result["execution_authority"] is False
