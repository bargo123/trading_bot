from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _characteristic_time(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "horizon_s": 5.0,
        "velu_characteristic_time_s": 10.0,
        "velu_quote_event_count": 4,
        "velu_characteristic_time_provenance": "observed timestamped quote changes",
    }
    state.update(overrides)
    return state


def _profile(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_profile_current_volume": 100.0,
        "velu_profile_expected_volume": 100.0,
        "velu_profile_current_volatility": 0.001,
        "velu_profile_expected_volatility": 0.001,
        "velu_profile_current_spread": 0.0002,
        "velu_profile_expected_spread": 0.0002,
        "velu_profile_spread_limit_multiplier": 1.5,
        "velu_profile_activity_spike_multiplier": 2.0,
        "velu_profile_data_provenance": "observed timestamped intraday profile",
    }
    state.update(overrides)
    return state


def _volume_return(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_lagged_return": 0.001,
        "velu_volume_turnover_change": 0.80,
        "velu_return_volume_regime": "speculative",
        "velu_return_volume_data_provenance": "observed timestamped return and real volume",
    }
    state.update(overrides)
    return state


def _cost(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_order_size": 100.0,
        "velu_average_daily_volume": 10000.0,
        "velu_volatility": 0.02,
        "velu_spread": 0.001,
        "velu_impact_alpha": 0.5,
        "velu_spread_beta": 0.5,
        "velu_expected_gross_return": 0.003,
        "velu_tcost_model_status": "validated",
        "velu_tcost_data_provenance": "observed timestamped execution outcomes",
    }
    state.update(overrides)
    return state


def test_velu_characteristic_time_requires_a_natural_event_time_scale():
    short = evaluate_module("velu_characteristic_time", _characteristic_time())
    assert short["view"] == "WAIT"
    assert short["velu_characteristic_time_action"] == "UNDER_SAMPLED_CHARACTERISTIC_TIME"
    assert short["velu_normalized_time"] == pytest.approx(0.5)

    aligned = evaluate_module(
        "velu_characteristic_time",
        _characteristic_time(horizon_s=20.0),
    )
    assert aligned["view"] == "WAIT"
    assert aligned["velu_characteristic_time_action"] == "TIME_SCALE_ALIGNED"
    assert aligned["velu_normalized_time"] == pytest.approx(2.0)


def test_velu_intraday_profile_uses_measured_profile_multipliers():
    normal = evaluate_module("velu_intraday_profile", _profile())
    assert normal["velu_profile_action"] == "PROFILE_ALIGNED"
    assert normal["velu_spread_multiplier"] == pytest.approx(1.0)

    wide = evaluate_module(
        "velu_intraday_profile",
        _profile(velu_profile_current_spread=0.0004),
    )
    assert wide["view"] == "WAIT"
    assert wide["velu_profile_action"] == "SPREAD_ABOVE_PROFILE"

    spike = evaluate_module(
        "velu_intraday_profile",
        _profile(velu_profile_current_volume=250.0),
    )
    assert spike["view"] == "WAIT"
    assert spike["velu_profile_action"] == "ACTIVITY_PROFILE_SHOCK"


def test_velu_volume_return_regime_changes_continuation_vs_reversal_direction():
    continuation = evaluate_module("velu_volume_return_filter", _volume_return())
    assert continuation["view"] == "BUY"
    assert continuation["velu_return_volume_action"] == "HIGH_ACTIVITY_CONTINUATION"

    reversal = evaluate_module(
        "velu_volume_return_filter",
        _volume_return(velu_return_volume_regime="liquidity"),
    )
    assert reversal["view"] == "SELL"
    assert reversal["velu_return_volume_action"] == "HIGH_ACTIVITY_REVERSAL"

    unknown = evaluate_module(
        "velu_volume_return_filter",
        _volume_return(velu_return_volume_regime="unknown"),
    )
    assert unknown["view"] == "MISSING_DATA"


def test_velu_square_root_cost_hurdle_is_net_of_spread_once():
    result = evaluate_module("velu_square_root_cost_hurdle", _cost())
    assert result["view"] == "BUY"
    assert result["velu_tcost_action"] == "NET_EDGE_AFTER_SQRT_IMPACT"
    assert result["velu_estimated_total_cost"] == pytest.approx(0.0015)
    assert result["velu_expected_net_return"] == pytest.approx(0.0015)

    rejected = evaluate_module(
        "velu_square_root_cost_hurdle",
        _cost(velu_expected_gross_return=0.001),
    )
    assert rejected["view"] == "WAIT"
    assert rejected["velu_tcost_action"] == "COST_HURDLE_FAIL"


