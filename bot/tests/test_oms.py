"""Donadio OMS pre-trade + tick-to-trade. Not a 100% WR claim."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.engines.base import OrderRequest, Quote
from aegis.oms import (
    TickToTrade,
    close_attempt_blocked,
    is_market_closed_retcode,
    market_closed_backoff_until,
    oms_allows,
    open_attempt_blocked,
    quote_age_s,
    update_close_backoff,
)


def _q(*, bid=1.10000, ask=1.10010, age_s=0.4):
    now = datetime.now(timezone.utc)
    return Quote("EURUSD", bid, ask, now - timedelta(seconds=age_s)), now


def _req(**extra):
    base = dict(
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        kind="market",
        stop_loss=1.09700,
        take_profit=1.10020,
    )
    base.update(extra)
    return OrderRequest(**base)


def test_flags_off_do_not_block():
    q, now = _q()
    ok, reason = oms_allows(_req(), q, {}, now=now)
    assert ok and reason == ""


def test_oms_rejects_bad_qty_side_stops_and_stale():
    cfg = {"oms_pretrade": True, "mt5_max_lots": 0.1, "max_positions": 40, "max_quote_age_s": 5.0}
    q, now = _q()
    assert oms_allows(_req(quantity=0), q, cfg, now=now)[1] == "qty"
    assert oms_allows(_req(side="hold"), q, cfg, now=now)[1] == "side"
    assert oms_allows(_req(quantity=1.0), q, cfg, now=now)[1] == "max_lots"
    assert oms_allows(_req(), q, cfg, open_count=40, now=now)[1] == "max_positions"
    # buy SL above bid / TP below ask
    assert oms_allows(_req(stop_loss=1.10050), q, cfg, now=now)[1] == "stops"
    assert oms_allows(_req(take_profit=1.09990), q, cfg, now=now)[1] == "stops"
    stale, now2 = _q(age_s=12.0)
    assert oms_allows(_req(), stale, cfg, now=now2)[1] == "stale_quote"
    ok, reason = oms_allows(_req(), q, cfg, now=now)
    assert ok and reason == ""


def test_oms_sell_stops_must_be_above_ask():
    cfg = {"oms_pretrade": True, "max_quote_age_s": 5.0}
    q, now = _q()
    bad = _req(side="sell", stop_loss=1.09900, take_profit=1.09990)
    assert oms_allows(bad, q, cfg, now=now)[1] == "stops"
    good = _req(side="sell", stop_loss=1.10300, take_profit=1.09990)
    assert oms_allows(good, q, cfg, now=now)[0] is True


def test_oms_uses_explicit_broker_geometry_not_virtual_strategy_levels():
    cfg = {"oms_pretrade": True, "max_quote_age_s": 5.0}
    q, now = _q()
    # The virtual target is intentionally below the executable ask; it is
    # controller-owned and must not be treated as an MT5 TP. The emergency
    # broker stop is valid for the BUY and is the only level OMS should check.
    req = _req(
        stop_loss=1.10050,
        take_profit=1.09990,
        broker_stop_loss=1.09960,
        broker_take_profit=None,
    )
    ok, reason = oms_allows(req, q, cfg, now=now)
    assert ok, reason


def test_oms_still_rejects_invalid_explicit_broker_geometry():
    cfg = {"oms_pretrade": True, "max_quote_age_s": 5.0}
    q, now = _q()
    req = _req(
        stop_loss=1.09900,
        take_profit=1.10100,
        broker_stop_loss=1.10050,
    )
    ok, reason = oms_allows(req, q, cfg, now=now)
    assert not ok
    assert reason == "stops"


def test_quote_age_and_tick_to_trade_snapshot():
    q, now = _q(age_s=1.25)
    age = quote_age_s(q, now)
    assert 1.2 <= age <= 1.4
    clock = TickToTrade(n=16)
    clock.record_ms(4.0)
    clock.record_ms(8.0)
    clock.record_ms(12.0)
    clock.note_reject("stale_quote")
    clock.note_reject("stops")
    snap = clock.snapshot()
    assert snap["t2t_n"] == 3
    assert snap["t2t_p50_ms"] == 8.0
    assert snap["quote_stale"] == 1
    assert snap["oms_rejects"] == 1


def test_10018_is_market_closed_10019_is_not():
    assert is_market_closed_retcode("10018 Market closed")
    assert is_market_closed_retcode("flatten close failed: 10018 Market closed")
    assert is_market_closed_retcode("Market closed")
    assert not is_market_closed_retcode("10019 No money")
    assert not is_market_closed_retcode("flatten close failed: 10019 No money")
    assert not is_market_closed_retcode("10009 done")
    assert not is_market_closed_retcode("")


def test_friday_cutoff_10018_skips_until_sunday_open():
    friday = datetime(2026, 8, 14, 21, 12, tzinfo=timezone.utc)
    until = market_closed_backoff_until(friday)
    assert until == datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc)
    friday_ts = friday.timestamp()
    until_ts = update_close_backoff(0.0, "10018 Market closed", friday)
    assert close_attempt_blocked(friday_ts, until_ts)
    assert close_attempt_blocked(datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc).timestamp(), until_ts)
    assert not close_attempt_blocked(datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc).timestamp(), until_ts)


def test_weekday_10018_short_backoff_keeps_never_green_alive():
    wed = datetime(2026, 8, 12, 14, 30, tzinfo=timezone.utc)
    until = market_closed_backoff_until(wed)
    delta = (until - wed).total_seconds()
    assert 60 <= delta <= 1800
    assert until.date() == wed.date()
    assert update_close_backoff(0.0, "10019 No money", wed) == 0.0
    later = wed + timedelta(seconds=delta + 1)
    until_ts = update_close_backoff(0.0, "flatten close failed: 10018 Market closed", wed)
    assert close_attempt_blocked(wed.timestamp(), until_ts)
    assert not close_attempt_blocked(later.timestamp(), until_ts)


def test_open_10018_reuses_flatten_weekend_block_10019_does_not():
    """Firehose entries share flatten's 10018 clock; 10019 stays a margin skip."""
    friday = datetime(2026, 8, 14, 23, 58, tzinfo=timezone.utc)
    flatten_until = update_close_backoff(0.0, "flatten close failed: 10018 Market closed", friday)
    open_until = update_close_backoff(0.0, "10018 Market closed", friday)
    assert flatten_until == open_until
    assert open_attempt_blocked(friday.timestamp(), flatten_until)
    assert open_attempt_blocked(
        datetime(2026, 8, 16, 20, 59, tzinfo=timezone.utc).timestamp(), flatten_until
    )
    assert not open_attempt_blocked(
        datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc).timestamp(), flatten_until
    )
    assert update_close_backoff(flatten_until, "10019 No money", friday) == flatten_until
    assert update_close_backoff(0.0, "10019 No money", friday) == 0.0
    assert not is_market_closed_retcode("10019 No money")
    wed = datetime(2026, 8, 12, 14, 30, tzinfo=timezone.utc)
    weekday_until = update_close_backoff(0.0, "10018 Market closed", wed)
    later = wed + timedelta(seconds=901)
    assert open_attempt_blocked(wed.timestamp(), weekday_until)
    assert not open_attempt_blocked(later.timestamp(), weekday_until)


if __name__ == "__main__":
    test_flags_off_do_not_block()
    test_oms_rejects_bad_qty_side_stops_and_stale()
    test_oms_sell_stops_must_be_above_ask()
    test_quote_age_and_tick_to_trade_snapshot()
    test_10018_is_market_closed_10019_is_not()
    test_friday_cutoff_10018_skips_until_sunday_open()
    test_weekday_10018_short_backoff_keeps_never_green_alive()
    test_open_10018_reuses_flatten_weekend_block_10019_does_not()
    print("OK")
