from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


PROVENANCE = "observed timestamped quote data"


def test_aldridge_bid_ask_bounce_requires_filtering_before_using_tick_returns():
    contaminated = evaluate_module(
        "aldridge_bid_ask_bounce_filter",
        {
            "aldridge_bid_ask_bounce_detected": True,
            "aldridge_midquote_filter_applied": False,
            "aldridge_bid_ask_bounce_autocorrelation": -0.4,
            "aldridge_bid_ask_data_provenance": PROVENANCE,
        },
    )
    filtered = evaluate_module(
        "aldridge_bid_ask_bounce_filter",
        {
            "aldridge_bid_ask_bounce_detected": True,
            "aldridge_midquote_filter_applied": True,
            "aldridge_bid_ask_bounce_autocorrelation": -0.4,
            "aldridge_bid_ask_data_provenance": PROVENANCE,
        },
    )
    assert contaminated["aldridge_bounce_assessment"] == "BOUNCE_CONTAMINATION"
    assert filtered["aldridge_bounce_assessment"] == "FILTERED_BOUNCE"
    assert contaminated["directional_claim"] is False


def test_aldridge_duration_is_activity_context_and_never_a_directional_signal():
    short = evaluate_module(
        "aldridge_quote_duration",
        {
            "aldridge_interquote_duration_ms": 20,
            "aldridge_duration_baseline_ms": 100,
            "aldridge_duration_context": "activity_context_only",
            "aldridge_duration_data_provenance": PROVENANCE,
        },
    )
    long = evaluate_module(
        "aldridge_quote_duration",
        {
            "aldridge_interquote_duration_ms": 250,
            "aldridge_duration_baseline_ms": 100,
            "aldridge_duration_context": "activity_context_only",
            "aldridge_duration_data_provenance": PROVENANCE,
        },
    )
    assert short["aldridge_duration_assessment"] == "SHORT_DURATION_ACTIVITY"
    assert long["aldridge_duration_assessment"] == "LONG_DURATION_INACTIVITY"
    assert short["view"] == "WAIT"
    assert short["directional_claim"] is False


def test_aldridge_trade_direction_does_not_treat_tick_or_quote_inference_as_truth():
    inferred = evaluate_module(
        "aldridge_trade_direction_uncertainty",
        {
            "aldridge_trade_direction_available": True,
            "aldridge_trade_direction_method": "tick rule",
            "aldridge_trade_direction_data_provenance": PROVENANCE,
        },
    )
    observed = evaluate_module(
        "aldridge_trade_direction_uncertainty",
        {
            "aldridge_trade_direction_available": True,
            "aldridge_trade_direction_method": "exchange buyer seller identifier",
            "aldridge_trade_direction_data_provenance": PROVENANCE,
        },
    )
    assert inferred["aldridge_trade_direction_assessment"] == "INFERRED_DIRECTION_UNCERTAIN"
    assert observed["aldridge_trade_direction_assessment"] == "OBSERVED_DIRECTION"
    assert inferred["directional_claim"] is False


def test_aldridge_data_rules_fail_closed_on_missing_or_invalid_provenance():
    unavailable = evaluate_module(
        "aldridge_trade_direction_uncertainty",
        {
            "aldridge_trade_direction_available": True,
            "aldridge_trade_direction_method": "quote rule",
            "aldridge_trade_direction_data_provenance": "synthetic fixture",
        },
    )
    invalid = evaluate_module(
        "aldridge_bid_ask_bounce_filter",
        {
            "aldridge_bid_ask_bounce_detected": True,
            "aldridge_midquote_filter_applied": False,
            "aldridge_bid_ask_bounce_autocorrelation": -1.5,
            "aldridge_bid_ask_data_provenance": PROVENANCE,
        },
    )
    assert unavailable["view"] == "MISSING_DATA"
    assert invalid["view"] == "MISSING_DATA"

