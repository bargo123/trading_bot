"""Explainable research theses, calibrated evidence, and aggregate exposure policy.

Nothing here connects to MT5.  Exposure recommendations are research proxies and
require a validated risk policy before they can be considered for execution.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

from aegis.research.fingerprint import config_fingerprint

def thesis_information_id(
    *,
    symbol: str,
    side: str,
    setup: str,
    invalidation: str,
    htf_bucket: str = "",
    session: str = "",
) -> str:
    """Stable id for redundant information. Repeated EMA prints share this hash."""
    blob = "|".join(
        [
            str(symbol).upper(),
            str(side).lower(),
            " ".join(str(setup).lower().split()),
            " ".join(str(invalidation).lower().split()),
            str(htf_bucket),
            str(session),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class EvidenceItem:
    source: str
    concept: str
    supports: bool
    detail: str
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibratedEvidence:
    n: int
    expected_return: float | None
    mean_lower_95: float | None
    favorable_probability: float | None
    probability_lower_95: float | None
    downside_std: float | None
    uncertainty: str
    eligible: bool
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def calibrate_outcomes(outcomes: Sequence[float], *, min_samples: int = 20) -> CalibratedEvidence:
    """Estimate outcome uncertainty; absent data stays unavailable, never optimistic."""
    values = [float(value) for value in outcomes]
    n = len(values)
    if not n:
        return CalibratedEvidence(0, None, None, None, None, None, "no_observations", False)
    avg = mean(values)
    sigma = pstdev(values) if n > 1 else 0.0
    se = sigma / math.sqrt(n) if n > 1 else float("inf")
    lower = avg - 1.96 * se if math.isfinite(se) else None
    wins = sum(value > 0 for value in values)
    probability = wins / n
    # Wilson lower bound: reliability of the estimated favorable probability.
    z = 1.96
    denom = 1 + z * z / n
    centre = probability + z * z / (2 * n)
    spread = z * math.sqrt((probability * (1 - probability) + z * z / (4 * n)) / n)
    probability_lower = (centre - spread) / denom
    eligible = n >= min_samples and lower is not None and lower > 0
    uncertainty = (
        "insufficient_sample"
        if n < min_samples
        else "mean_not_positive_with_95_confidence"
        if lower is None or lower <= 0
        else "calibrated"
    )
    downside = [value for value in values if value < 0]
    return CalibratedEvidence(
        n=n,
        expected_return=avg,
        mean_lower_95=lower,
        favorable_probability=probability,
        probability_lower_95=probability_lower,
        downside_std=pstdev(downside) if len(downside) > 1 else None,
        uncertainty=uncertainty,
        eligible=eligible,
    )


@dataclass(frozen=True)
class Thesis:
    thesis_id: str
    symbol: str
    side: str
    setup: str
    market_state: Mapping[str, Any]
    supporting_evidence: tuple[EvidenceItem, ...]
    contradicting_evidence: tuple[EvidenceItem, ...]
    invalidation: str
    expected_duration: str
    calibrated_evidence: CalibratedEvidence
    book_provenance: tuple[Mapping[str, Any], ...] = ()
    historical_analogue_query: Mapping[str, Any] = field(default_factory=dict)
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "supporting_evidence": [asdict(item) for item in self.supporting_evidence],
            "contradicting_evidence": [asdict(item) for item in self.contradicting_evidence],
            "calibrated_evidence": self.calibrated_evidence.as_dict(),
        }


@dataclass(frozen=True)
class ExposureDecision:
    thesis_id: str
    action: str
    current_risk_usd: float
    target_risk_usd: float
    delta_risk_usd: float
    reason: str
    label: str = "research_proxy"


def target_thesis_exposure(
    *,
    thesis: Thesis,
    current_risk_usd: float,
    correlated_risk_usd: float,
    total_risk_budget_usd: float,
    validated_risk_fraction: float | None,
) -> ExposureDecision:
    """Allocate aggregate thesis risk only with calibrated edge and validated policy.

    `validated_risk_fraction` must be supplied by a separately validated candidate;
    this function deliberately refuses to invent a Kelly fraction or confidence score.
    """
    current = max(0.0, float(current_risk_usd))
    remaining = max(0.0, float(total_risk_budget_usd) - max(0.0, float(correlated_risk_usd)))
    evidence = thesis.calibrated_evidence
    if not evidence.eligible:
        return ExposureDecision(thesis.thesis_id, "reduce_or_wait", current, 0.0, -current, evidence.uncertainty)
    if validated_risk_fraction is None or not 0 < float(validated_risk_fraction) <= 1:
        return ExposureDecision(
            thesis.thesis_id,
            "wait",
            current,
            current,
            0.0,
            "no validated risk fraction attached to this thesis",
        )
    target = remaining * float(validated_risk_fraction)
    action = "increase" if target > current else "reduce" if target < current else "hold"
    return ExposureDecision(
        thesis.thesis_id,
        action,
        current,
        target,
        target - current,
        "calibrated lower confidence bound positive; aggregate exposure, not order count",
    )


def explain_thesis(thesis: Thesis, exposure: ExposureDecision) -> str:
    """Render an audit-friendly research decision without implying execution."""
    calibration = thesis.calibrated_evidence
    regime = thesis.market_state.get("regime", "unknown")
    if isinstance(regime, Mapping):
        regime = regime.get("label", "unknown")
    support = "; ".join(f"{item.source}: {item.detail}" for item in thesis.supporting_evidence) or "none"
    contradict = "; ".join(
        f"{item.source}: {item.detail}" for item in thesis.contradicting_evidence
    ) or "none"
    return "\n".join(
        [
            f"THESIS: {thesis.thesis_id}",
            f"DECISION: {exposure.action.upper()} (research-only; no order placed)",
            f"SETUP: {thesis.setup}",
            f"REGIME: {regime}",
            f"EVIDENCE: {support}",
            f"CONTRADICTING_EVIDENCE: {contradict}",
            f"BOOK_PROVENANCE: {len(thesis.book_provenance)} hashed source(s)",
            f"ESTIMATED_EDGE: {calibration.expected_return}",
            f"UNCERTAINTY: {calibration.uncertainty}; n={calibration.n}; lower95={calibration.mean_lower_95}",
            f"CURRENT_THESIS_RISK_USD: {exposure.current_risk_usd:.4f}",
            f"TARGET_THESIS_RISK_USD: {exposure.target_risk_usd:.4f}",
            f"INVALIDATION: {thesis.invalidation}",
            f"EXPECTED_DURATION: {thesis.expected_duration}",
        ]
    )


def thesis_experiment_row(
    *,
    thesis: Thesis,
    dataset_fingerprint: str,
    status: str = "open",
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    """Build append-only registry payload with state and book provenance intact."""
    state = dict(thesis.market_state)
    return {
        "id": thesis.thesis_id,
        "hypothesis": thesis.setup,
        "status": status,
        "config_fingerprint": config_fingerprint(
            {
                "thesis_id": thesis.thesis_id,
                "symbol": thesis.symbol,
                "side": thesis.side,
                "setup": thesis.setup,
                "invalidation": thesis.invalidation,
            }
        ),
        "dataset_fingerprint": dataset_fingerprint,
        "provenance": {
            "market_state": state,
            "book_provenance": list(thesis.book_provenance),
            "supporting_evidence": [asdict(item) for item in thesis.supporting_evidence],
            "contradicting_evidence": [asdict(item) for item in thesis.contradicting_evidence],
            "calibration": thesis.calibrated_evidence.as_dict(),
        },
        "params": {
            "expected_duration": thesis.expected_duration,
            "invalidation": thesis.invalidation,
            "label": thesis.label,
        },
        "rejection_reason": rejection_reason,
    }
