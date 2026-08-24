from __future__ import annotations

from aegis.engines.base import PositionSnapshot
from scripts.run_broker_paper import (
    confirmed_position_geometry,
    close_ticket_confirmed,
    normalize_protective_stops,
    persist_confirmed_firehose_basket,
)


def test_normalize_protective_stops_buy_respects_broker_min_distance():
    sl, tp = normalize_protective_stops(
        side="buy",
        entry=1.10020,
        sl=1.10015,
        tp=1.10025,
        spec={"point": 0.00001, "trade_stops_level": 20, "trade_freeze_level": 0},
        fallback_step=0.0001,
    )
    assert sl == 1.10000
    assert tp == 1.10040


def test_normalize_protective_stops_sell_respects_broker_min_distance():
    sl, tp = normalize_protective_stops(
        side="sell",
        entry=159.500,
        sl=159.505,
        tp=159.495,
        spec={"point": 0.001, "trade_stops_level": 10, "trade_freeze_level": 0},
        fallback_step=0.01,
    )
    assert sl == 159.510
    assert tp == 159.490


def test_close_ticket_confirmed_rejects_ok_response_when_ticket_remains_open():
    """A pending or partial close must not release Firehose lifecycle state."""
    positions = [
        PositionSnapshot(
            symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.1, ticket="T1",
        )
    ]

    assert close_ticket_confirmed(positions, "T1") is False


def test_close_ticket_confirmed_accepts_absent_exact_ticket():
    positions = [
        PositionSnapshot(
            symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.1, ticket="T2",
        )
    ]

    assert close_ticket_confirmed(positions, "T1") is True


def _contract(symbol: str) -> dict[str, float | str]:
    return {
        "name": symbol,
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
    }


def _basket_metadata(symbol: str = "EURUSD") -> dict[str, object]:
    return {
        "basket_id": "basket-1001",
        "hypothesis_id": "hyp-1",
        "family": "breakout",
        "symbol": symbol,
        "side": "buy",
        "trigger_id": "trigger-1",
        "entry_price": 1.1000,
        "stop_loss": 1.09985,
        "risk_budget": 0.15,
        "clip_cap": 1,
        "regime": "trend",
        "session": "london",
        "cost_evidence": {"spread_usd": 0.01, "commission_usd": 0.02},
    }


def test_confirmed_fill_persists_exact_one_clip_basket_in_symbol_store(tmp_path):
    result = persist_confirmed_firehose_basket(
        root=tmp_path,
        ticket_id="T1",
        metadata=_basket_metadata(),
        contract=_contract("EURUSD"),
        volume=0.01,
    )

    assert result == {
        "status": "PERSISTED",
        "basket_id": "basket-1001",
        "ticket_id": "T1",
        "initial_risk_usd": 0.15,
        "entry_price": 1.1,
        "stop_loss": 1.09985,
    }
    assert (tmp_path / "intel" / "firehose_baskets" / "EURUSD.json").is_file()


def test_unconfirmed_fill_does_not_create_basket_store(tmp_path):
    result = persist_confirmed_firehose_basket(
        root=tmp_path,
        ticket_id=None,
        metadata=_basket_metadata(),
        contract=_contract("EURUSD"),
        volume=0.01,
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "unconfirmed_fill"}
    assert not (tmp_path / "intel" / "firehose_baskets").exists()


def test_invalid_symbol_contract_does_not_persist_basket(tmp_path):
    result = persist_confirmed_firehose_basket(
        root=tmp_path,
        ticket_id="T1",
        metadata=_basket_metadata(),
        contract=_contract("GBPUSD"),
        volume=0.01,
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    assert not (tmp_path / "intel" / "firehose_baskets").exists()


def test_confirmed_position_geometry_uses_broker_average_and_stop():
    geometry = confirmed_position_geometry(
        PositionSnapshot(
            symbol="EURUSD", side="buy", quantity=0.01,
            avg_price=1.10012, stop_loss=1.09985, ticket="T1",
        ),
    )

    assert geometry == {"entry_price": 1.10012, "stop_loss": 1.09985, "volume": 0.01}


def test_confirmed_position_geometry_rejects_missing_broker_stop():
    geometry = confirmed_position_geometry(
        PositionSnapshot(symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.10012, ticket="T1"),
    )

    assert geometry == {"status": "NO_EVIDENCE", "reason": "missing_confirmed_geometry"}
