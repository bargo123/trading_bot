import json
import multiprocessing
import time
from pathlib import Path

import pytest

from aegis.intel.firehose_basket import BasketMetadataStore, can_add_clip
from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata
from aegis.sizing import ContractSpec


def _store_basket(store, *, clip_cap=3, unrealized_pnl=5.0, risk_budget=20.0):
    return store.create_basket(
        basket_id="basket-1",
        hypothesis_id="hypothesis-1",
        family="breakout",
        symbol="EURUSD",
        side="buy",
        risk_budget=risk_budget,
        clip_cap=clip_cap,
        tick_value=2.5,
        tick_size=0.0001,
        regime="trend",
        session="london",
        entry_geometry={"entry_price": 1.1000, "stop_loss": 1.0980},
        unrealized_pnl=unrealized_pnl,
    )


def _trusted_contract(*, tick_value=2.5, tick_size=0.0001):
    return ContractSpec(
        symbol="EURUSD", tick_size=tick_size, tick_value=tick_value,
        contract_size=100000.0, volume_min=0.01, volume_max=100.0, volume_step=0.01,
    )


def _metadata_store(path):
    return BasketMetadataStore(path, trusted_contract=_trusted_contract())


def _continuation(**overrides):
    observed_at = time.time()
    continuation = {
        "side": "buy",
        "trigger_id": "trigger-2",
        "fresh_trigger": True,
        "positive_evidence": True,
        "normal_spread": True,
        "remaining_ev": 0.25,
        "adverse_selection": False,
        "policy_artifact": {"validated": True, "complete": True},
        "broker_pnl": {"unrealized_pnl": 5.0, "observed_at": observed_at},
        "evaluated_at": observed_at,
    }
    continuation.update(overrides)
    return continuation


def _record_initial_clip(store):
    return store.record_ticket(
        "basket-1",
        ticket_id="ticket-1",
        trigger_id="trigger-1",
        clip_sequence=1,
        entry_price=1.1000,
        stop_loss=1.0980,
        volume=0.2,
        cost_evidence={"spread_ticks": 1.0, "commission_usd": 0.4},
        regime="trend",
        session="london",
    )


def _record_competing_clip(path, ready, proceed, outcomes):
    store = _metadata_store(Path(path))
    ready.set()
    if not proceed.wait(10):
        outcomes.put(("timeout", ""))
        return
    try:
        store.record_ticket(
            "basket-1", ticket_id="ticket-competing", trigger_id="trigger-competing",
            clip_sequence=2, entry_price=1.1000, stop_loss=1.0980, volume=0.2,
            cost_evidence={"spread_ticks": 1.0}, regime="trend", session="london",
            continuation=_continuation(trigger_id="trigger-competing"),
        )
    except ValueError as exc:
        outcomes.put(("rejected", str(exc)))
    else:
        outcomes.put(("admitted", ""))


def test_restart_preserves_exact_basket_ticket_ownership_and_geometry(tmp_path):
    basket_path = tmp_path / "baskets.json"
    ticket_path = tmp_path / "tickets.json"
    basket_store = _metadata_store(basket_path)
    _store_basket(basket_store)
    _record_initial_clip(basket_store)

    ticket_store = TicketMetadataStore(ticket_path)
    ticket_store.add(create_ticket_metadata(
        ticket="ticket-1", hypothesis_id="hypothesis-1", thesis_key="breakout",
        strategy_family="breakout", expected_mechanism="continuation", side="buy",
        entry_price=1.1000, stop_loss=1.0980, target_price=1.1040, max_hold_s=300,
        regime="trend", session="london", symbol="EURUSD", basket_id="basket-1",
        trigger_id="trigger-1", clip_sequence=1,
        entry_geometry={"entry_price": 1.1000, "stop_loss": 1.0980},
        initial_risk=10.0, cost_evidence={"spread_ticks": 1.0, "commission_usd": 0.4},
    ))

    restored_basket = _metadata_store(basket_path).get_basket("basket-1")
    restored_ticket = TicketMetadataStore(ticket_path).get("ticket-1")

    assert restored_basket.ticket_ids == ("ticket-1",)
    assert restored_basket.tickets[0].trigger_id == "trigger-1"
    assert restored_basket.tickets[0].clip_sequence == 1
    assert restored_basket.tickets[0].entry_geometry == {
        "entry_price": 1.1, "stop_loss": 1.098,
    }
    assert restored_basket.tickets[0].cost_evidence == {
        "spread_ticks": 1.0, "commission_usd": 0.4,
    }
    assert restored_ticket.basket_id == "basket-1"
    assert restored_ticket.entry_geometry == {"entry_price": 1.1, "stop_loss": 1.098}


