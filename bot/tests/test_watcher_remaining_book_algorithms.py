from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _qpl(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "oreste_qpl_level": 1.1000,
        "oreste_current_price": 1.1001,
        "oreste_qpl_tolerance": 0.0002,
        "oreste_qpl_role": "support",
        "oreste_qpl_interaction": "rejection",
        "oreste_qpl_confirmation": "confirmed",
        "oreste_qpl_next_level": 1.1010,
        "oreste_qpl_data_provenance": "observed timestamped QPL chart level",
    }
    state.update(overrides)
    return state


def _entelechy(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "oreste_qpl_level": 1.1000,
        "oreste_gann_angle_level": 1.1001,
        "oreste_current_price": 1.10005,
        "oreste_entelechy_tolerance": 0.0002,
        "oreste_entelechy_interaction": "reversal",
        "oreste_entelechy_direction": "BUY",
        "oreste_entelechy_confirmation": "confirmed",
        "oreste_entelechy_data_provenance": "observed timestamped QPL and Gann chart",
    }
    state.update(overrides)
    return state


def _time_price(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "oreste_time_signal": "reversal_up",
        "oreste_price_signal": "reversal_up",
        "oreste_time_direction": "UP",
        "oreste_price_direction": "UP",
        "oreste_time_confirmation": "confirmed",
        "oreste_price_confirmation": "confirmed",
        "oreste_time_price_agreement": True,
        "oreste_time_price_data_provenance": "observed timestamped price and time study",
    }
    state.update(overrides)
    return state


def _volatility_risk(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "oreste_volatility_regime": "high",
        "oreste_baseline_stop_distance": 0.0005,
        "oreste_current_stop_distance": 0.0010,
        "oreste_position_risk_usd": 0.15,
        "oreste_max_risk_usd": 0.15,
        "oreste_position_units": 1.0,
        "oreste_baseline_units": 2.0,
        "oreste_volatility_data_provenance": "observed timestamped volatility and risk state",
    }
    state.update(overrides)
    return state


def _scenario(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "qf_scenario_pnl": [0.10, 0.04, -0.03, 0.02],
        "qf_risk_budget": 0.15,
        "qf_scenario_data_provenance": "timestamped historical replay scenarios",
    }
    state.update(overrides)
    return state


def _edge(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "douglas_edge_defined": True,
        "douglas_edge_p_win": 0.62,
        "douglas_edge_sample_n": 80,
        "douglas_outcomes_independent": True,
        "douglas_risk_accepted": True,
        "douglas_data_provenance": "observed chronological strategy journal",
    }
    state.update(overrides)
    return state


def _tendler(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "tendler_performance_state": "C",
        "tendler_emotion_signal": "anger",
        "tendler_root_cause_identified": False,
        "tendler_execution_error": "revenge reentry",
        "tendler_data_provenance": "observed execution journal",
    }
    state.update(overrides)
    return state


def _plan(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "drakoln_money_management_defined": True,
        "drakoln_technical_method_defined": True,
        "drakoln_risk_management_defined": True,
        "drakoln_trade_plan_defined": True,
        "drakoln_entry_rules_defined": True,
        "drakoln_exit_rules_defined": True,
        "drakoln_risk_reward_defined": True,
        "drakoln_losing_streak_plan_defined": True,
        "drakoln_winning_streak_plan_defined": True,
        "drakoln_data_provenance": "observed completed trading plan",
    }
    state.update(overrides)
    return state


def test_oreste_qpl_requires_proximity_confirmation_and_maps_support_rejection():
    result = evaluate_module("oreste_qpl_interaction", _qpl())
    assert result["view"] == "BUY"
    assert result["oreste_qpl_assessment"] == "CONFIRMED_REJECTION"
    assert result["oreste_qpl_target"] == pytest.approx(1.1010)

    unconfirmed = evaluate_module(
        "oreste_qpl_interaction", _qpl(oreste_qpl_confirmation="unconfirmed")
    )
    assert unconfirmed["view"] == "WAIT"

    far = evaluate_module("oreste_qpl_interaction", _qpl(oreste_current_price=1.1020))
    assert far["oreste_qpl_assessment"] == "NO_PROXIMITY"


def test_oreste_entelechy_requires_two_levels_and_confirmed_reversal():
    result = evaluate_module("oreste_entelechy_confluence", _entelechy())
    assert result["view"] == "BUY"
    assert result["oreste_entelechy_assessment"] == "CONFIRMED_REVERSAL"

    mismatch = evaluate_module(
        "oreste_entelechy_confluence", _entelechy(oreste_entelechy_direction="SELL")
    )
    assert mismatch["view"] == "SELL"
    assert mismatch["candidate_alignment"] == "OPPOSES"

    far = evaluate_module(
        "oreste_entelechy_confluence", _entelechy(oreste_current_price=1.1020)
    )
    assert far["oreste_entelechy_assessment"] == "NO_CONFLUENCE_PROXIMITY"


def test_oreste_time_price_confluence_requires_agreement_not_one_signal():
    result = evaluate_module("oreste_time_price_confluence", _time_price())
    assert result["view"] == "BUY"
    assert result["oreste_time_price_assessment"] == "CONFIRMED_CONFLUENCE"

    disagreement = evaluate_module(
        "oreste_time_price_confluence", _time_price(oreste_price_direction="DOWN")
    )
    assert disagreement["view"] == "WAIT"
    assert disagreement["oreste_time_price_assessment"] == "DIRECTION_DISAGREEMENT"


def test_oreste_volatility_risk_expands_stop_and_reduces_units_without_more_risk():
    result = evaluate_module("oreste_volatility_scaled_risk", _volatility_risk())
    assert result["view"] == "WAIT"
    assert result["oreste_volatility_risk_assessment"] == "ADJUSTED_WITHIN_RISK"
    assert result["oreste_stop_expanded"] is True
    assert result["oreste_units_reduced"] is True

    unsafe = evaluate_module(
        "oreste_volatility_scaled_risk",
        _volatility_risk(oreste_current_stop_distance=0.0002),
    )
    assert unsafe["oreste_volatility_risk_assessment"] == "STOP_TOO_TIGHT_FOR_VOL"


def test_quantum_finance_scenario_stress_is_explicitly_a_classical_analogue():
    result = evaluate_module("quantum_finance_scenario_stress", _scenario())
    assert result["view"] == "WAIT"
    assert result["quantum_finance_scenario_assessment"] == "WITHIN_BUDGET"
    assert result["implementation_class"] == "CLASSICAL_SCENARIO_ANALOGUE"
    assert result["quantum_execution_claim"] is False

    breach = evaluate_module(
        "quantum_finance_scenario_stress", _scenario(qf_scenario_pnl=[0.01, -0.20])
    )
    assert breach["quantum_finance_scenario_assessment"] == "STRESS_EXCEEDS_BUDGET"


def test_douglas_edge_uses_probabilities_without_a_95_percent_gate():
    result = evaluate_module("douglas_probability_edge", _edge())
    assert result["view"] == "WAIT"
    assert result["douglas_edge_assessment"] == "PROBABILISTIC_EDGE"
    assert result["douglas_edge_probability"] == pytest.approx(0.62)

    no_edge = evaluate_module(
        "douglas_probability_edge", _edge(douglas_edge_p_win=0.49)
    )
    assert no_edge["douglas_edge_assessment"] == "NO_EDGE_OBSERVED"


def test_tendler_emotion_is_a_root_cause_signal_not_a_directional_signal():
    result = evaluate_module("tendler_process_error", _tendler())
    assert result["view"] == "WAIT"
    assert result["tendler_assessment"] == "ROOT_CAUSE_REVIEW"
    assert result["directional_claim"] is False

    stable = evaluate_module(
        "tendler_process_error",
        _tendler(
            tendler_performance_state="A",
            tendler_emotion_signal="neutral",
            tendler_root_cause_identified=True,
            tendler_execution_error="technical learning error",
        ),
    )
    assert stable["tendler_assessment"] == "LEARNING_REVIEW"


def test_drakoln_plan_integrity_requires_all_three_pillars_and_exit_plan():
    result = evaluate_module("drakoln_plan_integrity", _plan())
    assert result["view"] == "WAIT"
    assert result["drakoln_plan_assessment"] == "PLAN_COMPLETE"

    incomplete = evaluate_module(
        "drakoln_plan_integrity", _plan(drakoln_exit_rules_defined=False)
    )
    assert incomplete["drakoln_plan_assessment"] == "PLAN_INCOMPLETE"
    assert "drakoln_exit_rules_defined" in incomplete["missing_plan_elements"]


def _narang_horizon(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_forecast_target": "captured net return",
        "narang_forecast_horizon_s": 3,
        "narang_evaluation_horizon_s": 3,
        "narang_horizon_data_provenance": "observed timestamped executable quote replay",
    }
    state.update(overrides)
    return state


