from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.execution_circuit import ExecutionCircuit


@pytest.mark.parametrize(
    "kwargs",
    (
        {"limit": 0, "window_s": 60, "backoff_s": 900},
        {"limit": 3, "window_s": 0, "backoff_s": 900},
        {"limit": 3, "window_s": 60, "backoff_s": float("nan")},
    ),
)
def test_invalid_circuit_settings_fail_closed(kwargs: dict[str, float]):
    with pytest.raises(ValueError, match="execution circuit settings"):
        ExecutionCircuit(**kwargs)


def test_three_no_money_rejections_open_persistent_backoff(tmp_path: Path):
    circuit = ExecutionCircuit(limit=3, window_s=60, backoff_s=900)
    for second in (0, 10, 20):
        circuit.observe("10019 No money", now=float(second))

    allowed, reason = circuit.allow(now=21.0)
    assert not allowed
    assert reason == "no_money_backoff"

    path = tmp_path / "execution_circuit.json"
    circuit.save_json(path)
    restored = ExecutionCircuit(limit=3, window_s=60, backoff_s=900)
    assert restored.load_json(path)
    assert restored.dump() == circuit.dump()
    assert not restored.allow(now=22.0)[0]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("limit", 3.5),
        ("consecutive_failures", True),
        ("window_s", True),
        ("blocked_until", "1000"),
        ("no_money_times", [20.0, 10.0]),
    ),
)
def test_invalid_integer_state_does_not_mutate_the_circuit(
    tmp_path: Path, field: str, value: object
):
    circuit = ExecutionCircuit(
        limit=3,
        window_s=60,
        backoff_s=900,
        blocked_until=1000,
        consecutive_failures=2,
    )
    before = circuit.dump()
    payload = dict(before)
    payload[field] = value
    path = tmp_path / "execution_circuit.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert not circuit.load_json(path)
    assert circuit.dump() == before


def test_accepted_order_does_not_erase_active_no_money_backoff():
    circuit = ExecutionCircuit(limit=1, window_s=60, backoff_s=900)
    circuit.observe("10019 No money", now=10.0)
    circuit.observe("accepted", now=11.0, ok=True)

    assert circuit.consecutive_failures == 0
    assert circuit.allow(now=12.0) == (False, "no_money_backoff")


def test_persisted_configuration_does_not_override_current_validated_settings(
    tmp_path: Path,
):
    path = tmp_path / "execution_circuit.json"
    old = ExecutionCircuit(
        limit=9,
        window_s=300,
        backoff_s=1200,
        blocked_until=500,
        consecutive_failures=2,
    )
    old.observe("10019 No money", now=10.0)
    old.save_json(path)

    current = ExecutionCircuit(limit=3, window_s=60, backoff_s=900)
    assert current.load_json(path)
    assert (current.limit, current.window_s, current.backoff_s) == (3, 60, 900)
    assert current.blocked_until == 500
    assert current.consecutive_failures == 3
    assert list(current.no_money_times) == [10.0]
