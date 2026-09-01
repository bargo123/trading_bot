from __future__ import annotations

from datetime import datetime, timezone

from aegis.research.watcher_feature_engine import enrich_watcher_state


def _quote(timestamp: float, mid: float) -> dict[str, float]:
    return {
        "time": timestamp,
        "bid": mid - 0.00002,
        "ask": mid + 0.00002,
        "mid": mid,
    }


def test_price_in_time_context_uses_completed_london_ntz_and_current_breakout_only():
    day = datetime(2026, 8, 24, 7, 0, tzinfo=timezone.utc).timestamp()
    ntz_values = (1.1000, 1.0995, 1.1004, 1.1010, 1.1006, 1.1002)
    history = [_quote(day + index * 10 * 60, value) for index, value in enumerate(ntz_values)]
    now = day + 70 * 60
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "pit_anomalous_day": False},
        _quote(now, 1.1013),
        symbol_history=history,
    )

    assert state["pit_session"] == "london_after_0800_gmt"
    assert 10.0 <= state["pit_ntz_width_pips"] <= 30.0
    assert state["pit_breakout_direction"] == "up"
    assert state["pit_breakout_confirmation"] == "confirmed"
    assert state["pit_inside_ntz"] is False
    assert state["pit_data_provenance"] == "causal_session_range_quote_proxy"
    assert state["feature_provenance"]["price_in_time"] == "causal_session_range_quote_proxy"


def test_price_in_time_context_derives_opening_cross_session_and_asian_range_fields():
    day = datetime(2026, 8, 24, 7, 0, tzinfo=timezone.utc).timestamp()
    history = [
        _quote(day, 1.1000),
        _quote(day + 10 * 60, 1.0994),
        _quote(day + 50 * 60, 1.0998),
    ]
    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        _quote(day + 70 * 60, 1.1003),
        symbol_history=history,
    )

    assert state["pit_europe_open_price"] == 1.1
    assert state["pit_opening_price_relation"] == "above"
    assert state["pit_opening_cross_direction"] == "up"
    assert state["pit_session_window"] == "london_morning"
    assert state["pit_session_data_provenance"] == "observed GMT session clock"
    assert state["pit_asian_range_limit_pips"] == 40.0
    assert state["pit_anomaly_data_provenance"] == "not_observed"
