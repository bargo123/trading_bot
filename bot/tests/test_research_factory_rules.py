"""Tests for canonical hypotheses and fail-closed rule compilation."""
from __future__ import annotations

from dataclasses import replace
from inspect import Parameter, signature

import pytest

import aegis.research_factory.core as research_factory_core
from aegis.research_factory.hypothesis import (
    Hypothesis,
    HypothesisOrigin,
    HypothesisRegistry,
    HypothesisStatus,
)
from aegis.research_factory.rules import compile_hypothesis


def complete_hypothesis(**overrides):
    values = {
        "hypothesis_id": "hyp-breakout-1",
        "origin": HypothesisOrigin.DATA_DERIVED,
        "problem": "Breakouts continue after clearing the prior range",
        "proposed_mechanism": "Range clearance reveals directional demand",
        "features_required": ["high", "low", "close", "regime"],
        "entry_rule": {"type": "breakout", "direction": "long", "window": 20},
        "exit_rule": {"type": "regime_change"},
        "side": "buy",
        "entry_price": 100.0,
        "invalidation_price": 99.0,
        "target_price": 102.0,
        "max_hold_s": 300,
        "expected_effect": "Positive net expectancy",
        "falsification_criterion": "Net expectancy is non-positive out of sample",
        "training_period": "2024-01-01/2024-06-30",
        "validation_period": "2024-07-01/2024-09-30",
        "book_evidence": [{"source": "book", "passage_hash": "abc"}],
        "ml_evidence": {"model": "chronological"},
        "loss_autopsy_evidence": [{"loss_class": "FALSE_BREAKOUT"}],
    }
    values.update(overrides)
    return Hypothesis(**values)


def test_hypothesis_round_trip_preserves_structured_fields_and_enums():
    hypothesis = complete_hypothesis(status=HypothesisStatus.TESTING)

    restored = Hypothesis.from_dict(hypothesis.to_dict())

    assert restored == hypothesis
    assert restored.origin is HypothesisOrigin.DATA_DERIVED
    assert restored.status is HypothesisStatus.TESTING
    assert restored.side == "buy"
    assert restored.entry_rule == {
        "type": "breakout",
        "direction": "long",
        "window": 20,
    }
    assert restored.exit_rule == {"type": "regime_change"}


def test_registry_update_status_stores_enum():
    registry = HypothesisRegistry()
    hypothesis = complete_hypothesis()
    registry.register(hypothesis)

    assert registry.update_status(hypothesis.hypothesis_id, "TESTING") is True
    assert hypothesis.status is HypothesisStatus.TESTING


def test_core_uses_the_canonical_hypothesis_schema():
    assert research_factory_core.Hypothesis is Hypothesis
    assert research_factory_core.HypothesisOrigin is HypothesisOrigin


def test_research_state_round_trip_uses_canonical_hypothesis_enums(tmp_path):
    hypothesis = complete_hypothesis(status=HypothesisStatus.TESTING)
    state = research_factory_core.ResearchState(
        hypothesis_registry={hypothesis.hypothesis_id: hypothesis}
    )
    path = tmp_path / "state.json"

    state.save(path)
    restored = research_factory_core.ResearchState.load(path)

    assert restored.hypothesis_registry[hypothesis.hypothesis_id] == hypothesis


@pytest.mark.parametrize(
    "field",
    [
        "side",
        "expected_effect",
        "training_period",
        "validation_period",
        "invalidation_price",
        "target_price",
        "book_evidence",
        "ml_evidence",
        "loss_autopsy_evidence",
    ],
)
def test_evidence_bearing_schema_fields_have_no_invented_defaults(field):
    assert signature(Hypothesis).parameters[field].default is Parameter.empty


@pytest.mark.parametrize(
    "entry_rule,available_columns,reason",
    [
        ({"type": "unknown"}, {"time", "close"}, "unknown entry rule"),
        (
            {"type": "breakout", "direction": "long"},
            {"time", "close"},
            "missing columns",
        ),
        (
            {"type": "breakout", "direction": "long", "window": 0},
            {"time", "high", "low", "close", "regime"},
            "window",
        ),
    ],
)
def test_invalid_rules_are_not_executable(entry_rule, available_columns, reason):
    hypothesis = complete_hypothesis(entry_rule=entry_rule)

    result = compile_hypothesis(hypothesis, available_columns)

    assert result.status == "NOT_EXECUTABLE"
    assert reason in result.reason


