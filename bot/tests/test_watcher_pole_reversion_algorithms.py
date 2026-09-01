import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _reversion_state(**overrides):
    state = {
        "side": "BUY",
        "pole_current_value": 98.0,
        "pole_local_median": 100.0,
        "pole_reversion_rate": 0.78,
        "pole_min_reversion_rate": 0.75,
        "pole_reversion_observation_n": 240,
        "pole_reversion_assumptions": "validated theorem assumptions",
        "pole_reversion_data_provenance": "observed sequential values",
    }
    state.update(overrides)
    return state


def _multi_step_state(**overrides):
    state = {
        "side": "SELL",
        "pole_current_value": 102.0,
        "pole_local_median": 100.0,
        "pole_one_step_reversion_probability": 0.75,
        "pole_reversion_steps": 3,
        "pole_independence_assumption": "validated for this sample",
        "pole_multistep_data_provenance": "observed sequential values",
    }
    state.update(overrides)
    return state


def test_pole_75_percent_reversion_is_conditional_and_directional():
    buy = evaluate_module("pole_75_percent_reversion", _reversion_state())
    sell = evaluate_module(
        "pole_75_percent_reversion",
        _reversion_state(side="SELL", pole_current_value=102.0),
    )
    below_rule = evaluate_module(
        "pole_75_percent_reversion",
        _reversion_state(pole_reversion_rate=0.74),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["pole_reversion_rule"] == "75_PERCENT_CONDITIONAL"
    assert buy["pole_reversion_probability"] == pytest.approx(0.78)
    assert below_rule["view"] == "WAIT"
    assert below_rule["pole_reversion_action"] == "RATE_BELOW_RULE"
    assert buy["execution_authority"] is False


def test_pole_75_percent_reversion_requires_observed_assumptions():
    unvalidated = evaluate_module(
        "pole_75_percent_reversion",
        _reversion_state(pole_reversion_assumptions="not validated"),
    )
    synthetic = evaluate_module(
        "pole_75_percent_reversion",
        _reversion_state(pole_reversion_data_provenance="synthetic fixture"),
    )

    assert unvalidated["applicability"] == "APPLICABLE"
    assert unvalidated["pole_reversion_action"] == "ASSUMPTIONS_NOT_VALIDATED"
    assert synthetic["applicability"] == "MISSING_DATA"


def test_pole_multi_step_reversion_uses_explicit_independence_assumption():
    result = evaluate_module("pole_multi_step_reversion", _multi_step_state())
    not_independent = evaluate_module(
        "pole_multi_step_reversion",
        _multi_step_state(pole_independence_assumption="unvalidated"),
    )
    no_bias = evaluate_module(
        "pole_multi_step_reversion",
        _multi_step_state(pole_one_step_reversion_probability=0.49),
    )

    assert result["view"] == "SELL"
    assert result["pole_at_least_one_reversion_probability"] == pytest.approx(0.984375)
    assert result["pole_multistep_action"] == "REVERSION_BIAS"
    assert not_independent["view"] == "WAIT"
    assert not_independent["pole_multistep_action"] == "INDEPENDENCE_NOT_VALIDATED"
    assert no_bias["view"] == "WAIT"
    assert no_bias["pole_multistep_action"] == "NO_POSITIVE_REVERSION_BIAS"


def test_pole_multi_step_reversion_fails_closed_for_invalid_horizon():
    result = evaluate_module(
        "pole_multi_step_reversion",
        _multi_step_state(pole_reversion_steps=0),
    )

    assert result["view"] == "WAIT"
    assert result["pole_multistep_action"] == "INVALID_MULTISTEP_INPUT"
