from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _law(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "grinold_information_coefficient": 0.05,
        "grinold_breadth_per_year": 400.0,
        "grinold_target_information_ratio": 0.8,
        "grinold_fundamental_law_provenance": "observed chronological forecast outcomes",
    }
    state.update(overrides)
    return state


def _alpha(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "grinold_residual_volatility": 0.02,
        "grinold_information_coefficient": 0.10,
        "grinold_standardized_score": 1.5,
        "grinold_alpha_data_provenance": "observed chronological forecast outcomes",
    }
    state.update(overrides)
    return state


def _turnover(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "grinold_marginal_value_added": 0.0012,
        "grinold_marginal_transaction_cost": 0.0008,
        "grinold_turnover_fraction": 0.10,
        "grinold_turnover_limit": 0.25,
        "grinold_turnover_data_provenance": "observed portfolio turnover and net outcomes",
    }
    state.update(overrides)
    return state


def test_grinold_fundamental_law_reports_skill_breadth_capacity():
    result = evaluate_module("grinold_fundamental_law", _law())
    assert result["view"] == "WAIT"
    assert result["grinold_predicted_information_ratio"] == pytest.approx(1.0)
    assert result["grinold_fundamental_law_action"] == "TARGET_WITHIN_SKILL_BREADTH_CAPACITY"

    insufficient = evaluate_module(
        "grinold_fundamental_law",
        _law(grinold_target_information_ratio=1.2),
    )
    assert insufficient["grinold_fundamental_law_action"] == "TARGET_EXCEEDS_SKILL_BREADTH_CAPACITY"


def test_grinold_alpha_scaling_uses_residual_volatility_ic_and_score():
    result = evaluate_module("grinold_alpha_scaling", _alpha())
    assert result["view"] == "BUY"
    assert result["grinold_expected_alpha"] == pytest.approx(0.003)

    opposed = evaluate_module(
        "grinold_alpha_scaling",
        _alpha(grinold_standardized_score=-1.5),
    )
    assert opposed["view"] == "SELL"
    assert opposed["candidate_alignment"] == "OPPOSES"


def test_grinold_turnover_rule_trades_only_when_marginal_value_clears_cost():
    trade = evaluate_module("grinold_turnover_frontier", _turnover())
    assert trade["view"] == "WAIT"
    assert trade["grinold_turnover_action"] == "MARGINAL_VALUE_CLEARS_COST"

    no_trade = evaluate_module(
        "grinold_turnover_frontier",
        _turnover(grinold_marginal_transaction_cost=0.0012),
    )
    assert no_trade["grinold_turnover_action"] == "MARGINAL_COST_EXCEEDS_VALUE"


def test_grinold_rules_require_observed_forecast_or_turnover_evidence():
    missing = evaluate_module(
        "grinold_alpha_scaling",
        _alpha(grinold_alpha_data_provenance="synthetic fixture"),
    )
    assert missing["view"] == "MISSING_DATA"

    invalid = evaluate_module(
        "grinold_fundamental_law",
        _law(grinold_breadth_per_year=0),
    )
    assert invalid["grinold_fundamental_law_action"] == "INVALID_FUNDAMENTAL_LAW_INPUT"
