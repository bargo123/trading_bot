from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _state(**overrides):
    state = {
        "evaluation_phase": "post_trade",
        "dejong_spread_data_provenance": "observed_transaction_quotes",
        "dejong_trade_observations": [
            {
                "bid": 100.0,
                "ask": 100.2,
                "trade_price": 100.2,
                "trade_initiator": "BUY",
                "next_midpoint": 100.15,
            },
            {
                "bid": 100.1,
                "ask": 100.3,
                "trade_price": 100.1,
                "trade_initiator": "SELL",
                "next_midpoint": 100.15,
            },
            {
                "bid": 100.2,
                "ask": 100.4,
                "trade_price": 100.4,
                "trade_initiator": "BUY",
                "next_midpoint": 100.35,
            },
        ],
    }
    state.update(overrides)
    return state


def test_dejong_spread_decomposition_applies_the_book_definitions():
    result = evaluate_module("dejong_spread_decomposition", _state())

    assert result["view"] == "WAIT"
    assert result["applicability"] == "APPLICABLE"
    assert result["directional_claim"] is False
    assert result["dejong_spread_sample_n"] == 3
    assert result["dejong_quoted_spread"] == pytest.approx(0.2)
    assert result["dejong_effective_spread"] == pytest.approx(0.2)
    assert result["dejong_realized_spread"] == pytest.approx(0.1)
    assert result["dejong_adverse_selection_proxy"] == pytest.approx(0.1)
    assert result["dejong_spread_assessment"] == "POSITIVE_ADVERSE_SELECTION_OR_INVENTORY"
    assert result["execution_authority"] is False


def test_dejong_spread_decomposition_is_not_a_pre_entry_signal():
    result = evaluate_module(
        "dejong_spread_decomposition",
        _state(evaluation_phase="pre_entry"),
    )

    assert result["view"] == "NOT_APPLICABLE"
    assert result["directional_claim"] is False
    assert result["execution_authority"] is False


def test_dejong_spread_decomposition_rejects_synthetic_transaction_provenance():
    result = evaluate_module(
        "dejong_spread_decomposition",
        _state(dejong_spread_data_provenance="synthetic_fixture"),
    )

    assert result["applicability"] == "MISSING_DATA"
    assert result["view"] == "MISSING_DATA"
    assert "dejong_spread_data_provenance" in result["missing_inputs"]


def test_dejong_spread_decomposition_does_not_silently_use_invalid_rows():
    result = evaluate_module(
        "dejong_spread_decomposition",
        _state(
            dejong_trade_observations=[
                {"bid": 1.0, "ask": 0.9, "trade_price": 0.9, "trade_initiator": "BUY"},
                {"bid": 1.0, "ask": 1.1, "trade_price": 1.1, "trade_initiator": "BUY"},
            ]
        ),
    )

    assert result["applicability"] == "MISSING_DATA"
    assert result["view"] == "MISSING_DATA"
    assert "dejong_trade_observations" in result["missing_inputs"]


def test_dejong_duration_weighted_spread_uses_observed_inter_quote_durations():
    result = evaluate_module(
        "dejong_duration_weighted_spread",
        {
            "dejong_quote_observations": [
                {"bid": 100.0, "ask": 100.1, "duration_s": 1.0},
                {"bid": 100.0, "ask": 100.5, "duration_s": 3.0},
            ],
            "dejong_duration_data_provenance": "observed_quote_intervals",
        },
    )

    assert result["view"] == "WAIT"
    assert result["applicability"] == "APPLICABLE"
    assert result["directional_claim"] is False
    assert result["dejong_quote_sample_n"] == 2
    assert result["dejong_calendar_time_spread"] == pytest.approx(0.3)
    assert result["dejong_duration_weighted_spread"] == pytest.approx(0.4)
    assert result["dejong_duration_assessment"] == "DURATION_WEIGHTED_WIDER"
    assert result["execution_authority"] is False


def test_dejong_duration_weighted_spread_rejects_proxy_intervals():
    result = evaluate_module(
        "dejong_duration_weighted_spread",
        {
            "dejong_quote_observations": [
                {"bid": 1.0, "ask": 1.1, "duration_s": 1.0},
                {"bid": 1.0, "ask": 1.2, "duration_s": 1.0},
            ],
            "dejong_duration_data_provenance": "tick_activity_proxy",
        },
    )

    assert result["applicability"] == "MISSING_DATA"
    assert result["view"] == "MISSING_DATA"
    assert "dejong_duration_data_provenance" in result["missing_inputs"]