def _narang_conditional(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_primary_signal": "micro momentum",
        "narang_conditioning_signal": "higher timeframe trend",
        "narang_primary_direction": "BUY",
        "narang_conditioning_direction": "BUY",
        "narang_conditioning_confirmed": True,
        "narang_alpha_data_provenance": "observed timestamped market state",
    }
    state.update(overrides)
    return state


def _narang_cost(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_expected_gross_benefit_usd": 0.12,
        "narang_estimated_transaction_cost_usd": 0.04,
        "narang_cost_components": {"commission": 0.01, "slippage": 0.02, "impact": 0.01},
        "narang_cost_data_provenance": "observed executable fills and quote replay",
    }
    state.update(overrides)
    return state


def _narang_liquidity(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_order_size": 1.0,
        "narang_available_liquidity": 5.0,
        "narang_market_impact_estimate_usd": 0.01,
        "narang_liquidity_data_provenance": "observed timestamped executable liquidity",
    }
    state.update(overrides)
    return state


def _brown_ma(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_ma_stack": "stacked_spreading",
        "brown_trend_direction": "BUY",
        "brown_ma_spread": 0.0008,
        "brown_ma_data_provenance": "observed timestamped moving-average chart",
    }
    state.update(overrides)
    return state


def _brown_band(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_band_touch": "lower",
        "brown_signal_direction": "BUY",
        "brown_signal_confirmed": True,
        "brown_signal_close_relation": "below_center",
        "brown_band_data_provenance": "observed timestamped price and Bollinger chart",
    }
    state.update(overrides)
    return state


def _brown_stop(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_entry_price": 1.1000,
        "brown_recent_structural_low": 1.0990,
        "brown_recent_structural_high": 1.1010,
        "brown_stop_price": 1.0988,
        "brown_stop_buffer": 0.0002,
        "brown_stop_data_provenance": "observed timestamped price structure",
    }
    state.update(overrides)
    return state


def _brown_qmp(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_qmp_dot": "green",
        "brown_qmp_next_candle_open": True,
        "brown_qmp_stop_reference": "below_recent_low",
        "brown_qmp_stop_clearance": 0.0003,
        "brown_qmp_min_stop_clearance": 0.0002,
        "brown_qmp_data_provenance": "observed timestamped QMP and price bars",
    }
    state.update(overrides)
    return state


def _brown_macd_zero(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_qmp_dot": "green",
        "brown_macd_platinum_value": -0.0004,
        "brown_macd_zero_data_provenance": "observed timestamped QMP and MACD bars",
    }
    state.update(overrides)
    return state


def _brown_qqe(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_qmp_dot": "green",
        "brown_qqe_line_1": 42.0,
        "brown_qqe_line_2": 47.0,
        "brown_qqe_mode": "midline",
        "brown_qqe_data_provenance": "observed timestamped QMP and QQE bars",
    }
    state.update(overrides)
    return state


def _brown_multi_ma(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_qmp_dot": "green",
        "brown_ma_50": 1.1050,
        "brown_ma_100": 1.1020,
        "brown_ma_240": 1.0980,
        "brown_multi_ma_data_provenance": "observed timestamped 50/100/240 moving-average bars",
    }
    state.update(overrides)
    return state


def _brown_trendline(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_original_qmp_dot": "green",
        "brown_opposite_qmp_dot_present": False,
        "brown_trendline_break_direction": "UP",
        "brown_trendline_break_confirmed": True,
        "brown_trendline_next_candle_open": True,
        "brown_trendline_data_provenance": "observed timestamped QMP and trendline bars",
    }
    state.update(overrides)
    return state


def _brown_divergence(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_divergence_kind": "hidden",
        "brown_divergence_direction": "BUY",
        "brown_divergence_trend": "UP",
        "brown_divergence_confirmed": True,
        "brown_divergence_data_provenance": "observed timestamped price and oscillator pivots",
    }
    state.update(overrides)
    return state


def _brown_band_management(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brown_trade_side": "BUY",
        "brown_entry_center_relation": "below_center",
        "brown_current_center_relation": "above_center",
        "brown_trade_profit_positive": True,
        "brown_management_action_viable": True,
        "brown_opposite_band_touched": False,
        "brown_bollinger_management_data_provenance": "observed timestamped trade and Bollinger bars",
    }
    state.update(overrides)
    return state


def _pyramid_lock(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "pyramid_add_preplanned": True,
        "pyramid_market_regime": "strong trend",
        "pyramid_same_thesis": True,
        "pyramid_position_profit_usd": 0.05,
        "pyramid_risk_before_usd": 0.15,
        "pyramid_risk_after_usd": 0.10,
        "pyramid_max_risk_usd": 0.15,
        "pyramid_add_direction": "BUY",
        "pyramid_data_provenance": "observed timestamped position and stop journal",
    }
    state.update(overrides)
    return state


def _grinold_horizon(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "grinold_signal_half_life_s": 10.0,
        "grinold_signal_age_s": 5.0,
        "grinold_holding_horizon_s": 8.0,
        "grinold_information_data_provenance": "observed timestamped signal replay",
    }
    state.update(overrides)
    return state


def _grinold_utility(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "grinold_short_term_alpha_usd": 0.12,
        "grinold_short_term_risk_adjustment_usd": 0.03,
        "grinold_market_impact_usd": 0.04,
        "grinold_trade_utility_data_provenance": "observed timestamped execution replay",
    }
    state.update(overrides)
    return state


def _clenow_regime(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "clenow_fast_ema": 1.1050,
        "clenow_slow_ema": 1.1000,
        "clenow_trend_filter": "up",
        "clenow_regime_data_provenance": "observed timestamped daily EMA study",
    }
    state.update(overrides)
    return state


def _clenow_sizing(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "clenow_equity_usd": 1_000_000.0,
        "clenow_atr": 10.0,
        "clenow_point_value": 100.0,
        "clenow_risk_factor": 0.002,
        "clenow_sizing_data_provenance": "observed timestamped ATR and contract specification",
    }
    state.update(overrides)
    return state


def _clenow_exposure(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "clenow_candidate_base_currency": "EUR",
        "clenow_candidate_quote_currency": "USD",
        "clenow_candidate_risk_usd": 100.0,
        "clenow_existing_positions": [
            {"base_currency": "GBP", "quote_currency": "JPY", "side": "BUY", "risk_usd": 100.0},
        ],
        "clenow_currency_exposure_limit_usd": 250.0,
        "clenow_exposure_data_provenance": "observed timestamped portfolio currency exposures",
    }
    state.update(overrides)
    return state


def _cartea_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "cartea_state_duration_s": 0.1,
        "cartea_state_revision_volatility": 0.0001,
        "cartea_state_zero_revision_probability": 0.99,
        "cartea_state_persistence": 0.8,
        "cartea_median_duration_s": 1.0,
        "cartea_median_revision_volatility": 0.001,
        "cartea_median_zero_revision_probability": 0.5,
        "cartea_median_persistence": 0.5,
        "cartea_state_data_provenance": "observed timestamped tick-state HMM replay",
    }
    state.update(overrides)
    return state


def _cartea_freshness(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "cartea_quote_created_time_s": 100.0,
        "cartea_now_time_s": 100.2,
        "cartea_last_trade_time_s": 99.8,
        "cartea_last_state_change_time_s": 99.7,
        "cartea_quote_max_age_s": 1.0,
        "cartea_quote_data_provenance": "observed timestamped quote and event stream",
    }
    state.update(overrides)
    return state


def _em_confirmation(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "em_average_a_direction": "up",
        "em_average_b_direction": "up",
        "em_dow_confirmation_scope": "two averages",
        "em_data_provenance": "observed timestamped closing-price average study",
    }
    state.update(overrides)
    return state


def _em_basing(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "em_basing_mode": "wave_low",
        "em_basing_point_low": 100.0,
        "em_day_away_count": 3,
        "em_lower_low_before_confirmation": False,
        "em_existing_stop_price": 94.0,
        "em_stop_filter_fraction": 0.05,
        "em_data_provenance": "observed timestamped price-wave study",
    }
    state.update(overrides)
    return state


def _carter_352(**overrides):
    state = {
        "symbol": "ES",
        "side": "SELL",
        "carter_352_market": "ES",
        "carter_352_reference_time": "15:30",
        "carter_352_entry_time": "15:52",
        "carter_352_exit_time": "16:13",
        "carter_352_session_timezone": "America/New_York",
        "carter_352_reference_price": 5000.0,
        "carter_352_entry_price": 5001.5,
        "carter_352_move_direction": "up",
        "carter_352_min_move_points": 1.0,
        "carter_352_stop_points": 2.0,
        "carter_352_data_provenance": "observed timestamped one-minute ES session replay",
    }
    state.update(overrides)
    return state