def test_velu_rules_fail_closed_without_real_source_data():
    missing = evaluate_module(
        "velu_intraday_profile",
        _profile(velu_profile_data_provenance="tick_activity_proxy"),
    )
    assert missing["view"] == "MISSING_DATA"

    missing_cost_model = evaluate_module(
        "velu_square_root_cost_hurdle",
        _cost(velu_tcost_model_status="unvalidated"),
    )
    assert missing_cost_model["view"] == "MISSING_DATA"


def _distance_pair(**overrides):
    state = {
        "symbol": "LEG_A",
        "side": "BUY",
        "velu_pair_leg_a_symbol": "LEG_A",
        "velu_pair_leg_b_symbol": "LEG_B",
        "velu_pair_formation_a_prices": [100.0, 101.0, 99.0, 100.0],
        "velu_pair_formation_b_prices": [100.0, 100.0, 100.0, 100.0],
        "velu_pair_current_a_price": 97.0,
        "velu_pair_current_b_price": 100.0,
        "velu_pair_round_trip_cost": 0.001,
        "velu_pair_data_provenance": "observed historical pair prices",
    }
    state.update(overrides)
    return state


def test_velu_distance_pair_normalizes_paths_and_requires_cost_covered_divergence():
    result = evaluate_module("velu_distance_pairs", _distance_pair())

    assert result["view"] == "BUY"
    assert result["applicability"] == "APPLICABLE"
    assert result["candidate_alignment"] == "SUPPORTS"
    assert result["velu_pair_signal"] == "BUY_A_SELL_B"
    assert result["velu_pair_current_deviation"] < 0
    assert result["velu_pair_entry_threshold"] > 0
    assert result["velu_pair_cost_hurdle_passed"] is True
    assert result["velu_pair_rms_distance"] >= 0
    assert result["execution_authority"] is False


def test_velu_distance_pair_maps_the_other_leg_to_the_opposite_side():
    result = evaluate_module(
        "velu_distance_pairs",
        _distance_pair(
            symbol="LEG_B",
            side="BUY",
            velu_pair_current_a_price=103.0,
        ),
    )

    assert result["view"] == "BUY"
    assert result["velu_pair_signal"] == "SELL_A_BUY_B"
    assert result["candidate_alignment"] == "SUPPORTS"


def test_velu_distance_pair_rejects_divergence_that_does_not_cover_cost():
    result = evaluate_module(
        "velu_distance_pairs",
        _distance_pair(
            velu_pair_current_a_price=98.0,
            velu_pair_round_trip_cost=0.05,
        ),
    )

    assert result["view"] == "WAIT"
    assert result["velu_pair_signal"] == "NONE"
    assert result["velu_pair_action"] == "COST_HURDLE_FAIL"


def test_velu_distance_pair_rejects_synthetic_prices():
    result = evaluate_module(
        "velu_distance_pairs",
        _distance_pair(velu_pair_data_provenance="synthetic_fixture"),
    )

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"


def _sampling(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "velu_sampling_fast_returns": [1.0, -1.0, 1.0, -1.0],
        "velu_sampling_slow_returns": [0.5, 0.2, -0.1, 0.4],
        "velu_sampling_fast_interval_s": 1.0,
        "velu_sampling_slow_interval_s": 5.0,
        "velu_sampling_data_provenance": "observed timestamped quote returns",
    }
    state.update(overrides)
    return state


def test_velu_sampling_diagnostic_flags_negative_fine_interval_dependence():
    result = evaluate_module("velu_microstructure_noise_sampling", _sampling())

    assert result["view"] == "WAIT"
    assert result["velu_sampling_action"] == "MICROSTRUCTURE_NOISE_REVIEW"
    assert result["velu_sampling_fast_lag1_autocorrelation"] < 0
    assert result["velu_sampling_variance_gap"] > 0
    assert result["directional_claim"] is False


def test_velu_sampling_diagnostic_does_not_create_a_warning_without_negative_lag_one():
    result = evaluate_module(
        "velu_microstructure_noise_sampling",
        _sampling(velu_sampling_fast_returns=[0.1, 0.2, 0.3, 0.4]),
    )

    assert result["velu_sampling_action"] == "NO_NEGATIVE_LAG1_WARNING"
    assert result["warnings"] == []


def test_velu_sampling_diagnostic_rejects_proxy_data_and_invalid_intervals():
    proxy = evaluate_module(
        "velu_microstructure_noise_sampling",
        _sampling(velu_sampling_data_provenance="tick_activity_proxy"),
    )
    invalid = evaluate_module(
        "velu_microstructure_noise_sampling",
        _sampling(velu_sampling_fast_interval_s=5.0),
    )

    assert proxy["applicability"] == "MISSING_DATA"
    assert invalid["velu_sampling_action"] == "INVALID_SAMPLING_INPUTS"
