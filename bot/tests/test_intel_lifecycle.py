from aegis.engines import PositionSnapshot
from aegis.intel.lifecycle import exposure_snapshot, ingest_deals, new_cursor, pretrade_ok


def test_pretrade_and_exposure_snapshot():
    positions = [
        PositionSnapshot("EURUSD", "buy", 0.01, 1.10),
        PositionSnapshot("GBPUSD", "buy", 0.01, 1.25),
    ]
    snap = exposure_snapshot(positions)
    assert snap["n"] == 2
    assert snap["currency_direction"]["USD"] == -2
    ok, reason = pretrade_ok(
        positions=positions,
        symbol="AUDUSD",
        side="buy",
        quantity=0.01,
        avg_price=0.65,
        cfg={"max_positions": 40, "max_currency_direction_positions": 10, "max_per_symbol": 5},
    )
    assert ok, reason


def test_ingest_deals_is_idempotent():
    cursor = new_cursor()
    deals = [
        {
            "ticket": "11",
            "order": "21",
            "position": "30",
            "symbol": "EURUSD",
            "entry": 1,
            "profit": 0.08,
            "commission": -0.02,
            "swap": 0.0,
            "comment": "",
            "reason": 5,
            "time": "2026-08-14T10:01:00.123Z",
        }
    ]
    first = ingest_deals(deals, cursor)
    second = ingest_deals(deals, cursor)
    assert first
    assert first[0]["is_exit"] is True
    assert second == []
