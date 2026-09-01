from __future__ import annotations

from datetime import datetime, timezone
import math

import pytest

from aegis.research.watcher_algorithms import evaluate_all, evaluate_module
from aegis.research.watcher_feature_engine import enrich_watcher_state
from scripts.watcher_knowledge_engine import _state_from_event


def _history(*, start: float = 0.0, end: float = 4200.0, step: float = 5.0):
    rows = []
    count = int((end - start) / step)
    for index in range(count + 1):
        timestamp = start + index * step
        # A rising path with a small pullback and a fresh upside break.
        phase = index % 40
        mid = 1.1000 + (index * 0.00001) - (0.00012 if phase == 39 else 0.0)
        rows.append({
            "time": timestamp,
            "bid": mid - 0.00002,
            "ask": mid + 0.00002,
            "mid": mid,
            "tick_volume": 10 + (8 if phase >= 35 else 0),
        })
    return rows


def test_quote_features_are_point_in_time_and_do_not_copy_outcomes():
    history = _history(end=1200.0)
    history.append({"time": 9999.0, "bid": 9.0, "ask": 9.1, "mid": 9.05})

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "entry": 1.1120},
        {"time": 1200.0, "bid": 1.1120, "ask": 1.11204, "mid": 1.11202,
         "captured_exit_net_pnl": 99.0, "mfe": 99.0},
        symbol_history=history,
    )

    assert state["quote_history_n"] < len(history)
    assert state["quote_history_last_time"] <= 1200.0
    assert state["quote_history_future_excluded"] is True
    assert state["trend"] == "up"
    assert state["m15_trend"] == "up"
    assert state["ema_fast"] > state["ema_slow"]
    assert "captured_exit_net_pnl" not in state
    assert "mfe" not in state
    assert state["feature_provenance"]["volume"] == "tick_activity_proxy"


