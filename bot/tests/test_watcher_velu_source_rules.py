from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies"


def _filter(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_filter_current_price": 106.0,
        "velu_filter_reference_extreme": 100.0,
        "velu_filter_reference_type": "past_low",
        "velu_filter_threshold": 0.05,
        "velu_filter_position": "flat",
        "velu_filter_data_provenance": "observed timestamped daily closes",
    }
    state.update(overrides)
    return state


def test_alexander_filter_enters_long_after_the_observed_percentage_move_from_a_low():
    result = evaluate_module("velu_alexander_filter", _filter())

    assert result["source_books"] == [SOURCE]
    assert result["view"] == "BUY"
    assert result["velu_filter_action"] == "ENTER_LONG"
    assert result["velu_filter_move_fraction"] == pytest.approx(0.06)


def test_alexander_filter_reverses_long_to_short_after_a_move_down_from_a_high():
    result = evaluate_module(
        "velu_alexander_filter",
        _filter(
            side="SELL",
            velu_filter_current_price=104.0,
            velu_filter_reference_extreme=110.0,
            velu_filter_reference_type="subsequent_high",
            velu_filter_position="long",
        ),
    )

    assert result["view"] == "SELL"
    assert result["velu_filter_action"] == "REVERSE_TO_SHORT"


def test_alexander_filter_ignores_a_move_smaller_than_the_filter():
    result = evaluate_module(
        "velu_alexander_filter",
        _filter(velu_filter_current_price=104.0),
    )

    assert result["view"] == "WAIT"
    assert result["velu_filter_action"] == "FILTER_NOT_REACHED"


def _ma(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_ma_mode": "reversal",
        "velu_ma_upper_ratio": 1.01,
        "velu_ma_lower_ratio": 0.99,
        "velu_ma_data_provenance": "observed timestamped closes",
    }
    state.update(overrides)
    return state


def test_sma_rule_computes_the_running_average_and_maps_below_band_to_reversal_buy():
    result = evaluate_module(
        "velu_sma_rule",
        _ma(velu_sma_prices=[100.0, 100.0, 100.0, 98.0]),
    )

    assert result["view"] == "BUY"
    assert result["velu_sma_action"] == "REVERSAL_BUY"
    assert result["velu_sma_value"] == pytest.approx(99.5)
    assert result["velu_sma_ratio"] > 1.01


def test_sma_rule_can_run_in_momentum_mode_above_the_upper_band():
    result = evaluate_module(
        "velu_sma_rule",
        _ma(
            side="BUY",
            velu_ma_mode="momentum",
            velu_sma_prices=[100.0, 100.0, 100.0, 102.0],
        ),
    )

    assert result["view"] == "BUY"
    assert result["velu_sma_action"] == "MOMENTUM_BUY"


def _ewa(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_ewa_prices": [100.0, 100.0, 100.0, 97.0],
        "velu_ewa_lambda": 0.5,
        "velu_ma_mode": "reversal",
        "velu_ma_upper_ratio": 1.01,
        "velu_ma_lower_ratio": 0.99,
        "velu_ewa_data_provenance": "observed timestamped closes",
    }
    state.update(overrides)
    return state


def test_ewa_rule_uses_the_source_lambda_weighting_and_is_directional():
    result = evaluate_module("velu_ewa_rule", _ewa())

    assert result["view"] == "BUY"
    assert result["velu_ewa_action"] == "REVERSAL_BUY"
    assert result["velu_ewa_value"] > 98.0


def test_ewa_rule_rejects_an_invalid_smoothing_constant():
    result = evaluate_module("velu_ewa_rule", _ewa(velu_ewa_lambda=1.0))

    assert result["view"] == "WAIT"
    assert result["velu_ewa_action"] == "INVALID_EWA_INPUT"


def _bwma(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "velu_bwma_prices": [100.0] * 19 + [104.0],
        "velu_bwma_band_multiplier": 2.0,
        "velu_bwma_data_provenance": "observed timestamped closes",
    }
    state.update(overrides)
    return state


def test_bwma_rule_uses_weighted_average_and_two_sample_standard_deviation_bands():
    result = evaluate_module("velu_bwma_bollinger_rule", _bwma())

    assert result["view"] == "SELL"
    assert result["velu_bwma_action"] == "UPPER_BAND_SELL"
    assert result["velu_bwma_band_multiplier"] == pytest.approx(2.0)
    assert result["velu_bwma_value"] > 100.0


def test_bwma_rule_waits_inside_the_source_bands():
    result = evaluate_module(
        "velu_bwma_bollinger_rule",
        _bwma(velu_bwma_prices=[100.0] * 20),
    )

    assert result["view"] == "WAIT"
    assert result["velu_bwma_action"] == "INSIDE_BANDS"


