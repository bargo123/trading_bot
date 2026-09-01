from aegis.research.watcher_algorithms import evaluate_module


def _record_state(**overrides):
    state = {
        "side": "BUY",
        "schwager_record_extreme": "new high",
        "schwager_record_extreme_held": True,
        "schwager_record_data_provenance": "observed chart bars",
    }
    state.update(overrides)
    return state


def _consolidation_state(**overrides):
    state = {
        "side": "BUY",
        "schwager_consolidation_location": "upper",
        "schwager_consolidation_narrow": True,
        "schwager_broader_range_context": True,
        "schwager_consolidation_data_provenance": "observed range chart",
    }
    state.update(overrides)
    return state


def _news_state(**overrides):
    state = {
        "side": "SELL",
        "schwager_news_direction": "bullish",
        "schwager_news_importance": "significant",
        "schwager_news_followthrough": False,
        "schwager_news_data_provenance": "observed timestamped news and price response",
    }
    state.update(overrides)
    return state


def test_schwager_record_extreme_hold_supports_continuation_on_both_sides():
    high = evaluate_module("schwager_record_extreme_continuation", _record_state())
    low = evaluate_module(
        "schwager_record_extreme_continuation",
        _record_state(side="SELL", schwager_record_extreme="new low"),
    )

    assert high["view"] == "BUY"
    assert low["view"] == "SELL"
    assert high["schwager_record_assessment"] == "HELD_RECORD_HIGH_CONTINUATION"
    assert high["execution_authority"] is False


def test_schwager_record_extreme_does_not_signal_without_hold_or_observed_data():
    not_held = evaluate_module(
        "schwager_record_extreme_continuation",
        _record_state(schwager_record_extreme_held=False),
    )
    synthetic = evaluate_module(
        "schwager_record_extreme_continuation",
        _record_state(schwager_record_data_provenance="synthetic chart"),
    )

    assert not_held["view"] == "WAIT"
    assert synthetic["view"] == "MISSING_DATA"


def test_schwager_narrow_consolidation_bias_uses_location_not_a_generic_range_signal():
    upper = evaluate_module("schwager_narrow_consolidation_bias", _consolidation_state())
    lower = evaluate_module(
        "schwager_narrow_consolidation_bias",
        _consolidation_state(side="SELL", schwager_consolidation_location="lower"),
    )
    broad = evaluate_module(
        "schwager_narrow_consolidation_bias",
        _consolidation_state(schwager_consolidation_narrow=False),
    )

    assert upper["view"] == "BUY"
    assert lower["view"] == "SELL"
    assert upper["schwager_consolidation_assessment"] == "UPPER_NARROW_BULLISH"
    assert broad["view"] == "WAIT"


def test_schwager_significant_news_non_followthrough_reverses_the_news_direction():
    result = evaluate_module("schwager_news_non_followthrough_reversal", _news_state())
    followed = evaluate_module(
        "schwager_news_non_followthrough_reversal",
        _news_state(schwager_news_followthrough=True),
    )

    assert result["view"] == "SELL"
    assert result["schwager_news_assessment"] == "BULLISH_NEWS_FAILURE_REVERSAL"
    assert followed["view"] == "WAIT"
