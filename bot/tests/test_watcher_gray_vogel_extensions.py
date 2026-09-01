from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _lookback(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_lookback_regime": "intermediate",
        "gray_short_term_return": 0.02,
        "gray_intermediate_return": 0.24,
        "gray_long_term_return": 0.18,
        "gray_intermediate_skip_recent": True,
        "gray_data_provenance": "observed historical cross-sectional returns",
    }
    state.update(overrides)
    return state


def _lottery(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_lottery_max_return": 0.03,
        "gray_lottery_beta": 0.85,
        "gray_lottery_max_return_limit": 0.10,
        "gray_lottery_beta_limit": 1.50,
        "gray_lottery_lookback": "prior_month",
        "gray_lottery_data_provenance": "observed historical daily returns",
    }
    state.update(overrides)
    return state


def _seasonality(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_seasonal_month": 2,
        "gray_seasonal_sample_n": 240,
        "gray_seasonal_expectancy": 0.012,
        "gray_seasonal_validation": "validated chronological out-of-sample",
        "gray_seasonal_data_provenance": "observed historical monthly returns",
    }
    state.update(overrides)
    return state


def test_gray_vogel_lookback_regime_separates_reversal_from_continuation():
    intermediate = evaluate_module("gray_vogel_lookback_regime", _lookback())
    short_reversal = evaluate_module(
        "gray_vogel_lookback_regime",
        _lookback(gray_lookback_regime="short_term", side="SELL"),
    )
    long_reversal = evaluate_module(
        "gray_vogel_lookback_regime",
        _lookback(gray_lookback_regime="long_term", side="BUY", gray_long_term_return=-0.22),
    )

    assert intermediate["view"] == "BUY"
    assert intermediate["gray_return_effect"] == "continuation"
    assert short_reversal["view"] == "SELL"
    assert short_reversal["gray_return_effect"] == "reversal"
    assert long_reversal["view"] == "BUY"
    assert long_reversal["gray_return_effect"] == "reversal"
    assert intermediate["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"gray_intermediate_skip_recent": False},
        {"gray_lookback_regime": "unrecognized"},
        {"gray_intermediate_return": "not-a-return"},
    ],
)
def test_gray_vogel_lookback_regime_fails_closed_without_the_required_historical_definition(overrides):
    result = evaluate_module("gray_vogel_lookback_regime", _lookback(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_gray_vogel_lottery_filter_passes_smooth_paths_but_flags_extreme_max_or_beta():
    clean = evaluate_module("gray_vogel_lottery_avoidance", _lottery())
    extreme_max = evaluate_module(
        "gray_vogel_lottery_avoidance",
        _lottery(gray_lottery_max_return=0.12),
    )
    extreme_beta = evaluate_module(
        "gray_vogel_lottery_avoidance",
        _lottery(gray_lottery_beta=1.60),
    )

    assert clean["view"] == "WAIT"
    assert clean["gray_lottery_assessment"] == "LOTTERY_EXPOSURE_NOT_ELEVATED"
    assert clean["directional_claim"] is False
    assert extreme_max["gray_lottery_assessment"] == "AVOID_LOTTERY_EXPOSURE"
    assert extreme_beta["gray_lottery_assessment"] == "AVOID_LOTTERY_EXPOSURE"
    assert extreme_max["warnings"]


def test_gray_vogel_seasonality_identifies_pre_quarter_end_timing_without_making_a_directional_claim():
    favorable = evaluate_module("gray_vogel_seasonality_timing", _seasonality())
    neutral = evaluate_module(
        "gray_vogel_seasonality_timing",
        _seasonality(gray_seasonal_month=7),
    )
    weak = evaluate_module(
        "gray_vogel_seasonality_timing",
        _seasonality(gray_seasonal_expectancy=-0.001),
    )

    assert favorable["view"] == "WAIT"
    assert favorable["gray_seasonal_assessment"] == "PRE_QUARTER_END_MOMENTUM_WINDOW"
    assert favorable["directional_claim"] is False
    assert neutral["gray_seasonal_assessment"] == "SEASONAL_EDGE_NOT_IDENTIFIED"
    assert weak["gray_seasonal_assessment"] == "SEASONAL_EDGE_NOT_IDENTIFIED"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "gray_vogel_lookback_regime",
        "gray_vogel_lottery_avoidance",
        "gray_vogel_seasonality_timing",
    ],
)
def test_gray_vogel_extensions_fail_closed_without_observed_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
