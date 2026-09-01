from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


SOURCE_PROVENANCE = "observed chronological price series"


def test_chan_adf_requires_negative_statistic_beyond_critical_value():
    result = evaluate_module(
        "chan_adf_mean_reversion",
        {
            "chan_adf_t_statistic": -3.5,
            "chan_adf_critical_value": -2.9,
            "chan_adf_coefficient": -0.04,
            "chan_adf_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert result["view"] == "WAIT"
    assert result["chan_adf_assessment"] == "MEAN_REVERSION_SUPPORTED"
    assert result["directional_claim"] is False


def test_chan_adf_does_not_promote_a_non_rejected_or_positive_coefficient():
    not_rejected = evaluate_module(
        "chan_adf_mean_reversion",
        {
            "chan_adf_t_statistic": -2.0,
            "chan_adf_critical_value": -2.9,
            "chan_adf_coefficient": -0.04,
            "chan_adf_data_provenance": SOURCE_PROVENANCE,
        },
    )
    positive = evaluate_module(
        "chan_adf_mean_reversion",
        {
            "chan_adf_t_statistic": -3.5,
            "chan_adf_critical_value": -2.9,
            "chan_adf_coefficient": 0.04,
            "chan_adf_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert not_rejected["chan_adf_assessment"] == "NEGATIVE_BUT_NOT_REJECTED"
    assert positive["chan_adf_assessment"] == "NON_MEAN_REVERTING"


def test_chan_hurst_and_variance_ratio_keep_random_walks_separate_from_supported_states():
    hurst = evaluate_module(
        "chan_hurst_stationarity",
        {
            "chan_hurst_exponent": 0.35,
            "chan_hurst_null_rejected": True,
            "chan_hurst_data_provenance": SOURCE_PROVENANCE,
        },
    )
    variance_ratio = evaluate_module(
        "chan_variance_ratio_stationarity",
        {
            "chan_variance_ratio": 0.72,
            "chan_variance_ratio_null_rejected": True,
            "chan_variance_ratio_data_provenance": SOURCE_PROVENANCE,
        },
    )
    random_walk = evaluate_module(
        "chan_hurst_stationarity",
        {
            "chan_hurst_exponent": 0.5,
            "chan_hurst_null_rejected": False,
            "chan_hurst_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert hurst["chan_hurst_assessment"] == "MEAN_REVERSION_SUPPORTED"
    assert variance_ratio["chan_variance_ratio_assessment"] == "MEAN_REVERSION_SUPPORTED"
    assert random_walk["chan_hurst_assessment"] == "RANDOM_WALK_NOT_REJECTED"


def test_chan_hurst_and_variance_ratio_fail_closed_without_significance_or_valid_range():
    untested = evaluate_module(
        "chan_hurst_stationarity",
        {
            "chan_hurst_exponent": 0.35,
            "chan_hurst_null_rejected": False,
            "chan_hurst_data_provenance": SOURCE_PROVENANCE,
        },
    )
    invalid = evaluate_module(
        "chan_variance_ratio_stationarity",
        {
            "chan_variance_ratio": -1.0,
            "chan_variance_ratio_null_rejected": True,
            "chan_variance_ratio_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert untested["chan_hurst_assessment"] == "RANDOM_WALK_NOT_REJECTED"
    assert invalid["view"] == "MISSING_DATA"


def test_chan_half_life_requires_a_negative_reversion_coefficient_and_fits_declared_horizon():
    compatible = evaluate_module(
        "chan_mean_reversion_half_life",
        {
            "chan_mean_reversion_coefficient": -0.2,
            "chan_mean_reversion_half_life": 3.0,
            "chan_mean_reversion_horizon": 5.0,
            "chan_half_life_data_provenance": SOURCE_PROVENANCE,
        },
    )
    too_slow = evaluate_module(
        "chan_mean_reversion_half_life",
        {
            "chan_mean_reversion_coefficient": -0.02,
            "chan_mean_reversion_half_life": 20.0,
            "chan_mean_reversion_horizon": 5.0,
            "chan_half_life_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert compatible["chan_half_life_assessment"] == "PRACTICAL_FOR_HORIZON"
    assert too_slow["chan_half_life_assessment"] == "TOO_SLOW_FOR_HORIZON"


def test_chan_half_life_can_report_a_measured_value_without_inventing_a_horizon():
    result = evaluate_module(
        "chan_mean_reversion_half_life",
        {
            "chan_mean_reversion_coefficient": -0.2,
            "chan_mean_reversion_half_life": 3.0,
            "chan_half_life_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert result["chan_half_life_assessment"] == "HORIZON_NOT_DECLARED"


def test_chan_cadf_and_johansen_require_validated_cointegration_geometry():
    cadf = evaluate_module(
        "chan_cadf_cointegration",
        {
            "chan_cadf_t_statistic": -3.7,
            "chan_cadf_critical_value": -3.3,
            "chan_cadf_hedge_ratio": 0.82,
            "chan_cadf_independent_order": "EURUSD -> GBPUSD",
            "chan_cadf_data_provenance": SOURCE_PROVENANCE,
        },
    )
    johansen = evaluate_module(
        "chan_johansen_cointegration",
        {
            "chan_johansen_statistic": 19.0,
            "chan_johansen_critical_value": 15.5,
            "chan_johansen_rank": 1,
            "chan_johansen_series_n": 2,
            "chan_johansen_best_eigenvalue": 0.12,
            "chan_johansen_eigenvector": [-1.0, 0.82],
            "chan_johansen_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert cadf["chan_cadf_assessment"] == "COINTEGRATION_SUPPORTED"
    assert johansen["chan_johansen_assessment"] == "COINTEGRATION_SUPPORTED"
    assert cadf["directional_claim"] is False
    assert johansen["directional_claim"] is False


def test_chan_cadf_and_johansen_reject_weak_or_malformed_relationships():
    cadf = evaluate_module(
        "chan_cadf_cointegration",
        {
            "chan_cadf_t_statistic": -2.0,
            "chan_cadf_critical_value": -3.3,
            "chan_cadf_hedge_ratio": 0.82,
            "chan_cadf_independent_order": "EURUSD -> GBPUSD",
            "chan_cadf_data_provenance": SOURCE_PROVENANCE,
        },
    )
    johansen = evaluate_module(
        "chan_johansen_cointegration",
        {
            "chan_johansen_statistic": 19.0,
            "chan_johansen_critical_value": 15.5,
            "chan_johansen_rank": 0,
            "chan_johansen_series_n": 2,
            "chan_johansen_best_eigenvalue": 0.12,
            "chan_johansen_eigenvector": [-1.0],
            "chan_johansen_data_provenance": SOURCE_PROVENANCE,
        },
    )
    assert cadf["chan_cadf_assessment"] == "COINTEGRATION_NOT_REJECTED"
    assert johansen["view"] == "MISSING_DATA"