def test_broker_native_risk_budget_uses_tick_value_and_tick_size(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store)
    _record_initial_clip(store)
    basket = store.get_basket("basket-1")

    assert basket.total_risk == pytest.approx(10.0)
    assert can_add_clip(basket, _continuation(), 10.0) == (True, "allowed")
    assert can_add_clip(basket, _continuation(), 10.01) == (False, "risk_budget")

    with pytest.raises(ValueError, match="risk_budget"):
        store.record_ticket(
            "basket-1", ticket_id="ticket-2", trigger_id="trigger-2", clip_sequence=2,
            entry_price=1.1000, stop_loss=1.0980, volume=0.201,
            cost_evidence={"spread_ticks": 1.0}, regime="trend", session="london",
            continuation=_continuation(),
        )


def test_clip_cap_rejects_another_clip(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store, clip_cap=1)
    _record_initial_clip(store)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(), 1.0) == (
        False, "clip_cap",
    )


def test_add_requires_fresh_same_side_continuation_and_validated_policy(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store)
    _record_initial_clip(store)
    basket = store.get_basket("basket-1")

    assert can_add_clip(basket, _continuation(fresh_trigger=False), 1.0) == (
        False, "stale_trigger",
    )
    assert can_add_clip(basket, _continuation(trigger_id="trigger-1"), 1.0) == (
        False, "stale_trigger",
    )
    assert can_add_clip(basket, _continuation(policy_artifact=None), 1.0) == (
        False, "no_validated_policy",
    )


def test_losing_basket_cannot_add_a_clip(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store, unrealized_pnl=-0.01)
    _record_initial_clip(store)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(
        broker_pnl={"unrealized_pnl": -0.01, "observed_at": time.time()},
    ), 1.0) == (
        False, "losing_basket",
    )


def test_opposite_side_continuation_cannot_self_hedge(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store)
    _record_initial_clip(store)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(side="sell"), 1.0) == (
        False, "opposite_side_self_hedge",
    )


def test_add_rejects_missing_or_stale_broker_pnl(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store)
    _record_initial_clip(store)
    basket = store.get_basket("basket-1")

    assert can_add_clip(basket, _continuation(broker_pnl=None), 1.0) == (
        False, "missing_broker_pnl",
    )
    assert can_add_clip(basket, _continuation(
        broker_pnl={"unrealized_pnl": 5.0, "observed_at": 90.0},
    ), 1.0) == (False, "stale_broker_pnl")


@pytest.mark.parametrize("proposed_risk", [float("nan"), float("inf"), 0.0, -1.0])
def test_add_rejects_nonfinite_or_nonpositive_risk(tmp_path, proposed_risk):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store)
    _record_initial_clip(store)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(), proposed_risk) == (
        False, "invalid_risk",
    )


def test_create_basket_rejects_nan_risk_budget(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")

    with pytest.raises(ValueError, match="invalid_basket_limits"):
        _store_basket(store, risk_budget=float("nan"))


def test_record_ticket_rolls_back_and_raises_when_persistence_fails(tmp_path, monkeypatch):
    path = tmp_path / "baskets.json"
    store = _metadata_store(path)
    _store_basket(store)

    def fail_save():
        raise OSError("disk full")

    monkeypatch.setattr(store, "_save", fail_save)
    with pytest.raises(OSError, match="disk full"):
        _record_initial_clip(store)

    assert store.get_basket("basket-1").ticket_ids == ()
    assert _metadata_store(path).get_basket("basket-1").ticket_ids == ()


def test_admission_reloads_current_state_inside_cross_process_lock(tmp_path):
    path = tmp_path / "baskets.json"
    initial = _metadata_store(path)
    _store_basket(initial)
    _record_initial_clip(initial)

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    proceed = context.Event()
    outcomes = context.Queue()
    competing = context.Process(
        target=_record_competing_clip, args=(str(path), ready, proceed, outcomes),
    )
    competing.start()
    assert ready.wait(10)

    primary = _metadata_store(path)
    primary.record_ticket(
        "basket-1", ticket_id="ticket-primary", trigger_id="trigger-primary",
        clip_sequence=2, entry_price=1.1000, stop_loss=1.0980, volume=0.2,
        cost_evidence={"spread_ticks": 1.0}, regime="trend", session="london",
        continuation=_continuation(trigger_id="trigger-primary"),
    )
    proceed.set()
    competing.join(10)

    assert competing.exitcode == 0
    assert outcomes.get(timeout=1)[0] == "rejected"
    assert _metadata_store(path).get_basket("basket-1").ticket_ids == (
        "ticket-1", "ticket-primary",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk_budget", float("inf")),
        ("tick_value", float("nan")),
        ("ticket.initial_risk", float("nan")),
        ("ticket.volume", float("inf")),
    ],
)
def test_reload_fails_closed_on_nonfinite_serialized_basket_fields(tmp_path, field, value):
    path = tmp_path / "baskets.json"
    store = _metadata_store(path)
    _store_basket(store)
    _record_initial_clip(store)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    if field.startswith("ticket."):
        persisted["basket-1"]["tickets"][0][field.removeprefix("ticket.")] = value
    else:
        persisted["basket-1"][field] = value
    path.write_text(json.dumps(persisted), encoding="utf-8")

    reloaded = _metadata_store(path)

    assert reloaded.get_basket("basket-1") is None
    with pytest.raises(KeyError):
        reloaded.record_ticket(
            "basket-1", ticket_id="ticket-2", trigger_id="trigger-2", clip_sequence=2,
            entry_price=1.1000, stop_loss=1.0980, volume=0.2,
            cost_evidence={"spread_ticks": 1.0}, regime="trend", session="london",
            continuation=_continuation(),
        )