def test_narang_horizon_contract_requires_exact_forecast_and_evaluation_horizon():
    result = evaluate_module("narang_horizon_specification", _narang_horizon())
    assert result["view"] == "WAIT"
    assert result["narang_horizon_assessment"] == "HORIZON_ALIGNED"
    assert result["narang_horizon_s"] == 3

    mismatch = evaluate_module(
        "narang_horizon_specification",
        _narang_horizon(narang_evaluation_horizon_s=10),
    )
    assert mismatch["narang_horizon_assessment"] == "HORIZON_MISMATCH"


def test_narang_conditional_alpha_requires_agreement_before_directional_view():
    result = evaluate_module("narang_conditional_alpha", _narang_conditional())
    assert result["view"] == "BUY"
    assert result["narang_conditional_assessment"] == "CONFIRMED_AGREEMENT"

    disagreement = evaluate_module(
        "narang_conditional_alpha",
        _narang_conditional(narang_conditioning_direction="SELL"),
    )
    assert disagreement["view"] == "WAIT"
    assert disagreement["narang_conditional_assessment"] == "DIRECTION_DISAGREEMENT"


def test_narang_cost_hurdle_requires_gross_benefit_to_exceed_all_costs():
    result = evaluate_module("narang_cost_hurdle", _narang_cost())
    assert result["view"] == "WAIT"
    assert result["narang_cost_assessment"] == "COST_HURDLE_CLEARED"
    assert result["narang_net_benefit_usd"] == pytest.approx(0.08)

    rejected = evaluate_module(
        "narang_cost_hurdle",
        _narang_cost(narang_expected_gross_benefit_usd=0.03),
    )
    assert rejected["narang_cost_assessment"] == "COST_HURDLE_NOT_CLEARED"


def test_narang_liquidity_checks_order_size_against_available_liquidity():
    result = evaluate_module("narang_liquidity_impact", _narang_liquidity())
    assert result["view"] == "WAIT"
    assert result["narang_liquidity_assessment"] == "LIQUIDITY_COMPATIBLE"
    assert result["narang_size_to_liquidity_ratio"] == pytest.approx(0.2)

    oversized = evaluate_module(
        "narang_liquidity_impact",
        _narang_liquidity(narang_order_size=6.0),
    )
    assert oversized["narang_liquidity_assessment"] == "IMPACT_RISK"


def test_brown_ma_filter_follows_a_clear_stacked_trend_and_waits_when_unclear():
    result = evaluate_module("brown_ma_stack_filter", _brown_ma())
    assert result["view"] == "BUY"
    assert result["brown_ma_assessment"] == "STACKED_TREND_CONFIRMED"

    unclear = evaluate_module(
        "brown_ma_stack_filter",
        _brown_ma(brown_ma_stack="flat_tight", brown_trend_direction=None),
    )
    assert unclear["view"] == "WAIT"
    assert unclear["brown_ma_assessment"] == "TREND_UNCLEAR"


def test_brown_band_filter_requires_directional_touch_and_center_confirmation():
    result = evaluate_module("brown_band_signal_filter", _brown_band())
    assert result["view"] == "BUY"
    assert result["brown_band_assessment"] == "CONFIRMED_LOWER_BAND_BUY"

    wrong_side = evaluate_module(
        "brown_band_signal_filter",
        _brown_band(brown_band_touch="upper"),
    )
    assert wrong_side["view"] == "WAIT"
    assert wrong_side["brown_band_assessment"] == "TOUCH_DIRECTION_MISMATCH"


def test_brown_structural_stop_requires_room_beyond_the_recent_extreme():
    result = evaluate_module("brown_structural_stop_buffer", _brown_stop())
    assert result["view"] == "WAIT"
    assert result["brown_stop_assessment"] == "STRUCTURAL_BUFFER_VALID"
    assert result["brown_stop_distance"] == pytest.approx(0.0012)

    too_tight = evaluate_module(
        "brown_structural_stop_buffer",
        _brown_stop(brown_stop_price=1.0991),
    )
    assert too_tight["brown_stop_assessment"] == "BUFFER_INSUFFICIENT"


def test_brown_qmp_dot_is_a_next_candle_trigger_with_structural_stop_room():
    result = evaluate_module("brown_qmp_filter_trigger", _brown_qmp())
    assert result["view"] == "BUY"
    assert result["brown_qmp_assessment"] == "GREEN_DOT_NEXT_CANDLE"

    sell = evaluate_module(
        "brown_qmp_filter_trigger",
        _brown_qmp(
            side="SELL",
            brown_qmp_dot="red",
            brown_qmp_stop_reference="above_recent_high",
        ),
    )
    assert sell["view"] == "SELL"

    no_room = evaluate_module(
        "brown_qmp_filter_trigger",
        _brown_qmp(brown_qmp_stop_clearance=0.0001),
    )
    assert no_room["view"] == "WAIT"
    assert no_room["brown_qmp_assessment"] == "STOP_CLEARANCE_INSUFFICIENT"


def test_brown_macd_platinum_zero_filter_requires_qmp_direction_on_the_source_side():
    buy = evaluate_module("brown_macd_zero_filter", _brown_macd_zero())
    assert buy["view"] == "BUY"
    assert buy["brown_macd_assessment"] == "BELOW_ZERO_BUY_FILTER"

    sell = evaluate_module(
        "brown_macd_zero_filter",
        _brown_macd_zero(side="SELL", brown_qmp_dot="red", brown_macd_platinum_value=0.0004),
    )
    assert sell["view"] == "SELL"
    assert sell["brown_macd_assessment"] == "ABOVE_ZERO_SELL_FILTER"

    mismatch = evaluate_module(
        "brown_macd_zero_filter",
        _brown_macd_zero(brown_macd_platinum_value=0.0004),
    )
    assert mismatch["view"] == "WAIT"


def test_brown_qqe_filter_supports_midline_and_extreme_variants():
    midline = evaluate_module("brown_qqe_filter", _brown_qqe())
    assert midline["view"] == "BUY"
    assert midline["brown_qqe_assessment"] == "MIDLINE_BUY_FILTER"

    extreme = evaluate_module(
        "brown_qqe_filter",
        _brown_qqe(
            brown_qqe_mode="extreme",
            brown_qqe_line_1=34.0,
            brown_qqe_line_2=52.0,
        ),
    )
    assert extreme["view"] == "BUY"
    assert extreme["brown_qqe_assessment"] == "OVERSOLD_BUY_FILTER"

    outside = evaluate_module(
        "brown_qqe_filter",
        _brown_qqe(brown_qqe_line_1=52.0, brown_qqe_line_2=55.0),
    )
    assert outside["view"] == "WAIT"


def test_brown_multi_ma_filter_requires_exact_50_100_240_alignment_and_qmp_trigger():
    result = evaluate_module("brown_multi_ma_alignment", _brown_multi_ma())
    assert result["view"] == "BUY"
    assert result["brown_multi_ma_assessment"] == "BULLISH_50_100_240_ALIGNMENT"

    sell = evaluate_module(
        "brown_multi_ma_alignment",
        _brown_multi_ma(
            side="SELL",
            brown_qmp_dot="red",
            brown_ma_50=1.0980,
            brown_ma_100=1.1020,
            brown_ma_240=1.1050,
        ),
    )
    assert sell["view"] == "SELL"

    mixed = evaluate_module("brown_multi_ma_alignment", _brown_multi_ma(brown_ma_100=1.1060))
    assert mixed["view"] == "WAIT"


def test_brown_trendline_reentry_preserves_qmp_thesis_until_an_opposite_dot_appears():
    result = evaluate_module("brown_trendline_break_reentry", _brown_trendline())
    assert result["view"] == "BUY"
    assert result["brown_trendline_assessment"] == "BUY_REENTRY"

    sell = evaluate_module(
        "brown_trendline_break_reentry",
        _brown_trendline(
            side="SELL",
            brown_original_qmp_dot="red",
            brown_trendline_break_direction="DOWN",
        ),
    )
    assert sell["view"] == "SELL"

    invalidated = evaluate_module(
        "brown_trendline_break_reentry",
        _brown_trendline(brown_opposite_qmp_dot_present=True),
    )
    assert invalidated["view"] == "WAIT"
    assert invalidated["brown_trendline_assessment"] == "THESIS_INVALIDATED"


def test_brown_divergence_distinguishes_regular_reversal_from_hidden_continuation():
    hidden = evaluate_module("brown_divergence_type_filter", _brown_divergence())
    assert hidden["view"] == "BUY"
    assert hidden["brown_divergence_assessment"] == "HIDDEN_CONTINUATION"

    regular = evaluate_module(
        "brown_divergence_type_filter",
        _brown_divergence(
            side="SELL",
            brown_divergence_kind="regular",
            brown_divergence_direction="SELL",
            brown_divergence_trend="UP",
        ),
    )
    assert regular["view"] == "SELL"
    assert regular["brown_divergence_assessment"] == "REGULAR_REVERSAL"

    wrong_hidden = evaluate_module(
        "brown_divergence_type_filter",
        _brown_divergence(brown_divergence_direction="SELL"),
    )
    assert wrong_hidden["view"] == "WAIT"


