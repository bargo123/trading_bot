import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _provenance():
    return "observed_completed_quote_bars"


def test_brooks_barbwire_is_an_uncertainty_filter_not_a_directional_signal():
    result = evaluate_module(
        "brooks_barbwire_filter",
        {
            "brooks_barbwire_bars": 4,
            "brooks_barbwire_doji_count": 1,
            "brooks_barbwire_overlap_fraction": 0.75,
            "brooks_barbwire_tail_fraction": 0.6,
            "brooks_barbwire_data_provenance": _provenance(),
        },
    )
    assert result["view"] == "WAIT"
    assert result["brooks_barbwire_assessment"] == "BARBWIRE_UNCERTAINTY"
    assert result["directional_claim"] is False


def test_brooks_breakout_mode_requires_current_strength_and_prior_follow_through():
    result = evaluate_module(
        "brooks_breakout_mode",
        {
            "side": "BUY",
            "brooks_breakout_mode_active": True,
            "brooks_breakout_direction": "BUY",
            "brooks_breakout_body_fraction": 0.8,
            "brooks_breakout_tail_fraction": 0.2,
            "brooks_breakout_prior_follow_through": True,
            "brooks_breakout_data_provenance": _provenance(),
        },
    )
    assert result["view"] == "BUY"
    assert result["brooks_breakout_assessment"] == "CONFIRMED_BREAKOUT_MODE"

    weak = evaluate_module(
        "brooks_breakout_mode",
        {
            "side": "BUY",
            "brooks_breakout_mode_active": True,
            "brooks_breakout_direction": "BUY",
            "brooks_breakout_body_fraction": 0.8,
            "brooks_breakout_tail_fraction": 0.2,
            "brooks_breakout_prior_follow_through": False,
            "brooks_breakout_data_provenance": _provenance(),
        },
    )
    assert weak["view"] == "WAIT"


def test_brooks_failed_breakout_reverses_only_after_point_failure_and_confirmation():
    result = evaluate_module(
        "brooks_failed_breakout_reversal",
        {
            "side": "SELL",
            "brooks_failed_breakout_detected": True,
            "brooks_failed_breakout_original_direction": "BUY",
            "brooks_failed_breakout_reversal_confirmed": True,
            "brooks_failed_breakout_point": 1.102,
            "brooks_current_price": 1.100,
            "brooks_failed_breakout_range_midpoint": 1.101,
            "brooks_failed_breakout_data_provenance": _provenance(),
        },
    )
    assert result["view"] == "SELL"
    assert result["brooks_failed_breakout_target_distance"] == pytest.approx(0.001)

    unconfirmed = evaluate_module(
        "brooks_failed_breakout_reversal",
        {
            "side": "SELL",
            "brooks_failed_breakout_detected": True,
            "brooks_failed_breakout_original_direction": "BUY",
            "brooks_failed_breakout_reversal_confirmed": False,
            "brooks_failed_breakout_point": 1.102,
            "brooks_current_price": 1.100,
            "brooks_failed_breakout_range_midpoint": 1.101,
            "brooks_failed_breakout_data_provenance": _provenance(),
        },
    )
    assert unconfirmed["view"] == "WAIT"


def test_brooks_measured_move_projects_leg_one_equals_leg_two_without_entry_authority():
    result = evaluate_module(
        "brooks_measured_move_projection",
        {
            "brooks_measured_move_leg_start": 1.100,
            "brooks_measured_move_leg_end": 1.105,
            "brooks_measured_move_pullback_end": 1.103,
            "brooks_measured_move_direction": "BUY",
            "brooks_measured_move_data_provenance": _provenance(),
        },
    )
    assert result["view"] == "WAIT"
    assert result["brooks_measured_move_leg_size"] == pytest.approx(0.005)
    assert result["brooks_measured_move_target"] == pytest.approx(1.108)
    assert result["directional_claim"] is False


@pytest.mark.parametrize("algorithm_id", ["brooks_barbwire_filter", "brooks_breakout_mode", "brooks_failed_breakout_reversal", "brooks_measured_move_projection"])
def test_brooks_range_perspectives_are_research_only(algorithm_id):
    result = evaluate_module(algorithm_id, {})
    assert result["execution_authority"] is False
    assert result["research_only"] is True
    assert result["uses_future_data"] is False


def test_brooks_shrinking_stairs_marks_waning_breakout_momentum_without_a_directional_entry():
    result = evaluate_module(
        "brooks_shrinking_stairs",
        {
            "side": "BUY",
            "brooks_stairs_direction": "up",
            "brooks_stairs_breakout_sizes": [12, 8, 3],
            "brooks_stairs_data_provenance": _provenance(),
        },
    )

    assert result["view"] == "WAIT"
    assert result["brooks_stairs_assessment"] == "SHRINKING_STAIRS_WANING_MOMENTUM"
    assert result["warnings"]
    assert result["execution_authority"] is False


