from aegis.research.watcher_feature_engine import enrich_watcher_state


def test_quote_history_derives_causal_ponsi_pennant_without_active_bar_lookahead():
    history = []
    bars = [
        (1.1000, 1.1003, 1.0999, 1.1002),
        (1.1002, 1.1010, 1.1001, 1.1009),
        (1.1009, 1.1016, 1.1008, 1.1015),
        (1.1015, 1.1017, 1.1013, 1.10155),
        (1.10155, 1.10165, 1.1014, 1.1015),
        (1.1015, 1.1024, 1.1015, 1.1024),
    ]
    for index, (opening, high, low, closing) in enumerate(bars):
        start = index * 15.0
        for offset, value in ((1.0, opening), (4.0, high), (7.0, low), (10.0, closing)):
            history.append({
                "time": start + offset,
                "bid": value - 0.00002,
                "ask": value + 0.00002,
                "mid": value,
            })

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "session": "london"},
        {"time": 95.0, "bid": 1.10238, "ask": 1.10242, "mid": 1.10240},
        symbol_history=history,
    )

    assert state["ponsi_pattern"] == "pennant"
    assert state["ponsi_flagpole_direction"] == "up"
    assert state["ponsi_breakout_direction"] == "up"
    assert state["ponsi_breakout_confirmation"] == "confirmed"
    assert state["ponsi_data_provenance"] == "causal_completed_quote_bar_proxy"
    assert state["feature_provenance"]["ponsi"] == "causal_completed_quote_bar_proxy"
    assert state["quote_history_future_excluded"] is False


def test_quote_history_derives_ponsi_price_action_entry_location_from_completed_reaction():
    history = []
    bars = [
        (1.1010, 1.1012, 1.1008, 1.1010),
        (1.1005, 1.1007, 1.1002, 1.1004),
        (1.1003, 1.1005, 1.1000, 1.1002),
        (1.1002, 1.1004, 1.1000, 1.1001),
        (1.1000, 1.1004, 1.0998, 1.10015),
    ]
    for index, (opening, high, low, closing) in enumerate(bars):
        start = index * 15.0
        for offset, value in ((1.0, opening), (4.0, high), (7.0, low), (10.0, closing)):
            history.append({
                "time": start + offset,
                "bid": value - 0.00002,
                "ask": value + 0.00002,
                "mid": value,
            })

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY", "session": "london"},
        {"time": 80.0, "bid": 1.10013, "ask": 1.10017, "mid": 1.10015},
        symbol_history=history,
    )

    assert state["ponsi_price_level"] == "support"
    assert state["ponsi_price_action"] == "rejection"
    assert state["ponsi_entry_order_location"] == "above support"
    assert state["ponsi_level_test_count"] >= 1
    assert state["ponsi_approach_speed"] == "measured"
