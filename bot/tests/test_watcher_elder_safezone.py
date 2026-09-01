from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "elder_safezone_trend": "up",
        "elder_safezone_reference_price": 1.1050,
        "elder_safezone_average_penetration": 0.0008,
        "elder_safezone_coefficient": 2.0,
        "elder_safezone_lookback_days": 14,
        "elder_safezone_penetration_count": 5,
        "elder_safezone_data_provenance": "observed historical daily bars",
    }
    state.update(overrides)
    return state


def test_elder_safezone_places_a_stop_outside_observed_market_noise():
    long_stop = evaluate_module("elder_safezone_stop", _state())
    assert long_stop["view"] == "WAIT"
    assert long_stop["elder_safezone_action"] == "LONG_NOISE_BUFFER"
    assert long_stop["elder_safezone_stop_price"] == 1.1034
    assert long_stop["directional_claim"] is False

    short_stop = evaluate_module(
        "elder_safezone_stop",
        _state(
            side="SELL",
            elder_safezone_trend="down",
            elder_safezone_average_penetration=0.001,
            elder_safezone_coefficient=3.0,
        ),
    )
    assert short_stop["elder_safezone_action"] == "SHORT_NOISE_BUFFER"
    assert short_stop["elder_safezone_stop_price"] == 1.108


def test_elder_safezone_requires_the_source_coefficient_and_observed_penetrations():
    invalid = evaluate_module(
        "elder_safezone_stop",
        _state(elder_safezone_trend="down", elder_safezone_coefficient=2.0),
    )
    assert invalid["elder_safezone_action"] == "INVALID_SAFEZONE_INPUT"

    missing = evaluate_module("elder_safezone_stop", {"symbol": "EURUSD", "side": "BUY"})
    assert missing["view"] == "MISSING_DATA"
    assert missing["applicability"] == "MISSING_DATA"
    assert missing["execution_authority"] is False
