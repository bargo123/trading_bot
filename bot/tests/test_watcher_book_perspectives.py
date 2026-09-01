from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from aegis.research import watcher_algorithms
from aegis.research.watcher_algorithms import evaluate_module
from aegis.research.watcher_book_perspectives import (
    BOOK_ALGORITHM_COVERAGE,
    BOOK_REVIEW_COVERAGE,
    _FAMILY_ALGORITHM_PERSPECTIVES,
    analyze_book_perspectives,
    evaluate_book_algorithm,
    strategy_implementation_status,
)


EXPECTED_ALGORITHM_MODULES = {
    "trend_continuation",
    "trend_pullback",
    "range_edge_fade",
    "failed_breakout",
    "breakout_continuation",
    "volume_effort_result",
    "pyramiding",
    "adverse_selection",
    "time_stop",
    "intermarket_analysis",
    "noise_filter",
    "tail_risk",
    "event_arbitrage",
    "spread_scalping",
    "latency_arbitrage",
    "rebate_capture",
    "market_impact_symmetry",
    "dejong_roll_spread_estimator",
    "dejong_spread_decomposition",
    "dejong_duration_weighted_spread",
    "al_brooks_high_low_count",
    "al_brooks_wedge",
    "al_brooks_failed_failure",
    "al_brooks_spike_channel",
    "al_brooks_double_flag",
    "al_brooks_range_location",
    "volman_double_doji_break",
    "volman_first_break",
    "volman_second_break",
    "volman_block_break",
    "volman_range_break",
    "volman_inside_range_break",
    "volman_advanced_range_break",
    "volman_tipping_point_exit",
    "volman_unfavorable_path_filter",
    "volman_pullback_quality",
    "vpa_long_legged_doji",
    "vpa_narrow_spread_high_volume",
    "vpa_stopping_volume",
    "vpa_topping_out_volume",
    "vpa_breakout_volume_validation",
    "vpa_trend_effort_confirmation",
    "edwards_magee_head_shoulders",
    "edwards_magee_triangle_breakout",
    "edwards_magee_gap_classification",
    "edwards_magee_support_resistance_flip",
    "edwards_magee_channel_deterioration",
    "edwards_magee_one_day_reversal",
    "edwards_magee_selling_climax",
    "edwards_magee_trendline_penetration",
    "edwards_magee_broadening_breakout",
    "edwards_magee_key_reversal_day",
    "edwards_magee_spike_reversal",
    "edwards_magee_runaway_day",
    "edwards_magee_dow_confirmation",
    "edwards_magee_basing_points_stop",
    "edwards_magee_breakout_confirmation",
    "edwards_magee_climactic_volume_stop",
    "edwards_magee_defensive_exit",
    "ponsi_level_bounce",
    "ponsi_intraday_breakout",
    "ponsi_pennant_continuation",
    "ponsi_round_number_bounce",
    "ponsi_boomerang_fade",
    "anderson_high_volume_runner",
    "anderson_conditional_bracket",
    "nison_three_line_break",
    "nison_renko_trend",
    "nison_kagi_yang_yin",
    "nison_disparity_reversal",
    "nison_hammer_hanging_man",
    "nison_shooting_star",
    "nison_doji_confirmation",
    "nison_two_line_reversal",
    "nison_three_line_star",
    "nison_spring_upthrust",
    "nison_last_engulfing",
    "nison_window_context",
    "nison_three_windows",
    "nison_record_sessions",
    "nison_harami",
    "nison_harami_cross",
    "nison_two_black_gapping",
    "nison_gapping_doji",
    "nison_extra_line_break_confirmation",
    "nison_three_line_neck",
    "nison_kagi_double_window",
    "nison_kagi_tweezers",
    "nison_kagi_three_buddha",
    "aldridge_order_flow_autocorrelation",
    "aldridge_trade_aggressiveness",
    "aldridge_bid_ask_bounce_filter",
    "aldridge_quote_duration",
    "aldridge_trade_direction_uncertainty",
    "aldridge_quote_matching",
    "aldridge_triangular_arbitrage",
    "aldridge_uip_arbitrage",
    "aldridge_index_composition_arbitrage",
    "aldridge_volatility_curve_arbitrage",
    "aldridge_futures_basis_arbitrage",
    "aldridge_futures_etf_arbitrage",
    "aldridge_dual_class_arbitrage",
    "aldridge_risk_arbitrage",
    "aronson_objective_rule_definition",
    "aronson_reality_check",
    "aronson_practical_significance",
    "aronson_detrended_rule_return",
    "johnson_implementation_shortfall",
    "johnson_adaptive_shortfall",
    "johnson_price_inline",
    "johnson_liquidity_seeking",
    "johnson_order_difficulty",
    "elliott_impulse_rules",
    "elliott_wave_three_extension",
    "elliott_diagonal_rules",
    "elliott_corrective_structure",
    "elliott_alternation",
    "price_in_time_ntz_projection",
    "price_in_time_range_cycle",
    "price_in_time_pending_order",
    "price_in_time_ntz_breakout",
    "price_in_time_trade_management_models",
    "price_in_time_opening_price",
    "price_in_time_session_filter",
    "price_in_time_anomaly_filter",
    "thomas_push_pull_10xroi",
    "thomas_ma_momentum_filter",
    "thomas_break_even_after_pullback",
    "thomas_fixed_r_target",
    "thomas_breakout_context",
    "thomas_parabolic_exhaustion_exit",
    "clenow_dual_ema_breakout",
    "clenow_core_breakout",
    "clenow_core_exit",
    "clenow_volatility_trailing_stop",
    "clenow_style_diversification",
    "silvani_retail_contrarian",
    "silvani_rolling_pivot_filter",
    "silvani_friday_stop_run",
    "aziz_abcd_pattern",
    "aziz_bull_flag_momentum",
    "aziz_red_to_green",
    "aziz_bhod",
    "aziz_bottom_reversal",
    "aziz_top_reversal",
    "aziz_moving_average_trend",
    "aziz_vwap_control",
    "aziz_stock_in_play_scanner",
    "aziz_premarket_gapper_scanner",
    "aziz_relative_volume_independence",
    "aziz_reversal_market_context",
    "aziz_opening_range_breakout",
    "grail_time_anchor_breakout",
    "grail_bracket_lifecycle",
    "grail_regime_failure_warning",
    "chan_linear_mean_reversion",
    "chan_kalman_mean_reversion",
    "chan_cross_sectional_mean_reversion",
    "chan_time_series_momentum",
    "chan_alexander_filter",
    "chan_opening_gap_momentum",
    "chan_news_drift",
    "chan_stop_order_momentum",
    "chan_order_flow_momentum",
    "chan_bid_ask_imbalance",
    "chan_ratio_trade",
    "chan_ticking_quote_matching",
    "chan_hft_quote_data_requirements",
    "chan_bulk_volume_order_flow",
    "chan_leveraged_rebalance_momentum",
    "chan_half_kelly_cap",
    "chan_adf_mean_reversion",
    "chan_hurst_stationarity",
    "chan_variance_ratio_stationarity",
    "chan_mean_reversion_half_life",
    "chan_cadf_cointegration",
    "chan_johansen_cointegration",
    "ultimate_price_rejection",
    "ultimate_ema_reversal",
    "ultimate_head_shoulders",
    "ultimate_double_triple_test",
    "ultimate_vpa_extreme",
    "ultimate_mtf_confirmation",
    "ultimate_mw_bat_pattern",
    "ultimate_correlation_lag",
    "ultimate_abandoned_baby_ema5",
    "ultimate_triangle_pattern",
    "ultimate_cascade_exhaustion",
    "ultimate_sandwich_pattern",
    "ultimate_fractal_pattern",
    "ultimate_local_extrema_timing",
    "ultimate_sentiment_change",
    "ultimate_high_performance_confluence",
    "ultimate_news_sr_reaction",
    "pf_three_box_catapult",
    "pf_double_top_bottom",
    "pf_triple_top_bottom",
    "pf_pole_reversal",
    "pf_trendline_signal_confirmation",
    "pf_opposing_poles",
    "pf_45_degree_trendline",
    "pf_early_fulcrum_entry",
    "pf_trend_aligned_signal",
    "pf_vertical_count_target",
    "pf_horizontal_count_target",
    "pf_shakeout_filter",
    "pf_trap_reversal",
    "pf_one_box_semicatapult",
    "pf_one_box_fulcrum",
    "damir_fib_confluence_reversal",
    "damir_confirmed_trend_change",
    "damir_value_rejection_sequence",
    "damir_value_location_guideline",
    "damir_value_health_warning",
    "gann_reverse_signal_day",
    "gann_higher_tops_bottoms",
    "gann_halfway_point",
    "gann_repeated_level_reversal",
    "gann_secondary_reaction",
    "gann_fourth_level_reversal",
    "brooks_breakout_pullback_test",
    "brooks_barbwire_filter",
    "brooks_breakout_mode",
    "brooks_failed_breakout_reversal",
    "brooks_measured_move_projection",
    "brooks_shrinking_stairs",
    "brooks_micro_measuring_gap",
    "brooks_always_in_mode",
    "brooks_trader_equation",
    "brooks_two_reasons_entry",
    "brooks_timeframe_discipline",
    "elder_triple_screen",
    "elder_impulse_censorship",
    "elder_force_index_pullback",
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
    "carter_scalper_alert",
    "carter_tick_extreme_fade",
    "carter_anchor_squeeze",
    "carter_brick_reversal",
    "carter_holp_lohp",
    "carter_end_of_day_fade",
    "carter_ema_propulsion",
    "carter_opening_gap_fade",
    "carter_pivot_play",
    "carter_atr_mean_reversion",
    "carter_tick_flow_follow",
    "carter_352_play",
    "carter_multisetup_confirmation",
    "chan_exit_policy",
    "elder_safezone_stop",
    "carter_tick_price_divergence",
    "carter_tick_noise_regime",
    "schwager_bull_bear_trap",
    "schwager_false_trend_breakout",
    "schwager_filled_gap_failure",
    "schwager_spike_extreme_failure",
    "schwager_wide_range_day_failure",
    "schwager_counter_flag_failure",
    "grimes_pullback_quality",
    "grimes_three_push_exhaustion",
    "developing_hft_flow_exhaustion",
    "developing_hft_liquidity_depth",
    "developing_hft_volatility_clustering",
    "developing_hft_stat_arb_dislocation",
    "developing_hft_news_impact",
    "harris_immediacy_cost",
    "harris_limit_order_regret",
    "harris_stop_order_momentum",
    "murphy_inverse_relationship",
    "murphy_lead_lag_confirmation",
    "murphy_relationship_regime",
    "murphy_sector_rotation",
    "schwager_ma_turn_filter",
    "schwager_range_breakout_confirmation",
    "schwager_range_participation_filter",
    "schwager_restrictive_reversal_day",
    "schwager_minor_reaction_reentry",
    "schwager_long_ma_reaction",
    "schwager_oscillator_price_confirmation",
    "schwager_trend_adjusted_oscillator",
    "schwager_island_reversal_validation",
    "schwager_equity_deterioration_warning",
    "schwager_record_extreme_continuation",
    "schwager_narrow_consolidation_bias",
    "schwager_news_non_followthrough_reversal",
    "oreste_qpl_interaction",
    "oreste_entelechy_confluence",
    "oreste_time_price_confluence",
    "oreste_volatility_scaled_risk",
    "cartea_regime_rebate_safety",
    "cartea_inventory_skew",
    "cartea_state_intensity",
    "cartea_quote_freshness_guard",
    "aldridge_pair_dislocation",
    "dalton_trend_day_integrity",
    "dalton_auction_point_retest",
    "dalton_day_structure",
    "dalton_failed_range_extension",
    "dalton_single_print_retest",
    "process_discipline_control",
    "douglas_probability_edge",
    "tendler_process_error",
    "drakoln_plan_integrity",
    "narang_horizon_specification",
    "narang_conditional_alpha",
    "narang_linear_alpha_blend",
    "narang_alpha_rotation",
    "narang_run_frequency_tradeoff",
    "davey_euro_night_strategy",
    "davey_euro_day_strategy",
    "davey_three_bar_baseline",
    "narang_cost_hurdle",
    "narang_liquidity_impact",
    "narang_forecast_bucket_monotonicity",
    "narang_time_decay",
    "narang_parameter_robustness",
    "narang_portfolio_value_add",
    "narang_risk_monitoring",
    "narang_regime_change_warning",
    "narang_exogenous_shock_filter",
    "narang_contagion_exposure",
    "brown_ma_stack_filter",
    "brown_band_signal_filter",
    "brown_structural_stop_buffer",
    "brown_qmp_filter_trigger",
    "brown_macd_zero_filter",
    "brown_qqe_filter",
    "brown_multi_ma_alignment",
    "brown_trendline_break_reentry",
    "brown_divergence_type_filter",
    "brown_bollinger_trade_management",
    "tharp_narrow_range_breakout",
    "tharp_failed_test_reversal",
    "tharp_mae_winner_band",
    "tharp_r_multiple_expectancy",
    "tharp_market_selection",
    "ponsi_ema_trend_technique",
    "ponsi_squeeze_play",
    "ponsi_multitimeframe_pullback",
    "ponsi_fibonacci_trend_reentry",
    "ponsi_price_action_level",
    "ponsi_round_trip",
    "ponsi_interest_rate_edge",
    "pyramiding_risk_lock",
    "grinold_information_horizon",
    "grinold_trade_utility",
    "grinold_fundamental_law",
    "grinold_alpha_scaling",
    "grinold_turnover_frontier",
    "clenow_regime_filter",
    "clenow_atr_impact_sizing",
    "clenow_currency_exposure",
    "clenow_countertrend_pullback",
    "clenow_term_structure_carry",
    "pole_spread_reversion",
    "pole_popcorn_reversion",
    "pole_turning_point_event",
    "pole_event_pair_selection",
    "pole_staged_spread_entries",
    "pole_forecast_monitoring",
    "pole_cuscore_change_point",
    "pole_75_percent_reversion",
    "pole_multi_step_reversion",
    "pole_spread_margin",
    "pole_evolutionary_operation",
    "pole_catastrophe_entry",
    "pole_catastrophe_exit",
    "velu_omnibus_rule",
    "velu_fair_value_residual",
    "velu_sign_magnitude_decomposition",
    "velu_alexander_filter",
    "velu_sma_rule",
    "velu_ewa_rule",
    "velu_bwma_bollinger_rule",
    "velu_moving_average_oscillator",
    "velu_rsi_reversal",
    "velu_kernel_pattern",
    "velu_characteristic_time",
    "velu_intraday_profile",
    "velu_volume_return_filter",
    "velu_square_root_cost_hurdle",
    "velu_distance_pairs",
    "velu_microstructure_noise_sampling",
    "velu_duration_intensity",
    "gray_vogel_path_momentum",
    "gray_vogel_rebalance_tradeoff",
    "gray_vogel_lookback_regime",
    "gray_vogel_lottery_avoidance",
    "gray_vogel_seasonality_timing",
    "gray_vogel_52_week_high",
    "gray_vogel_absolute_strength",
    "gray_vogel_momentum_stop_loss",
    "gray_vogel_time_series_overlay",
    "gray_vogel_fundamental_momentum",
    "lien_intraday_range_reversal",
    "lien_medium_term_breakout",
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
    "lien_high_probability_turn",
    "lien_two_day_low_stop",
    "lien_two_stage_profit_management",
    "link_ten_period_breakout",
    "link_trendline_buffer_breakout",
    "link_opening_range_breakout_30m",
    "link_reversal_day",
    "link_double_top_bottom_reversal",
    "link_pain_reversal",
    "link_key_number_reversal",
    "link_multi_timeframe_confirmation",
    "link_news_reaction_fade",
    "link_stochastic_wave_entry",
    "link_stochastic_cross_entry",
    "link_stochastic_extreme_retest",
    "link_rsi_fifty_line_entry",
    "link_rsi_extreme_exit",
    "link_rsi_pattern_break",
    "link_macd_signal_line_entry",
    "link_adx_regime_switch",
    "link_stochastic_failed_move",
    "link_trend_retracement_entry",
    "link_atr_risk_feasibility",
    "link_stop_discipline",
    "momentum",
    "market_profile",
    "mean_reversion",
    "trend_structure",
    "breakout_quality",
    "pullback_retest",
    "price_action_candles",
    "momentum_exhaustion",
    "volume_price",
    "volume_open_interest",
    "murphy_percentage_retracement",
    "murphy_speed_resistance_lines",
    "volatility_regime",
    "microstructure",
    "mean_reversion_vs_momentum",
    "higher_timeframe_alignment",
    "session_liquidity",
    "risk_reward_geometry",
    "validation_integrity",
    "market_profile_auction",
    "statistical_arbitrage",
    "oscillator_signal",
    "scalping_execution",
    "support_resistance",
    "chart_patterns",
    "moving_average_context",
    "channel_analysis",
    "range_edge_rejection",
    "volatility_breakout",
    "divergence",
    "opening_range",
    "news_event_risk",
    "liquidity_sweep",
    "correlation_context",
    "trade_management",
    "bollinger_bands",
    "macd_signal",
    "atr_regime",
    "fibonacci_retracement",
    "pivot_levels",
    "rsi_reversal",
    "stochastic_reversal",
    "donchian_breakout",
    "adx_trend_strength",
    "keltner_channel",
    "ichimoku_context",
    "cci_reversal",
    "williams_reversal",
    "vwap_context",
    "obv_volume",
    "rate_of_change",
    "parabolic_sar",
    "elliott_wave",
    "harmonic_patterns",
    "gann_levels",
    "cointegration_pairs",
    "kalman_filter",
    "seasonality_context",
    "order_book_imbalance",
    "volume_profile_context",
    "fundamental_macro",
    "sentiment_positioning",
    "time_series_forecasting",
    "machine_learning_signal",
    "portfolio_allocation",
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
    "deprado_sample_uniqueness",
    "deprado_sequential_bootstrap",
    "deprado_combinatorial_purged_cv",
    "deprado_probabilistic_sharpe",
    "deprado_deflated_sharpe",
    "deprado_strategy_failure_probability",
    "deprado_cusum_filter",
    "deprado_entropy",
    "deprado_tick_imbalance_bar",
    "deprado_volume_imbalance_bar",
    "deprado_dollar_imbalance_bar",
    "deprado_tick_runs_bar",
    "deprado_volume_runs_bar",
    "deprado_dollar_runs_bar",
    "deprado_tick_bar",
    "deprado_volume_bar",
    "deprado_dollar_bar",
    "realized_volatility",
    "fractional_differentiation",
    "risk_parity_allocation",
    "vwap_execution",
    "twap_execution",
    "participation_execution",
    "ewmac_trend_following",
    "carry_rule",
    "ab_system",
    "carver_forecast_cap",
    "carver_position_inertia",
    "carver_speed_limit",
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
    "quantum_finance_scenario_stress",
}


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "buy",
        "structure": "bullish breakout with confirmed retest",
        "regime": "trend",
        "m15_context": {"trend": "up"},
        "h1_context": {"trend": "up"},
        "momentum_context": {"direction": "positive"},
        "short_returns": {"return_1": 0.0001, "return_3": 0.0002},
        "volume_context": {"volume_ratio": 1.4, "price_change": 0.0002},
        "volatility": "normal",
        "spread_pips": 0.8,
        "quote_age_s": 0.2,
        "quote_fresh": True,
        "imbalance": 0.2,
        "entry": 1.1000,
        "stop": 1.0990,
        "target": 1.1015,
        "expected_net_ev": 0.04,
        "sample_size": 40,
        "validation_status": "WALK_FORWARD",
        "cost_assumptions": {"spread": True, "slippage": True},
    }
    state.update(overrides)
    return state


