from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Andrew Aziz — How to Day Trade for a Living"


def _abcd(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aziz_abcd_impulse_direction": "up",
        "aziz_abcd_point_b_confirmed": True,
        "aziz_abcd_point_c_support": 1.1000,
        "aziz_abcd_c_support_holds": True,
        "aziz_abcd_entry_near_c": True,
        "aziz_abcd_stop_defined": True,
        "aziz_abcd_data_provenance": "causal_completed_quote_bar_proxy",
    }
    state.update(overrides)
    return state


def _flag(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aziz_bull_flag_pole_direction": "up",
        "aziz_bull_flag_consolidation": True,
        "aziz_bull_flag_consolidation_count": 1,
        "aziz_bull_flag_breakout_confirmation": True,
        "aziz_bull_flag_volume_confirmation": True,
        "aziz_bull_flag_stop_defined": True,
        "aziz_bull_flag_data_provenance": "causal_completed_quote_bar_proxy",
    }
    state.update(overrides)
    return state


def _red_to_green(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aziz_rtg_transition": "red_to_green",
        "aziz_rtg_previous_close": 1.1000,
        "aziz_rtg_moving_toward_level": True,
        "aziz_rtg_volume_confirmation": True,
        "aziz_rtg_stop_defined": True,
        "aziz_rtg_target_defined": True,
        "aziz_rtg_data_provenance": "causal_completed_quote_bar_proxy",
    }
    state.update(overrides)
    return state


def _bhod(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aziz_bhod_level": 1.1000,
        "aziz_bhod_break_direction": "up",
        "aziz_bhod_prior_level_touches": 2,
        "aziz_bhod_break_confirmation": True,
        "aziz_bhod_pullback_quality": "decent",
        "aziz_bhod_volume_confirmation": True,
        "aziz_bhod_stop_defined": True,
        "aziz_bhod_data_provenance": "causal_completed_quote_bar_proxy",
    }
    state.update(overrides)
    return state


def test_abcd_requires_an_impulse_support_hold_and_entry_near_c():
    result = evaluate_module("aziz_abcd_pattern", _abcd())

    assert result["view"] == "BUY"
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"aziz_abcd_impulse_direction": "down"},
        {"aziz_abcd_c_support_holds": False},
        {"aziz_abcd_entry_near_c": False},
        {"aziz_abcd_stop_defined": False},
    ],
)
def test_abcd_waits_when_the_source_setup_is_not_confirmed(overrides):
    result = evaluate_module("aziz_abcd_pattern", _abcd(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_bull_flag_requires_first_or_second_consolidation_and_breakout():
    result = evaluate_module("aziz_bull_flag_momentum", _flag())

    assert result["view"] == "BUY"
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"aziz_bull_flag_consolidation_count": 3},
        {"aziz_bull_flag_breakout_confirmation": False},
        {"aziz_bull_flag_volume_confirmation": False},
        {"aziz_bull_flag_pole_direction": "down"},
    ],
)
def test_bull_flag_waits_for_a_fresh_confirmed_breakout(overrides):
    result = evaluate_module("aziz_bull_flag_momentum", _flag(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize(
    ("transition", "side", "expected"),
    [("red_to_green", "BUY", "BUY"), ("green_to_red", "SELL", "SELL")],
)
def test_red_to_green_uses_previous_close_as_a_directional_level(transition, side, expected):
    result = evaluate_module(
        "aziz_red_to_green",
        _red_to_green(aziz_rtg_transition=transition, side=side),
    )

    assert result["view"] == expected
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]


def test_red_to_green_waits_without_volume_or_defined_exit_plan():
    result = evaluate_module(
        "aziz_red_to_green",
        _red_to_green(aziz_rtg_volume_confirmation=False, aziz_rtg_target_defined=False),
    )

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_bhod_requires_repeated_level_tests_and_confirmed_break():
    result = evaluate_module("aziz_bhod", _bhod())

    assert result["view"] == "BUY"
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]