def test_brooks_shrinking_stairs_requires_three_positive_strictly_decreasing_breakouts():
    result = evaluate_module(
        "brooks_shrinking_stairs",
        {
            "side": "SELL",
            "brooks_stairs_direction": "down",
            "brooks_stairs_breakout_sizes": [3, 3, 1],
            "brooks_stairs_data_provenance": _provenance(),
        },
    )

    assert result["view"] == "WAIT"
    assert result["brooks_stairs_assessment"] == "NO_SHRINKING_STAIRS"
    assert result["reasons"]


def _micro_gap(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brooks_gap_trend_direction": "up",
        "brooks_gap_trend_bar_strength": "strong",
        "brooks_gap_before_high": 1.1000,
        "brooks_gap_before_low": 1.0990,
        "brooks_gap_after_high": 1.1020,
        "brooks_gap_after_low": 1.1010,
        "brooks_gap_data_provenance": _provenance(),
    }
    state.update(overrides)
    return state


def test_brooks_micro_measuring_gap_requires_nonoverlap_around_a_strong_bar():
    result = evaluate_module("brooks_micro_measuring_gap", _micro_gap())

    assert result["view"] == "BUY"
    assert result["brooks_gap_assessment"] == "BULL_MICRO_MEASURING_GAP"
    assert result["brooks_gap_signal_role"] == "STRENGTH_CONTEXT"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("brooks_gap_trend_bar_strength", "weak"),
        ("brooks_gap_after_low", 1.0995),
        ("brooks_gap_trend_direction", "down"),
    ],
)
def test_brooks_micro_measuring_gap_waits_without_strength_nonoverlap_and_alignment(field, value):
    result = evaluate_module("brooks_micro_measuring_gap", _micro_gap(**{field: value}))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_brooks_always_in_mode_requires_directional_mode_and_spike_confirmation():
    result = evaluate_module(
        "brooks_always_in_mode",
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "brooks_always_in_mode": True,
            "brooks_always_in_direction": "down",
            "brooks_always_in_spike_confirmed": True,
            "brooks_always_in_data_provenance": _provenance(),
        },
    )

    assert result["view"] == "SELL"
    assert result["brooks_always_in_assessment"] == "ALWAYS_IN_DIRECTION_CONFIRMED"
    assert result["execution_authority"] is False


def test_brooks_always_in_mode_does_not_authorize_when_mode_or_spike_is_missing():
    result = evaluate_module(
        "brooks_always_in_mode",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "brooks_always_in_mode": True,
            "brooks_always_in_direction": "up",
            "brooks_always_in_spike_confirmed": False,
            "brooks_always_in_data_provenance": _provenance(),
        },
    )

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_brooks_trader_equation_uses_probability_reward_risk_and_cost_without_a_95_percent_gate():
    result = evaluate_module(
        "brooks_trader_equation",
        {
            "brooks_trader_equation_probability": 0.60,
            "brooks_trader_equation_reward": 2.0,
            "brooks_trader_equation_risk": 1.0,
            "brooks_trader_equation_cost": 0.05,
            "brooks_trader_equation_unit": "points",
            "brooks_trader_equation_data_provenance": _provenance(),
        },
    )

    assert result["brooks_trader_equation_assessment"] == "POSITIVE_AFTER_COST"
    assert result["brooks_trader_equation_edge"] == pytest.approx(0.75)
    assert result["brooks_trader_equation_break_even_probability"] == pytest.approx(0.35)
    assert result["directional_claim"] is False
    assert "95-percent entry gate" in result["warnings"][0]


def test_brooks_trader_equation_rejects_negative_after_cost_and_missing_provenance():
    negative = evaluate_module(
        "brooks_trader_equation",
        {
            "brooks_trader_equation_probability": 0.40,
            "brooks_trader_equation_reward": 1.0,
            "brooks_trader_equation_risk": 1.0,
            "brooks_trader_equation_cost": 0.01,
            "brooks_trader_equation_unit": "points",
            "brooks_trader_equation_data_provenance": _provenance(),
        },
    )
    missing = evaluate_module(
        "brooks_trader_equation",
        {
            "brooks_trader_equation_probability": 0.60,
            "brooks_trader_equation_reward": 2.0,
            "brooks_trader_equation_risk": 1.0,
            "brooks_trader_equation_cost": 0.05,
            "brooks_trader_equation_unit": "points",
        },
    )

    assert negative["brooks_trader_equation_assessment"] == "NEGATIVE_AFTER_COST"
    assert missing["applicability"] == "MISSING_DATA"