def test_each_named_algorithm_has_its_own_python_module_and_evaluator():
    package_dir = Path(__file__).parents[1] / "aegis" / "research" / "watcher_algorithms"
    assert {path.stem for path in package_dir.glob("*.py") if path.stem not in {"__init__", "_common", "_deprado_common", "_deprado_bars_common", "_aldridge_arbitrage_common", "bulkowski_pattern_common", "bulkowski_hs_common", "bulkowski_scallop_common"}} == EXPECTED_ALGORITHM_MODULES
    for name in EXPECTED_ALGORITHM_MODULES:
        module = importlib.import_module(f"aegis.research.watcher_algorithms.{name}")
        assert callable(module.evaluate)
        result = module.evaluate(_state())
        assert result["algorithm_id"] == name
        assert result["execution_authority"] is False


def test_expanded_algorithms_use_available_context_without_fabricating_signals():
    state = _state(
        support=1.0995,
        resistance=1.1010,
        level_role="support_hold",
        pattern="bull_flag",
        pattern_confirmation="confirmed",
        ema_fast=1.1002,
        ema_slow=1.0998,
        ema_fast_slope="up",
        channel_state="upper_breakout_confirmed",
        range_position="upper_edge",
        range_edge_rejection="bearish_rejection",
        volatility_percentile=0.8,
        volatility_transition="compression_expansion",
        breakout_state="breakout_up_confirmed",
        price_oscillator_divergence="bullish_hidden",
        opening_range_state="opening_drive_up",
        news_state="no_high_impact_news",
        liquidity_sweep="sell_side_sweep_reclaimed",
        correlation_state="aligned",
        remaining_ev=0.03,
        continuation_probability=0.7,
    )
    results = {item["algorithm_id"]: item for item in analyze_book_perspectives(state)["perspectives"]}
    assert results["support_resistance"]["view"] == "BUY"
    assert results["chart_patterns"]["view"] == "BUY"
    assert results["moving_average_context"]["view"] == "BUY"
    assert results["volatility_breakout"]["view"] == "BUY"
    assert results["divergence"]["view"] == "BUY"
    assert results["opening_range"]["view"] == "BUY"
    assert results["news_event_risk"]["view"] == "BUY"
    assert results["liquidity_sweep"]["view"] == "BUY"
    assert results["trade_management"]["view"] == "BUY"
    assert all(item["execution_authority"] is False for item in results.values())