def test_quote_history_enables_each_data_supported_perspective_without_fabrication():
    history = _history()
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "entry": 1.1420},
        {"time": 4200.0, "bid": 1.1420, "ask": 1.14204, "mid": 1.14202, "tick_volume": 25},
        symbol_history=history,
        universe_history={"EURUSD": history, "GBPUSD": [
            {**item, "mid": item["mid"] * 0.9, "bid": item["bid"] * 0.9,
             "ask": item["ask"] * 0.9}
            for item in history
        ]},
    )

    results = {item["algorithm_id"]: item for item in evaluate_all(state)}
    unsupported = {
        "narang_alpha_rotation", "narang_run_frequency_tradeoff", "davey_euro_night_strategy", "davey_euro_day_strategy", "davey_three_bar_baseline", "chan_hft_quote_data_requirements", "chan_bulk_volume_order_flow",
        "validation_integrity", "news_event_risk", "trade_management", "pyramiding", "market_profile", "adverse_selection", "time_stop", "intermarket_analysis", "noise_filter", "tail_risk", "event_arbitrage", "spread_scalping", "latency_arbitrage", "rebate_capture", "market_impact_symmetry", "dejong_roll_spread_estimator", "dejong_spread_decomposition", "dejong_duration_weighted_spread", "al_brooks_high_low_count", "al_brooks_wedge", "al_brooks_failed_failure", "al_brooks_spike_channel", "al_brooks_double_flag", "al_brooks_range_location",
        "pivot_levels", "fibonacci_retracement", "vwap_context", "obv_volume",
        "volman_tipping_point_exit", "volman_unfavorable_path_filter", "volman_pullback_quality",
        "elliott_wave", "harmonic_patterns", "gann_levels", "cointegration_pairs",
        "kalman_filter", "seasonality_context", "order_book_imbalance", "aldridge_triangular_arbitrage", "aldridge_uip_arbitrage", "aldridge_index_composition_arbitrage", "aldridge_volatility_curve_arbitrage", "aldridge_futures_basis_arbitrage", "aldridge_futures_etf_arbitrage", "aldridge_dual_class_arbitrage", "aldridge_risk_arbitrage", "aronson_objective_rule_definition", "aronson_reality_check", "aronson_practical_significance", "aronson_detrended_rule_return", "vpa_trend_effort_confirmation",
            "volume_profile_context", "volume_open_interest", "murphy_percentage_retracement", "murphy_speed_resistance_lines", "fundamental_macro", "sentiment_positioning", "edwards_magee_dow_confirmation", "edwards_magee_basing_points_stop", "edwards_magee_breakout_confirmation", "edwards_magee_climactic_volume_stop", "edwards_magee_defensive_exit", "edwards_magee_one_day_reversal", "edwards_magee_selling_climax", "edwards_magee_trendline_penetration", "edwards_magee_broadening_breakout", "edwards_magee_key_reversal_day", "edwards_magee_spike_reversal", "edwards_magee_runaway_day",
        "time_series_forecasting", "machine_learning_signal", "portfolio_allocation",
        "bollinger_pair_mean_reversion",
        "candlestick_patterns",
        "cross_sectional_momentum", "meta_labeling",
        "market_making_inventory", "forecast_combination", "triple_barrier_label",
        "purged_walk_forward", "deprado_sample_uniqueness", "deprado_sequential_bootstrap", "deprado_combinatorial_purged_cv", "deprado_probabilistic_sharpe", "deprado_deflated_sharpe", "deprado_strategy_failure_probability", "deprado_cusum_filter", "deprado_entropy", "deprado_tick_imbalance_bar", "deprado_volume_imbalance_bar", "deprado_dollar_imbalance_bar", "deprado_tick_runs_bar", "deprado_volume_runs_bar", "deprado_dollar_runs_bar", "deprado_tick_bar", "deprado_volume_bar", "deprado_dollar_bar", "fractional_differentiation",
        "risk_parity_allocation", "vwap_execution", "twap_execution", "participation_execution",
        "carry_rule", "ab_system", "wyckoff_spring_upthrust",
        "al_brooks_second_entry", "kangaroo_tail", "relative_strength",
        "point_and_figure", "cycle_analysis", "factor_momentum", "fundamental_law",
        "market_impact", "garch_volatility", "hawkes_order_flow",
        "volatility_targeting", "position_sizing",
            "random_forest_signal", "bayesian_pairs", "pca_eigenportfolio", "bet_sizing",
            "feature_importance_stability", "stochastic_volatility",
            "ponsi_level_bounce", "ponsi_intraday_breakout", "ponsi_pennant_continuation", "ponsi_multitimeframe_pullback", "ponsi_fibonacci_trend_reentry", "ponsi_price_action_level", "ponsi_interest_rate_edge",
            "ponsi_round_number_bounce", "ponsi_boomerang_fade", "anderson_high_volume_runner",
            "nison_three_line_break", "nison_renko_trend", "nison_kagi_yang_yin", "nison_disparity_reversal", "nison_hammer_hanging_man", "nison_shooting_star", "nison_doji_confirmation", "nison_two_line_reversal", "nison_three_line_star", "nison_spring_upthrust", "nison_last_engulfing", "nison_window_context", "nison_three_windows", "nison_record_sessions", "nison_harami", "nison_harami_cross", "nison_two_black_gapping", "nison_gapping_doji", "nison_extra_line_break_confirmation", "nison_three_line_neck", "nison_kagi_double_window", "nison_kagi_tweezers", "nison_kagi_three_buddha", "aldridge_order_flow_autocorrelation", "aldridge_trade_aggressiveness", "aldridge_bid_ask_bounce_filter", "aldridge_quote_duration", "aldridge_trade_direction_uncertainty", "aldridge_quote_matching", "anderson_conditional_bracket",
            "price_in_time_ntz_breakout", "price_in_time_trade_management_models",
            "price_in_time_opening_price", "price_in_time_session_filter", "price_in_time_anomaly_filter",
            "thomas_push_pull_10xroi", "thomas_ma_momentum_filter",
            "thomas_break_even_after_pullback", "thomas_fixed_r_target",
            "thomas_breakout_context", "thomas_parabolic_exhaustion_exit",
            "clenow_dual_ema_breakout", "clenow_countertrend_pullback", "clenow_term_structure_carry",
            "clenow_core_breakout", "clenow_core_exit", "clenow_volatility_trailing_stop", "clenow_style_diversification",
            "silvani_retail_contrarian", "silvani_rolling_pivot_filter", "silvani_friday_stop_run",
            "aziz_abcd_pattern", "aziz_bull_flag_momentum", "aziz_red_to_green", "aziz_bhod",
            "aziz_bottom_reversal", "aziz_top_reversal", "aziz_moving_average_trend", "aziz_vwap_control", "aziz_stock_in_play_scanner",
            "aziz_premarket_gapper_scanner", "aziz_relative_volume_independence", "aziz_reversal_market_context",
            "aziz_opening_range_breakout",
            "grail_time_anchor_breakout", "grail_bracket_lifecycle", "grail_regime_failure_warning",
            "chan_linear_mean_reversion", "chan_kalman_mean_reversion", "chan_exit_policy",
            "chan_cross_sectional_mean_reversion", "chan_time_series_momentum",
            "chan_alexander_filter",
            "chan_opening_gap_momentum", "chan_news_drift", "chan_stop_order_momentum",
            "chan_order_flow_momentum", "chan_bid_ask_imbalance", "chan_ratio_trade",
            "chan_ticking_quote_matching", "chan_leveraged_rebalance_momentum",
            "chan_half_kelly_cap", "chan_adf_mean_reversion", "chan_hurst_stationarity",
            "chan_variance_ratio_stationarity", "chan_cadf_cointegration", "chan_johansen_cointegration",
            "ultimate_price_rejection", "ultimate_ema_reversal", "ultimate_head_shoulders",
            "ultimate_double_triple_test", "ultimate_vpa_extreme", "ultimate_mtf_confirmation",
            "ultimate_mw_bat_pattern", "ultimate_correlation_lag",
            "ultimate_abandoned_baby_ema5", "ultimate_triangle_pattern",
            "ultimate_cascade_exhaustion", "ultimate_sandwich_pattern", "ultimate_fractal_pattern",
            "ultimate_local_extrema_timing", "ultimate_sentiment_change", "ultimate_high_performance_confluence",
            "ultimate_news_sr_reaction",
            "pf_three_box_catapult", "pf_double_top_bottom", "pf_triple_top_bottom", "pf_pole_reversal", "pf_trendline_signal_confirmation", "pf_opposing_poles", "pf_45_degree_trendline", "pf_early_fulcrum_entry", "pf_trend_aligned_signal", "pf_vertical_count_target", "pf_horizontal_count_target", "pf_shakeout_filter", "pf_trap_reversal", "pf_one_box_semicatapult", "pf_one_box_fulcrum", "damir_fib_confluence_reversal", "damir_confirmed_trend_change", "damir_value_rejection_sequence", "damir_value_location_guideline", "damir_value_health_warning",
            "gann_reverse_signal_day",
            "gann_higher_tops_bottoms", "gann_halfway_point",
            "gann_repeated_level_reversal", "gann_secondary_reaction",
            "gann_fourth_level_reversal",
            "brooks_breakout_pullback_test", "brooks_barbwire_filter", "brooks_breakout_mode", "brooks_failed_breakout_reversal", "brooks_measured_move_projection", "brooks_shrinking_stairs", "brooks_micro_measuring_gap", "brooks_always_in_mode", "brooks_trader_equation", "brooks_two_reasons_entry", "brooks_timeframe_discipline", "elder_triple_screen",
            "elder_impulse_censorship", "elder_force_index_pullback", "elder_safezone_stop",
            "bulkowski_double_bottom", "bulkowski_double_top", "bulkowski_flag_breakout",
            "bulkowski_ascending_triangle", "bulkowski_falling_wedge",
            "bulkowski_broadening_bottom", "bulkowski_broadening_top",
            "bulkowski_right_angled_ascending", "bulkowski_right_angled_descending",
            "bulkowski_ascending_broadening_wedge", "bulkowski_descending_broadening_wedge",
            "bulkowski_barr_bottom", "bulkowski_barr_top", "bulkowski_cup_with_handle",
            "bulkowski_inverted_cup_with_handle", "bulkowski_diamond_bottom", "bulkowski_diamond_top",
            "bulkowski_high_tight_flag", "bulkowski_gap", "bulkowski_head_shoulders_bottom",
            "bulkowski_complex_head_shoulders_bottom", "bulkowski_head_shoulders_top",
            "bulkowski_complex_head_shoulders_top", "bulkowski_horn_bottom", "bulkowski_horn_top",
            "bulkowski_island_reversal", "bulkowski_long_island", "bulkowski_measured_move_down",
            "bulkowski_measured_move_up",
            "bulkowski_pennant", "bulkowski_pipe_bottom", "bulkowski_pipe_top",
            "bulkowski_rectangle_bottom", "bulkowski_rectangle_top", "bulkowski_rounding_bottom",
            "bulkowski_rounding_top", "bulkowski_ascending_scallop",
            "bulkowski_ascending_inverted_scallop", "bulkowski_descending_scallop",
            "bulkowski_descending_inverted_scallop",
            "bulkowski_descending_triangle", "bulkowski_symmetrical_triangle",
            "bulkowski_rising_wedge", "bulkowski_triple_bottom", "bulkowski_triple_top",
            "bulkowski_three_falling_peaks", "bulkowski_three_rising_valleys",
            "bulkowski_dead_cat_bounce", "bulkowski_inverted_dead_cat_bounce",
            "bulkowski_earnings_surprise_good", "bulkowski_earnings_surprise_bad",
            "bulkowski_fda_drug_approval", "bulkowski_earnings_flag",
            "bulkowski_same_store_sales_good", "bulkowski_same_store_sales_bad",
            "bulkowski_stock_downgrade", "bulkowski_stock_upgrade",
            "carter_scalper_alert", "carter_tick_extreme_fade",
            "carter_anchor_squeeze", "carter_brick_reversal", "carter_holp_lohp",
            "carter_end_of_day_fade", "carter_ema_propulsion",
            "carter_opening_gap_fade", "carter_pivot_play", "carter_atr_mean_reversion",
            "carter_tick_flow_follow", "carter_352_play", "carter_multisetup_confirmation",
            "carter_tick_price_divergence", "carter_tick_noise_regime",
            "schwager_bull_bear_trap", "schwager_false_trend_breakout", "schwager_filled_gap_failure", "schwager_restrictive_reversal_day",
            "schwager_spike_extreme_failure", "schwager_wide_range_day_failure", "schwager_counter_flag_failure",
            "schwager_minor_reaction_reentry", "schwager_long_ma_reaction", "schwager_oscillator_price_confirmation",
            "schwager_trend_adjusted_oscillator", "schwager_island_reversal_validation", "schwager_equity_deterioration_warning",
            "schwager_record_extreme_continuation", "schwager_narrow_consolidation_bias", "schwager_news_non_followthrough_reversal",
            "grimes_pullback_quality", "grimes_three_push_exhaustion",
            "developing_hft_flow_exhaustion", "developing_hft_liquidity_depth", "developing_hft_volatility_clustering", "developing_hft_stat_arb_dislocation", "developing_hft_news_impact", "harris_immediacy_cost", "harris_limit_order_regret", "harris_stop_order_momentum", "murphy_inverse_relationship", "murphy_lead_lag_confirmation", "murphy_relationship_regime", "murphy_sector_rotation", "schwager_ma_turn_filter", "schwager_range_breakout_confirmation", "schwager_range_participation_filter", "cartea_regime_rebate_safety", "cartea_inventory_skew", "cartea_state_intensity", "cartea_quote_freshness_guard",
            "aldridge_pair_dislocation", "dalton_trend_day_integrity", "dalton_auction_point_retest",
            "dalton_day_structure", "dalton_failed_range_extension", "dalton_single_print_retest",
                "johnson_implementation_shortfall", "johnson_adaptive_shortfall", "johnson_price_inline", "johnson_liquidity_seeking", "johnson_order_difficulty",
                "elliott_impulse_rules", "elliott_wave_three_extension", "elliott_diagonal_rules",
                "elliott_corrective_structure", "elliott_alternation",
                "price_in_time_ntz_projection", "price_in_time_range_cycle", "price_in_time_pending_order",
            "process_discipline_control", "oreste_qpl_interaction", "oreste_entelechy_confluence", "oreste_time_price_confluence", "oreste_volatility_scaled_risk", "quantum_finance_scenario_stress", "douglas_probability_edge", "tendler_process_error", "drakoln_plan_integrity", "narang_horizon_specification", "narang_conditional_alpha", "narang_linear_alpha_blend", "narang_cost_hurdle", "narang_liquidity_impact", "narang_forecast_bucket_monotonicity", "narang_time_decay", "narang_parameter_robustness", "narang_portfolio_value_add", "narang_risk_monitoring", "narang_regime_change_warning", "narang_exogenous_shock_filter", "narang_contagion_exposure", "brown_ma_stack_filter", "brown_band_signal_filter", "brown_structural_stop_buffer", "brown_qmp_filter_trigger", "brown_macd_zero_filter", "brown_qqe_filter", "brown_multi_ma_alignment", "brown_trendline_break_reentry", "brown_divergence_type_filter", "brown_bollinger_trade_management", "tharp_narrow_range_breakout", "tharp_failed_test_reversal", "tharp_mae_winner_band", "tharp_r_multiple_expectancy", "tharp_market_selection", "pyramiding_risk_lock", "grinold_information_horizon", "grinold_trade_utility", "grinold_fundamental_law", "grinold_alpha_scaling", "grinold_turnover_frontier", "clenow_regime_filter", "clenow_atr_impact_sizing", "clenow_currency_exposure",
            "ponsi_ema_trend_technique", "ponsi_squeeze_play",
        "pole_spread_reversion", "pole_popcorn_reversion", "pole_turning_point_event", "pole_event_pair_selection", "pole_staged_spread_entries", "pole_forecast_monitoring", "pole_cuscore_change_point", "pole_75_percent_reversion", "pole_multi_step_reversion", "pole_spread_margin", "pole_evolutionary_operation", "pole_catastrophe_entry", "pole_catastrophe_exit", "velu_omnibus_rule", "velu_fair_value_residual", "velu_sign_magnitude_decomposition", "velu_alexander_filter", "velu_sma_rule", "velu_ewa_rule", "velu_bwma_bollinger_rule", "velu_moving_average_oscillator", "velu_rsi_reversal", "velu_kernel_pattern", "velu_characteristic_time", "velu_intraday_profile", "velu_volume_return_filter", "velu_square_root_cost_hurdle", "velu_distance_pairs", "gray_vogel_path_momentum", "gray_vogel_rebalance_tradeoff", "gray_vogel_lookback_regime", "gray_vogel_lottery_avoidance", "gray_vogel_seasonality_timing", "gray_vogel_52_week_high", "gray_vogel_absolute_strength", "gray_vogel_momentum_stop_loss", "gray_vogel_time_series_overlay", "gray_vogel_fundamental_momentum", "carver_forecast_cap", "carver_position_inertia", "carver_speed_limit",
                "velu_microstructure_noise_sampling",
                "lien_intraday_range_reversal", "lien_medium_term_breakout",
                "lien_double_zero_fade", "lien_wait_for_real_deal", "lien_fader",
                "lien_filter_false_breakout", "lien_channel_breakout", "lien_perfect_order",
                "lien_short_term_momentum_20_100", "lien_proactive_news", "lien_reactive_news",
                "lien_combined_news", "lien_high_probability_turn", "lien_two_day_low_stop", "lien_two_stage_profit_management",
                "link_ten_period_breakout", "link_trendline_buffer_breakout",
                "link_opening_range_breakout_30m", "link_reversal_day",
                "link_double_top_bottom_reversal", "link_pain_reversal",
                "link_key_number_reversal",
                "link_multi_timeframe_confirmation", "link_news_reaction_fade", "link_stochastic_wave_entry", "link_stochastic_cross_entry", "link_stochastic_extreme_retest", "link_rsi_fifty_line_entry", "link_rsi_extreme_exit", "link_rsi_pattern_break", "link_macd_signal_line_entry", "link_adx_regime_switch", "link_stochastic_failed_move", "link_trend_retracement_entry", "link_atr_risk_feasibility", "link_stop_discipline",
            }
    assert all(
        results[name]["applicability"] != "MISSING_DATA"
        for name in results
        if name not in unsupported
    )
    assert results["volume_price"]["warnings"]
    assert "tick_activity_proxy" in results["volume_price"]["warnings"][0]
    for name in (
        "ten_period_sd_breakout", "triple_screen", "volume_spread_analysis", "initial_balance_profile",
        "force_index", "elder_impulse", "realized_volatility", "ewmac_trend_following",
        "ttm_squeeze", "turtle_breakout",
    ):
        assert results[name]["applicability"] == "APPLICABLE"
    assert results["price_action_candles"]["view"] == "SELL"
    assert results["news_event_risk"]["applicability"] == "MISSING_DATA"
    assert results["validation_integrity"]["applicability"] == "MISSING_DATA"
    assert results["trade_management"]["applicability"] == "MISSING_DATA"
    assert all(item["execution_authority"] is False for item in results.values())


