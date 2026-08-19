#!/usr/bin/env python3
"""Edge-derived clip sizing.

The property that matters: risk per clip is controlled, and lots follow from the
invalidation distance. A fixed lot size means a wide stop silently risks 10x what a
tight stop risks.
"""
from __future__ import annotations

import pytest

from aegis.intel.thesis_sizing import (
    SizingPlan,
    evidence_confidence,
    size_thesis_clip,
)

# Real MetaQuotes-Demo EURUSD spec: $100_000 per 1.0 of price, per lot.
EURUSD_SPEC = {
    "trade_tick_size": 0.00001,
    "trade_tick_value": 1.0,
    "trade_tick_value_loss": 1.0,
    "trade_contract_size": 100000.0,
    "volume_min": 0.01,
    "volume_step": 0.01,
    "volume_max": 100.0,
}
PIP = 0.0001


def _plan(**overrides) -> SizingPlan:
    kwargs = {
        "entry": 1.10000,
        "invalidation": 1.10000 - 20 * PIP,
        "spec": EURUSD_SPEC,
        "risk_budget_usd": 1000.0,
        "validated_risk_fraction": 0.08,
        "current_risk_usd": 0.0,
        "max_clips": 5,
        "confidence": 1.0,
        "hard_max_lots": 0.1,
    }
    kwargs.update(overrides)
    return size_thesis_clip(**kwargs)


def test_risk_per_clip_is_the_controlled_quantity():
    plan = _plan()
    # budget = 1000 * 0.08 = $80; one clip of five = $16.
    assert plan.risk_budget_usd == pytest.approx(80.0)
    assert plan.clip_budget_usd == pytest.approx(16.0)
    assert plan.allowed
    # 20 pips * $100_000/price = $200 loss per lot -> 16/200 = 0.08 lots.
    assert plan.lots == pytest.approx(0.08)
    assert plan.risk_usd == pytest.approx(16.0)


def test_wider_invalidation_gets_fewer_lots_for_the_same_risk():
    """The whole point: a fixed lot size makes a wide stop risk far more.

    ``hard_max_lots`` is lifted here so the risk-equalising behaviour is what is
    under test rather than the safety cap.
    """
    tight = _plan(invalidation=1.10000 - 5 * PIP, hard_max_lots=1.0)
    wide = _plan(invalidation=1.10000 - 50 * PIP, hard_max_lots=1.0)
    assert tight.lots > wide.lots
    # Risk lands just under the same $16 clip budget in both cases; the shortfall is
    # only lot-step rounding, which always floors. Fixed sizing cannot do this.
    for plan in (tight, wide):
        assert plan.risk_usd <= plan.clip_budget_usd + 1e-9
        assert plan.risk_usd == pytest.approx(16.0, abs=2.0)
    # A fixed 0.01-lot clip would instead have risked 10x more on the wide stop.
    assert (50 * PIP * 100000 * 0.01) == pytest.approx(10 * (5 * PIP * 100000 * 0.01))


def test_hard_max_lots_binding_reduces_risk_below_budget():
    """When the safety cap binds, it wins and risk lands under the clip budget."""
    capped = _plan(invalidation=1.10000 - 5 * PIP, hard_max_lots=0.1)
    assert capped.allowed
    assert capped.lots == pytest.approx(0.1)
    assert capped.risk_usd < capped.clip_budget_usd


def test_hard_max_lots_is_never_exceeded():
    plan = _plan(invalidation=1.10000 - 1 * PIP, hard_max_lots=0.1)
    assert plan.allowed
    assert plan.lots <= 0.1


def test_lots_snap_down_to_volume_step():
    plan = _plan(invalidation=1.10000 - 17 * PIP)
    # 16 / (0.0017 * 100000) = 0.0941... -> floors to 0.09, never rounds up.
    assert plan.lots == pytest.approx(0.09)
    assert plan.risk_usd <= plan.clip_budget_usd + 1e-9


def test_weak_evidence_produces_no_position_rather_than_a_gamble():
    """Padding up to the broker minimum would risk more than the edge earns."""
    plan = _plan(risk_budget_usd=10.0, validated_risk_fraction=0.01, invalidation=1.10000 - 50 * PIP)
    assert not plan.allowed
    assert plan.reason == "minimum_lot_exceeds_clip_budget"
    assert plan.lots == 0.0


def test_unvalidated_risk_fraction_is_refused():
    assert _plan(validated_risk_fraction=None).reason == "no_validated_risk_fraction"
    assert _plan(validated_risk_fraction=0.0).reason == "no_validated_risk_fraction"
    assert _plan(validated_risk_fraction=1.5).reason == "no_validated_risk_fraction"


def test_missing_invalidation_or_distance_is_refused():
    assert _plan(invalidation=None).reason == "no_structural_invalidation"
    assert _plan(invalidation=1.10000).reason == "no_invalidation_distance"


def test_missing_contract_value_is_refused_not_guessed():
    assert _plan(spec={}).reason == "contract_value_unavailable"


def test_existing_exposure_reduces_the_next_clip():
    fresh = _plan(current_risk_usd=0.0)
    partly = _plan(current_risk_usd=70.0)
    assert partly.clip_budget_usd < fresh.clip_budget_usd
    # Only $10 of the $80 budget is left, so the clip cannot exceed it.
    assert partly.clip_budget_usd == pytest.approx(10.0)


def test_thesis_at_target_exposure_takes_no_more():
    plan = _plan(current_risk_usd=80.0)
    assert not plan.allowed
    assert plan.reason == "thesis_at_target_exposure"


def test_confidence_haircut_scales_the_clip():
    full = _plan(confidence=1.0)
    half = _plan(confidence=0.5)
    assert half.clip_budget_usd == pytest.approx(full.clip_budget_usd * 0.5)
    assert half.lots < full.lots
    assert _plan(confidence=0.0).reason == "no_evidence_confidence"


def test_evidence_confidence_rewards_depth_and_rejects_uncalibrated():
    assert evidence_confidence(analogue_n=0, min_n=20) == 0.0
    assert evidence_confidence(analogue_n=19, min_n=20) == 0.0
    at_minimum = evidence_confidence(analogue_n=20, min_n=20)
    deep = evidence_confidence(analogue_n=200, min_n=20)
    assert 0 < at_minimum < deep <= 1.0
    # Uncalibrated evidence earns no size at all.
    assert evidence_confidence(analogue_n=500, min_n=20, uncertainty="insufficient_sample") == 0.0


def test_journal_payload_is_present():
    payload = _plan().journal()
    for key in ("size_ok", "size_reason", "size_lots", "size_risk_usd", "size_confidence"):
        assert key in payload