def test_context_only_algorithms_do_not_turn_a_candidate_side_into_a_signal():
    results = {
        item["algorithm_id"]: item
        for item in analyze_book_perspectives(_state(session="new_york", session_state="open"))["perspectives"]
    }

    assert results["session_liquidity"]["view"] == "WAIT"
    assert results["volatility_regime"]["view"] == "WAIT"


def test_expanded_algorithms_report_missing_inputs_instead_of_guessing():
    results = {item["algorithm_id"]: item for item in analyze_book_perspectives({"symbol": "EURUSD", "side": "buy"})["perspectives"]}
    for name in {
        "support_resistance",
        "chart_patterns",
        "moving_average_context",
        "channel_analysis",
        "range_edge_rejection",
        "volatility_breakout",
        "divergence",
        "opening_range",
        "news_event_risk",
        "liquidity_sweep",
        "correlation_context",
        "trade_management",
    }:
        assert results[name]["applicability"] == "MISSING_DATA"
        assert results[name]["execution_authority"] is False
        assert results[name]["uses_future_data"] is False


def test_empty_context_values_are_not_counted_as_evidence():
    results = {
        item["algorithm_id"]: item
        for item in analyze_book_perspectives({
            "symbol": "EURUSD",
            "side": "buy",
            "m15_context": {},
            "h1_context": {},
            "volatility_context": {},
            "quote_tick_dynamics": {},
        })["perspectives"]
    }

    assert results["higher_timeframe_alignment"]["applicability"] == "MISSING_DATA"
    assert results["volatility_regime"]["applicability"] == "MISSING_DATA"
    assert results["microstructure"]["applicability"] == "MISSING_DATA"