def test_quote_history_derives_rate_of_change_and_parabolic_sar_as_proxies():
    history = _quote_path([1.1000 + index * 0.0001 for index in range(40)], step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 39.0, "bid": 1.10388, "ask": 1.10392, "mid": 1.10390},
        symbol_history=history,
    )

    assert state["roc_1s"] > 0
    assert state["roc_5s"] > 0
    assert state["roc_state"] == "positive"
    assert state["parabolic_sar"] < state["mid"]


def test_quote_history_exposes_point_in_time_event_times_for_velu_duration_analysis():
    history = _quote_path([1.1000 + index * 0.0001 for index in range(12)], step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 11.0, "bid": 1.10108, "ask": 1.10112, "mid": 1.10110},
        symbol_history=history,
    )

    result = evaluate_module("velu_duration_intensity", state)
    assert len(state["velu_event_times"]) >= 7
    assert state["feature_provenance"]["velu_duration_intensity"] == "point_in_time_quote_history"
    assert result["applicability"] == "APPLICABLE"
    assert result["execution_authority"] is False


def _minute_bars(values, *, start=1_756_041_600.0, tick_volume=10.0):
    rows = []
    for index, pair in enumerate(values):
        bar_start = start + index * 60.0
        for offset, mid in enumerate(pair):
            rows.append({
                "time": bar_start + (5.0 if offset == 0 else 45.0),
                "bid": mid - 0.00002,
                "ask": mid + 0.00002,
                "mid": mid,
                "tick_volume": tick_volume,
            })
    return rows


def test_aziz_abcd_is_derived_from_completed_causal_quote_bars():
    history = _minute_bars([
        (1.1000, 1.1005),
        (1.1005, 1.1020),
        (1.1020, 1.1010),
        (1.1010, 1.1015),
    ])
    now = 1_756_041_600.0 + 4.0 * 60.0 + 10.0
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": now, "bid": 1.10128, "ask": 1.10132, "mid": 1.10130},
        symbol_history=history,
    )

    assert state["aziz_abcd_point_b_confirmed"] is True
    assert state["aziz_abcd_c_support_holds"] is True
    assert evaluate_module("aziz_abcd_pattern", state)["view"] == "BUY"


def test_aziz_bull_flag_requires_a_causal_break_and_observed_tick_volume():
    history = _minute_bars([
        (1.1000, 1.1010),
        (1.1010, 1.1025),
        (1.1025, 1.1040),
        (1.1040, 1.1042),
        (1.1042, 1.1043),
    ])
    now = 1_756_041_600.0 + 5.0 * 60.0 + 10.0
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {
            "time": now,
            "bid": 1.10458,
            "ask": 1.10462,
            "mid": 1.10460,
            "tick_volume": 30.0,
        },
        symbol_history=history,
    )

    assert state["aziz_bull_flag_breakout_confirmation"] is True
    assert state["aziz_bull_flag_volume_confirmation"] is True
    assert evaluate_module("aziz_bull_flag_momentum", state)["view"] == "BUY"
    assert state["sar_state"] == "bullish"
    assert state["sar_direction"] == "up"
    assert state["feature_provenance"]["rate_of_change"] == "point_in_time_quote_return_proxy"
    assert state["feature_provenance"]["parabolic_sar"] == "quote_mid_proxy"