@pytest.mark.parametrize(
    "overrides",
    [
        {"aziz_bhod_prior_level_touches": 1},
        {"aziz_bhod_break_confirmation": False},
        {"aziz_bhod_pullback_quality": "poor"},
        {"aziz_bhod_volume_confirmation": False},
    ],
)
def test_bhod_waits_when_break_quality_is_not_observed(overrides):
    result = evaluate_module("aziz_bhod", _bhod(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


@pytest.mark.parametrize(
    "algorithm_id",
    ["aziz_abcd_pattern", "aziz_bull_flag_momentum", "aziz_red_to_green", "aziz_bhod"],
)
def test_aziz_algorithms_fail_closed_without_causal_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _premarket_gapper(**overrides):
    state = {
        "symbol": "ABC",
        "aziz_asset_class": "equity",
        "aziz_gap_percent": 2.4,
        "aziz_premarket_volume": 50_000,
        "aziz_average_daily_volume": 500_000,
        "aziz_atr_usd": 0.50,
        "aziz_fundamental_catalyst": "earnings",
        "aziz_short_interest_percent": 22.0,
        "aziz_stock_scanner_data_provenance": "observed",
    }
    state.update(overrides)
    return state


def test_aziz_premarket_gapper_requires_the_book_scanner_inputs():
    result = evaluate_module("aziz_premarket_gapper_scanner", _premarket_gapper())

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "WAIT"
    assert result["aziz_premarket_scanner_assessment"] == "STOCK_IN_PLAY"
    assert result["aziz_premarket_gap_direction"] == "UP"
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("aziz_gap_percent", 1.9, "gap_below_two_percent"),
        ("aziz_premarket_volume", 49_999, "premarket_volume_below_50000"),
        ("aziz_average_daily_volume", 499_999, "average_volume_below_500000"),
        ("aziz_atr_usd", 0.49, "atr_below_fifty_cents"),
        ("aziz_fundamental_catalyst", "none", "fundamental_catalyst_missing"),
        ("aziz_short_interest_percent", 30.1, "short_interest_above_thirty_percent"),
    ],
)
def test_aziz_premarket_gapper_reports_each_failed_source_filter(field, value, failure):
    result = evaluate_module("aziz_premarket_gapper_scanner", _premarket_gapper(**{field: value}))

    assert result["aziz_premarket_scanner_assessment"] == "SCANNER_FILTER_FAILED"
    assert failure in result["aziz_premarket_scanner_failures"]
    assert result["view"] == "WAIT"


def test_aziz_premarket_gapper_is_equity_only_and_fail_closed_on_proxy_data():
    not_applicable = evaluate_module("aziz_premarket_gapper_scanner", _premarket_gapper(aziz_asset_class="forex"))
    proxy = evaluate_module(
        "aziz_premarket_gapper_scanner",
        _premarket_gapper(aziz_stock_scanner_data_provenance="synthetic_fixture"),
    )

    assert not_applicable["applicability"] == "NOT_APPLICABLE"
    assert not_applicable["view"] == "WAIT"
    assert proxy["applicability"] == "MISSING_DATA"
    assert "aziz_stock_scanner_data_provenance" in proxy["missing_inputs"]


def _relative_volume_independence(**overrides):
    state = {
        "symbol": "ABC",
        "aziz_asset_class": "equity",
        "aziz_relative_volume": 1.7,
        "aziz_market_independence": True,
        "aziz_sector_independence": True,
        "aziz_stock_scanner_data_provenance": "observed",
    }
    state.update(overrides)
    return state


def test_aziz_relative_volume_independence_requires_both_independence_checks():
    result = evaluate_module("aziz_relative_volume_independence", _relative_volume_independence())
    dependent = evaluate_module(
        "aziz_relative_volume_independence",
        _relative_volume_independence(aziz_sector_independence=False),
    )

    assert result["aziz_independence_assessment"] == "STOCK_IN_PLAY"
    assert result["view"] == "WAIT"
    assert dependent["aziz_independence_assessment"] == "NOT_INDEPENDENT"
    assert "sector_not_independent" in dependent["aziz_independence_failures"]


