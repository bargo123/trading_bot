from __future__ import annotations

import pytest

from scripts.build_short_horizon_model import (
    research_usd_per_price_unit_by_symbol,
    select_research_symbols,
)


def test_select_research_symbols_preserves_configured_order_and_normalizes():
    configured = ["EURUSD", "GBPUSD", "USDJPY"]

    assert select_research_symbols(configured, ["usdjpy", "eurusd"]) == [
        "EURUSD",
        "USDJPY",
    ]


def test_select_research_symbols_rejects_unknown_filter():
    with pytest.raises(ValueError, match="symbol filter did not match"):
        select_research_symbols(["EURUSD"], ["XAUUSD"])


def test_research_usd_conversion_uses_conservative_tick_value_at_minimum_lot():
    class Engine:
        @staticmethod
        def symbol_spec(symbol):
            assert symbol == "EURUSD"
            return {
                "trade_tick_value": 0.9,
                "trade_tick_value_profit": 0.8,
                "trade_tick_value_loss": -1.0,
                "trade_tick_size": 0.00001,
                "volume_min": 0.01,
                "trade_contract_size": 100000.0,
            }

    result = research_usd_per_price_unit_by_symbol(Engine(), ["EURUSD"])

    assert result == {"EURUSD": pytest.approx(1000.0)}


def test_research_usd_conversion_fails_closed_without_broker_money_math():
    class Engine:
        @staticmethod
        def symbol_spec(symbol):
            return {
                "trade_tick_value": 0.0,
                "trade_tick_size": 0.0,
                "volume_min": 0.01,
                "trade_contract_size": 0.0,
            }

    with pytest.raises(ValueError, match="USD conversion unavailable for EURUSD"):
        research_usd_per_price_unit_by_symbol(Engine(), ["EURUSD"])