def test_pivot_context_uses_only_the_immediately_previous_session():
    from datetime import datetime, timezone

    def stamp(hour: int, minute: int = 0) -> float:
        return datetime(2026, 8, 29, hour, minute, tzinfo=timezone.utc).timestamp()

    history = [
        {"time": stamp(0), "bid": 1.1000, "ask": 1.1002, "mid": 1.1001},
        {"time": stamp(1), "bid": 1.1030, "ask": 1.1032, "mid": 1.1031},
        {"time": stamp(2), "bid": 1.0990, "ask": 1.0992, "mid": 1.0991},
        {"time": stamp(7), "bid": 1.2000, "ask": 1.2002, "mid": 1.2001},
        {"time": stamp(8), "bid": 1.2020, "ask": 1.2022, "mid": 1.2021},
        {"time": stamp(9), "bid": 1.1980, "ask": 1.1982, "mid": 1.1981},
        {"time": stamp(10), "bid": 1.2000, "ask": 1.2002, "mid": 1.2001},
        {"time": stamp(11, 59), "bid": 1.2010, "ask": 1.2012, "mid": 1.2011},
    ]
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": stamp(13), "bid": 1.2018, "ask": 1.2020, "mid": 1.2019},
        symbol_history=history,
    )

    assert state["session"] == "new_york"
    assert state["previous_session_high"] == 1.2021
    assert state["previous_session_low"] == 1.1981
    assert state["previous_session_close"] == 1.2011
    assert state["feature_provenance"]["pivot"] == "observed_prior_session_quote_proxy"


def test_quote_history_does_not_infer_roc_or_sar_from_insufficient_observations():
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 2.0, "bid": 1.1001, "ask": 1.10014, "mid": 1.10012},
        symbol_history=_quote_path([1.1000, 1.10005, 1.1001], step=1.0),
    )

    assert "roc_5s" not in state
    assert "parabolic_sar" not in state


def test_quote_history_does_not_turn_generic_tick_activity_into_real_volume():
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "SELL"},
        {"time": 60.0, "bid": 1.1000, "ask": 1.10004, "mid": 1.10002},
        symbol_history=[
            {"time": 0.0, "bid": 1.1000, "ask": 1.10004, "mid": 1.10002},
            {"time": 30.0, "bid": 1.0998, "ask": 1.09984, "mid": 1.09982},
        ],
    )

    assert state["volume_context"]["source"] == "tick_activity_proxy"
    assert state["volume_context"]["is_real_volume"] is False
    assert "real_volume" not in state


def test_quote_proxies_are_explicitly_non_validated_for_volume_profile_and_pairs():
    history = _history()
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 4200.0, "bid": 1.1420, "ask": 1.14204, "mid": 1.14202},
        symbol_history=history,
        universe_history={"EURUSD": history, "GBPUSD": history},
    )
    results = {item["algorithm_id"]: item for item in evaluate_all(state)}

    assert "tick_activity_proxy" in results["volume_price"]["warnings"][0]
    assert "tick_price_profile_proxy" in results["market_profile_auction"]["warnings"][0]
    assert results["statistical_arbitrage"]["view"] == "WAIT"
    assert "not validated" in results["statistical_arbitrage"]["reasons"][0]


def test_live_watcher_event_adapter_uses_only_prior_quote_history():
    history = _history(end=600.0)
    history.append({"time": 601.0, "bid": 9.0, "ask": 9.1})
    event = {
        "event": "candidate_blocked",
        "timestamp": 600.0,
        "symbol": "EURUSD",
        "side": "buy",
        "bid": 1.1060,
        "ask": 1.10604,
        "future_quotes": [{"time": 601.0, "bid": 9.0, "ask": 9.1}],
        "mfe": 99.0,
    }

    state = _state_from_event(event, symbol_history=history)

    assert state["quote_history_last_time"] == 600.0
    assert state["quote_history_future_excluded"] is True
    assert state["quote_history_last_time"] < 601.0
    assert "future_quotes" not in state
    assert "mfe" not in state


def test_nested_future_and_outcome_payloads_are_removed_from_state():
    state = enrich_watcher_state({
        "symbol": "EURUSD",
        "side": "BUY",
        "context": {"trend": "up", "mfe": 4.0, "future_quotes": [{"mid": 9.0}]},
    })

    assert state["context"] == {"trend": "up"}


def test_malformed_optional_history_or_provenance_fails_closed_without_crashing():
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "feature_provenance": "invalid"},
        symbol_history=None,
    )

    assert state["symbol"] == "EURUSD"
    assert "feature_provenance" not in state


def test_malformed_trend_context_fails_closed_without_crashing():
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "m15_trend": {"bad": "value"}},
        {"time": 24.0, "bid": 1.1000, "ask": 1.10004, "mid": 1.10002},
        symbol_history=_quote_path([1.1000 + index * 0.0001 for index in range(25)], step=1.0),
    )

    assert isinstance(state, dict)
    assert state["quote_history_future_excluded"] is False


def test_insufficient_history_does_not_infer_chart_or_higher_timeframe_state():
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 100.0, "bid": 1.1000, "ask": 1.10004},
        symbol_history=[{"time": 100.0, "bid": 1.1000, "ask": 1.10004}],
    )
    results = {item["algorithm_id"]: item for item in evaluate_all(state)}

    assert "trend" not in state
    assert "chart_pattern" not in state
    assert results["higher_timeframe_alignment"]["applicability"] == "MISSING_DATA"
    assert results["risk_reward_geometry"]["applicability"] == "MISSING_DATA"
    assert results["opening_range"]["applicability"] == "MISSING_DATA"


def _quote_path(values, *, start=0.0, step=1.0, spread=0.00004):
    return [
        {
            "time": start + index * step,
            "bid": value - spread / 2.0,
            "ask": value + spread / 2.0,
            "mid": value,
        }
        for index, value in enumerate(values)
    ]


def test_quote_history_derives_breakout_retest_pullback_and_sweep_without_future_data():
    # Build an old range, break above it, then retest/reclaim the old ceiling.
    history = _quote_path([
        1.1000, 1.1002, 1.1001, 1.1003, 1.1002, 1.1003,
        1.1008, 1.10035, 1.1007, 1.10034, 1.10095,
    ])
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["breakout_state"] in {"breakout_up_confirmed", "breakout_up_retest"}
    assert state["retest"] == "retest_confirmed"
    assert state["pullback"] == "bullish_pullback_reclaimed"
    assert state["level_role"] == "resistance turned support"
    assert state["quote_history_future_excluded"] is False

    sweep_history = _quote_path([
        1.1000, 1.1002, 1.1001, 1.1003, 1.1002,
        1.1007, 1.10025, 1.10025,
    ])
    sweep_state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "SELL"},
        sweep_history[-1],
        symbol_history=sweep_history[:-1],
    )
    assert sweep_state["liquidity_sweep"] == "buy_side_sweep_rejected"
    assert sweep_state["sweep_state"] == "buy_side_sweep_rejected"
    assert sweep_state["level_role"] == "resistance_rejected"


def test_quote_history_derives_exhaustion_and_does_not_call_arbitrary_range_an_opening_range():
    history = _quote_path([
        1.1000, 1.1002, 1.1005, 1.1009, 1.1012,
        1.10135, 1.10140, 1.10142,
    ])
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["exhaustion"] == "bullish_momentum_exhaustion"
    assert state["momentum_decay"] == "decaying"
    # This timestamp is not in a completed session-opening window, and an
    # arbitrary recent range must not be mislabeled as an opening range.
    assert "opening_range_state" not in state


def test_completed_session_opening_range_is_derived_from_that_window_only():
    # 12:00 UTC on an arbitrary day: the first 30 minutes form the NY opening
    # range; later quotes break above it.
    session_start = datetime(2026, 8, 28, 12, tzinfo=timezone.utc).timestamp()
    opening = _quote_path(
        [1.1000, 1.1003, 1.1001, 1.1004],
        start=session_start,
        step=600.0,
    )
    later = _quote_path(
        [1.1005, 1.1008],
        start=session_start + 2400.0,
        step=600.0,
    )
    history = opening + later[:-1]
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        later[-1],
        symbol_history=history,
    )

    assert state["opening_range_state"] == "complete"
    assert state["opening_range_breakout"] == "breakout_up"
    assert state["opening_drive"] == "up"
    assert state["initial_balance"]["high"] == 1.1004
    assert state["initial_balance"]["low"] == 1.1000