@pytest.mark.parametrize(
    "side,entry_price,invalidation_price,target_price,reason",
    [
        ("buy", 100.0, 100.0, 102.0, "buy invalidation price"),
        ("buy", 100.0, 99.0, 100.0, "buy target price"),
        ("sell", 100.0, 100.0, 98.0, "sell invalidation price"),
        ("sell", 100.0, 101.0, 100.0, "sell target price"),
    ],
)
def test_invalid_price_geometry_is_not_executable(
    side, entry_price, invalidation_price, target_price, reason
):
    hypothesis = complete_hypothesis(
        side=side,
        entry_price=entry_price,
        invalidation_price=invalidation_price,
        target_price=target_price,
    )

    result = compile_hypothesis(
        hypothesis, {"time", "high", "low", "close", "regime"}
    )

    assert result.status == "NOT_EXECUTABLE"
    assert reason in result.reason


def test_missing_side_is_not_executable():
    result = compile_hypothesis(
        replace(complete_hypothesis(), side=None),
        {"time", "high", "low", "close", "regime"},
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.reason == "missing side"


def test_missing_source_evidence_is_not_executable():
    result = compile_hypothesis(
        complete_hypothesis(
            book_evidence=[], ml_evidence={}, loss_autopsy_evidence=[]
        ),
        {"time", "high", "low", "close", "regime"},
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.reason == "missing source evidence"


@pytest.mark.parametrize("exit_type", ["trailing_stop", "adverse_selection"])
def test_unimplemented_exit_types_are_not_executable(exit_type):
    result = compile_hypothesis(
        complete_hypothesis(exit_rule={"type": exit_type}),
        {"time", "high", "low", "close", "regime"},
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.reason == f"unknown exit rule: {exit_type}"


@pytest.mark.parametrize(
    "entry_rule,columns,normalized_direction",
    [
        (
            {"type": "breakout", "direction": "short", "window": 10},
            {"time", "high", "low", "close", "regime"},
            "long",
        ),
        (
            {"type": "mean_reversion", "direction": "short", "z_threshold": 2.0},
            {"time", "close", "sma_20", "regime"},
            "long",
        ),
        (
            {
                "type": "regime_structure_alignment",
                "required_regimes": ["trend"],
                "required_structure": True,
            },
            {"time", "regime", "structure"},
            "long",
        ),
    ],
)
def test_supported_entry_rules_are_executable(
    entry_rule, columns, normalized_direction
):
    result = compile_hypothesis(
        complete_hypothesis(
            entry_rule=entry_rule,
            features_required=sorted(columns - {"time"}),
            entry_price=None,
            invalidation_price=None,
            target_price=None,
        ),
        columns,
    )

    assert result.status == "EXECUTABLE"
    assert result.reason == ""
    assert result.entry_rule["direction"] == normalized_direction
    assert result.required_columns <= columns


@pytest.mark.parametrize(
    "exit_rule,max_hold_s,expected_type",
    [
        ({"type": "regime_change"}, 300, "regime_change"),
        ({"type": "stop_target"}, None, "stop_target"),
        ({"type": "stop_loss"}, None, "stop_loss"),
        ({"type": "target_hit"}, None, "target_hit"),
        ({"type": "elapsed_time"}, 300, "elapsed_time"),
        ({"type": "time_exit"}, 300, "elapsed_time"),
    ],
)
def test_supported_exit_rules_are_executable(exit_rule, max_hold_s, expected_type):
    columns = {"time", "high", "low", "close", "regime"}
    result = compile_hypothesis(
        complete_hypothesis(
            exit_rule=exit_rule,
            max_hold_s=max_hold_s,
            features_required=["high", "low", "close", "regime"],
        ),
        columns,
    )

    assert result.status == "EXECUTABLE"
    assert result.exit_rule["type"] == expected_type
    assert result.required_columns <= columns


def test_elapsed_time_requires_a_positive_holding_limit():
    result = compile_hypothesis(
        complete_hypothesis(exit_rule={"type": "elapsed_time"}, max_hold_s=None),
        {"time", "high", "low", "close", "regime"},
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.reason == "max_hold_s must be a positive integer"


@pytest.mark.parametrize(
    "exit_rule,overrides,reason",
    [
        (
            {"type": "stop_loss"},
            {"invalidation_price": None},
            "stop_loss requires an invalidation price",
        ),
        (
            {"type": "target_hit"},
            {"target_price": None},
            "target_hit requires a target price",
        ),
    ],
)
def test_explicit_price_exits_require_their_price(exit_rule, overrides, reason):
    result = compile_hypothesis(
        complete_hypothesis(exit_rule=exit_rule, max_hold_s=None, **overrides),
        {"time", "high", "low", "close", "regime"},
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.reason == reason
