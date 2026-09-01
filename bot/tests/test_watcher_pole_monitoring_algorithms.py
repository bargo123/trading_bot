import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _forecast_state(**overrides):
    state = {
        "pole_forecast_value": 1.1000,
        "pole_observed_value": 1.1010,
        "pole_forecast_error_scale": 0.00025,
        "pole_monitoring_threshold": 3.0,
        "pole_forecast_residual_streak": 3,
        "pole_required_residual_streak": 2,
        "pole_forecast_data_provenance": "observed sequential quote values",
    }
    state.update(overrides)
    return state


def _cuscore_state(**overrides):
    state = {
        "pole_cuscore": 4.2,
        "pole_cuscore_threshold": 3.0,
        "pole_change_direction": "up",
        "pole_change_confirmed": "confirmed",
        "pole_cuscore_data_provenance": "observed sequential quote values",
    }
    state.update(overrides)
    return state


def test_pole_forecast_monitoring_distinguishes_normal_error_from_intervention_signal():
    intervention = evaluate_module("pole_forecast_monitoring", _forecast_state())
    normal = evaluate_module(
        "pole_forecast_monitoring",
        _forecast_state(
            pole_observed_value=1.1002,
            pole_forecast_residual_streak=1,
        ),
    )

    assert intervention["view"] == "WAIT"
    assert intervention["pole_forecast_monitoring_action"] == "INTERVENE_MODEL_OR_EXIT"
    assert intervention["pole_standardized_residual"] == pytest.approx(4.0)
    assert normal["pole_forecast_monitoring_action"] == "WITHIN_MONITORING_BAND"
    assert intervention["directional_claim"] is False
    assert intervention["execution_authority"] is False


def test_pole_forecast_monitoring_fails_closed_for_unobserved_or_invalid_inputs():
    synthetic = evaluate_module(
        "pole_forecast_monitoring",
        _forecast_state(pole_forecast_data_provenance="synthetic fixture"),
    )
    invalid = evaluate_module(
        "pole_forecast_monitoring",
        _forecast_state(pole_forecast_error_scale=0),
    )

    assert synthetic["applicability"] == "MISSING_DATA"
    assert invalid["pole_forecast_monitoring_action"] == "INVALID_FORECAST_INPUT"


def test_pole_cuscore_change_point_requires_confirmed_observed_change():
    result = evaluate_module("pole_cuscore_change_point", _cuscore_state())
    unconfirmed = evaluate_module(
        "pole_cuscore_change_point",
        _cuscore_state(pole_change_confirmed="unconfirmed"),
    )
    below = evaluate_module(
        "pole_cuscore_change_point",
        _cuscore_state(pole_cuscore=2.9),
    )

    assert result["view"] == "WAIT"
    assert result["pole_change_point_action"] == "AVOID_OR_EXIT_REVERSION"
    assert result["pole_change_point_direction"] == "UP"
    assert unconfirmed["pole_change_point_action"] == "WAIT_FOR_CONFIRMATION"
    assert below["pole_change_point_action"] == "NO_CHANGE_POINT"
    assert result["directional_claim"] is False


def test_pole_cuscore_change_point_does_not_infer_a_reverse_trade():
    result = evaluate_module(
        "pole_cuscore_change_point",
        _cuscore_state(pole_change_direction="down"),
    )

    assert result["view"] == "WAIT"
    assert result["pole_reverse_candidate"] is False
    assert result["execution_authority"] is False


def _catastrophe_entry(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "pole_catastrophe_build_direction": "up",
        "pole_catastrophe_precursor_duration": 8.0,
        "pole_catastrophe_duration_p80": 8.0,
        "pole_catastrophe_precursor_confirmed": "confirmed",
        "pole_catastrophe_data_provenance": "observed sequential spread values",
    }
    state.update(overrides)
    return state