def test_brown_bollinger_management_marks_center_cross_and_outer_band_actions():
    center = evaluate_module("brown_bollinger_trade_management", _brown_band_management())
    assert center["view"] == "WAIT"
    assert center["brown_management_assessment"] == "CENTER_CROSS_PARTIAL_AND_PROTECT"
    assert center["directional_claim"] is False

    outer = evaluate_module(
        "brown_bollinger_trade_management",
        _brown_band_management(brown_current_center_relation="above_center", brown_opposite_band_touched=True),
    )
    assert outer["brown_management_assessment"] == "OPPOSITE_BAND_ACTION"

    not_viable = evaluate_module(
        "brown_bollinger_trade_management",
        _brown_band_management(brown_management_action_viable=False),
    )
    assert not_viable["brown_management_assessment"] == "ACTION_NOT_VIABLE"


def test_pyramiding_risk_lock_requires_preplanned_profit_funded_add_without_more_risk():
    result = evaluate_module("pyramiding_risk_lock", _pyramid_lock())
    assert result["view"] == "BUY"
    assert result["pyramiding_assessment"] == "SAFE_TREND_ADD"
    assert result["pyramiding_risk_locked"] is True

    unsafe = evaluate_module(
        "pyramiding_risk_lock",
        _pyramid_lock(pyramid_risk_after_usd=0.20),
    )
    assert unsafe["view"] == "WAIT"
    assert unsafe["pyramiding_assessment"] == "RISK_INCREASE"


def test_grinold_information_horizon_decays_with_signal_age_and_marks_stale_state():
    result = evaluate_module("grinold_information_horizon", _grinold_horizon())
    assert result["view"] == "WAIT"
    assert result["grinold_horizon_assessment"] == "IN_HORIZON"
    assert result["grinold_decay_weight"] == pytest.approx(0.5 ** 0.5)

    stale = evaluate_module(
        "grinold_information_horizon",
        _grinold_horizon(grinold_signal_age_s=12.0),
    )
    assert stale["grinold_horizon_assessment"] == "STALE_INFORMATION"


def test_grinold_trade_utility_subtracts_short_term_risk_and_impact_once():
    result = evaluate_module("grinold_trade_utility", _grinold_utility())
    assert result["view"] == "WAIT"
    assert result["grinold_trade_utility_assessment"] == "POSITIVE_TRADING_UTILITY"
    assert result["grinold_trade_utility_usd"] == pytest.approx(0.05)

    negative = evaluate_module(
        "grinold_trade_utility",
        _grinold_utility(grinold_market_impact_usd=0.10),
    )
    assert negative["grinold_trade_utility_assessment"] == "NEGATIVE_TRADING_UTILITY"


def test_clenow_regime_filter_exposes_ema_trend_and_rejects_flat_regime():
    result = evaluate_module("clenow_regime_filter", _clenow_regime())
    assert result["view"] == "BUY"
    assert result["clenow_regime_assessment"] == "BULLISH_TREND"
    assert result["clenow_regime_direction"] == "BUY"

    flat = evaluate_module(
        "clenow_regime_filter",
        _clenow_regime(clenow_fast_ema=1.1000, clenow_slow_ema=1.1000),
    )
    assert flat["view"] == "WAIT"
    assert flat["clenow_regime_assessment"] == "NON_TRENDING"


def test_clenow_atr_sizing_targets_common_volatility_impact_and_rounds_down():
    result = evaluate_module("clenow_atr_impact_sizing", _clenow_sizing())
    assert result["view"] == "WAIT"
    assert result["clenow_sizing_assessment"] == "VOLATILITY_NORMALIZED_SIZE"
    assert result["clenow_recommended_contracts"] == 2
    assert result["clenow_theoretical_impact_usd"] == pytest.approx(2000.0)

    invalid = evaluate_module("clenow_atr_impact_sizing", _clenow_sizing(clenow_atr=0))
    assert invalid["clenow_sizing_assessment"] == "INVALID_VOLATILITY_INPUT"


def test_clenow_currency_exposure_flags_stacked_quote_currency_risk():
    result = evaluate_module("clenow_currency_exposure", _clenow_exposure())
    assert result["view"] == "WAIT"
    assert result["clenow_exposure_assessment"] == "DIVERSIFIED_CURRENCY_EXPOSURE"
    assert result["clenow_projected_currency_exposure_usd"]["USD"] == pytest.approx(-100.0)

    concentrated = evaluate_module(
        "clenow_currency_exposure",
        _clenow_exposure(clenow_candidate_base_currency="GBP"),
    )
    assert concentrated["clenow_exposure_assessment"] == "CONCENTRATED_CURRENCY_RISK"


def test_cartea_state_model_identifies_fast_low_revision_regime():
    result = evaluate_module("cartea_state_intensity", _cartea_state())
    assert result["view"] == "WAIT"
    assert result["cartea_state_assessment"] == "REBATE_FAVORABLE"
    assert result["cartea_activity_class"] == "FAST"
    assert result["cartea_revision_class"] == "LOW"

    adverse = evaluate_module(
        "cartea_state_intensity",
        _cartea_state(
            cartea_state_duration_s=2.0,
            cartea_state_revision_volatility=0.002,
            cartea_state_zero_revision_probability=0.1,
            cartea_state_persistence=0.1,
        ),
    )
    assert adverse["cartea_state_assessment"] == "REBATE_UNFAVORABLE"


def test_cartea_quote_freshness_invalidates_after_trade_or_state_change():
    result = evaluate_module("cartea_quote_freshness_guard", _cartea_freshness())
    assert result["view"] == "WAIT"
    assert result["cartea_quote_assessment"] == "QUOTE_FRESH"

    traded = evaluate_module(
        "cartea_quote_freshness_guard",
        _cartea_freshness(cartea_last_trade_time_s=100.1),
    )
    assert traded["cartea_quote_assessment"] == "QUOTE_STALE"

    aged = evaluate_module(
        "cartea_quote_freshness_guard",
        _cartea_freshness(cartea_now_time_s=101.1),
    )
    assert aged["cartea_quote_assessment"] == "QUOTE_STALE"


def test_edwards_magee_confirmation_requires_harmonic_average_directions():
    result = evaluate_module("edwards_magee_dow_confirmation", _em_confirmation())
    assert result["view"] == "BUY"
    assert result["edwards_magee_confirmation_assessment"] == "HARMONIC_CONFIRMATION"

    mixed = evaluate_module(
        "edwards_magee_dow_confirmation",
        _em_confirmation(em_average_b_direction="down"),
    )
    assert mixed["view"] == "WAIT"
    assert mixed["edwards_magee_confirmation_assessment"] == "MIXED_AVERAGES"


def test_edwards_magee_basing_points_confirm_three_days_away_and_ratchet_stop():
    result = evaluate_module("edwards_magee_basing_points_stop", _em_basing())
    assert result["view"] == "WAIT"
    assert result["edwards_magee_basing_assessment"] == "BASING_POINT_CONFIRMED"
    assert result["edwards_magee_candidate_stop"] == pytest.approx(95.0)

    unsafe = evaluate_module(
        "edwards_magee_basing_points_stop",
        _em_basing(em_day_away_count=2),
    )
    assert unsafe["edwards_magee_basing_assessment"] == "THREE_DAY_RULE_NOT_MET"

    loosen = evaluate_module(
        "edwards_magee_basing_points_stop",
        _em_basing(em_existing_stop_price=96.0),
    )
    assert loosen["edwards_magee_basing_assessment"] == "STOP_WOULD_LOOSEN"


def test_carter_352_play_fades_a_qualified_late_session_move():
    result = evaluate_module("carter_352_play", _carter_352())
    assert result["view"] == "SELL"
    assert result["carter_352_assessment"] == "QUALIFIED_FADE"
    assert result["carter_352_stop_points"] == pytest.approx(2.0)

    small_move = evaluate_module(
        "carter_352_play",
        _carter_352(carter_352_entry_price=5000.5),
    )
    assert small_move["view"] == "WAIT"
    assert small_move["carter_352_assessment"] == "MOVE_THRESHOLD_NOT_MET"

    fx = evaluate_module("carter_352_play", _carter_352(carter_352_market="EURUSD"))
    assert fx["applicability"] == "NOT_APPLICABLE"


def _ultimate_sandwich(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ultimate_sandwich_bar_directions": ["UP", "DOWN", "UP", "DOWN", "UP", "DOWN"],
        "ultimate_sandwich_tight_range": True,
        "ultimate_sandwich_straight_range": True,
        "ultimate_sandwich_break_direction": "UP",
        "ultimate_sandwich_break_confirmed": True,
        "ultimate_data_provenance": "observed timestamped sandwich bars",
    }
    state.update(overrides)
    return state