def test_quote_history_derives_indicator_context_with_explicit_proxy_provenance():
    values = [1.1000 + (index * 0.00003) + (0.00008 if index % 7 == 0 else 0.0) for index in range(45)]
    history = _quote_path(values, step=5.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["bollinger_window_n"] == 20
    assert state["bollinger_upper"] > state["bollinger_middle"] > state["bollinger_lower"]
    assert state["macd_state"] == "bullish"
    assert state["macd_histogram"] > 0
    assert state["atr_14"] > 0
    assert state["feature_provenance"]["bollinger"] == "quote_observation_proxy"
    assert state["feature_provenance"]["macd"] == "quote_observation_proxy"
    assert state["feature_provenance"]["atr"] == "quote_observation_proxy"


def test_quote_history_derives_range_retracement_context_without_calling_it_a_swing():
    history = _history(end=4200.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["fib_retracement_zone"] in {"0.236", "0.382", "0.500", "0.618", "0.786", "range_edge"}
    assert state["fib_data_provenance"] == "observed_range_retracement_proxy"
    assert state["feature_provenance"]["fibonacci"] == "observed_range_retracement_proxy"


def test_pivot_context_requires_an_observed_prior_session_window():
    # 07:00-12:00 UTC is the immediately preceding London session for the
    # 13:00 UTC New York observation.
    prior = _quote_path([1.1000, 1.1010, 1.0990, 1.1005], start=25200.0, step=3600.0)
    current = _quote_path([1.1010], start=46800.0, step=1.0)[0]
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        current,
        symbol_history=prior,
    )

    assert state["pivot"] == (1.1010 + 1.0990 + 1.1005) / 3.0
    assert state["pivot_relation"] == "above_pivot"
    assert state["pivot_data_provenance"] == "observed_prior_session_quote_proxy"


def test_quote_history_exposes_stochastic_state_separately_from_rsi():
    history = _history(end=4200.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["stochastic_k"] == state["stochastic"]
    assert state["stochastic_state"] in {"overbought", "oversold", "neutral"}


def test_quote_history_derives_source_specific_link_oscillator_inputs():
    history = _history(end=4200.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert 0.0 <= state["link_stoch_fast"] <= 100.0
    assert 0.0 <= state["link_stoch_slow"] <= 100.0
    assert state["link_stoch_data_provenance"] == "observed_quote_derived_oscillator"
    assert state["link_rsi_data_provenance"] == "observed_quote_derived_oscillator"
    assert state["link_rsi_fifty_line"] == 50.0
    assert state["link_rsi_oversold"] == 30.0
    assert state["link_rsi_overbought"] == 70.0
    assert state["link_rsi_extreme_data_provenance"] == "observed_quote_derived_oscillator"
    assert isinstance(state["link_rsi_stall_confirmed"], bool)
    assert "link_macd_line" in state
    assert "link_macd_signal_line" in state
    assert state["link_macd_data_provenance"] == "observed_quote_derived_oscillator"
    assert isinstance(state["link_stoch_slow_bottomed"], bool)
    stochastic = evaluate_module("link_stochastic_wave_entry", state)
    stochastic_cross = evaluate_module("link_stochastic_cross_entry", state)
    rsi = evaluate_module("link_rsi_fifty_line_entry", state)
    rsi_extreme = evaluate_module("link_rsi_extreme_exit", state)
    macd = evaluate_module("link_macd_signal_line_entry", state)
    assert stochastic["applicability"] == "APPLICABLE"
    assert stochastic_cross["applicability"] == "APPLICABLE"
    assert rsi["applicability"] == "APPLICABLE"
    assert rsi_extreme["applicability"] == "APPLICABLE"
    assert macd["applicability"] == "APPLICABLE"
    assert state["quote_history_future_excluded"] is False


def test_quote_history_derives_additional_indicator_context_with_proxy_labels():
    history = _history(end=4200.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    for key in ("adx", "di_plus", "di_minus", "keltner_middle", "keltner_upper", "keltner_lower", "tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b", "cci", "williams_r"):
        assert key in state
    assert state["feature_provenance"]["adx"] == "quote_observation_proxy"
    assert state["feature_provenance"]["keltner"] == "quote_observation_proxy"
    assert state["feature_provenance"]["ichimoku"] == "quote_observation_proxy"
    assert state["feature_provenance"]["cci"] == "quote_observation_proxy"
    assert state["feature_provenance"]["williams"] == "quote_observation_proxy"


def test_tick_volume_perspectives_are_present_but_explicitly_not_real_volume():
    history = _history(end=4200.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert "vwap_proxy" in state
    assert "obv_proxy" in state
    assert state["vwap_data_provenance"] == "tick_volume_proxy"
    assert state["obv_data_provenance"] == "tick_volume_proxy"
    assert state["feature_provenance"]["vwap"] == "tick_volume_proxy"
    assert state["feature_provenance"]["obv"] == "tick_volume_proxy"


def test_quote_bar_shape_distinguishes_closed_hammer_from_generic_direction():
    values = [1.1000] * 30 + [1.1000, 1.0980, 1.1005] + [1.1005] * 13
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["closed_bar"] is True
    assert state["candle_pattern"] == "bullish_hammer"
    assert state["candle_body"] > 0
    assert state["candle_lower_wick"] > state["candle_body"] * 2
    assert state["candle_data_provenance"] == "completed_quote_bar_proxy"


def test_active_quote_bar_is_not_presented_as_a_closed_candlestick():
    values = [1.1000] * 15 + [1.1000, 1.0980, 1.1005]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state.get("candlestick_pattern") != "hammer"
    assert state.get("candle_pattern") == "doji"


def test_quote_history_detects_a_completed_double_top_without_future_data():
    values = [
        1.1000, 1.1010, 1.1002, 1.1011, 1.1003, 1.1006,
        1.1008, 1.1010, 1.1000, 1.0993,
    ]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "SELL"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["chart_pattern"] == "double_top"
    assert state["pattern_confirmation"] == "rejection_observed"
    assert state["pattern_direction"] == "down"
    assert state["pattern_detection_provenance"] == "quote_extrema_proxy"


def test_quote_history_detects_an_ascending_triangle_before_breakout():
    values = [
        1.1000, 1.1010, 1.1000, 1.10105, 1.1003, 1.10102,
        1.1006, 1.1009,
    ]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["chart_pattern"] == "ascending_triangle"
    assert state["pattern_confirmation"] == "converging_range"
    assert state["pattern_direction"] == "up"


def test_quote_history_detects_head_and_shoulders_structure():
    values = [1.1000, 1.1010, 1.1002, 1.1020, 1.1003, 1.1010, 1.1005, 1.0990]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "SELL"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["chart_pattern"] == "head_and_shoulders"
    assert state["pattern_direction"] == "down"
    assert state["pattern_confirmation"] == "right_shoulder_observed"


def test_quote_history_derives_explicit_breakout_volatility_and_ewma_inputs():
    values = [1.1000 + (index % 5) * 0.00002 for index in range(80)]
    values[-1] = 1.1020
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["breakout_lookback"] == 10
    assert state["breakout_high_10"] < state["current_price"]
    assert state["breakout_low_10"] < state["breakout_high_10"]
    assert state["breakout_sd"] > 0
    assert state["breakout_buffer_sd"] == 0.5
    assert state["turtle_entry_lookback"] == 20
    assert state["turtle_exit_lookback"] == 10
    assert state["turtle_high"] < state["current_price"]
    assert state["turtle_confirmation"] == "quote_breakout_confirmed"
    assert state["realized_volatility_window_s"] == 60
    assert state["realized_volatility_observation_n"] >= 2
    assert state["ewmac_fast_lookback"] == 12
    assert state["ewmac_slow_lookback"] == 26
    assert state["ewma_fast"] == state["ema_fast"]
    assert state["ewma_slow"] == state["ema_slow"]
    assert state["feature_provenance"]["breakout_rules"] == "prior_quote_observations"


def test_quote_history_derives_volume_proxy_force_index_and_impulse_inputs():
    values = [1.1000 + index * 0.00002 for index in range(90)]
    history = _quote_path(values, step=1.0)
    for index, item in enumerate(history):
        item["tick_volume"] = 10 + index
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["force_index_data_provenance"] == "tick_volume_proxy"
    assert state["force_index_confirmation"] == "quote_proxy_confirmed"
    assert state["force_index"] > 0
    assert state["force_index_direction"] == "up"
    assert state["ema_slope"] == "up"
    assert state["macd_histogram_slope"] in {"up", "down", "flat"}
    assert state["impulse_state"] in {"green", "red", "neutral"}
    assert state["feature_provenance"]["force_index"] == "tick_volume_proxy"
    assert state["feature_provenance"]["elder_impulse"] == "quote_observation_proxy"


def test_quote_history_derives_squeeze_and_named_candle_aliases_with_provenance():
    values = [1.1000] * 30 + [1.1000, 1.0980, 1.1005] + [1.1005] * 13
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["candlestick_pattern"] == "hammer"
    assert state["candlestick_confirmation"] == "quote_bar_proxy_confirmed"
    assert state["squeeze_state"] in {"on", "off", "released"}
    assert state["squeeze_direction"] in {"up", "down", "flat"}
    assert state["squeeze_momentum"] is not None
    assert state["squeeze_confirmation"] in {"quote_proxy_confirmed", "quote_proxy_unconfirmed"}
    assert state["feature_provenance"]["candlestick_patterns"] == "completed_quote_bar_proxy"
    assert state["feature_provenance"]["ttm_squeeze"] == "quote_observation_proxy"


def test_quote_history_derives_three_screen_context_without_future_data():
    history = _history()
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["primary_trend"] in {"up", "down", "range"}
    assert state["intermediate_oscillator"]
    assert state["short_trigger"] in {"up_confirmed", "down_confirmed", "unresolved"}
    assert state["three_screen_data_provenance"] == "quote_observation_proxy"


def test_quote_history_derives_asof_cross_sectional_momentum_rank():
    histories = {}
    for symbol, slope in ((f"S{index:02d}", 0.00001 + index * 0.000001) for index in range(12)):
        values = [1.1000 + point * slope for point in range(130)]
        histories[symbol] = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "S11", "side": "BUY"},
        histories["S11"][-1],
        symbol_history=histories["S11"][:-1],
        universe_history={name: rows[:-1] for name, rows in histories.items()},
    )

    assert state["rank_universe_n"] == 12
    assert 0.0 <= state["momentum_rank_percentile"] <= 1.0
    assert state["momentum_direction"] == "up"
    assert state["ranking_as_of"]
    assert state["feature_provenance"]["cross_sectional_momentum"] == "asof_quote_return_rank"
    assert state["factor_signal"] == "BUY"
    assert state["factor_score"] > 0
    assert state["factor_rank_percentile"] == state["momentum_rank_percentile"]
    assert state["factor_as_of"] == state["ranking_as_of"]
    assert state["relative_strength_benchmark"] == "universe_median"
    assert state["relative_strength_ratio"] > 1
    assert state["relative_strength_direction"] == "up"
    assert state["relative_strength_as_of"] == state["ranking_as_of"]


def test_cross_asset_context_aligns_asof_without_requiring_identical_tick_times():
    left_values = [1.1000 + index * 0.00005 for index in range(31)]
    right_values = [1.3000 + index * 0.00004 for index in range(30)]
    left = _quote_path(left_values, start=0.0, step=10.0)
    right = _quote_path(right_values, start=0.25, step=10.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        left[-1],
        symbol_history=left[:-1],
        universe_history={"EURUSD": left[:-1], "GBPUSD": right},
    )

    assert state["correlation"] > 0.99
    assert state["correlation_state"] == "aligned"
    assert state["cross_asset"] == "quote_return_relationship_GBPUSD"
    assert state["feature_provenance"]["cross_asset"] == "quote_return_correlation_proxy"


def test_quote_history_derives_causal_descriptive_seasonality_without_lookahead():
    from datetime import datetime, timedelta, timezone

    current_time = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    history = []
    for weeks_ago in range(1, 36):
        anchor_time = current_time - timedelta(days=7 * weeks_ago)
        anchor = 1.1000 + weeks_ago * 0.00001
        history.extend([
            {"time": anchor_time.timestamp(), "bid": anchor, "ask": anchor + 0.0002, "mid": anchor + 0.0001},
            {"time": (anchor_time + timedelta(seconds=60)).timestamp(), "bid": anchor + 0.0004, "ask": anchor + 0.0006, "mid": anchor + 0.0005},
        ])
    history.append({
        "time": (current_time + timedelta(seconds=60)).timestamp(),
        "bid": 9.0,
        "ask": 9.1,
        "mid": 9.05,
    })
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": current_time.timestamp(), "bid": 1.1000, "ask": 1.1002, "mid": 1.1001},
        symbol_history=history,
    )

    assert state["quote_history_future_excluded"] is True
    assert state["seasonal_sample_n"] == 35
    assert state["seasonal_expectancy"] > 0
    assert state["seasonal_direction"] == "up"
    assert state["seasonal_validation"] == "chronological_prior_quote_return_descriptive_not_validated"
    assert state["feature_provenance"]["seasonality"] == "causal_prior_quote_return_conditioning"
    seasonality = next(item for item in evaluate_all(state) if item["algorithm_id"] == "seasonality_context")
    assert seasonality["applicability"] == "APPLICABLE"
    assert seasonality["view"] == "WAIT"
    assert "not validated" in seasonality["reasons"][0]


def test_quote_history_derives_fractional_difference_without_claiming_stationarity():
    history = _quote_path([1.1000 + index * 0.00001 for index in range(100)], step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert math.isfinite(state["fractional_diff_value"])
    assert state["fractional_diff_d"] == 0.5
    assert state["fractional_diff_observation_n"] >= 50
    assert state["fractional_diff_stationarity"] == "descriptive_quote_proxy_not_validated"
    assert state["feature_provenance"]["fractional_differentiation"] == "causal_log_quote_fractional_difference"
    result = next(item for item in evaluate_all(state) if item["algorithm_id"] == "fractional_differentiation")
    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "WAIT"
    assert "not validated" in result["reasons"][0]


def test_quote_history_derives_causal_kalman_local_level_proxy_without_signal_authority():
    history = _history(end=600.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert math.isfinite(state["kalman_residual"])
    assert math.isfinite(state["kalman_zscore"])
    assert state["kalman_data_provenance"] == "causal_local_level_quote_filter_proxy"
    assert state["kalman_confirmation"] == "quote_proxy_unconfirmed"
    result = next(item for item in evaluate_all(state) if item["algorithm_id"] == "kalman_filter")
    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "WAIT"
    assert "stable or confirmed" in result["reasons"][0]


def test_quote_history_derives_nonvalidated_volatility_and_order_flow_proxies():
    values = [
        1.1000 + index * 0.00001 + (0.00008 if index % 3 == 0 else -0.00003 if index % 3 == 1 else 0.0)
        for index in range(180)
    ]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert math.isfinite(state["garch_forecast"])
    assert state["garch_model_status"] == "descriptive_quote_garch_proxy_not_validated"
    assert state["garch_data_provenance"] == "causal_quote_garch_recursion_proxy"
    assert math.isfinite(state["stochastic_volatility_forecast"])
    assert state["stochastic_volatility_status"] == "descriptive_log_variance_proxy_not_validated"
    assert state["stochastic_volatility_data_provenance"] == "causal_log_return_variance_proxy"
    assert state["hawkes_buy_intensity"] > 0
    assert state["hawkes_sell_intensity"] > 0
    assert state["hawkes_model_status"] == "descriptive_quote_direction_proxy_not_validated"
    assert state["hawkes_confirmation"] == "quote_direction_proxy_unconfirmed"
    assert state["feature_provenance"]["hawkes_order_flow"] == "causal_quote_direction_intensity_proxy"

    results = {item["algorithm_id"]: item for item in evaluate_all(state)}
    for name in ("garch_volatility", "stochastic_volatility", "hawkes_order_flow"):
        assert results[name]["applicability"] == "APPLICABLE"
        assert results[name]["view"] == "WAIT"


def test_quote_history_derives_wyckoff_sweep_and_kangaroo_tail_proxies():
    sweep_values = [1.1000, 1.1002, 1.1001, 1.1003, 1.1002, 1.0993, 1.1001, 1.1001]
    sweep_history = _quote_path(sweep_values)
    for index, item in enumerate(sweep_history):
        item["tick_volume"] = 10 + index
    sweep_state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        sweep_history[-1],
        symbol_history=sweep_history[:-1],
    )

    assert sweep_state["wyckoff_event"] == "spring"
    assert sweep_state["wyckoff_confirmation"] == "quote_price_proxy_confirmed"
    assert sweep_state["wyckoff_volume_confirmation"] == "quote_volume_proxy_confirmed"
    assert sweep_state["feature_provenance"]["wyckoff"] == "quote_sweep_and_tick_volume_proxy"

    tail_values = [1.1000] * 30 + [1.1000, 1.0980, 1.1005] + [1.1005] * 13
    tail_history = _quote_path(tail_values)
    for index, item in enumerate(tail_history):
        item["tick_volume"] = 10 + index
    tail_state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        tail_history[-1],
        symbol_history=tail_history[:-1],
    )
    assert tail_state["tail_direction"] == "bullish"
    assert tail_state["tail_context"] == "support"
    assert tail_state["tail_confirmation"] == "quote_bar_proxy_confirmed"
    assert tail_state["tail_wick_ratio"] > 2


def test_quote_history_derives_point_and_figure_geometry_without_future_data():
    values = [
        1.1000, 1.1004, 1.1008, 1.1012, 1.1016, 1.1020,
        1.1016, 1.1012, 1.1008, 1.1004, 1.1000,
        1.1004, 1.1008, 1.1012, 1.1016, 1.1020, 1.1024,
        1.1028, 1.1032, 1.1036, 1.1040, 1.1044,
    ]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["pnf_box_size"] > 0
    assert state["pnf_reversal_boxes"] == 3
    assert state["pnf_direction"] == "up"
    assert state["pnf_pattern"]
    assert state["pnf_confirmation"]
    assert state["pnf_observation_n"] == len(history)
    assert state["feature_provenance"]["point_and_figure"] == "quote_point_and_figure_proxy"


def test_quote_history_derives_causal_cycle_phase_with_explicit_proxy_provenance():
    values = [1.1000 + 0.0010 * math.sin(2.0 * math.pi * index / 20.0) for index in range(137)]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["cycle_period"] == 20
    assert state["cycle_direction"] == "up"
    assert state["cycle_state"] == "trough_rising"
    assert state["cycle_confidence"] >= 0.5
    assert state["cycle_data_provenance"] == "causal_quote_autocorrelation_proxy"
    assert state["feature_provenance"]["cycle_analysis"] == "causal_quote_autocorrelation_proxy"


def test_quote_history_derives_confirmed_second_entry_from_completed_bars_only():
    bar_ends = (1.1010, 1.1006, 1.1012, 1.1008, 1.1018)
    bar_starts = (1.1000, 1.1010, 1.1006, 1.1012, 1.1008)
    values = []
    for opening, closing in zip(bar_starts, bar_ends):
        values.extend(opening + (closing - opening) * index / 14.0 for index in range(15))
    history = _quote_path(values, step=1.0)
    final = {"time": 75.0, "bid": 1.10178, "ask": 1.10182, "mid": 1.1018}
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        final,
        symbol_history=history,
    )

    assert state["second_entry_direction"] == "up"
    assert state["second_entry_number"] == 2
    assert state["second_entry_context"] == "bullish_pullback"
    assert state["second_entry_confirmation"] == "quote_bar_proxy_confirmed"
    assert state["second_entry_bar_end_time"] == 75.0
    assert state["feature_provenance"]["second_entry"] == "completed_quote_bar_proxy"


def test_quote_history_derives_al_brooks_count_and_range_location_as_observed_proxies():
    bar_starts = (1.1000, 1.1010, 1.1006, 1.1012, 1.1008)
    bar_ends = (1.1010, 1.1006, 1.1012, 1.1008, 1.1018)
    values = []
    for opening, closing in zip(bar_starts, bar_ends):
        values.extend((opening, (opening + closing) / 2.0, closing))
    history = _quote_path(values, step=5.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 80.0, "bid": 1.10178, "ask": 1.10182, "mid": 1.1018},
        symbol_history=history,
    )

    assert state["bar_count_direction"] == "up"
    assert state["bar_count"] == 1
    assert state["bar_count_trendline_break"] is True
    assert state["bar_count_confirmation"] == "quote_bar_proxy_confirmed"
    assert state["feature_provenance"]["al_brooks"] == "completed_quote_bar_proxy"


