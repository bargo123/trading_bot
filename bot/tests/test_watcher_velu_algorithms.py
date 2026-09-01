import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _omnibus_state(**overrides):
    state = {
        "side": "BUY",
        "velu_price_rule_direction": "up",
        "velu_realized_volatility": 0.0010,
        "velu_predicted_volatility": 0.0020,
        "velu_cumulative_actual_volume": 80.0,
        "velu_cumulative_predicted_volume": 100.0,
        "velu_omnibus_data_provenance": "observed completed interval data",
    }
    state.update(overrides)
    return state


def _fair_value_state(**overrides):
    state = {
        "side": "BUY",
        "velu_observed_return": -0.020,
        "velu_factor_expected_return": 0.001,
        "velu_fair_value_residual_threshold": 0.010,
        "velu_factor_model_status": "validated point-in-time factor model",
        "velu_fair_value_data_provenance": "observed point-in-time returns",
    }
    state.update(overrides)
    return state


def _decomposition_state(**overrides):
    state = {
        "side": "BUY",
        "velu_direction_probability": 0.62,
        "velu_expected_absolute_move": 0.010,
        "velu_transaction_cost": 0.001,
        "velu_decomposition_assumption": "validated conditional independence",
        "velu_decomposition_data_provenance": "observed point-in-time model inputs",
    }
    state.update(overrides)
    return state


def test_velu_omnibus_rule_requires_all_three_conditions_and_supports_both_sides():
    buy = evaluate_module("velu_omnibus_rule", _omnibus_state())
    sell = evaluate_module(
        "velu_omnibus_rule",
        _omnibus_state(side="SELL", velu_price_rule_direction="down"),
    )
    failed_volatility = evaluate_module(
        "velu_omnibus_rule",
        _omnibus_state(velu_realized_volatility=0.002),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["velu_omnibus_action"] == "ENTRY_ALL_CONDITIONS_TRUE"
    assert failed_volatility["view"] == "WAIT"
    assert failed_volatility["velu_omnibus_action"] == "REALIZED_VOL_NOT_BELOW_FORECAST"
    assert buy["execution_authority"] is False


def test_velu_omnibus_rule_does_not_infer_missing_or_synthetic_volume():
    missing = evaluate_module(
        "velu_omnibus_rule",
        _omnibus_state(velu_cumulative_predicted_volume=None),
    )
    synthetic = evaluate_module(
        "velu_omnibus_rule",
        _omnibus_state(velu_omnibus_data_provenance="synthetic fixture"),
    )

    assert missing["applicability"] == "MISSING_DATA"
    assert synthetic["applicability"] == "MISSING_DATA"


def test_velu_fair_value_residual_is_factor_adjusted_and_directional():
    buy = evaluate_module("velu_fair_value_residual", _fair_value_state())
    sell = evaluate_module(
        "velu_fair_value_residual",
        _fair_value_state(side="SELL", velu_observed_return=0.020),
    )
    small = evaluate_module(
        "velu_fair_value_residual",
        _fair_value_state(velu_observed_return=0.005),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["velu_fair_value_action"] == "RESIDUAL_REVERSION"
    assert buy["velu_factor_residual"] == pytest.approx(-0.021)
    assert small["view"] == "WAIT"
    assert small["velu_fair_value_action"] == "RESIDUAL_WITHIN_BAND"


def test_velu_fair_value_residual_requires_validated_factor_model():
    result = evaluate_module(
        "velu_fair_value_residual",
        _fair_value_state(velu_factor_model_status="not validated"),
    )

    assert result["view"] == "WAIT"
    assert result["velu_fair_value_action"] == "FACTOR_MODEL_NOT_VALIDATED"


def test_velu_sign_magnitude_decomposition_requires_positive_net_excess_move():
    buy = evaluate_module("velu_sign_magnitude_decomposition", _decomposition_state())
    sell = evaluate_module(
        "velu_sign_magnitude_decomposition",
        _decomposition_state(side="SELL", velu_direction_probability=0.38),
    )
    cost_kills_edge = evaluate_module(
        "velu_sign_magnitude_decomposition",
        _decomposition_state(velu_transaction_cost=0.003),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["velu_decomposition_action"] == "POSITIVE_NET_EXCESS_MOVE"
    assert buy["velu_expected_net_move"] == pytest.approx(0.0014)
    assert cost_kills_edge["view"] == "WAIT"
    assert cost_kills_edge["velu_decomposition_action"] == "COST_EXCEEDS_EXPECTED_MOVE"


def test_velu_sign_magnitude_decomposition_requires_validated_assumption():
    result = evaluate_module(
        "velu_sign_magnitude_decomposition",
        _decomposition_state(velu_decomposition_assumption="unvalidated"),
    )

    assert result["view"] == "WAIT"
    assert result["velu_decomposition_action"] == "ASSUMPTION_NOT_VALIDATED"