def _ultimate_fractal(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ultimate_fractal_shape": "symmetric repeating reversal",
        "ultimate_fractal_stage": "second",
        "ultimate_fractal_direction": "UP",
        "ultimate_fractal_scale_count": 3,
        "ultimate_fractal_observed": True,
        "ultimate_data_provenance": "observed timestamped multi-timeframe fractal study",
    }
    state.update(overrides)
    return state


def _ultimate_extreme(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ultimate_extreme_type": "local_minimum",
        "ultimate_extreme_zone": "support",
        "ultimate_extreme_confirmed": True,
        "ultimate_extreme_distance_pips": 0.4,
        "ultimate_data_provenance": "observed timestamped local extrema",
    }
    state.update(overrides)
    return state


def _ultimate_sentiment(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ultimate_sentiment_previous_long_pct": 48.0,
        "ultimate_sentiment_previous_short_pct": 52.0,
        "ultimate_sentiment_current_long_pct": 53.0,
        "ultimate_sentiment_current_short_pct": 47.0,
        "ultimate_sentiment_interval_hours": 3.0,
        "ultimate_sentiment_min_change_pct": 2.0,
        "ultimate_data_provenance": "observed timestamped broker sentiment snapshots",
    }
    state.update(overrides)
    return state


def _ultimate_confluence(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ultimate_confluence_signals": [
            {"name": "chart_pattern", "direction": "BUY", "confirmed": True},
            {"name": "correlation", "direction": "BUY", "confirmed": True},
            {"name": "volume", "direction": "BUY", "confirmed": False},
        ],
        "ultimate_confluence_min_confirmations": 2,
        "ultimate_data_provenance": "observed timestamped independent signal studies",
    }
    state.update(overrides)
    return state


def test_ultimate_sandwich_requires_alternation_tightness_and_confirmed_break():
    result = evaluate_module("ultimate_sandwich_pattern", _ultimate_sandwich())
    assert result["view"] == "BUY"
    assert result["ultimate_sandwich_assessment"] == "QUALIFIED_BREAK"
    assert result["ultimate_sandwich_bar_count"] == 6

    invalid = evaluate_module(
        "ultimate_sandwich_pattern",
        _ultimate_sandwich(ultimate_sandwich_bar_directions=["UP", "UP", "DOWN", "UP"]),
    )
    assert invalid["view"] == "WAIT"
    assert invalid["ultimate_sandwich_assessment"] == "ALTERNATION_INVALID"


def test_ultimate_fractal_only_signals_an_observed_early_stage():
    result = evaluate_module("ultimate_fractal_pattern", _ultimate_fractal())
    assert result["view"] == "BUY"
    assert result["ultimate_fractal_assessment"] == "EARLY_STAGE_SIGNAL"

    mature = evaluate_module(
        "ultimate_fractal_pattern",
        _ultimate_fractal(ultimate_fractal_stage="mature"),
    )
    assert mature["view"] == "WAIT"
    assert mature["ultimate_fractal_assessment"] == "EARLY_STAGE_REQUIRED"


def test_ultimate_local_extrema_timing_aligns_buy_with_support_minimum():
    result = evaluate_module("ultimate_local_extrema_timing", _ultimate_extreme())
    assert result["view"] == "BUY"
    assert result["ultimate_extreme_assessment"] == "LOCAL_MINIMUM_ENTRY_ZONE"

    wrong_zone = evaluate_module(
        "ultimate_local_extrema_timing",
        _ultimate_extreme(ultimate_extreme_zone="resistance"),
    )
    assert wrong_zone["view"] == "WAIT"
    assert wrong_zone["ultimate_extreme_assessment"] == "EXTREME_ZONE_MISMATCH"


def test_ultimate_sentiment_uses_recent_change_not_absolute_positioning():
    result = evaluate_module("ultimate_sentiment_change", _ultimate_sentiment())
    assert result["view"] == "BUY"
    assert result["ultimate_sentiment_change_pct"] == pytest.approx(5.0)

    invalid = evaluate_module(
        "ultimate_sentiment_change",
        _ultimate_sentiment(ultimate_sentiment_current_short_pct=40.0),
    )
    assert invalid["view"] == "WAIT"
    assert invalid["ultimate_sentiment_assessment"] == "SENTIMENT_TOTAL_INVALID"


def test_ultimate_high_performance_confluence_requires_agreeing_confirmed_signals():
    result = evaluate_module("ultimate_high_performance_confluence", _ultimate_confluence())
    assert result["view"] == "BUY"
    assert result["ultimate_confluence_assessment"] == "CONFIRMED_CONFLUENCE"
    assert result["ultimate_confluence_confirmed_count"] == 2

    disagreement = evaluate_module(
        "ultimate_high_performance_confluence",
        _ultimate_confluence(ultimate_confluence_signals=[
            {"name": "pattern", "direction": "BUY", "confirmed": True},
            {"name": "correlation", "direction": "SELL", "confirmed": True},
        ]),
    )
    assert disagreement["view"] == "WAIT"
    assert disagreement["ultimate_confluence_assessment"] == "SIGNAL_DISAGREEMENT"


def _schwager_trap(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "schwager_original_breakout_direction": "UP",
        "schwager_trap_confirmation": "strong price",
        "schwager_trap_confirmation_observed": True,
        "schwager_trap_invalidated": False,
        "schwager_data_provenance": "observed timestamped range breakout replay",
    }
    state.update(overrides)
    return state


def _schwager_false_trend(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "schwager_trend_direction": "DOWN",
        "schwager_trend_line_break_direction": "UP",
        "schwager_counter_close_count": 2,
        "schwager_required_counter_closes": 2,
        "schwager_false_breakout_confirmed": True,
        "schwager_data_provenance": "observed timestamped trend-line closes",
    }
    state.update(overrides)
    return state


def _schwager_gap(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "schwager_gap_direction": "UP",
        "schwager_gap_filled_by_close": True,
        "schwager_gap_width_class": "wide",
        "schwager_gap_breakaway": True,
        "schwager_consecutive_gaps_filled": 1,
        "schwager_filled_gap_invalidated": False,
        "schwager_data_provenance": "observed timestamped gap and closing prices",
    }
    state.update(overrides)
    return state


def _schwager_spike(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_spike_direction": "UP",
        "schwager_spike_extreme_penetrated": True,
        "schwager_spike_age_weeks": 4.0,
        "schwager_spike_magnitude": 2.0,
        "schwager_spike_invalidated": False,
        "schwager_data_provenance": "observed timestamped spike extreme replay",
    }
    state.update(overrides)
    return state


def _schwager_wide_day(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_wide_day_direction": "DOWN",
        "schwager_wide_day_penetration_direction": "UP",
        "schwager_wide_day_extreme_penetrated": True,
        "schwager_wide_day_close_strength": "strong",
        "schwager_wide_day_invalidated": False,
        "schwager_data_provenance": "observed timestamped wide-range-day closes",
    }
    state.update(overrides)
    return state


def _schwager_counter_flag(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "schwager_flag_prior_swing_direction": "DOWN",
        "schwager_flag_breakout_direction": "UP",
        "schwager_flag_breakout_confirmed": True,
        "schwager_flag_invalidated": False,
        "schwager_data_provenance": "observed timestamped flag breakout replay",
    }
    state.update(overrides)
    return state


def test_schwager_bull_bear_trap_fades_a_confirmed_failed_range_break():
    result = evaluate_module("schwager_bull_bear_trap", _schwager_trap())
    assert result["view"] == "SELL"
    assert result["schwager_trap_assessment"] == "BULL_TRAP_CONFIRMED"

    invalidated = evaluate_module(
        "schwager_bull_bear_trap",
        _schwager_trap(schwager_trap_invalidated=True),
    )
    assert invalidated["view"] == "WAIT"
    assert invalidated["schwager_trap_assessment"] == "TRAP_INVALIDATED"


def test_schwager_false_trend_breakout_requires_repeated_counter_closes():
    result = evaluate_module("schwager_false_trend_breakout", _schwager_false_trend())
    assert result["view"] == "SELL"
    assert result["schwager_false_trend_assessment"] == "FALSE_UPSIDE_BREAK"

    insufficient = evaluate_module(
        "schwager_false_trend_breakout",
        _schwager_false_trend(schwager_counter_close_count=1),
    )
    assert insufficient["view"] == "WAIT"
    assert insufficient["schwager_false_trend_assessment"] == "COUNTER_CLOSES_INSUFFICIENT"


