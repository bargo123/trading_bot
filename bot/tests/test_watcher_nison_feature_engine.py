from aegis.research.watcher_feature_engine import enrich_watcher_state


def test_quote_history_derives_causal_three_line_break_state():
    history = []
    closes = [1.1000, 1.1005, 1.1010, 1.1015, 1.1018]
    for index, closing in enumerate(closes):
        start = index * 15.0
        opening = closes[index - 1] if index else closing - 0.0001
        for offset, value in ((1.0, opening), (5.0, closing)):
            history.append({
                "time": start + offset,
                "bid": value - 0.00002,
                "ask": value + 0.00002,
                "mid": value,
            })

    state = enrich_watcher_state(
        {"symbol": "EURUSD", "side": "BUY"},
        {"time": 80.0, "bid": 1.10178, "ask": 1.10182, "mid": 1.10180},
        symbol_history=history,
    )

    assert state["nison_three_line_direction"] == "up"
    assert state["nison_three_line_consecutive"] >= 3
    assert state["nison_three_line_confirmation"] == "confirmed"
    assert state["nison_data_provenance"] == "causal_price_filtered_quote_bar_proxy"
    assert state["quote_history_future_excluded"] is False