def _oscillator(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_oscillator_previous_short": 99.0,
        "velu_oscillator_previous_long": 100.0,
        "velu_oscillator_current_short": 101.0,
        "velu_oscillator_current_long": 100.0,
        "velu_oscillator_data_provenance": "observed timestamped moving averages",
    }
    state.update(overrides)
    return state


def test_moving_average_oscillator_signals_an_upward_cross():
    result = evaluate_module("velu_moving_average_oscillator", _oscillator())

    assert result["view"] == "BUY"
    assert result["velu_oscillator_action"] == "UPWARD_CROSS"


def test_moving_average_oscillator_signals_a_downward_cross():
    result = evaluate_module(
        "velu_moving_average_oscillator",
        _oscillator(
            side="SELL",
            velu_oscillator_previous_short=101.0,
            velu_oscillator_current_short=99.0,
        ),
    )

    assert result["view"] == "SELL"
    assert result["velu_oscillator_action"] == "DOWNWARD_CROSS"


def test_velu_rsi_reversal_uses_the_source_seventy_thirty_levels():
    buy = evaluate_module(
        "velu_rsi_reversal",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "velu_rsi_value": 29.0,
            "velu_rsi_data_provenance": "observed timestamped RSI",
        },
    )
    sell = evaluate_module(
        "velu_rsi_reversal",
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "velu_rsi_value": 71.0,
            "velu_rsi_data_provenance": "observed timestamped RSI",
        },
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["velu_rsi_action"] == "OVERSOLD_BUY"
    assert sell["velu_rsi_action"] == "OVERBOUGHT_SELL"
    assert buy["velu_rsi_oversold"] == 30.0
    assert sell["velu_rsi_overbought"] == 70.0


def test_velu_rsi_reversal_waits_between_the_source_extremes():
    result = evaluate_module(
        "velu_rsi_reversal",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "velu_rsi_value": 50.0,
            "velu_rsi_data_provenance": "observed timestamped RSI",
        },
    )

    assert result["view"] == "WAIT"
    assert result["velu_rsi_action"] == "INSIDE_NEUTRAL_ZONE"


def _kernel(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "velu_kernel_prices": [100.0, 102.0, 101.0],
        "velu_kernel_bandwidth": 0.5,
        "velu_kernel_bandwidth_selection": "cross_validated",
        "velu_kernel_data_provenance": "observed timestamped closes",
    }
    state.update(overrides)
    return state


def test_kernel_pattern_rule_uses_causal_smoothed_slope_change_for_a_peak():
    result = evaluate_module("velu_kernel_pattern", _kernel())

    assert result["view"] == "SELL"
    assert result["velu_kernel_action"] == "CONFIRMED_SMOOTHED_PEAK"
    assert result["velu_kernel_extremum"] == "PEAK"
    assert result["uses_future_data"] is False


def test_kernel_pattern_rule_can_confirm_a_smoothed_trough():
    result = evaluate_module(
        "velu_kernel_pattern",
        _kernel(side="BUY", velu_kernel_prices=[100.0, 98.0, 99.0]),
    )

    assert result["view"] == "BUY"
    assert result["velu_kernel_action"] == "CONFIRMED_SMOOTHED_TROUGH"


@pytest.mark.parametrize(
    ("algorithm_id", "state_key"),
    [
        ("velu_alexander_filter", "velu_filter_data_provenance"),
        ("velu_sma_rule", "velu_ma_data_provenance"),
        ("velu_ewa_rule", "velu_ewa_data_provenance"),
        ("velu_bwma_bollinger_rule", "velu_bwma_data_provenance"),
        ("velu_moving_average_oscillator", "velu_oscillator_data_provenance"),
        ("velu_rsi_reversal", "velu_rsi_data_provenance"),
        ("velu_kernel_pattern", "velu_kernel_data_provenance"),
    ],
)
def test_velu_source_rules_reject_synthetic_provenance(algorithm_id, state_key):
    states = {
        "velu_alexander_filter": _filter(),
        "velu_sma_rule": _ma(velu_sma_prices=[100.0, 99.0]),
        "velu_ewa_rule": _ewa(),
        "velu_bwma_bollinger_rule": _bwma(),
        "velu_moving_average_oscillator": _oscillator(),
        "velu_rsi_reversal": {"side": "BUY", "velu_rsi_value": 25.0, "velu_rsi_data_provenance": "observed"},
        "velu_kernel_pattern": _kernel(),
    }
    states[algorithm_id][state_key] = "synthetic fixture"

    result = evaluate_module(algorithm_id, states[algorithm_id])

    assert result["view"] == "MISSING_DATA"
    assert state_key in result["missing_inputs"]