def test_schwager_gap_failure_requires_a_close_based_fill_not_intraday_touch():
    result = evaluate_module("schwager_filled_gap_failure", _schwager_gap())
    assert result["view"] == "SELL"
    assert result["schwager_gap_assessment"] == "FILLED_GAP_FAILURE"

    touch_only = evaluate_module(
        "schwager_filled_gap_failure",
        _schwager_gap(schwager_gap_filled_by_close=False),
    )
    assert touch_only["view"] == "WAIT"
    assert touch_only["schwager_gap_assessment"] == "CLOSE_FILL_REQUIRED"


def test_schwager_spike_extreme_penetration_continues_beyond_the_failed_spike():
    result = evaluate_module("schwager_spike_extreme_failure", _schwager_spike())
    assert result["view"] == "BUY"
    assert result["schwager_spike_assessment"] == "SPIKE_EXTREME_PENETRATED"

    invalidated = evaluate_module(
        "schwager_spike_extreme_failure",
        _schwager_spike(schwager_spike_invalidated=True),
    )
    assert invalidated["view"] == "WAIT"
    assert invalidated["schwager_spike_assessment"] == "SPIKE_SIGNAL_INVALIDATED"


def test_schwager_wide_range_day_failure_requires_opposite_extreme_close():
    result = evaluate_module("schwager_wide_range_day_failure", _schwager_wide_day())
    assert result["view"] == "BUY"
    assert result["schwager_wide_day_assessment"] == "WIDE_DAY_FAILURE_CONFIRMED"

    mismatch = evaluate_module(
        "schwager_wide_range_day_failure",
        _schwager_wide_day(schwager_wide_day_penetration_direction="DOWN"),
    )
    assert mismatch["view"] == "WAIT"
    assert mismatch["schwager_wide_day_assessment"] == "PENETRATION_DIRECTION_INVALID"


def test_schwager_counter_flag_break_trades_the_unexpected_direction():
    result = evaluate_module("schwager_counter_flag_failure", _schwager_counter_flag())
    assert result["view"] == "BUY"
    assert result["schwager_flag_assessment"] == "COUNTER_BREAK_CONFIRMED"

    expected = evaluate_module(
        "schwager_counter_flag_failure",
        _schwager_counter_flag(schwager_flag_breakout_direction="DOWN"),
    )
    assert expected["view"] == "WAIT"
    assert expected["schwager_flag_assessment"] == "BREAK_NOT_COUNTER_TO_SWING"


def _aziz_bottom_reversal(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aziz_consecutive_down_candles": 5,
        "aziz_rsi": 8.0,
        "aziz_level_role": "support",
        "aziz_confirmation_candle": "bullish doji",
        "aziz_new_high_triggered": True,
        "aziz_data_provenance": "observed timestamped five-minute reversal study",
    }
    state.update(overrides)
    return state


def _aziz_top_reversal(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "aziz_consecutive_up_candles": 5,
        "aziz_rsi": 92.0,
        "aziz_level_role": "resistance",
        "aziz_confirmation_candle": "bearish doji",
        "aziz_new_low_triggered": True,
        "aziz_data_provenance": "observed timestamped five-minute reversal study",
    }
    state.update(overrides)
    return state


def _aziz_ma_trend(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aziz_ma_period": 9,
        "aziz_price_relation_to_ma": "above",
        "aziz_ma_role": "support",
        "aziz_ma_confirmation": True,
        "aziz_ma_entry_near": True,
        "aziz_ma_break_invalidated": False,
        "aziz_data_provenance": "observed timestamped moving-average trend study",
    }
    state.update(overrides)
    return state


def _aziz_vwap(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aziz_vwap_relation": "above",
        "aziz_vwap_retest_outcome": "held",
        "aziz_vwap_session_phase": "post_open",
        "aziz_vwap_data_provenance": "observed timestamped VWAP interaction",
    }
    state.update(overrides)
    return state


def _aziz_stock_in_play(**overrides):
    state = {
        "symbol": "AAPL",
        "side": "BUY",
        "aziz_asset_class": "equity",
        "aziz_gap_usd": 1.20,
        "aziz_atr_usd": 0.75,
        "aziz_relative_volume": 2.0,
        "aziz_average_daily_volume": 800000,
        "aziz_stock_scanner_data_provenance": "observed timestamped equity scanner",
    }
    state.update(overrides)
    return state


def test_aziz_bottom_reversal_requires_extreme_selloff_support_and_trigger():
    result = evaluate_module("aziz_bottom_reversal", _aziz_bottom_reversal())
    assert result["view"] == "BUY"
    assert result["aziz_bottom_assessment"] == "CONFIRMED_BOTTOM_REVERSAL"

    weak = evaluate_module("aziz_bottom_reversal", _aziz_bottom_reversal(aziz_rsi=20.0))
    assert weak["view"] == "WAIT"
    assert weak["aziz_bottom_assessment"] == "RSI_NOT_EXTREME"


def test_aziz_top_reversal_mirrors_bottom_reversal_conditions():
    result = evaluate_module("aziz_top_reversal", _aziz_top_reversal())
    assert result["view"] == "SELL"
    assert result["aziz_top_assessment"] == "CONFIRMED_TOP_REVERSAL"

    wrong_trigger = evaluate_module(
        "aziz_top_reversal",
        _aziz_top_reversal(aziz_new_low_triggered=False),
    )
    assert wrong_trigger["view"] == "WAIT"
    assert wrong_trigger["aziz_top_assessment"] == "TRIGGER_NOT_CONFIRMED"


def test_aziz_moving_average_trend_requires_confirmed_near_ma_entry():
    result = evaluate_module("aziz_moving_average_trend", _aziz_ma_trend())
    assert result["view"] == "BUY"
    assert result["aziz_ma_assessment"] == "CONFIRMED_MA_TREND"

    far = evaluate_module("aziz_moving_average_trend", _aziz_ma_trend(aziz_ma_entry_near=False))
    assert far["view"] == "WAIT"
    assert far["aziz_ma_assessment"] == "ENTRY_NOT_NEAR_MA"


def test_aziz_vwap_control_distinguishes_held_and_rejected_vwap():
    result = evaluate_module("aziz_vwap_control", _aziz_vwap())
    assert result["view"] == "BUY"
    assert result["aziz_vwap_assessment"] == "BUYER_CONTROL_ABOVE_VWAP"

    sideways = evaluate_module(
        "aziz_vwap_control",
        _aziz_vwap(aziz_vwap_retest_outcome="sideways"),
    )
    assert sideways["view"] == "WAIT"
    assert sideways["aziz_vwap_assessment"] == "VWAP_CONTROL_UNRESOLVED"


def test_aziz_stock_in_play_scanner_is_equity_scoped_and_uses_all_thresholds():
    result = evaluate_module("aziz_stock_in_play_scanner", _aziz_stock_in_play())
    assert result["view"] == "WAIT"
    assert result["aziz_stock_scanner_assessment"] == "STOCK_IN_PLAY"

    fx = evaluate_module(
        "aziz_stock_in_play_scanner",
        _aziz_stock_in_play(aziz_asset_class="forex"),
    )
    assert fx["applicability"] == "NOT_APPLICABLE"
    assert fx["aziz_stock_scanner_assessment"] == "EQUITY_ONLY"


def _tharp_narrow_range(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "tharp_trend_direction": "BUY",
        "tharp_range_ratio": 0.55,
        "tharp_inside_day": False,
        "tharp_narrowest_range": False,
        "tharp_breakout_direction": "BUY",
        "tharp_entry_confirmation": "confirmed",
        "tharp_data_provenance": "observed timestamped range and entry study",
    }
    state.update(overrides)
    return state


def _tharp_failed_test(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "tharp_test_extreme_direction": "UP",
        "tharp_test_returned_inside": True,
        "tharp_test_reversal_direction": "SELL",
        "tharp_test_confirmation": "confirmed",
        "tharp_data_provenance": "observed timestamped failed-test sequence",
    }
    state.update(overrides)
    return state


def _tharp_mae(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "tharp_current_mae_r": 0.80,
        "tharp_winner_mae_p95_r": 1.00,
        "tharp_initial_stop_r": 1.30,
        "tharp_mae_data_provenance": "observed broker-confirmed winner and loser outcomes",
    }
    state.update(overrides)
    return state


def _tharp_expectancy(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "tharp_win_probability": 0.45,
        "tharp_average_win_r": 2.0,
        "tharp_average_loss_r": 1.0,
        "tharp_cost_r": 0.10,
        "tharp_expectancy_sample_n": 120,
        "tharp_expectancy_data_provenance": "observed chronological net outcomes",
    }
    state.update(overrides)
    return state


def _tharp_market_selection(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "tharp_liquidity_status": "liquid",
        "tharp_volatility_reward_to_risk": 2.5,
        "tharp_market_fit": "fits trend criteria",
        "tharp_market_selection_data_provenance": "observed timestamped market-selection study",
    }
    state.update(overrides)
    return state


