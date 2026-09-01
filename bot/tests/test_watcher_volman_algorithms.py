from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


VOLMAN_SOURCE = "Bob Volman — Forex Price Action Scalping"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "volman_trend": "up",
        "volman_signal_direction": "up",
        "volman_signal_break": "confirmed",
        "volman_path_clear": True,
        "volman_data_provenance": "causal_quote_bar_proxy",
        "feature_provenance": {"volman": "causal_quote_bar_proxy"},
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("algorithm_id", "specific", "expected_view"),
    [
        (
            "volman_double_doji_break",
            {
                "volman_setup": "double_doji_break",
                "volman_pullback_to_ema": True,
                "volman_pattern_bars": 2,
                "volman_signal_bar_range_pips": 5.0,
            },
            "BUY",
        ),
        (
            "volman_first_break",
            {
                "volman_setup": "first_break",
                "volman_burst_move": True,
                "volman_first_pullback": True,
                "volman_pullback_to_ema": True,
                "volman_signal_bar_range_pips": 6.0,
            },
            "BUY",
        ),
        (
            "volman_second_break",
            {
                "volman_setup": "second_break",
                "volman_first_break_failed": True,
                "volman_second_attempt": True,
            },
            "BUY",
        ),
        (
            "volman_block_break",
            {
                "volman_setup": "block_break",
                "volman_block_bars": 4,
                "volman_block_compression": True,
                "volman_market_pressure": "up",
            },
            "BUY",
        ),
        (
            "volman_range_break",
            {
                "volman_setup": "range_break",
                "volman_range_bars": 8,
                "volman_range_width_pips": 22.0,
                "volman_prebreak_tension": True,
            },
            "BUY",
        ),
        (
            "volman_inside_range_break",
            {
                "volman_setup": "inside_range_break",
                "volman_range_bars": 8,
                "volman_inner_block_bars": 3,
                "volman_range_room_pips": 14.0,
            },
            "BUY",
        ),
        (
            "volman_advanced_range_break",
            {
                "volman_setup": "advanced_range_break",
                "volman_prior_range_break": True,
                "volman_post_break_retest": True,
                "volman_signal_cluster_bars": 3,
            },
            "BUY",
        ),
    ],
)
def test_volman_setup_modules_emit_only_after_their_own_confirmations(
    algorithm_id, specific, expected_view
):
    result = evaluate_module(algorithm_id, _state(**specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [VOLMAN_SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "volman_double_doji_break",
        "volman_first_break",
        "volman_second_break",
        "volman_block_break",
        "volman_range_break",
        "volman_inside_range_break",
        "volman_advanced_range_break",
    ],
)
def test_volman_setup_modules_fail_closed_when_setup_evidence_is_absent(algorithm_id):
    result = evaluate_module(algorithm_id, _state())

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_volman_sell_orientation_is_preserved():
    result = evaluate_module(
        "volman_second_break",
        _state(
            side="SELL",
            volman_trend="down",
            volman_signal_direction="down",
            volman_setup="second_break",
            volman_first_break_failed=True,
            volman_second_attempt=True,
        ),
    )

    assert result["view"] == "SELL"
    assert result["candidate_alignment"] == "SUPPORTS"


def test_volman_range_break_does_not_treat_a_tease_or_blocked_path_as_a_signal():
    result = evaluate_module(
        "volman_range_break",
        _state(
            volman_setup="range_break",
            volman_range_bars=8,
            volman_range_width_pips=22.0,
            volman_prebreak_tension=True,
            volman_signal_break="tease",
            volman_path_clear=False,
        ),
    )

    assert result["view"] == "WAIT"
    assert "confirmed" in " ".join(result["reasons"]).lower() or "path" in " ".join(result["reasons"]).lower()
