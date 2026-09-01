from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Steve Nison — Beyond Candlesticks"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "nison_data_provenance": "causal_price_filtered_chart_proxy",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("algorithm_id", "specific", "expected_view"),
    [
        (
            "nison_three_line_break",
            {
                "nison_three_line_direction": "up",
                "nison_three_line_consecutive": 3,
                "nison_three_line_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "nison_renko_trend",
            {
                "nison_renko_direction": "down",
                "nison_renko_bricks": 4,
                "nison_renko_reversal_size_pips": 5.0,
                "nison_renko_confirmation": "confirmed",
            },
            "SELL",
        ),
        (
            "nison_kagi_yang_yin",
            {
                "nison_kagi_line": "yang",
                "nison_kagi_structure": "rising_shoulders_rising_waists",
                "nison_kagi_transition": "confirmed",
            },
            "BUY",
        ),
        (
            "nison_disparity_reversal",
            {
                "nison_disparity_state": "oversold",
                "nison_reversal_direction": "up",
                "nison_reversal_confirmation": "confirmed",
            },
            "BUY",
        ),
    ],
)
def test_nison_modules_emit_only_after_their_named_price_filtered_signal(
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
        "nison_three_line_break",
        "nison_renko_trend",
        "nison_kagi_yang_yin",
        "nison_disparity_reversal",
    ],
)
def test_nison_modules_fail_closed_without_their_chart_evidence(algorithm_id):
    result = evaluate_module(algorithm_id, _state())

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_three_line_break_does_not_call_alternating_lines_a_trend():
    result = evaluate_module(
        "nison_three_line_break",
        _state(
            nison_three_line_direction="up",
            nison_three_line_consecutive=2,
            nison_three_line_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "three" in " ".join(result["reasons"]).lower()


def test_kagi_thin_yin_line_is_bearish_even_if_side_is_buy():
    result = evaluate_module(
        "nison_kagi_yang_yin",
        _state(
            nison_kagi_line="yin",
            nison_kagi_structure="falling_shoulders_falling_waists",
            nison_kagi_transition="confirmed",
        ),
    )

    assert result["view"] == "SELL"
    assert result["candidate_alignment"] == "OPPOSES"


def test_disparity_without_reversal_confirmation_is_only_context():
    result = evaluate_module(
        "nison_disparity_reversal",
        _state(
            nison_disparity_state="overbought",
            nison_reversal_direction="down",
            nison_reversal_confirmation="not_confirmed",
        ),
    )

    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("specific", "expected_view", "side"),
    [
        (
            {
                "nison_three_windows_direction": "rising",
                "nison_three_windows_count": 3,
                "nison_three_windows_last_window_close": "below_bottom",
                "nison_three_windows_confirmation": "confirmed",
            },
            "SELL",
            "SELL",
        ),
        (
            {
                "nison_three_windows_direction": "falling",
                "nison_three_windows_count": 4,
                "nison_three_windows_last_window_close": "above_top",
                "nison_three_windows_confirmation": True,
            },
            "BUY",
            "BUY",
        ),
    ],
)
def test_three_windows_requires_last_window_close_confirmation(specific, expected_view, side):
    result = evaluate_module("nison_three_windows", _state(side=side, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["nison_three_windows_assessment"].endswith("CONFIRMED")
    assert result["execution_authority"] is False


def test_three_windows_does_not_countertrade_on_intraday_penetration_only():
    result = evaluate_module(
        "nison_three_windows",
        _state(
            side="SELL",
            nison_three_windows_direction="rising",
            nison_three_windows_count=3,
            nison_three_windows_last_window_close="intraday_below_bottom",
            nison_three_windows_confirmation="not_confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert "close" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize(
    ("specific", "expected_view", "side"),
    [
        (
            {
                "nison_gapping_doji_trend": "falling",
                "nison_gapping_doji_gap_direction": "lower",
                "nison_gapping_doji_is_doji": True,
                "nison_gapping_doji_confirmation_direction": "down",
                "nison_gapping_doji_confirmation": "confirmed",
            },
            "SELL",
            "SELL",
        ),
        (
            {
                "nison_gapping_doji_trend": "rising",
                "nison_gapping_doji_gap_direction": "higher",
                "nison_gapping_doji_is_doji": True,
                "nison_gapping_doji_confirmation_direction": "up",
                "nison_gapping_doji_confirmation": True,
            },
            "BUY",
            "BUY",
        ),
    ],
)
def test_gapping_doji_requires_next_session_confirmation(specific, expected_view, side):
    result = evaluate_module("nison_gapping_doji", _state(side=side, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["nison_gapping_doji_assessment"].endswith("CONFIRMED")


def test_gapping_doji_without_follow_through_is_not_a_signal():
    result = evaluate_module(
        "nison_gapping_doji",
        _state(
            side="SELL",
            nison_gapping_doji_trend="falling",
            nison_gapping_doji_gap_direction="lower",
            nison_gapping_doji_is_doji=True,
            nison_gapping_doji_confirmation_direction="up",
            nison_gapping_doji_confirmation=False,
        ),
    )

    assert result["view"] == "WAIT"
    assert "confirmation" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize(
    ("specific", "expected_view", "side"),
    [
        (
            {
                "nison_extra_confirmation_turnaround": "up",
                "nison_extra_confirmation_line": "up",
                "nison_extra_confirmation": True,
            },
            "BUY",
            "BUY",
        ),
        (
            {
                "nison_extra_confirmation_turnaround": "down",
                "nison_extra_confirmation_line": "down",
                "nison_extra_confirmation": "confirmed",
            },
            "SELL",
            "SELL",
        ),
    ],
)
def test_extra_line_break_confirmation_requires_following_same_color_line(
    specific, expected_view, side
):
    result = evaluate_module("nison_extra_line_break_confirmation", _state(side=side, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["execution_authority"] is False


def test_extra_line_break_confirmation_does_not_promote_turnaround_alone():
    result = evaluate_module(
        "nison_extra_line_break_confirmation",
        _state(
            side="BUY",
            nison_extra_confirmation_turnaround="up",
            nison_extra_confirmation_line="down",
            nison_extra_confirmation=False,
        ),
    )

    assert result["view"] == "WAIT"
    assert "extra" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize(
    ("sequence", "expected_view", "side"),
    [
        ("black_shoe_white_suit_white_neck", "BUY", "BUY"),
        ("white_neck_black_suit_black_shoe", "SELL", "SELL"),
    ],
)
def test_three_line_neck_requires_the_book_sequence_and_small_line(
    sequence, expected_view, side
):
    result = evaluate_module(
        "nison_three_line_neck",
        _state(
            side=side,
            nison_three_line_neck_sequence=sequence,
            nison_three_line_neck_small_line=True,
            nison_three_line_neck_confirmation="confirmed",
        ),
    )

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"


def test_three_line_neck_without_small_neck_or_shoe_is_wait():
    result = evaluate_module(
        "nison_three_line_neck",
        _state(
            side="BUY",
            nison_three_line_neck_sequence="black_shoe_white_suit_white_neck",
            nison_three_line_neck_small_line=False,
            nison_three_line_neck_confirmation=True,
        ),
    )

    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("specific", "expected_view", "side"),
    [
        (
            {
                "nison_kagi_double_window_type": "bottom",
                "nison_kagi_double_window_trend": "down",
                "nison_kagi_double_window_left_separation": True,
                "nison_kagi_double_window_right_separation": True,
                "nison_kagi_double_window_confirmation_direction": "up",
                "nison_kagi_double_window_confirmation": True,
            },
            "BUY",
            "BUY",
        ),
        (
            {
                "nison_kagi_double_window_type": "top",
                "nison_kagi_double_window_trend": "up",
                "nison_kagi_double_window_left_separation": True,
                "nison_kagi_double_window_right_separation": True,
                "nison_kagi_double_window_confirmation_direction": "down",
                "nison_kagi_double_window_confirmation": "confirmed",
            },
            "SELL",
            "SELL",
        ),
    ],
)
def test_kagi_double_window_requires_both_level_separations_and_break(
    specific, expected_view, side
):
    result = evaluate_module("nison_kagi_double_window", _state(side=side, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"


def test_kagi_double_window_without_both_separations_is_not_a_signal():
    result = evaluate_module(
        "nison_kagi_double_window",
        _state(
            side="BUY",
            nison_kagi_double_window_type="bottom",
            nison_kagi_double_window_trend="down",
            nison_kagi_double_window_left_separation=True,
            nison_kagi_double_window_right_separation=False,
            nison_kagi_double_window_confirmation_direction="up",
            nison_kagi_double_window_confirmation=True,
        ),
    )

    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("specific", "expected_view", "side"),
    [
        (
            {
                "nison_kagi_tweezers_type": "top",
                "nison_kagi_tweezers_level_match": True,
                "nison_kagi_tweezers_confirmation_direction": "down",
                "nison_kagi_tweezers_confirmation": True,
            },
            "SELL",
            "SELL",
        ),
        (
            {
                "nison_kagi_tweezers_type": "bottom",
                "nison_kagi_tweezers_level_match": True,
                "nison_kagi_tweezers_confirmation_direction": "up",
                "nison_kagi_tweezers_confirmation": "confirmed",
            },
            "BUY",
            "BUY",
        ),
    ],
)
def test_kagi_tweezers_requires_matching_level_and_confirmation(specific, expected_view, side):
    result = evaluate_module("nison_kagi_tweezers", _state(side=side, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"


def test_kagi_tweezers_without_level_match_is_wait():
    result = evaluate_module(
        "nison_kagi_tweezers",
        _state(
            side="SELL",
            nison_kagi_tweezers_type="top",
            nison_kagi_tweezers_level_match=False,
            nison_kagi_tweezers_confirmation_direction="down",
            nison_kagi_tweezers_confirmation=True,
        ),
    )

    assert result["view"] == "WAIT"


@pytest.mark.parametrize(
    ("specific", "expected_view", "side"),
    [
        (
            {
                "nison_kagi_three_buddha_type": "top",
                "nison_kagi_three_buddha_break_direction": "below",
                "nison_kagi_three_buddha_break_levels": 1,
                "nison_kagi_three_buddha_confirmation": True,
            },
            "SELL",
            "SELL",
        ),
        (
            {
                "nison_kagi_three_buddha_type": "reverse",
                "nison_kagi_three_buddha_break_direction": "above",
                "nison_kagi_three_buddha_break_levels": 2,
                "nison_kagi_three_buddha_confirmation": "confirmed",
            },
            "BUY",
            "BUY",
        ),
    ],
)
def test_kagi_three_buddha_requires_right_shoulder_break(specific, expected_view, side):
    result = evaluate_module("nison_kagi_three_buddha", _state(side=side, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"


def test_kagi_three_buddha_without_right_shoulder_break_is_wait():
    result = evaluate_module(
        "nison_kagi_three_buddha",
        _state(
            side="SELL",
            nison_kagi_three_buddha_type="top",
            nison_kagi_three_buddha_break_direction="above",
            nison_kagi_three_buddha_break_levels=1,
            nison_kagi_three_buddha_confirmation=True,
        ),
    )

    assert result["view"] == "WAIT"