def test_tharp_narrow_range_setup_requires_trend_compression_and_timing_trigger():
    result = evaluate_module("tharp_narrow_range_breakout", _tharp_narrow_range())
    assert result["view"] == "BUY"
    assert result["tharp_narrow_range_assessment"] == "CONFIRMED_SETUP"

    wide = evaluate_module(
        "tharp_narrow_range_breakout", _tharp_narrow_range(tharp_range_ratio=0.75)
    )
    assert wide["view"] == "WAIT"
    assert wide["tharp_narrow_range_assessment"] == "COMPRESSION_NOT_CONFIRMED"

    no_trigger = evaluate_module(
        "tharp_narrow_range_breakout",
        _tharp_narrow_range(tharp_entry_confirmation="unconfirmed"),
    )
    assert no_trigger["view"] == "WAIT"
    assert no_trigger["tharp_narrow_range_assessment"] == "TIMING_NOT_CONFIRMED"


def test_tharp_failed_test_reversal_requires_return_inside_and_confirmation():
    result = evaluate_module("tharp_failed_test_reversal", _tharp_failed_test())
    assert result["view"] == "SELL"
    assert result["tharp_failed_test_assessment"] == "CONFIRMED_REVERSAL"

    no_return = evaluate_module(
        "tharp_failed_test_reversal", _tharp_failed_test(tharp_test_returned_inside=False)
    )
    assert no_return["view"] == "WAIT"
    assert no_return["tharp_failed_test_assessment"] == "NO_FAILED_TEST"


def test_tharp_mae_band_is_a_non_directional_warning_for_stop_research():
    within = evaluate_module("tharp_mae_winner_band", _tharp_mae())
    assert within["view"] == "WAIT"
    assert within["tharp_mae_assessment"] == "WITHIN_WINNER_BAND"
    assert within["directional_claim"] is False

    exceeded = evaluate_module(
        "tharp_mae_winner_band", _tharp_mae(tharp_current_mae_r=1.20)
    )
    assert exceeded["view"] == "WAIT"
    assert exceeded["tharp_mae_assessment"] == "EXCEEDS_WINNER_BAND"
    assert exceeded["warnings"]


def test_tharp_r_multiple_expectancy_is_after_cost_and_not_a_win_rate_gate():
    result = evaluate_module("tharp_r_multiple_expectancy", _tharp_expectancy())
    assert result["view"] == "WAIT"
    assert result["tharp_expectancy_assessment"] == "POSITIVE_EXPECTANCY"
    assert result["tharp_expectancy_per_r"] == pytest.approx(0.25)
    assert result["directional_claim"] is False

    negative = evaluate_module(
        "tharp_r_multiple_expectancy",
        _tharp_expectancy(tharp_win_probability=0.30, tharp_cost_r=0.20),
    )
    assert negative["tharp_expectancy_assessment"] == "NON_POSITIVE_EXPECTANCY"


def test_tharp_market_selection_requires_liquidity_and_two_to_three_r_volatility():
    result = evaluate_module("tharp_market_selection", _tharp_market_selection())
    assert result["view"] == "WAIT"
    assert result["tharp_market_selection_assessment"] == "MARKET_FITS"
    assert result["directional_claim"] is False

    low_vol = evaluate_module(
        "tharp_market_selection",
        _tharp_market_selection(tharp_volatility_reward_to_risk=1.2),
    )
    assert low_vol["tharp_market_selection_assessment"] == "INSUFFICIENT_VOLATILITY"


def _ponsi_ema_trend(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ponsi_trend_direction": "BUY",
        "ponsi_ma10": 1.1050,
        "ponsi_ma20": 1.1040,
        "ponsi_ma50": 1.1020,
        "ponsi_ma200": 1.0950,
        "ponsi_ema10_support_bars": 12,
        "ponsi_price_at_ema10": True,
        "ponsi_pullback_confirmation": "confirmed",
        "ponsi_stop_buffer_atr": 0.50,
        "ponsi_data_provenance": "observed timestamped daily EMA and pullback study",
    }
    state.update(overrides)
    return state


def _ponsi_squeeze(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "SELL",
        "ponsi_ema20_slope": "flat",
        "ponsi_atr_trend": "falling",
        "ponsi_bollinger_width_trend": "falling",
        "ponsi_consolidation_bars": 18,
        "ponsi_breakout_direction": "SELL",
        "ponsi_breakout_confirmation": "confirmed",
        "ponsi_data_provenance": "observed timestamped ATR and Bollinger-width study",
    }
    state.update(overrides)
    return state


def test_ponsi_ema_trend_technique_requires_proper_order_ema_support_and_pullback():
    result = evaluate_module("ponsi_ema_trend_technique", _ponsi_ema_trend())
    assert result["view"] == "BUY"
    assert result["ponsi_ema_technique_assessment"] == "CONFIRMED_PULLBACK"
    assert result["ponsi_stop_buffer_atr"] == pytest.approx(0.50)

    insufficient_support = evaluate_module(
        "ponsi_ema_trend_technique", _ponsi_ema_trend(ponsi_ema10_support_bars=7)
    )
    assert insufficient_support["view"] == "WAIT"
    assert insufficient_support["ponsi_ema_technique_assessment"] == "EMA_SUPPORT_NOT_ESTABLISHED"

    wrong_order = evaluate_module(
        "ponsi_ema_trend_technique", _ponsi_ema_trend(ponsi_ma20=1.1060)
    )
    assert wrong_order["view"] == "WAIT"
    assert wrong_order["ponsi_ema_technique_assessment"] == "PROPER_ORDER_MISSING"


def test_ponsi_squeeze_play_requires_falling_volatility_and_confirmed_breakout():
    result = evaluate_module("ponsi_squeeze_play", _ponsi_squeeze())
    assert result["view"] == "SELL"
    assert result["ponsi_squeeze_assessment"] == "CONFIRMED_BREAKOUT"

    rising_vol = evaluate_module(
        "ponsi_squeeze_play", _ponsi_squeeze(ponsi_atr_trend="rising")
    )
    assert rising_vol["view"] == "WAIT"
    assert rising_vol["ponsi_squeeze_assessment"] == "VOLATILITY_NOT_CONTRACTING"

    no_break = evaluate_module(
        "ponsi_squeeze_play", _ponsi_squeeze(ponsi_breakout_confirmation="unconfirmed")
    )
    assert no_break["view"] == "WAIT"
    assert no_break["ponsi_squeeze_assessment"] == "BREAKOUT_NOT_CONFIRMED"


def _ultimate_ema_reversal(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ultimate_ema_fast_period": 9,
        "ultimate_ema_slow_period": 15,
        "ultimate_ema_cross_direction": "up",
        "ultimate_ema_cross_confirmed": True,
        "ultimate_data_provenance": "observed timestamped EMA crossover",
    }
    state.update(overrides)
    return state


def _ultimate_head_shoulders(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "SELL",
        "ultimate_hs_pattern": "head_and_shoulders",
        "ultimate_hs_left_head_complete": True,
        "ultimate_hs_right_shoulder_observed": True,
        "ultimate_hs_right_shoulder_overlap_pct": 85,
        "ultimate_data_provenance": "observed timestamped swing-pattern study",
    }
    state.update(overrides)
    return state


def _ultimate_double_triple(**overrides):
    state = {
        "symbol": "USDJPY",
        "side": "BUY",
        "ultimate_multi_test_type": "double_bottom",
        "ultimate_multi_test_zone": "support",
        "ultimate_multi_test_count": 2,
        "ultimate_multi_test_bounce_confirmed": True,
        "ultimate_data_provenance": "observed timestamped support retests",
    }
    state.update(overrides)
    return state


def _ultimate_vpa(**overrides):
    state = {
        "symbol": "AUDUSD",
        "side": "SELL",
        "ultimate_vpa_timeframe": "1H",
        "ultimate_vpa_volume_event": "spike",
        "ultimate_vpa_price_location": "daily_high_resistance",
        "ultimate_vpa_volume_ratio": 1.8,
        "ultimate_data_provenance": "observed timestamped volume-price study",
    }
    state.update(overrides)
    return state


def _ultimate_mtf(**overrides):
    state = {
        "symbol": "EURGBP",
        "side": "BUY",
        "ultimate_mtf_entry_direction": "BUY",
        "ultimate_mtf_higher_direction": "BUY",
        "ultimate_mtf_higher_timeframe": "daily",
        "ultimate_mtf_agreement_confirmed": True,
        "ultimate_data_provenance": "observed timestamped multi-timeframe study",
    }
    state.update(overrides)
    return state


def _ultimate_mw(**overrides):
    state = {
        "symbol": "NZDUSD",
        "side": "BUY",
        "ultimate_mw_shape": "W",
        "ultimate_mw_zone": "support",
        "ultimate_mw_completed": True,
        "ultimate_data_provenance": "observed timestamped price-pattern study",
    }
    state.update(overrides)
    return state


