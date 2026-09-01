from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Bob Volman — Forex Price Action Scalping"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "volman_data_provenance": "causal_quote_bar_proxy",
        "feature_provenance": {"volman": "causal_quote_bar_proxy"},
    }
    state.update(overrides)
    return state


def test_tipping_point_exit_uses_executable_side_and_does_not_guess_from_pnl():
    hold = evaluate_module(
        "volman_tipping_point_exit",
        _state(
            volman_tipping_point_price=1.1000,
            volman_current_exit_price=1.1001,
            volman_tipping_point_source="pullback_low",
            volman_tipping_point_activated=True,
        ),
    )
    assert hold["view"] == "WAIT"
    assert hold["volman_tipping_point_action"] == "HOLD_VALID_TIPPING_POINT"
    assert hold["execution_authority"] is False
    assert hold["source_books"] == [SOURCE]

    exit_result = evaluate_module(
        "volman_tipping_point_exit",
        _state(
            volman_tipping_point_price=1.1000,
            volman_current_exit_price=1.0999,
            volman_tipping_point_source="pullback_low",
            volman_tipping_point_activated=True,
        ),
    )
    assert exit_result["view"] == "WAIT"
    assert exit_result["volman_tipping_point_action"] == "EXIT_TIPPING_POINT_BREACHED"


def test_tipping_point_exit_reverses_orientation_for_sell_and_requires_activation():
    sell = evaluate_module(
        "volman_tipping_point_exit",
        _state(
            side="SELL",
            volman_tipping_point_price=1.1000,
            volman_current_exit_price=1.1001,
            volman_tipping_point_source="pullback_high",
            volman_tipping_point_activated=True,
        ),
    )
    assert sell["volman_tipping_point_action"] == "EXIT_TIPPING_POINT_BREACHED"

    inactive = evaluate_module(
        "volman_tipping_point_exit",
        _state(
            volman_tipping_point_price=1.1000,
            volman_current_exit_price=1.0999,
            volman_tipping_point_source="pullback_low",
            volman_tipping_point_activated=False,
        ),
    )
    assert inactive["volman_tipping_point_action"] == "WAIT_FOR_ACTIVATION"


def test_tipping_point_exit_fails_closed_without_technical_level_or_provenance():
    result = evaluate_module("volman_tipping_point_exit", _state())
    assert result["view"] == "MISSING_DATA"
    assert "volman_tipping_point_price" in result["missing_inputs"]
    assert result["execution_authority"] is False


def test_unfavorable_path_filter_requires_clear_room_and_no_visible_blocker():
    usable = evaluate_module(
        "volman_unfavorable_path_filter",
        _state(
            volman_market_favorable=True,
            volman_path_room_pips=12.0,
            volman_left_clustered=False,
            volman_resistance_blocking=False,
            volman_pressure_aligned=True,
        ),
    )
    assert usable["view"] == "BUY"
    assert usable["volman_path_assessment"] == "FAVORABLE_PATH"

    blocked = evaluate_module(
        "volman_unfavorable_path_filter",
        _state(
            volman_market_favorable=True,
            volman_path_room_pips=12.0,
            volman_left_clustered=False,
            volman_resistance_blocking=True,
            volman_pressure_aligned=True,
        ),
    )
    assert blocked["view"] == "WAIT"
    assert blocked["volman_path_assessment"] == "VISIBLE_BLOCKER"


def test_unfavorable_path_filter_rejects_thin_room_and_unfavorable_pressure():
    short_room = evaluate_module(
        "volman_unfavorable_path_filter",
        _state(
            volman_market_favorable=True,
            volman_path_room_pips=9.9,
            volman_left_clustered=False,
            volman_resistance_blocking=False,
            volman_pressure_aligned=True,
        ),
    )
    assert short_room["view"] == "WAIT"
    assert short_room["volman_path_assessment"] == "INSUFFICIENT_PATH_ROOM"

    bad_market = evaluate_module(
        "volman_unfavorable_path_filter",
        _state(
            volman_market_favorable=False,
            volman_path_room_pips=12.0,
            volman_left_clustered=False,
            volman_resistance_blocking=False,
            volman_pressure_aligned=False,
        ),
    )
    assert bad_market["view"] == "WAIT"
    assert bad_market["volman_path_assessment"] == "UNFAVORABLE_MARKET"


def test_pullback_quality_distinguishes_diagonal_from_clustered_continuation():
    good = evaluate_module(
        "volman_pullback_quality",
        _state(
            volman_trend="up",
            volman_pullback_style="diagonal",
            volman_pullback_fraction=0.40,
            volman_setup="second_break",
            volman_signal_direction="up",
        ),
    )
    assert good["view"] == "BUY"
    assert good["volman_pullback_assessment"] == "QUALITY_CONTINUATION_PULLBACK"

    weak = evaluate_module(
        "volman_pullback_quality",
        _state(
            volman_trend="up",
            volman_pullback_style="clustering",
            volman_pullback_fraction=0.20,
            volman_setup="double_doji_break",
            volman_signal_direction="up",
        ),
    )
    assert weak["view"] == "WAIT"
    assert weak["volman_pullback_assessment"] == "CLUSTERED_PULLBACK_CAUTION"


def test_pullback_quality_allows_thin_horizontal_action_only_within_the_trend():
    result = evaluate_module(
        "volman_pullback_quality",
        _state(
            side="SELL",
            volman_trend="down",
            volman_signal_direction="down",
            volman_pullback_style="thin_horizontal",
            volman_pullback_fraction=0.35,
            volman_setup="block_break",
        ),
    )
    assert result["view"] == "SELL"
    assert result["volman_pullback_assessment"] == "QUALITY_CONTINUATION_PULLBACK"
