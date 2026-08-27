"""Offline tests for MT5Engine using a fake MetaTrader5 module."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.engines.mt5 import MT5Engine
from aegis.engines.base import OrderRequest
from aegis.engines import create_engine


class FakeTick(SimpleNamespace):
    pass


class FakeInfo(SimpleNamespace):
    pass


class FakeResult(SimpleNamespace):
    pass


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_REMOVE = 8
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TIME_GTC = 0
    TIMEFRAME_M1 = 1
    TIMEFRAME_H1 = 16385
    TIMEFRAME_D1 = 16408

    def __init__(self, *, trade_mode: int = 0, initialize_ok: bool = True, logged_in: bool = True) -> None:
        self.trade_mode = trade_mode
        self.initialize_ok = initialize_ok
        self.logged_in = logged_in
        self.shutdown_calls = 0
        self.login_calls = 0
        self.selected: list[str] = []
        self.pending: dict[int, SimpleNamespace] = {}
        self.positions: list[SimpleNamespace] = []
        self.sends: list[dict] = []
        self.next_ticket = 100
        self.symbol = FakeInfo(
            name="EURUSD",
            visible=True,
            filling_mode=2,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=100.0,
            digits=5,
            point=0.00001,
            trade_tick_size=0.00001,
            trade_contract_size=100000.0,
            spread=20,
            trade_stops_level=0,
            trade_freeze_level=0,
            swap_long=0.0,
            swap_short=0.0,
            trade_mode=0,
        )
        self.tick = FakeTick(bid=1.10000, ask=1.10020, time=1_700_000_000)

    def initialize(self, **kwargs):
        return self.initialize_ok

    def shutdown(self):
        self.shutdown_calls += 1

    def login(self, login, password="", server=""):
        self.login_calls += 1
        self.logged_in = True
        return True

    def last_error(self):
        return (-1, "fake")

    def account_info(self):
        if not self.logged_in:
            return None
        return SimpleNamespace(
            login=555,
            equity=10_000.0,
            currency="USD",
            margin_free=9_500.0,
            trade_mode=self.trade_mode,
            server="Demo-Server",
            company="FakeBroker",
            balance=10_000.0,
            leverage=100,
            trade_expert=True,
            trade_allowed=True,
        )

    def terminal_info(self):
        return SimpleNamespace(trade_allowed=True, connected=True)

    def symbol_info(self, name):
        if str(name).upper() in {"EURUSD", "USDJPY"}:
            attrs = vars(self.symbol).copy()
            attrs["name"] = str(name)
            return SimpleNamespace(**attrs)
        return None

    def symbols_get(self):
        return [self.symbol]

    def symbol_select(self, name, enable=True):
        self.selected.append(name)
        return True

    def symbol_info_tick(self, name):
        return self.tick

    def copy_ticks_range(self, name, start, end, flags):
        return [
            {
                "time": 1_700_000_000,
                "bid": 1.10000,
                "ask": 1.10020,
                "last": 0.0,
                "volume": 0.0,
                "flags": 0,
            }
        ]

    def copy_rates_from_pos(self, name, tf, start, count):
        rows = []
        base = 1_700_000_000
        for i in range(min(int(count), 60)):
            rows.append(
                {
                    "time": base + i * 3600,
                    "open": 1.1,
                    "high": 1.11,
                    "low": 1.09,
                    "close": 1.105,
                    "tick_volume": 10,
                }
            )
        return rows

    def positions_get(self, symbol=None):
        if symbol:
            return [p for p in self.positions if p.symbol == symbol]
        return list(self.positions)

    def orders_get(self, symbol=None):
        vals = list(self.pending.values())
        if symbol:
            return [o for o in vals if str(getattr(o, "symbol", "")) == str(symbol)]
        return vals

    def history_deals_get(self, start, end, group=None):
        return list(getattr(self, "deals", []) or [])

    def history_orders_get(self, start, end, group=None):
        return list(getattr(self, "orders_hist", []) or [])

    def order_send(self, request):
        self.sends.append(dict(request))
        action = request.get("action")
        ticket = self.next_ticket
        self.next_ticket += 1
        if action == self.TRADE_ACTION_PENDING:
            self.pending[ticket] = SimpleNamespace(ticket=ticket, symbol=request["symbol"], volume=request["volume"])
            return FakeResult(retcode=10008, order=ticket, comment="placed", price=request.get("price", 0), deal=0)
        if action == self.TRADE_ACTION_REMOVE:
            oid = int(request["order"])
            self.pending.pop(oid, None)
            return FakeResult(retcode=10009, order=oid, comment="cancelled", price=0, deal=0)
        if action == self.TRADE_ACTION_DEAL and request.get("position"):
            pid = int(request["position"])
            self.positions = [p for p in self.positions if int(p.ticket) != pid]
            return FakeResult(retcode=10009, order=ticket, comment="closed", price=request.get("price", 0), deal=ticket)
        if action == self.TRADE_ACTION_DEAL:
            self.positions.append(
                SimpleNamespace(
                    ticket=ticket,
                    symbol=request["symbol"],
                    volume=request["volume"],
                    type=0 if request["type"] == self.ORDER_TYPE_BUY else 1,
                    price_open=request.get("price", 0),
                    profit=0.0,
                )
            )
            return FakeResult(retcode=10009, order=ticket, comment="done", price=request.get("price", 0), deal=ticket)
        return FakeResult(retcode=10004, order=0, comment="unsupported", price=0, deal=0)

    def order_calc_margin(self, order_type, symbol, volume, price):
        return 30.0


def _engine(api: FakeMT5, **cfg) -> MT5Engine:
    base = {"allow_live": False, "mode": "mt5_demo", "mt5_max_lots": 0.10}
    base.update(cfg)
    return MT5Engine(base, api=api)


def test_factory_mt5():
    eng = create_engine({"engine": "mt5", "allow_live": False})
    assert isinstance(eng, MT5Engine)
    assert eng.name == "mt5"


def test_connect_demo_ok():
    api = FakeMT5(trade_mode=0)
    eng = _engine(api)
    eng.connect()
    acct = eng.account()
    assert acct.is_paper
    assert acct.account_id == "555"
    assert acct.equity == 10_000.0
    eng.disconnect()
    assert api.shutdown_calls == 0
    eng2 = _engine(api)
    eng2.connect()
    eng2.disconnect(shutdown=True)
    assert api.shutdown_calls == 1


def test_connect_live_refused():
    api = FakeMT5(trade_mode=2)
    eng = _engine(api)
    try:
        eng.connect()
        raise AssertionError("expected live refuse")
    except RuntimeError as exc:
        assert "non-demo" in str(exc).lower() or "refusing" in str(exc).lower()
    assert api.shutdown_calls == 1


def test_connect_not_logged_in():
    api = FakeMT5(logged_in=False)
    eng = _engine(api)
    try:
        eng.connect()
        raise AssertionError("expected login error")
    except RuntimeError as exc:
        assert "not logged in" in str(exc).lower()


def test_resolve_broker_suffix():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    q = eng.quote("EURUSD.gc")
    assert q.symbol == "EURUSD"
    assert q.bid == 1.1


def test_quote_and_bars():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    q = eng.quote("EURUSD")
    assert q.bid == 1.1
    assert q.ask == 1.10020
    bars = eng.bars("EURUSD", "1h", 5)
    assert len(bars) >= 50
    assert bars[0].close == 1.105


def test_bars_normalize_mt5_period_timestamps_to_minute_boundaries():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()

    bars = eng.bars("EURUSD", "1m", 1)

    assert bars
    assert all(bar.time.second == 0 and bar.time.microsecond == 0 for bar in bars)


def test_units_quantity_refused():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    res = eng.place_order(OrderRequest(symbol="EURUSD", side="buy", quantity=20000, kind="market"))
    assert not res.ok
    assert "lots" in res.message.lower()


def test_place_and_cancel_limit():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    res = eng.place_and_cancel_limit("EURUSD", "buy", 0.01, 1.05)
    assert res.ok
    assert not api.pending
    assert any(s.get("action") == api.TRADE_ACTION_PENDING for s in api.sends)
    assert any(s.get("action") == api.TRADE_ACTION_REMOVE for s in api.sends)


def test_flatten_closes_position():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    api.positions.append(
        SimpleNamespace(ticket=7, symbol="EURUSD", volume=0.01, type=0, price_open=1.1, profit=-0.5)
    )
    res = eng.flatten_positions("EURUSD")
    assert res.ok
    assert not api.positions


def test_flatten_one_symbol_leaves_other_pending():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    api.positions.append(
        SimpleNamespace(ticket=7, symbol="EURUSD", volume=0.01, type=0, price_open=1.1, profit=-0.5)
    )
    api.pending[88] = SimpleNamespace(ticket=88, symbol="GBPUSD", volume=0.01)
    res = eng.flatten_positions("EURUSD")
    assert res.ok
    assert not api.positions
    assert 88 in api.pending


def test_round_trip_spread_usd():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    usd = eng.round_trip_spread_usd("EURUSD", 0.01)
    # 0.01 lots * 100000 contract * 0.00020 spread
    assert abs(usd - 0.20) < 1e-9


def test_copy_ticks_and_spec():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    ticks = eng.copy_ticks("EURUSD", lookback_seconds=10)
    assert len(ticks) == 1
    spec = eng.symbol_spec("EURUSD")
    assert spec["trade_contract_size"] == 100000.0
    assert abs(spec["spread_price"] - 0.00020) < 1e-9


def test_max_lots_cap():
    api = FakeMT5()
    eng = _engine(api, mt5_max_lots=0.02)
    eng.connect()
    res = eng.place_order(OrderRequest(symbol="EURUSD", side="buy", quantity=0.05, kind="market"))
    assert not res.ok
    assert "mt5_max_lots" in res.message


def test_place_order_uses_emergency_broker_geometry_not_virtual_target():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()
    res = eng.place_order(OrderRequest(
        symbol="EURUSD", side="buy", quantity=0.01, kind="market",
        stop_loss=1.09990, take_profit=1.10100,
        broker_stop_loss=1.09960, broker_take_profit=None,
    ))
    assert res.ok
    assert api.sends[-1]["sl"] == 1.0996
    assert api.sends[-1]["tp"] == 0.0


def test_history_deals_and_orders_readonly():
    api = FakeMT5()
    api.deals = [
        SimpleNamespace(
            ticket=9,
            order=8,
            symbol="EURUSD",
            type=0,
            volume=0.01,
            price=1.1,
            profit=0.12,
            commission=0.0,
            swap=0.0,
            fee=-0.01,
            entry=1,
            magic=1,
            comment="out",
            time=1_700_000_000,
            time_msc=1_700_000_000_000,
        )
    ]
    api.orders_hist = [
        SimpleNamespace(
            ticket=8,
            symbol="EURUSD",
            state=4,
            type=0,
            volume_initial=0.01,
            price_open=1.1,
            sl=1.09,
            tp=1.11,
            magic=1,
            comment="x",
            time_setup=1_700_000_000,
        )
    ]
    eng = _engine(api)
    eng.connect_readonly()
    eng._server_utc_offset_s = 3600
    deals = eng.history_deals(7)
    orders = eng.history_orders(7)
    assert deals[0]["profit"] == 0.12
    assert deals[0]["fee"] == -0.01
    assert deals[0]["time"] == "2023-11-14T21:13:20+00:00"
    assert deals[0]["time_msc"] == 1_699_996_400_000
    assert orders[0]["ticket"] == "8"
    assert api.shutdown_calls == 0


def test_order_margin_uses_broker_native_account_currency_calculation():
    api = FakeMT5()
    eng = _engine(api)
    eng.connect()

    assert eng.order_margin("USDJPY", "buy", 0.03, 159.38) == 30.0


def test_connect_readonly_live_does_not_shutdown():
    api = FakeMT5(trade_mode=2)
    eng = _engine(api)
    try:
        eng.connect_readonly()
        raise AssertionError("expected live refuse")
    except RuntimeError as exc:
        assert "non-demo" in str(exc).lower() or "refusing" in str(exc).lower()
    assert api.shutdown_calls == 0


def test_positions_include_ticket_sl_tp():
    api = FakeMT5()
    api.positions = [
        SimpleNamespace(
            ticket=42,
            symbol="EURUSD",
            volume=0.01,
            type=0,
            price_open=1.1,
            profit=0.01,
            sl=1.09,
            tp=1.11,
            time_msc=1_700_000_123_456,
        )
    ]
    eng = _engine(api)
    eng.connect_readonly()
    eng._server_utc_offset_s = 3600
    pos = eng.positions()
    assert pos[0].ticket == "42"
    assert pos[0].stop_loss == 1.09
    assert pos[0].take_profit == 1.11
    assert pos[0].opened_ts == 1_699_996_523.456
    assert api.shutdown_calls == 0


if __name__ == "__main__":
    test_factory_mt5()
    test_connect_demo_ok()
    test_connect_live_refused()
    test_connect_not_logged_in()
    test_resolve_broker_suffix()
    test_quote_and_bars()
    test_units_quantity_refused()
    test_place_and_cancel_limit()
    test_flatten_closes_position()
    test_flatten_one_symbol_leaves_other_pending()
    test_round_trip_spread_usd()
    test_copy_ticks_and_spec()
    test_max_lots_cap()
    test_history_deals_and_orders_readonly()
    test_connect_readonly_live_does_not_shutdown()
    test_positions_include_ticket_sl_tp()
    print("OK")