def test_ultimate_ema_reversal_uses_the_source_9_15_crossover():
    result = evaluate_module("ultimate_ema_reversal", _ultimate_ema_reversal())
    assert result["view"] == "BUY"
    assert result["ultimate_ema_assessment"] == "CONFIRMED_CROSS"

    invalid = evaluate_module(
        "ultimate_ema_reversal", _ultimate_ema_reversal(ultimate_ema_fast_period=8)
    )
    assert invalid["view"] == "WAIT"
    assert invalid["ultimate_ema_assessment"] == "EMA_PERIODS_INVALID"


def test_ultimate_head_shoulders_requires_an_overlapping_right_shoulder():
    result = evaluate_module("ultimate_head_shoulders", _ultimate_head_shoulders())
    assert result["view"] == "SELL"
    assert result["ultimate_hs_assessment"] == "RIGHT_SHOULDER_SETUP"

    weak_overlap = evaluate_module(
        "ultimate_head_shoulders",
        _ultimate_head_shoulders(ultimate_hs_right_shoulder_overlap_pct=79),
    )
    assert weak_overlap["view"] == "WAIT"
    assert weak_overlap["ultimate_hs_assessment"] == "SHOULDER_OVERLAP_INSUFFICIENT"


def test_ultimate_double_triple_test_requires_zone_aligned_bounce():
    result = evaluate_module("ultimate_double_triple_test", _ultimate_double_triple())
    assert result["view"] == "BUY"
    assert result["ultimate_multi_test_assessment"] == "CONFIRMED_BOTTOM_BOUNCE"

    mismatch = evaluate_module(
        "ultimate_double_triple_test",
        _ultimate_double_triple(ultimate_multi_test_zone="resistance"),
    )
    assert mismatch["view"] == "WAIT"
    assert mismatch["ultimate_multi_test_assessment"] == "ZONE_PATTERN_MISMATCH"


def test_ultimate_vpa_extreme_reversal_uses_volume_spike_and_daily_extreme():
    result = evaluate_module("ultimate_vpa_extreme", _ultimate_vpa())
    assert result["view"] == "SELL"
    assert result["ultimate_vpa_assessment"] == "SPIKE_AT_RESISTANCE"

    weak_volume = evaluate_module(
        "ultimate_vpa_extreme", _ultimate_vpa(ultimate_vpa_volume_ratio=0.9)
    )
    assert weak_volume["view"] == "WAIT"
    assert weak_volume["ultimate_vpa_assessment"] == "VOLUME_EVENT_INVALID"


def test_ultimate_mtf_confirmation_requires_directional_agreement():
    result = evaluate_module("ultimate_mtf_confirmation", _ultimate_mtf())
    assert result["view"] == "BUY"
    assert result["ultimate_mtf_assessment"] == "CONFIRMED_AGREEMENT"

    disagreement = evaluate_module(
        "ultimate_mtf_confirmation",
        _ultimate_mtf(ultimate_mtf_higher_direction="SELL"),
    )
    assert disagreement["view"] == "WAIT"
    assert disagreement["ultimate_mtf_assessment"] == "TIMEFRAME_DISAGREEMENT"


def test_ultimate_mw_bat_is_explicitly_low_confidence_context():
    result = evaluate_module("ultimate_mw_bat_pattern", _ultimate_mw())
    assert result["view"] == "BUY"
    assert result["ultimate_mw_assessment"] == "LOW_CONFIDENCE_PATTERN"
    assert result["confidence_class"] == "LOW"
    assert result["execution_authority"] is False


def _thomas_ma_momentum(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "thomas_ma_fast_period": 3,
        "thomas_ma_slow_period": 10,
        "thomas_ma_direction": "up",
        "thomas_ma_separation_observed": True,
        "thomas_candles_hug_fast_ma": True,
        "thomas_candles_touch_slow_ma": False,
        "thomas_data_provenance": "observed timestamped moving-average momentum study",
    }
    state.update(overrides)
    return state


def _thomas_breakeven(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "BUY",
        "thomas_trade_in_profit": True,
        "thomas_first_hourly_pullback_complete": True,
        "thomas_continued_after_first_pullback": True,
        "thomas_break_even_ready": True,
        "thomas_data_provenance": "observed timestamped trade-management study",
    }
    state.update(overrides)
    return state


def _thomas_target(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "thomas_stop_pips": 25,
        "thomas_target_pips": 250,
        "thomas_target_multiple": 10,
        "thomas_data_provenance": "observed timestamped fixed-R geometry study",
    }
    state.update(overrides)
    return state


def test_thomas_ma_momentum_requires_separated_3_and_10_period_averages():
    result = evaluate_module("thomas_ma_momentum_filter", _thomas_ma_momentum())
    assert result["view"] == "BUY"
    assert result["thomas_ma_assessment"] == "STRONG_MOMENTUM"

    weak = evaluate_module(
        "thomas_ma_momentum_filter",
        _thomas_ma_momentum(thomas_candles_touch_slow_ma=True),
    )
    assert weak["view"] == "WAIT"
    assert weak["thomas_ma_assessment"] == "WEAK_MOMENTUM"


def test_thomas_break_even_rule_waits_for_first_pullback_then_continuation():
    result = evaluate_module("thomas_break_even_after_pullback", _thomas_breakeven())
    assert result["view"] == "WAIT"
    assert result["thomas_breakeven_assessment"] == "MOVE_TO_BREAK_EVEN"
    assert result["directional_claim"] is False

    early = evaluate_module(
        "thomas_break_even_after_pullback",
        _thomas_breakeven(thomas_first_hourly_pullback_complete=False),
    )
    assert early["thomas_breakeven_assessment"] == "WAIT_FOR_FIRST_PULLBACK"


def test_thomas_fixed_r_target_requires_source_geometry():
    result = evaluate_module("thomas_fixed_r_target", _thomas_target())
    assert result["view"] == "WAIT"
    assert result["thomas_target_assessment"] == "TARGET_GEOMETRY_VALID"
    assert result["directional_claim"] is False

    mismatch = evaluate_module(
        "thomas_fixed_r_target",
        _thomas_target(thomas_target_pips=200),
    )
    assert mismatch["thomas_target_assessment"] == "TARGET_GEOMETRY_INVALID"


def _grail_regime(**overrides):
    state = {
        "symbol": "GBPUSD",
        "side": "BUY",
        "grail_strategy_regime": "trending",
        "grail_intraday_trend_present": True,
        "grail_regime_observed": True,
        "grail_regime_provenance": "observed timestamped regime study",
    }
    state.update(overrides)
    return state


def test_grail_regime_warning_rejects_the_trend_system_in_a_nontrend_regime():
    result = evaluate_module("grail_regime_failure_warning", _grail_regime())
    assert result["view"] == "WAIT"
    assert result["grail_regime_assessment"] == "REGIME_FITS"
    assert result["directional_claim"] is False

    no_trend = evaluate_module(
        "grail_regime_failure_warning",
        _grail_regime(grail_strategy_regime="range", grail_intraday_trend_present=False),
    )
    assert no_trend["grail_regime_assessment"] == "SYSTEM_NOT_FIT"
    assert no_trend["warnings"]


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "oreste_qpl_interaction",
        "oreste_entelechy_confluence",
        "oreste_time_price_confluence",
        "oreste_volatility_scaled_risk",
        "quantum_finance_scenario_stress",
        "douglas_probability_edge",
        "tendler_process_error",
        "drakoln_plan_integrity",
        "narang_horizon_specification",
        "narang_conditional_alpha",
        "narang_cost_hurdle",
        "narang_liquidity_impact",
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
        "thomas_ma_momentum_filter",
        "thomas_break_even_after_pullback",
        "thomas_fixed_r_target",
        "ponsi_ema_trend_technique",
        "ponsi_squeeze_play",
        "pyramiding_risk_lock",
        "grinold_information_horizon",
        "grinold_trade_utility",
        "clenow_regime_filter",
        "clenow_atr_impact_sizing",
        "clenow_currency_exposure",
        "cartea_state_intensity",
        "cartea_quote_freshness_guard",
        "edwards_magee_dow_confirmation",
        "edwards_magee_basing_points_stop",
        "carter_352_play",
        "ultimate_sandwich_pattern",
        "ultimate_fractal_pattern",
        "ultimate_local_extrema_timing",
        "ultimate_sentiment_change",
        "ultimate_high_performance_confluence",
        "schwager_bull_bear_trap",
        "schwager_false_trend_breakout",
        "schwager_filled_gap_failure",
        "schwager_spike_extreme_failure",
        "schwager_wide_range_day_failure",
        "schwager_counter_flag_failure",
        "aziz_bottom_reversal",
        "aziz_top_reversal",
        "aziz_moving_average_trend",
        "aziz_vwap_control",
        "aziz_stock_in_play_scanner",
    ],
)
def test_remaining_book_algorithms_fail_closed_without_evidence(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
    assert result["research_only"] is True
