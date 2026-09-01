from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _pole(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "pole_spread_zscore": -2.4,
        "pole_entry_zscore_threshold": 2.0,
        "pole_exit_zscore_target": 0.0,
        "pole_stationarity": "validated",
        "pole_pair_correlation": 0.92,
        "pole_min_pair_correlation": 0.80,
        "pole_calibration_window": 60,
        "pole_pair_id": "EURUSD-GBPUSD",
        "pole_data_provenance": "historical_quote_pairs",
    }
    state.update(overrides)
    return state


def _gray(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_formation_return": 0.42,
        "gray_momentum_decile": 10,
        "gray_positive_return_fraction": 0.68,
        "gray_negative_return_fraction": 0.32,
        "gray_formation_lookback_months": 12,
        "gray_skip_recent_period": True,
        "gray_universe_count": 100,
        "gray_data_provenance": "historical_adjusted_returns",
    }
    state.update(overrides)
    return state


def test_pole_calibrated_spread_reversion_maps_extremes_to_the_correct_side():
    buy = evaluate_module("pole_spread_reversion", _pole())
    sell = evaluate_module(
        "pole_spread_reversion",
        _pole(side="SELL", pole_spread_zscore=2.4),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["pole_reversion_target_zscore"] == 0.0
    assert buy["source_books"] == ["Andrew Pole — Statistical Arbitrage"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"pole_spread_zscore": 1.5},
        {"pole_stationarity": "not_validated"},
        {"pole_pair_correlation": 0.4},
        {"pole_exit_zscore_target": 2.5},
        {"pole_calibration_window": 0},
    ],
)
def test_pole_waits_for_a_calibrated_stationary_spread_edge(overrides):
    result = evaluate_module("pole_spread_reversion", _pole(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_gray_vogel_requires_skip_recent_period_and_continuous_path():
    buy = evaluate_module("gray_vogel_path_momentum", _gray())
    sell = evaluate_module(
        "gray_vogel_path_momentum",
        _gray(
            side="SELL",
            gray_formation_return=-0.32,
            gray_momentum_decile=1,
            gray_positive_return_fraction=0.31,
            gray_negative_return_fraction=0.69,
        ),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["gray_information_discreteness"] < 0
    assert buy["source_books"] == ["Wesley R. Gray and Jack R. Vogel — Quantitative Momentum"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"gray_momentum_decile": 5},
        {"gray_skip_recent_period": False},
        {"gray_formation_lookback_months": 6},
        {"gray_positive_return_fraction": 0.6, "gray_negative_return_fraction": 0.6},
        {"gray_formation_return": 0.0},
    ],
)
def test_gray_vogel_waits_when_rank_or_path_quality_is_not_observed(overrides):
    result = evaluate_module("gray_vogel_path_momentum", _gray(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize("algorithm_id", ["pole_spread_reversion", "gray_vogel_path_momentum"])
def test_pole_and_gray_fail_closed_without_real_historical_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