def test_pole_catastrophe_entry_uses_the_observed_eightieth_percentile_duration():
    result = evaluate_module("pole_catastrophe_entry", _catastrophe_entry())
    early = evaluate_module(
        "pole_catastrophe_entry",
        _catastrophe_entry(pole_catastrophe_precursor_duration=7.9),
    )

    assert result["view"] == "SELL"
    assert result["candidate_alignment"] == "SUPPORTS"
    assert result["pole_catastrophe_entry_action"] == "REVERSAL_ALERT"
    assert result["pole_catastrophe_reversal_side"] == "SELL"
    assert result["pole_catastrophe_duration_ratio"] == pytest.approx(1.0)
    assert early["view"] == "WAIT"
    assert early["pole_catastrophe_entry_action"] == "WAIT_FOR_EIGHTIETH_PERCENTILE"
    assert result["execution_authority"] is False


def test_pole_catastrophe_entry_inverts_a_downward_buildup_for_the_other_side():
    result = evaluate_module(
        "pole_catastrophe_entry",
        _catastrophe_entry(
            side="BUY",
            pole_catastrophe_build_direction="down",
        ),
    )

    assert result["view"] == "BUY"
    assert result["pole_catastrophe_reversal_side"] == "BUY"


def test_pole_catastrophe_entry_requires_confirmed_observed_duration():
    unconfirmed = evaluate_module(
        "pole_catastrophe_entry",
        _catastrophe_entry(pole_catastrophe_precursor_confirmed="unconfirmed"),
    )
    synthetic = evaluate_module(
        "pole_catastrophe_entry",
        _catastrophe_entry(pole_catastrophe_data_provenance="synthetic fixture"),
    )

    assert unconfirmed["view"] == "WAIT"
    assert unconfirmed["pole_catastrophe_entry_action"] == "WAIT_FOR_PRECURSOR_CONFIRMATION"
    assert synthetic["applicability"] == "MISSING_DATA"


def _catastrophe_exit(**overrides):
    state = {
        "evaluation_phase": "open_trade",
        "side": "SELL",
        "pole_catastrophe_build_direction": "up",
        "pole_catastrophe_reversal_spike_direction": "down",
        "pole_catastrophe_reversal_spike_confirmed": "confirmed",
        "pole_catastrophe_elapsed_periods": 4.0,
        "pole_catastrophe_exit_duration_periods": 3.0,
        "pole_catastrophe_move_magnitude": 2.0,
        "pole_catastrophe_min_exit_magnitude": 1.5,
        "pole_catastrophe_exit_data_provenance": "observed sequential spread values",
    }
    state.update(overrides)
    return state


def test_pole_catastrophe_exit_requires_opposite_spike_duration_and_magnitude():
    result = evaluate_module("pole_catastrophe_exit", _catastrophe_exit())
    duration_only = evaluate_module(
        "pole_catastrophe_exit",
        _catastrophe_exit(pole_catastrophe_move_magnitude=1.0),
    )

    assert result["view"] == "WAIT"
    assert result["pole_catastrophe_exit_action"] == "EXIT_READY"
    assert result["pole_catastrophe_duration_reached"] is True
    assert result["pole_catastrophe_magnitude_reached"] is True
    assert duration_only["pole_catastrophe_exit_action"] == "CONTINUE_MONITORING_DURATION_AND_MAGNITUDE"
    assert result["execution_authority"] is False


def test_pole_catastrophe_exit_waits_for_confirmed_opposite_spike():
    wrong_direction = evaluate_module(
        "pole_catastrophe_exit",
        _catastrophe_exit(pole_catastrophe_reversal_spike_direction="up"),
    )
    unconfirmed = evaluate_module(
        "pole_catastrophe_exit",
        _catastrophe_exit(pole_catastrophe_reversal_spike_confirmed="unconfirmed"),
    )
    pre_entry = evaluate_module(
        "pole_catastrophe_exit",
        _catastrophe_exit(evaluation_phase="pre_entry"),
    )

    assert wrong_direction["pole_catastrophe_exit_action"] == "WAIT_FOR_OPPOSITE_SPIKE"
    assert unconfirmed["pole_catastrophe_exit_action"] == "WAIT_FOR_OPPOSITE_SPIKE"
    assert pre_entry["view"] == "NOT_APPLICABLE"
