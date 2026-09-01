from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Trading with Intermarket Analysis"


def _inverse(**overrides):
    state = {
        "symbol": "COMMODITIES",
        "side": "BUY",
        "murphy_lead_symbol": "USD_INDEX",
        "murphy_target_symbol": "COMMODITIES",
        "murphy_lead_direction": "DOWN",
        "murphy_target_direction": "UP",
        "murphy_expected_relationship": "inverse",
        "murphy_rolling_correlation": -0.8,
        "murphy_relationship_status": "validated_inverse_relationship",
        "murphy_observation_n": 200,
        "murphy_data_provenance": "observed synchronized cross asset charts",
    }
    state.update(overrides)
    return state


def _lead_lag(**overrides):
    state = {
        "symbol": "STOCKS",
        "side": "SELL",
        "murphy_lead_symbol": "BONDS",
        "murphy_target_symbol": "STOCKS",
        "murphy_lead_direction": "UP",
        "murphy_target_direction": "DOWN",
        "murphy_expected_relationship": "inverse",
        "murphy_lead_changed_first": True,
        "murphy_relationship_status": "validated_lead_lag_relationship",
        "murphy_observation_n": 120,
        "murphy_lead_lag_provenance": "observed timestamped cross asset turns",
    }
    state.update(overrides)
    return state


def _regime(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "murphy_current_correlation": -0.25,
        "murphy_baseline_correlation": -0.8,
        "murphy_relationship_state": "weakening",
        "murphy_relationship_observation_n": 300,
        "murphy_relationship_regime_provenance": "observed rolling cross asset correlation",
    }
    state.update(overrides)
    return state


def _sector(**overrides):
    state = {
        "symbol": "CONSUMER_DISCRETIONARY",
        "side": "BUY",
        "murphy_business_cycle_phase": "early_expansion",
        "murphy_leader_group": "consumer_discretionary",
        "murphy_candidate_group": "consumer_discretionary",
        "murphy_candidate_direction": "BUY",
        "murphy_relative_strength": 0.3,
        "murphy_sector_rotation_status": "validated_sector_rotation",
        "murphy_sector_observation_n": 80,
        "murphy_sector_data_provenance": "observed timestamped sector returns",
    }
    state.update(overrides)
    return state


def test_murphy_inverse_relationship_requires_observed_strength_and_confirms_target_side():
    result = evaluate_module("murphy_inverse_relationship", _inverse())
    assert result["view"] == "BUY"
    assert result["murphy_intermarket_assessment"] == "INVERSE_CONFIRMED"
    assert result["source_books"] == [SOURCE]

    weak = evaluate_module(
        "murphy_inverse_relationship",
        _inverse(murphy_rolling_correlation=-0.1),
    )
    assert weak["view"] == "WAIT"
    assert weak["murphy_intermarket_assessment"] == "RELATIONSHIP_WEAK"


def test_murphy_lead_lag_requires_lead_turn_before_target_confirmation():
    result = evaluate_module("murphy_lead_lag_confirmation", _lead_lag())
    assert result["view"] == "SELL"
    assert result["murphy_lead_lag_assessment"] == "LEAD_CONFIRMED"

    simultaneous = evaluate_module(
        "murphy_lead_lag_confirmation",
        _lead_lag(murphy_lead_changed_first=False),
    )
    assert simultaneous["view"] == "WAIT"
    assert simultaneous["murphy_lead_lag_assessment"] == "LEAD_NOT_PROVEN"


def test_murphy_relationship_regime_guard_surfaces_weakening_correlations():
    result = evaluate_module("murphy_relationship_regime", _regime())
    assert result["view"] == "WAIT"
    assert result["murphy_relationship_assessment"] == "WEAKENING"
    assert result["murphy_downweight_relationship"] is True

    stable = evaluate_module(
        "murphy_relationship_regime",
        _regime(
            murphy_current_correlation=-0.75,
            murphy_relationship_state="stable",
        ),
    )
    assert stable["murphy_relationship_assessment"] == "STABLE"
    assert stable["murphy_downweight_relationship"] is False


def test_murphy_sector_rotation_requires_validated_phase_and_leadership():
    result = evaluate_module("murphy_sector_rotation", _sector())
    assert result["view"] == "BUY"
    assert result["murphy_sector_assessment"] == "LEADING_SECTOR"

    mismatch = evaluate_module(
        "murphy_sector_rotation",
        _sector(murphy_candidate_group="utilities"),
    )
    assert mismatch["view"] == "WAIT"
    assert mismatch["murphy_sector_assessment"] == "PHASE_MISMATCH"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "murphy_inverse_relationship",
        "murphy_lead_lag_confirmation",
        "murphy_relationship_regime",
        "murphy_sector_rotation",
    ],
)
def test_murphy_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