def test_book_perspectives_are_multiple_attributed_and_research_only():
    result = analyze_book_perspectives(_state())

    assert len(result["perspectives"]) >= 10
    assert {item["perspective_id"] for item in result["perspectives"]} >= {
        "trend_structure",
        "breakout_quality",
        "pullback_retest",
        "microstructure",
        "risk_reward_geometry",
    }
    assert all(item["execution_authority"] is False for item in result["perspectives"])
    assert all(item["research_only"] is True for item in result["perspectives"])
    assert all(item["uses_future_data"] is False for item in result["perspectives"])
    assert all(item["source_books"] for item in result["perspectives"])
    assert result["execution_authority"] is False
    assert result["no_lookahead"] is True


def test_every_algorithm_result_has_the_read_only_research_contract():
    required = {
        "algorithm_id",
        "applicability",
        "view",
        "reasons",
        "inputs_used",
        "missing_inputs",
        "source_books",
        "execution_authority",
        "uses_future_data",
        "research_only",
    }

    perspectives = analyze_book_perspectives(_state())["perspectives"]

    assert len(perspectives) == len(EXPECTED_ALGORITHM_MODULES)
    for item in perspectives:
        assert required <= set(item)
        assert isinstance(item["reasons"], list)
        assert isinstance(item["inputs_used"], list)
        assert isinstance(item["missing_inputs"], list)
        assert item["execution_authority"] is False
        assert item["uses_future_data"] is False
        assert item["research_only"] is True


def test_algorithm_exception_isolated_as_missing_research_data(monkeypatch):
    original_import_module = watcher_algorithms.import_module

    def broken_import(module_name):
        if module_name.endswith(".breakout_quality"):
            raise RuntimeError("fixture evaluator failure")
        return original_import_module(module_name)

    monkeypatch.setattr(watcher_algorithms, "import_module", broken_import)

    perspectives = analyze_book_perspectives(_state())["perspectives"]
    result = next(item for item in perspectives if item["algorithm_id"] == "breakout_quality")

    assert result["applicability"] == "MISSING_DATA"
    assert result["view"] == "MISSING_DATA"
    assert result["missing_inputs"] == ["algorithm_evaluation"]
    assert any("evaluation_error" in reason for reason in result["reasons"])
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False
    assert result["research_only"] is True