def test_initial_ticket_rejects_zero_broker_native_risk(tmp_path):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store)

    with pytest.raises(ValueError, match="invalid_broker_risk"):
        store.record_ticket(
            "basket-1", ticket_id="ticket-1", trigger_id="trigger-1", clip_sequence=1,
            entry_price=1.1000, stop_loss=1.1000, volume=0.2,
            cost_evidence={"spread_ticks": 1.0}, regime="trend", session="london",
        )


def test_pnl_freshness_uses_trusted_clock_not_caller_timestamp(tmp_path, monkeypatch):
    store = _metadata_store(tmp_path / "baskets.json")
    _store_basket(store)
    _record_initial_clip(store)
    monkeypatch.setattr("aegis.intel.firehose_basket.time.time", lambda: 100.0)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(
        broker_pnl={"unrealized_pnl": 5.0, "observed_at": 0.0}, evaluated_at=0.0,
    ), 1.0) == (False, "stale_broker_pnl")


def test_reload_fails_closed_when_persisted_root_is_not_a_basket_mapping(tmp_path):
    path = tmp_path / "baskets.json"
    path.write_text("[]", encoding="utf-8")

    assert _metadata_store(path).get_basket("basket-1") is None


def test_reload_rejects_root_key_that_does_not_match_embedded_basket_id(tmp_path):
    path = tmp_path / "baskets.json"
    store = _metadata_store(path)
    _store_basket(store)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    persisted["alias-basket"] = persisted.pop("basket-1")
    path.write_text(json.dumps(persisted), encoding="utf-8")

    reloaded = _metadata_store(path)

    assert reloaded.get_basket("basket-1") is None
    assert reloaded.get_basket("alias-basket") is None


def test_reload_rejects_reduced_finite_ticket_risk_before_another_clip_can_admit(tmp_path):
    path = tmp_path / "baskets.json"
    store = _metadata_store(path)
    _store_basket(store)
    _record_initial_clip(store)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    persisted["basket-1"]["tickets"][0]["initial_risk"] = 1.0
    path.write_text(json.dumps(persisted), encoding="utf-8")

    reloaded = _metadata_store(path)

    assert reloaded.get_basket("basket-1") is None
    with pytest.raises(KeyError):
        reloaded.record_ticket(
            "basket-1", ticket_id="ticket-2", trigger_id="trigger-2", clip_sequence=2,
            entry_price=1.1000, stop_loss=1.0980, volume=0.38,
            cost_evidence={"spread_ticks": 1.0}, regime="trend", session="london",
            continuation=_continuation(),
        )


def test_reload_requires_trusted_contract_evidence(tmp_path):
    path = tmp_path / "baskets.json"
    store = _metadata_store(path)
    _store_basket(store)

    assert BasketMetadataStore(path).get_basket("basket-1") is None


def test_reload_rejects_persisted_contract_mismatch(tmp_path):
    path = tmp_path / "baskets.json"
    store = _metadata_store(path)
    _store_basket(store)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    persisted["basket-1"]["tick_value"] = 5.0
    path.write_text(json.dumps(persisted), encoding="utf-8")

    assert BasketMetadataStore(path, trusted_contract=_trusted_contract()).get_basket("basket-1") is None


def test_reload_rejects_coordinated_persisted_tick_and_risk_tampering(tmp_path):
    path = tmp_path / "baskets.json"
    store = _metadata_store(path)
    _store_basket(store)
    _record_initial_clip(store)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    persisted["basket-1"]["tick_value"] = 5.0
    persisted["basket-1"]["tickets"][0]["initial_risk"] = 20.0
    path.write_text(json.dumps(persisted), encoding="utf-8")

    reloaded = BasketMetadataStore(path, trusted_contract=_trusted_contract())

    assert reloaded.get_basket("basket-1") is None
