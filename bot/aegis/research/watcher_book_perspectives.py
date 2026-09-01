"""Compatibility/catalog API for the human-authored Watcher algorithms.

The executable perspectives live in :mod:`watcher_algorithms`, one module per
algorithm. This module keeps the older public API used by the Watcher and
reports book-review coverage; it does not contain a second copy of the rules.
"""
from __future__ import annotations

from typing import Any, Mapping

from .book_strategy_evidence import evaluate_strategy_evidence
from .book_strategy_extraction import source_label_from_path
from .watcher_algorithms import ALGORITHM_MODULES, evaluate_all, evaluate_module


BOOK_REVIEW_COVERAGE = {
    "Algorithmic Trading and Quantitative Strategies": "PARTIALLY_REVIEWED",
    "Technical Analysis of the Financial Markets": "PARTIALLY_REVIEWED_SCANNED",
    "Technical Analysis of Stock Trends": "PARTIALLY_REVIEWED",
    "The Microstructure of Financial Markets": "REVIEWED",
    "The Art and Science of Technical Analysis": "REVIEWED",
    "Statistical Arbitrage": "PARTIALLY_REVIEWED",
    "Inside the Black Box": "PARTIALLY_REVIEWED",
    "Quantitative Momentum": "PARTIALLY_REVIEWED",
    "Building Winning Algorithmic Trading Systems": "REVIEWED",
    "Reading Price Charts Bar by Bar": "REVIEWED",
    "The New Trading for a Living": "REVIEWED",
    "Evidence-Based Technical Analysis": "REVIEWED",
    "Quantitative Trading": "REVIEWED",
    "High-Frequency Trading": "REVIEWED",
    "Markets in Profile": "REVIEWED",
    "Market Microstructure: Confronting Many Viewpoints": "REVIEWED",
    "Algorithmic Trading (Winning Strategies and Their Rationale)": "PARTIALLY_REVIEWED",
    "A Complete Guide to Volume Price Analysis": "REVIEWED",
    "Algorithmic Trading and DMA": "PARTIALLY_REVIEWED_SCANNED",
    "Forex Price Action Scalping": "REVIEWED",
    "Encyclopedia of Chart Patterns": "REVIEWED",
    "Day Trading and Swing Trading the Currency Market": "REVIEWED",
    "Machine Trading": "REVIEWED",
    "Mind Over Markets": "REVIEWED",
    "Japanese Candlestick Charting Techniques": "PARTIALLY_REVIEWED_SCANNED",
    "Trades, Quotes and Prices": "REVIEWED",
    "Empirical Market Microstructure": "REVIEWED",
    "Mastering the Trade": "PARTIALLY_REVIEWED",
    "High Probability Trading": "PARTIALLY_REVIEWED",
    "Advances in Financial Machine Learning": "PARTIALLY_REVIEWED",
    "Market Microstructure Theory": "PARTIALLY_REVIEWED_SCANNED",
    "An Introduction to High-Frequency Finance": "PARTIALLY_REVIEWED_SCANNED",
    "Python for Finance": "PARTIALLY_REVIEWED",
    "Active Portfolio Management": "PARTIALLY_REVIEWED",
    "Systematic Trading": "REVIEWED",
    "The Economics of Financial Markets": "PARTIALLY_REVIEWED",
    "Machine Learning for Algorithmic Trading": "PARTIALLY_REVIEWED",
    "Quantitative Finance For Dummies": "PARTIALLY_REVIEWED",
    "Trading Price Action Trading Ranges": "PARTIALLY_REVIEWED_SCANNED",
    "Forex Patterns & Probabilities": "PARTIALLY_REVIEWED",
    "Brian Anderson — The 1 Hour Trade": "PARTIALLY_REVIEWED",
    "Steve Nison — Beyond Candlesticks": "PARTIALLY_REVIEWED_SCANNED",
    "The Price in Time — Forex Strategy": "REVIEWED",
    "The 10XROI Trading System": "REVIEWED",
    "Following the Trend — Diversified Managed Futures Trading": "PARTIALLY_REVIEWED",
    "Beat the Forex Dealer": "PARTIALLY_REVIEWED_SCANNED",
    "Developing High-Frequency Trading Systems": "PARTIALLY_REVIEWED_SCANNED",
    "Elliott Wave Principle": "PARTIALLY_REVIEWED_SCANNED",
    "Getting Started in Technical Analysis": "PARTIALLY_REVIEWED_SCANNED",
    "Hands-On Machine Learning for Algorithmic Trading": "PARTIALLY_REVIEWED_SCANNED",
    "How to Day Trade for a Living": "PARTIALLY_REVIEWED_SCANNED",
    "How to Make Profits in Commodities": "PARTIALLY_REVIEWED_SCANNED",
    "Market Structure": "PARTIALLY_REVIEWED",
    "Modelling Asset Prices for Algorithmic and High-Frequency Trading": "PARTIALLY_REVIEWED_SCANNED",
    "Price Action Breakdown": "PARTIALLY_REVIEWED_SCANNED",
    "Profitable Forex Trading Using High and Low Risk Strategies": "PARTIALLY_REVIEWED_SCANNED",
    "Pyramiding": "REVIEWED",
    "Quantum Finance": "PARTIALLY_REVIEWED",
    "Quantum Trading": "PARTIALLY_REVIEWED",
    "Reminiscences of a Stock Operator": "PARTIALLY_REVIEWED_SCANNED",
    "Risk Basics": "PARTIALLY_REVIEWED",
    "Steidlmayer on Markets": "PARTIALLY_REVIEWED_SCANNED",
    "Stock Market Wizards": "PARTIALLY_REVIEWED_SCANNED",
    "Stock Trading & Investing Using Volume Price Analysis": "PARTIALLY_REVIEWED_SCANNED",
    "The Definitive Guide to Point and Figure": "PARTIALLY_REVIEWED_SCANNED",
    "The Disciplined Trader": "PARTIALLY_REVIEWED",
    "The Holy Grail Forex Trading System": "PARTIALLY_REVIEWED_SCANNED",
    "The Man Who Solved the Market": "PARTIALLY_REVIEWED_SCANNED",
    "The Mental Game of Trading": "PARTIALLY_REVIEWED",
    "The New Market Wizards": "PARTIALLY_REVIEWED_SCANNED",
    "The Ultimate Forex Trading System": "PARTIALLY_REVIEWED_SCANNED",
    "Trade the Price Action": "REVIEWED",
    "Trade Your Way to Financial Freedom": "PARTIALLY_REVIEWED_SCANNED",
    "Trading and Exchanges": "PARTIALLY_REVIEWED_SCANNED",
    "Trading in the Zone": "PARTIALLY_REVIEWED",
    "Trading with Intermarket Analysis": "PARTIALLY_REVIEWED_SCANNED",
    "Winning the Trading Game": "PARTIALLY_REVIEWED",
}


