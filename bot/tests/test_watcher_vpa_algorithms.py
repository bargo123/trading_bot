from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


VPA_SOURCE = "Anna Coulling — A Complete Guide To Volume Price Analysis"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "vpa_volume_provenance": "real_traded_volume",
        "vpa_data_provenance": "causal_completed_bar",
        "feature_provenance": {"vpa": "causal_completed_bar"},
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("algorithm_id", "specific", "expected_view"),
    [
        (
            "vpa_long_legged_doji",
            {
                "vpa_setup": "long_legged_doji",
                "vpa_candle_range_pips": 18.0,
                "vpa_candle_body_fraction": 0.08,
                "vpa_volume_ratio": 0.45,
            },
            "WAIT",
        ),
        (
            "vpa_narrow_spread_high_volume",
            {
                "vpa_setup": "narrow_spread_high_volume",
                "vpa_price_direction": "up",
                "vpa_spread_pips": 2.0,
                "vpa_average_spread_pips": 6.0,
                "vpa_volume_ratio": 1.8,
                "vpa_confirmation": "confirmed",
            },
            "SELL",
        ),
        (
            "vpa_stopping_volume",
            {
                "vpa_setup": "stopping_volume",
                "vpa_trend": "down",
                "vpa_lower_wick_ratio": 2.5,
                "vpa_close_location": "upper_half",
                "vpa_volume_ratio": 1.7,
                "vpa_sequence_bars": 3,
                "vpa_confirmation": "confirmed",
            },
            "BUY",
        ),
        (
            "vpa_topping_out_volume",
            {
                "vpa_setup": "topping_out_volume",
                "vpa_trend": "up",
                "vpa_upper_wick_ratio": 2.5,
                "vpa_spread_contraction": True,
                "vpa_volume_ratio": 1.8,
                "vpa_sequence_bars": 3,
                "vpa_confirmation": "confirmed",
            },
            "SELL",
        ),
        (
            "vpa_breakout_volume_validation",
            {
                "vpa_setup": "breakout_volume_validation",
                "vpa_breakout_direction": "up",
                "vpa_breakout_confirmation": "confirmed",
                "vpa_clear_water": True,
                "vpa_breakout_volume_ratio": 1.8,
                "vpa_retest_volume_ratio": 0.6,
            },
            "BUY",
        ),
    ],
)
def test_vpa_modules_use_named_setup_and_volume_confirmation(algorithm_id, specific, expected_view):
    result = evaluate_module(algorithm_id, _state(side=expected_view, **specific))

    assert result["view"] == expected_view
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [VPA_SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "vpa_long_legged_doji",
        "vpa_narrow_spread_high_volume",
        "vpa_stopping_volume",
        "vpa_topping_out_volume",
        "vpa_breakout_volume_validation",
    ],
)
def test_vpa_modules_fail_closed_without_named_setup(algorithm_id):
    result = evaluate_module(algorithm_id, _state())

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def test_tick_activity_proxy_never_masquerades_as_traded_volume_confirmation():
    result = evaluate_module(
        "vpa_stopping_volume",
        _state(
            vpa_volume_provenance="tick_activity_proxy",
            vpa_setup="stopping_volume",
            vpa_trend="down",
            vpa_lower_wick_ratio=2.5,
            vpa_close_location="upper_half",
            vpa_volume_ratio=1.7,
            vpa_sequence_bars=3,
            vpa_confirmation="confirmed",
        ),
    )

    assert result["view"] == "WAIT"
    assert result["applicability"] == "APPLICABLE"
    assert any("proxy" in warning for warning in result["warnings"])


def test_low_volume_breakout_is_wait_not_a_validated_breakout():
    result = evaluate_module(
        "vpa_breakout_volume_validation",
        _state(
            vpa_setup="breakout_volume_validation",
            vpa_breakout_direction="down",
            vpa_breakout_confirmation="confirmed",
            vpa_clear_water=True,
            vpa_breakout_volume_ratio=0.7,
            vpa_retest_volume_ratio=0.5,
        ),
    )

    assert result["view"] == "WAIT"
    assert "volume" in " ".join(result["reasons"]).lower()
