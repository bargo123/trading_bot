from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


def test_dalton_day_structure_preserves_the_observed_profile_classification():
    result = evaluate_module(
        "dalton_day_structure",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "dalton_day_type": "normal variation day",
            "dalton_day_direction": "up",
            "dalton_initial_balance_range": 0.0010,
            "dalton_range_extension": 0.0018,
            "dalton_close_location_percent": 12.0,
            "dalton_extension_sides": "up",
            "dalton_data_provenance": "observed_completed_profile_periods",
        },
    )
    assert result["view"] == "WAIT"
    assert result["dalton_day_structure_classification"] == "NORMAL_VARIATION_DAY"
    assert result["dalton_extension_ratio"] == pytest.approx(1.8)


def test_dalton_failed_range_extension_fades_a_failed_up_or_down_auction():
    sell = evaluate_module(
        "dalton_failed_range_extension",
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "dalton_extension_direction": "up",
            "dalton_initial_balance_high": 1.1020,
            "dalton_initial_balance_low": 1.1000,
            "dalton_auction_point_price": 1.1021,
            "dalton_close_price": 1.1016,
            "dalton_failed_extension_confirmed": True,
            "dalton_data_provenance": "observed_completed_profile_periods",
        },
    )
    buy = evaluate_module(
        "dalton_failed_range_extension",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "dalton_extension_direction": "down",
            "dalton_initial_balance_high": 1.1020,
            "dalton_initial_balance_low": 1.1000,
            "dalton_auction_point_price": 1.0999,
            "dalton_close_price": 1.1004,
            "dalton_failed_extension_confirmed": True,
            "dalton_data_provenance": "observed_completed_profile_periods",
        },
    )
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"


def test_dalton_single_print_retest_requires_a_shallow_held_area():
    result = evaluate_module(
        "dalton_single_print_retest",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "dalton_single_print_origin": "up",
            "dalton_single_print_retrace_depth_percent": 25.0,
            "dalton_single_print_retest_is_shallow": True,
            "dalton_single_print_area_held": True,
            "dalton_single_print_close_direction": "up",
            "dalton_single_print_confirmed": True,
            "dalton_data_provenance": "observed_completed_profile_periods",
        },
    )
    assert result["view"] == "BUY"
    assert result["dalton_single_print_assessment"] == "SHALLOW_SUPPORT_RETEST"

    failed = dict(
        symbol="EURUSD",
        side="BUY",
        dalton_single_print_origin="up",
        dalton_single_print_retrace_depth_percent=75.0,
        dalton_single_print_retest_is_shallow=False,
        dalton_single_print_area_held=False,
        dalton_single_print_close_direction="down",
        dalton_single_print_confirmed=True,
        dalton_data_provenance="observed_completed_profile_periods",
    )
    assert evaluate_module("dalton_single_print_retest", failed)["view"] == "WAIT"
