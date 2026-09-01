from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _atr(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "link_atr_value": 0.0100,
        "link_stop_distance": 0.0020,
        "link_max_atr_risk_fraction": 0.30,
        "link_atr_risk_data_provenance": "observed timestamped ATR and structural stop",
    }
    state.update(overrides)
    return state


def _stop(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "link_stop_initial_distance": 0.0020,
        "link_stop_current_distance": 0.0020,
        "link_stop_moved_away": False,
        "link_stop_discipline_data_provenance": "observed timestamped stop amendments",
    }
    state.update(overrides)
    return state


def test_link_atr_risk_skips_when_a_structurally_correct_stop_is_too_far():
    result = evaluate_module("link_atr_risk_feasibility", _atr())
    assert result["view"] == "WAIT"
    assert result["link_atr_risk_assessment"] == "RISK_FEASIBLE"
    assert result["link_max_stop_distance"] == pytest.approx(0.003)
    assert result["directional_claim"] is False

    skip = evaluate_module(
        "link_atr_risk_feasibility",
        _atr(link_stop_distance=0.0040),
    )
    assert skip["link_atr_risk_assessment"] == "STOP_TOO_FAR_SKIP"


def test_link_cancel_if_close_detects_only_stop_widening():
    intact = evaluate_module("link_stop_discipline", _stop())
    assert intact["link_stop_discipline_assessment"] == "STOP_PROTECTION_INTACT"

    widened = evaluate_module(
        "link_stop_discipline",
        _stop(link_stop_current_distance=0.0030),
    )
    assert widened["link_stop_discipline_assessment"] == "CANCEL_IF_CLOSE_VIOLATION"

    declared = evaluate_module(
        "link_stop_discipline",
        _stop(link_stop_moved_away=True),
    )
    assert declared["link_stop_discipline_assessment"] == "CANCEL_IF_CLOSE_VIOLATION"


@pytest.mark.parametrize(
    "algorithm_id",
    ["link_atr_risk_feasibility", "link_stop_discipline"],
)
def test_link_risk_rules_fail_closed_without_observed_inputs(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