def _two_reasons(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "brooks_entry_reasons": ["moving average pullback", "second leg confirmation"],
        "brooks_strong_trend": False,
        "brooks_second_entry": False,
        "brooks_trendline_overshoot_reversal": False,
        "brooks_countertrend": False,
        "brooks_two_reasons_data_provenance": _provenance(),
    }
    state.update(overrides)
    return state


def test_brooks_two_reasons_entry_supports_two_distinct_reasons_and_documented_exceptions():
    result = evaluate_module("brooks_two_reasons_entry", _two_reasons())
    second_entry = evaluate_module(
        "brooks_two_reasons_entry",
        _two_reasons(
            brooks_entry_reasons=["second entry"],
            brooks_second_entry=True,
        ),
    )

    assert result["view"] == "BUY"
    assert result["brooks_two_reasons_assessment"] == "TWO_REASONS_CONFIRMED"
    assert second_entry["view"] == "BUY"
    assert second_entry["brooks_two_reasons_assessment"] == "SECOND_ENTRY_SINGLE_REASON_EXCEPTION"


def test_brooks_two_reasons_entry_rejects_steep_countertrend_without_break_or_overshoot():
    result = evaluate_module(
        "brooks_two_reasons_entry",
        _two_reasons(
            brooks_entry_reasons=["high 2", "weak signal bar"],
            brooks_strong_trend=True,
            brooks_countertrend=True,
        ),
    )

    assert result["view"] == "WAIT"
    assert result["brooks_two_reasons_assessment"] == "COUNTERTREND_AGAINST_STEEP_TREND"


def test_brooks_timeframe_discipline_flags_holding_a_trade_beyond_its_plan():
    result = evaluate_module(
        "brooks_timeframe_discipline",
        {
            "brooks_intended_trade_type": "scalp",
            "brooks_planned_horizon_s": 60,
            "brooks_elapsed_horizon_s": 75,
            "brooks_horizon_plan_intact": False,
            "brooks_timeframe_data_provenance": _provenance(),
        },
    )

    assert result["brooks_timeframe_assessment"] == "TIMEFRAME_DRIFT_EXIT_REVIEW"
    assert result["brooks_timeframe_exceeded"] is True
    assert result["execution_authority"] is False


def test_brooks_timeframe_discipline_accepts_an_intact_plan_without_a_timer_exit():
    result = evaluate_module(
        "brooks_timeframe_discipline",
        {
            "brooks_intended_trade_type": "trade",
            "brooks_planned_horizon_s": 300,
            "brooks_elapsed_horizon_s": 120,
            "brooks_horizon_plan_intact": True,
            "brooks_timeframe_data_provenance": _provenance(),
        },
    )

    assert result["brooks_timeframe_assessment"] == "TIMEFRAME_PLAN_INTACT"
    assert result["brooks_timeframe_exceeded"] is False
    assert result["warnings"] == []


@pytest.mark.parametrize("algorithm_id", ["brooks_trader_equation", "brooks_two_reasons_entry", "brooks_timeframe_discipline"])
def test_new_brooks_perspectives_are_research_only(algorithm_id):
    result = evaluate_module(algorithm_id, {})
    assert result["execution_authority"] is False
    assert result["research_only"] is True
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    ("algorithm_id", "provenance_key"),
    [
        ("brooks_shrinking_stairs", "brooks_stairs_data_provenance"),
        ("brooks_micro_measuring_gap", "brooks_gap_data_provenance"),
        ("brooks_always_in_mode", "brooks_always_in_data_provenance"),
    ],
)
def test_brooks_quote_bar_proxy_is_allowed_only_with_exact_observed_label(algorithm_id, provenance_key):
    state = {
        "side": "BUY",
        "brooks_stairs_direction": "up",
        "brooks_stairs_breakout_sizes": [3, 2, 1],
        "brooks_gap_trend_direction": "up",
        "brooks_gap_trend_bar_strength": "strong",
        "brooks_gap_before_high": 1.1000,
        "brooks_gap_before_low": 1.0990,
        "brooks_gap_after_high": 1.1020,
        "brooks_gap_after_low": 1.1010,
        "brooks_always_in_mode": True,
        "brooks_always_in_direction": "up",
        "brooks_always_in_spike_confirmed": True,
        "brooks_stairs_data_provenance": "completed_quote_bar_proxy",
        "brooks_gap_data_provenance": "completed_quote_bar_proxy",
        "brooks_always_in_data_provenance": "completed_quote_bar_proxy",
    }
    result = evaluate_module(algorithm_id, state)
    assert result["view"] in {"BUY", "WAIT"}
    bad = dict(state)
    bad[provenance_key] = "synthetic_quote_bar_proxy"
    blocked = evaluate_module(algorithm_id, bad)
    assert blocked["applicability"] == "MISSING_DATA"