def test_quote_history_derives_new_brooks_range_perspectives_from_completed_bars():
    bars = [
        (1.1000, 1.1005, 1.1010),
        (1.1012, 1.1018, 1.1024),
        (1.1026, 1.1028, 1.1030),
        (1.10315, 1.10320, 1.10325),
    ]
    history = []
    for index, path in enumerate(bars):
        history.extend(_quote_path(path, start=index * 15.0 + 1.0, step=6.0))

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 70.0, "bid": 1.10338, "ask": 1.10342, "mid": 1.10340},
        symbol_history=history,
    )

    assert state["brooks_stairs_direction"] == "up"
    assert state["brooks_stairs_breakout_sizes"] == pytest.approx([14.0, 6.0, 2.5])
    assert state["brooks_gap_trend_direction"] == "up"
    assert state["brooks_gap_trend_bar_strength"] == "strong"
    assert state["brooks_gap_before_high"] == pytest.approx(1.1024)
    assert state["brooks_gap_after_low"] == pytest.approx(1.10315)
    assert state["brooks_always_in_mode"] is True
    assert state["brooks_always_in_direction"] == "up"
    assert state["brooks_always_in_spike_confirmed"] is True
    assert state["brooks_strong_trend"] is True
    assert state["brooks_countertrend"] is False
    assert "always-in strong trend" in state["brooks_entry_reasons"]
    assert state["feature_provenance"]["brooks_two_reasons"] == "completed_quote_bar_proxy"
    assert state["feature_provenance"]["brooks_range_rules"] == "completed_quote_bar_proxy"
    assert evaluate_module("brooks_shrinking_stairs", state)["brooks_stairs_assessment"] == "SHRINKING_STAIRS_WANING_MOMENTUM"
    assert evaluate_module("brooks_micro_measuring_gap", state)["view"] == "BUY"
    assert evaluate_module("brooks_always_in_mode", state)["view"] == "BUY"