def test_every_reviewed_book_has_explicit_human_authored_module_coverage():
    assert set(BOOK_ALGORITHM_COVERAGE) == set(BOOK_REVIEW_COVERAGE)
    assert all(BOOK_ALGORITHM_COVERAGE[book] for book in BOOK_REVIEW_COVERAGE)
    assert all(
        algorithm_id in EXPECTED_ALGORITHM_MODULES
        for algorithm_ids in BOOK_ALGORITHM_COVERAGE.values()
        for algorithm_id in algorithm_ids
    )


def test_every_registered_module_has_at_least_one_book_attribution():
    covered = {
        algorithm_id
        for algorithm_ids in BOOK_ALGORITHM_COVERAGE.values()
        for algorithm_id in algorithm_ids
    }

    assert EXPECTED_ALGORITHM_MODULES <= covered


def test_perspectives_ignore_future_quote_payloads():
    result = analyze_book_perspectives(_state(
        future_quotes=[{"bid": 9.0, "ask": 9.1, "timestamp": 9999}],
        counterfactual_quotes=[{"bid": 9.0, "ask": 9.1, "timestamp": 9999}],
    ))

    assert all("future_quotes" not in item["inputs_used"] for item in result["perspectives"])
    assert all("counterfactual_quotes" not in item["inputs_used"] for item in result["perspectives"])
    assert all(item["uses_future_data"] is False for item in result["perspectives"])


def test_missing_inputs_remain_missing_instead_of_becoming_a_probability():
    result = analyze_book_perspectives({"symbol": "EURUSD", "side": "buy"})

    assert any(item["applicability"] in {"MISSING_DATA", "NOT_APPLICABLE"} for item in result["perspectives"])
    assert all("probability" not in item for item in result["perspectives"])
    assert result["research_only"] is True


def test_major_book_strategy_families_have_explicit_watcher_evaluators():
    result = analyze_book_perspectives(_state())
    ids = {item["perspective_id"] for item in result["perspectives"]}

    assert set(_FAMILY_ALGORITHM_PERSPECTIVES) >= {
        "breakout", "volatility", "reversal", "momentum", "scalping",
        "mean_reversion", "statistical_arbitrage", "order_flow",
        "candlestick", "market_profile", "volume_price",
    }
    assert set(_FAMILY_ALGORITHM_PERSPECTIVES.values()) <= ids


