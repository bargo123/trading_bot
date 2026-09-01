from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "carter_multisetup_pivot_view": "BUY",
        "carter_multisetup_scalper_view": "BUY",
        "carter_multisetup_data_provenance": "observed causal pivot and tick-chart signals",
    }
    state.update(overrides)
    return state


def test_carter_multisetup_requires_agreement_between_named_setups():
    result = evaluate_module("carter_multisetup_confirmation", _state())
    assert result["view"] == "BUY"
    assert result["carter_multisetup_action"] == "COMBINED_CONFIRMATION"
    assert result["carter_multisetup_agreement_count"] == 2
    assert result["directional_claim"] is True

    conflict = evaluate_module(
        "carter_multisetup_confirmation",
        _state(carter_multisetup_scalper_view="SELL"),
    )
    assert conflict["view"] == "WAIT"
    assert conflict["carter_multisetup_action"] == "CONFLICT_WAIT"


def test_carter_multisetup_keeps_the_source_direction_and_fails_closed():
    sell = evaluate_module(
        "carter_multisetup_confirmation",
        _state(
            side="SELL",
            carter_multisetup_pivot_view="SELL",
            carter_multisetup_scalper_view="SELL",
        ),
    )
    assert sell["view"] == "SELL"

    missing = evaluate_module("carter_multisetup_confirmation", {"symbol": "EURUSD", "side": "BUY"})
    assert missing["view"] == "MISSING_DATA"
    assert missing["applicability"] == "MISSING_DATA"
    assert missing["execution_authority"] is False
