"""Offline regression tests for IBKR order and account hygiene."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.engines.ibkr import IBKREngine
from aegis.engines.base import OrderRequest
from aegis.engines.ibkr_order_state import is_working_status


class FakeIB:
    def __init__(self) -> None:
        self.account_summary_calls = 0

    def isConnected(self) -> bool:
        return True

    def accountValues(self):
        return [
            SimpleNamespace(tag="NetLiquidation", value="250000.00", currency="USD"),
            SimpleNamespace(tag="AvailableFunds", value="249000.00", currency="USD"),
            SimpleNamespace(tag="Currency", value="USD", currency="USD"),
        ]

    def accountSummary(self):
        self.account_summary_calls += 1
        raise AssertionError("accountSummary() must not be called")

    def managedAccounts(self):
        return ["PAPER_ACCOUNT"]


class FakeClient:
    def __init__(self) -> None:
        self.next_id = 100

    def getReqId(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value


class FakeOrderIB(FakeIB):
    def __init__(
        self,
        parent_status: str = "PreSubmitted",
        child_status: str = "PreSubmitted",
    ) -> None:
        super().__init__()
        self.client = FakeClient()
        self.parent_status = parent_status
        self.child_status = child_status
        self.placed_orders = []
        self.cancelled_order_ids: set[int] = set()

    def placeOrder(self, contract, order):
        if not int(getattr(order, "orderId", 0) or 0):
            order.orderId = self.client.getReqId()
        order.clientId = 7
        self.placed_orders.append(order)
        status = (
            self.parent_status
            if not int(getattr(order, "parentId", 0) or 0)
            else self.child_status
        )
        return SimpleNamespace(
            order=order,
            orderStatus=SimpleNamespace(status=status),
            fills=[],
        )

    def cancelOrder(self, order):
        self.cancelled_order_ids.add(int(order.orderId))

    def sleep(self, _seconds: float) -> None:
        return None


def trade_with_status(status: str, order_id: int):
    order = SimpleNamespace(orderId=order_id, clientId=7, permId=10_000 + order_id)
    return SimpleNamespace(order=order, orderStatus=SimpleNamespace(status=status))


class FakeLifecycleIB(FakeOrderIB):
    def __init__(self, order_refreshes=None, position_qty: float = 0.0) -> None:
        super().__init__()
        self.order_refreshes = list(order_refreshes or [[]])
        self.global_cancel_calls = 0
        self.actions: list[str] = []
        self._positions = []
        if position_qty:
            contract = SimpleNamespace(symbol="EUR", currency="USD")
            self._positions.append(
                SimpleNamespace(contract=contract, position=position_qty, avgCost=1.15430)
            )

    def reqGlobalCancel(self) -> None:
        self.global_cancel_calls += 1
        self.actions.append("global_cancel")

    def reqAllOpenOrders(self):
        if len(self.order_refreshes) > 1:
            return self.order_refreshes.pop(0)
        return self.order_refreshes[0]

    def positions(self):
        return list(self._positions)

    def placeOrder(self, contract, order):
        trade = super().placeOrder(contract, order)
        if getattr(order, "orderRef", "") == "aegis_flatten":
            self.actions.append(str(order.action))
            self._positions = []
        return trade


class FakeStreamingIB(FakeOrderIB):
    def __init__(self) -> None:
        super().__init__()
        self.market_data_contracts = []
        self.cancelled_market_data_contracts = []
        self.ticker = SimpleNamespace(bid=3500.0, ask=3500.1)
        self.market_data_types = []

    def reqMarketDataType(self, market_data_type):
        self.market_data_types.append(market_data_type)

    def reqMktData(self, contract, genericTickList, snapshot, regulatorySnapshot):
        self.market_data_contracts.append(contract)
        assert genericTickList == ""
        assert snapshot is False
        assert regulatorySnapshot is False
        return self.ticker

    def cancelMktData(self, contract):
        self.cancelled_market_data_contracts.append(contract)


def connected_engine(fake: FakeIB) -> IBKREngine:
    engine = IBKREngine({"ib_port": 4002, "ib_client_id": 7, "allow_live": False})
    engine._ib = fake
    return engine


def connected_order_engine(fake: FakeOrderIB) -> IBKREngine:
    engine = connected_engine(fake)
    engine._contracts["EURUSD"] = object()
    return engine


def bracket_request() -> OrderRequest:
    return OrderRequest(
        symbol="EURUSD",
        side="buy",
        quantity=20_000,
        stop_loss=1.15380,
        take_profit=1.15460,
        client_tag="test_bracket",
    )


def connected_mgc_order_engine(fake: FakeOrderIB, *, sec_type: str) -> IBKREngine:
    engine = IBKREngine(
        {
            "ib_port": 4002,
            "ib_client_id": 7,
            "allow_live": False,
            "ib_futures_exchange": "COMEX",
            "ib_futures_expiry": "202610",
            "contract_multiplier": 10,
            "tick_size": 0.1,
        }
    )
    engine._ib = fake
    engine._contracts["MGC:202610"] = SimpleNamespace(
        secType=sec_type,
        symbol="MGC",
        localSymbol="MGCV6",
        conId=744880158,
        exchange="COMEX",
        currency="USD",
        lastTradeDateOrContractMonth="20261028",
        multiplier="10",
    )
    return engine


def test_pending_cancel_is_not_displayed_as_working():
    assert is_working_status("Submitted")
    assert is_working_status("PreSubmitted")
    assert not is_working_status("PendingCancel")
    assert not is_working_status("Cancelled")


def test_account_uses_cached_values_without_summary_subscription():
    fake = FakeIB()
    snapshot = connected_engine(fake).account()
    assert snapshot.equity == 250_000.0
    assert snapshot.available_funds == 249_000.0
    assert fake.account_summary_calls == 0


def test_bracket_sets_explicit_tif_and_atomic_transmit_chain():
    fake = FakeOrderIB()
    result = connected_order_engine(fake).place_order(bracket_request())
    parent, take_profit, stop_loss = fake.placed_orders
    assert [order.tif for order in (parent, take_profit, stop_loss)] == ["GTC", "GTC", "GTC"]
    assert [order.transmit for order in (parent, take_profit, stop_loss)] == [False, False, True]
    assert take_profit.parentId == parent.orderId == stop_loss.parentId
    assert result.ok


def test_cancelled_parent_returns_failure_and_cancels_complete_chain():
    fake = FakeOrderIB(parent_status="Cancelled")
    result = connected_order_engine(fake).place_order(bracket_request())
    assert not result.ok
    assert fake.cancelled_order_ids == {int(order.orderId) for order in fake.placed_orders}


def test_inactive_protective_child_cancels_the_complete_bracket():
    fake = FakeOrderIB(child_status="Inactive")
    result = connected_order_engine(fake).place_order(bracket_request())
    assert not result.ok
    assert "child" in result.message.lower()
    assert fake.cancelled_order_ids == {int(order.orderId) for order in fake.placed_orders}


def test_continuous_mgc_contract_is_refused_before_order_submission():
    fake = FakeOrderIB()
    engine = connected_mgc_order_engine(fake, sec_type="CONTFUT")
    result = engine.place_order(
        OrderRequest(symbol="MGC", side="buy", quantity=1, take_profit=3501.0, stop_loss=3499.0)
    )
    assert not result.ok
    assert "continuous" in result.message.lower()
    assert fake.placed_orders == []


def test_contract_metadata_surfaces_mgc_execution_identity():
    engine = connected_mgc_order_engine(FakeOrderIB(), sec_type="FUT")
    assert engine.contract_metadata("MGC") == {
        "symbol": "MGC",
        "local_symbol": "MGCV6",
        "con_id": 744880158,
        "sec_type": "FUT",
        "expiry": "20261028",
        "exchange": "COMEX",
        "currency": "USD",
        "multiplier": 10.0,
        "tick_size": 0.1,
    }


def test_mgc_market_data_uses_one_persistent_subscription_then_cancels_it():
    fake = FakeStreamingIB()
    engine = connected_mgc_order_engine(fake, sec_type="FUT")
    subscription = engine.subscribe_quote("MGC")
    assert subscription.ticker is fake.ticker
    assert len(fake.market_data_contracts) == 1
    engine.cancel_quote(subscription)
    assert fake.cancelled_market_data_contracts == fake.market_data_contracts


def test_shadow_subscription_explicitly_requests_delayed_market_data():
    fake = FakeStreamingIB()
    engine = connected_mgc_order_engine(fake, sec_type="FUT")
    engine.cfg["ib_market_data_type"] = 3
    engine.subscribe_quote("MGC")
    assert fake.market_data_types == [3]


def test_cancel_all_waits_until_no_working_or_cancelling_orders():
    fake = FakeLifecycleIB(
        order_refreshes=[
            [trade_with_status("Submitted", 301)],
            [trade_with_status("PendingCancel", 301)],
            [],
        ]
    )
    result = connected_order_engine(fake).cancel_all_orders(timeout_s=0.1, poll_s=0)
    assert result.ok
    assert fake.global_cancel_calls == 1
    assert fake.order_refreshes == [[]]


def test_flatten_cancels_closes_cancels_and_verifies():
    fake = FakeLifecycleIB(position_qty=20_000)
    engine = connected_order_engine(fake)
    result = engine.flatten_positions("EURUSD", timeout_s=0.1, poll_s=0)
    assert result.ok
    assert fake.actions == ["global_cancel", "SELL", "global_cancel"]
    assert engine.positions("EURUSD") == []


if __name__ == "__main__":
    test_pending_cancel_is_not_displayed_as_working()
    test_account_uses_cached_values_without_summary_subscription()
    test_bracket_sets_explicit_tif_and_atomic_transmit_chain()
    test_cancelled_parent_returns_failure_and_cancels_complete_chain()
    test_cancel_all_waits_until_no_working_or_cancelling_orders()
    test_flatten_cancels_closes_cancels_and_verifies()
    print("OK")
