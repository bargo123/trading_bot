from __future__ import annotations

from aegis.intel.capture_calibration import authorize_capture_probability


def test_authorization_uses_geometry_breakeven_not_fixed_probability_floor():
    low_payoff = authorize_capture_probability(
        successes=12,
        observations=20,
        breakeven_probability=0.20,
        evidence_source="measured_analogue",
        provenance="mt5_tick_replay",
    )
    high_payoff = authorize_capture_probability(
        successes=12,
        observations=20,
        breakeven_probability=0.70,
        evidence_source="measured_analogue",
        provenance="mt5_tick_replay",
    )

    assert low_payoff.required_probability == 0.20
    assert high_payoff.required_probability == 0.70
    assert low_payoff.lower_95 is not None
    assert low_payoff.authorized is True
    assert low_payoff.lower_95 >= low_payoff.required_probability
    assert high_payoff.lower_95 < high_payoff.required_probability
    assert high_payoff.authorized is False
    assert low_payoff.reason == "capture_probability_authorized"
    assert high_payoff.reason == "capture_probability_lcb_below_breakeven"


def test_high_payoff_does_not_rescue_a_thin_or_weak_capture_sample():
    result = authorize_capture_probability(
        successes=5,
        observations=20,
        breakeven_probability=0.20,
        evidence_source="measured_analogue",
        provenance="mt5_tick_replay",
    )

    assert result.authorized is False
    assert result.reason == "capture_probability_lcb_below_breakeven"
    assert result.probability == 0.25
    assert result.observations == 20


def test_insufficient_observations_fail_closed_even_when_point_estimate_is_high():
    result = authorize_capture_probability(
        successes=9,
        observations=10,
        breakeven_probability=0.20,
        evidence_source="measured_analogue",
        provenance="mt5_tick_replay",
    )

    assert result.authorized is False
    assert result.reason == "capture_evidence_insufficient"
    assert result.lower_95 is not None


def test_unmeasured_or_invalid_evidence_cannot_authorize_capture():
    for provenance in ("synthetic_proxy", "unknown"):
        result = authorize_capture_probability(
            successes=20,
            observations=20,
            breakeven_probability=0.20,
            evidence_source="analogue",
            provenance=provenance,
        )
        assert result.authorized is False
        assert result.reason == "capture_evidence_not_measured"

    invalid = authorize_capture_probability(
        successes=20,
        observations=20,
        breakeven_probability=None,
        evidence_source="measured_analogue",
        provenance="mt5_tick_replay",
    )
    assert invalid.authorized is False
    assert invalid.reason == "capture_breakeven_unavailable"
