#!/usr/bin/env python3
"""Future-dated quotes must be rejected, not treated as perfectly fresh.

``quote_age_s`` clamps at zero, so a tick stamped in the future reported an age of
0.0s and passed the staleness gate. Broker clock skew or corrupt tick data would
then price a real order.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aegis.oms import OrderRequest, oms_allows, quote_age_s, quote_future_skew_s

try:  # Quote lives with the engines in this tree.
    from aegis.engines import Quote
except ImportError:  # pragma: no cover
    from aegis.engines.base import Quote  # type: ignore

NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)
CFG = {
    "oms_pretrade": True,
    "max_quote_age_s": 5.0,
    "mt5_max_lots": 0.1,
    "max_positions": 40,
}


def _quote(offset_s: float) -> Quote:
    return Quote(symbol="EURUSD", bid=1.10000, ask=1.10002, time=NOW + timedelta(seconds=offset_s))


def _req() -> OrderRequest:
    return OrderRequest(symbol="EURUSD", side="buy", quantity=0.01)


def test_fresh_quote_is_allowed():
    ok, reason = oms_allows(_req(), _quote(0.0), CFG, now=NOW)
    assert ok, reason


def test_stale_quote_is_rejected():
    ok, reason = oms_allows(_req(), _quote(-30.0), CFG, now=NOW)
    assert not ok
    assert reason == "stale_quote"


def test_future_quote_is_rejected():
    """The regression: a tick 60s in the future used to report age 0.0 and pass."""
    quote = _quote(60.0)
    assert quote_age_s(quote, NOW) == 0.0, "age is clamped, which is why the gate missed this"
    assert quote_future_skew_s(quote, NOW) == pytest.approx(60.0)
    ok, reason = oms_allows(_req(), quote, CFG, now=NOW)
    assert not ok
    assert reason == "future_quote"


def test_small_clock_jitter_inside_tolerance_is_allowed():
    ok, reason = oms_allows(_req(), _quote(2.0), CFG, now=NOW)
    assert ok, reason


def test_future_skew_tolerance_is_configurable_and_defaults_to_max_age():
    quote = _quote(8.0)
    # Default tolerance mirrors max_quote_age_s (5s), so 8s ahead is rejected.
    assert oms_allows(_req(), quote, CFG, now=NOW)[1] == "future_quote"
    # An explicit wider tolerance permits it.
    loose = {**CFG, "max_quote_future_skew_s": 30.0}
    assert oms_allows(_req(), quote, loose, now=NOW)[0]
    # Zero disables the check.
    off = {**CFG, "max_quote_future_skew_s": 0}
    assert oms_allows(_req(), quote, off, now=NOW)[0]


def test_missing_timestamp_is_still_infinitely_stale():
    quote = Quote(symbol="EURUSD", bid=1.10000, ask=1.10002, time=None)
    assert quote_age_s(quote, NOW) == float("inf")
    assert quote_future_skew_s(quote, NOW) == 0.0
    ok, reason = oms_allows(_req(), quote, CFG, now=NOW)
    assert not ok
    assert reason == "stale_quote"


def test_naive_timestamps_are_treated_as_utc():
    naive_future = Quote(symbol="EURUSD", bid=1.10000, ask=1.10002, time=datetime(2026, 8, 19, 12, 1, 0))
    assert quote_future_skew_s(naive_future, NOW) == pytest.approx(60.0)


def test_crossed_quote_still_rejected_ahead_of_age_checks():
    crossed = Quote(symbol="EURUSD", bid=1.10005, ask=1.10000, time=NOW)
    ok, reason = oms_allows(_req(), crossed, CFG, now=NOW)
    assert not ok
    assert reason == "crossed_quote"
