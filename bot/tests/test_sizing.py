from dataclasses import replace

import pytest

from aegis.sizing import ContractSpec, size_lots_for_risk


def eurusd_spec() -> ContractSpec:
    return ContractSpec(
        symbol="EURUSD",
        tick_size=0.00001,
        tick_value=1.0,
        contract_size=100000.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )


def test_sizes_down_to_broker_step_without_exceeding_risk():
    result = size_lots_for_risk(
        equity=10_000.0,
        risk_percent=0.5,
        entry=1.10000,
        stop=1.09500,
        spec=eurusd_spec(),
    )
    assert result.allowed
    assert result.lots == 0.10
    assert result.risk_usd <= 50.0


def test_rejects_when_minimum_lot_exceeds_risk_budget():
    result = size_lots_for_risk(
        equity=57.0,
        risk_percent=0.25,
        entry=1.10000,
        stop=1.09500,
        spec=eurusd_spec(),
    )
    assert not result.allowed
    assert result.reason == "minimum_lot_exceeds_risk"


def test_broker_maximum_is_rounded_down_to_volume_step():
    result = size_lots_for_risk(
        equity=1_000_000.0,
        risk_percent=1.0,
        entry=1.10000,
        stop=1.09500,
        spec=replace(eurusd_spec(), volume_max=0.105),
    )
    assert result.allowed
    assert result.lots == 0.10
    assert result.risk_usd <= result.budget_usd


def test_contract_spec_uses_most_conservative_tick_value():
    spec = ContractSpec.from_mapping(
        "EURUSD",
        {
            "name": "EURUSD.a",
            "point": 0.00001,
            "trade_tick_value": 0.95,
            "trade_tick_value_profit": 0.98,
            "trade_tick_value_loss": -1.02,
            "trade_contract_size": 100000,
            "volume_min": 0.01,
            "volume_max": 100,
            "volume_step": 0.01,
        },
    )
    assert spec.symbol == "EURUSD.a"
    assert spec.tick_size == 0.00001
    assert spec.tick_value == 1.02


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trade_tick_value", float("nan")),
        ("trade_tick_value", float("inf")),
        ("trade_tick_value_profit", float("nan")),
        ("trade_tick_value_profit", float("inf")),
        ("trade_tick_value_loss", float("nan")),
        ("trade_tick_value_loss", float("inf")),
    ],
)
def test_contract_spec_rejects_every_nonfinite_supplied_tick_value(field, value):
    raw = {
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "trade_tick_value_profit": 0.99,
        "trade_tick_value_loss": 1.01,
        "trade_contract_size": 100000.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
    }
    raw[field] = value
    with pytest.raises(ValueError, match="tick_value"):
        ContractSpec.from_mapping("EURUSD", raw)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"equity": 0.0}, "equity"),
        ({"risk_percent": 0.0}, "risk_percent"),
        ({"stop": 1.10000}, "stop_distance"),
        ({"spec": replace(eurusd_spec(), tick_size=0.0)}, "tick_value"),
        ({"spec": replace(eurusd_spec(), tick_value=0.0)}, "tick_value"),
        ({"spec": replace(eurusd_spec(), volume_step=0.0)}, "volume_spec"),
        ({"spec": replace(eurusd_spec(), volume_max=0.001)}, "volume_spec"),
        ({"equity": float("nan")}, "equity"),
        ({"risk_percent": float("inf")}, "risk_percent"),
        ({"entry": float("nan")}, "stop_distance"),
        ({"spec": replace(eurusd_spec(), tick_value=float("nan"))}, "tick_value"),
        ({"spec": replace(eurusd_spec(), contract_size=0.0)}, "contract_size"),
        ({"spec": replace(eurusd_spec(), volume_max=float("inf"))}, "volume_spec"),
    ],
)
def test_rejects_invalid_sizing_inputs_with_explicit_reason(changes, reason):
    inputs = {
        "equity": 10_000.0,
        "risk_percent": 0.5,
        "entry": 1.10000,
        "stop": 1.09500,
        "spec": eurusd_spec(),
    }
    inputs.update(changes)
    result = size_lots_for_risk(**inputs)
    assert not result.allowed
    assert result.reason == reason
