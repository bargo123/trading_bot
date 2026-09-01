import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Edwards & Magee — Technical Analysis of Stock Trends"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "em_data_provenance": "causal_completed_quote_bar_proxy",
        "em_volume_provenance": "real_traded_volume",
        "feature_provenance": {"edwards_magee": "causal_completed_quote_bar_proxy"},
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("algorithm_id", "specific", "expected_view"),
    [
        (
            "edwards_magee_head_shoulders",
            {
                "em_setup": "head_shoulders_top",
                "em_breakout_direction": "down",
                "em_breakout_confirmation": "confirmed",
                "em_volume_pattern": "right_shoulder_lower_volume",
                "em_neckline_break_pips": 3.0,
            },
            "SELL",
        ),
        (
            "edwards_magee_triangle_breakout",
            {
                "em_setup": "symmetrical_triangle",
                "em_breakout_direction": "up",
                "em_breakout_confirmation": "confirmed",
                "em_triangle_stage": "half_to_three_quarters",
                "em_breakout_volume_ratio": 1.8,
            },
            "BUY",
        ),
        (
            "edwards_magee_gap_classification",
            {
                "em_gap_type": "breakaway",
                "em_gap_direction": "up",
                "em_gap_confirmation": "confirmed",
                "em_gap_size_pips": 4.0,
            },
            "BUY",
        ),
        (
            "edwards_magee_support_resistance_flip",
            {
                "em_sr_role": "resistance_to_support",
                "em_sr_retest": "held",
                "em_sr_confirmation": "confirmed",
                "em_sr_break_margin_pips": 2.0,
            },
            "BUY",
        ),
        (
            "edwards_magee_channel_deterioration",
            {
                "em_channel_direction": "up",
                "em_channel_state": "basic_line_broken",
                "em_channel_confirmation": "confirmed",
                "em_channel_break_margin_pips": 2.0,
            },
            "SELL",
        ),
    ],
)
def test_classical_chart_modules_require_named_confirmed_setup(algorithm_id, specific, expected_view):
    result = evaluate_module(algorithm_id, _state(side=expected_view, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "edwards_magee_head_shoulders",
        "edwards_magee_triangle_breakout",
        "edwards_magee_gap_classification",
        "edwards_magee_support_resistance_flip",
        "edwards_magee_channel_deterioration",
    ],
)
def test_classical_chart_modules_fail_closed_without_causal_setup(algorithm_id):
    result = evaluate_module(algorithm_id, _state())

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_triangle_upside_requires_real_volume_confirmation():
    result = evaluate_module(
        "edwards_magee_triangle_breakout",
        _state(
            em_setup="symmetrical_triangle",
            em_breakout_direction="up",
            em_breakout_confirmation="confirmed",
            em_triangle_stage="half_to_three_quarters",
            em_breakout_volume_ratio=1.8,
            em_volume_provenance="tick_activity_proxy",
        ),
    )

    assert result["view"] == "WAIT"
    assert any("volume" in warning.lower() for warning in result["warnings"])


def test_gap_area_event_is_wait_not_a_directional_breakout():
    result = evaluate_module(
        "edwards_magee_gap_classification",
        _state(
            em_gap_type="area",
            em_gap_direction="up",
            em_gap_confirmation="confirmed",
            em_gap_size_pips=3.0,
        ),
    )

    assert result["view"] == "WAIT"
    assert "area" in " ".join(result["reasons"]).lower()


def test_head_and_shoulders_requires_the_source_volume_sequence_not_only_a_shape_label():
    result = evaluate_module(
        "edwards_magee_head_shoulders",
        _state(
            em_setup="head_shoulders_top",
            em_breakout_direction="down",
            em_breakout_confirmation="confirmed",
            em_volume_pattern="flat_volume",
            em_neckline_break_pips=3.0,
        ),
    )

    assert result["view"] == "WAIT"
    assert "volume" in " ".join(result["reasons"]).lower()


def test_triangle_breakout_requires_source_quality_volume_in_both_directions():
    result = evaluate_module(
        "edwards_magee_triangle_breakout",
        _state(
            side="SELL",
            em_setup="descending_triangle",
            em_breakout_direction="down",
            em_breakout_confirmation="confirmed",
            em_triangle_stage="half_to_three_quarters",
            em_breakout_volume_ratio=1.8,
            em_volume_provenance="tick_activity_proxy",
        ),
    )

    assert result["view"] == "WAIT"
    assert "volume" in " ".join(result["warnings"]).lower()


def test_one_day_reversal_is_a_temporary_countertrend_signal_only_with_extreme_volume():
    result = evaluate_module(
        "edwards_magee_one_day_reversal",
        _state(
            em_one_day_trend="up",
            em_one_day_intraday_range_pct=2.5,
            em_one_day_net_change_pct=0.2,
            em_one_day_volume_ratio=2.4,
            em_one_day_reversal_confirmation="confirmed",
        ),
    )

    assert result["view"] == "SELL"
    assert result["applicability"] == "APPLICABLE"
    assert result["edwards_magee_horizon"] == "temporary_minor_trend"


def test_one_day_reversal_rejects_a_tick_activity_proxy_as_source_volume():
    result = evaluate_module(
        "edwards_magee_one_day_reversal",
        _state(
            em_one_day_trend="up",
            em_one_day_intraday_range_pct=2.5,
            em_one_day_net_change_pct=0.2,
            em_one_day_volume_ratio=2.4,
            em_one_day_reversal_confirmation="confirmed",
            em_volume_provenance="tick_activity_proxy",
        ),
    )

    assert result["view"] == "WAIT"
    assert "real" in " ".join(result["warnings"]).lower()