def test_quote_history_derives_volman_double_doji_break_as_a_causal_proxy():
    bars = [
        (1.10000, 1.10025),
        (1.10025, 1.10050),
        (1.10050, 1.10075),
        (1.10075, 1.10100),
        (1.10100, 1.10125),
        (1.10125, 1.10150),
        (1.10150, 1.10175),
        (1.10175, 1.10200),
        (1.10200, 1.10225),
        (1.10225, 1.10245),
        (1.10245, 1.10220),
        (1.10220, 1.10223),
        (1.10223, 1.10225),
        (1.10225, 1.10280),
    ]
    history = []
    for index, (opening, closing) in enumerate(bars):
        start = index * 15.0
        history.extend(_quote_path([opening, closing], start=start + 1.0, step=9.0))

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": len(bars) * 15.0 + 5.0, "bid": 1.10278, "ask": 1.10282, "mid": 1.10280},
        symbol_history=history,
    )

    assert "double_doji_break" in state["volman_setups"]
    assert state["volman_signal_break"] == "confirmed"
    assert state["volman_data_provenance"] == "causal_completed_quote_bar_proxy"
    assert state["feature_provenance"]["volman"] == "causal_completed_quote_bar_proxy"


def _volman_extension_history(*, descending: bool = False):
    levels = [
        (1.1000, 1.1005),
        (1.1005, 1.1010),
        (1.1010, 1.1015),
        (1.1015, 1.1020),
        (1.1020, 1.1018),
        (1.1018, 1.1013),
        (1.1013, 1.1010),
        (1.1010, 1.1025),
    ]
    if descending:
        levels = [(2.2050 - opening, 2.2050 - closing) for opening, closing in levels]
    history = []
    for index, (opening, closing) in enumerate(levels):
        history.extend(_quote_path([opening, closing], start=index * 15.0 + 1.0, step=9.0))
    return history


def test_volman_extensions_are_derived_causally_with_buy_executable_exit_price():
    history = _volman_extension_history()
    history.append({"time": 999.0, "bid": 9.0, "ask": 9.1, "mid": 9.05})
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 125.0, "bid": 1.10248, "ask": 1.10252, "mid": 1.10250},
        symbol_history=history,
    )

    assert state["quote_history_future_excluded"] is True
    assert state["volman_market_favorable"] is True
    assert state["volman_path_room_pips"] >= 10.0
    assert state["volman_pressure_aligned"] is True
    assert state["volman_pullback_style"] == "diagonal"
    assert state["volman_pullback_fraction"] == pytest.approx(0.5)
    assert state["volman_tipping_point_source"] == "pullback_low"
    assert state["volman_tipping_point_price"] == pytest.approx(1.1010)
    assert state["volman_current_exit_price"] == pytest.approx(1.10248)
    assert state["volman_tipping_point_activated"] is True
    assert state["volman_data_provenance"] == "causal_completed_quote_bar_proxy"


