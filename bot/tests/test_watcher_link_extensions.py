from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _adx(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "link_adx_value": 34.0,
        "link_adx_direction": "rising",
        "link_major_trend_direction": "BUY",
        "link_data_provenance": "observed causal indicator series",
    }
    state.update(overrides)
    return state


def _stochastic(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "link_stochastic_failure_direction": "up",
        "link_stochastic_fast_reversal": True,
        "link_stochastic_fast_crossed_slow": False,
        "link_stochastic_zone": "overbought",
        "link_data_provenance": "observed causal oscillator series",
    }
    state.update(overrides)
    return state


def _retracement(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "link_major_trend_direction": "BUY",
        "link_retracement_fraction": 0.50,
        "link_retracement_level_confirmed": True,
        "link_retracement_support_held": True,
        "link_retracement_chasing": False,
        "link_retracement_stop_outside": True,
        "link_data_provenance": "observed causal retracement series",
    }
    state.update(overrides)
    return state


def test_link_adx_switches_between_trend_and_range_modes():
    strong = evaluate_module("link_adx_regime_switch", _adx())
    range_bound = evaluate_module(
        "link_adx_regime_switch",
        _adx(link_adx_value=18.0, link_adx_direction="flat"),
    )
    weakening = evaluate_module(
        "link_adx_regime_switch",
        _adx(link_adx_value=34.0, link_adx_direction="falling"),
    )

    assert strong["link_adx_mode"] == "TREND_FOLLOWING"
    assert strong["view"] == "BUY"
    assert range_bound["link_adx_mode"] == "OSCILLATOR_RANGE"
    assert range_bound["view"] == "WAIT"
    assert weakening["link_adx_mode"] == "TREND_WEAKENING"
    assert weakening["view"] == "WAIT"
    assert strong["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"link_adx_value": 25.0},
        {"link_adx_direction": "falling", "link_adx_value": 18.0},
        {"link_major_trend_direction": "SELL"},
    ],
)
def test_link_adx_does_not_authorize_an_ambiguous_or_countertrend_state(overrides):
    result = evaluate_module("link_adx_regime_switch", _adx(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_link_stochastic_failed_move_maps_failed_oscillator_recovery_to_the_opposite_side():
    sell = evaluate_module("link_stochastic_failed_move", _stochastic())
    buy = evaluate_module(
        "link_stochastic_failed_move",
        _stochastic(
            side="BUY",
            link_stochastic_failure_direction="down",
            link_stochastic_zone="oversold",
        ),
    )
    crossed = evaluate_module(
        "link_stochastic_failed_move",
        _stochastic(link_stochastic_fast_crossed_slow=True),
    )

    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"
    assert sell["link_stochastic_assessment"] == "FAILED_UPWARD_RECOVERY"
    assert crossed["view"] == "WAIT"
    assert sell["execution_authority"] is False


def test_link_retracement_entry_requires_a_confirmed_trend_aligned_pullback():
    buy = evaluate_module("link_trend_retracement_entry", _retracement())
    sell = evaluate_module(
        "link_trend_retracement_entry",
        _retracement(side="SELL", link_major_trend_direction="SELL", link_retracement_fraction=0.618),
    )
    chasing = evaluate_module(
        "link_trend_retracement_entry",
        _retracement(link_retracement_chasing=True),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["link_retracement_level"] == "50_PERCENT"
    assert sell["link_retracement_level"] == "61_8_PERCENT"
    assert chasing["view"] == "WAIT"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "link_adx_regime_switch",
        "link_stochastic_failed_move",
        "link_trend_retracement_entry",
    ],
)
def test_link_extensions_fail_closed_without_observed_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
