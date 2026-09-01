import pytest

from aegis.research.watcher_algorithms import evaluate_module


def test_pole_spread_margin_uses_a_margin_inside_observed_extremes():
    result = evaluate_module(
        "pole_spread_margin",
        {
            "side": "BUY",
            "pole_spread_value": 1.02,
            "pole_spread_min": 1.0,
            "pole_spread_max": 1.1,
            "pole_spread_margin_fraction": 0.2,
            "pole_spread_stationarity": "validated stationary",
            "pole_spread_data_provenance": "observed_pair_spread_history",
        },
    )
    assert result["view"] == "BUY"
    assert result["pole_spread_lower_boundary"] == pytest.approx(1.02)
    assert result["pole_spread_margin_assessment"] == "LOWER_MARGIN_BUY"

    inside = evaluate_module(
        "pole_spread_margin",
        {
            "pole_spread_value": 1.06,
            "pole_spread_min": 1.0,
            "pole_spread_max": 1.1,
            "pole_spread_margin_fraction": 0.2,
            "pole_spread_stationarity": "validated stationary",
            "pole_spread_data_provenance": "observed_pair_spread_history",
        },
    )
    assert inside["view"] == "WAIT"


def test_pole_spread_margin_requires_stationarity_and_positive_range():
    result = evaluate_module(
        "pole_spread_margin",
        {
            "pole_spread_value": 1.02,
            "pole_spread_min": 1.0,
            "pole_spread_max": 1.1,
            "pole_spread_margin_fraction": 0.2,
            "pole_spread_stationarity": "not validated",
            "pole_spread_data_provenance": "observed_pair_spread_history",
        },
    )
    assert result["view"] == "WAIT"
    assert "stationarity" in " ".join(result["reasons"])


def test_pole_evolutionary_operation_waits_through_noise_and_flags_persistent_shift():
    result = evaluate_module(
        "pole_evolutionary_operation",
        {
            "pole_current_calibration_edge": 0.002,
            "pole_neighbor_calibration_edges": [0.0025, 0.003],
            "pole_observed_persistence_periods": 1,
            "pole_required_persistence_periods": 4,
            "pole_evolution_data_provenance": "observed_walk_forward_calibration_history",
        },
    )
    assert result["pole_evolution_action"] == "MONITOR_LOCAL_NOISE"

    persistent = evaluate_module(
        "pole_evolutionary_operation",
        {
            "pole_current_calibration_edge": 0.002,
            "pole_neighbor_calibration_edges": [0.0025, 0.003],
            "pole_observed_persistence_periods": 4,
            "pole_required_persistence_periods": 4,
            "pole_evolution_data_provenance": "observed_walk_forward_calibration_history",
        },
    )
    assert persistent["pole_evolution_action"] == "REVIEW_CALIBRATION_SHIFT"
    assert persistent["directional_claim"] is False


@pytest.mark.parametrize("algorithm_id", ["pole_spread_margin", "pole_evolutionary_operation"])
def test_pole_perspectives_are_research_only(algorithm_id):
    result = evaluate_module(algorithm_id, {})
    assert result["execution_authority"] is False
    assert result["research_only"] is True
    assert result["uses_future_data"] is False
