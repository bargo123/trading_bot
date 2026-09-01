from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCES = [
    "Mark Douglas — The Disciplined Trader",
    "Mark Douglas — Trading in the Zone",
    "Jared Tendler — The Mental Game of Trading",
    "Noble DraKoln — Winning the Trading Game",
]


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "process_rules_defined": True,
        "process_risk_defined": True,
        "process_rule_compliant": True,
        "process_loss_accepted": True,
        "process_revenge_impulse": False,
        "process_confirmation_bias": False,
        "process_emotional_state": "stable",
        "process_data_provenance": "operator_journal_at_decision_time",
    }
    state.update(overrides)
    return state


def test_process_discipline_is_ready_only_when_risk_and_rules_are_defined():
    result = evaluate_module("process_discipline_control", _state())
    assert result["view"] == "WAIT"
    assert result["process_assessment"] == "READY"
    assert result["directional_claim"] is False
    assert result["source_books"] == SOURCES


@pytest.mark.parametrize(
    "overrides",
    [
        {"process_rules_defined": False},
        {"process_risk_defined": False},
        {"process_rule_compliant": False},
        {"process_loss_accepted": False},
        {"process_revenge_impulse": True},
        {"process_confirmation_bias": True},
    ],
)
def test_process_discipline_flags_unready_or_emotion_driven_decisions(overrides):
    result = evaluate_module("process_discipline_control", _state(**overrides))
    assert result["view"] == "WAIT"
    assert result["process_assessment"] == "BLOCKED"
    assert result["reasons"]


def test_process_discipline_is_not_a_directional_trade_signal():
    result = evaluate_module("process_discipline_control", _state(side="SELL"))
    assert result["view"] == "WAIT"
    assert result["candidate_alignment"] == "UNRESOLVED"
    assert result["execution_authority"] is False


def test_process_discipline_fails_closed_without_journal_provenance():
    result = evaluate_module("process_discipline_control", {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