def test_volman_tipping_point_uses_sell_ask_and_reverses_technical_level():
    history = _volman_extension_history(descending=True)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "SELL"},
        {"time": 125.0, "bid": 1.10246, "ask": 1.10250, "mid": 1.10248},
        symbol_history=history,
    )

    assert state["volman_tipping_point_source"] == "pullback_high"
    assert state["volman_current_exit_price"] == pytest.approx(1.10250)
    assert state["volman_tipping_point_price"] == pytest.approx(1.1040)
    assert state["volman_tipping_point_activated"] is True


def test_volman_extension_derivation_does_not_use_future_quote_to_change_features():
    history = _volman_extension_history()
    baseline = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 125.0, "bid": 1.10248, "ask": 1.10252, "mid": 1.10250},
        symbol_history=history,
    )
    with_future = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 125.0, "bid": 1.10248, "ask": 1.10252, "mid": 1.10250},
        symbol_history=[*history, {"time": 126.0, "bid": 1.0900, "ask": 1.09004, "mid": 1.09002}],
    )

    for key in (
        "volman_path_room_pips",
        "volman_pullback_style",
        "volman_pullback_fraction",
        "volman_tipping_point_price",
        "volman_pressure_aligned",
    ):
        assert with_future[key] == baseline[key]


def test_quote_history_derives_vpa_anomaly_without_claiming_traded_volume():
    history = []
    bars = [
        (1.1000, 1.1004, 20),
        (1.1004, 1.1008, 20),
        (1.1008, 1.1012, 20),
        (1.1012, 1.1016, 20),
        (1.1016, 1.1020, 20),
        (1.1020, 1.1021, 5),
    ]
    for index, (opening, closing, volume) in enumerate(bars):
        start = index * 15.0
        bar_points = (
            ((1.0, opening), (7.0, opening + 0.0015), (10.0, opening + 0.0001))
            if index == len(bars) - 1
            else ((1.0, opening), (10.0, closing))
        )
        for offset, value in bar_points:
            history.append({
                "time": start + offset,
                "bid": value - 0.00002,
                "ask": value + 0.00002,
                "mid": value,
                "tick_volume": volume,
            })
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": len(bars) * 15.0 + 5.0, "bid": 1.1021 - 0.00002, "ask": 1.1021 + 0.00002, "mid": 1.1021},
        symbol_history=history,
    )

    assert state["vpa_setup"] == "long_legged_doji"
    assert state["vpa_volume_provenance"] == "tick_activity_proxy"
    assert state["feature_provenance"]["vpa"] == "causal_completed_bar_tick_activity_proxy"


def test_quote_history_derives_edwards_magee_triangle_without_active_bar_lookahead():
    history = []
    bars = [
        (1.1005, 1.1010, 1.1000, 1.1006, 20),
        (1.1005, 1.1009, 1.1002, 1.1006, 20),
        (1.1005, 1.1008, 1.10035, 1.1005, 20),
        (1.1005, 1.1007, 1.10045, 1.10052, 20),
        (1.1007, 1.1018, 1.1007, 1.1018, 40),
    ]
    for index, (opening, high, low, closing, volume) in enumerate(bars):
        start = index * 15.0
        for offset, value in ((1.0, opening), (4.0, high), (7.0, low), (10.0, closing)):
            history.append({
                "time": start + offset,
                "bid": value - 0.00002,
                "ask": value + 0.00002,
                "mid": value,
                "tick_volume": volume,
            })

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 80.0, "bid": 1.10178, "ask": 1.10182, "mid": 1.10180},
        symbol_history=history,
    )

    assert state["em_setup"] == "symmetrical_triangle"
    assert state["em_breakout_direction"] == "up"
    assert state["em_breakout_confirmation"] == "confirmed"
    assert state["em_data_provenance"] == "causal_completed_quote_bar_proxy"
    assert state["feature_provenance"]["edwards_magee"] == "causal_completed_quote_bar_proxy"
    assert state["quote_history_future_excluded"] is False


def test_completed_quote_bars_recognize_a_three_candle_morning_star_proxy():
    values = [
        1.1040, 1.1008, 1.1010,
        1.1011, 1.1009, 1.1012,
        1.1013, 1.1042, 1.1040,
    ]
    history = _quote_path(values, step=5.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 50.0, "bid": 1.1040, "ask": 1.10404, "mid": 1.10402},
        symbol_history=history,
    )

    assert state["candlestick_pattern"] == "morning_star"
    assert state["candlestick_confirmation"] == "quote_bar_proxy_confirmed"
    assert state["feature_provenance"]["candlestick_patterns"] == "completed_quote_bar_proxy"


def test_quote_history_derives_walk_forward_forecast_without_future_data():
    values = [1.1000 + index * 0.00001 + 0.00003 * (index % 5) for index in range(220)]
    history = _quote_path(values, step=1.0)
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "horizon_s": 5},
        history[-1],
        symbol_history=history[:-1],
    )

    assert state["forecast_model"] == "causal_linear_drift"
    assert state["forecast_oos_status"] == "WALK_FORWARD"
    assert state["forecast_oos_n"] >= 20
    assert state["forecast_current_price"] == history[-1]["mid"]
    assert state["forecast_horizon_s"] == 5
    assert state["forecast_uncertainty"] > 0
    assert state["forecast_training_last_time"] == history[-1]["time"]
    assert state["feature_provenance"]["time_series_forecasting"] == "causal_quote_walk_forward"


def test_quote_history_derives_causal_chan_gap_and_stop_trigger_without_fabricating_events_or_order_flow():
    bars = [
        (1.1000, 1.1001),
        (1.1001, 1.1002),
        (1.1002, 1.1001),
        (1.1001, 1.1003),
        (1.1020, 1.1022),
    ]
    history = []
    for index, (opening, closing) in enumerate(bars):
        start = index * 15.0
        history.extend(_quote_path([opening, closing], start=start + 1.0, step=9.0))
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 100.0, "bid": 1.10248, "ask": 1.10252, "mid": 1.10250},
        symbol_history=history,
    )

    assert state["chan_gap_open_price"] == 1.1020
    assert state["chan_gap_prior_high"] == pytest.approx(1.1003)
    assert state["chan_gap_data_provenance"] == "causal_completed_quote_bar_gap_proxy"
    assert state["chan_stop_level_role"] == "resistance"
    assert state["chan_stop_break_confirmed"] is True
    assert state["chan_stop_data_provenance"] == "causal_quote_range_stop_proxy"
    assert "chan_news_event_present" not in state
    assert "chan_order_flow_value" not in state


def test_quote_history_preserves_explicit_level_two_and_signed_flow_inputs_for_chan_perspectives():
    history = _quote_path([1.1000, 1.1002, 1.1003, 1.1005], step=1.0)
    for index, item in enumerate(history):
        item.update({"bid_size": 300.0, "ask_size": 100.0, "signed_order_flow": 75.0 + index})
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 4.0, "bid": 1.10048, "ask": 1.10052, "mid": 1.1005,
         "bid_size": 300.0, "ask_size": 100.0, "signed_order_flow": 100.0},
        symbol_history=history,
    )

    assert state["chan_bid_size"] == 300.0
    assert state["chan_ask_size"] == 100.0
    assert state["chan_order_flow_value"] > 0
    assert evaluate_module("chan_bid_ask_imbalance", state)["view"] == "BUY"
    assert evaluate_module("chan_order_flow_momentum", state)["view"] == "BUY"


def test_quote_history_derives_chan_half_life_causally_without_fabricating_significance():
    history = []
    for index in range(1, 161):
        mid = 1.1000 + 0.0008 * (0.97 ** index)
        history.append({
            "time": float(index),
            "bid": mid - 0.00002,
            "ask": mid + 0.00002,
            "mid": mid,
        })
    future = {"time": 999.0, "bid": 1.5000, "ask": 1.5002, "mid": 1.5001}
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "horizon_s": 20},
        {"time": 161.0, "bid": 1.10002, "ask": 1.10006, "mid": 1.10004},
        symbol_history=[*history, future],
    )

    assert state["quote_history_future_excluded"] is True
    assert state["chan_mean_reversion_coefficient"] < 0
    assert state["chan_mean_reversion_half_life"] > 0
    assert state["chan_half_life_data_provenance"] == "observed_causal_log_quote_series"
    assert "chan_hurst_null_rejected" not in state
    assert "chan_adf_critical_value" not in state