def test_selling_climax_requires_panic_decline_extreme_volume_and_recovery():
    result = evaluate_module(
        "edwards_magee_selling_climax",
        _state(
            side="BUY",
            em_climax_decline_intensity="panic",
            em_climax_gap_direction="down",
            em_climax_volume_ratio=3.0,
            em_climax_recovery_confirmation="confirmed",
        ),
    )

    assert result["view"] == "BUY"
    assert result["edwards_magee_horizon"] == "short_term"


def test_selling_climax_does_not_fire_without_a_recovery_confirmation():
    result = evaluate_module(
        "edwards_magee_selling_climax",
        _state(
            em_climax_decline_intensity="panic",
            em_climax_gap_direction="down",
            em_climax_volume_ratio=3.0,
            em_climax_recovery_confirmation="not_confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "recovery" in " ".join(result["reasons"]).lower()


def test_trendline_penetration_requires_extent_volume_and_post_break_action():
    result = evaluate_module(
        "edwards_magee_trendline_penetration",
        _state(
            side="SELL",
            em_trendline_direction="up",
            em_trendline_penetration_pips=3.0,
            em_trendline_volume_ratio=1.8,
            em_trendline_post_action="follow_through",
            em_trendline_confirmation="confirmed",
        ),
    )

    assert result["view"] == "SELL"
    assert result["edwards_magee_tests_passed"] == ["extent", "volume", "post_action"]


def test_trendline_penetration_waits_when_the_post_break_action_is_not_observed():
    result = evaluate_module(
        "edwards_magee_trendline_penetration",
        _state(
            em_trendline_direction="up",
            em_trendline_penetration_pips=3.0,
            em_trendline_volume_ratio=1.8,
            em_trendline_post_action="unresolved",
            em_trendline_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "post-penetration" in " ".join(result["reasons"]).lower()


def test_right_angled_broadening_breakout_is_directional_only_after_decisive_real_volume_break():
    result = evaluate_module(
        "edwards_magee_broadening_breakout",
        _state(
            side="BUY",
            em_broadening_type="flat_top",
            em_broadening_break_direction="up",
            em_broadening_break_margin_pct=3.2,
            em_broadening_volume_ratio=1.7,
            em_broadening_confirmation="confirmed",
        ),
    )

    assert result["view"] == "BUY"
    assert result["edwards_magee_assessment"] == "RIGHT_ANGLED_BROADENING_BREAK"


def test_symmetrical_broadening_is_a_warning_not_a_directional_entry():
    result = evaluate_module(
        "edwards_magee_broadening_breakout",
        _state(
            em_broadening_type="symmetrical",
            em_broadening_break_direction="down",
            em_broadening_break_margin_pct=3.2,
            em_broadening_volume_ratio=1.7,
            em_broadening_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "unreliable" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize(
    ("trend", "extreme", "close_relation", "expected"),
    [
        ("up", "new_high", "below_prior_close", "SELL"),
        ("down", "new_low", "above_prior_close", "BUY"),
    ],
)
def test_key_reversal_day_reverses_the_prior_trend_only_after_the_extreme_fails(
    trend, extreme, close_relation, expected
):
    result = evaluate_module(
        "edwards_magee_key_reversal_day",
        _state(
            side=expected,
            em_key_reversal_trend=trend,
            em_key_reversal_extreme=extreme,
            em_key_reversal_close_relation=close_relation,
            em_key_reversal_confirmation="confirmed",
        ),
    )

    assert result["view"] == expected
    assert result["edwards_magee_assessment"] == "KEY_REVERSAL_DAY"


def test_key_reversal_day_waits_when_the_extreme_and_prior_close_do_not_agree():
    result = evaluate_module(
        "edwards_magee_key_reversal_day",
        _state(
            em_key_reversal_trend="up",
            em_key_reversal_extreme="new_high",
            em_key_reversal_close_relation="above_prior_close",
            em_key_reversal_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "extreme" in " ".join(result["reasons"]).lower()


def test_spike_reversal_uses_context_close_and_followup_confirmation():
    result = evaluate_module(
        "edwards_magee_spike_reversal",
        _state(
            side="SELL",
            em_spike_context="top",
            em_spike_range_ratio=2.2,
            em_spike_close_bias="down",
            em_spike_followup="reversal_confirmed",
            em_spike_confirmation="confirmed",
        ),
    )

    assert result["view"] == "SELL"
    assert result["edwards_magee_assessment"] == "SPIKE_REVERSAL"


def test_spike_reversal_waits_until_later_bars_distinguish_it_from_a_runaway_day():
    result = evaluate_module(
        "edwards_magee_spike_reversal",
        _state(
            em_spike_context="top",
            em_spike_range_ratio=2.2,
            em_spike_close_bias="down",
            em_spike_followup="unresolved",
            em_spike_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "follow" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize(
    ("followup", "returned_to_origin", "expected"),
    [
        ("continued_volume", False, "BUY"),
        ("false_return", True, "SELL"),
    ],
)
def test_runaway_day_requires_followup_and_reverses_only_after_return_to_origin(
    followup, returned_to_origin, expected
):
    result = evaluate_module(
        "edwards_magee_runaway_day",
        _state(
            side=expected,
            em_runaway_direction="up",
            em_runaway_range_ratio=2.4,
            em_runaway_close_location="near_high",
            em_runaway_followup=followup,
            em_runaway_returned_to_origin=returned_to_origin,
            em_runaway_confirmation="confirmed",
            em_volume_provenance="real_traded_volume",
        ),
    )

    assert result["view"] == expected
    assert result["edwards_magee_assessment"] in {"RUNAWAY_CONTINUATION", "RUNAWAY_FALSE_SIGNAL"}
