import pytest

from aegis.intel.firehose_basket import BasketMetadataStore, can_add_clip
from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata


def _store_basket(store, *, clip_cap=3, unrealized_pnl=5.0):
    return store.create_basket(
        basket_id="basket-1",
        hypothesis_id="hypothesis-1",
        family="breakout",
        symbol="EURUSD",
        side="buy",
        risk_budget=20.0,
        clip_cap=clip_cap,
        tick_value=2.5,
        tick_size=0.0001,
        regime="trend",
        session="london",
        entry_geometry={"entry_price": 1.1000, "stop_loss": 1.0980},
        unrealized_pnl=unrealized_pnl,
    )


def _continuation(**overrides):
    continuation = {
        "side": "buy",
        "trigger_id": "trigger-2",
        "fresh_trigger": True,
        "positive_evidence": True,
        "normal_spread": True,
        "remaining_ev": 0.25,
        "adverse_selection": False,
        "policy_artifact": {"validated": True, "complete": True},
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


def test_restart_preserves_exact_basket_ticket_ownership_and_geometry(tmp_path):
    basket_path = tmp_path / "baskets.json"
    ticket_path = tmp_path / "tickets.json"
    basket_store = BasketMetadataStore(basket_path)
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

    restored_basket = BasketMetadataStore(basket_path).get_basket("basket-1")
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
    store = BasketMetadataStore(tmp_path / "baskets.json")
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
    store = BasketMetadataStore(tmp_path / "baskets.json")
    _store_basket(store, clip_cap=1)
    _record_initial_clip(store)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(), 1.0) == (
        False, "clip_cap",
    )


def test_add_requires_fresh_same_side_continuation_and_validated_policy(tmp_path):
    store = BasketMetadataStore(tmp_path / "baskets.json")
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
    store = BasketMetadataStore(tmp_path / "baskets.json")
    _store_basket(store, unrealized_pnl=-0.01)
    _record_initial_clip(store)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(), 1.0) == (
        False, "losing_basket",
    )


def test_opposite_side_continuation_cannot_self_hedge(tmp_path):
    store = BasketMetadataStore(tmp_path / "baskets.json")
    _store_basket(store)
    _record_initial_clip(store)

    assert can_add_clip(store.get_basket("basket-1"), _continuation(side="sell"), 1.0) == (
        False, "opposite_side_self_hedge",
    )