# This is a human-authored research crosswalk, not an extraction result. A
# book may inform several perspectives; a perspective does not imply that the
# book supplied a complete executable rule.
BOOK_ALGORITHM_COVERAGE = {
    "Algorithmic Trading and Quantitative Strategies": ("volatility_breakout", "statistical_arbitrage", "volatility_regime", "realized_volatility", "correlation_context", "validation_integrity", "purged_walk_forward", "time_series_forecasting", "forecast_combination", "velu_omnibus_rule", "velu_fair_value_residual", "velu_sign_magnitude_decomposition", "velu_alexander_filter", "velu_sma_rule", "velu_ewa_rule", "velu_bwma_bollinger_rule", "velu_moving_average_oscillator", "velu_rsi_reversal", "velu_kernel_pattern", "velu_characteristic_time", "velu_intraday_profile", "velu_volume_return_filter", "velu_square_root_cost_hurdle", "velu_distance_pairs", "velu_microstructure_noise_sampling", "velu_duration_intensity", "vwap_execution", "twap_execution", "participation_execution", "portfolio_allocation"),
    "Technical Analysis of the Financial Markets": ("trend_structure", "support_resistance", "chart_patterns", "moving_average_context", "oscillator_signal", "rsi_reversal", "stochastic_reversal", "channel_analysis", "bollinger_bands", "macd_signal", "atr_regime", "fibonacci_retracement", "pivot_levels", "donchian_breakout", "adx_trend_strength", "keltner_channel", "ichimoku_context", "cci_reversal", "williams_reversal", "vwap_context", "obv_volume", "rate_of_change", "parabolic_sar", "elliott_wave", "harmonic_patterns", "gann_levels", "relative_strength", "point_and_figure", "cycle_analysis", "volume_profile_context", "volume_open_interest", "murphy_percentage_retracement", "murphy_speed_resistance_lines"),
    "Technical Analysis of Stock Trends": ("edwards_magee_head_shoulders", "edwards_magee_triangle_breakout", "edwards_magee_gap_classification", "edwards_magee_support_resistance_flip", "edwards_magee_channel_deterioration", "edwards_magee_one_day_reversal", "edwards_magee_selling_climax", "edwards_magee_trendline_penetration", "edwards_magee_broadening_breakout", "edwards_magee_key_reversal_day", "edwards_magee_spike_reversal", "edwards_magee_runaway_day", "edwards_magee_dow_confirmation", "edwards_magee_basing_points_stop", "edwards_magee_breakout_confirmation", "edwards_magee_climactic_volume_stop", "edwards_magee_defensive_exit", "support_resistance", "chart_patterns", "channel_analysis", "breakout_quality", "volume_price"),
    "The Microstructure of Financial Markets": ("microstructure", "liquidity_sweep", "scalping_execution", "volatility_regime", "dejong_roll_spread_estimator", "dejong_spread_decomposition", "dejong_duration_weighted_spread"),
    "The Art and Science of Technical Analysis": ("grimes_pullback_quality", "grimes_three_push_exhaustion", "trend_structure", "trend_continuation", "trend_pullback", "breakout_quality", "breakout_continuation", "failed_breakout", "pullback_retest", "support_resistance", "channel_analysis", "volatility_breakout", "wyckoff_spring_upthrust", "trade_management", "noise_filter"),
    "Statistical Arbitrage": ("pole_spread_reversion", "pole_popcorn_reversion", "pole_turning_point_event", "pole_event_pair_selection", "pole_staged_spread_entries", "pole_forecast_monitoring", "pole_cuscore_change_point", "pole_75_percent_reversion", "pole_multi_step_reversion", "pole_spread_margin", "pole_evolutionary_operation", "pole_catastrophe_entry", "pole_catastrophe_exit", "statistical_arbitrage", "mean_reversion", "mean_reversion_vs_momentum", "correlation_context", "validation_integrity", "cointegration_pairs", "bayesian_pairs", "kalman_filter", "time_series_forecasting"),
    "Inside the Black Box": ("validation_integrity", "trade_management", "machine_learning_signal", "portfolio_allocation", "narang_horizon_specification", "narang_conditional_alpha", "narang_linear_alpha_blend", "narang_alpha_rotation", "narang_run_frequency_tradeoff", "narang_cost_hurdle", "narang_liquidity_impact", "narang_forecast_bucket_monotonicity", "narang_time_decay", "narang_parameter_robustness", "narang_portfolio_value_add", "narang_risk_monitoring", "narang_regime_change_warning", "narang_exogenous_shock_filter", "narang_contagion_exposure"),
    "Quantitative Momentum": ("gray_vogel_path_momentum", "gray_vogel_rebalance_tradeoff", "gray_vogel_lookback_regime", "gray_vogel_lottery_avoidance", "gray_vogel_seasonality_timing", "gray_vogel_52_week_high", "gray_vogel_absolute_strength", "gray_vogel_momentum_stop_loss", "gray_vogel_time_series_overlay", "gray_vogel_fundamental_momentum", "momentum", "momentum_exhaustion", "trend_structure", "validation_integrity", "rate_of_change", "cross_sectional_momentum", "factor_momentum"),
    "Building Winning Algorithmic Trading Systems": ("validation_integrity", "trade_management", "volatility_breakout", "position_sizing", "pyramiding", "tail_risk", "davey_euro_night_strategy", "davey_euro_day_strategy", "davey_three_bar_baseline"),
    "Reading Price Charts Bar by Bar": ("trend_structure", "trend_continuation", "trend_pullback", "breakout_quality", "breakout_continuation", "failed_breakout", "pullback_retest", "price_action_candles", "al_brooks_second_entry", "al_brooks_high_low_count", "al_brooks_wedge", "al_brooks_failed_failure", "al_brooks_spike_channel", "al_brooks_double_flag", "al_brooks_range_location", "kangaroo_tail", "range_edge_rejection", "range_edge_fade", "support_resistance", "trade_management"),
    "The New Trading for a Living": ("elder_triple_screen", "elder_impulse_censorship", "elder_force_index_pullback", "elder_safezone_stop", "higher_timeframe_alignment", "trend_structure", "oscillator_signal", "rsi_reversal", "stochastic_reversal", "volume_price", "divergence", "risk_reward_geometry", "trade_management", "pyramiding", "macd_signal", "atr_regime", "adx_trend_strength", "keltner_channel", "ichimoku_context", "cci_reversal", "williams_reversal", "triple_screen", "force_index", "elder_impulse"),
    "Evidence-Based Technical Analysis": ("validation_integrity", "noise_filter", "tail_risk", "event_arbitrage", "rebate_capture", "aronson_objective_rule_definition", "aronson_reality_check", "aronson_practical_significance", "aronson_detrended_rule_return"),
    "Quantitative Trading": ("mean_reversion", "mean_reversion_vs_momentum", "statistical_arbitrage", "volatility_regime", "stochastic_volatility", "correlation_context", "validation_integrity", "bollinger_bands", "bollinger_pair_mean_reversion", "atr_regime", "cointegration_pairs", "bayesian_pairs", "kalman_filter", "rate_of_change", "time_series_forecasting", "forecast_combination", "ewmac_trend_following", "chan_exit_policy", "chan_hft_quote_data_requirements", "portfolio_allocation", "time_stop"),
    "High-Frequency Trading": ("aldridge_pair_dislocation", "aldridge_triangular_arbitrage", "aldridge_uip_arbitrage", "aldridge_index_composition_arbitrage", "aldridge_volatility_curve_arbitrage", "aldridge_futures_basis_arbitrage", "aldridge_futures_etf_arbitrage", "aldridge_dual_class_arbitrage", "aldridge_risk_arbitrage", "adverse_selection", "microstructure", "scalping_execution", "volatility_regime", "realized_volatility", "garch_volatility", "liquidity_sweep", "news_event_risk", "order_book_imbalance", "hawkes_order_flow", "market_making_inventory", "market_impact", "time_stop", "noise_filter", "event_arbitrage", "spread_scalping", "latency_arbitrage", "rebate_capture", "market_impact_symmetry", "aldridge_order_flow_autocorrelation", "aldridge_trade_aggressiveness", "aldridge_bid_ask_bounce_filter", "aldridge_quote_duration", "aldridge_trade_direction_uncertainty", "aldridge_quote_matching"),
    "Markets in Profile": ("dalton_trend_day_integrity", "dalton_auction_point_retest", "dalton_day_structure", "dalton_failed_range_extension", "dalton_single_print_retest", "market_profile", "market_profile_auction", "initial_balance_profile", "range_edge_rejection", "opening_range", "support_resistance", "higher_timeframe_alignment", "volume_profile_context"),
    "Market Microstructure: Confronting Many Viewpoints": ("microstructure", "liquidity_sweep", "volatility_regime", "realized_volatility", "order_book_imbalance", "hawkes_order_flow", "market_making_inventory", "market_impact"),
    "Algorithmic Trading (Winning Strategies and Their Rationale)": ("chan_linear_mean_reversion", "chan_kalman_mean_reversion", "chan_cross_sectional_mean_reversion", "chan_time_series_momentum", "chan_alexander_filter", "chan_opening_gap_momentum", "chan_news_drift", "chan_stop_order_momentum", "chan_order_flow_momentum", "chan_bid_ask_imbalance", "chan_ratio_trade", "chan_ticking_quote_matching", "chan_leveraged_rebalance_momentum", "chan_half_kelly_cap", "chan_adf_mean_reversion", "chan_hurst_stationarity", "chan_variance_ratio_stationarity", "chan_mean_reversion_half_life", "chan_cadf_cointegration", "chan_johansen_cointegration", "statistical_arbitrage", "mean_reversion_vs_momentum", "volatility_breakout", "bollinger_pair_mean_reversion", "validation_integrity"),
    "A Complete Guide to Volume Price Analysis": ("volume_price", "volume_effort_result", "volume_spread_analysis", "wyckoff_spring_upthrust", "breakout_quality", "breakout_continuation", "failed_breakout", "volatility_breakout", "donchian_breakout", "vwap_context", "obv_volume", "volume_profile_context", "vpa_long_legged_doji", "vpa_narrow_spread_high_volume", "vpa_stopping_volume", "vpa_topping_out_volume", "vpa_breakout_volume_validation", "vpa_trend_effort_confirmation"),
    "Algorithmic Trading and DMA": ("adverse_selection", "microstructure", "liquidity_sweep", "scalping_execution", "order_book_imbalance", "market_making_inventory", "vwap_execution", "twap_execution", "participation_execution", "latency_arbitrage", "rebate_capture", "spread_scalping", "johnson_implementation_shortfall", "johnson_adaptive_shortfall", "johnson_price_inline", "johnson_liquidity_seeking", "johnson_order_difficulty"),
    "Forex Price Action Scalping": ("scalping_execution", "trend_continuation", "trend_pullback", "breakout_quality", "breakout_continuation", "failed_breakout", "pullback_retest", "channel_analysis", "range_edge_rejection", "range_edge_fade", "moving_average_context", "donchian_breakout", "noise_filter", "volman_double_doji_break", "volman_first_break", "volman_second_break", "volman_block_break", "volman_range_break", "volman_inside_range_break", "volman_advanced_range_break", "volman_tipping_point_exit", "volman_unfavorable_path_filter", "volman_pullback_quality"),
    "Encyclopedia of Chart Patterns": ("bulkowski_double_bottom", "bulkowski_double_top", "bulkowski_flag_breakout", "bulkowski_ascending_triangle", "bulkowski_falling_wedge", "bulkowski_broadening_bottom", "bulkowski_broadening_top", "bulkowski_right_angled_ascending", "bulkowski_right_angled_descending", "bulkowski_ascending_broadening_wedge", "bulkowski_descending_broadening_wedge", "bulkowski_barr_bottom", "bulkowski_barr_top", "bulkowski_cup_with_handle", "bulkowski_inverted_cup_with_handle", "bulkowski_diamond_bottom", "bulkowski_diamond_top", "bulkowski_high_tight_flag", "bulkowski_gap", "bulkowski_head_shoulders_bottom", "bulkowski_complex_head_shoulders_bottom", "bulkowski_head_shoulders_top", "bulkowski_complex_head_shoulders_top", "bulkowski_horn_bottom", "bulkowski_horn_top", "bulkowski_island_reversal", "bulkowski_long_island", "bulkowski_measured_move_down", "bulkowski_measured_move_up", "bulkowski_pennant", "bulkowski_pipe_bottom", "bulkowski_pipe_top", "bulkowski_rectangle_bottom", "bulkowski_rectangle_top", "bulkowski_rounding_bottom", "bulkowski_rounding_top", "bulkowski_ascending_scallop", "bulkowski_ascending_inverted_scallop", "bulkowski_descending_scallop", "bulkowski_descending_inverted_scallop", "bulkowski_descending_triangle", "bulkowski_symmetrical_triangle", "bulkowski_rising_wedge", "bulkowski_triple_bottom", "bulkowski_triple_top", "bulkowski_three_falling_peaks", "bulkowski_three_rising_valleys", "bulkowski_dead_cat_bounce", "bulkowski_inverted_dead_cat_bounce", "bulkowski_earnings_surprise_good", "bulkowski_earnings_surprise_bad", "bulkowski_fda_drug_approval", "bulkowski_earnings_flag", "bulkowski_same_store_sales_good", "bulkowski_same_store_sales_bad", "bulkowski_stock_downgrade", "bulkowski_stock_upgrade", "chart_patterns", "candlestick_patterns", "point_and_figure", "breakout_quality", "validation_integrity"),
    "Day Trading and Swing Trading the Currency Market": ("lien_intraday_range_reversal", "lien_medium_term_breakout", "lien_double_zero_fade", "lien_wait_for_real_deal", "lien_fader", "lien_filter_false_breakout", "lien_channel_breakout", "lien_perfect_order", "lien_short_term_momentum_20_100", "lien_proactive_news", "lien_reactive_news", "lien_combined_news", "lien_high_probability_turn", "lien_two_day_low_stop", "lien_two_stage_profit_management", "session_liquidity", "news_event_risk", "event_arbitrage", "correlation_context", "intermarket_analysis", "moving_average_context", "channel_analysis", "opening_range", "pivot_levels", "vwap_context", "seasonality_context", "fundamental_macro", "sentiment_positioning", "carry_rule", "relative_strength"),
    "Machine Trading": ("momentum", "statistical_arbitrage", "volatility_regime", "realized_volatility", "stochastic_volatility", "validation_integrity", "trade_management", "macd_signal", "atr_regime", "rate_of_change", "cointegration_pairs", "bayesian_pairs", "kalman_filter", "time_series_forecasting", "forecast_combination", "ewmac_trend_following", "carry_rule", "random_forest_signal", "machine_learning_signal", "chan_bulk_volume_order_flow", "portfolio_allocation"),
    "Mind Over Markets": ("dalton_trend_day_integrity", "dalton_auction_point_retest", "dalton_day_structure", "dalton_failed_range_extension", "dalton_single_print_retest", "market_profile", "market_profile_auction", "initial_balance_profile", "range_edge_rejection", "opening_range", "volume_profile_context"),
    "Japanese Candlestick Charting Techniques": ("price_action_candles", "candlestick_patterns", "divergence", "support_resistance"),
    "Trades, Quotes and Prices": ("adverse_selection", "microstructure", "liquidity_sweep", "scalping_execution", "order_book_imbalance", "market_impact_symmetry"),
    "Empirical Market Microstructure": ("microstructure", "liquidity_sweep", "validation_integrity", "order_book_imbalance", "market_impact_symmetry"),
    "Mastering the Trade": ("carter_scalper_alert", "carter_tick_extreme_fade", "carter_tick_flow_follow", "carter_anchor_squeeze", "carter_brick_reversal", "carter_holp_lohp", "carter_end_of_day_fade", "carter_ema_propulsion", "carter_opening_gap_fade", "carter_pivot_play", "carter_atr_mean_reversion", "carter_352_play", "carter_multisetup_confirmation", "carter_tick_price_divergence", "carter_tick_noise_regime", "chart_patterns", "volatility_breakout", "ttm_squeeze", "moving_average_context", "channel_analysis", "opening_range", "fibonacci_retracement", "pivot_levels", "elliott_wave", "harmonic_patterns", "gann_levels", "fundamental_macro", "ten_period_sd_breakout"),
    "High Probability Trading": ("link_ten_period_breakout", "link_trendline_buffer_breakout", "link_opening_range_breakout_30m", "link_reversal_day", "link_double_top_bottom_reversal", "link_pain_reversal", "link_key_number_reversal", "link_multi_timeframe_confirmation", "link_news_reaction_fade", "link_stochastic_wave_entry", "link_stochastic_cross_entry", "link_stochastic_extreme_retest", "link_rsi_fifty_line_entry", "link_rsi_extreme_exit", "link_rsi_pattern_break", "link_macd_signal_line_entry", "link_adx_regime_switch", "link_stochastic_failed_move", "link_trend_retracement_entry", "link_atr_risk_feasibility", "link_stop_discipline", "support_resistance", "risk_reward_geometry", "trade_management", "rsi_reversal", "stochastic_reversal", "cci_reversal", "williams_reversal", "ten_period_sd_breakout", "ttm_squeeze"),
    "Advances in Financial Machine Learning": ("validation_integrity", "purged_walk_forward", "deprado_sample_uniqueness", "deprado_sequential_bootstrap", "deprado_combinatorial_purged_cv", "deprado_probabilistic_sharpe", "deprado_deflated_sharpe", "deprado_strategy_failure_probability", "deprado_cusum_filter", "deprado_entropy", "deprado_tick_imbalance_bar", "deprado_volume_imbalance_bar", "deprado_dollar_imbalance_bar", "deprado_tick_runs_bar", "deprado_volume_runs_bar", "deprado_dollar_runs_bar", "deprado_tick_bar", "deprado_volume_bar", "deprado_dollar_bar", "triple_barrier_label", "fractional_differentiation", "bet_sizing", "feature_importance_stability", "meta_labeling", "momentum_exhaustion", "volatility_regime", "machine_learning_signal", "random_forest_signal", "forecast_combination", "time_stop", "tail_risk"),
    "Market Microstructure Theory": ("microstructure", "liquidity_sweep", "volatility_regime"),
    "An Introduction to High-Frequency Finance": ("volatility_regime", "realized_volatility", "microstructure", "scalping_execution"),
    "Python for Finance": ("validation_integrity",),
    "Active Portfolio Management": ("correlation_context", "statistical_arbitrage", "volatility_regime", "stochastic_volatility", "validation_integrity", "portfolio_allocation", "risk_parity_allocation", "pca_eigenportfolio", "fundamental_law", "factor_momentum", "bet_sizing", "sentiment_positioning", "grinold_information_horizon", "grinold_trade_utility", "grinold_fundamental_law", "grinold_alpha_scaling", "grinold_turnover_frontier"),
    "Systematic Trading": ("momentum", "trend_structure", "turtle_breakout", "volatility_regime", "realized_volatility", "volatility_targeting", "trade_management", "pyramiding", "validation_integrity", "purged_walk_forward", "atr_regime", "donchian_breakout", "adx_trend_strength", "keltner_channel", "rate_of_change", "ewmac_trend_following", "carry_rule", "ab_system", "carver_forecast_cap", "carver_position_inertia", "carver_speed_limit", "position_sizing", "seasonality_context", "portfolio_allocation", "risk_parity_allocation", "forecast_combination", "tail_risk"),
    "The Economics of Financial Markets": ("correlation_context", "news_event_risk", "validation_integrity", "fundamental_macro", "sentiment_positioning"),
    "Machine Learning for Algorithmic Trading": ("validation_integrity", "purged_walk_forward", "triple_barrier_label", "fractional_differentiation", "bet_sizing", "feature_importance_stability", "meta_labeling", "momentum_exhaustion", "volatility_regime", "stochastic_volatility", "machine_learning_signal", "random_forest_signal", "time_series_forecasting", "forecast_combination", "pca_eigenportfolio"),
    "Quantitative Finance For Dummies": ("risk_reward_geometry", "validation_integrity", "portfolio_allocation", "volatility_targeting", "position_sizing", "time_series_forecasting"),
    "Trading Price Action Trading Ranges": ("brooks_breakout_pullback_test", "brooks_barbwire_filter", "brooks_breakout_mode", "brooks_failed_breakout_reversal", "brooks_measured_move_projection", "brooks_shrinking_stairs", "brooks_micro_measuring_gap", "brooks_always_in_mode", "brooks_trader_equation", "brooks_two_reasons_entry", "brooks_timeframe_discipline", "mean_reversion", "range_edge_rejection", "range_edge_fade", "market_profile_auction", "support_resistance", "price_action_candles", "fibonacci_retracement", "failed_breakout", "al_brooks_high_low_count", "al_brooks_wedge", "al_brooks_failed_failure", "al_brooks_spike_channel", "al_brooks_double_flag", "al_brooks_range_location"),
    "Forex Patterns & Probabilities": ("ponsi_level_bounce", "ponsi_intraday_breakout", "ponsi_pennant_continuation", "ponsi_round_number_bounce", "ponsi_boomerang_fade", "ponsi_ema_trend_technique", "ponsi_squeeze_play", "ponsi_multitimeframe_pullback", "ponsi_fibonacci_trend_reentry", "ponsi_price_action_level", "ponsi_round_trip", "ponsi_interest_rate_edge", "trend_structure", "support_resistance", "volatility_breakout", "failed_breakout", "range_edge_fade", "session_liquidity", "risk_reward_geometry"),
    "Brian Anderson — The 1 Hour Trade": ("anderson_high_volume_runner", "anderson_conditional_bracket", "opening_range", "volume_price", "higher_timeframe_alignment", "risk_reward_geometry"),
    "Steve Nison — Beyond Candlesticks": ("nison_three_line_break", "nison_renko_trend", "nison_kagi_yang_yin", "nison_disparity_reversal", "nison_hammer_hanging_man", "nison_shooting_star", "nison_doji_confirmation", "nison_two_line_reversal", "nison_three_line_star", "nison_spring_upthrust", "nison_last_engulfing", "nison_window_context", "nison_three_windows", "nison_record_sessions", "nison_harami", "nison_harami_cross", "nison_two_black_gapping", "nison_gapping_doji", "nison_extra_line_break_confirmation", "nison_three_line_neck", "nison_kagi_double_window", "nison_kagi_tweezers", "nison_kagi_three_buddha", "candlestick_patterns", "support_resistance", "divergence"),
    "The Price in Time — Forex Strategy": ("price_in_time_ntz_breakout", "price_in_time_ntz_projection", "price_in_time_range_cycle", "price_in_time_pending_order", "price_in_time_trade_management_models", "price_in_time_opening_price", "price_in_time_session_filter", "price_in_time_anomaly_filter", "opening_range", "session_liquidity", "risk_reward_geometry", "time_stop"),
    "The 10XROI Trading System": ("thomas_push_pull_10xroi", "thomas_ma_momentum_filter", "thomas_break_even_after_pullback", "thomas_fixed_r_target", "thomas_breakout_context", "thomas_parabolic_exhaustion_exit", "support_resistance", "trend_continuation", "risk_reward_geometry", "trade_management"),
    "Following the Trend — Diversified Managed Futures Trading": ("clenow_dual_ema_breakout", "clenow_regime_filter", "clenow_atr_impact_sizing", "clenow_currency_exposure", "clenow_countertrend_pullback", "clenow_term_structure_carry", "clenow_core_breakout", "clenow_core_exit", "clenow_volatility_trailing_stop", "clenow_style_diversification", "turtle_breakout", "ewmac_trend_following", "volatility_targeting", "position_sizing", "tail_risk"),
    "Beat the Forex Dealer": ("silvani_retail_contrarian", "silvani_rolling_pivot_filter", "silvani_friday_stop_run", "sentiment_positioning", "adverse_selection", "news_event_risk", "validation_integrity"),
    "Developing High-Frequency Trading Systems": ("developing_hft_flow_exhaustion", "developing_hft_liquidity_depth", "developing_hft_volatility_clustering", "developing_hft_stat_arb_dislocation", "developing_hft_news_impact", "microstructure", "scalping_execution", "latency_arbitrage", "market_impact", "order_book_imbalance", "validation_integrity"),
    "Elliott Wave Principle": ("elliott_wave", "elliott_impulse_rules", "elliott_wave_three_extension", "elliott_diagonal_rules", "elliott_corrective_structure", "elliott_alternation", "chart_patterns", "trend_structure", "support_resistance", "validation_integrity"),
    "Getting Started in Technical Analysis": ("trend_structure", "support_resistance", "chart_patterns", "price_action_candles", "oscillator_signal", "moving_average_context", "schwager_ma_turn_filter", "schwager_range_breakout_confirmation", "schwager_range_participation_filter", "schwager_restrictive_reversal_day", "schwager_bull_bear_trap", "schwager_false_trend_breakout", "schwager_filled_gap_failure", "schwager_spike_extreme_failure", "schwager_wide_range_day_failure", "schwager_counter_flag_failure", "schwager_minor_reaction_reentry", "schwager_long_ma_reaction", "schwager_oscillator_price_confirmation", "schwager_trend_adjusted_oscillator", "schwager_island_reversal_validation", "schwager_equity_deterioration_warning", "schwager_record_extreme_continuation", "schwager_narrow_consolidation_bias", "schwager_news_non_followthrough_reversal", "validation_integrity"),
    "Hands-On Machine Learning for Algorithmic Trading": ("validation_integrity", "purged_walk_forward", "triple_barrier_label", "meta_labeling", "random_forest_signal", "feature_importance_stability", "forecast_combination", "bet_sizing"),
    "How to Day Trade for a Living": ("aziz_abcd_pattern", "aziz_bull_flag_momentum", "aziz_red_to_green", "aziz_bhod", "aziz_bottom_reversal", "aziz_top_reversal", "aziz_moving_average_trend", "aziz_vwap_control", "aziz_stock_in_play_scanner", "aziz_premarket_gapper_scanner", "aziz_relative_volume_independence", "aziz_reversal_market_context", "aziz_opening_range_breakout", "opening_range", "vwap_context", "volume_price", "momentum", "risk_reward_geometry", "trade_management", "validation_integrity"),
    "How to Make Profits in Commodities": ("gann_reverse_signal_day", "gann_higher_tops_bottoms", "gann_halfway_point", "gann_repeated_level_reversal", "gann_secondary_reaction", "gann_fourth_level_reversal", "gann_levels", "cycle_analysis", "trend_structure", "support_resistance", "time_series_forecasting", "validation_integrity"),
    "Market Structure": ("trend_structure", "support_resistance", "chart_patterns", "range_edge_rejection", "breakout_quality"),
    "Modelling Asset Prices for Algorithmic and High-Frequency Trading": ("cartea_regime_rebate_safety", "cartea_inventory_skew", "cartea_state_intensity", "cartea_quote_freshness_guard", "hawkes_order_flow", "market_making_inventory", "microstructure", "realized_volatility", "market_impact", "validation_integrity"),
    "Price Action Breakdown": ("damir_value_rejection_sequence", "damir_value_location_guideline", "damir_value_health_warning", "trend_structure", "support_resistance", "price_action_candles", "chart_patterns", "breakout_quality", "pullback_retest", "risk_reward_geometry"),
    "Profitable Forex Trading Using High and Low Risk Strategies": ("trend_structure", "rsi_reversal", "stochastic_reversal", "macd_signal", "divergence", "risk_reward_geometry", "trade_management", "brown_ma_stack_filter", "brown_band_signal_filter", "brown_structural_stop_buffer", "brown_qmp_filter_trigger", "brown_macd_zero_filter", "brown_qqe_filter", "brown_multi_ma_alignment", "brown_trendline_break_reentry", "brown_divergence_type_filter", "brown_bollinger_trade_management"),
    "Pyramiding": ("pyramiding", "pyramiding_risk_lock", "trade_management", "position_sizing", "risk_reward_geometry", "tail_risk"),
    "Quantum Finance": ("validation_integrity", "time_series_forecasting", "portfolio_allocation", "quantum_finance_scenario_stress"),
    "Quantum Trading": ("validation_integrity", "time_series_forecasting", "cycle_analysis", "portfolio_allocation", "oreste_qpl_interaction", "oreste_entelechy_confluence", "oreste_time_price_confluence", "oreste_volatility_scaled_risk"),
    "Reminiscences of a Stock Operator": ("trend_structure", "trend_continuation", "pyramiding", "position_sizing", "trade_management", "validation_integrity"),
    "Risk Basics": ("risk_reward_geometry", "position_sizing", "portfolio_allocation", "tail_risk", "validation_integrity"),
    "Steidlmayer on Markets": ("dalton_trend_day_integrity", "dalton_auction_point_retest", "dalton_day_structure", "dalton_failed_range_extension", "dalton_single_print_retest", "market_profile", "market_profile_auction", "initial_balance_profile", "volume_profile_context", "range_edge_rejection"),
    "Stock Market Wizards": ("trend_structure", "momentum", "trade_management", "risk_reward_geometry", "validation_integrity"),
    "Stock Trading & Investing Using Volume Price Analysis": ("volume_price", "volume_effort_result", "volume_spread_analysis", "vpa_long_legged_doji", "vpa_narrow_spread_high_volume", "vpa_stopping_volume", "vpa_topping_out_volume", "vpa_breakout_volume_validation", "vpa_trend_effort_confirmation"),
    "The Definitive Guide to Point and Figure": ("pf_double_top_bottom", "pf_triple_top_bottom", "pf_three_box_catapult", "pf_pole_reversal", "pf_trendline_signal_confirmation", "pf_opposing_poles", "pf_45_degree_trendline", "pf_early_fulcrum_entry", "pf_trend_aligned_signal", "pf_vertical_count_target", "pf_horizontal_count_target", "pf_shakeout_filter", "pf_trap_reversal", "pf_one_box_semicatapult", "pf_one_box_fulcrum", "point_and_figure", "breakout_quality", "trend_structure", "support_resistance", "validation_integrity"),
    "The Disciplined Trader": ("process_discipline_control", "douglas_probability_edge", "trade_management", "validation_integrity", "noise_filter", "tail_risk"),
    "The Holy Grail Forex Trading System": ("grail_time_anchor_breakout", "grail_bracket_lifecycle", "grail_regime_failure_warning", "validation_integrity", "trend_structure", "session_liquidity", "risk_reward_geometry", "trade_management"),
    "The Man Who Solved the Market": ("statistical_arbitrage", "momentum", "market_making_inventory", "microstructure", "validation_integrity"),
    "The Mental Game of Trading": ("process_discipline_control", "tendler_process_error", "trade_management", "validation_integrity", "noise_filter"),
    "The New Market Wizards": ("trend_structure", "momentum", "trade_management", "risk_reward_geometry", "validation_integrity"),
    "The Ultimate Forex Trading System": ("ultimate_price_rejection", "ultimate_ema_reversal", "ultimate_head_shoulders", "ultimate_double_triple_test", "ultimate_vpa_extreme", "ultimate_mtf_confirmation", "ultimate_mw_bat_pattern", "ultimate_correlation_lag", "ultimate_abandoned_baby_ema5", "ultimate_triangle_pattern", "ultimate_cascade_exhaustion", "ultimate_sandwich_pattern", "ultimate_fractal_pattern", "ultimate_local_extrema_timing", "ultimate_sentiment_change", "ultimate_high_performance_confluence", "ultimate_news_sr_reaction", "validation_integrity", "trend_structure", "session_liquidity", "risk_reward_geometry", "trade_management"),
    "Trade the Price Action": ("damir_fib_confluence_reversal", "damir_confirmed_trend_change", "trend_structure", "price_action_candles", "support_resistance", "breakout_quality", "pullback_retest", "risk_reward_geometry"),
    "Trade Your Way to Financial Freedom": ("position_sizing", "bet_sizing", "risk_reward_geometry", "trade_management", "validation_integrity", "tharp_narrow_range_breakout", "tharp_failed_test_reversal", "tharp_mae_winner_band", "tharp_r_multiple_expectancy", "tharp_market_selection"),
    "Trading and Exchanges": ("microstructure", "adverse_selection", "order_book_imbalance", "market_impact", "scalping_execution", "harris_immediacy_cost", "harris_limit_order_regret", "harris_stop_order_momentum", "validation_integrity"),
    "Trading in the Zone": ("process_discipline_control", "douglas_probability_edge", "trade_management", "validation_integrity", "noise_filter"),
    "Trading with Intermarket Analysis": ("intermarket_analysis", "correlation_context", "relative_strength", "murphy_inverse_relationship", "murphy_lead_lag_confirmation", "murphy_relationship_regime", "murphy_sector_rotation", "trend_structure", "validation_integrity"),
    "Winning the Trading Game": ("process_discipline_control", "drakoln_plan_integrity", "validation_integrity", "risk_reward_geometry", "position_sizing", "trade_management"),
}


