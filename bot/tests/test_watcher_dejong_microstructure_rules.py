import pytest

from aegis.research.watcher_algorithms import evaluate_module
from aegis.research.watcher_feature_engine import enrich_watcher_state


def test_dejong_roll_spread_requires_observed_transaction_price_autocovariance():
    result = evaluate_module(
        "dejong_roll_spread_estimator",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "dejong_roll_autocovariance": -0.000000000025,
            "dejong_roll_sample_n": 40,
            "dejong_roll_data_provenance": "observed_transaction_prices",
        },
    )

    assert result["view"] == "WAIT"
    assert result["applicability"] == "APPLICABLE"
    assert result["directional_claim"] is False
    assert result["dejong_roll_spread_estimate"] == pytest.approx(1e-5)
    assert result["dejong_roll_assessment"] == "SPREAD_ESTIMATED"
    assert result["execution_authority"] is False


def test_dejong_roll_does_not_treat_positive_autocovariance_as_a_spread_estimate():
    result = evaluate_module(
        "dejong_roll_spread_estimator",
        {
            "dejong_roll_autocovariance": 0.01,
            "dejong_roll_sample_n": 40,
            "dejong_roll_data_provenance": "observed_transaction_prices",
        },
    )

    assert result["view"] == "WAIT"
    assert result["dejong_roll_assessment"] == "NO_NEGATIVE_AUTOCOVARIANCE"
    assert "non-positive" in result["reasons"][0]
    assert "dejong_roll_spread_estimate" not in result


def test_dejong_roll_feature_is_causal_and_never_falls_back_to_midpoint_prices():
    prices = [1.10000, 1.10020, 1.10005, 1.10025, 1.10010, 1.10030, 1.10015]
    history = []
    for index, price in enumerate(prices):
        history.append(
            {
                "time": float(index),
                "bid": price - 0.00005,
                "ask": price + 0.00005,
                "last": price,
            }
        )
    history.append(
        {
            "time": 99.0,
            "bid": 9.0,
            "ask": 9.1,
            "last": 9.05,
        }
    )

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {
            "time": 6.0,
            "bid": prices[-1] - 0.00005,
            "ask": prices[-1] + 0.00005,
            "last": prices[-1],
        },
        symbol_history=history,
    )

    assert state["quote_history_future_excluded"] is True
    assert state["dejong_roll_sample_n"] == len(prices) - 1
    assert state["dejong_roll_autocovariance"] < 0
    assert state["dejong_roll_spread_estimate"] > 0
    assert state["dejong_roll_data_provenance"] == "observed_causal_transaction_prices"
    assert state["feature_provenance"]["dejong_roll"] == "observed_causal_transaction_prices"


def test_dejong_roll_is_missing_when_only_bid_ask_midpoints_exist():
    history = [
        {"time": float(i), "bid": 1.1 + i * 0.0001, "ask": 1.1001 + i * 0.0001}
        for i in range(8)
    ]

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 7.0, "bid": 1.1007, "ask": 1.1008},
        symbol_history=history,
    )

    result = evaluate_module("dejong_roll_spread_estimator", state)
    assert result["applicability"] == "MISSING_DATA"
    assert "dejong_roll_autocovariance" in result["missing_inputs"]
