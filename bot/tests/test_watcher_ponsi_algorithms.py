from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Ed Ponsi — Forex Patterns & Probabilities"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "ponsi_data_provenance": "causal_completed_quote_bar_proxy",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("algorithm_id", "specific", "expected_view"),
    [
        (
            "ponsi_level_bounce",
            {
                "ponsi_level_type": "support",
                "ponsi_first_bounce": True,
                "ponsi_reversal_direction": "up",
                "ponsi_entry_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "ponsi_intraday_breakout",
            {
                "ponsi_triangle_type": "ascending_triangle",
                "ponsi_prior_trend": "up",
                "ponsi_session_quality": "london_new_york_high_liquidity",
                "ponsi_breakout_direction": "up",
                "ponsi_breakout_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "ponsi_pennant_continuation",
            {
                "ponsi_pattern": "pennant",
                "ponsi_flagpole_direction": "up",
                "ponsi_flagpole_impulse": True,
                "ponsi_consolidation_contracting": True,
                "ponsi_consolidation_bars": 3,
                "ponsi_breakout_direction": "up",
                "ponsi_breakout_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "ponsi_round_number_bounce",
            {
                "ponsi_round_number_test": "resistance",
                "ponsi_extension_from_ma_pips": 24.0,
                "ponsi_first_bounce": True,
                "ponsi_reversal_direction": "down",
                "ponsi_entry_confirmation": "confirmed",
            },
            "SELL",
        ),
        (
            "ponsi_boomerang_fade",
            {
                "ponsi_dead_zone": True,
                "ponsi_breakout_direction": "down",
                "ponsi_reversal_confirmation": "confirmed",
                "ponsi_open_retest": True,
                "ponsi_time_remaining_s": 4200.0,
            },
            "BUY",
        ),
    ],
)
def test_ponsi_modules_emit_only_after_their_own_confirmed_setup(
    algorithm_id, specific, expected_view
):
    result = evaluate_module(algorithm_id, _state(side=expected_view, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "ponsi_level_bounce",
        "ponsi_intraday_breakout",
        "ponsi_pennant_continuation",
        "ponsi_round_number_bounce",
        "ponsi_boomerang_fade",
    ],
)
def test_ponsi_modules_fail_closed_without_causal_setup(algorithm_id):
    result = evaluate_module(algorithm_id, _state())

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_intraday_breakout_requires_trend_and_liquid_session_alignment():
    result = evaluate_module(
        "ponsi_intraday_breakout",
        _state(
            ponsi_triangle_type="ascending_triangle",
            ponsi_prior_trend="down",
            ponsi_session_quality="late_asia_low_liquidity",
            ponsi_breakout_direction="up",
            ponsi_breakout_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "trend" in " ".join(result["reasons"]).lower() or "liquidity" in " ".join(result["reasons"]).lower()


def test_round_number_bounce_does_not_use_a_small_extension():
    result = evaluate_module(
        "ponsi_round_number_bounce",
        _state(
            ponsi_round_number_test="support",
            ponsi_extension_from_ma_pips=12.0,
            ponsi_first_bounce=True,
            ponsi_reversal_direction="up",
            ponsi_entry_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "20" in " ".join(result["reasons"])


def test_boomerang_does_not_trade_outside_the_low_liquidity_window():
    result = evaluate_module(
        "ponsi_boomerang_fade",
        _state(
            ponsi_dead_zone=False,
            ponsi_breakout_direction="down",
            ponsi_reversal_confirmation="confirmed",
            ponsi_open_retest=True,
            ponsi_time_remaining_s=4200.0,
        ),
    )

    assert result["view"] == "WAIT"
    assert "dead zone" in " ".join(result["reasons"]).lower()


def test_ponsi_sell_orientation_is_preserved():
    result = evaluate_module(
        "ponsi_pennant_continuation",
        _state(
            side="SELL",
            ponsi_pattern="flag",
            ponsi_flagpole_direction="down",
            ponsi_flagpole_impulse=True,
            ponsi_consolidation_contracting=True,
            ponsi_consolidation_bars=4,
            ponsi_breakout_direction="down",
            ponsi_breakout_confirmation="confirmed",
        ),
    )

    assert result["view"] == "SELL"
    assert result["candidate_alignment"] == "SUPPORTS"


def test_ponsi_multiple_timeframe_pullback_requires_long_trend_and_lower_timeframe_trigger():
    result = evaluate_module(
        "ponsi_multitimeframe_pullback",
        _state(
            side="BUY",
            ponsi_long_term_trend="up",
            ponsi_short_term_location="support",
            ponsi_short_term_oscillator="neutral",
            ponsi_oscillator_transition="not_needed",
            ponsi_mtf_data_provenance="observed timestamped daily and hourly study",
        ),
    )

    assert result["view"] == "BUY"
    assert result["ponsi_mtf_assessment"] == "TREND_ALIGNED_PULLBACK"

    opposite = evaluate_module(
        "ponsi_multitimeframe_pullback",
        _state(
            side="BUY",
            ponsi_long_term_trend="down",
            ponsi_short_term_location="support",
            ponsi_short_term_oscillator="oversold",
            ponsi_oscillator_transition="falling",
            ponsi_mtf_data_provenance="observed timestamped daily and hourly study",
        ),
    )
    assert opposite["view"] == "WAIT"
    assert opposite["ponsi_mtf_assessment"] == "LONG_TERM_DIRECTION_CONFLICT"


def test_ponsi_fibonacci_trend_reentry_requires_accepted_retracement_and_oscillator_turn():
    result = evaluate_module(
        "ponsi_fibonacci_trend_reentry",
        _state(
            side="SELL",
            ponsi_primary_trend="down",
            ponsi_fibonacci_ratio=0.382,
            ponsi_fibonacci_level_role="resistance",
            ponsi_fibonacci_at_level=True,
            ponsi_short_oscillator_state="overbought",
            ponsi_oscillator_transition="falling_to_neutral",
            ponsi_fibonacci_entry_confirmation="confirmed",
            ponsi_data_provenance="observed timestamped Fibonacci and oscillator study",
        ),
    )

    assert result["view"] == "SELL"
    assert result["ponsi_fibonacci_assessment"] == "CONFIRMED_TREND_REENTRY"

    no_turn = evaluate_module(
        "ponsi_fibonacci_trend_reentry",
        {
            **_state(
                side="SELL",
                ponsi_primary_trend="down",
                ponsi_fibonacci_ratio=0.618,
                ponsi_fibonacci_level_role="resistance",
                ponsi_fibonacci_at_level=True,
                ponsi_short_oscillator_state="overbought",
                ponsi_oscillator_transition="still_overbought",
                ponsi_fibonacci_entry_confirmation="confirmed",
                ponsi_data_provenance="observed timestamped Fibonacci and oscillator study",
            )
        },
    )
    assert no_turn["view"] == "WAIT"
    assert no_turn["ponsi_fibonacci_assessment"] == "OSCILLATOR_TURN_MISSING"


def test_ponsi_price_action_level_avoids_fast_approach_and_waits_for_confirmed_rejection():
    result = evaluate_module(
        "ponsi_price_action_level",
        _state(
            side="BUY",
            ponsi_price_level="support",
            ponsi_approach_speed="measured",
            ponsi_price_action="rejection",
            ponsi_entry_order_location="above_support",
            ponsi_level_test_count=1,
            ponsi_data_provenance="observed timestamped level-price action study",
        ),
    )
    assert result["view"] == "BUY"
    assert result["ponsi_price_action_assessment"] == "CONFIRMED_LEVEL_REACTION"

    freight_train = evaluate_module(
        "ponsi_price_action_level",
        _state(
            side="BUY",
            ponsi_price_level="support",
            ponsi_approach_speed="fast",
            ponsi_price_action="rejection",
            ponsi_entry_order_location="above_support",
            ponsi_level_test_count=1,
            ponsi_data_provenance="observed timestamped level-price action study",
        ),
    )
    assert freight_train["view"] == "WAIT"
    assert freight_train["ponsi_price_action_assessment"] == "FREIGHT_TRAIN_APPROACH"


def test_ponsi_round_trip_applies_short_term_spread_and_stop_geometry():
    result = evaluate_module(
        "ponsi_round_trip",
        _state(
            side="SELL",
            ponsi_round_trip_level="resistance",
            ponsi_round_trip_extension_pips=24.0,
            ponsi_round_trip_bounce_count=1,
            ponsi_round_trip_reversal_direction="down",
            ponsi_round_trip_spread_pips=4.0,
            ponsi_data_provenance="observed timestamped round-number intraday study",
        ),
    )
    assert result["view"] == "SELL"
    assert result["ponsi_round_trip_stop_pips"] == pytest.approx(19.0)
    assert result["ponsi_round_trip_first_target_pips"] == pytest.approx(19.0)

    wide = evaluate_module(
        "ponsi_round_trip",
        _state(
            side="SELL",
            ponsi_round_trip_level="resistance",
            ponsi_round_trip_extension_pips=24.0,
            ponsi_round_trip_bounce_count=1,
            ponsi_round_trip_reversal_direction="down",
            ponsi_round_trip_spread_pips=6.0,
            ponsi_data_provenance="observed timestamped round-number intraday study",
        ),
    )
    assert wide["view"] == "WAIT"
    assert wide["ponsi_round_trip_assessment"] == "SPREAD_TOO_WIDE"


@pytest.mark.parametrize(
    ("side", "base_rate", "quote_rate", "differential_change", "expected"),
    [
        ("BUY", 4.25, 1.0, 25.0, "BUY"),
        ("SELL", 1.0, 4.25, -25.0, "SELL"),
    ],
)
def test_ponsi_interest_rate_edge_requires_a_widening_signed_differential(
    side, base_rate, quote_rate, differential_change, expected
):
    result = evaluate_module(
        "ponsi_interest_rate_edge",
        _state(
            side=side,
            ponsi_base_rate=base_rate,
            ponsi_quote_rate=quote_rate,
            ponsi_rate_differential_bps=(base_rate - quote_rate) * 100.0,
            ponsi_rate_differential_change_bps=differential_change,
            ponsi_rate_policy_outlook="widening",
            ponsi_rate_data_provenance="observed timestamped central-bank rate study",
        ),
    )
    assert result["view"] == expected
    assert result["ponsi_carry_assessment"] == "WIDENING_CARRY_BIAS"


def test_ponsi_interest_rate_edge_does_not_turn_missing_macro_data_into_a_signal():
    result = evaluate_module(
        "ponsi_interest_rate_edge",
        _state(
            side="BUY",
            ponsi_base_rate=4.25,
            ponsi_quote_rate=1.0,
            ponsi_rate_differential_bps=325.0,
            ponsi_rate_differential_change_bps=25.0,
            ponsi_rate_policy_outlook="widening",
            ponsi_rate_data_provenance="synthetic fixture",
        ),
    )
    assert result["view"] == "MISSING_DATA"
    assert "ponsi_rate_data_provenance" in result["missing_inputs"]