_FAMILY_ALGORITHM_PERSPECTIVES = {
    "breakout": "breakout_quality",
    "volatility": "volatility_regime",
    "reversal": "momentum_exhaustion",
    "momentum": "momentum_exhaustion",
    "scalping": "scalping_execution",
    "mean_reversion": "mean_reversion_vs_momentum",
    "statistical_arbitrage": "statistical_arbitrage",
    "order_flow": "microstructure",
    "candlestick": "price_action_candles",
    "market_profile": "market_profile_auction",
    "volume_price": "volume_price",
    "support_resistance": "support_resistance",
    "chart_patterns": "chart_patterns",
    "moving_average": "moving_average_context",
    "channel": "channel_analysis",
    "range": "range_edge_rejection",
    "volatility_breakout": "volatility_breakout",
    "divergence": "divergence",
    "opening_range": "opening_range",
    "news_event": "news_event_risk",
    "liquidity_sweep": "liquidity_sweep",
    "correlation": "correlation_context",
    "trade_management": "trade_management",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _raw_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = record.get("raw_record")
    return raw if isinstance(raw, Mapping) else record


def _source_books(raw: Mapping[str, Any], fallback: Any = ()) -> list[str]:
    """Keep the source record visible alongside perspective attributions."""
    result: list[str] = []
    title = source_label_from_path(_text(raw.get("source_path"))) if _text(raw.get("source_path")) else ""
    if not title:
        title = _text(raw.get("source_title"))
    if title:
        result.append(title)
    if isinstance(fallback, (list, tuple)):
        for value in fallback:
            label = _text(value)
            if label and label not in result:
                result.append(label)
    return result


def _family(record: Mapping[str, Any]) -> str:
    raw = _raw_record(record)
    algorithm = raw.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    return _text(raw.get("strategy_family") or algorithm.get("family")).lower()


def strategy_implementation_status(record: Mapping[str, Any]) -> str:
    """Classify what the Watcher can honestly do with one book record."""
    raw = _raw_record(record)
    source_status = _text(raw.get("status")).upper()
    algorithm = raw.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    if (
        source_status == "CODED_EXACT"
        and isinstance(algorithm.get("compiled_entry_predicates"), Mapping)
        and bool(algorithm.get("compiled_entry_predicates"))
    ):
        return "WATCHER_EXACT_RULE"
    # A compile error means the passage is not specific enough for an exact
    # predicate, but a known family can still receive the lower-authority,
    # human-authored family perspective.  This expands research coverage
    # without pretending that missing parameters were recovered.
    if source_status in {"FAMILY_PROXY", "COMPILE_ERROR"} and _family(record) in _FAMILY_ALGORITHM_PERSPECTIVES:
        return "WATCHER_FAMILY_PERSPECTIVE"
    # An untestable passage can still be useful as a contextual research view
    # when its family is known.  Keep this status distinct: no missing entry,
    # exit, or parameter is inferred, and it can never authorize a trade.
    if source_status == "UNTESTABLE_SOURCE" and _family(record) in _FAMILY_ALGORITHM_PERSPECTIVES:
        return "WATCHER_FAMILY_CONTEXT"
    return "SPECIFICATION_ONLY"


def evaluate_book_algorithm(
    record: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    context_snapshot: Mapping[str, Any] | None = None,
    implementation_status: str | None = None,
) -> dict[str, Any]:
    """Evaluate one record without upgrading research text into live authority."""
    raw = _raw_record(record)
    implementation = (
        str(implementation_status)
        if implementation_status is not None
        else strategy_implementation_status(record)
    )
    perspective_id = _FAMILY_ALGORITHM_PERSPECTIVES.get(_family(record))
    if implementation == "WATCHER_EXACT_RULE":
        evidence = evaluate_strategy_evidence(
            raw,
            state,
            context_snapshot=context_snapshot,
        )
        evaluation_status = str(evidence.get("evaluation_status") or evidence.get("status") or "UNKNOWN")
        if evaluation_status == "MATCH":
            candidate_side = _text(raw.get("side_rule") or state.get("side")).upper()
            view = candidate_side if candidate_side in {"BUY", "SELL"} else "WAIT"
            status = "MATCH"
            applicability = "APPLICABLE"
            reasons = ["all compiled predicates are satisfied at this point in time"]
        elif evaluation_status == "MISSING_INPUT":
            view = "MISSING_DATA"
            status = "MISSING_INPUT"
            applicability = "MISSING_DATA"
            reasons = [
                "compiled rule cannot be evaluated without its required point-in-time inputs",
                *[f"missing_{item}" for item in evidence.get("missing") or ()],
            ]
        elif evaluation_status == "NO_MATCH":
            view = "NOT_APPLICABLE"
            status = "NO_MATCH"
            applicability = "NOT_APPLICABLE"
            reasons = [
                "one or more compiled predicates are not satisfied",
                *[f"predicate_failed:{item}" for item in evidence.get("failed_predicates") or ()],
            ]
        else:
            view = "MISSING_DATA"
            status = evaluation_status
            applicability = "MISSING_DATA"
            reasons = [str(evidence.get("reason") or "exact_rule_evaluation_unavailable")]
        return {
            "implementation_status": implementation,
            "perspective_id": perspective_id,
            "status": status,
            "view": view,
            "applicability": applicability,
            "evaluation_status": evaluation_status,
            "reasons": reasons,
            "missing_inputs": list(evidence.get("missing") or ()),
            "failed_predicates": list(evidence.get("failed_predicates") or ()),
            "context_hash": evidence.get("context_hash"),
            "evidence_status": evidence.get("evidence_status"),
            "source_books": _source_books(raw),
            "execution_authority": False,
            "uses_future_data": False,
            "research_only": True,
        }
    if implementation == "SPECIFICATION_ONLY":
        return {
            "implementation_status": implementation,
            "perspective_id": None,
            "status": "SPECIFICATION_ONLY",
            "view": "MISSING_DATA",
            "reasons": ["source does not contain a complete testable entry/exit/parameter rule"],
            "missing_inputs": ["complete_entry_exit_parameters"],
            "source_books": _source_books(raw),
            "execution_authority": False,
            "uses_future_data": False,
            "research_only": True,
        }
    if perspective_id is None:
        return {
            "implementation_status": "SPECIFICATION_ONLY",
            "perspective_id": None,
            "status": "SPECIFICATION_ONLY",
            "view": "MISSING_DATA",
            "reasons": ["source does not contain a complete testable entry/exit/parameter rule"],
            "missing_inputs": ["complete_entry_exit_parameters"],
            "source_books": _source_books(raw),
            "execution_authority": False,
            "uses_future_data": False,
            "research_only": True,
        }
    analysis = evaluate_module(perspective_id, state)
    return {
        "implementation_status": implementation,
        "perspective_id": perspective_id,
        "status": analysis.get("status", analysis.get("applicability", "APPLICABLE")),
        "applicability": analysis.get("applicability", "MISSING_DATA"),
        "evaluation_status": "FAMILY_CONTEXT" if implementation == "WATCHER_FAMILY_CONTEXT" else "FAMILY_PERSPECTIVE",
        "view": analysis.get("view", "WAIT"),
        "reasons": analysis.get("reasons", []),
        "missing_inputs": analysis.get("missing_inputs", []),
        "source_books": _source_books(raw, analysis.get("source_books", [])),
        "execution_authority": False,
        "uses_future_data": False,
        "research_only": True,
    }


def analyze_book_perspectives(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate every individually authored perspective on one copied snapshot."""
    if not isinstance(state, Mapping):
        state = {}
    perspectives = []
    for analysis in evaluate_all(state):
        item = dict(analysis)
        item.setdefault("perspective_id", item.get("algorithm_id"))
        perspectives.append(item)
    counts = {
        key: sum(item["view"] == key for item in perspectives)
        for key in ("BUY", "SELL", "WAIT", "NOT_APPLICABLE", "MISSING_DATA")
    }
    applicable = [item for item in perspectives if item["applicability"] == "APPLICABLE"]
    directional = [item for item in applicable if item["view"] in {"BUY", "SELL"}]
    consensus = "UNRESOLVED"
    if directional:
        buy = sum(item["view"] == "BUY" for item in directional)
        sell = sum(item["view"] == "SELL" for item in directional)
        consensus = "BUY" if buy > sell else "SELL" if sell > buy else "MIXED"
    return {
        "perspectives": perspectives,
        "consensus": consensus,
        "counts": counts,
        "applicable_count": len(applicable),
        "coverage": {
            "books_in_review_record": len(BOOK_REVIEW_COVERAGE),
            "book_status_counts": {
                status: sum(value == status for value in BOOK_REVIEW_COVERAGE.values())
                for status in sorted(set(BOOK_REVIEW_COVERAGE.values()))
            },
            "review_record": "reports/research/watcher_book_review.md",
            "explicit_family_algorithms": sorted(_FAMILY_ALGORITHM_PERSPECTIVES),
            "algorithm_modules": list(ALGORITHM_MODULES),
            "book_algorithm_coverage": {
                book: list(algorithms) for book, algorithms in BOOK_ALGORITHM_COVERAGE.items()
            },
        },
        "execution_authority": False,
        "research_only": True,
        "no_lookahead": True,
    }


__all__ = [
    "ALGORITHM_MODULES",
    "BOOK_ALGORITHM_COVERAGE",
    "BOOK_REVIEW_COVERAGE",
    "_FAMILY_ALGORITHM_PERSPECTIVES",
    "analyze_book_perspectives",
    "evaluate_book_algorithm",
    "strategy_implementation_status",
]
