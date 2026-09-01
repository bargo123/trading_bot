from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Rishi K. Narang — Inside the Black Box"


def _buckets(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_forecast_bucket_returns": [-0.04, -0.01, 0.01, 0.03, 0.05],
        "narang_forecast_bucket_data_provenance": "observed chronological forecast buckets",
    }
    state.update(overrides)
    return state


def _decay(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_delay_grid_s": [0, 1, 2, 3],
        "narang_delayed_entry_returns": [0.10, 0.07, 0.03, -0.01],
        "narang_time_decay_data_provenance": "observed timestamped delayed-entry replay",
    }
    state.update(overrides)
    return state


def _parameters(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_parameter_grid": [0.8, 0.9, 1.0, 1.1, 1.2],
        "narang_parameter_expectancies": [0.06, 0.08, 0.081, 0.079, 0.06],
        "narang_parameter_neighbor_tolerance": 0.25,
        "narang_parameter_data_provenance": "observed chronological parameter sweep",
    }
    state.update(overrides)
    return state


def _value_add(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_baseline_expectancy": 0.020,
        "narang_with_strategy_expectancy": 0.040,
        "narang_baseline_max_drawdown": -0.10,
        "narang_with_strategy_max_drawdown": -0.09,
        "narang_min_value_add": 0.005,
        "narang_value_add_data_provenance": "observed chronological portfolio replay",
    }
    state.update(overrides)
    return state


def _risk(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_exposure_observed": 0.40,
        "narang_exposure_limit": 1.00,
        "narang_pnl_observed": 0.02,
        "narang_pnl_expected": 0.01,
        "narang_pnl_deviation_limit": 0.05,
        "narang_execution_latency_ms": 40.0,
        "narang_execution_latency_limit_ms": 100.0,
        "narang_system_health": "healthy",
        "narang_risk_monitor_data_provenance": "observed timestamped runtime monitor",
    }
    state.update(overrides)
    return state


def test_narang_forecast_buckets_require_monotonic_outcomes_for_predictive_ordering():
    result = evaluate_module("narang_forecast_bucket_monotonicity", _buckets())
    assert result["view"] == "WAIT"
    assert result["narang_bucket_assessment"] == "MONOTONIC_FORECAST_ORDER"
    assert result["narang_bucket_monotonicity_fraction"] == pytest.approx(1.0)
    assert result["directional_claim"] is False
    assert result["source_books"] == [SOURCE]

    broken = evaluate_module(
        "narang_forecast_bucket_monotonicity",
        _buckets(narang_forecast_bucket_returns=[-0.04, 0.02, -0.01, 0.03, 0.05]),
    )
    assert broken["narang_bucket_assessment"] == "NON_MONOTONIC_FORECAST_ORDER"
    assert broken["view"] == "WAIT"


def test_narang_time_decay_exposes_delayed_entry_degradation():
    result = evaluate_module("narang_time_decay", _decay())
    assert result["narang_time_decay_assessment"] == "DECAY_WITH_DELAY"
    assert result["narang_time_decay_slope"] == pytest.approx(-0.0366666667)
    assert result["directional_claim"] is False

    persistent = evaluate_module(
        "narang_time_decay",
        _decay(narang_delayed_entry_returns=[0.01, 0.02, 0.02, 0.03]),
    )
    assert persistent["narang_time_decay_assessment"] == "NO_DECAY_OBSERVED"


def test_narang_parameter_plateau_is_preferred_over_a_lonely_peak():
    result = evaluate_module("narang_parameter_robustness", _parameters())
    assert result["narang_parameter_assessment"] == "ROBUST_PLATEAU"
    assert result["narang_robust_parameter"] == pytest.approx(1.0)

    lonely = evaluate_module(
        "narang_parameter_robustness",
        _parameters(
            narang_parameter_grid=[0.9, 1.0, 1.1],
            narang_parameter_expectancies=[0.01, 0.12, 0.00],
        ),
    )
    assert lonely["narang_parameter_assessment"] == "SINGLE_PEAK_WARNING"


def test_narang_portfolio_value_add_compares_with_and_without_the_strategy():
    result = evaluate_module("narang_portfolio_value_add", _value_add())
    assert result["narang_portfolio_assessment"] == "VALUE_ADDED"
    assert result["narang_expectancy_delta"] == pytest.approx(0.02)

    harmful = evaluate_module(
        "narang_portfolio_value_add",
        _value_add(narang_with_strategy_max_drawdown=-0.30),
    )
    assert harmful["narang_portfolio_assessment"] == "DRAWDOWN_DETERIORATION"


def test_narang_risk_monitoring_covers_exposure_pnl_execution_and_system_health():
    result = evaluate_module("narang_risk_monitoring", _risk())
    assert result["narang_risk_monitor_assessment"] == "MONITOR_CLEAR"
    assert result["narang_monitor_checks"] == {
        "exposure": "CLEAR",
        "pnl": "CLEAR",
        "execution": "CLEAR",
        "system": "CLEAR",
    }

    alert = evaluate_module(
        "narang_risk_monitoring",
        _risk(narang_execution_latency_ms=150.0, narang_system_health="degraded"),
    )
    assert alert["narang_risk_monitor_assessment"] == "MONITOR_ALERT"
    assert alert["narang_monitor_checks"]["execution"] == "ALERT"
    assert alert["narang_monitor_checks"]["system"] == "ALERT"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "narang_forecast_bucket_monotonicity",
        "narang_time_decay",
        "narang_parameter_robustness",
        "narang_portfolio_value_add",
        "narang_risk_monitoring",
    ],
)
def test_narang_research_rules_fail_closed_without_observed_inputs(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