def test_implementation_status_is_truthful_for_exact_family_and_unknown_records():
    exact = {"status": "CODED_EXACT", "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}}}
    family = {"status": "FAMILY_PROXY", "algorithm": {"family": "mean_reversion"}}
    compile_error = {"status": "COMPILE_ERROR", "algorithm": {"family": "breakout"}}
    context = {"status": "UNTESTABLE_SOURCE", "algorithm": {"family": "breakout"}}
    compile_error_without_family = {"status": "COMPILE_ERROR", "algorithm": {}}
    unknown = {"status": "UNTESTABLE_SOURCE", "algorithm": {"family": "unknown"}}

    assert strategy_implementation_status(exact) == "WATCHER_EXACT_RULE"
    assert strategy_implementation_status(family) == "WATCHER_FAMILY_PERSPECTIVE"
    assert strategy_implementation_status(compile_error) == "WATCHER_FAMILY_PERSPECTIVE"
    assert strategy_implementation_status(context) == "WATCHER_FAMILY_CONTEXT"
    assert strategy_implementation_status(compile_error_without_family) == "SPECIFICATION_ONLY"
    assert strategy_implementation_status(unknown) == "SPECIFICATION_ONLY"


def test_compile_error_with_known_family_is_replayed_as_lower_authority_perspective():
    record = {
        "status": "COMPILE_ERROR",
        "strategy_family": "breakout",
        "algorithm": {"family": "breakout"},
    }

    result = evaluate_book_algorithm(record, _state())

    assert result["implementation_status"] == "WATCHER_FAMILY_PERSPECTIVE"
    assert result["perspective_id"] == "breakout_quality"
    assert result["execution_authority"] is False
    assert result["research_only"] is True


def test_untestable_known_family_is_context_only_not_an_exact_rule():
    record = {
        "status": "UNTESTABLE_SOURCE",
        "strategy_family": "breakout",
        "algorithm": {"family": "breakout"},
    }

    result = evaluate_book_algorithm(record, _state())

    assert result["implementation_status"] == "WATCHER_FAMILY_CONTEXT"
    assert result["perspective_id"] == "breakout_quality"
    assert result["evaluation_status"] == "FAMILY_CONTEXT"
    assert result["execution_authority"] is False
    assert result["research_only"] is True


def test_exact_book_rule_analysis_returns_real_match_status_without_authority():
    record = {
        "status": "CODED_EXACT",
        "side_rule": "BUY",
        "algorithm": {
            "family": "breakout",
            "compiled_entry_predicates": {"structure_eq": "breakout"},
        },
    }

    matching = evaluate_book_algorithm(record, {"side": "BUY", "structure": "breakout"})
    failed = evaluate_book_algorithm(record, {"side": "BUY", "structure": "range"})
    missing = evaluate_book_algorithm(record, {"side": "BUY"})

    assert matching["status"] == "MATCH"
    assert matching["evaluation_status"] == "MATCH"
    assert matching["view"] == "BUY"
    assert failed["status"] == "NO_MATCH"
    assert failed["view"] == "NOT_APPLICABLE"
    assert missing["status"] == "MISSING_INPUT"
    assert missing["view"] == "MISSING_DATA"
    assert all(item["execution_authority"] is False for item in (matching, failed, missing))


def test_exact_book_rule_keeps_real_book_provenance_when_registry_title_is_a_page_excerpt():
    record = {
        "status": "CODED_EXACT",
        "source_title": "P1: printer header 178 TRADING STRATEGIES",
        "source_path": r"C:\Users\Zaid barghouthi\Downloads\[Wiley finance series] Adam Grimes - The art and science of technical analysis (2012, Wiley) - libgen.li.pdf",
        "side_rule": "BUY",
        "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}},
    }

    result = evaluate_book_algorithm(record, {"side": "BUY", "structure": "breakout"})

    assert result["source_books"] == ["Adam Grimes — The art and science of technical analysis"]
    assert all(not item.startswith("P1:") for item in result["source_books"])


def test_each_record_gets_an_explicit_family_or_specification_evaluation():
    family = {"status": "FAMILY_PROXY", "algorithm": {"family": "breakout"}}
    unknown = {"status": "UNTESTABLE_SOURCE", "algorithm": {"family": "unknown"}}

    family_result = evaluate_book_algorithm(family, _state())
    unknown_result = evaluate_book_algorithm(unknown, _state())

    assert family_result["implementation_status"] == "WATCHER_FAMILY_PERSPECTIVE"
    assert family_result["perspective_id"] == "breakout_quality"
    assert family_result["research_only"] is True
    assert unknown_result["status"] == "SPECIFICATION_ONLY"
    assert unknown_result["missing_inputs"] == ["complete_entry_exit_parameters"]


def test_conflicting_book_perspectives_are_reported_not_resolved_by_fabrication():
    result = analyze_book_perspectives(_state(
        structure="bullish breakout",
        m15_context={"trend": "down"},
        h1_context={"trend": "down"},
        momentum_context={"direction": "negative"},
        volume_context={"volume_ratio": 0.5, "price_change": -0.0001},
    ))

    views = {item["view"] for item in result["perspectives"]}
    assert "BUY" in views and "SELL" in views
    assert any(item["view"] == "WAIT" for item in result["perspectives"])


@pytest.mark.parametrize(
    ("algorithm_id", "state", "expected_view"),
    [
        (
            "trend_continuation",
            {"side": "BUY", "trend": "up", "pullback": "bullish_pullback_reclaimed"},
            "BUY",
        ),
        (
            "trend_pullback",
            {"side": "SELL", "m15_trend": "down", "retest": "retest_confirmed", "pullback": "bearish_pullback_reclaimed"},
            "SELL",
        ),
        (
            "range_edge_fade",
            {"side": "BUY", "range_state": "range", "range_edge_rejection": "lower_edge_reclaimed"},
            "BUY",
        ),
        (
            "failed_breakout",
            {"side": "SELL", "breakout_state": "failed_break_up"},
            "SELL",
        ),
        (
            "breakout_continuation",
            {"side": "BUY", "breakout_state": "breakout_up_confirmed"},
            "BUY",
        ),
        (
            "volume_effort_result",
            {
                "side": "BUY",
                "volume_context": {"is_real_volume": True},
                "volume_data_provenance": "real_traded_volume",
                "effort_result_direction": "BUY",
                "volume_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "pyramiding",
            {
                "side": "BUY",
                "pyramid_state": "authorized",
                "same_thesis": True,
                "position_profit": 0.02,
                "pyramid_signal": "BUY",
            },
            "BUY",
        ),
        (
            "adverse_selection",
            {
                "side": "BUY",
                "quote_fresh": True,
                "quote_age_s": 0.2,
                "spread_pips": 0.5,
                "adverse_selection_state": "low",
                "adverse_selection_provenance": "point_in_time_quote_flow",
            },
            "WAIT",
        ),
        (
            "time_stop",
            {
                "side": "BUY",
                "elapsed_s": 5.0,
                "time_stop_s": 3.0,
                "current_executable_pnl": -0.01,
                "remaining_ev": -0.001,
                "never_green": True,
            },
            "WAIT",
        ),
        (
            "intermarket_analysis",
            {
                "side": "BUY",
                "intermarket_signal": "BUY",
                "intermarket_confirmation": "confirmed",
                "intermarket_provenance": "point_in_time_cross_asset",
                "intermarket_as_of": "2026-08-29T10:00:00Z",
                "dollar_index_direction": "down",
                "bond_direction": "up",
            },
            "BUY",
        ),
        (
            "noise_filter",
            {
                "side": "BUY",
                "noise_state": "low_noise",
                "noise_provenance": "point_in_time_quote_history",
                "quote_fresh": True,
                "quote_age_s": 0.2,
            },
            "WAIT",
        ),
        (
            "tail_risk",
            {
                "side": "BUY",
                "tail_risk_state": "controlled",
                "tail_risk_provenance": "walk_forward_net_outcomes",
                "p95_loss": -0.05,
                "risk_budget": 0.15,
            },
            "WAIT",
        ),
        (
            "event_arbitrage",
            {
                "side": "BUY",
                "event_state": "released",
                "event_as_of": "2026-08-29T10:00:00Z",
                "decision_as_of": "2026-08-29T10:00:02Z",
                "event_window_s": 15,
                "event_surprise": 1.5,
                "event_response_direction": "BUY",
                "event_response_confirmation": "confirmed",
                "event_oos_n": 40,
                "event_expectancy_net": 0.02,
                "event_provenance": "timestamped_event_study",
            },
            "BUY",
        ),
        (
            "spread_scalping",
            {
                "side": "BUY",
                "spread_scalping_state": "controlled",
                "spread_scalping_provenance": "point_in_time_quote_history",
                "two_sided_quote": True,
                "inventory_state": "flat",
                "adverse_selection_state": "low",
                "closeability": "observed",
                "net_edge": 0.01,
            },
            "WAIT",
        ),
        (
            "latency_arbitrage",
            {
                "side": "BUY",
                "latency_state": "measured",
                "venue_count": 2,
                "venue_price_discrepancy": 0.0004,
                "latency_budget_ms": 20,
                "latency_observed_ms": 5,
                "net_edge_after_cost": 0.02,
                "latency_provenance": "timestamped_multi_venue_quotes",
                "venue_timestamps_synchronized": True,
            },
            "WAIT",
        ),
        (
            "rebate_capture",
            {
                "side": "BUY",
                "rebate_state": "measured",
                "rebate_provenance": "venue_fee_schedule",
                "rebate_per_unit": 0.001,
                "transaction_cost_per_unit": 0.0005,
                "fill_probability": 0.7,
                "directional_probability": 0.6,
                "net_edge_after_cost": 0.001,
            },
            "WAIT",
        ),
        (
            "market_impact_symmetry",
            {
                "side": "BUY",
                "impact_buy": 0.0002,
                "impact_sell": -0.0002,
                "impact_observation_n": 200,
                "impact_symmetry_status": "symmetric",
                "impact_provenance": "timestamped_trade_outcomes",
            },
            "WAIT",
        ),
        (
            "al_brooks_high_low_count",
            {
                "side": "BUY",
                "bar_count_direction": "up",
                "bar_count": 2,
                "bar_count_context": "bullish pullback",
                "bar_count_trendline_break": True,
                "bar_count_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "al_brooks_wedge",
            {
                "side": "BUY",
                "wedge_reversal_direction": "BUY",
                "wedge_pushes": 3,
                "wedge_trendline_break": True,
                "wedge_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "al_brooks_failed_failure",
            {
                "side": "BUY",
                "failed_failure_direction": "BUY",
                "initial_breakout_failed": True,
                "failure_of_failure": True,
                "failed_failure_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "al_brooks_spike_channel",
            {
                "side": "BUY",
                "spike_channel_signal": "BUY",
                "spike_channel_state": "spike_then_channel",
                "spike_channel_test": "held",
                "spike_channel_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "al_brooks_double_flag",
            {
                "side": "BUY",
                "double_flag_type": "double_bottom_bull_flag",
                "double_flag_second_test": "held",
                "double_flag_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "al_brooks_range_location",
            {
                "side": "BUY",
                "range_state": "range",
                "range_location": "lower_edge",
                "range_location_provenance": "point_in_time_price_action",
                "range_location_confirmation": "observed",
            },
            "WAIT",
        ),
        (
            "momentum",
            {"side": "BUY", "momentum": 0.001, "momentum_direction": "up", "follow_through": "present"},
            "BUY",
        ),
        (
            "market_profile",
            {
                "side": "SELL",
                "market_profile": {"source": "real_volume_profile"},
                "profile_data_provenance": "real_volume_profile",
                "profile_signal": "SELL",
            },
            "SELL",
        ),
        (
            "mean_reversion",
            {"side": "BUY", "regime": "range", "zscore": -2.5},
            "BUY",
        ),
    ],
)
def test_named_book_concepts_have_dedicated_strict_perspectives(algorithm_id, state, expected_view):
    result = evaluate_module(algorithm_id, state)

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["execution_authority"] is False
    assert result["research_only"] is True


def test_named_book_concepts_fail_closed_on_missing_or_proxy_evidence():
    missing = evaluate_module("failed_breakout", {"side": "SELL", "breakout_state": "breakout_up_confirmed"})
    missing_range = evaluate_module("range_edge_fade", {"side": "BUY", "range_edge_rejection": "lower_edge_reclaimed"})
    unconfirmed_breakout = evaluate_module(
        "breakout_continuation",
        {"side": "BUY", "break_direction": "up", "breakout_confirmation": "unconfirmed"},
    )
    unconfirmed_break_state = evaluate_module(
        "breakout_continuation",
        {"side": "BUY", "breakout_state": "breakout_up"},
    )
    proxy_volume = evaluate_module(
        "volume_effort_result",
        {
            "side": "BUY",
            "volume_context": {"is_real_volume": False, "source": "tick_activity_proxy"},
            "volume_data_provenance": "tick_activity_proxy",
            "effort_result_direction": "BUY",
            "volume_confirmation": "confirmed",
        },
    )
    unsafe_pyramid = evaluate_module(
        "pyramiding",
        {
            "side": "BUY",
            "pyramid_state": "authorized",
            "same_thesis": True,
            "position_profit": -0.01,
            "pyramid_signal": "BUY",
            "risk_increase_after_loss": True,
        },
    )
    toxic_flow = evaluate_module(
        "adverse_selection",
        {
            "side": "BUY",
            "quote_fresh": True,
            "quote_age_s": 0.2,
            "spread_pips": 0.5,
            "adverse_selection_state": "toxic informed flow",
        },
    )
    missing_time_stop = evaluate_module(
        "time_stop",
        {
            "side": "BUY",
            "elapsed_s": 5.0,
            "current_executable_pnl": -0.01,
            "remaining_ev": -0.001,
            "never_green": True,
        },
    )
    synthetic_intermarket = evaluate_module(
        "intermarket_analysis",
        {
            "side": "BUY",
            "intermarket_signal": "BUY",
            "intermarket_confirmation": "confirmed",
            "intermarket_provenance": "synthetic",
            "intermarket_as_of": "2026-08-29T10:00:00Z",
            "dollar_index_direction": "down",
            "bond_direction": "up",
        },
    )
    negated_intermarket = evaluate_module(
        "intermarket_analysis",
        {
            "side": "BUY",
            "intermarket_signal": "not BUY",
            "intermarket_confirmation": "confirmed",
            "intermarket_provenance": "point_in_time_cross_asset",
            "intermarket_as_of": "2026-08-29T10:00:00Z",
            "dollar_index_direction": "down",
            "bond_direction": "up",
        },
    )
    unknown_observation = evaluate_module(
        "intermarket_analysis",
        {
            "side": "BUY",
            "intermarket_signal": "BUY",
            "intermarket_confirmation": "confirmed",
            "intermarket_provenance": "point_in_time_cross_asset",
            "intermarket_as_of": "2026-08-29T10:00:00Z",
            "dollar_index_direction": "unknown",
            "bond_direction": "up",
        },
    )
    conflicted_intermarket = evaluate_module(
        "intermarket_analysis",
        {
            "side": "BUY",
            "intermarket_signal": "BUY",
            "intermarket_confirmation": "confirmed",
            "intermarket_provenance": "point_in_time_cross_asset",
            "intermarket_as_of": "2026-08-29T10:00:00Z",
            "dollar_index_direction": "down",
            "bond_direction": "up",
            "intermarket_state": "conflicted",
        },
    )
    high_noise = evaluate_module(
        "noise_filter",
        {
            "side": "BUY",
            "noise_state": "high_noise",
            "noise_provenance": "point_in_time_quote_history",
            "quote_fresh": True,
            "quote_age_s": 0.2,
        },
    )
    numeric_noise_only = evaluate_module(
        "noise_filter",
        {"side": "BUY", "noise_ratio": 0.8, "noise_provenance": "point_in_time_quote_history"},
    )
    high_tail = evaluate_module(
        "tail_risk",
        {"side": "BUY", "tail_risk_state": "unbounded_tail", "tail_risk_provenance": "walk_forward_net_outcomes"},
    )
    numeric_tail_only = evaluate_module(
        "tail_risk",
        {"side": "BUY", "p95_loss": -0.05, "tail_risk_provenance": "walk_forward_net_outcomes"},
    )
    unreleased_event = evaluate_module(
        "event_arbitrage",
        {
            "side": "BUY",
            "event_state": "scheduled",
            "event_as_of": "2026-08-29T10:00:00Z",
            "decision_as_of": "2026-08-29T09:59:59Z",
            "event_window_s": 15,
            "event_surprise": 1.5,
            "event_response_direction": "BUY",
            "event_response_confirmation": "confirmed",
            "event_oos_n": 40,
            "event_expectancy_net": 0.02,
            "event_provenance": "timestamped_event_study",
        },
    )
    naive_spread = evaluate_module(
        "spread_scalping",
        {
            "side": "BUY",
            "spread_scalping_state": "controlled",
            "spread_scalping_provenance": "point_in_time_quote_history",
            "two_sided_quote": True,
            "inventory_state": "flat",
            "adverse_selection_state": "high",
            "closeability": "observed",
            "net_edge": 0.01,
        },
    )
    single_venue_latency = evaluate_module(
        "latency_arbitrage",
        {
            "side": "BUY",
            "latency_state": "measured",
            "venue_count": 1,
            "venue_price_discrepancy": 0.0004,
            "latency_budget_ms": 20,
            "latency_observed_ms": 5,
            "net_edge_after_cost": 0.02,
            "latency_provenance": "timestamped_multi_venue_quotes",
        },
    )
    rebate_without_forecast = evaluate_module(
        "rebate_capture",
        {
            "side": "BUY",
            "rebate_state": "measured",
            "rebate_provenance": "venue_fee_schedule",
            "rebate_per_unit": 0.001,
            "transaction_cost_per_unit": 0.0005,
            "fill_probability": 0.7,
            "net_edge_after_cost": 0.001,
        },
    )
    asymmetric_impact = evaluate_module(
        "market_impact_symmetry",
        {
            "side": "BUY",
            "impact_buy": 0.0003,
            "impact_sell": -0.0001,
            "impact_observation_n": 200,
            "impact_symmetry_status": "asymmetric",
            "impact_provenance": "timestamped_trade_outcomes",
        },
    )
    weak_bar_count = evaluate_module(
        "al_brooks_high_low_count",
        {"side": "BUY", "bar_count_direction": "up", "bar_count": 2, "bar_count_context": "bullish pullback", "bar_count_confirmation": "confirmed"},
    )
    two_push_wedge = evaluate_module(
        "al_brooks_wedge",
        {"side": "BUY", "wedge_reversal_direction": "BUY", "wedge_pushes": 2, "wedge_confirmation": "confirmed"},
    )
    unconfirmed_failed_failure = evaluate_module(
        "al_brooks_failed_failure",
        {"side": "BUY", "failed_failure_direction": "BUY", "initial_breakout_failed": True, "failure_of_failure": True},
    )
    proxy_spike_channel = evaluate_module(
        "al_brooks_spike_channel",
        {"side": "BUY", "spike_channel_signal": "BUY", "spike_channel_state": "spike_then_channel", "spike_channel_test": "held", "spike_channel_confirmation": "confirmed", "spike_channel_provenance": "synthetic"},
    )
    failed_flag_test = evaluate_module(
        "al_brooks_double_flag",
        {"side": "BUY", "double_flag_type": "double_bottom_bull_flag", "double_flag_second_test": "failed", "double_flag_confirmation": "confirmed"},
    )
    middle_range = evaluate_module(
        "al_brooks_range_location",
        {"side": "BUY", "range_state": "range", "range_location": "middle", "range_location_provenance": "point_in_time_price_action", "range_location_confirmation": "observed"},
    )
    missing_freshness = evaluate_module(
        "adverse_selection",
        {
            "side": "BUY",
            "spread_pips": 0.5,
            "adverse_selection_state": "low",
        },
    )
    proxy_profile = evaluate_module(
        "market_profile",
        {
            "side": "BUY",
            "market_profile": {"source": "tick_price_profile_proxy"},
            "profile_data_provenance": "tick_price_profile_proxy",
            "profile_signal": "BUY",
        },
    )
    nested_proxy_profile = evaluate_module(
        "market_profile",
        {
            "side": "BUY",
            "market_profile": {"source": "tick_price_profile_proxy"},
            "profile_data_provenance": "real_volume_profile",
            "profile_signal": "BUY",
        },
    )
    negated_momentum = evaluate_module(
        "momentum",
        {
            "side": "BUY",
            "momentum": 0.001,
            "momentum_direction": "not up",
            "follow_through": "present",
        },
    )
    negated_mean_reversion = evaluate_module(
        "mean_reversion",
        {
            "side": "BUY",
            "regime": "range",
            "zscore": -2.5,
            "mean_reversion_signal": "not buy",
        },
    )
    trend_mean_reversion = evaluate_module(
        "mean_reversion",
        {"side": "BUY", "regime": "trend", "zscore": -2.5},
    )

    assert missing["view"] == "WAIT"
    assert missing_range["applicability"] == "MISSING_DATA"
    assert unconfirmed_breakout["view"] == "WAIT"
    assert unconfirmed_break_state["view"] == "WAIT"
    assert proxy_volume["view"] == "WAIT"
    assert unsafe_pyramid["view"] == "WAIT"
    assert toxic_flow["view"] == "WAIT"
    assert toxic_flow["adverse_selection_assessment"] == "HIGH"
    assert missing_freshness["adverse_selection_assessment"] == "UNKNOWN"
    assert missing_time_stop["applicability"] == "MISSING_DATA"
    assert synthetic_intermarket["view"] == "WAIT"
    assert synthetic_intermarket["intermarket_assessment"] == "UNKNOWN"
    assert negated_intermarket["view"] == "WAIT"
    assert unknown_observation["applicability"] == "MISSING_DATA"
    assert conflicted_intermarket["view"] == "WAIT"
    assert conflicted_intermarket["intermarket_assessment"] == "CONFLICTED"
    assert high_noise["view"] == "WAIT"
    assert high_noise["noise_assessment"] == "HIGH"
    assert numeric_noise_only["noise_assessment"] == "UNKNOWN"
    assert high_tail["view"] == "WAIT"
    assert high_tail["tail_risk_assessment"] == "HIGH"
    assert numeric_tail_only["tail_risk_assessment"] == "UNKNOWN"
    assert unreleased_event["view"] == "WAIT"
    assert naive_spread["spread_scalping_assessment"] == "HIGH_RISK"
    assert single_venue_latency["latency_assessment"] == "NOT_APPLICABLE"
    assert rebate_without_forecast["rebate_assessment"] == "UNKNOWN"
    assert asymmetric_impact["impact_symmetry_assessment"] == "ASYMMETRIC"
    assert weak_bar_count["view"] == "WAIT"
    assert two_push_wedge["view"] == "WAIT"
    assert unconfirmed_failed_failure["view"] == "WAIT"
    assert proxy_spike_channel["view"] == "WAIT"
    assert failed_flag_test["view"] == "WAIT"
    assert middle_range["range_location_assessment"] == "MIDDLE"
    assert proxy_profile["view"] == "WAIT"
    assert nested_proxy_profile["view"] == "WAIT"
    assert negated_momentum["view"] == "WAIT"
    assert negated_mean_reversion["view"] == "WAIT"
    assert trend_mean_reversion["applicability"] == "NOT_APPLICABLE"
    assert proxy_volume["applicability"] == "APPLICABLE"
