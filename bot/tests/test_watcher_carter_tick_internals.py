from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


def _state(**overrides):
    state = {
        "symbol": "ES",
        "side": "BUY",
        "carter_tick_price_change": -4.0,
        "carter_tick_change": 250.0,
        "carter_tick_divergence_min_abs": 100.0,
        "carter_tick_divergence_data_provenance": "observed intraday price and breadth ticks",
    }
    state.update(overrides)
    return state


def test_carter_tick_price_divergence_identifies_opposing_pressure():
    bullish = evaluate_module("carter_tick_price_divergence", _state())
    assert bullish["view"] == "BUY"
    assert bullish["carter_tick_divergence_action"] == "BULLISH_DIVERGENCE"

    bearish = evaluate_module(
        "carter_tick_price_divergence",
        _state(
            side="SELL",
            carter_tick_price_change=4.0,
            carter_tick_change=-250.0,
        ),
    )
    assert bearish["view"] == "SELL"
    assert bearish["carter_tick_divergence_action"] == "BEARISH_DIVERGENCE"


def test_carter_tick_noise_bands_keep_neutral_ticks_out_of_actionable_views():
    quiet = evaluate_module(
        "carter_tick_noise_regime",
        {
            "symbol": "ES",
            "side": "BUY",
            "carter_tick_value": 250.0,
            "carter_tick_data_provenance": "observed breadth tick",
        },
    )
    assert quiet["view"] == "WAIT"
    assert quiet["carter_tick_regime"] == "NOISE"

    extreme = evaluate_module(
        "carter_tick_noise_regime",
        {
            "symbol": "ES",
            "side": "BUY",
            "carter_tick_value": 1200.0,
            "carter_tick_data_provenance": "observed breadth tick",
        },
    )
    assert extreme["carter_tick_regime"] == "EXTREME_BUYING_PRESSURE"
    assert extreme["directional_claim"] is False


def test_carter_tick_internals_fail_closed_without_observed_breadth_data():
    for algorithm_id in ("carter_tick_price_divergence", "carter_tick_noise_regime"):
        result = evaluate_module(algorithm_id, {"symbol": "ES", "side": "BUY"})
        assert result["view"] == "MISSING_DATA"
        assert result["applicability"] == "MISSING_DATA"
        assert result["execution_authority"] is False
