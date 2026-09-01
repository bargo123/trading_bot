from aegis.research.watcher_algorithms import evaluate_module


def _state(direction, price_change, volume_change):
    return {
        "side": "BUY" if direction == "up" else "SELL",
        "vpa_trend_direction": direction,
        "vpa_trend_price_change": price_change,
        "vpa_trend_volume_change": volume_change,
        "vpa_trend_bars": 4,
        "vpa_volume_provenance": "real traded volume aligned to completed bars",
    }


def test_vpa_trend_effort_confirms_price_direction_when_volume_expands():
    buy = evaluate_module("vpa_trend_effort_confirmation", _state("up", 0.01, 0.20))
    assert buy["view"] == "BUY"
    assert buy["vpa_trend_effort_assessment"] == "UPTREND_EFFORT_CONFIRMED"

    sell = evaluate_module("vpa_trend_effort_confirmation", _state("down", -0.01, 0.20))
    assert sell["view"] == "SELL"
    assert sell["vpa_trend_effort_assessment"] == "DOWNTREND_EFFORT_CONFIRMED"


def test_vpa_trend_effort_flags_price_volume_anomaly_instead_of_reversing_blindly():
    result = evaluate_module("vpa_trend_effort_confirmation", _state("up", 0.01, -0.20))
    assert result["view"] == "WAIT"
    assert result["vpa_trend_effort_assessment"] == "UPTREND_EFFORT_ANOMALY"
    assert result["directional_claim"] is False


def test_vpa_trend_effort_requires_real_traded_volume():
    result = evaluate_module(
        "vpa_trend_effort_confirmation",
        {**_state("up", 0.01, 0.20), "vpa_volume_provenance": "tick-volume proxy"},
    )
    assert result["view"] == "WAIT"
    assert "real traded volume" in " ".join(result["reasons"])
