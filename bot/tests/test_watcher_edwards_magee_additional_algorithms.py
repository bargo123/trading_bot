from aegis.research.watcher_algorithms import evaluate_module


def _breakout_state(**overrides):
    state = {
        "side": "BUY",
        "em_confirmation_break_direction": "up",
        "em_confirmation_close_confirmed": "confirmed",
        "em_confirmation_penetration_pct": 3.4,
        "em_confirmation_required_penetration_pct": 3.0,
        "em_confirmation_volume_required": True,
        "em_confirmation_volume_confirmed": "confirmed",
        "em_data_provenance": "observed completed chart bar",
        "em_volume_provenance": "real traded volume",
    }
    state.update(overrides)
    return state


def _climax_state(**overrides):
    state = {
        "side": "BUY",
        "em_climax_volume_ratio": 2.4,
        "em_climax_prior_peak_volume_ratio": 1.2,
        "em_climax_extreme_multiple": 1.5,
        "em_climax_reached_objective": True,
        "em_climax_outside_trend_channel": False,
        "em_climax_new_extreme_breakout": False,
        "em_climax_followthrough_volume": False,
        "em_data_provenance": "observed completed chart bar",
        "em_volume_provenance": "real traded volume",
    }
    state.update(overrides)
    return state


def _defensive_state(**overrides):
    state = {
        "side": "BUY",
        "em_defensive_adverse_signal": "basic trendline break",
        "em_defensive_signal_confirmed": "confirmed",
        "em_defensive_reversal_break_confirmed": False,
        "em_defensive_reversal_pattern": "none",
        "em_data_provenance": "observed completed chart bar",
    }
    state.update(overrides)
    return state


def test_edwards_magee_breakout_confirmation_requires_close_margin_and_volume_rule():
    buy = evaluate_module("edwards_magee_breakout_confirmation", _breakout_state())
    sell = evaluate_module(
        "edwards_magee_breakout_confirmation",
        _breakout_state(side="SELL", em_confirmation_break_direction="down"),
    )
    no_close = evaluate_module(
        "edwards_magee_breakout_confirmation",
        _breakout_state(em_confirmation_close_confirmed="unconfirmed"),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["edwards_magee_confirmation_assessment"] == "DECISIVE_BREAKOUT_CONFIRMED"
    assert no_close["view"] == "WAIT"
    assert no_close["edwards_magee_confirmation_assessment"] == "CLOSE_NOT_CONFIRMED"
    assert buy["execution_authority"] is False


def test_edwards_magee_breakout_confirmation_does_not_infer_missing_volume():
    narrow = evaluate_module(
        "edwards_magee_breakout_confirmation",
        _breakout_state(em_confirmation_penetration_pct=2.9),
    )
    no_volume = evaluate_module(
        "edwards_magee_breakout_confirmation",
        _breakout_state(em_confirmation_volume_confirmed="unconfirmed"),
    )
    no_real_volume = evaluate_module(
        "edwards_magee_breakout_confirmation",
        _breakout_state(em_volume_provenance="tick activity proxy"),
    )

    assert narrow["view"] == "WAIT"
    assert narrow["edwards_magee_confirmation_assessment"] == "DECISIVE_MARGIN_NOT_MET"
    assert no_volume["view"] == "WAIT"
    assert no_volume["edwards_magee_confirmation_assessment"] == "VOLUME_CONFIRMATION_NOT_MET"
    assert no_real_volume["view"] == "WAIT"
    assert no_real_volume["edwards_magee_confirmation_assessment"] == "REAL_VOLUME_UNAVAILABLE"


def test_edwards_magee_climactic_volume_requests_profit_protection():
    result = evaluate_module("edwards_magee_climactic_volume_stop", _climax_state())
    continuation_exception = evaluate_module(
        "edwards_magee_climactic_volume_stop",
        _climax_state(
            em_climax_reached_objective=False,
            em_climax_new_extreme_breakout=True,
            em_climax_followthrough_volume=False,
        ),
    )
    ordinary = evaluate_module(
        "edwards_magee_climactic_volume_stop",
        _climax_state(
            em_climax_volume_ratio=1.4,
            em_climax_reached_objective=False,
            em_climax_outside_trend_channel=False,
        ),
    )

    assert result["view"] == "WAIT"
    assert result["edwards_magee_climax_action"] == "PROTECT_PROFIT"
    assert result["directional_claim"] is False
    assert continuation_exception["edwards_magee_climax_action"] == "NEW_EXTREME_CONTINUATION_EXCEPTION"
    assert ordinary["edwards_magee_climax_action"] == "CONTINUE"


def test_edwards_magee_climax_is_fail_closed_for_invalid_or_nonreal_volume():
    invalid = evaluate_module(
        "edwards_magee_climactic_volume_stop",
        _climax_state(em_climax_extreme_multiple=0),
    )
    synthetic = evaluate_module(
        "edwards_magee_climactic_volume_stop",
        _climax_state(em_volume_provenance="synthetic"),
    )

    assert invalid["view"] == "WAIT"
    assert invalid["edwards_magee_climax_action"] == "INVALID_CLIMAX_INPUT"
    assert synthetic["applicability"] == "APPLICABLE"
    assert synthetic["edwards_magee_climax_action"] == "REAL_VOLUME_UNAVAILABLE"


def test_edwards_magee_separates_defensive_exit_from_an_opposite_entry():
    exit_only = evaluate_module("edwards_magee_defensive_exit", _defensive_state())
    reverse = evaluate_module(
        "edwards_magee_defensive_exit",
        _defensive_state(
            em_defensive_reversal_break_confirmed=True,
            em_defensive_reversal_pattern="rectangle",
        ),
    )
    unconfirmed = evaluate_module(
        "edwards_magee_defensive_exit",
        _defensive_state(em_defensive_signal_confirmed="unconfirmed"),
    )

    assert exit_only["view"] == "WAIT"
    assert exit_only["edwards_magee_defensive_action"] == "EXIT_CURRENT_COMMITMENT"
    assert exit_only["edwards_magee_reverse_candidate"] is False
    assert reverse["view"] == "SELL"
    assert reverse["edwards_magee_defensive_action"] == "EXIT_AND_REVERSE_CANDIDATE"
    assert reverse["edwards_magee_reverse_candidate"] is True
    assert unconfirmed["edwards_magee_defensive_action"] == "WAIT_FOR_CONFIRMATION"


def test_edwards_magee_defensive_exit_rejects_unknown_signals_and_missing_provenance():
    unknown = evaluate_module(
        "edwards_magee_defensive_exit",
        _defensive_state(em_defensive_adverse_signal="vague weakness"),
    )
    missing = evaluate_module(
        "edwards_magee_defensive_exit",
        _defensive_state(em_data_provenance="synthetic"),
    )

    assert unknown["view"] == "WAIT"
    assert unknown["edwards_magee_defensive_action"] == "INVALID_ADVERSE_SIGNAL"
    assert missing["applicability"] == "MISSING_DATA"
