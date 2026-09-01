"""Research candidate contract. Legacy 1/30 firehose is a benchmark, not a default."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis.sizing import ContractSpec, SizingDecision, size_lots_for_risk


class CandidateReject(ValueError):
    """Candidate is incomplete or uses the disallowed legacy payoff without evidence."""


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    regime: str
    timeframe: str
    data_requirements: tuple[str, ...]
    entry: str
    invalidation_stop: str
    risk_percent: float
    exit: str
    max_hold: str
    filters: tuple[str, ...] = ()
    correlation_caps: tuple[str, ...] = ()
    tp_pips: float | None = None
    sl_pips: float | None = None
    evidence_allows_legacy_payoff: bool = False
    label: str = "research_proxy"


def assert_candidate_complete(spec: CandidateSpec) -> None:
    required = (
        spec.name,
        spec.regime,
        spec.timeframe,
        spec.entry,
        spec.invalidation_stop,
        spec.exit,
        spec.max_hold,
    )
    if any(not str(v).strip() for v in required):
        raise CandidateReject("candidate missing required fields")
    if not spec.data_requirements:
        raise CandidateReject("candidate missing data_requirements")
    if spec.risk_percent <= 0:
        raise CandidateReject("risk_percent must be positive")
    if (
        spec.tp_pips == 1.0
        and spec.sl_pips == 30.0
        and not spec.evidence_allows_legacy_payoff
    ):
        raise CandidateReject("legacy 1/30 payoff is benchmark-only unless holdout evidence is attached")


def size_candidate(
    *,
    spec: CandidateSpec,
    equity: float,
    entry: float,
    stop: float,
    contract: ContractSpec,
) -> SizingDecision:
    assert_candidate_complete(spec)
    return size_lots_for_risk(
        equity=equity,
        risk_percent=spec.risk_percent,
        entry=entry,
        stop=stop,
        spec=contract,
    )
