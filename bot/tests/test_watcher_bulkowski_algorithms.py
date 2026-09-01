from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Thomas N. Bulkowski — Encyclopedia of Chart Patterns"


def _double_bottom(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_double_variant": "adam_adam",
        "bulkowski_prior_trend": "down",
        "bulkowski_intervening_move_pct": 14.0,
        "bulkowski_bottom_variation_pct": 3.0,
        "bulkowski_bottom_separation_weeks": 4.0,
        "bulkowski_confirmation_price": 110.0,
        "bulkowski_breakout_close": 111.0,
        "bulkowski_lowest_low": 100.0,
        "bulkowski_stop_buffer": 0.10,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _double_top(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_double_variant": "eve_eve",
        "bulkowski_prior_trend": "up",
        "bulkowski_intervening_move_pct": 12.0,
        "bulkowski_top_variation_pct": 3.0,
        "bulkowski_top_separation_weeks": 4.0,
        "bulkowski_confirmation_price": 90.0,
        "bulkowski_breakout_close": 89.0,
        "bulkowski_highest_high": 100.0,
        "bulkowski_stop_buffer": 0.10,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _flag(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_flag_trend_direction": "up",
        "bulkowski_flag_duration_days": 10.0,
        "bulkowski_flag_upper_slope": -0.10,
        "bulkowski_flag_lower_slope": -0.10,
        "bulkowski_flag_parallel_confirmed": True,
        "bulkowski_pre_flag_run_points": 20.0,
        "bulkowski_preceding_trend_strong": True,
        "bulkowski_flag_volume_trend": "down",
        "bulkowski_flag_breakout_direction": "up",
        "bulkowski_flag_breakout_close_confirmed": True,
        "bulkowski_flag_breakout_price": 120.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _triangle(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_triangle_type": "ascending",
        "bulkowski_triangle_top_slope": 0.0,
        "bulkowski_triangle_bottom_slope": 0.10,
        "bulkowski_triangle_top_touches": 2,
        "bulkowski_triangle_bottom_touches": 2,
        "bulkowski_triangle_crossings": 4,
        "bulkowski_triangle_volume_trend": "down",
        "bulkowski_triangle_breakout_direction": "up",
        "bulkowski_triangle_breakout_close_confirmed": True,
        "bulkowski_triangle_breakout_price": 120.0,
        "bulkowski_triangle_height": 10.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _wedge(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_wedge_type": "falling",
        "bulkowski_wedge_upper_slope": -0.20,
        "bulkowski_wedge_lower_slope": -0.10,
        "bulkowski_wedge_touches": 6,
        "bulkowski_wedge_duration_days": 30,
        "bulkowski_wedge_volume_trend": "down",
        "bulkowski_wedge_breakout_direction": "up",
        "bulkowski_wedge_breakout_confirmed": True,
        "bulkowski_wedge_breakout_price": 120.0,
        "bulkowski_wedge_high": 125.0,
        "bulkowski_wedge_low": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _broadening(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_broadening_type": "bottom",
        "bulkowski_broadening_prior_trend": "down",
        "bulkowski_broadening_top_slope": 0.20,
        "bulkowski_broadening_bottom_slope": -0.10,
        "bulkowski_broadening_top_touches": 3,
        "bulkowski_broadening_bottom_touches": 2,
        "bulkowski_broadening_breakout_direction": "up",
        "bulkowski_broadening_breakout_close_confirmed": True,
        "bulkowski_broadening_breakout_price": 120.0,
        "bulkowski_broadening_high": 115.0,
        "bulkowski_broadening_low": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _right_angled(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_right_angled_type": "descending",
        "bulkowski_right_angled_prior_trend": "up",
        "bulkowski_right_angled_horizontal_slope": 0.0,
        "bulkowski_right_angled_sloped_slope": -0.15,
        "bulkowski_right_angled_horizontal_touches": 2,
        "bulkowski_right_angled_sloped_touches": 2,
        "bulkowski_right_angled_breakout_direction": "down",
        "bulkowski_right_angled_breakout_close_confirmed": True,
        "bulkowski_right_angled_breakout_price": 90.0,
        "bulkowski_right_angled_high": 110.0,
        "bulkowski_right_angled_low": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _broadening_wedge(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_broadening_wedge_type": "ascending",
        "bulkowski_broadening_wedge_upper_slope": 0.20,
        "bulkowski_broadening_wedge_lower_slope": 0.10,
        "bulkowski_broadening_wedge_upper_touches": 3,
        "bulkowski_broadening_wedge_lower_touches": 3,
        "bulkowski_broadening_wedge_breakout_direction": "up",
        "bulkowski_broadening_wedge_breakout_close_confirmed": True,
        "bulkowski_broadening_wedge_breakout_price": 120.0,
        "bulkowski_broadening_wedge_high": 115.0,
        "bulkowski_broadening_wedge_low": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _barr(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_barr_type": "bottom",
        "bulkowski_barr_lead_in_slope": -0.10,
        "bulkowski_barr_bump_slope": -0.35,
        "bulkowski_barr_lead_in_duration_days": 45,
        "bulkowski_barr_lead_in_height": 5.0,
        "bulkowski_barr_bump_height": 11.0,
        "bulkowski_barr_breakout_direction": "up",
        "bulkowski_barr_breakout_close_confirmed": True,
        "bulkowski_barr_breakout_price": 120.0,
        "bulkowski_barr_high": 125.0,
        "bulkowski_barr_low": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _cup(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_cup_type": "normal",
        "bulkowski_cup_prior_trend": "up",
        "bulkowski_cup_prior_rise_pct": 35.0,
        "bulkowski_cup_shape": "rounded",
        "bulkowski_cup_duration_weeks": 20.0,
        "bulkowski_cup_handle_duration_days": 10.0,
        "bulkowski_cup_handle_trend": "down",
        "bulkowski_cup_handle_retrace_pct": 12.0,
        "bulkowski_cup_handle_upper_half": True,
        "bulkowski_cup_left_lip": 110.0,
        "bulkowski_cup_right_lip": 111.0,
        "bulkowski_cup_low": 90.0,
        "bulkowski_cup_high": 111.0,
        "bulkowski_cup_breakout_direction": "up",
        "bulkowski_cup_breakout_close_confirmed": True,
        "bulkowski_cup_breakout_price": 112.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _inverted_cup(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_cup_type": "inverted",
        "bulkowski_cup_prior_trend": "up",
        "bulkowski_cup_shape": "rounded",
        "bulkowski_cup_duration_weeks": 18.0,
        "bulkowski_cup_handle_duration_days": 10.0,
        "bulkowski_cup_handle_retrace_pct": 42.0,
        "bulkowski_cup_handle_exceeds_top": False,
        "bulkowski_cup_left_lip": 110.0,
        "bulkowski_cup_right_lip": 111.0,
        "bulkowski_cup_low": 90.0,
        "bulkowski_cup_high": 120.0,
        "bulkowski_cup_handle_height": 8.0,
        "bulkowski_cup_breakout_direction": "down",
        "bulkowski_cup_breakout_close_confirmed": True,
        "bulkowski_cup_breakout_price": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _diamond(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_diamond_type": "bottom",
        "bulkowski_diamond_prior_trend": "down",
        "bulkowski_diamond_widening_confirmed": True,
        "bulkowski_diamond_narrowing_confirmed": True,
        "bulkowski_diamond_widening_swings": 3,
        "bulkowski_diamond_narrowing_swings": 3,
        "bulkowski_diamond_breakout_direction": "up",
        "bulkowski_diamond_breakout_close_confirmed": True,
        "bulkowski_diamond_breakout_price": 120.0,
        "bulkowski_diamond_high": 115.0,
        "bulkowski_diamond_low": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _high_tight_flag(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_htf_prior_rise_pct": 105.0,
        "bulkowski_htf_prior_rise_days": 50.0,
        "bulkowski_htf_flag_duration_days": 20.0,
        "bulkowski_htf_flag_retrace_pct": 15.0,
        "bulkowski_htf_run_points": 40.0,
        "bulkowski_htf_breakout_direction": "up",
        "bulkowski_htf_breakout_close_confirmed": True,
        "bulkowski_htf_breakout_price": 120.0,
        "bulkowski_htf_flag_low": 110.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _gap(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_gap_type": "breakaway",
        "bulkowski_gap_context": "consolidation",
        "bulkowski_gap_direction": "up",
        "bulkowski_gap_prior_high": 100.0,
        "bulkowski_gap_current_low": 102.0,
        "bulkowski_gap_current_high": 105.0,
        "bulkowski_gap_follow_through_confirmed": True,
        "bulkowski_gap_breakout_price": 102.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _head_shoulders(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_hs_type": "normal",
        "bulkowski_hs_prior_trend": "down",
        "bulkowski_hs_left_shoulder": 90.0,
        "bulkowski_hs_head": 80.0,
        "bulkowski_hs_right_shoulder": 91.0,
        "bulkowski_hs_shoulder_symmetry_pct": 8.0,
        "bulkowski_hs_neckline_price": 100.0,
        "bulkowski_hs_breakout_direction": "up",
        "bulkowski_hs_breakout_close_confirmed": True,
        "bulkowski_hs_breakout_price": 101.0,
        "bulkowski_hs_extra_shoulders": 0,
        "bulkowski_hs_extra_heads": 0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _horn(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_horn_type": "bottom",
        "bulkowski_horn_prior_trend": "down",
        "bulkowski_horn_left_extreme": 80.0,
        "bulkowski_horn_right_extreme": 82.0,
        "bulkowski_horn_intervening_extreme": 95.0,
        "bulkowski_horn_span_weeks": 1.0,
        "bulkowski_horn_breakout_direction": "up",
        "bulkowski_horn_breakout_close_confirmed": True,
        "bulkowski_horn_breakout_price": 96.0,
        "bulkowski_data_provenance": "observed_weekly_quote_bars",
    }
    state.update(overrides)
    return state


def _island(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_island_type": "reversal",
        "bulkowski_island_prior_trend": "down",
        "bulkowski_island_left_gap_direction": "down",
        "bulkowski_island_right_gap_direction": "up",
        "bulkowski_island_gap_prices_overlap": True,
        "bulkowski_island_duration_days": 20.0,
        "bulkowski_island_breakout_direction": "up",
        "bulkowski_island_breakout_close_confirmed": True,
        "bulkowski_island_breakout_price": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _long_island(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_long_island_prior_trend": "up",
        "bulkowski_long_island_left_gap_direction": "up",
        "bulkowski_long_island_right_gap_direction": "down",
        "bulkowski_long_island_left_gap_width": 2.0,
        "bulkowski_long_island_right_gap_width": 1.5,
        "bulkowski_long_island_gaps_aligned": False,
        "bulkowski_long_island_duration_days": 60.0,
        "bulkowski_long_island_breakout_direction": "down",
        "bulkowski_long_island_breakout_close_confirmed": True,
        "bulkowski_long_island_breakout_price": 90.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _measured_move(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_measured_move_type": "down",
        "bulkowski_mm_first_leg_start": 120.0,
        "bulkowski_mm_first_leg_end": 100.0,
        "bulkowski_mm_corrective_phase_start": 100.0,
        "bulkowski_mm_corrective_phase_end": 112.0,
        "bulkowski_mm_second_leg_current": 95.0,
        "bulkowski_mm_corrective_retrace_pct": 60.0,
        "bulkowski_mm_breakout_confirmed": True,
        "bulkowski_mm_breakout_price": 99.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _pennant(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_pennant_trend_direction": "up",
        "bulkowski_pennant_duration_days": 10.0,
        "bulkowski_pennant_upper_slope": -0.10,
        "bulkowski_pennant_lower_slope": 0.10,
        "bulkowski_pennant_converging_confirmed": True,
        "bulkowski_pennant_preceding_run_points": 20.0,
        "bulkowski_pennant_breakout_direction": "up",
        "bulkowski_pennant_breakout_close_confirmed": True,
        "bulkowski_pennant_breakout_price": 120.0,
        "bulkowski_pennant_high": 115.0,
        "bulkowski_pennant_low": 110.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _pipe(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_pipe_type": "bottom",
        "bulkowski_pipe_timeframe": "weekly",
        "bulkowski_pipe_prior_trend": "down",
        "bulkowski_pipe_spikes_unusually_large": True,
        "bulkowski_pipe_overlap_confirmed": True,
        "bulkowski_pipe_obvious_confirmed": True,
        "bulkowski_pipe_left_low": 80.0,
        "bulkowski_pipe_right_low": 82.0,
        "bulkowski_pipe_left_high": 95.0,
        "bulkowski_pipe_right_high": 94.0,
        "bulkowski_pipe_high": 95.0,
        "bulkowski_pipe_low": 80.0,
        "bulkowski_pipe_breakout_direction": "up",
        "bulkowski_pipe_breakout_close_confirmed": True,
        "bulkowski_pipe_breakout_price": 96.0,
        "bulkowski_data_provenance": "observed_weekly_quote_bars",
    }
    state.update(overrides)
    return state


def _rectangle(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_rectangle_type": "bottom",
        "bulkowski_rectangle_prior_trend": "down",
        "bulkowski_rectangle_upper_slope": 0.01,
        "bulkowski_rectangle_lower_slope": -0.01,
        "bulkowski_rectangle_horizontal_boundaries_confirmed": True,
        "bulkowski_rectangle_upper_touches": 3,
        "bulkowski_rectangle_lower_touches": 3,
        "bulkowski_rectangle_high": 115.0,
        "bulkowski_rectangle_low": 100.0,
        "bulkowski_rectangle_breakout_direction": "up",
        "bulkowski_rectangle_breakout_close_confirmed": True,
        "bulkowski_rectangle_breakout_price": 116.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _rounding(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_rounding_type": "bottom",
        "bulkowski_rounding_timeframe": "weekly",
        "bulkowski_rounding_prior_trend": "up",
        "bulkowski_rounding_shape": "rounded_bowl",
        "bulkowski_rounding_start_price": 110.0,
        "bulkowski_rounding_end_price": 111.0,
        "bulkowski_rounding_low": 90.0,
        "bulkowski_rounding_high": 111.0,
        "bulkowski_rounding_end_variation_pct": 0.9,
        "bulkowski_rounding_curve_confirmed": True,
        "bulkowski_rounding_breakout_direction": "up",
        "bulkowski_rounding_breakout_close_confirmed": True,
        "bulkowski_rounding_breakout_price": 112.0,
        "bulkowski_data_provenance": "observed_weekly_quote_bars",
    }
    state.update(overrides)
    return state


def _scallop(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_scallop_type": "ascending",
        "bulkowski_scallop_prior_trend": "up",
        "bulkowski_scallop_shape_confirmed": True,
        "bulkowski_scallop_smooth_confirmed": True,
        "bulkowski_scallop_start_price": 100.0,
        "bulkowski_scallop_peak_price": 120.0,
        "bulkowski_scallop_bowl_low": 95.0,
        "bulkowski_scallop_end_price": 115.0,
        "bulkowski_scallop_retrace_pct": 60.0,
        "bulkowski_scallop_width_days": 20.0,
        "bulkowski_scallop_proportion_confirmed": True,
        "bulkowski_scallop_breakout_direction": "up",
        "bulkowski_scallop_breakout_close_confirmed": True,
        "bulkowski_scallop_breakout_price": 121.0,
        "bulkowski_scallop_high": 120.0,
        "bulkowski_scallop_low": 95.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _descending_triangle(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_desc_triangle_top_slope": -0.10,
        "bulkowski_desc_triangle_bottom_slope": 0.0,
        "bulkowski_desc_triangle_top_touches": 3,
        "bulkowski_desc_triangle_bottom_touches": 3,
        "bulkowski_desc_triangle_horizontal_support_confirmed": True,
        "bulkowski_desc_triangle_white_space_covered": True,
        "bulkowski_desc_triangle_high": 120.0,
        "bulkowski_desc_triangle_low": 100.0,
        "bulkowski_desc_triangle_breakout_direction": "down",
        "bulkowski_desc_triangle_breakout_close_confirmed": True,
        "bulkowski_desc_triangle_breakout_price": 99.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _symmetrical_triangle(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_sym_triangle_upper_slope": -0.10,
        "bulkowski_sym_triangle_lower_slope": 0.10,
        "bulkowski_sym_triangle_upper_touches": 3,
        "bulkowski_sym_triangle_lower_touches": 3,
        "bulkowski_sym_triangle_converging_confirmed": True,
        "bulkowski_sym_triangle_white_space_covered": True,
        "bulkowski_sym_triangle_duration_weeks": 6.0,
        "bulkowski_sym_triangle_high": 120.0,
        "bulkowski_sym_triangle_low": 100.0,
        "bulkowski_sym_triangle_breakout_direction": "up",
        "bulkowski_sym_triangle_breakout_close_confirmed": True,
        "bulkowski_sym_triangle_breakout_price": 121.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _rising_wedge(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_rising_wedge_upper_slope": 0.10,
        "bulkowski_rising_wedge_lower_slope": 0.20,
        "bulkowski_rising_wedge_upper_touches": 3,
        "bulkowski_rising_wedge_lower_touches": 3,
        "bulkowski_rising_wedge_duration_weeks": 6.0,
        "bulkowski_rising_wedge_breakout_direction": "down",
        "bulkowski_rising_wedge_breakout_close_confirmed": True,
        "bulkowski_rising_wedge_breakout_price": 99.0,
        "bulkowski_rising_wedge_high": 120.0,
        "bulkowski_rising_wedge_low": 100.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _triple(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_triple_type": "bottom",
        "bulkowski_triple_prior_trend": "down",
        "bulkowski_triple_timeframe": "weekly",
        "bulkowski_triple_first": 90.0,
        "bulkowski_triple_second": 90.5,
        "bulkowski_triple_third": 90.2,
        "bulkowski_triple_level_variation_pct": 1.1,
        "bulkowski_triple_distinct_confirmed": True,
        "bulkowski_triple_proportion_confirmed": True,
        "bulkowski_triple_confirmation_level": 110.0,
        "bulkowski_triple_high": 110.0,
        "bulkowski_triple_low": 90.0,
        "bulkowski_triple_breakout_direction": "up",
        "bulkowski_triple_breakout_close_confirmed": True,
        "bulkowski_triple_breakout_price": 111.0,
        "bulkowski_data_provenance": "observed_weekly_quote_bars",
    }
    state.update(overrides)
    return state


def _three_peaks(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_three_peaks_prior_trend": "up",
        "bulkowski_three_peaks_first": 120.0,
        "bulkowski_three_peaks_second": 115.0,
        "bulkowski_three_peaks_third": 110.0,
        "bulkowski_three_peaks_proportion_confirmed": True,
        "bulkowski_three_peaks_confirmation_level": 100.0,
        "bulkowski_three_peaks_pattern_high": 120.0,
        "bulkowski_three_peaks_pattern_low": 100.0,
        "bulkowski_three_peaks_breakout_direction": "down",
        "bulkowski_three_peaks_breakout_close_confirmed": True,
        "bulkowski_three_peaks_breakout_price": 99.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _three_valleys(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_three_valleys_prior_trend": "up",
        "bulkowski_three_valleys_first": 90.0,
        "bulkowski_three_valleys_second": 95.0,
        "bulkowski_three_valleys_third": 100.0,
        "bulkowski_three_valleys_proportion_confirmed": True,
        "bulkowski_three_valleys_confirmation_level": 120.0,
        "bulkowski_three_valleys_pattern_high": 120.0,
        "bulkowski_three_valleys_pattern_low": 90.0,
        "bulkowski_three_valleys_breakout_direction": "up",
        "bulkowski_three_valleys_breakout_close_confirmed": True,
        "bulkowski_three_valleys_breakout_price": 121.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _dcb(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_dcb_negative_event_confirmed": True,
        "bulkowski_dcb_price_gap_down_confirmed": True,
        "bulkowski_dcb_plunge_pct": 30.0,
        "bulkowski_dcb_bounce_pct": 20.0,
        "bulkowski_dcb_postbounce_decline_pct": 20.0,
        "bulkowski_dcb_plunge_days": 2.0,
        "bulkowski_dcb_bounce_days": 10.0,
        "bulkowski_dcb_decline_days": 20.0,
        "bulkowski_dcb_event_high": 120.0,
        "bulkowski_dcb_event_low": 84.0,
        "bulkowski_dcb_bounce_high": 101.0,
        "bulkowski_dcb_current_price": 90.0,
        "bulkowski_dcb_decline_confirmed": True,
        "bulkowski_dcb_signal_direction": "down",
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _idcb(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_idcb_positive_event_confirmed": True,
        "bulkowski_idcb_price_gap_up_confirmed": True,
        "bulkowski_idcb_initial_rise_pct": 15.0,
        "bulkowski_idcb_rise_days": 1.0,
        "bulkowski_idcb_retrace_pct": 50.0,
        "bulkowski_idcb_launch_price": 100.0,
        "bulkowski_idcb_retrace_low": 99.0,
        "bulkowski_idcb_current_price": 112.0,
        "bulkowski_idcb_higher_high_confirmed": True,
        "bulkowski_idcb_recovery_confirmed": True,
        "bulkowski_idcb_signal_direction": "up",
        "bulkowski_idcb_signal_price": 112.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _earnings_surprise(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_earnings_surprise_type": "good",
        "bulkowski_earnings_prior_trend": "up",
        "bulkowski_earnings_announced": True,
        "bulkowski_earnings_announcement_range": 8.0,
        "bulkowski_earnings_month_average_range": 5.0,
        "bulkowski_earnings_announcement_high": 110.0,
        "bulkowski_earnings_announcement_low": 100.0,
        "bulkowski_earnings_breakout_direction": "up",
        "bulkowski_earnings_breakout_close_confirmed": True,
        "bulkowski_earnings_breakout_price": 111.0,
        "bulkowski_earnings_nearby_support_clear": True,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _fda(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_fda_approval_announced": True,
        "bulkowski_fda_announcement_range": 8.0,
        "bulkowski_fda_month_average_range": 5.0,
        "bulkowski_fda_gap_confirmed": True,
        "bulkowski_fda_volume_above_average": True,
        "bulkowski_fda_announcement_high": 110.0,
        "bulkowski_fda_announcement_low": 100.0,
        "bulkowski_fda_breakout_direction": "up",
        "bulkowski_fda_breakout_close_confirmed": True,
        "bulkowski_fda_breakout_price": 111.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _earnings_flag(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_earnings_flag_good_earnings_confirmed": True,
        "bulkowski_earnings_flag_flagpole_points": 20.0,
        "bulkowski_earnings_flag_flagpole_days": 2.0,
        "bulkowski_earnings_flag_consolidation_confirmed": True,
        "bulkowski_earnings_flag_duration_days": 10.0,
        "bulkowski_earnings_flag_high": 110.0,
        "bulkowski_earnings_flag_low": 100.0,
        "bulkowski_earnings_flag_breakout_direction": "up",
        "bulkowski_earnings_flag_breakout_close_confirmed": True,
        "bulkowski_earnings_flag_breakout_price": 111.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _same_store(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "bulkowski_same_store_type": "good",
        "bulkowski_same_store_announced": True,
        "bulkowski_same_store_range": 8.0,
        "bulkowski_same_store_month_average_range": 5.0,
        "bulkowski_same_store_gap_confirmed": True,
        "bulkowski_same_store_volume_above_average": True,
        "bulkowski_same_store_announcement_high": 110.0,
        "bulkowski_same_store_announcement_low": 100.0,
        "bulkowski_same_store_breakout_direction": "up",
        "bulkowski_same_store_breakout_close_confirmed": True,
        "bulkowski_same_store_breakout_price": 111.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def _broker_event(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "SELL",
        "bulkowski_broker_event_announced": True,
        "bulkowski_broker_event_range": 8.0,
        "bulkowski_broker_event_month_average_range": 5.0,
        "bulkowski_broker_event_volume_above_average": True,
        "bulkowski_broker_event_announcement_high": 110.0,
        "bulkowski_broker_event_announcement_low": 100.0,
        "bulkowski_broker_event_breakout_direction": "down",
        "bulkowski_broker_event_breakout_close_confirmed": True,
        "bulkowski_broker_event_breakout_price": 99.0,
        "bulkowski_data_provenance": "observed_daily_quote_bars",
    }
    state.update(overrides)
    return state


def test_bulkowski_double_bottom_requires_confirmed_breakout_and_measure_rule():
    result = evaluate_module("bulkowski_double_bottom", _double_bottom())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 120.0
    assert result["bulkowski_stop_price"] == pytest.approx(99.90)
    assert result["source_books"] == [SOURCE]
    assert evaluate_module("bulkowski_double_bottom", _double_bottom(bulkowski_breakout_close=109.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_double_bottom", _double_bottom(bulkowski_intervening_move_pct=8.0))["view"] == "WAIT"


def test_bulkowski_double_top_is_the_directional_mirror():
    result = evaluate_module("bulkowski_double_top", _double_top())
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 80.0
    assert result["bulkowski_stop_price"] == pytest.approx(100.10)
    assert evaluate_module("bulkowski_double_top", _double_top(bulkowski_breakout_close=91.0))["view"] == "WAIT"


def test_bulkowski_flag_requires_strong_preceding_run_short_duration_and_breakout():
    result = evaluate_module("bulkowski_flag_breakout", _flag())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 140.0
    assert evaluate_module("bulkowski_flag_breakout", _flag(bulkowski_flag_duration_days=22))["view"] == "WAIT"
    assert evaluate_module("bulkowski_flag_breakout", _flag(bulkowski_preceding_trend_strong=False))["view"] == "WAIT"


def test_bulkowski_ascending_triangle_requires_two_sided_structure_and_close_break():
    result = evaluate_module("bulkowski_ascending_triangle", _triangle())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 130.0
    sell = evaluate_module(
        "bulkowski_ascending_triangle",
        _triangle(
            side="SELL",
            bulkowski_triangle_breakout_direction="down",
            bulkowski_triangle_breakout_price=100.0,
        ),
    )
    assert sell["view"] == "SELL"
    assert sell["bulkowski_measure_target"] == 90.0
    assert evaluate_module("bulkowski_ascending_triangle", _triangle(bulkowski_triangle_top_touches=1))["view"] == "WAIT"


def test_bulkowski_falling_wedge_requires_converging_down_slopes_and_five_touches():
    result = evaluate_module("bulkowski_falling_wedge", _wedge())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 125.0
    assert evaluate_module("bulkowski_falling_wedge", _wedge(bulkowski_wedge_touches=4))["view"] == "WAIT"
    assert evaluate_module("bulkowski_falling_wedge", _wedge(bulkowski_wedge_lower_slope=0.0))["view"] == "WAIT"


def test_bulkowski_broadening_bottom_requires_diverging_lines_and_confirmed_breakout():
    result = evaluate_module("bulkowski_broadening_bottom", _broadening())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 135.0
    assert evaluate_module("bulkowski_broadening_bottom", _broadening(bulkowski_broadening_top_slope=0.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_broadening_bottom", _broadening(bulkowski_broadening_breakout_close_confirmed=False))["view"] == "WAIT"


def test_bulkowski_broadening_top_mirrors_prior_trend_and_breakout():
    result = evaluate_module(
        "bulkowski_broadening_top",
        _broadening(
            side="SELL",
            bulkowski_broadening_type="top",
            bulkowski_broadening_prior_trend="up",
            bulkowski_broadening_breakout_direction="down",
            bulkowski_broadening_breakout_price=90.0,
        ),
    )
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 75.0
    assert evaluate_module("bulkowski_broadening_top", _broadening(bulkowski_broadening_prior_trend="down"))["view"] == "WAIT"


def test_bulkowski_right_angled_formations_require_horizontal_and_sloped_boundaries():
    result = evaluate_module("bulkowski_right_angled_descending", _right_angled())
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 80.0
    assert evaluate_module("bulkowski_right_angled_descending", _right_angled(bulkowski_right_angled_horizontal_touches=1))["view"] == "WAIT"
    ascending = evaluate_module(
        "bulkowski_right_angled_ascending",
        _right_angled(
            side="BUY",
            bulkowski_right_angled_type="ascending",
            bulkowski_right_angled_prior_trend="up",
            bulkowski_right_angled_sloped_slope=0.15,
            bulkowski_right_angled_breakout_direction="up",
            bulkowski_right_angled_breakout_price=120.0,
        ),
    )
    assert ascending["view"] == "BUY"


def test_bulkowski_broadening_wedges_require_three_touches_and_divergence():
    result = evaluate_module("bulkowski_ascending_broadening_wedge", _broadening_wedge())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 135.0
    descending = evaluate_module(
        "bulkowski_descending_broadening_wedge",
        _broadening_wedge(
            side="SELL",
            bulkowski_broadening_wedge_type="descending",
            bulkowski_broadening_wedge_upper_slope=-0.10,
            bulkowski_broadening_wedge_lower_slope=-0.20,
            bulkowski_broadening_wedge_breakout_direction="down",
            bulkowski_broadening_wedge_breakout_price=90.0,
        ),
    )
    assert descending["view"] == "SELL"
    assert evaluate_module("bulkowski_ascending_broadening_wedge", _broadening_wedge(bulkowski_broadening_wedge_upper_touches=2))["view"] == "WAIT"


def test_bulkowski_barr_requires_deep_bump_and_lead_in():
    result = evaluate_module("bulkowski_barr_bottom", _barr())
    assert result["view"] == "BUY"
    assert evaluate_module("bulkowski_barr_bottom", _barr(bulkowski_barr_bump_height=9.0))["view"] == "WAIT"
    top = evaluate_module(
        "bulkowski_barr_top",
        _barr(
            side="SELL",
            bulkowski_barr_type="top",
            bulkowski_barr_lead_in_slope=0.10,
            bulkowski_barr_bump_slope=0.35,
            bulkowski_barr_breakout_direction="down",
            bulkowski_barr_breakout_price=90.0,
        ),
    )
    assert top["view"] == "SELL"


def test_bulkowski_cup_with_handle_uses_rise_duration_lips_and_breakout():
    result = evaluate_module("bulkowski_cup_with_handle", _cup())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 132.0
    assert evaluate_module("bulkowski_cup_with_handle", _cup(bulkowski_cup_prior_rise_pct=25.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_cup_with_handle", _cup(bulkowski_cup_handle_upper_half=False))["view"] == "WAIT"


def test_bulkowski_inverted_cup_uses_right_rim_break_and_handle_measure():
    result = evaluate_module("bulkowski_inverted_cup_with_handle", _inverted_cup())
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 92.0
    assert evaluate_module("bulkowski_inverted_cup_with_handle", _inverted_cup(bulkowski_cup_handle_exceeds_top=True))["view"] == "WAIT"
    assert evaluate_module("bulkowski_inverted_cup_with_handle", _inverted_cup(bulkowski_cup_breakout_close_confirmed=False))["view"] == "WAIT"


def test_bulkowski_diamonds_require_widening_then_narrowing_structure():
    result = evaluate_module("bulkowski_diamond_bottom", _diamond())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 135.0
    top = evaluate_module(
        "bulkowski_diamond_top",
        _diamond(
            side="SELL",
            bulkowski_diamond_type="top",
            bulkowski_diamond_prior_trend="up",
            bulkowski_diamond_breakout_direction="down",
            bulkowski_diamond_breakout_price=90.0,
        ),
    )
    assert top["view"] == "SELL"
    assert evaluate_module("bulkowski_diamond_bottom", _diamond(bulkowski_diamond_narrowing_confirmed=False))["view"] == "WAIT"


def test_bulkowski_high_tight_flag_requires_a_doubling_run_and_bounded_pause():
    result = evaluate_module("bulkowski_high_tight_flag", _high_tight_flag())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 140.0
    assert evaluate_module("bulkowski_high_tight_flag", _high_tight_flag(bulkowski_htf_prior_rise_pct=90.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_high_tight_flag", _high_tight_flag(bulkowski_htf_flag_retrace_pct=25.0))["view"] == "WAIT"


def test_bulkowski_gap_classification_requires_true_bidirectional_gap_and_context():
    result = evaluate_module("bulkowski_gap", _gap())
    assert result["view"] == "BUY"
    assert result["bulkowski_gap_width"] == 2.0
    assert evaluate_module("bulkowski_gap", _gap(bulkowski_gap_current_low=99.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_gap", _gap(bulkowski_gap_context="trend"))["view"] == "WAIT"


def test_bulkowski_head_and_shoulders_variants_require_symmetry_and_neckline_break():
    result = evaluate_module("bulkowski_head_shoulders_bottom", _head_shoulders())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 121.0
    top = evaluate_module(
        "bulkowski_head_shoulders_top",
        _head_shoulders(
            side="SELL",
            bulkowski_hs_prior_trend="up",
            bulkowski_hs_left_shoulder=110.0,
            bulkowski_hs_head=120.0,
            bulkowski_hs_right_shoulder=109.0,
            bulkowski_hs_neckline_price=100.0,
            bulkowski_hs_breakout_direction="down",
            bulkowski_hs_breakout_price=99.0,
        ),
    )
    assert top["view"] == "SELL"
    complex_bottom = evaluate_module(
        "bulkowski_complex_head_shoulders_bottom",
        _head_shoulders(bulkowski_hs_type="complex", bulkowski_hs_extra_shoulders=2),
    )
    assert complex_bottom["view"] == "BUY"
    assert evaluate_module("bulkowski_head_shoulders_bottom", _head_shoulders(bulkowski_hs_shoulder_symmetry_pct=25.0))["view"] == "WAIT"


def test_bulkowski_horn_variants_require_two_spikes_and_one_week_separation():
    result = evaluate_module("bulkowski_horn_bottom", _horn())
    assert result["view"] == "BUY"
    top = evaluate_module(
        "bulkowski_horn_top",
        _horn(
            side="SELL",
            bulkowski_horn_type="top",
            bulkowski_horn_prior_trend="up",
            bulkowski_horn_left_extreme=110.0,
            bulkowski_horn_right_extreme=108.0,
            bulkowski_horn_intervening_extreme=95.0,
            bulkowski_horn_breakout_direction="down",
            bulkowski_horn_breakout_price=94.0,
        ),
    )
    assert top["view"] == "SELL"
    assert evaluate_module("bulkowski_horn_bottom", _horn(bulkowski_horn_span_weeks=3.0))["view"] == "WAIT"


def test_bulkowski_island_reversal_requires_opposing_gaps_at_a_shared_level():
    result = evaluate_module("bulkowski_island_reversal", _island())
    assert result["view"] == "BUY"
    top = evaluate_module(
        "bulkowski_island_reversal",
        _island(
            side="SELL",
            bulkowski_island_prior_trend="up",
            bulkowski_island_left_gap_direction="up",
            bulkowski_island_right_gap_direction="down",
            bulkowski_island_breakout_direction="down",
            bulkowski_island_breakout_price=90.0,
        ),
    )
    assert top["view"] == "SELL"
    assert evaluate_module("bulkowski_island_reversal", _island(bulkowski_island_gap_prices_overlap=False))["view"] == "WAIT"


def test_bulkowski_long_island_requires_wide_unaligned_gaps_and_short_duration():
    result = evaluate_module("bulkowski_long_island", _long_island())
    assert result["view"] == "SELL"
    assert evaluate_module("bulkowski_long_island", _long_island(bulkowski_long_island_left_gap_width=0.5))["view"] == "WAIT"
    assert evaluate_module("bulkowski_long_island", _long_island(bulkowski_long_island_gaps_aligned=True))["view"] == "WAIT"


def test_bulkowski_measured_move_variants_require_a_38_to_62_percent_correction():
    result = evaluate_module("bulkowski_measured_move_down", _measured_move())
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 102.0
    up = evaluate_module(
        "bulkowski_measured_move_up",
        _measured_move(
            side="BUY",
            bulkowski_measured_move_type="up",
            bulkowski_mm_first_leg_start=80.0,
            bulkowski_mm_first_leg_end=100.0,
            bulkowski_mm_corrective_phase_start=100.0,
            bulkowski_mm_corrective_phase_end=88.0,
            bulkowski_mm_second_leg_current=105.0,
            bulkowski_mm_breakout_price=101.0,
        ),
    )
    assert up["view"] == "BUY"
    assert evaluate_module("bulkowski_measured_move_down", _measured_move(bulkowski_mm_corrective_retrace_pct=20.0))["view"] == "WAIT"


def test_bulkowski_pennant_requires_a_short_converging_pause_after_a_fast_run():
    result = evaluate_module("bulkowski_pennant", _pennant())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 140.0
    assert evaluate_module("bulkowski_pennant", _pennant(bulkowski_pennant_duration_days=22.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_pennant", _pennant(bulkowski_pennant_converging_confirmed=False))["view"] == "WAIT"


def test_bulkowski_pipe_bottom_and_top_require_weekly_spikes_and_confirmation():
    result = evaluate_module("bulkowski_pipe_bottom", _pipe())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 111.0
    top = evaluate_module(
        "bulkowski_pipe_top",
        _pipe(
            side="SELL",
            bulkowski_pipe_type="top",
            bulkowski_pipe_prior_trend="up",
            bulkowski_pipe_left_high=120.0,
            bulkowski_pipe_right_high=118.0,
            bulkowski_pipe_low=105.0,
            bulkowski_pipe_breakout_direction="down",
            bulkowski_pipe_breakout_price=104.0,
        ),
    )
    assert top["view"] == "SELL"
    assert evaluate_module("bulkowski_pipe_bottom", _pipe(bulkowski_pipe_timeframe="daily"))["view"] == "WAIT"


def test_bulkowski_rectangles_require_trend_context_flat_boundaries_and_touches():
    result = evaluate_module("bulkowski_rectangle_bottom", _rectangle())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 131.0
    top = evaluate_module(
        "bulkowski_rectangle_top",
        _rectangle(
            side="SELL",
            bulkowski_rectangle_type="top",
            bulkowski_rectangle_prior_trend="up",
            bulkowski_rectangle_breakout_direction="down",
            bulkowski_rectangle_breakout_price=99.0,
        ),
    )
    assert top["view"] == "SELL"
    assert evaluate_module("bulkowski_rectangle_bottom", _rectangle(bulkowski_rectangle_lower_touches=1))["view"] == "WAIT"


def test_bulkowski_rounding_turns_require_curved_shape_even_ends_and_breakout():
    result = evaluate_module("bulkowski_rounding_bottom", _rounding())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 132.0
    top = evaluate_module(
        "bulkowski_rounding_top",
        _rounding(
            side="SELL",
            bulkowski_rounding_type="top",
            bulkowski_rounding_shape="rounded_dome",
            bulkowski_rounding_end_price=110.0,
            bulkowski_rounding_high=120.0,
            bulkowski_rounding_breakout_direction="down",
            bulkowski_rounding_breakout_price=89.0,
        ),
    )
    assert top["view"] == "SELL"
    assert evaluate_module("bulkowski_rounding_bottom", _rounding(bulkowski_rounding_end_variation_pct=6.0))["view"] == "WAIT"


def test_bulkowski_scallop_variants_preserve_their_distinct_shapes_and_directions():
    result = evaluate_module("bulkowski_ascending_scallop", _scallop())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 146.0
    inverted_up = evaluate_module(
        "bulkowski_ascending_inverted_scallop",
        _scallop(
            bulkowski_scallop_type="ascending_inverted",
            bulkowski_scallop_end_price=105.0,
            bulkowski_scallop_breakout_price=121.0,
        ),
    )
    assert inverted_up["view"] == "BUY"
    descending = evaluate_module(
        "bulkowski_descending_scallop",
        _scallop(
            side="SELL",
            bulkowski_scallop_type="descending",
            bulkowski_scallop_prior_trend="down",
            bulkowski_scallop_start_price=120.0,
            bulkowski_scallop_peak_price=125.0,
            bulkowski_scallop_end_price=105.0,
            bulkowski_scallop_breakout_direction="down",
            bulkowski_scallop_breakout_price=94.0,
            bulkowski_scallop_high=120.0,
            bulkowski_scallop_low=95.0,
        ),
    )
    assert descending["view"] == "SELL"
    inverted_down = evaluate_module(
        "bulkowski_descending_inverted_scallop",
        _scallop(
            side="SELL",
            bulkowski_scallop_type="descending_inverted",
            bulkowski_scallop_prior_trend="down",
            bulkowski_scallop_start_price=100.0,
            bulkowski_scallop_peak_price=120.0,
            bulkowski_scallop_bowl_low=80.0,
            bulkowski_scallop_end_price=90.0,
            bulkowski_scallop_breakout_direction="down",
            bulkowski_scallop_breakout_price=79.0,
            bulkowski_scallop_high=120.0,
            bulkowski_scallop_low=80.0,
        ),
    )
    assert inverted_down["view"] == "SELL"
    assert evaluate_module("bulkowski_ascending_scallop", _scallop(bulkowski_scallop_proportion_confirmed=False))["view"] == "WAIT"


def test_bulkowski_descending_triangle_requires_two_sided_structure_and_breakout():
    result = evaluate_module("bulkowski_descending_triangle", _descending_triangle())
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 79.0
    upward = evaluate_module(
        "bulkowski_descending_triangle",
        _descending_triangle(side="BUY", bulkowski_desc_triangle_breakout_direction="up", bulkowski_desc_triangle_breakout_price=121.0),
    )
    assert upward["view"] == "BUY"
    assert evaluate_module("bulkowski_descending_triangle", _descending_triangle(bulkowski_desc_triangle_top_touches=1))["view"] == "WAIT"


def test_bulkowski_symmetrical_triangle_requires_convergence_crossings_and_duration():
    result = evaluate_module("bulkowski_symmetrical_triangle", _symmetrical_triangle())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 141.0
    assert evaluate_module("bulkowski_symmetrical_triangle", _symmetrical_triangle(bulkowski_sym_triangle_duration_weeks=3.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_symmetrical_triangle", _symmetrical_triangle(bulkowski_sym_triangle_white_space_covered=False))["view"] == "WAIT"


def test_bulkowski_rising_wedge_requires_two_upslopes_five_touches_and_three_weeks():
    result = evaluate_module("bulkowski_rising_wedge", _rising_wedge())
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 79.0
    assert evaluate_module("bulkowski_rising_wedge", _rising_wedge(bulkowski_rising_wedge_upper_touches=1, bulkowski_rising_wedge_lower_touches=2))["view"] == "WAIT"
    assert evaluate_module("bulkowski_rising_wedge", _rising_wedge(bulkowski_rising_wedge_duration_weeks=2.0))["view"] == "WAIT"


def test_bulkowski_triple_bottom_and_top_require_distinct_near_equal_levels_and_confirmation():
    result = evaluate_module("bulkowski_triple_bottom", _triple())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 131.0
    top = evaluate_module(
        "bulkowski_triple_top",
        _triple(
            side="SELL",
            bulkowski_triple_type="top",
            bulkowski_triple_prior_trend="up",
            bulkowski_triple_first=120.0,
            bulkowski_triple_second=119.5,
            bulkowski_triple_third=120.2,
            bulkowski_triple_high=120.5,
            bulkowski_triple_low=100.0,
            bulkowski_triple_confirmation_level=100.0,
            bulkowski_triple_breakout_direction="down",
            bulkowski_triple_breakout_price=99.0,
        ),
    )
    assert top["view"] == "SELL"
    assert evaluate_module("bulkowski_triple_bottom", _triple(bulkowski_triple_level_variation_pct=6.0))["view"] == "WAIT"


def test_bulkowski_three_falling_peaks_and_rising_valleys_require_monotonic_proportional_turns():
    falling = evaluate_module("bulkowski_three_falling_peaks", _three_peaks())
    assert falling["view"] == "SELL"
    assert falling["bulkowski_measure_target"] == 79.0
    rising = evaluate_module("bulkowski_three_rising_valleys", _three_valleys())
    assert rising["view"] == "BUY"
    assert rising["bulkowski_measure_target"] == 151.0
    assert evaluate_module("bulkowski_three_falling_peaks", _three_peaks(bulkowski_three_peaks_second=125.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_three_rising_valleys", _three_valleys(bulkowski_three_valleys_third=85.0))["view"] == "WAIT"


def test_bulkowski_dead_cat_bounce_requires_gap_plunge_bounce_and_second_decline():
    result = evaluate_module("bulkowski_dead_cat_bounce", _dcb())
    assert result["view"] == "SELL"
    assert result["bulkowski_measure_target"] == 54.0
    assert evaluate_module("bulkowski_dead_cat_bounce", _dcb(bulkowski_dcb_plunge_pct=10.0))["view"] == "WAIT"
    assert evaluate_module("bulkowski_dead_cat_bounce", _dcb(bulkowski_dcb_decline_confirmed=False))["view"] == "WAIT"


def test_bulkowski_inverted_dead_cat_bounce_requires_positive_event_retrace_and_recovery():
    result = evaluate_module("bulkowski_inverted_dead_cat_bounce", _idcb())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 124.0
    assert evaluate_module("bulkowski_inverted_dead_cat_bounce", _idcb(bulkowski_idcb_retrace_pct=20.0))["view"] == "WAIT"


def test_bulkowski_earnings_surprise_good_and_bad_use_opposite_trend_and_breakout_rules():
    result = evaluate_module("bulkowski_earnings_surprise_good", _earnings_surprise())
    assert result["view"] == "BUY"
    bad = evaluate_module(
        "bulkowski_earnings_surprise_bad",
        _earnings_surprise(
            side="SELL",
            bulkowski_earnings_surprise_type="bad",
            bulkowski_earnings_prior_trend="down",
            bulkowski_earnings_breakout_direction="down",
            bulkowski_earnings_breakout_price=99.0,
        ),
    )
    assert bad["view"] == "SELL"
    assert evaluate_module("bulkowski_earnings_surprise_good", _earnings_surprise(bulkowski_earnings_announcement_range=4.0))["view"] == "WAIT"


def test_bulkowski_fda_approval_requires_large_move_volume_and_confirmed_breakout():
    result = evaluate_module("bulkowski_fda_drug_approval", _fda())
    assert result["view"] == "BUY"
    down = evaluate_module(
        "bulkowski_fda_drug_approval",
        _fda(side="SELL", bulkowski_fda_breakout_direction="down", bulkowski_fda_breakout_price=99.0),
    )
    assert down["view"] == "SELL"
    assert evaluate_module("bulkowski_fda_drug_approval", _fda(bulkowski_fda_volume_above_average=False))["view"] == "WAIT"


def test_bulkowski_earnings_flag_requires_fast_flagpole_consolidation_and_breakout():
    result = evaluate_module("bulkowski_earnings_flag", _earnings_flag())
    assert result["view"] == "BUY"
    assert result["bulkowski_measure_target"] == 131.0
    assert evaluate_module("bulkowski_earnings_flag", _earnings_flag(bulkowski_earnings_flag_flagpole_days=3.0))["view"] == "WAIT"


def test_bulkowski_same_store_sales_good_and_bad_require_event_range_volume_and_direction():
    good = evaluate_module("bulkowski_same_store_sales_good", _same_store())
    assert good["view"] == "BUY"
    bad = evaluate_module(
        "bulkowski_same_store_sales_bad",
        _same_store(
            side="SELL",
            bulkowski_same_store_type="bad",
            bulkowski_same_store_gap_confirmed=False,
            bulkowski_same_store_breakout_direction="down",
            bulkowski_same_store_breakout_price=99.0,
        ),
    )
    assert bad["view"] == "SELL"
    assert evaluate_module("bulkowski_same_store_sales_good", _same_store(bulkowski_same_store_range=4.0, bulkowski_same_store_gap_confirmed=False))["view"] == "WAIT"


def test_bulkowski_stock_downgrade_and_upgrade_require_large_high_volume_event_reaction():
    downgrade = evaluate_module("bulkowski_stock_downgrade", _broker_event())
    assert downgrade["view"] == "SELL"
    upgrade = evaluate_module(
        "bulkowski_stock_upgrade",
        _broker_event(side="BUY", bulkowski_broker_event_breakout_direction="up", bulkowski_broker_event_breakout_price=111.0),
    )
    assert upgrade["view"] == "BUY"
    assert evaluate_module("bulkowski_stock_upgrade", _broker_event(bulkowski_broker_event_volume_above_average=False))["view"] == "WAIT"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "bulkowski_double_bottom",
        "bulkowski_double_top",
        "bulkowski_flag_breakout",
        "bulkowski_ascending_triangle",
        "bulkowski_falling_wedge",
        "bulkowski_broadening_bottom",
        "bulkowski_broadening_top",
        "bulkowski_right_angled_ascending",
        "bulkowski_right_angled_descending",
        "bulkowski_ascending_broadening_wedge",
        "bulkowski_descending_broadening_wedge",
        "bulkowski_barr_bottom",
        "bulkowski_barr_top",
        "bulkowski_cup_with_handle",
        "bulkowski_inverted_cup_with_handle",
        "bulkowski_diamond_bottom",
        "bulkowski_diamond_top",
        "bulkowski_high_tight_flag",
        "bulkowski_gap",
        "bulkowski_head_shoulders_bottom",
        "bulkowski_complex_head_shoulders_bottom",
        "bulkowski_head_shoulders_top",
        "bulkowski_complex_head_shoulders_top",
        "bulkowski_horn_bottom",
        "bulkowski_horn_top",
        "bulkowski_island_reversal",
        "bulkowski_long_island",
        "bulkowski_measured_move_down",
        "bulkowski_measured_move_up",
        "bulkowski_pennant",
        "bulkowski_pipe_bottom",
        "bulkowski_pipe_top",
        "bulkowski_rectangle_bottom",
        "bulkowski_rectangle_top",
        "bulkowski_rounding_bottom",
        "bulkowski_rounding_top",
        "bulkowski_ascending_scallop",
        "bulkowski_ascending_inverted_scallop",
        "bulkowski_descending_scallop",
        "bulkowski_descending_inverted_scallop",
        "bulkowski_descending_triangle",
        "bulkowski_symmetrical_triangle",
        "bulkowski_rising_wedge",
        "bulkowski_triple_bottom",
        "bulkowski_triple_top",
        "bulkowski_three_falling_peaks",
        "bulkowski_three_rising_valleys",
        "bulkowski_dead_cat_bounce",
        "bulkowski_inverted_dead_cat_bounce",
        "bulkowski_earnings_surprise_good",
        "bulkowski_earnings_surprise_bad",
        "bulkowski_fda_drug_approval",
        "bulkowski_earnings_flag",
        "bulkowski_same_store_sales_good",
        "bulkowski_same_store_sales_bad",
        "bulkowski_stock_downgrade",
        "bulkowski_stock_upgrade",
    ],
)
def test_bulkowski_algorithms_fail_closed_without_observed_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "AAPL", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False
