from aegis.research.watcher_algorithms import evaluate_module


def _ratio_state(**overrides):
    state = {
        "side": "BUY",
        "chan_ratio_bid_size": 900.0,
        "chan_ratio_ask_size": 100.0,
        "chan_ratio_imbalance_min": 4.0,
        "chan_ratio_spread_ticks": 2.0,
        "chan_ratio_tick_size": 0.0001,
        "chan_ratio_round_trip_commission_per_unit": 0.00005,
        "chan_ratio_fill_model": "pro-rata",
        "chan_ratio_data_provenance": "observed",
    }
    state.update(overrides)
    return state


def _ticking_state(**overrides):
    state = {
        "side": "BUY",
        "chan_ticking_spread_ticks": 4.0,
        "chan_ticking_tick_size": 0.0001,
        "chan_ticking_round_trip_commission_per_unit": 0.00005,
        "chan_ticking_price_pressure": "buy",
        "chan_ticking_order_priority": "observed",
        "chan_ticking_data_provenance": "measured",
    }
    state.update(overrides)
    return state


def test_chan_ratio_trade_requires_observed_imbalance_and_supports_both_sides():
    buy = evaluate_module("chan_ratio_trade", _ratio_state())
    sell = evaluate_module(
        "chan_ratio_trade",
        _ratio_state(side="SELL", chan_ratio_bid_size=100.0, chan_ratio_ask_size=900.0),
    )

    assert buy["view"] == "BUY"
    assert buy["chan_ratio_assessment"] == "BUY_PRESSURE_RATIO_TRADE"
    assert sell["view"] == "SELL"
    assert sell["chan_ratio_assessment"] == "SELL_PRESSURE_RATIO_TRADE"
    assert buy["execution_authority"] is False


def test_chan_ratio_trade_rejects_non_prorata_or_unmeasured_inputs():
    non_prorata = evaluate_module("chan_ratio_trade", _ratio_state(chan_ratio_fill_model="price-time"))
    synthetic = evaluate_module("chan_ratio_trade", _ratio_state(chan_ratio_data_provenance="synthetic"))

    assert non_prorata["view"] == "WAIT"
    assert "pro-rata" in " ".join(non_prorata["reasons"])
    assert synthetic["view"] == "MISSING_DATA"


def test_chan_ticking_quote_matching_requires_more_than_two_ticks_and_cost_room():
    buy = evaluate_module("chan_ticking_quote_matching", _ticking_state())
    sell = evaluate_module(
        "chan_ticking_quote_matching",
        _ticking_state(side="SELL", chan_ticking_price_pressure="sell"),
    )
    too_narrow = evaluate_module(
        "chan_ticking_quote_matching",
        _ticking_state(chan_ticking_spread_ticks=2.0),
    )

    assert buy["view"] == "BUY"
    assert buy["chan_ticking_assessment"] == "BUY_QUOTE_MATCH"
    assert sell["view"] == "SELL"
    assert sell["chan_ticking_assessment"] == "SELL_QUOTE_MATCH"
    assert too_narrow["view"] == "WAIT"


def test_chan_ticking_quote_matching_does_not_hide_commission_failure():
    result = evaluate_module(
        "chan_ticking_quote_matching",
        _ticking_state(chan_ticking_round_trip_commission_per_unit=0.00025),
    )

    assert result["view"] == "WAIT"
    assert result["chan_ticking_assessment"] == "COST_HURDLE_FAILED"


def test_chan_hft_quote_data_requires_executable_bid_ask_last_history():
    result = evaluate_module(
        "chan_hft_quote_data_requirements",
        {
            "chan_hft_bid_quotes": [1.1000, 1.1001, 1.1002],
            "chan_hft_ask_quotes": [1.1002, 1.1003, 1.1004],
            "chan_hft_last_quotes": [1.1001, 1.1002, 1.1003],
            "chan_hft_order_book_available": False,
            "chan_hft_quote_data_provenance": "observed bid ask last replay",
        },
    )

    assert result["applicability"] == "APPLICABLE"
    assert result["chan_hft_data_action"] == "QUOTE_DATA_READY_WITH_BOOK_LIMITATION"
    assert result["chan_hft_quote_observation_n"] == 3
    assert result["directional_claim"] is False
    assert result["execution_authority"] is False

    missing_last = evaluate_module(
        "chan_hft_quote_data_requirements",
        {
            "chan_hft_bid_quotes": [1.1000, 1.1001, 1.1002],
            "chan_hft_ask_quotes": [1.1002, 1.1003, 1.1004],
            "chan_hft_order_book_available": True,
            "chan_hft_quote_data_provenance": "observed",
        },
    )
    assert missing_last["applicability"] == "MISSING_DATA"


def test_chan_bulk_volume_classification_separates_entry_and_position_exit_rules():
    buy = evaluate_module(
        "chan_bulk_volume_order_flow",
        {
            "side": "BUY",
            "chan_bvc_delta_price": 0.002,
            "chan_bvc_delta_price_sigma": 0.001,
            "chan_bvc_volume": 500.0,
            "chan_bvc_entry_fraction": 0.95,
            "chan_bvc_exit_fraction": 0.5,
            "chan_bvc_position": "flat",
            "chan_bvc_data_provenance": "observed volume-bar replay",
        },
    )
    sell_exit = evaluate_module(
        "chan_bulk_volume_order_flow",
        {
            "side": "SELL",
            "chan_bvc_delta_price": 0.002,
            "chan_bvc_delta_price_sigma": 0.001,
            "chan_bvc_volume": 500.0,
            "chan_bvc_entry_fraction": 0.95,
            "chan_bvc_exit_fraction": 0.5,
            "chan_bvc_position": "short",
            "chan_bvc_data_provenance": "observed volume-bar replay",
        },
    )

    assert buy["view"] == "BUY"
    assert buy["chan_bvc_action"] == "BUY_ENTRY"
    assert buy["chan_bvc_buy_fraction"] > 0.95
    assert sell_exit["view"] == "WAIT"
    assert sell_exit["chan_bvc_action"] == "EXIT_SHORT"
    assert buy["execution_authority"] is False