def test_aziz_relative_volume_independence_rejects_non_equity_and_low_relative_volume():
    not_applicable = evaluate_module(
        "aziz_relative_volume_independence",
        _relative_volume_independence(aziz_asset_class="forex"),
    )
    low_volume = evaluate_module(
        "aziz_relative_volume_independence",
        _relative_volume_independence(aziz_relative_volume=1.49),
    )

    assert not_applicable["applicability"] == "NOT_APPLICABLE"
    assert low_volume["aziz_independence_assessment"] == "RELATIVE_VOLUME_LOW"
    assert low_volume["view"] == "WAIT"


def _reversal_context(**overrides):
    state = {
        "symbol": "ABC",
        "side": "BUY",
        "aziz_reversal_setup": "bottom",
        "aziz_market_reversal_context": "mixed",
        "aziz_sector_reversal_context": "against_underlying_move",
        "aziz_reversal_context_data_provenance": "observed",
    }
    state.update(overrides)
    return state


def test_aziz_reversal_context_supports_a_bottom_reversal_when_broad_context_is_not_aligned_against_it():
    result = evaluate_module("aziz_reversal_market_context", _reversal_context())

    assert result["aziz_reversal_context_assessment"] == "CONTEXT_SUPPORTS_REVERSAL"
    assert result["view"] == "WAIT"
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    ("setup", "market", "sector"),
    [
        ("bottom", "with_underlying_move", "with_underlying_move"),
        ("top", "with_underlying_move", "with_underlying_move"),
    ],
)
def test_aziz_reversal_context_warns_when_both_broad_contexts_move_with_the_underlying_move(
    setup, market, sector
):
    result = evaluate_module(
        "aziz_reversal_market_context",
        _reversal_context(
            side="BUY" if setup == "bottom" else "SELL",
            aziz_reversal_setup=setup,
            aziz_market_reversal_context=market,
            aziz_sector_reversal_context=sector,
        ),
    )

    assert result["aziz_reversal_context_assessment"] == "REVERSAL_CONTEXT_CONFLICT"
    assert result["view"] == "WAIT"
    assert result["reasons"]


def _orb(**overrides):
    state = {
        "symbol": "ABC",
        "side": "BUY",
        "aziz_orb_range_minutes": 5,
        "aziz_orb_high": 10.05,
        "aziz_orb_low": 10.00,
        "aziz_orb_atr": 0.20,
        "aziz_orb_price": 10.08,
        "aziz_orb_break_direction": "up",
        "aziz_orb_break_confirmed": True,
        "aziz_orb_vwap": 10.03,
        "aziz_orb_data_provenance": "observed",
    }
    state.update(overrides)
    return state


def test_aziz_orb_is_a_directional_entry_signal_with_vwap_invalidation_not_a_fabricated_target():
    result = evaluate_module("aziz_opening_range_breakout", _orb())

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "BUY"
    assert result["aziz_orb_signal_role"] == "ENTRY_ONLY_NO_TARGET"
    assert result["aziz_orb_invalidation"] == "CLOSE_BELOW_VWAP"
    assert "target" not in result
    assert result["execution_authority"] is False


def test_aziz_orb_supports_the_short_direction_with_the_opposite_vwap_invalidation():
    result = evaluate_module(
        "aziz_opening_range_breakout",
        _orb(
            side="SELL",
            aziz_orb_price=9.96,
            aziz_orb_break_direction="down",
            aziz_orb_vwap=9.98,
        ),
    )

    assert result["view"] == "SELL"
    assert result["aziz_orb_invalidation"] == "CLOSE_ABOVE_VWAP"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("aziz_orb_break_confirmed", False),
        ("aziz_orb_break_direction", "down"),
        ("aziz_orb_price", 10.04),
        ("aziz_orb_vwap", 10.09),
        ("aziz_orb_atr", 0.05),
    ],
)
def test_aziz_orb_waits_when_entry_or_vwap_geometry_is_not_confirmed(field, value):
    result = evaluate_module("aziz_opening_range_breakout", _orb(**{field: value}))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_aziz_orb_fail_closes_without_causal_provenance():
    result = evaluate_module(
        "aziz_opening_range_breakout",
        _orb(aziz_orb_data_provenance="synthetic_fixture"),
    )

    assert result["applicability"] == "MISSING_DATA"
    assert "aziz_orb_data_provenance" in result["missing_inputs"]
